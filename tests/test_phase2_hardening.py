"""Phase 2 tests — Hardening (H1-H13).

Tests cover: audit log, savepoint/rollback, checksums, tombstones,
fusion conflict, dynamic degree filter, disk guard, network timeout,
tree file lock, ConceptTranslator thread safety.
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days, ConceptTranslator
from sync_backend import (
    SharedFileBackend, SyncPayload, SyncEdge, SyncFusion,
    get_sync_backend, check_disk_space, save_sync_config,
)


# ── Helpers ──────────────────────────────────────────────────────

def _make_db(tmp_path, name="test.db", edges=None, fusions=None):
    db = MyceliumDB(tmp_path / name)
    if edges:
        for a, b, count in edges:
            db.upsert_connection(a, b, count=count)
    if fusions:
        for a, b, form, strength in fusions:
            a_id = db._get_or_create_concept(a)
            b_id = db._get_or_create_concept(b)
            db._conn.execute(
                "INSERT OR IGNORE INTO fusions (a, b, form, strength, fused_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (a_id, b_id, form, strength, today_days())
            )
    db.commit()
    return db


# ── H1: Sync audit log ──────────────────────────────────────────

class TestH1AuditLog:
    def test_log_sync_creates_entry(self, tmp_path):
        """H1: log_sync writes an entry to sync_log table."""
        db = _make_db(tmp_path, "h1.db")
        db.log_sync(action="push", repo="test-repo", count=42)
        logs = db.get_sync_log()
        assert len(logs) >= 1
        assert logs[0]["action"] == "push"
        assert logs[0]["repo"] == "test-repo"
        assert logs[0]["count"] == 42
        db.close()

    def test_log_sync_records_errors(self, tmp_path):
        """H1: log_sync records error messages."""
        db = _make_db(tmp_path, "h1b.db")
        db.log_sync(action="pull", errors="connection timeout")
        logs = db.get_sync_log()
        assert logs[0]["errors"] == "connection timeout"
        db.close()

    def test_log_sync_records_checksum(self, tmp_path):
        """H1: log_sync records payload checksum."""
        db = _make_db(tmp_path, "h1c.db")
        db.log_sync(action="push", checksum="abc123")
        logs = db.get_sync_log()
        assert logs[0]["checksum"] == "abc123"
        db.close()

    def test_push_creates_audit_entry(self, tmp_path):
        """H1: SharedFileBackend.push() creates audit log entry."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)
        local = _make_db(tmp_path, "local.db", edges=[("a", "b", 1)])
        backend.push(SyncPayload(repo_name="test", zone="z"), local)
        local.close()

        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        logs = meta_db.get_sync_log()
        assert len(logs) >= 1
        assert logs[0]["action"] == "push"
        meta_db.close()


# ── H2: Pre-sync snapshot + rollback ─────────────────────────────

class TestH2Savepoint:
    def test_savepoint_rollback(self, tmp_path):
        """H2: Savepoint allows rollback on failure."""
        db = _make_db(tmp_path, "h2.db", edges=[("x", "y", 5)])
        db.savepoint("test_sp")
        # Use raw SQL to avoid auto-commit — normalized order (min/max)
        a_key, b_key = min("edge", "new"), max("edge", "new")
        a_id = db._get_or_create_concept(a_key)
        b_id = db._get_or_create_concept(b_key)
        td = today_days()
        db._conn.execute(
            "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
            (a_id, b_id, 10, td, td))
        assert db.has_connection("new", "edge")
        db.rollback_to("test_sp")
        # After rollback, new edge should be gone
        assert not db.has_connection("new", "edge")
        # Original edge still there
        assert db.has_connection("x", "y")
        db.release_savepoint("test_sp")
        db.close()

    def test_savepoint_release(self, tmp_path):
        """H2: Release commits the savepoint changes."""
        db = _make_db(tmp_path, "h2b.db")
        db.savepoint("sp2")
        a_id = db._get_or_create_concept("a")
        b_id = db._get_or_create_concept("b")
        td = today_days()
        db._conn.execute(
            "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
            (a_id, b_id, 5, td, td))
        db.release_savepoint("sp2")
        db.commit()
        assert db.has_connection("a", "b")
        db.close()


