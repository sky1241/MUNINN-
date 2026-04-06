"""Tests for auto_label_zones() wiring in save().

Validates that:
1. auto_label_zones() is called during save() when federated=True and >= 50 connections
2. auto_label_zones() is NOT called when federated=False
3. auto_label_zones() is NOT called when < 50 connections
4. Failures in auto_label_zones() don't break save()
"""

import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium import Mycelium
from mycelium_db import MyceliumDB, today_days


def _make_mycelium(tmp_path: str, federated: bool = False) -> Mycelium:
    """Create a test mycelium with SQLite backend."""
    repo = Path(tmp_path) / "repo"
    repo.mkdir(exist_ok=True)
    m = Mycelium(repo_path=repo, federated=federated)
    m.observe(["seed_a", "seed_b"])
    m.save()
    assert m._db is not None
    return m


def _seed_many_connections(m: Mycelium, n: int = 60):
    """Create enough connections to trigger zone detection (>= 50)."""
    # Generate concept groups that create pairwise connections
    batch_size = 4
    for i in range(0, n, batch_size):
        concepts = [f"concept_{i+j}" for j in range(batch_size)]
        m.observe(concepts)
    m.save()


class TestAutoLabelZonesWiring:
    """auto_label_zones() should be called in save() under right conditions."""

    def test_called_when_federated_and_enough_data(self, tmp_path):
        """Federated + >= 50 connections = auto_label_zones() called."""
        m = _make_mycelium(str(tmp_path), federated=True)
        _seed_many_connections(m, n=60)

        with patch.object(m, 'auto_label_zones', return_value={}) as mock:
            m.save()
            mock.assert_called_once()

    def test_not_called_when_not_federated(self, tmp_path):
        """federated=False = auto_label_zones() NOT called."""
        m = _make_mycelium(str(tmp_path), federated=False)
        _seed_many_connections(m, n=60)

        with patch.object(m, 'auto_label_zones', return_value={}) as mock:
            m.save()
            mock.assert_not_called()

    def test_not_called_when_few_connections(self, tmp_path):
        """< 50 connections = auto_label_zones() NOT called."""
        m = _make_mycelium(str(tmp_path), federated=True)
        # Only seed_a/seed_b from _make_mycelium = 1 connection, way under 50

        with patch.object(m, 'auto_label_zones', return_value={}) as mock:
            m.save()
            mock.assert_not_called()

    def test_failure_doesnt_break_save(self, tmp_path):
        """If auto_label_zones() raises, save() should still complete."""
        m = _make_mycelium(str(tmp_path), federated=True)
        _seed_many_connections(m, n=60)

        with patch.object(m, 'auto_label_zones', side_effect=RuntimeError("scipy missing")):
            # Should not raise
            m.save()
            # Verify data is still persisted
            assert m._db is not None
            assert m._db.connection_count() >= 50

    def test_save_still_works_after_zone_labeling(self, tmp_path):
        """E2E: save with real auto_label_zones (may return {} if no scipy)."""
        m = _make_mycelium(str(tmp_path), federated=True)
        _seed_many_connections(m, n=60)

        # Just verify save() doesn't crash — auto_label_zones may fail gracefully
        # if scipy is not installed
        m.save()
        assert m._db.connection_count() >= 50
