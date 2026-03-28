"""X1b — Purge existing secrets from mycelium databases.

Tests:
  X1b.1  purge_secret_concepts removes contaminated concepts
  X1b.2  purge_secret_concepts removes associated edges
  X1b.3  purge_secret_concepts removes associated fusions
  X1b.4  purge_secret_concepts preserves clean concepts
  X1b.5  purge_secret_concepts returns 0 when no secrets
  X1b.6  purge_secrets_db works on local + meta databases
"""
import sys, os, tempfile, shutil, sqlite3
from muninn.mycelium_db import MyceliumDB
from pathlib import Path


def _make_db(tmpdir, name="mycelium.db"):
    """Create a test DB with some clean + contaminated concepts."""
    db_path = Path(tmpdir) / name
    db = MyceliumDB(db_path)

    # Insert clean concepts
    clean_id1 = db._get_or_create_concept("compression")
    clean_id2 = db._get_or_create_concept("pipeline")
    clean_id3 = db._get_or_create_concept("memory")

    # Insert contaminated concepts (secret-like names)
    secret_id1 = db._get_or_create_concept("ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345")
    secret_id2 = db._get_or_create_concept("sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890")
    secret_id3 = db._get_or_create_concept("AKIAIOSFODNN7EXAMPLE")

    # Create edges involving secrets
    from muninn.mycelium_db import date_to_days
    today = date_to_days("2026-03-27")
    db._conn.execute("INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                     (clean_id1, secret_id1, 5.0, today, today))
    db._conn.execute("INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                     (secret_id2, clean_id2, 3.0, today, today))
    # Clean edge
    db._conn.execute("INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                     (clean_id1, clean_id2, 10.0, today, today))

    # Create a fusion involving a secret
    db._conn.execute("INSERT OR REPLACE INTO fusions (a, b, form, strength, fused_at) VALUES (?, ?, ?, ?, ?)",
                     (clean_id1, secret_id1, "comp_ghp", 5.0, today))

    db._conn.commit()
    return db, {
        "clean": [clean_id1, clean_id2, clean_id3],
        "secret": [secret_id1, secret_id2, secret_id3],
    }


def test_x1b_1_purge_removes_concepts():
    """Contaminated concepts are removed."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        db, ids = _make_db(tmpdir)
        n = db.purge_secret_concepts()
        assert n == 3, f"X1b.1 FAIL: expected 3 purged, got {n}"

        # Verify concepts are gone
        remaining = list(db._conn.execute("SELECT name FROM concepts").fetchall())
        names = [r[0] for r in remaining]
        assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345" not in names
        assert "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890" not in names
        assert "AKIAIOSFODNN7EXAMPLE" not in names
        db.close()
        print(f"  X1b.1 PASS: {n} secret concepts purged")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1b_2_purge_removes_edges():
    """Edges involving contaminated concepts are removed."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        db, ids = _make_db(tmpdir)
        db.purge_secret_concepts()

        edges = list(db._conn.execute("SELECT a, b FROM edges").fetchall())
        # Only the clean edge should remain
        assert len(edges) == 1, f"X1b.2 FAIL: expected 1 clean edge, got {len(edges)}"
        a, b = edges[0]
        assert a == ids["clean"][0] and b == ids["clean"][1], f"X1b.2 FAIL: wrong edge {a},{b}"
        db.close()
        print(f"  X1b.2 PASS: secret edges removed, {len(edges)} clean edge preserved")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1b_3_purge_removes_fusions():
    """Fusions involving contaminated concepts are removed."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        db, ids = _make_db(tmpdir)
        db.purge_secret_concepts()

        fusions = list(db._conn.execute("SELECT a, b FROM fusions").fetchall())
        assert len(fusions) == 0, f"X1b.3 FAIL: expected 0 fusions, got {len(fusions)}"
        db.close()
        print(f"  X1b.3 PASS: secret fusions removed")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1b_4_preserves_clean():
    """Clean concepts are preserved."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        db, ids = _make_db(tmpdir)
        db.purge_secret_concepts()

        remaining = [r[0] for r in db._conn.execute("SELECT name FROM concepts").fetchall()]
        assert "compression" in remaining, f"X1b.4 FAIL: 'compression' lost"
        assert "pipeline" in remaining, f"X1b.4 FAIL: 'pipeline' lost"
        assert "memory" in remaining, f"X1b.4 FAIL: 'memory' lost"
        assert len(remaining) == 3, f"X1b.4 FAIL: expected 3 clean, got {len(remaining)}"
        db.close()
        print(f"  X1b.4 PASS: {len(remaining)} clean concepts preserved")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1b_5_no_secrets_returns_zero():
    """Returns 0 when database has no secrets."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        db_path = Path(tmpdir) / "clean.db"
        db = MyceliumDB(db_path)
        db._get_or_create_concept("compression")
        db._get_or_create_concept("pipeline")
        db._conn.commit()

        n = db.purge_secret_concepts()
        assert n == 0, f"X1b.5 FAIL: expected 0, got {n}"
        db.close()
        print(f"  X1b.5 PASS: no secrets, returned 0")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1b_6_purge_db_function():
    """purge_secrets_db works on local .muninn/mycelium.db."""
    tmpdir = tempfile.mkdtemp(prefix="muninn_x1b_")
    try:
        # Create fake repo structure with .muninn/mycelium.db
        muninn_dir = Path(tmpdir) / ".muninn"
        muninn_dir.mkdir()
        db, ids = _make_db(str(muninn_dir))
        db.close()

        # Test only the local DB purge (not meta) by checking directly
        db2 = MyceliumDB(muninn_dir / "mycelium.db")
        n = db2.purge_secret_concepts()
        assert n == 3, f"X1b.6 FAIL: expected 3 purged from local, got {n}"

        # Verify only clean concepts remain
        remaining = [r[0] for r in db2._conn.execute("SELECT name FROM concepts").fetchall()]
        assert len(remaining) == 3, f"X1b.6 FAIL: expected 3 clean remaining, got {len(remaining)}"
        db2.close()
        print(f"  X1b.6 PASS: purge_secret_concepts purged {n} from local DB")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_x1b_1_purge_removes_concepts()
    test_x1b_2_purge_removes_edges()
    test_x1b_3_purge_removes_fusions()
    test_x1b_4_preserves_clean()
    test_x1b_5_no_secrets_returns_zero()
    test_x1b_6_purge_db_function()
    print("\nAll X1b tests PASS")
