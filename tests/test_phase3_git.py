"""Phase 3 tests — GitBackend (G1-G5).

Tests cover: auto-init, push/pull, CRDT merge, delta sync,
remote support, factory integration, tombstone respect.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from muninn.mycelium_db import MyceliumDB, today_days
from muninn.sync_backend import (
    GitBackend, SharedFileBackend, SyncPayload,
    get_sync_backend,
)


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


# ── G1: GitBackend core ─────────────────────────────────────────

class TestG1Core:
    def test_auto_init_creates_repo(self, tmp_path):
        """G1: GitBackend auto-creates a git repo."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)
        assert (repo / ".git").exists()
        assert (repo / "meta.json").exists()

    def test_push_creates_json(self, tmp_path):
        """G1: Push exports edges to a JSON file in the repo."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)
        local = _make_db(tmp_path, "local.db", edges=[
            ("python", "code", 5),
            ("memory", "compress", 3),
        ])
        n = backend.push(SyncPayload(repo_name="test-repo", zone="dev"), local)
        local.close()

        assert n == 2
        assert (repo / "test-repo.json").exists()
        data = json.loads((repo / "test-repo.json").read_text(encoding="utf-8"))
        assert len(data["edges"]) == 2
        assert data["repo"] == "test-repo"

    def test_push_commits_to_git(self, tmp_path):
        """G1: Push creates a git commit."""
        import subprocess
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)
        local = _make_db(tmp_path, "local.db", edges=[("a", "b", 1)])
        backend.push(SyncPayload(repo_name="r", zone="z"), local)
        local.close()

        r = subprocess.run(
            ["git", "log", "--oneline"], cwd=str(repo),
            capture_output=True, text=True
        )
        assert "sync: r" in r.stdout

    def test_pull_into_local(self, tmp_path):
        """G1: Pull brings edges from git repo into local DB."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        # Push from repo A
        repo_a = _make_db(tmp_path, "a.db", edges=[
            ("neural", "network", 10),
            ("deep", "learning", 7),
        ])
        backend.push(SyncPayload(repo_name="repo-a", zone="ml"), repo_a)
        repo_a.close()

        # Pull into repo B
        repo_b = _make_db(tmp_path, "b.db")
        n = backend.pull(repo_b, max_pull=100)

        assert n == 2
        assert repo_b.has_connection("neural", "network")
        assert repo_b.has_connection("deep", "learning")
        repo_b.close()

    def test_pull_no_duplicates(self, tmp_path):
        """G1: Pull doesn't overwrite existing connections."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        src = _make_db(tmp_path, "src.db", edges=[("x", "y", 5)])
        backend.push(SyncPayload(repo_name="src", zone="z"), src)
        src.close()

        local = _make_db(tmp_path, "local.db", edges=[("x", "y", 100)])
        n = backend.pull(local, max_pull=100)
        assert n == 0  # Already exists
        local.close()

    def test_status(self, tmp_path):
        """G1: Status reports correct info."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)
        status = backend.status()
        assert status["type"] == "git"
        assert status["exists"] is True

    def test_pull_nonexistent(self, tmp_path):
        """G1: Pull from nonexistent repo returns 0."""
        backend = GitBackend.__new__(GitBackend)
        backend.repo_path = tmp_path / "nonexistent"
        backend.remote = None
        local = _make_db(tmp_path, "local.db")
        assert backend.pull(local) == 0
        local.close()


# ── G2: CRDT merge ──────────────────────────────────────────────

class TestG2CRDTMerge:
    def test_higher_count_updates(self, tmp_path):
        """G2: Pull updates count when remote has higher value."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        # Push with count=20
        src = _make_db(tmp_path, "src.db", edges=[("a", "b", 20)])
        backend.push(SyncPayload(repo_name="src", zone="z"), src)
        src.close()

        # Local has count=5
        local = _make_db(tmp_path, "local.db", edges=[("a", "b", 5)])
        backend.pull(local, max_pull=100)

        conn = local.get_connection("a", "b")
        assert conn["count"] == 20  # Updated to higher
        local.close()

    def test_roundtrip_two_repos(self, tmp_path):
        """G2: Full roundtrip — repo A pushes, repo B pulls."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        # Repo A pushes
        a = _make_db(tmp_path, "a.db", edges=[
            ("graph", "theory", 8),
        ], fusions=[("graph", "theory", "graph_theory", 0.9)])
        backend.push(SyncPayload(repo_name="a", zone="math"), a)
        a.close()

        # Repo B pulls
        b = _make_db(tmp_path, "b.db")
        n = backend.pull(b, max_pull=100)
        assert n >= 1
        assert b.has_connection("graph", "theory")
        assert b.has_fusion("graph", "theory")
        b.close()