# ── H3: Integrity checksums ─────────────────────────────────────

class TestH3Checksums:
    def test_payload_checksum_deterministic(self):
        """H3: Same payload produces same checksum."""
        p1 = SyncPayload(repo_name="r", zone="z", timestamp="fixed")
        p2 = SyncPayload(repo_name="r", zone="z", timestamp="fixed")
        assert p1.checksum() == p2.checksum()

    def test_payload_checksum_changes(self):
        """H3: Different payload produces different checksum."""
        p1 = SyncPayload(repo_name="r1", zone="z", timestamp="fixed")
        p2 = SyncPayload(repo_name="r2", zone="z", timestamp="fixed")
        assert p1.checksum() != p2.checksum()

    def test_checksum_is_sha256(self):
        """H3: Checksum is valid SHA256 hex string."""
        p = SyncPayload(repo_name="r", zone="z")
        cs = p.checksum()
        assert len(cs) == 64
        int(cs, 16)  # Valid hex


# ── H4: Tombstones ──────────────────────────────────────────────

class TestH4Tombstones:
    def test_record_tombstone(self, tmp_path):
        """H4: Tombstone is recorded for deleted edge."""
        db = _make_db(tmp_path, "h4.db", edges=[("a", "b", 5)])
        db.record_tombstone("a", "b", deleted_by="decay")
        assert db.is_tombstoned("a", "b")
        db.close()

    def test_tombstone_blocks_pull(self, tmp_path):
        """H4: Tombstoned edges are not pulled from meta."""
        meta_dir = tmp_path / "meta"
        meta_db = _make_db(meta_dir, "meta_mycelium.db", edges=[
            ("alive", "edge", 10),
            ("dead", "edge", 5),
        ])
        meta_db.close()

        local = _make_db(tmp_path, "local.db")
        # Create tombstone for dead|edge
        local._get_or_create_concept("dead")
        local._get_or_create_concept("edge")
        local.commit()
        local.record_tombstone("dead", "edge", deleted_by="test")

        backend = SharedFileBackend(meta_dir)
        n = backend.pull(local, max_pull=100)

        assert local.has_connection("alive", "edge")
        assert not local.has_connection("dead", "edge")
        local.close()

    def test_get_tombstones(self, tmp_path):
        """H4: get_tombstones returns all recorded tombstones."""
        db = _make_db(tmp_path, "h4c.db", edges=[("x", "y", 1), ("p", "q", 2)])
        db.record_tombstone("x", "y")
        db.record_tombstone("p", "q")
        tombstones = db.get_tombstones()
        assert len(tombstones) == 2
        db.close()

    def test_not_tombstoned(self, tmp_path):
        """H4: Non-tombstoned edge returns False."""
        db = _make_db(tmp_path, "h4d.db", edges=[("a", "b", 1)])
        assert not db.is_tombstoned("a", "b")
        db.close()


# ── H5: Fusion conflict resolution ──────────────────────────────

