"""Tests for wiring DB functions — replacing inline SQL with db method calls.

Validates that:
1. vacuum_if_needed() calls db.vacuum() (not inline SQL)
2. get_zones() calls db.get_zone_counts() (not inline SQL)
3. get_bridges() calls db.get_multi_zone_edges() (not inline SQL)
4. detect_anomalies() calls db.get_zone_avg_count() (not inline SQL)
5. decay() calls db.delete_stale_fusions() after removing dead edges
"""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium import Mycelium
from mycelium_db import MyceliumDB


def _make_mycelium(tmp_path: str) -> Mycelium:
    """Create a test mycelium with SQLite backend."""
    repo = Path(tmp_path) / "repo"
    repo.mkdir(exist_ok=True)
    m = Mycelium(repo_path=repo)
    # Seed + save to initialize SQLite backend (_db is None until first save)
    m.observe(["init_a", "init_b"])
    m.save()
    assert m._db is not None, "DB should be initialized after save()"
    return m


def _seed_data(m: Mycelium):
    """Seed test data: concepts, edges, zones, fusions."""
    m.observe(["alpha", "beta", "gamma", "delta"])
    m.observe(["alpha", "beta"])  # reinforce
    m.observe(["gamma", "delta"])  # reinforce
    # Add zones
    if m._db is not None:
        with m._db.transaction() as txn:
            # Tag some edges with zones
            rows = txn.execute("SELECT a, b FROM edges LIMIT 4").fetchall()
            for i, (a, b) in enumerate(rows):
                zone = f"zone_{i % 2}"
                txn.execute(
                    "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                    (a, b, zone))
                # Add second zone on first edge for bridge testing
                if i == 0:
                    txn.execute(
                        "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                        (a, b, "zone_1"))


class TestVacuumWiring:
    """T1: vacuum_if_needed() should call db.vacuum()."""

    def test_vacuum_calls_db_method(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        m.observe(["test", "data"])
        assert m._db is not None

        with patch.object(m._db, 'vacuum') as mock_vacuum:
            result = m.vacuum_if_needed()
            assert result is True
            mock_vacuum.assert_called_once()

    def test_vacuum_handles_error(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        m.observe(["test", "data"])

        with patch.object(m._db, 'vacuum', side_effect=sqlite3.OperationalError("locked")):
            result = m.vacuum_if_needed()
            assert result is False

    def test_vacuum_no_db(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        m._db = None
        assert m.vacuum_if_needed() is False


class TestGetZonesWiring:
    """T2: get_zones() should call db.get_zone_counts()."""

    def test_get_zones_calls_db_method(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)

        with patch.object(m._db, 'get_zone_counts', return_value={"zone_0": 5, "zone_1": 3}) as mock:
            result = m.get_zones()
            mock.assert_called_once()
            assert "zone_0" in result
            assert result["zone_0"] == 5

    def test_get_zones_returns_sorted(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)

        with patch.object(m._db, 'get_zone_counts', return_value={"small": 1, "big": 10}):
            result = m.get_zones()
            keys = list(result.keys())
            assert keys[0] == "big"  # sorted descending


class TestGetBridgesWiring:
    """T3: get_bridges() should call db.get_multi_zone_edges()."""

    def test_get_bridges_calls_db_method(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)

        original_method = m._db.get_multi_zone_edges
        called = [False]

        def spy(*args, **kwargs):
            called[0] = True
            return original_method(*args, **kwargs)

        with patch.object(m._db, 'get_multi_zone_edges', side_effect=spy):
            bridges = m.get_bridges()
            assert called[0], "get_multi_zone_edges() was not called"

    def test_get_bridges_returns_list(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)
        bridges = m.get_bridges()
        assert isinstance(bridges, list)


class TestDetectAnomaliesWiring:
    """T4: detect_anomalies() should call db.get_zone_avg_count()."""

    def test_detect_anomalies_calls_db_method(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)

        original_method = m._db.get_zone_avg_count
        call_count = [0]

        def spy(zone):
            call_count[0] += 1
            return original_method(zone)

        with patch.object(m._db, 'get_zone_avg_count', side_effect=spy):
            result = m.detect_anomalies()
            assert call_count[0] > 0, "get_zone_avg_count() was never called"
            assert "weak_zones" in result

    def test_detect_anomalies_returns_structure(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        _seed_data(m)
        result = m.detect_anomalies()
        assert "isolated" in result
        assert "hubs" in result
        assert "weak_zones" in result


class TestDecayDeleteStaleFusions:
    """T5: decay() should call db.delete_stale_fusions() after removing dead edges."""

    def test_decay_calls_delete_stale_fusions(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        # Create old data that will decay
        m.observe(["old_concept", "stale_data"])
        # Artificially age the connection (30 days ago, realistic epoch-day)
        if m._db is not None:
            from mycelium_db import today_days
            old_date = today_days() - 30
            with m._db.transaction() as txn:
                txn.execute("UPDATE edges SET last_seen = ?, count = 0.001", (old_date,))

        with patch.object(m._db, 'delete_stale_fusions', return_value=0) as mock:
            removed = m.decay(days=1)
            if removed > 0:
                mock.assert_called_once_with(min_edge_count=1)

    def test_decay_no_dead_no_stale_call(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        m.observe(["fresh", "data"])
        # Don't age — nothing should die

        with patch.object(m._db, 'delete_stale_fusions') as mock:
            m.decay(days=1)
            # If nothing died, delete_stale_fusions should NOT be called
            mock.assert_not_called()

    def test_decay_returns_count(self, tmp_path):
        m = _make_mycelium(str(tmp_path))
        m.observe(["test", "data"])
        result = m.decay(days=1)
        assert isinstance(result, int)
        assert result >= 0


class TestEndToEnd:
    """E2E: Verify that the full pipeline still works with wired DB functions."""

    def test_full_cycle(self, tmp_path):
        """observe -> save -> zones -> bridges -> anomalies -> decay -> vacuum"""
        m = _make_mycelium(str(tmp_path))

        # Step 1: Observe data
        m.observe(["python", "compression", "memory", "tokens"])
        m.observe(["python", "compression"])
        m.observe(["memory", "tokens", "context"])

        # Step 2: Save
        m.save()

        # Step 3: Zones (returns dict even if empty)
        zones = m.get_zones()
        assert isinstance(zones, dict)

        # Step 4: Bridges
        bridges = m.get_bridges()
        assert isinstance(bridges, list)

        # Step 5: Anomalies
        anomalies = m.detect_anomalies()
        assert "isolated" in anomalies

        # Step 6: Decay
        removed = m.decay(days=1)
        assert isinstance(removed, int)

        # Step 7: Vacuum
        result = m.vacuum_if_needed()
        assert result is True

        m.save()
