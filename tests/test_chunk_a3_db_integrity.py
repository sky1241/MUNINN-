"""CHUNK A3 — PRAGMA integrity_check au boot mycelium.

Sans integrity_check, une mycelium.db corrompue (fsync issue, ext4 bug,
kill -9 pendant un commit, disk full) reste utilisable mais retourne
des données incohérentes. bridge_fast() catch la silencieuse via generic
except → user ne sait jamais que mycelium est cassé.

Fix: helper public `check_integrity()` qui run PRAGMA integrity_check
+ PRAGMA wal_checkpoint(RESTART). Caller (doctor, boot) décide de raise
ou warn.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A3
"""
import sqlite3
import sys
from pathlib import Path

import pytest

# BUG-091 shim/path collision: when other tests load engine/core/mycelium_db
# under the bare name, `from muninn.mycelium_db import` triggers a circular
# import in the shim. Workaround: load the module under a unique name via
# importlib.util.spec_from_file_location so it never collides.
def _load_mycelium_db_class():
    """Load MyceliumDB class from engine/core/mycelium_db.py under a unique name."""
    repo = Path(__file__).resolve().parent.parent
    engine_core = repo / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    import importlib.util
    src = engine_core / "mycelium_db.py"
    spec = importlib.util.spec_from_file_location("_chunk_a3_isolated_mycelium_db", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MyceliumDB


def test_check_integrity_returns_ok_on_fresh_db(tmp_path):
    """Fresh empty DB must report integrity OK."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "fresh.db")
    assert hasattr(db, "check_integrity"), \
        "check_integrity missing — should be on MyceliumDB since chunk a3 fix"
    ok, msg = db.check_integrity()
    assert ok is True, f"Fresh DB reported corrupt: {msg}"
    assert msg == "ok"


def test_check_integrity_after_writes(tmp_path):
    """DB with writes must still report OK after checkpoint."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "with_writes.db")
    assert hasattr(db, "check_integrity"), \
        "check_integrity missing — should be on MyceliumDB since chunk a3 fix"
    db.set_meta("test_key", "test_value")
    db.set_meta("counter", "42")
    ok, msg = db.check_integrity()
    assert ok is True, f"DB with writes reported corrupt: {msg}"


def test_check_integrity_detects_garbage_file(tmp_path):
    """A non-SQLite file at db_path must fail integrity check.

    Note: sqlite3.connect() may not raise on garbage; integrity_check is
    the layer that catches it.
    """
    MyceliumDB = _load_mycelium_db_class()
    bad = tmp_path / "garbage.db"
    bad.write_bytes(b"NOT A SQLITE FILE - JUST BYTES" * 10)

    # MyceliumDB init may fail (raise) OR succeed but integrity check fails.
    # Both are acceptable — what matters is we don't continue with corrupt data.
    try:
        db = MyceliumDB(bad)
        assert hasattr(db, "check_integrity"), \
            "check_integrity missing — should be on MyceliumDB since chunk a3 fix"
        ok, msg = db.check_integrity()
        assert ok is False, "Garbage file passed integrity check (it should not)"
        assert msg != "ok"
    except sqlite3.DatabaseError:
        # Acceptable: sqlite3 itself rejected the file at connect time
        pass


def test_check_integrity_detects_truncated(tmp_path):
    """A truncated DB (mid-write kill simulation) must fail integrity."""
    MyceliumDB = _load_mycelium_db_class()

    # Create a valid DB then truncate it
    good = tmp_path / "good.db"
    db = MyceliumDB(good)
    assert hasattr(db, "check_integrity"), \
        "check_integrity missing — should be on MyceliumDB since chunk a3 fix"

    # Force some content
    for i in range(10):
        db.set_meta(f"k{i}", f"v{i}")
    db.checkpoint_wal()

    # Sanity: full DB still ok
    ok, _ = db.check_integrity()
    assert ok is True

    # Close + truncate to first 1024 bytes (enough for header but not full DB)
    db._conn.close()
    full_size = good.stat().st_size
    if full_size <= 1024:
        pytest.skip("DB too small to meaningfully truncate")
    with open(good, "r+b") as f:
        f.truncate(1024)

    # Re-open. Either init fails OR check_integrity fails.
    try:
        db2 = MyceliumDB(good)
        ok, msg = db2.check_integrity()
        assert ok is False, f"Truncated DB passed integrity check: {msg}"
    except sqlite3.DatabaseError:
        # Acceptable
        pass


def test_check_integrity_runs_wal_checkpoint(tmp_path):
    """Calling check_integrity should trigger a WAL checkpoint (merge WAL into main DB)."""
    MyceliumDB = _load_mycelium_db_class()
    db = MyceliumDB(tmp_path / "wal_check.db")
    assert hasattr(db, "check_integrity"), \
        "check_integrity missing — should be on MyceliumDB since chunk a3 fix"
    # Write something to ensure WAL has data
    db.set_meta("checkpoint_test", "1")
    ok, _ = db.check_integrity()
    assert ok is True
    # We don't assert on WAL file size (sqlite manages it) but the call
    # itself should not raise.
