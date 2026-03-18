"""Test H3+H4+M11+M12: write methods in mycelium_db never commit.

Bug: upsert_connection, upsert_fusion, delete_connection,
update_connection_count, and add_zone_to_edge execute SQL
but never call commit(). Data is lost on crash or clean close.

Fix: Add self._conn.commit() to each write method.
"""
import sys, tempfile, sqlite3
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_upsert_connection_persists():
    """H3: upsert_connection must survive close+reopen."""
    from mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"

    db = MyceliumDB(db_path)
    db.upsert_connection("alpha", "beta", increment=1)
    db._conn.close()

    # Reopen and check
    db2 = MyceliumDB(db_path)
    conn = db2.get_connection("alpha", "beta")
    db2._conn.close()

    print(f"  upsert_connection persisted: {conn is not None}")
    assert conn is not None, "upsert_connection data lost after close!"
    assert conn["count"] >= 1, f"count={conn['count']}, expected >= 1"
    print("  PASS upsert_connection")


def test_upsert_fusion_persists():
    """H3: upsert_fusion must survive close+reopen."""
    from mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"

    db = MyceliumDB(db_path)
    db.upsert_fusion("gamma", "delta", form="gamma+delta", strength=10)
    db._conn.close()

    db2 = MyceliumDB(db_path)
    has = db2.has_fusion("gamma", "delta")
    db2._conn.close()

    print(f"  upsert_fusion persisted: {has}")
    assert has, "upsert_fusion data lost after close!"
    print("  PASS upsert_fusion")


def test_delete_connection_persists():
    """H4: delete_connection must actually delete on disk."""
    from mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"

    # Create connection first
    db = MyceliumDB(db_path)
    db.upsert_connection("epsilon", "zeta", increment=5)
    db._conn.commit()  # ensure it's there
    db.delete_connection("epsilon", "zeta")
    db._conn.close()

    # Reopen and check deletion persisted
    db2 = MyceliumDB(db_path)
    conn = db2.get_connection("epsilon", "zeta")
    db2._conn.close()

    print(f"  delete_connection persisted: {conn is None}")
    assert conn is None, "delete_connection didn't persist!"
    print("  PASS delete_connection")


def test_update_connection_count_persists():
    """M11: update_connection_count must survive close+reopen."""
    from mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"

    db = MyceliumDB(db_path)
    db.upsert_connection("theta", "iota", increment=1)
    db._conn.commit()  # ensure base data exists
    db.update_connection_count("theta", "iota", 42)
    db._conn.close()

    db2 = MyceliumDB(db_path)
    conn = db2.get_connection("theta", "iota")
    db2._conn.close()

    count = conn["count"] if conn else 0
    print(f"  update_connection_count persisted: count={count} (expected 42)")
    assert count == 42, f"update_connection_count lost: count={count}"
    print("  PASS update_connection_count")


def test_add_zone_to_edge_persists():
    """M12: add_zone_to_edge must survive close+reopen."""
    from mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    db_path = tmp / "test.db"

    db = MyceliumDB(db_path)
    db.upsert_connection("kappa", "lambda", increment=1)
    db._conn.commit()  # ensure edge exists
    db.add_zone_to_edge("kappa", "lambda", "test_zone")
    db._conn.close()

    db2 = MyceliumDB(db_path)
    conn = db2.get_connection("kappa", "lambda")
    db2._conn.close()

    zones = conn.get("zones", []) if conn else []
    print(f"  add_zone_to_edge persisted: zones={zones}")
    assert "test_zone" in zones, f"add_zone_to_edge lost: zones={zones}"
    print("  PASS add_zone_to_edge")


if __name__ == "__main__":
    print("## H3+H4+M11+M12 — missing commits in mycelium_db")
    test_upsert_connection_persists()
    test_upsert_fusion_persists()
    test_delete_connection_persists()
    test_update_connection_count_persists()
    test_add_zone_to_edge_persists()
    print("\n  ALL 5/5 PASS")