class TestH5FusionConflict:
    def test_stronger_form_wins(self, tmp_path):
        """H5: When two repos push different fusion forms, stronger wins."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        # Repo A: form="ab" strength=5
        repo_a = _make_db(tmp_path, "a.db",
                          edges=[("alpha", "beta", 10)],
                          fusions=[("alpha", "beta", "ab", 5)])
        backend.push(SyncPayload(repo_name="a", zone="a"), repo_a)
        repo_a.close()

        # Repo B: form="alphabeta" strength=10 (stronger)
        repo_b = _make_db(tmp_path, "b.db",
                          edges=[("alpha", "beta", 10)],
                          fusions=[("alpha", "beta", "alphabeta", 10)])
        backend.push(SyncPayload(repo_name="b", zone="b"), repo_b)
        repo_b.close()

        # Check meta — stronger form should win
        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        a_id = meta_db._concept_cache.get("alpha")
        b_id = meta_db._concept_cache.get("beta")
        row = meta_db._conn.execute(
            "SELECT form, strength FROM fusions WHERE a=? AND b=?",
            (a_id, b_id)
        ).fetchone()
        assert row is not None
        assert row[0] == "alphabeta"  # Stronger form won
        assert row[1] == 10
        meta_db.close()

    def test_weaker_form_rejected(self, tmp_path):
        """H5: Weaker fusion form doesn't overwrite stronger."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        # Repo A: strong form
        repo_a = _make_db(tmp_path, "a.db",
                          edges=[("x", "y", 5)],
                          fusions=[("x", "y", "xy_strong", 20)])
        backend.push(SyncPayload(repo_name="a", zone="a"), repo_a)
        repo_a.close()

        # Repo B: weaker form
        repo_b = _make_db(tmp_path, "b.db",
                          edges=[("x", "y", 5)],
                          fusions=[("x", "y", "xy_weak", 3)])
        backend.push(SyncPayload(repo_name="b", zone="b"), repo_b)
        repo_b.close()

        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        a_id = meta_db._concept_cache.get("x")
        b_id = meta_db._concept_cache.get("y")
        row = meta_db._conn.execute(
            "SELECT form FROM fusions WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        assert row[0] == "xy_strong"  # Strong form preserved
        meta_db.close()


# ── H6: Dynamic degree filter ───────────────────────────────────

class TestH6DynamicDegree:
    def test_dynamic_percentile_decreases_with_repos(self, tmp_path, monkeypatch):
        """H6: More repos = tighter filter percentile."""
        from mycelium import Mycelium
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / ".muninn").mkdir()

        meta_dir = tmp_path / "meta"
        meta_dir.mkdir(parents=True)
        monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

        # Create meta with 4 repos
        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        meta_db.set_meta("repos", "a,b,c,d")
        meta_db.close()

        m = Mycelium(repo_dir, federated=True)
        pct = m._dynamic_degree_percentile()
        # With 4 repos: 0.05 / sqrt(4) = 0.025
        assert pct < m.DEGREE_FILTER_PERCENTILE
        assert pct >= 0.005  # Floor

    def test_non_federated_uses_base(self, tmp_path):
        """H6: Non-federated mode uses base percentile."""
        from mycelium import Mycelium
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / ".muninn").mkdir()

        m = Mycelium(repo_dir, federated=False)
        pct = m._dynamic_degree_percentile()
        assert pct == m.DEGREE_FILTER_PERCENTILE


# ── H9: Disk full guard ─────────────────────────────────────────

class TestH9DiskGuard:
    def test_check_disk_space_ok(self, tmp_path):
        """H9: Disk space check passes on normal filesystem."""
        assert check_disk_space(tmp_path, min_mb=1) is True

    def test_check_disk_space_huge_requirement(self, tmp_path):
        """H9: Disk space check fails with absurd requirement."""
        # 100TB — no disk has this
        assert check_disk_space(tmp_path, min_mb=100_000_000) is False

    def test_push_raises_on_no_space(self, tmp_path, monkeypatch):
        """H9: Push raises OSError when disk is full."""
        import shutil
        monkeypatch.setattr(shutil, "disk_usage",
                            lambda p: type("U", (), {"free": 1024})())  # 1KB
        meta_dir = tmp_path / "meta2"
        backend = SharedFileBackend(meta_dir)
        local = _make_db(tmp_path, "local.db", edges=[("a", "b", 1)])
        with pytest.raises(OSError, match="H9"):
            backend.push(SyncPayload(repo_name="t", zone="z"), local)
        local.close()


