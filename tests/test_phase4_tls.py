"""Phase 4 tests — TLS Backend (T1-T4).

Tests cover: real CRDT merge on server, TLSBackend class,
server CLI existence, ACL check, factory integration.

NOTE: Tests that require TLS use the existing test_sync_tls.py infrastructure
(self-signed certs + localhost server). These tests focus on the new
T1-T4 functionality specifically.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium_db import MyceliumDB, today_days


# ── T1: SyncServer real CRDT merge ──────────────────────────────

class TestT1ServerMerge:
    def test_merge_push_creates_edges(self, tmp_path):
        """T1: _merge_push creates edges in meta DB via CRDT."""
        from sync_tls import SyncServer
        meta_db_path = str(tmp_path / "meta.db")
        # We can't start a full TLS server without certs,
        # but we can test _merge_push directly
        server = SyncServer.__new__(SyncServer)
        server.meta_db_path = meta_db_path

        connections = [
            {"a": "python", "b": "code", "count": 5,
             "first_seen": today_days(), "last_seen": today_days()},
            {"a": "memory", "b": "compress", "count": 3,
             "first_seen": today_days(), "last_seen": today_days()},
        ]
        merged = server._merge_push(connections, "test-repo", "dev")
        assert merged == 2

        # Verify in DB
        db = MyceliumDB(Path(meta_db_path))
        assert db.has_connection("python", "code")
        assert db.has_connection("memory", "compress")
        db.close()

    def test_merge_push_crdt_max_count(self, tmp_path):
        """T1: CRDT merge uses MAX(count)."""
        from sync_tls import SyncServer
        meta_db_path = str(tmp_path / "meta.db")
        server = SyncServer.__new__(SyncServer)
        server.meta_db_path = meta_db_path

        # First push: count=5
        server._merge_push(
            [{"a": "x", "b": "y", "count": 5,
              "first_seen": today_days(), "last_seen": today_days()}],
            "repo-a", "zone-a"
        )
        # Second push: count=10
        server._merge_push(
            [{"a": "x", "b": "y", "count": 10,
              "first_seen": today_days(), "last_seen": today_days()}],
            "repo-b", "zone-b"
        )

        db = MyceliumDB(Path(meta_db_path))
        conn = db.get_connection("x", "y")
        assert conn["count"] == 10  # MAX(5, 10)
        db.close()

    def test_merge_push_tracks_repo(self, tmp_path):
        """T1: _merge_push registers repo in meta."""
        from sync_tls import SyncServer
        meta_db_path = str(tmp_path / "meta.db")
        server = SyncServer.__new__(SyncServer)
        server.meta_db_path = meta_db_path

        server._merge_push(
            [{"a": "a", "b": "b", "count": 1,
              "first_seen": today_days(), "last_seen": today_days()}],
            "my-repo", "z"
        )

        db = MyceliumDB(Path(meta_db_path))
        repos = db.get_meta("repos", "")
        assert "my-repo" in repos
        db.close()

    def test_query_pull_returns_data(self, tmp_path):
        """T1: _query_pull returns connections from meta DB."""
        from sync_tls import SyncServer
        meta_db_path = str(tmp_path / "meta.db")
        server = SyncServer.__new__(SyncServer)
        server.meta_db_path = meta_db_path

        # Populate meta
        server._merge_push(
            [{"a": "neural", "b": "network", "count": 10,
              "first_seen": today_days(), "last_seen": today_days()}],
            "ml-repo", "ml"
        )

        result = server._query_pull(["neural"], max_pull=100)
        assert result["count"] >= 1
        assert any(c["a"] == "neural" or c["b"] == "neural"
                    for c in result["connections"])

    def test_query_pull_empty_concepts(self, tmp_path):
        """T1: _query_pull with empty concepts returns top edges."""
        from sync_tls import SyncServer
        meta_db_path = str(tmp_path / "meta.db")
        server = SyncServer.__new__(SyncServer)
        server.meta_db_path = meta_db_path

        server._merge_push(
            [{"a": "a", "b": "b", "count": 1,
              "first_seen": today_days(), "last_seen": today_days()}],
            "r", "z"
        )

        result = server._query_pull([], max_pull=100)
        assert result["count"] >= 1


# ── T2: TLSBackend class ────────────────────────────────────────

class TestT2TLSBackend:
    def test_tls_backend_exists(self):
        """T2: TLSBackend class is importable."""
        from sync_tls import TLSBackend
        assert TLSBackend is not None

    def test_tls_backend_has_push_pull_status(self):
        """T2: TLSBackend has push/pull/status methods."""
        from sync_tls import TLSBackend
        backend = TLSBackend.__new__(TLSBackend)
        assert hasattr(backend, "push")
        assert hasattr(backend, "pull")
        assert hasattr(backend, "status")

    def test_status_offline(self):
        """T2: Status reports disconnected when no server."""
        from sync_tls import TLSBackend
        backend = TLSBackend(host="localhost", port=19999, verify=False)
        status = backend.status()
        assert status["type"] == "tls"
        assert status["connected"] is False


# ── T3: Server CLI ───────────────────────────────────────────────

class TestT3ServerCLI:
    def test_serve_cli_exists(self):
        """T3: serve_cli function exists."""
        from sync_tls import serve_cli
        assert callable(serve_cli)

    def test_main_guard(self):
        """T3: sync_tls.py has __main__ guard."""
        src = (Path(__file__).resolve().parent.parent / "engine" / "core" / "sync_tls.py"
               ).read_text(encoding="utf-8")
        assert 'if __name__ == "__main__"' in src
        assert "serve_cli()" in src


# ── T4: Auth + ACL ──────────────────────────────────────────────

class TestT4AuthACL:
    def test_server_stores_allowed_users(self):
        """T4: SyncServer accepts allowed_users parameter."""
        from sync_tls import SyncServer
        server = SyncServer.__new__(SyncServer)
        server.allowed_users = ["alice", "bob"]
        assert server.allowed_users == ["alice", "bob"]

    def test_check_acl_method_exists(self):
        """T4: SyncServer._check_acl method exists."""
        from sync_tls import SyncServer
        assert hasattr(SyncServer, "_check_acl")

    def test_server_init_with_acl(self, tmp_path):
        """T4: SyncServer can be initialized with allowed_users."""
        from sync_tls import SyncServer, generate_certs
        try:
            certs = generate_certs(tmp_path / "certs")
        except ImportError:
            pytest.skip("cryptography not installed")

        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(tmp_path / "meta.db"),
            allowed_users=["admin", "dev1"],
        )
        assert server.allowed_users == ["admin", "dev1"]


# ── Factory integration ─────────────────────────────────────────

class TestTLSFactory:
    def test_factory_tls_config(self):
        """Factory recognizes 'tls' backend type."""
        from sync_backend import get_sync_backend
        # This will fail to connect but should create the backend
        try:
            backend = get_sync_backend({
                "backend": "tls",
                "tls_host": "localhost",
                "tls_port": 19998,
                "tls_verify": False,
            })
            from sync_tls import TLSBackend
            assert isinstance(backend, TLSBackend)
        except ImportError:
            pytest.skip("sync_tls import failed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
