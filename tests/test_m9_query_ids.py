"""Test M9: query_ids NameError in pull_from_meta when query_concepts=None.

Bug: When query_concepts is None and self._db is not None,
query_ids is never defined. Line 2229 raises NameError.

Fix: Initialize query_ids = set() before the if/else block.
"""
import sys, tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m9_pull_from_meta_none():
    """pull_from_meta(None) should not crash with NameError."""
    from muninn.mycelium import Mycelium
    from muninn.mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    try:
        # Create local mycelium with SQLite
        muninn_dir = tmp / ".muninn"
        muninn_dir.mkdir()
        db_path = muninn_dir / "mycelium.db"
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db._conn.commit()
        db._conn.close()

        # Create meta mycelium
        meta_dir = tmp / ".meta_muninn"
        meta_dir.mkdir()
        meta_db_path = meta_dir / "meta_mycelium.db"
        meta_db = MyceliumDB(meta_db_path)
        meta_db.set_meta("migration_complete", "1")
        # Add some test data to meta
        meta_db.upsert_connection("test_concept_a", "test_concept_b", increment=5)
        meta_db._conn.commit()
        meta_db._conn.close()

        # Create Mycelium pointing to our meta
        m = Mycelium(tmp)
        assert m._db is not None, "Should be in SQLite mode"

        # Monkey-patch meta_db_path to use our test meta
        original_meta_db_path = m.meta_db_path
        m.meta_db_path = lambda: meta_db_path

        # THIS IS THE BUG: pull_from_meta(None) should not crash
        crashed = False
        error_msg = ""
        try:
            result = m.pull_from_meta(query_concepts=None)
            print(f"  pull_from_meta(None) returned: {result}")
        except NameError as e:
            crashed = True
            error_msg = str(e)
            print(f"  NameError: {e}")
        except Exception as e:
            print(f"  Other error: {type(e).__name__}: {e}")

        # Restore and close
        m.meta_db_path = original_meta_db_path
        if m._db and m._db._conn:
            m._db._conn.close()

        print(f"  Crashed with NameError: {crashed}")
        assert not crashed, f"pull_from_meta(None) crashed: {error_msg}"

        print("  PASS")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("## M9 — query_ids NameError in pull_from_meta(None)")
    test_m9_pull_from_meta_none()
