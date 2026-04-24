"""Phase 1 tests — SyncBackend, SharedFileBackend, Factory, Payload, F4 rewiring.

Tests cover F1-F7: ABC, SharedFileBackend, factory, payload serialization,
env var override, atomic config write, and Mycelium delegation.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

from muninn.mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days
from muninn.sync_backend import (
    SyncBackend, SharedFileBackend, SyncPayload, SyncEdge, SyncFusion,
    get_sync_backend, _load_sync_config, save_sync_config,
)


# ── Helpers ──────────────────────────────────────────────────────

def _make_db(tmp_path, name="test.db", edges=None, fusions=None):
    """Create a MyceliumDB with optional edges and fusions."""
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


# ── F1: SyncBackend ABC ─────────────────────────────────────────

class TestSyncBackendABC:
    def test_cannot_instantiate(self):
        """F1: SyncBackend is abstract — cannot instantiate directly."""
        with pytest.raises(TypeError):
            SyncBackend()

    def test_subclass_must_implement(self):
        """F1: Subclass without implementations raises TypeError."""
        class BadBackend(SyncBackend):
            pass
        with pytest.raises(TypeError):
            BadBackend()

    def test_shared_file_is_sync_backend(self):
        """F1: SharedFileBackend is a proper SyncBackend subclass."""
        with tempfile.TemporaryDirectory() as tmp:
            backend = SharedFileBackend(Path(tmp))
            assert isinstance(backend, SyncBackend)


# ── F2: SharedFileBackend push/pull ──────────────────────────────

class TestSharedFileBackend:
    def test_push_creates_meta_db(self, tmp_path):
        """F2: Push creates meta DB and stores edges."""
        local = _make_db(tmp_path, "local.db", edges=[
            ("python", "code", 5),
            ("memory", "compress", 3),
        ])
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        payload = SyncPayload(repo_name="test-repo", zone="test")
        n = backend.push(payload, local)

        assert n == 2
        assert (meta_dir / "meta_mycelium.db").exists()

        # Verify data in meta
        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        assert meta_db.has_connection("python", "code")
        assert meta_db.has_connection("memory", "compress")
        repos = meta_db.get_meta("repos", "")
        assert "test-repo" in repos
        meta_db.close()
        local.close()

    def test_pull_into_local(self, tmp_path):
        """F2: Pull brings edges from meta into local DB."""
        # Setup meta with data
        meta_dir = tmp_path / "meta"
        meta_db = _make_db(meta_dir, "meta_mycelium.db", edges=[
            ("neural", "network", 10),
            ("deep", "learning", 7),
        ])
        meta_db.close()

        # Pull into empty local
        local = _make_db(tmp_path, "local.db")
        backend = SharedFileBackend(meta_dir)
        n = backend.pull(local, max_pull=100)

        assert n == 2
        assert local.has_connection("neural", "network")
        assert local.has_connection("deep", "learning")
        local.close()

    def test_pull_no_duplicates(self, tmp_path):
        """F2: Pull does not overwrite existing local connections."""
        meta_dir = tmp_path / "meta"
        meta_db = _make_db(meta_dir, "meta_mycelium.db", edges=[
            ("python", "code", 5),
        ])
        meta_db.close()

        local = _make_db(tmp_path, "local.db", edges=[
            ("python", "code", 100),  # Local has higher count
        ])
        backend = SharedFileBackend(meta_dir)
        n = backend.pull(local, max_pull=100)

        assert n == 0  # Already exists, not pulled
        local.close()

    def test_push_pull_roundtrip(self, tmp_path):
        """F2: Push from repo A, pull into repo B — full roundtrip."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        # Repo A pushes
        repo_a = _make_db(tmp_path, "repo_a.db", edges=[
            ("graph", "theory", 8),
            ("node", "edge", 4),
        ], fusions=[
            ("graph", "theory", "graph_theory", 0.9),
        ])
        payload_a = SyncPayload(repo_name="repo-a", zone="math")
        backend.push(payload_a, repo_a)
        repo_a.close()

        # Repo B pulls
        repo_b = _make_db(tmp_path, "repo_b.db")
        n = backend.pull(repo_b, max_pull=100)

        assert n == 2
        assert repo_b.has_connection("graph", "theory")
        assert repo_b.has_connection("node", "edge")
        repo_b.close()

    def test_push_merge_strategy(self, tmp_path):
        """F2: CRDT merge — MAX(count), MIN(first_seen), MAX(last_seen)."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        # First push
        repo_a = _make_db(tmp_path, "repo_a.db", edges=[
            ("code", "python", 5),
        ])
        backend.push(SyncPayload(repo_name="a", zone="a"), repo_a)
        repo_a.close()

        # Second push with different counts
        repo_b = _make_db(tmp_path, "repo_b.db", edges=[
            ("code", "python", 10),
        ])
        backend.push(SyncPayload(repo_name="b", zone="b"), repo_b)
        repo_b.close()

        # Check meta — count should be MAX(5, 10) = 10
        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        # Query by joining concepts to avoid ID mismatch
        row = meta_db._conn.execute("""
            SELECT e.count FROM edges e
            JOIN concepts ca ON e.a = ca.id
            JOIN concepts cb ON e.b = cb.id
            WHERE ca.name = ? AND cb.name = ?
        """, ("code", "python")).fetchone()
        assert row is not None, "Edge not found in meta DB"
        assert row[0] == 10
        meta_db.close()

    def test_push_zone_tagging(self, tmp_path):
        """F2: Push tags edges with the payload zone."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        repo = _make_db(tmp_path, "repo.db", edges=[("a", "b", 1)])
        backend.push(SyncPayload(repo_name="r", zone="science"), repo)
        repo.close()

        meta_db = MyceliumDB(meta_dir / "meta_mycelium.db")
        a_id = meta_db._concept_cache["a"]
        b_id = meta_db._concept_cache["b"]
        zones = [r[0] for r in meta_db._conn.execute(
            "SELECT zone FROM edge_zones WHERE a=? AND b=?", (a_id, b_id)
        )]
        assert "science" in zones
        meta_db.close()

    def test_pull_with_query_concepts(self, tmp_path):
        """F2: Pull with query_concepts filters to relevant edges only."""
        meta_dir = tmp_path / "meta"
        meta_db = _make_db(meta_dir, "meta_mycelium.db", edges=[
            ("python", "code", 10),
            ("neural", "network", 5),
            ("graph", "theory", 3),
        ])
        meta_db.close()

        local = _make_db(tmp_path, "local.db")
        backend = SharedFileBackend(meta_dir)
        n = backend.pull(local, query_concepts=["python"], max_pull=100)

        assert n == 1  # Only python-related edges
        assert local.has_connection("python", "code")
        assert not local.has_connection("neural", "network")
        local.close()

    def test_pull_fusions(self, tmp_path):
        """F2: Pull includes fusions from meta."""
        meta_dir = tmp_path / "meta"
        meta_db = _make_db(meta_dir, "meta_mycelium.db",
                           edges=[("graph", "theory", 10)],
                           fusions=[("graph", "theory", "graph_theory", 0.9)])
        meta_db.close()

        local = _make_db(tmp_path, "local.db")
        backend = SharedFileBackend(meta_dir)
        backend.pull(local, max_pull=100)

        assert local.has_fusion("graph", "theory")
        local.close()

    def test_status(self, tmp_path):
        """F2: Status reports correct info."""
        meta_dir = tmp_path / "meta"
        backend = SharedFileBackend(meta_dir)

        # Before any push
        status = backend.status()
        assert status["type"] == "shared_file"
        assert not status["db_exists"]

        # After push
        repo = _make_db(tmp_path, "repo.db", edges=[("a", "b", 1)])
        backend.push(SyncPayload(repo_name="test", zone="z"), repo)
        repo.close()

        status = backend.status()
        assert status["db_exists"]
        assert status["connections"] >= 1
        assert "test" in status["repos"]

    def test_pull_nonexistent_meta(self, tmp_path):
        """F2: Pull from nonexistent meta returns 0."""
        backend = SharedFileBackend(tmp_path / "nonexistent")
        local = _make_db(tmp_path, "local.db")
        assert backend.pull(local) == 0
        local.close()


