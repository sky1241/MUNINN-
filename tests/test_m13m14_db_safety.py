"""Test M13+M14: _get_or_create_concept error handling + foreign keys.

M13: except sqlite3.Error catches everything including disk-full/corruption.
Fix: Only catch IntegrityError.

M14: PRAGMA foreign_keys=ON never set. Orphaned edge_zones possible.
Fix: Add pragma after connection open.
"""
import sys, tempfile, sqlite3
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m13_only_catches_integrity():
    """_get_or_create_concept should only catch IntegrityError, not all errors."""
    from muninn.mycelium_db import MyceliumDB
    import inspect

    # Check the source code
    source = inspect.getsource(MyceliumDB._get_or_create_concept)
    has_integrity = "IntegrityError" in source
    has_broad = "sqlite3.Error:" in source and "IntegrityError" not in source

    print(f"  Catches IntegrityError: {has_integrity}")
    print(f"  Catches broad sqlite3.Error: {has_broad}")
    assert has_integrity, "Should catch sqlite3.IntegrityError"
    assert not has_broad, "Should NOT catch broad sqlite3.Error"

    # Functional test: normal operation still works
    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"
    db = MyceliumDB(db_path)
    cid = db._get_or_create_concept("test_concept")
    assert cid > 0, f"Should return valid ID, got {cid}"
    # Duplicate should return same ID (IntegrityError caught silently)
    cid2 = db._get_or_create_concept("test_concept")
    assert cid == cid2, f"Same concept should return same ID: {cid} vs {cid2}"
    db._conn.close()

    print("  PASS M13")


def test_m14_foreign_keys_enabled():
    """PRAGMA foreign_keys should be ON."""
    from muninn.mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"
    db = MyceliumDB(db_path)

    fk = db._conn.execute("PRAGMA foreign_keys").fetchone()[0]
    print(f"  foreign_keys = {fk} (expected 1)")
    db._conn.close()

    assert fk == 1, f"foreign_keys should be ON (1), got {fk}"
    print("  PASS M14")


if __name__ == "__main__":
    print("## M13+M14 — DB safety")
    test_m13_only_catches_integrity()
    test_m14_foreign_keys_enabled()