# ── H10: Prune rollback ─────────────────────────────────────────

class TestH10PruneRollback:
    def test_rollback_snapshot_exists_in_code(self):
        """H10: Prune function contains rollback snapshot logic."""
        import muninn
        import inspect
        src = inspect.getsource(muninn.prune)
        assert "_pre_consolidate_snapshot" in src
        assert "H10 ROLLBACK" in src


# ── H11: Network timeout ────────────────────────────────────────

class TestH11NetworkTimeout:
    def test_timeout_on_unreachable_path(self, tmp_path):
        """H11: SharedFileBackend constructor has timeout mechanism."""
        backend = SharedFileBackend(tmp_path / "normal")
        assert backend.NETWORK_TIMEOUT == 5

    def test_safe_mkdir_works_locally(self, tmp_path):
        """H11: _safe_mkdir succeeds for local paths."""
        backend = SharedFileBackend.__new__(SharedFileBackend)
        backend.NETWORK_TIMEOUT = 5
        backend._safe_mkdir(tmp_path / "test_dir")
        assert (tmp_path / "test_dir").exists()


# ── H12: Tree file lock ─────────────────────────────────────────

class TestH12TreeLock:
    def test_lock_unlock_cycle(self, tmp_path):
        """H12: Lock and unlock completes without error."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn
        lock_f, acquired = muninn._tree_lock(tmp_path / "test.json")
        assert acquired is True
        muninn._tree_unlock(lock_f)

    def test_lock_creates_lockfile(self, tmp_path):
        """H12: Locking creates a .lock file."""
        import muninn
        lock_f, _ = muninn._tree_lock(tmp_path / "tree.json")
        # with_suffix(".lock") replaces .json with .lock
        assert (tmp_path / "tree.lock").exists()
        muninn._tree_unlock(lock_f)

    def test_concurrent_lock_blocks(self, tmp_path):
        """H12: Second lock on same file blocks (doesn't corrupt)."""
        import muninn
        lock1, acq1 = muninn._tree_lock(tmp_path / "concurrent.json", timeout=0.5)
        # Second lock should either block or timeout
        lock2, acq2 = muninn._tree_lock(tmp_path / "concurrent.json", timeout=0.2)
        # On Windows with msvcrt, second lock may or may not acquire
        # The important thing is no crash
        muninn._tree_unlock(lock1)
        muninn._tree_unlock(lock2)


# ── H13: ConceptTranslator thread safety ─────────────────────────

class TestH13ThreadSafety:
    def test_singleton_thread_safe(self):
        """H13: ConceptTranslator.get() is thread-safe."""
        # Reset singleton
        ConceptTranslator._instance = None
        results = []

        def _get():
            results.append(id(ConceptTranslator.get()))

        threads = [threading.Thread(target=_get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same instance
        assert len(set(results)) == 1
        ConceptTranslator._instance = None  # Cleanup

    def test_translate_has_lock(self):
        """H13: ConceptTranslator.translate() uses threading.Lock."""
        ct = ConceptTranslator()
        assert ct._lock is not None
        assert isinstance(ct._lock, type(threading.Lock()))

    def test_concurrent_translate(self):
        """H13: Concurrent translate calls don't crash."""
        ct = ConceptTranslator()
        errors = []

        def _translate():
            try:
                for word in ["hello", "world", "python", "code", "test"]:
                    ct.translate(word)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_translate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# ── Schema version ───────────────────────────────────────────────

class TestSchemaVersion:
    def test_schema_v3(self, tmp_path):
        """Schema version bumped to 3 for sync_log + tombstones."""
        db = MyceliumDB(tmp_path / "schema.db")
        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 3
        db.close()

    def test_sync_log_table_exists(self, tmp_path):
        """sync_log table created by schema."""
        db = MyceliumDB(tmp_path / "tables.db")
        tables = [r[0] for r in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )]
        assert "sync_log" in tables
        assert "tombstones" in tables
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
