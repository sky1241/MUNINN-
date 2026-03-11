"""TIER 3 S1+S2: SQLite storage + epoch-days tests."""
import json
import os
import shutil
import sqlite3
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.core.mycelium import Mycelium
from engine.core.mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days


def make_temp():
    return tempfile.mkdtemp(prefix="tier3_")


# ── S1: SQLite storage ──────────────────────────────────────────────

def test_s1_1_fresh_creates_db():
    """Fresh mycelium creates .db on save, no .json."""
    d = make_temp()
    try:
        m = Mycelium(d)
        m.observe(["alpha", "beta", "gamma"])
        m.save()
        assert os.path.exists(os.path.join(d, ".muninn", "mycelium.db"))
        assert not os.path.exists(os.path.join(d, ".muninn", "mycelium.json"))
        m.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_s1_2_roundtrip():
    """Save and reload preserves all data via DB queries."""
    d = make_temp()
    try:
        m = Mycelium(d)
        m.observe(["alpha", "beta"])
        m.observe(["alpha", "beta"])
        m.observe(["alpha", "beta"])
        m.observe(["alpha", "beta"])
        m.observe(["alpha", "beta"])
        m.observe(["gamma", "delta"])
        m.start_session()
        m.save()
        n1_conns = m._db.connection_count()
        n1_fusions = m._db.fusion_count()
        m.close()

        m2 = Mycelium(d)
        assert m2._db.connection_count() == n1_conns
        assert m2._db.fusion_count() == n1_fusions
        assert m2.data["session_count"] == 1
        # Check specific connection survives roundtrip
        conn = m2._db.get_connection("alpha", "beta")
        assert conn is not None
        assert conn["count"] == 5
        m2.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_s1_3_migration():
    """JSON mycelium auto-migrates to SQLite."""
    d = make_temp()
    muninn_dir = os.path.join(d, ".muninn")
    os.makedirs(muninn_dir)
    try:
        data = {
            "version": 1, "repo": "test", "created": "2026-03-07",
            "updated": "2026-03-11", "session_count": 42,
            "connections": {
                "foo|bar": {"count": 7, "first_seen": "2026-03-07", "last_seen": "2026-03-11"},
                "bar|baz": {"count": 3, "first_seen": "2026-03-08", "last_seen": "2026-03-09",
                            "zones": ["z1", "z2"]},
            },
            "fusions": {
                "foo|bar": {"concepts": ["foo", "bar"], "form": "foo+bar",
                            "strength": 7, "fused_at": "2026-03-10"},
            }
        }
        with open(os.path.join(muninn_dir, "mycelium.json"), "w") as f:
            json.dump(data, f, indent=2)

        m = Mycelium(d)
        assert os.path.exists(os.path.join(muninn_dir, "mycelium.db"))
        assert os.path.exists(os.path.join(muninn_dir, "mycelium.json.bak"))
        assert not os.path.exists(os.path.join(muninn_dir, "mycelium.json"))
        # Lazy mode: check via DB, not self.data["connections"]
        conn = m._db.get_connection("foo", "bar")
        assert conn is not None
        assert conn["count"] == 7
        assert m.data["session_count"] == 42
        conn2 = m._db.get_connection("bar", "baz")
        assert conn2 is not None
        zones = m._db.get_zones_for_edge("bar", "baz")
        assert "z1" in zones
        assert m._db.has_fusion("foo", "bar")
        m.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_s1_4_no_tmp_files():
    """SQLite save produces no .tmp files."""
    d = make_temp()
    try:
        m = Mycelium(d)
        m.observe(["alpha", "beta", "gamma"])
        m.save()
        muninn_dir = os.path.join(d, ".muninn")
        tmp_files = [f for f in os.listdir(muninn_dir) if f.endswith(".tmp")]
        assert len(tmp_files) == 0, f"Temp files found: {tmp_files}"
        m.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_s1_5_wal_mode():
    """Database uses WAL journal mode."""
    d = make_temp()
    try:
        m = Mycelium(d)
        m.observe(["alpha", "beta"])
        m.save()
        m.close()
        conn = sqlite3.connect(os.path.join(d, ".muninn", "mycelium.db"))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal", f"Expected WAL, got {mode}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ── S2: Epoch-days dates ────────────────────────────────────────────

def test_s2_1_date_conversion():
    """date_to_days and days_to_date are inverse functions."""
    test_dates = ["2020-01-01", "2026-03-11", "2025-12-31", "2030-06-15"]
    for d in test_dates:
        days = date_to_days(d)
        back = days_to_date(days)
        assert back == d, f"Round-trip failed: {d} -> {days} -> {back}"


def test_s2_2_dates_stored_as_int():
    """Dates in SQLite are integers, not strings."""
    d = make_temp()
    try:
        m = Mycelium(d)
        m.observe(["alpha", "beta"])
        m.save()
        m.close()
        conn = sqlite3.connect(os.path.join(d, ".muninn", "mycelium.db"))
        row = conn.execute("SELECT first_seen, last_seen FROM edges LIMIT 1").fetchone()
        conn.close()
        assert isinstance(row[0], int), f"first_seen is {type(row[0])}, expected int"
        assert isinstance(row[1], int), f"last_seen is {type(row[1])}, expected int"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_s2_3_epoch_ref():
    """2020-01-01 = day 0."""
    assert date_to_days("2020-01-01") == 0
    assert days_to_date(0) == "2020-01-01"


# ── MyceliumDB unit tests ───────────────────────────────────────────

def test_db_concept_ids():
    """Concepts are stored as integer IDs."""
    d = make_temp()
    try:
        db_path = os.path.join(d, "test.db")
        db = MyceliumDB(db_path)
        a_id = db._get_or_create_concept("alpha")
        b_id = db._get_or_create_concept("beta")
        assert isinstance(a_id, int)
        assert isinstance(b_id, int)
        assert a_id != b_id
        # Same concept returns same ID
        assert db._get_or_create_concept("alpha") == a_id
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_db_upsert_connection():
    """Upsert increments count correctly."""
    d = make_temp()
    try:
        db_path = os.path.join(d, "test.db")
        db = MyceliumDB(db_path)
        db.upsert_connection("alpha", "beta")
        db.upsert_connection("alpha", "beta")
        db.upsert_connection("alpha", "beta")
        db.commit()
        conn = db.get_connection("alpha", "beta")
        assert conn is not None
        assert conn["count"] == 3
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_db_without_rowid():
    """Tables use WITHOUT ROWID for efficiency."""
    d = make_temp()
    try:
        db_path = os.path.join(d, "test.db")
        db = MyceliumDB(db_path)
        # Check that edges table exists and has correct schema
        row = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='edges'"
        ).fetchone()
        assert "WITHOUT ROWID" in row[0], f"edges not WITHOUT ROWID: {row[0]}"
        row = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='fusions'"
        ).fetchone()
        assert "WITHOUT ROWID" in row[0], f"fusions not WITHOUT ROWID: {row[0]}"
        db.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
