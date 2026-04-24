"""Tests for BRIQUE 1: Delta observe — skip pairs already upserted this session.

Validates that:
1. First observe of a pair does the upsert (count increases)
2. Second observe of same pair in same session is SKIPPED (count unchanged)
3. start_session() resets the delta tracker
4. Different pairs in same session are NOT skipped
5. Performance: repeated observe is faster than first observe on large concept lists
"""
import os
import sys
import tempfile
import time

import pytest

from muninn.mycelium import Mycelium


@pytest.fixture
def fresh_mycelium(tmp_path):
    """Create a fresh mycelium with SQLite DB (not in-memory dict)."""
    from muninn.mycelium_db import MyceliumDB
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir()
    db_path = muninn_dir / "mycelium.db"
    # Create the DB so Mycelium loads in SQLite mode
    db = MyceliumDB(db_path)
    db._conn.execute("INSERT INTO meta (key, value) VALUES ('migration_complete', '1')")
    db._conn.commit()
    db.close()
    m = Mycelium(tmp_path)
    assert m._db is not None, "Mycelium should be in SQLite mode"
    m.start_session()
    return m


def _edge_count(m, a, b):
    """Get edge count between two concepts."""
    a_key = min(a, b)
    b_key = max(a, b)
    a_id = m._db._concept_cache.get(a_key)
    b_id = m._db._concept_cache.get(b_key)
    if a_id is None or b_id is None:
        return 0.0
    row = m._db._conn.execute(
        "SELECT count FROM edges WHERE a=? AND b=?", (a_id, b_id)
    ).fetchone()
    return row[0] if row else 0.0


class TestDeltaObserve:
    """Test that observe() skips pairs already seen this session."""

    def test_first_observe_creates_edge(self, fresh_mycelium):
        """First observe of a pair should create the edge with count=1."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo"])
        assert _edge_count(m, "alpha", "bravo") == 1.0

    def test_second_observe_skipped(self, fresh_mycelium):
        """Second observe of same pair in same session should be skipped."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo"])
        count_after_first = _edge_count(m, "alpha", "bravo")
        m.observe(["alpha", "bravo"])
        count_after_second = _edge_count(m, "alpha", "bravo")
        assert count_after_first == count_after_second == 1.0

    def test_different_pairs_not_skipped(self, fresh_mycelium):
        """Different pairs should NOT be skipped."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo"])
        m.observe(["alpha", "charlie"])
        assert _edge_count(m, "alpha", "bravo") == 1.0
        assert _edge_count(m, "alpha", "charlie") == 1.0

    def test_start_session_resets_delta(self, fresh_mycelium):
        """start_session() should reset the delta tracker, allowing re-observe."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo"])
        assert _edge_count(m, "alpha", "bravo") == 1.0

        m.start_session()  # Reset delta
        m.observe(["alpha", "bravo"])
        assert _edge_count(m, "alpha", "bravo") == 2.0  # Now it should increment

    def test_triple_observe_stays_at_one(self, fresh_mycelium):
        """Multiple observes in same session should all be skipped after first."""
        m = fresh_mycelium
        for _ in range(10):
            m.observe(["alpha", "bravo"])
        assert _edge_count(m, "alpha", "bravo") == 1.0

    def test_mixed_concepts_partial_skip(self, fresh_mycelium):
        """Overlapping concept lists: shared pairs skipped, new pairs created."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo", "charlie"])
        # alpha-bravo, alpha-charlie, bravo-charlie all created
        assert _edge_count(m, "alpha", "bravo") == 1.0
        assert _edge_count(m, "bravo", "charlie") == 1.0

        m.observe(["alpha", "bravo", "delta"])
        # alpha-bravo: SKIPPED (already seen)
        # alpha-delta: NEW
        # bravo-delta: NEW
        assert _edge_count(m, "alpha", "bravo") == 1.0  # Still 1, skipped
        assert _edge_count(m, "alpha", "delta") == 1.0  # New
        assert _edge_count(m, "bravo", "delta") == 1.0  # New

    def test_session_seen_set_grows(self, fresh_mycelium):
        """The _session_seen set should track all pairs observed."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo", "charlie"])
        # 3 pairs: (alpha,bravo), (alpha,charlie), (bravo,charlie)
        assert len(m._session_seen) == 3

    def test_performance_delta_faster(self, fresh_mycelium):
        """Repeated observe should be faster than first (skips DB writes)."""
        m = fresh_mycelium
        concepts = [f"concept_{i}" for i in range(20)]  # 190 pairs

        t0 = time.perf_counter()
        m.observe(concepts)
        first_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        m.observe(concepts)
        second_time = time.perf_counter() - t0

        # Second should be at least 2x faster (skips all DB writes)
        assert second_time < first_time, (
            f"Delta should be faster: first={first_time:.4f}s, second={second_time:.4f}s"
        )

    def test_arousal_does_not_bypass_delta(self, fresh_mycelium):
        """Even with different arousal values, delta should skip."""
        m = fresh_mycelium
        m.observe(["alpha", "bravo"], arousal=0.0)
        m.observe(["alpha", "bravo"], arousal=0.8)
        # Delta tracks by (a_id, b_id), not by arousal — still skipped
        assert _edge_count(m, "alpha", "bravo") == 1.0
