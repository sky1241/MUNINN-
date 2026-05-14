"""Phase 3 (2026-05-14) — observe_failure + table failures + penalty.

Validates:
  - Schema migration v3 → v4 adds `failures` table
  - Mycelium.observe_failure(text, weight=-0.5) writes pairs to that table
  - observe_text + observe_failure are isolated (edges vs failures)
  - Spreading activation applies failure penalty to lower-ranked concepts
  - Auto-calibration via MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE recomputes
  - Batched DB query is fast (<100ms for 100 concepts)
  - Bug #2101 (mycelium.observe(text, zone=) iterating chars) fixed
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine" / "core"))

from engine.core.mycelium import Mycelium  # noqa: E402
from engine.core.mycelium_db import MyceliumDB  # noqa: E402


def _make_sqlite_mycelium(tmp_path: Path) -> Mycelium:
    """Force a fresh SQLite-backed Mycelium under tmp_path."""
    db_path = tmp_path / ".muninn" / "mycelium.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_init = MyceliumDB(db_path)
    db_init._conn.execute(
        "INSERT INTO meta (key, value) VALUES ('migration_complete', '1')")
    db_init._conn.commit()
    db_init.close()
    return Mycelium(tmp_path)


# ─── A. Schema + migration ────────────────────────────────────────────


def test_failures_table_created_at_boot(tmp_path):
    """v4+: new DB has the failures table immediately."""
    db = MyceliumDB(tmp_path / "fresh.db")
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "failures" in tables
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 4  # bumped to 5 in K.2 (concept_embeddings)
    db.close()


def test_failures_table_has_required_indexes(tmp_path):
    db = MyceliumDB(tmp_path / "fresh.db")
    indexes = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_failures_a" in indexes
    assert "idx_failures_b" in indexes
    assert "idx_failures_last_seen" in indexes
    db.close()


def test_failures_table_migration_v3_to_v4(tmp_path):
    """Old DB at v3 gets the failures table added on next open."""
    db_path = tmp_path / "old.db"
    db = MyceliumDB(db_path)
    # Simulate a pre-v4 DB by dropping the table and forcing user_version=3
    db._conn.execute("DROP TABLE IF EXISTS failures")
    db._conn.execute("PRAGMA user_version = 3")
    db._conn.commit()
    db.close()
    # Re-open → migration v3 → v4 should restore the table
    db2 = MyceliumDB(db_path)
    tables = {r[0] for r in db2._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "failures" in tables
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] >= 4
    db2.close()


# ─── B. Batch DB methods ──────────────────────────────────────────────


def test_upsert_failure_creates_row(tmp_path):
    db = MyceliumDB(tmp_path / "test.db")
    db.upsert_failure("foo", "bar", weight=-0.5)
    row = db._conn.execute(
        "SELECT count, weight_sum FROM failures").fetchone()
    assert row == (1, -0.5)
    db.close()


def test_upsert_failure_increments_and_accumulates(tmp_path):
    db = MyceliumDB(tmp_path / "test.db")
    db.upsert_failure("foo", "bar", weight=-0.5)
    db.upsert_failure("foo", "bar", weight=-0.5)
    db.upsert_failure("foo", "bar", weight=-0.3)
    row = db._conn.execute(
        "SELECT count, weight_sum FROM failures").fetchone()
    assert row[0] == 3
    assert abs(row[1] - (-1.3)) < 1e-6
    db.close()


def test_upsert_failure_order_independent(tmp_path):
    db = MyceliumDB(tmp_path / "test.db")
    db.upsert_failure("alpha", "beta", weight=-0.5)
    db.upsert_failure("beta", "alpha", weight=-0.5)  # reversed
    n_rows = db._conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
    assert n_rows == 1


def test_get_failure_weight_returns_sum(tmp_path):
    db = MyceliumDB(tmp_path / "test.db")
    db.upsert_failure("foo", "bar", weight=-0.5)
    db.upsert_failure("foo", "baz", weight=-0.3)
    assert abs(db.get_failure_weight("foo") - (-0.8)) < 1e-6
    assert abs(db.get_failure_weight("bar") - (-0.5)) < 1e-6
    assert db.get_failure_weight("notpresent") == 0.0


def test_get_failure_weights_batch_perf(tmp_path):
    """Audit critical: batch must finish under 100ms for 100 concepts.
    Sequential per-concept was estimated at ~500ms (forbidden)."""
    db = MyceliumDB(tmp_path / "test.db")
    concepts = [f"concept{i}" for i in range(100)]
    for i in range(0, 100, 2):
        db.upsert_failure(concepts[i], concepts[i + 1], weight=-0.5)
    t0 = time.time()
    result = db.get_failure_weights_batch(concepts)
    elapsed_ms = (time.time() - t0) * 1000
    assert elapsed_ms < 100, f"batch took {elapsed_ms:.1f}ms (target <100ms)"
    assert len(result) > 0


# ─── C. Mycelium.observe_failure ──────────────────────────────────────


def test_observe_failure_records_pairs(tmp_path):
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_failure("mutex logger reconstruct cube")
    n = m._db._conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
    assert n > 0  # at least one pair stored


def test_observe_failure_session_dedup(tmp_path):
    """Calling observe_failure twice in the same session does NOT double-write."""
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_failure("mutex logger panic")
    w1 = m._db.get_failure_weight("mutex")
    m.observe_failure("mutex logger panic")  # dupe in same session
    w2 = m._db.get_failure_weight("mutex")
    assert w2 == w1, "session dedup should suppress identical re-observe"


def test_observe_failure_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNINN_OBSERVE_FAILURE_WEIGHT", "-1.5")
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_failure("unique alphabet beta gamma")
    w = m._db.get_failure_weight("alphabet")
    # 4 concepts → 3 pairs involving alphabet, each at -1.5 → -4.5
    assert w < -2.0, f"env override should give strong negative (got {w})"


def test_observe_failure_positive_weight_clamped(tmp_path):
    """Safety: passing a positive weight clamps to 0 (logic guard)."""
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_failure("alpha beta gamma delta", weight=+0.5)
    assert m._db.get_failure_weight("alpha") == 0.0


def test_observe_failure_does_not_touch_edges_table(tmp_path):
    """Isolation: observe_failure writes to failures, NEVER edges."""
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_failure("alpha beta gamma delta epsilon")
    n_edges = m._db._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    assert n_edges == 0


def test_observe_text_does_not_touch_failures_table(tmp_path):
    """Inverse isolation: observe_text writes to edges, NEVER failures."""
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_text("alpha beta gamma delta epsilon")
    n_failures = m._db._conn.execute(
        "SELECT COUNT(*) FROM failures").fetchone()[0]
    assert n_failures == 0


# ─── D. spread_activation + flag ──────────────────────────────────────


def test_spread_activation_penalizes_failed_concept(tmp_path):
    """A concept with strong failure weight is pushed down the ranking."""
    m = _make_sqlite_mycelium(tmp_path)
    # seedword connected to both goodthing and badthing via observe_text
    m.observe_text("seedword goodthing helpful useful")
    m.observe_text("seedword badthing useful needed")
    # badthing acquires heavy failure weight
    for i in range(20):
        m._session_seen.clear()
        m.observe_failure(f"badthing toxic broken crash{i}")
    res_with = m.spread_activation(["seedword"], hops=2, top_n=10)
    res_without = m.spread_activation(
        ["seedword"], hops=2, top_n=10, apply_failure_penalty=False)
    bad_with = dict(res_with).get("badthing", 0)
    bad_without = dict(res_without).get("badthing", 0)
    assert bad_with < bad_without, (
        f"penalty should LOWER badthing: with={bad_with} >= without={bad_without}")


def test_spread_activation_backward_compat_no_penalty_no_table(tmp_path):
    """apply_failure_penalty=True must NOT crash if failures table empty."""
    m = _make_sqlite_mycelium(tmp_path)
    m.observe_text("alpha beta gamma delta")
    # No observe_failure called → failures table is empty
    res = m.spread_activation(["alpha"], hops=2, top_n=10)
    assert isinstance(res, list)  # just must not crash


# ─── E. Auto-calibration ──────────────────────────────────────────────


def test_auto_calibration_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE", raising=False)
    m = _make_sqlite_mycelium(tmp_path)
    assert m._auto_cal_enabled is False


def test_auto_calibration_recomputes_weight_after_50_obs(tmp_path, monkeypatch):
    """After 50+ observations with > 100 total edges+failures,
    a JSON calibration file appears and persists."""
    monkeypatch.setenv("MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE", "1")
    m = _make_sqlite_mycelium(tmp_path)
    rnd = random.Random(42)
    pool = ["".join(rnd.choices(string.ascii_lowercase, k=8))
            for _ in range(200)]
    for _ in range(60):
        m.observe_text(" ".join(rnd.sample(pool, 8)))
    for _ in range(60):
        m._session_seen.clear()
        m.observe_failure(" ".join(rnd.sample(pool, 8)))
    assert m._failure_calibrated_weight is not None
    assert -1.0 <= m._failure_calibrated_weight <= -0.05
    calib_path = tmp_path / ".muninn" / "failure_weight_calibration.json"
    assert calib_path.exists()
    state = json.loads(calib_path.read_text(encoding="utf-8"))
    assert "weight" in state and "fail_rate" in state


def test_auto_calibration_persists_across_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE", "1")
    m = _make_sqlite_mycelium(tmp_path)
    rnd = random.Random(0)
    pool = ["".join(rnd.choices(string.ascii_lowercase, k=8))
            for _ in range(200)]
    for _ in range(60):
        m.observe_text(" ".join(rnd.sample(pool, 8)))
    for _ in range(60):
        m._session_seen.clear()
        m.observe_failure(" ".join(rnd.sample(pool, 8)))
    saved_weight = m._failure_calibrated_weight
    assert saved_weight is not None
    # Re-open
    m2 = Mycelium(tmp_path)
    assert m2._failure_calibrated_weight == saved_weight


# ─── F. Bug #2101 — observe iterating over characters ─────────────────


def test_bug_2101_observe_text_does_not_iterate_chars(tmp_path):
    """Phase 3 fix: cube_providers used to call observe(str) which iterates
    over characters. observe_text() must be used for raw strings."""
    m = _make_sqlite_mycelium(tmp_path)
    # If observe iterated chars, we'd see a, b, c, d, e... as concepts.
    m.observe_text("alpha beta gamma delta epsilon")
    # We must have multi-letter concepts in edges, not single chars
    rows = m._db._conn.execute(
        "SELECT name FROM concepts").fetchall()
    names = [r[0] for r in rows]
    assert all(len(n) >= 3 for n in names), \
        f"concepts must be ≥3 chars (got {names})"
    assert "alpha" in names
    assert "beta" in names