# ── F3: Factory ──────────────────────────────────────────────────

class TestFactory:
    def test_default_backend(self, tmp_path):
        """F3: Factory returns SharedFileBackend by default."""
        backend = get_sync_backend({"backend": "shared_file", "meta_path": str(tmp_path)})
        assert isinstance(backend, SharedFileBackend)

    def test_unknown_backend_falls_back(self, tmp_path):
        """F3: Unknown backend type falls back to SharedFileBackend."""
        backend = get_sync_backend({"backend": "unknown_type", "meta_path": str(tmp_path)})
        assert isinstance(backend, SharedFileBackend)

    def test_meta_path_from_config(self, tmp_path):
        """F3: Factory uses meta_path from config."""
        backend = get_sync_backend({"meta_path": str(tmp_path)})
        assert backend.meta_dir == tmp_path


# ── F5: SyncPayload serializer ───────────────────────────────────

class TestSyncPayload:
    def test_to_json_roundtrip(self):
        """F5: Payload serializes and deserializes correctly."""
        payload = SyncPayload(
            repo_name="test",
            zone="dev",
            edges=[SyncEdge("a", "b", 5.0, 100, 200, ["z1"])],
            fusions=[SyncFusion("a", "b", "ab", 0.8, 150)],
        )
        json_str = payload.to_json()
        restored = SyncPayload.from_json(json_str)

        assert restored.repo_name == "test"
        assert restored.zone == "dev"
        assert len(restored.edges) == 1
        assert restored.edges[0].a == "a"
        assert restored.edges[0].count == 5.0
        assert len(restored.fusions) == 1
        assert restored.fusions[0].form == "ab"

    def test_empty_payload(self):
        """F5: Empty payload serializes correctly."""
        payload = SyncPayload(repo_name="empty", zone="test")
        json_str = payload.to_json()
        restored = SyncPayload.from_json(json_str)
        assert restored.edges == []
        assert restored.fusions == []

    def test_valid_json(self):
        """F5: Payload produces valid JSON."""
        payload = SyncPayload(repo_name="x", zone="z")
        parsed = json.loads(payload.to_json())
        assert parsed["repo_name"] == "x"
        assert "timestamp" in parsed


