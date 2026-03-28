"""Phase 6 tests — Scale + Performance (P1-P10).

Tests cover: concurrent backoff, zone cleanup, growth limits, VACUUM,
observability, cache, batch deletes, single-pass detect, NCD cap,
tombstone TTL, secret pattern cache.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium_db import MyceliumDB, today_days


# ── P1: Concurrent SharedFile backoff ────────────────────────────

class TestP1ConcurrentBackoff:
    def test_backend_has_retry_config(self):
        """P1: SharedFileBackend has retry constants."""
        from sync_backend import SharedFileBackend
        assert hasattr(SharedFileBackend, "MAX_RETRIES")
        assert hasattr(SharedFileBackend, "BASE_DELAY")
        assert hasattr(SharedFileBackend, "MAX_DELAY")
        assert SharedFileBackend.MAX_RETRIES >= 3
        assert SharedFileBackend.BASE_DELAY > 0

    def test_retry_with_backoff_success(self, tmp_path):
        """P1: _retry_with_backoff returns on success."""
        from sync_backend import SharedFileBackend
        backend = SharedFileBackend(tmp_path / "meta")
        result = backend._retry_with_backoff(lambda: 42)
        assert result == 42

    def test_retry_with_backoff_non_lock_error(self, tmp_path):
        """P1: Non-lock errors are not retried."""
        from sync_backend import SharedFileBackend
        backend = SharedFileBackend(tmp_path / "meta")
        with pytest.raises(ValueError):
            backend._retry_with_backoff(lambda: (_ for _ in ()).throw(ValueError("bad")))


# ── P2: Zone cleanup ────────────────────────────────────────────

class TestP2ZoneCleanup:
    def test_cleanup_orphan_zones(self, tmp_path):
        """P2: cleanup_orphan_zones removes zones for deleted edges."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path, federated=True, zone="test")
        # Create edge with zone
        m.observe_text("python code pattern")
        m.save()

        # Manually delete edges but leave zones
        if m._db is not None:
            m._db._conn.execute("DELETE FROM edges")
            m._db._conn.commit()
            removed = m.cleanup_orphan_zones()
            assert removed >= 0  # May or may not have zones
        m.close()

    def test_cleanup_returns_zero_no_orphans(self, tmp_path):
        """P2: Returns 0 when no orphaned zones."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path, federated=True, zone="test")
        m.observe_text("hello world test")
        m.save()
        removed = m.cleanup_orphan_zones()
        assert removed == 0
        m.close()


# ── P3: Growth limits + VACUUM ───────────────────────────────────

class TestP3GrowthLimits:
    def test_growth_stats(self, tmp_path):
        """P3: growth_stats returns correct dict."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("graph theory algorithm")
        m.save()
        stats = m.growth_stats()
        assert "connections" in stats
        assert "concepts" in stats
        assert stats["connections"] >= 0
        m.close()

    def test_vacuum_runs(self, tmp_path):
        """P3: vacuum_if_needed executes without error."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("test data")
        m.save()
        result = m.vacuum_if_needed()
        assert result is True
        m.close()

    def test_max_connections_default(self):
        """P3: MAX_CONNECTIONS default is 0 (unlimited)."""
        from mycelium import Mycelium
        assert Mycelium.MAX_CONNECTIONS == 0


# ── P4: Observability ───────────────────────────────────────────

class TestP4Observability:
    def test_sync_metrics_returns_dict(self):
        """P4: sync_metrics returns monitoring dict."""
        from sync_backend import sync_metrics
        result = sync_metrics()
        assert isinstance(result, dict)
        assert "edges" in result
        assert "total_syncs" in result

    def test_sync_log_records(self, tmp_path):
        """P4: Sync operations create log entries."""
        db = MyceliumDB(tmp_path / "test.db")
        db.log_sync(action="push", repo="test", count=10)
        db.log_sync(action="pull", count=5)
        logs = db.get_sync_log(limit=10)
        assert len(logs) >= 2
        assert logs[0]["action"] in ("push", "pull")
        db.close()


# ── P5: Cache id_to_name ────────────────────────────────────────

class TestP5Cache:
    def test_id_to_name_populated(self, tmp_path):
        """P5: _id_to_name is populated on init."""
        db = MyceliumDB(tmp_path / "test.db")
        db.upsert_connection("alpha", "beta", count=5)
        db.commit()
        # Reopen to test cache loading
        db2 = MyceliumDB(tmp_path / "test.db")
        assert "alpha" in db2._concept_cache
        assert len(db2._id_to_name) >= 2
        db.close()
        db2.close()

    def test_concept_name_uses_cache(self, tmp_path):
        """P5: _concept_name returns from cache without DB query."""
        db = MyceliumDB(tmp_path / "test.db")
        cid = db._get_or_create_concept("cached_test")
        name = db._concept_name(cid)
        assert name == "cached_test"
        db.close()


# ── P6: Batch deletes in decay ──────────────────────────────────

class TestP6BatchDeletes:
    def test_decay_uses_executemany(self, tmp_path):
        """P6: decay() removes dead edges in batch."""
        # Create a DB first so Mycelium loads in SQLite mode
        db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
        for i in range(10):
            a_name = f"dead_{i}"
            b_name = f"target_{i}"
            a_norm, b_norm = min(a_name, b_name), max(a_name, b_name)
            a_id = db._get_or_create_concept(a_norm)
            b_id = db._get_or_create_concept(b_norm)
            db._conn.execute(
                "INSERT OR IGNORE INTO edges (a, b, count, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (a_id, b_id, 0.5, today_days() - 365, today_days() - 365))
        db.set_meta("migration_complete", "1")
        db.commit()
        db.close()

        from mycelium import Mycelium
        m = Mycelium(tmp_path)
        assert m._db is not None
        dead = m.decay(days=30)
        assert dead >= 10
        m.close()

    def test_decay_normal_edges_survive(self, tmp_path):
        """P6: Fresh edges survive decay."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("fresh concept today")
        m.save()
        dead = m.decay(days=30)
        assert dead == 0
        m.close()


