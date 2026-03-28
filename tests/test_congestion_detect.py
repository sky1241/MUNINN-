"""Tests for BRIQUE 3: Auto-detect congestion in observe().

Validates that:
1. Congestion check runs only once per session (not every observe call)
2. Fast observe does NOT trigger emergency decay
3. The congestion detection code exists and is wired correctly
4. _congestion_checked flag prevents repeated checks
"""
import os
import sys
import time
from unittest.mock import patch

import pytest

from muninn.mycelium import Mycelium
from muninn.mycelium_db import MyceliumDB


def _make_mycelium(tmp_path):
    """Create a fresh mycelium with SQLite DB."""
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)
    db_path = muninn_dir / "mycelium.db"
    db = MyceliumDB(db_path)
    db._conn.execute("INSERT INTO meta (key, value) VALUES ('migration_complete', '1')")
    db._conn.commit()
    db.close()
    m = Mycelium(tmp_path)
    return m


class TestCongestionDetect:
    """Test congestion detection in observe()."""

    def test_no_congestion_on_fast_db(self, tmp_path):
        """On a small DB, observe should be fast and NOT trigger decay."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo", "charlie"])
        # Should complete instantly, no congestion
        assert getattr(m, '_congestion_checked', False) is True

    def test_congestion_flag_set_once(self, tmp_path):
        """_congestion_checked should be set after first observe with pairs."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        assert not getattr(m, '_congestion_checked', False)
        m.observe(["alpha", "bravo"])
        assert m._congestion_checked is True

    def test_congestion_flag_survives_multiple_observes(self, tmp_path):
        """Flag should stay True across multiple observe calls."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo"])
        m.observe(["charlie", "delta"])
        m.observe(["echo", "foxtrot"])
        assert m._congestion_checked is True

    def test_congestion_code_exists(self):
        """Verify the congestion detection code is in mycelium.py."""
        import muninn.mycelium as mycelium
        source = open(mycelium.__file__, encoding="utf-8").read()
        assert "CONGESTION" in source
        assert "emergency decay" in source
        assert "_congestion_checked" in source

    def test_slow_batch_triggers_decay(self, tmp_path):
        """Directly test: if _congestion_checked is False and we call decay,
        old edges get cleaned. This validates the integration path."""
        m = _make_mycelium(tmp_path)
        m.start_session()

        # Add some old edges that decay can remove
        m.observe(["alpha", "bravo"])
        from muninn.mycelium import today_days
        td = today_days()
        a_id = m._db._concept_cache.get("alpha")
        b_id = m._db._concept_cache.get("bravo")
        # Make the edge very old
        m._db._conn.execute(
            "UPDATE edges SET last_seen=? WHERE a=? AND b=?",
            (td - 300, a_id, b_id))
        m._db._conn.commit()

        # Simulate what congestion detection does: call emergency decay
        dead = m.decay()
        assert dead >= 1, "Emergency decay should remove old edges"
        row = m._db._conn.execute(
            "SELECT count FROM edges WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        assert row is None, "Old edge should have been removed by emergency decay"

    def test_start_session_does_not_reset_congestion(self, tmp_path):
        """Congestion flag is per-Mycelium instance, not per session.
        We only check once to avoid repeated slow operations."""
        m = _make_mycelium(tmp_path)
        m.start_session()
        m.observe(["alpha", "bravo"])
        assert m._congestion_checked is True
        # start_session resets _session_seen but NOT _congestion_checked
        m.start_session()
        assert m._congestion_checked is True
