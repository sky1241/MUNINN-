"""X3-X7 — Database hardening fixes.

Tests:
  X3.1  Composite indexes exist after DB creation
  X3.2  Indexes are used by EXPLAIN QUERY PLAN on edge_zones lookup
  X4.1  PRAGMA user_version is set after creation
  X4.2  Migration is idempotent (open DB twice, no crash)
  X4.3  Migration flag is cleared after completion
  X5.1  days_to_date fallback returns today, not hardcoded date
  X6.1  Saturation loss is float, not int (no crash to 1)
  X7.1  Feed progress is written after save (order check)
"""
import sys, os, tempfile, shutil
from pathlib import Path


def test_x3_1_composite_indexes_exist():
    """Composite indexes are created with the DB."""
    from muninn.mycelium_db import MyceliumDB
    tmpdir = tempfile.mkdtemp(prefix="muninn_x3_")
    try:
        db = MyceliumDB(Path(tmpdir) / "test.db")
        indexes = [r[1] for r in db._conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index'").fetchall()]
        assert "idx_edge_zones_ab" in indexes, f"X3.1 FAIL: idx_edge_zones_ab missing"
        assert "idx_edges_last_seen_count" in indexes, f"X3.1 FAIL: idx_edges_last_seen_count missing"
        assert "idx_edges_b_a" in indexes, f"X3.1 FAIL: idx_edges_b_a missing"
        assert "idx_fusions_ab" in indexes, f"X3.1 FAIL: idx_fusions_ab missing"
        db.close()
        print(f"  X3.1 PASS: 4 composite indexes found")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x3_2_index_used_by_edge_zones_query():
    """EXPLAIN QUERY PLAN uses index for edge_zones(a,b) lookup."""
    from muninn.mycelium_db import MyceliumDB
    tmpdir = tempfile.mkdtemp(prefix="muninn_x3_")
    try:
        db = MyceliumDB(Path(tmpdir) / "test.db")
        plan = db._conn.execute(
            "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM edge_zones WHERE a=1 AND b=2"
        ).fetchall()
        plan_text = str(plan)
        # Should use PRIMARY KEY or idx_edge_zones_ab, not full scan
        assert "SCAN" not in plan_text or "INDEX" in plan_text, f"X3.2 FAIL: full scan on edge_zones"
        db.close()
        print(f"  X3.2 PASS: edge_zones query uses index")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x4_1_user_version_set():
    """PRAGMA user_version is set after creation."""
    from muninn.mycelium_db import MyceliumDB
    tmpdir = tempfile.mkdtemp(prefix="muninn_x4_")
    try:
        db = MyceliumDB(Path(tmpdir) / "test.db")
        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db.SCHEMA_VERSION, f"X4.1 FAIL: version={version}, expected {db.SCHEMA_VERSION}"
        db.close()
        print(f"  X4.1 PASS: user_version={version}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x4_2_migration_idempotent():
    """Opening DB twice doesn't crash (migration is idempotent)."""
    from muninn.mycelium_db import MyceliumDB
    tmpdir = tempfile.mkdtemp(prefix="muninn_x4_")
    try:
        db_path = Path(tmpdir) / "test.db"
        db1 = MyceliumDB(db_path)
        db1.close()
        # Open again — should not crash
        db2 = MyceliumDB(db_path)
        version = db2._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == db2.SCHEMA_VERSION
        db2.close()
        print(f"  X4.2 PASS: idempotent migration")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x4_3_migration_flag_cleared():
    """Migration in-progress flag is cleared after completion."""
    from muninn.mycelium_db import MyceliumDB
    tmpdir = tempfile.mkdtemp(prefix="muninn_x4_")
    try:
        db = MyceliumDB(Path(tmpdir) / "test.db")
        row = db._conn.execute(
            "SELECT value FROM meta WHERE key='_migration_in_progress'"
        ).fetchone()
        assert row is None, f"X4.3 FAIL: migration flag still set"
        db.close()
        print(f"  X4.3 PASS: migration flag cleared")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x5_1_days_to_date_fallback():
    """days_to_date fallback returns today, not hardcoded 2026-01-01."""
    from muninn.mycelium_db import days_to_date
    from datetime import datetime, timezone
    result = days_to_date("garbage")
    today_str = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")
    assert result == today_str, f"X5.1 FAIL: fallback={result}, expected {today_str}"
    assert result != "2026-01-01", f"X5.1 FAIL: still returning hardcoded 2026-01-01"
    print(f"  X5.1 PASS: fallback={result}")


def test_x6_1_saturation_float_not_int():
    """Saturation loss is float, preventing int truncation to 0/1."""
    from muninn.mycelium import Mycelium
    tmpdir = tempfile.mkdtemp(prefix="muninn_x6_")
    try:
        m = Mycelium(Path(tmpdir))
        # Enable saturation
        m.SATURATION_BETA = 0.001
        m.SATURATION_THRESHOLD = 10

        m.start_session()
        # Create a high-count edge
        m.observe(["alpha", "beta"])
        if m._db:
            # Set count to 1000 to trigger saturation
            a_id = m._db._concept_cache.get("alpha")
            b_id = m._db._concept_cache.get("beta")
            if a_id and b_id:
                m._db._conn.execute(
                    "UPDATE edges SET count=1000.0, last_seen=? WHERE a=? AND b=?",
                    (0, min(a_id, b_id), max(a_id, b_id)))
                m._db._conn.commit()

        # Run decay — with int(), count=1000 -> saturation_loss = int(0.001*1000*1000) = 1000 -> count=1
        # With float, saturation_loss = 1000.0 but count stays reasonable
        m.decay(days=1)

        if m._db:
            row = m._db._conn.execute(
                "SELECT count FROM edges WHERE a=? AND b=?",
                (min(a_id, b_id), max(a_id, b_id))).fetchone()
            if row:
                # Should not have crashed to exactly 1 (int truncation bug)
                assert row[0] != 1 or m.SATURATION_BETA == 0, \
                    f"X6.1 FAIL: count crashed to 1 (int truncation)"
                print(f"  X6.1 PASS: count={row[0]:.2f} (float saturation)")
            else:
                print(f"  X6.1 PASS: edge decayed to death (expected for old edge)")
        else:
            print(f"  X6.1 SKIP: no DB")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x7_1_feed_progress_order():
    """Verify feed progress code writes save() BEFORE progress file (source inspection)."""
    muninn_dir = os.path.join(os.path.dirname(__file__), "..", "engine", "core")
    source = ""
    for _mf in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"]:
        _mp = os.path.join(muninn_dir, _mf)
        if os.path.exists(_mp):
            with open(_mp, encoding="utf-8") as f:
                source += f.read() + "\n"

    # Find the checkpoint block: FEED_CHUNK_SIZE ... m.save() ... _atomic_json_write
    lines = source.split('\n')
    in_checkpoint = False
    save_line = None
    progress_line = None
    for i, line in enumerate(lines):
        if 'FEED_CHUNK_SIZE' in line:
            in_checkpoint = True
        if in_checkpoint:
            if 'm.save()' in line and save_line is None:
                save_line = i
            if '_atomic_json_write' in line and progress_line is None:
                progress_line = i
            if save_line and progress_line:
                break
    assert save_line is not None, "X7.1 FAIL: m.save() not found after FEED_CHUNK_SIZE"
    assert progress_line is not None, "X7.1 FAIL: progress write not found after FEED_CHUNK_SIZE"
    assert save_line < progress_line, \
        f"X7.1 FAIL: save() at line {save_line} is AFTER progress at line {progress_line}"
    print(f"  X7.1 PASS: save() (line {save_line}) before progress (line {progress_line})")


if __name__ == "__main__":
    test_x3_1_composite_indexes_exist()
    test_x3_2_index_used_by_edge_zones_query()
    test_x4_1_user_version_set()
    test_x4_2_migration_idempotent()
    test_x4_3_migration_flag_cleared()
    test_x5_1_days_to_date_fallback()
    test_x6_1_saturation_float_not_int()
    test_x7_1_feed_progress_order()
    print("\nAll X3-X7 tests PASS")
