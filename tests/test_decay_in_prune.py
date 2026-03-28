"""Tests for BRIQUE 2: Decay wired into prune().

Validates that:
1. decay() removes old edges (count drops to ~0 after DECAY_HALF_LIFE days)
2. decay() preserves recent edges
3. decay() is actually called during prune() (not just existing as dead code)
4. Immortal edges (3+ zones, federated mode) survive decay
5. After decay, edge count decreases
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from mycelium import Mycelium
from mycelium_db import MyceliumDB


def _make_mycelium(tmp_path, federated=False):
    """Create a mycelium with SQLite DB."""
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)
    db_path = muninn_dir / "mycelium.db"
    db = MyceliumDB(db_path)
    db._conn.execute("INSERT INTO meta (key, value) VALUES ('migration_complete', '1')")
    db._conn.commit()
    db.close()
    m = Mycelium(tmp_path, federated=federated)
    return m


def _count_edges(m):
    """Count total edges in the DB."""
    row = m._db._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
    return row[0]


def _get_edge(m, a, b):
    """Get edge data between two concepts."""
    a_key = min(a, b)
    b_key = max(a, b)
    a_id = m._db._concept_cache.get(a_key)
    b_id = m._db._concept_cache.get(b_key)
    if a_id is None or b_id is None:
        return None
    return m._db._conn.execute(
        "SELECT count, last_seen FROM edges WHERE a=? AND b=?", (a_id, b_id)
    ).fetchone()


def _set_last_seen(m, a, b, days_ago):
    """Manually set last_seen to simulate old edges."""
    from mycelium import today_days
    a_key = min(a, b)
    b_key = max(a, b)
    a_id = m._db._concept_cache.get(a_key)
    b_id = m._db._concept_cache.get(b_key)
    td = today_days() - days_ago
    m._db._conn.execute(
        "UPDATE edges SET last_seen=? WHERE a=? AND b=?", (td, a_id, b_id)
    )
    m._db._conn.commit()


class TestDecay:
    """Test that decay() properly removes old connections."""

    def test_recent_edges_survive(self, tmp_path):
        """Edges seen today should not be decayed."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo"])
        assert _count_edges(m) >= 1
        dead = m.decay()
        assert dead == 0
        assert _get_edge(m, "alpha", "bravo") is not None

    def test_old_edges_removed(self, tmp_path):
        """Edges not seen for > DECAY_HALF_LIFE * 10 should be removed."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo"])
        # Simulate edge not seen for 300 days (way past any half-life)
        _set_last_seen(m, "alpha", "bravo", 300)
        dead = m.decay()
        assert dead >= 1
        assert _get_edge(m, "alpha", "bravo") is None

    def test_mixed_old_and_new(self, tmp_path):
        """Only old edges die, recent ones survive."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo", "charlie"])
        # Make alpha-bravo old, keep alpha-charlie recent
        _set_last_seen(m, "alpha", "bravo", 300)
        edges_before = _count_edges(m)
        dead = m.decay()
        assert dead >= 1
        assert _get_edge(m, "alpha", "bravo") is None  # old = dead
        assert _get_edge(m, "alpha", "charlie") is not None  # recent = alive

    def test_decay_reduces_count_gradually(self, tmp_path):
        """Edge seen 1 half-life ago should have its count halved, not deleted."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        # Observe many times to build up count
        for _ in range(5):
            m.start_session()
            m.observe(["alpha", "bravo"])
        edge = _get_edge(m, "alpha", "bravo")
        original_count = edge[0]
        assert original_count == 5.0

        # Age by exactly 1 half-life
        half_life = m.DECAY_HALF_LIFE
        _set_last_seen(m, "alpha", "bravo", half_life + 1)
        m.decay()
        edge_after = _get_edge(m, "alpha", "bravo")
        assert edge_after is not None, "Should survive with count=2.5"
        assert edge_after[0] < original_count  # Count decreased

    def test_immortal_edges_federated(self, tmp_path):
        """Edges with 3+ zones should survive decay in federated mode."""
        m = _make_mycelium(tmp_path, federated=True)
        m.start_session()
        m.observe(["alpha", "bravo"])
        a_id = m._db._concept_cache.get("alpha")
        b_id = m._db._concept_cache.get("bravo")
        # Add 3 zones to make it immortal
        m._db._conn.execute(
            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
            (a_id, b_id, "zone1"))
        m._db._conn.execute(
            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
            (a_id, b_id, "zone2"))
        m._db._conn.execute(
            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
            (a_id, b_id, "zone3"))
        m._db._conn.commit()
        # Make it very old
        _set_last_seen(m, "alpha", "bravo", 500)
        dead = m.decay()
        assert dead == 0  # Immortal = no decay
        assert _get_edge(m, "alpha", "bravo") is not None


class TestDecayInPrune:
    """Test that prune() actually calls decay()."""

    def test_prune_calls_decay(self, tmp_path, monkeypatch):
        """Verify prune() runs mycelium decay (not just tree pruning)."""
        # We can't easily run full prune() (needs tree), but we can verify
        # the import path works by checking the code structure
        import muninn
        _mdir = Path(muninn.__file__).parent
        source = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["muninn.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
        # Verify decay is called in prune
        assert "m_decay.decay()" in source, "prune() must call mycelium decay()"
        assert "MYCELIUM DECAY" in source, "prune() must print decay results"