# ── G3: Auto-init ───────────────────────────────────────────────

class TestG3AutoInit:
    def test_init_repo_static(self, tmp_path):
        """G3: GitBackend.init_repo() creates and returns backend."""
        repo = tmp_path / "new_sync"
        backend = GitBackend.init_repo(repo)
        assert isinstance(backend, GitBackend)
        assert (repo / ".git").exists()

    def test_init_idempotent(self, tmp_path):
        """G3: Calling init twice doesn't crash."""
        repo = tmp_path / "idem"
        GitBackend(repo)
        GitBackend(repo)  # Second init = no crash
        assert (repo / ".git").exists()


# ── G4: Remote support ──────────────────────────────────────────

class TestG4Remote:
    def test_remote_stored(self, tmp_path):
        """G4: Remote URL is stored in the backend."""
        repo = tmp_path / "remote_test"
        backend = GitBackend(repo, remote="git@github.com:test/sync.git")
        assert backend.remote == "git@github.com:test/sync.git"

    def test_status_shows_remote(self, tmp_path):
        """G4: Status includes remote info."""
        repo = tmp_path / "remote_status"
        backend = GitBackend(repo, remote="https://example.com/sync.git")
        status = backend.status()
        assert status["remote"] == "https://example.com/sync.git"


# ── G5: Delta sync ──────────────────────────────────────────────

class TestG5DeltaSync:
    def test_delta_uses_last_seen(self, tmp_path):
        """G5: Push only exports edges newer than last_sync_day."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        # Set last_sync_day to today (all edges are "old")
        meta_file = repo / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["last_sync_day"] = today_days() + 1  # Future = nothing is newer
        meta_file.write_text(json.dumps(meta), encoding="utf-8")

        local = _make_db(tmp_path, "local.db", edges=[("a", "b", 5)])
        n = backend.push(SyncPayload(repo_name="delta", zone="z"), local)
        local.close()

        # Should export 0 edges (all are "old")
        data = json.loads((repo / "delta.json").read_text(encoding="utf-8"))
        assert len(data["edges"]) == 0

    def test_meta_tracks_last_sync(self, tmp_path):
        """G5: Meta file updates last_sync_day after push."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        local = _make_db(tmp_path, "local.db", edges=[("x", "y", 1)])
        backend.push(SyncPayload(repo_name="test", zone="z"), local)
        local.close()

        meta = json.loads((repo / "meta.json").read_text(encoding="utf-8"))
        assert "last_sync_day" in meta
        assert meta["last_sync_day"] == today_days()


# ── H4: Tombstone respect in git pull ────────────────────────────

class TestGitTombstones:
    def test_tombstoned_edges_skipped(self, tmp_path):
        """H4: Git pull respects tombstones."""
        repo = tmp_path / "sync.git"
        backend = GitBackend(repo)

        src = _make_db(tmp_path, "src.db", edges=[
            ("alive", "edge", 10),
            ("dead", "edge", 5),
        ])
        backend.push(SyncPayload(repo_name="src", zone="z"), src)
        src.close()

        local = _make_db(tmp_path, "local.db")
        local._get_or_create_concept("dead")
        local._get_or_create_concept("edge")
        local.commit()
        local.record_tombstone("dead", "edge")

        backend.pull(local, max_pull=100)
        assert local.has_connection("alive", "edge")
        assert not local.has_connection("dead", "edge")
        local.close()


# ── Factory integration ─────────────────────────────────────────

class TestGitFactory:
    def test_factory_creates_git_backend(self, tmp_path):
        """Factory returns GitBackend when config says git."""
        config = {
            "backend": "git",
            "git_path": str(tmp_path / "factory.git"),
        }
        backend = get_sync_backend(config)
        assert isinstance(backend, GitBackend)

    def test_push_pull_via_factory(self, tmp_path):
        """Full push/pull via factory-created GitBackend."""
        config = {
            "backend": "git",
            "git_path": str(tmp_path / "factory2.git"),
        }
        backend = get_sync_backend(config)

        local = _make_db(tmp_path, "local.db", edges=[("test", "factory", 3)])
        backend.push(SyncPayload(repo_name="fac", zone="z"), local)
        local.close()

        other = _make_db(tmp_path, "other.db")
        n = backend.pull(other, max_pull=100)
        assert n >= 1
        other.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