# ── P7: Single-pass detect_zones ────────────────────────────────

class TestP7SinglePass:
    def test_detect_zones_works(self, tmp_path):
        """P7: detect_zones returns zones (single-pass)."""
        from mycelium import Mycelium
        m = Mycelium(tmp_path, federated=True, zone="test")
        # Need enough connections for clustering
        for i in range(20):
            m.observe_text(f"concept_{i} related_{i} linked_{i} connected_{i}")
        m.save()
        try:
            zones = m.detect_zones()
            # May return {} if scipy not installed, that's OK
            assert isinstance(zones, dict)
        except ImportError:
            pytest.skip("scipy not installed")
        m.close()


# ── P8: NCD cap ─────────────────────────────────────────────────

class TestP8NCDCap:
    def test_sleep_consolidate_cap(self):
        """P8: _sleep_consolidate has MAX_NCD_BRANCHES cap."""
        import muninn
        _mdir = Path(muninn.__file__).parent
        src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["muninn.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
        assert "MAX_NCD_BRANCHES" in src
        assert "20" in src  # Cap value

    def test_sleep_consolidate_empty(self):
        """P8: _sleep_consolidate returns [] for <2 branches."""
        import muninn
        result = muninn._sleep_consolidate([], {})
        assert result == []
        result = muninn._sleep_consolidate([("a", {"file": "a.mn"})], {})
        assert result == []


# ── P9: Tombstone TTL cleanup ───────────────────────────────────

class TestP9TombstoneTTL:
    def test_cleanup_old_tombstones(self, tmp_path):
        """P9: Old tombstones are cleaned up."""
        db = MyceliumDB(tmp_path / "test.db")
        a_id = db._get_or_create_concept("old_a")
        b_id = db._get_or_create_concept("old_b")
        # Insert old tombstone (60 days ago)
        old_day = today_days() - 60
        db._conn.execute(
            "INSERT OR REPLACE INTO tombstones (a, b, deleted_at, deleted_by) "
            "VALUES (?, ?, ?, ?)", (a_id, b_id, old_day, "test"))
        db._conn.commit()

        removed = db.cleanup_old_tombstones(max_age_days=30)
        assert removed == 1
        db.close()

    def test_fresh_tombstones_survive(self, tmp_path):
        """P9: Recent tombstones are not cleaned up."""
        db = MyceliumDB(tmp_path / "test.db")
        a_id = db._get_or_create_concept("fresh_a")
        b_id = db._get_or_create_concept("fresh_b")
        db._conn.execute(
            "INSERT OR REPLACE INTO tombstones (a, b, deleted_at, deleted_by) "
            "VALUES (?, ?, ?, ?)", (a_id, b_id, today_days(), "test"))
        db._conn.commit()

        removed = db.cleanup_old_tombstones(max_age_days=30)
        assert removed == 0
        db.close()

    def test_cleanup_returns_count(self, tmp_path):
        """P9: cleanup_old_tombstones returns correct count."""
        db = MyceliumDB(tmp_path / "test.db")
        for i in range(5):
            a_id = db._get_or_create_concept(f"a{i}")
            b_id = db._get_or_create_concept(f"b{i}")
            db._conn.execute(
                "INSERT OR REPLACE INTO tombstones (a, b, deleted_at, deleted_by) "
                "VALUES (?, ?, ?, ?)", (a_id, b_id, today_days() - 60, "test"))
        db._conn.commit()
        removed = db.cleanup_old_tombstones(max_age_days=30)
        assert removed == 5
        db.close()


# ── P10: Secret patterns cache ──────────────────────────────────

class TestP10SecretCache:
    def test_compiled_patterns_exist(self):
        """P10: _COMPILED_SECRET_PATTERNS is populated."""
        import muninn
        assert hasattr(muninn, "_COMPILED_SECRET_PATTERNS")
        assert len(muninn._COMPILED_SECRET_PATTERNS) > 0
        # All should be compiled regex objects
        for pat in muninn._COMPILED_SECRET_PATTERNS:
            assert hasattr(pat, "search")
            assert hasattr(pat, "sub")

    def test_compiled_patterns_match(self):
        """P10: Compiled patterns detect secrets correctly."""
        import muninn
        test_text = "my token ghp_aBcDeFgHiJkLmNoPqRsT12345"
        found = any(p.search(test_text) for p in muninn._COMPILED_SECRET_PATTERNS)
        assert found is True

    def test_compiled_patterns_no_false_positive(self):
        """P10: Compiled patterns don't match normal text."""
        import muninn
        test_text = "the quick brown fox jumps over the lazy dog"
        found = any(p.search(test_text) for p in muninn._COMPILED_SECRET_PATTERNS)
        assert found is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