# ── F6: Env var override ─────────────────────────────────────────

class TestEnvVarOverride:
    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        """F6: MUNINN_META_PATH env var overrides config.json."""
        monkeypatch.setenv("MUNINN_META_PATH", str(tmp_path))
        config = _load_sync_config()
        assert config["meta_path"] == str(tmp_path)

    def test_no_env_var_uses_default(self, monkeypatch):
        """F6: Without env var, config falls through to defaults."""
        monkeypatch.delenv("MUNINN_META_PATH", raising=False)
        config = _load_sync_config()
        # meta_path could be None (default) or from config.json
        assert "meta_path" in config


# ── F7: Atomic config write ──────────────────────────────────────

class TestAtomicConfigWrite:
    def test_save_and_load(self, tmp_path, monkeypatch):
        """F7: save_sync_config writes valid JSON atomically."""
        # Redirect home to tmp
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        # Patch Path.home() to use tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        config = {"backend": "shared_file", "meta_path": "/some/path"}
        save_sync_config(config)

        config_path = tmp_path / ".muninn" / "config.json"
        assert config_path.exists()

        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        assert loaded["backend"] == "shared_file"
        assert loaded["meta_path"] == "/some/path"


# ── F4: Mycelium delegation ─────────────────────────────────────

class TestF4Delegation:
    def test_sync_to_meta_delegates(self, tmp_path, monkeypatch):
        """F4: sync_to_meta() uses backend when self._db is not None."""
        from muninn.mycelium import Mycelium

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        muninn_dir = repo_dir / ".muninn"
        muninn_dir.mkdir()

        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

        m = Mycelium(repo_dir)
        m.observe_text("python and code are related concepts")
        m.save()
        n = m.sync_to_meta()

        assert n > 0
        # Verify meta DB was created by the backend
        assert (meta_dir / "meta_mycelium.db").exists()

    def test_pull_from_meta_delegates(self, tmp_path, monkeypatch):
        """F4: pull_from_meta() uses backend when self._db is not None."""
        from muninn.mycelium import Mycelium

        meta_dir = tmp_path / "meta"
        # Create meta with data
        meta_db = _make_db(meta_dir, "meta_mycelium.db", edges=[
            ("neural", "network", 10),
        ])
        meta_db.close()
        monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        muninn_dir = repo_dir / ".muninn"
        muninn_dir.mkdir()
        # Create empty mycelium.db so Mycelium uses SQLite mode (_db != None)
        init_db = MyceliumDB(muninn_dir / "mycelium.db")
        init_db.close()

        m = Mycelium(repo_dir)
        assert m._db is not None, "Mycelium should be in SQLite mode"
        n = m.pull_from_meta(max_pull=100)

        assert n >= 1
        assert m._db.has_connection("neural", "network")

    def test_roundtrip_two_repos(self, tmp_path, monkeypatch):
        """F4: Full roundtrip — repo A pushes, repo B pulls via Mycelium API."""
        from muninn.mycelium import Mycelium

        meta_dir = tmp_path / "shared_meta"
        monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

        # Repo A
        repo_a_dir = tmp_path / "repo_a"
        repo_a_dir.mkdir()
        (repo_a_dir / ".muninn").mkdir()
        m_a = Mycelium(repo_a_dir)
        m_a.observe_text("quantum computing is revolutionary technology")
        m_a.save()
        m_a.sync_to_meta()

        # Repo B
        repo_b_dir = tmp_path / "repo_b"
        repo_b_dir.mkdir()
        (repo_b_dir / ".muninn").mkdir()
        m_b = Mycelium(repo_b_dir)
        n = m_b.pull_from_meta(max_pull=1000)

        assert n > 0  # Pulled some connections from repo A


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
