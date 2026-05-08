"""CHUNK A5 — lock SQLite reads + migration in MyceliumDB.

`set_meta` and `_get_or_create_concept` use `with self._lock:` correctly,
but read-side functions (`get_meta`, `get_connection`, `get_all_*`,
`connection_count`, `has_*`) and `_migrate_schema` execute SELECT/UPDATE
without holding the lock. Under concurrency, this allows readers to see
mid-commit state, and 2 processes opening the same DB can race on
migration.

Fix: wrap each affected method body with `with self._lock:`.

This file uses an isolated importlib.util load (same workaround as A3)
to avoid BUG-091 shim circular imports under combined test runs.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A5
"""
import sys
import threading
from pathlib import Path

import pytest


def _load_mycelium_db_class():
    """Isolated load of engine/core/mycelium_db.py (BUG-091 workaround)."""
    repo = Path(__file__).resolve().parent.parent
    engine_core = repo / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    import importlib.util
    src = engine_core / "mycelium_db.py"
    spec = importlib.util.spec_from_file_location("_chunk_a5_mycelium_db", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MyceliumDB


def test_concurrent_get_set_meta_no_corruption(tmp_path):
    """Concurrent get_meta/set_meta on the same DB must not raise."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "concurrent.db")

    errors = []
    stop_flag = [False]

    def writer():
        i = 0
        while not stop_flag[0] and i < 200:
            try:
                db.set_meta(f"k{i % 20}", str(i))
            except Exception as e:
                errors.append(("w", repr(e)))
            i += 1

    def reader():
        i = 0
        while not stop_flag[0] and i < 200:
            try:
                db.get_meta(f"k{i % 20}")
            except Exception as e:
                errors.append(("r", repr(e)))
            i += 1

    threads = (
        [threading.Thread(target=writer) for _ in range(2)]
        + [threading.Thread(target=reader) for _ in range(4)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    stop_flag[0] = True
    assert not errors, f"{len(errors)} errors during concurrency, e.g. {errors[:3]}"


def test_concurrent_has_connection_no_crash(tmp_path):
    """Concurrent observe + has_connection must not crash."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "has_conn.db")

    # Pre-populate some concepts
    for i in range(10):
        db._get_or_create_concept(f"c{i}")

    errors = []

    def writer():
        for i in range(100):
            try:
                a, b = f"c{i % 10}", f"c{(i + 1) % 10}"
                with db.transaction() as conn:
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    a_key, b_key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                    conn.execute(
                        "INSERT OR IGNORE INTO edges (a, b, count, first_seen, last_seen) "
                        "VALUES (?, ?, 1, 0, 0)",
                        (a_key, b_key)
                    )
            except Exception as e:
                errors.append(("w", repr(e)))

    def reader():
        for i in range(100):
            try:
                db.has_connection(f"c{i % 10}", f"c{(i + 1) % 10}")
                db.connection_count()
            except Exception as e:
                errors.append(("r", repr(e)))

    threads = (
        [threading.Thread(target=writer) for _ in range(2)]
        + [threading.Thread(target=reader) for _ in range(4)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"{len(errors)} errors, e.g. {errors[:3]}"


def test_concurrent_get_all_connections_consistent(tmp_path):
    """Concurrent reads of get_all_connections must complete without crashing."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "get_all.db")

    # Pre-populate
    for i in range(20):
        db._get_or_create_concept(f"c{i}")

    errors = []

    def writer():
        for i in range(50):
            try:
                a, b = f"c{i % 20}", f"c{(i + 7) % 20}"
                with db.transaction() as conn:
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    a_key, b_key = (a_id, b_id) if a_id < b_id else (b_id, a_id)
                    conn.execute(
                        "INSERT OR IGNORE INTO edges (a, b, count, first_seen, last_seen) "
                        "VALUES (?, ?, 1, 0, 0)",
                        (a_key, b_key)
                    )
            except Exception as e:
                errors.append(("w", repr(e)))

    def reader():
        for _ in range(20):
            try:
                conns = db.get_all_connections()
                assert isinstance(conns, dict)
            except Exception as e:
                errors.append(("r", repr(e)))

    threads = (
        [threading.Thread(target=writer) for _ in range(2)]
        + [threading.Thread(target=reader) for _ in range(2)]
    )
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"{len(errors)} errors, e.g. {errors[:3]}"


def test_get_meta_set_meta_basic_correctness(tmp_path):
    """Sanity: lock changes must not break basic get/set semantics."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "basic.db")
    db.set_meta("foo", "bar")
    assert db.get_meta("foo") == "bar"
    db.set_meta("foo", "baz")
    assert db.get_meta("foo") == "baz"
    assert db.get_meta("missing", default="DEFAULT") == "DEFAULT"


def test_has_connection_returns_bool_after_lock_added(tmp_path):
    """Sanity: has_connection still returns the expected booleans."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "has_bool.db")
    db._get_or_create_concept("alpha")
    db._get_or_create_concept("beta")
    assert db.has_connection("alpha", "beta") is False
    # Insert an edge and verify
    a = db._concept_cache["alpha"]
    b = db._concept_cache["beta"]
    a_key, b_key = (a, b) if a < b else (b, a)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, 1, 0, 0)",
            (a_key, b_key)
        )
    assert db.has_connection("alpha", "beta") is True
