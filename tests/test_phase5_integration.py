"""Phase 5 tests — Integration (I1-I5).

Tests cover: CLI sync commands, migration tool, hook verification,
doctor check, export/import JSON.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium_db import MyceliumDB, today_days
from sync_backend import (
    SharedFileBackend, SyncPayload, get_sync_backend, _load_sync_config,
    save_sync_config, verify_hooks, sync_doctor,
    export_meta_json, import_meta_json, migrate_backend,
)


def _make_db(tmp_path, name="test.db", edges=None):
    db = MyceliumDB(tmp_path / name)
    if edges:
        for a, b, count in edges:
            db.upsert_connection(a, b, count=count)
    db.commit()
    return db


# ── I1: CLI sync commands ────────────────────────────────────────

class TestI1CLI:
    def test_sync_status_cli(self, tmp_path, monkeypatch):
        """I1: sync status returns backend info."""
        monkeypatch.setenv("MUNINN_META_PATH", str(tmp_path))
        backend = get_sync_backend()
        status = backend.status()
        assert status["type"] == "shared_file"

    def test_sync_backend_switch(self, tmp_path, monkeypatch):
        """I1: backend= switch updates config."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config_dir = tmp_path / ".muninn"
        config_dir.mkdir(parents=True, exist_ok=True)
        config = {"backend": "shared_file"}
        config["backend"] = "git"
        save_sync_config(config)
        loaded = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert loaded["backend"] == "git"

    def test_sync_status_shared_file(self, tmp_path, monkeypatch):
        """I1: Status works for shared_file backend."""
        monkeypatch.setenv("MUNINN_META_PATH", str(tmp_path))
        backend = get_sync_backend()
        st = backend.status()
        assert "type" in st
        assert "meta_dir" in st

    def test_config_load_default(self, monkeypatch):
        """I1: Default config returns shared_file."""
        monkeypatch.delenv("MUNINN_META_PATH", raising=False)
        config = _load_sync_config()
        assert config["backend"] == "shared_file"

    def test_config_env_override(self, tmp_path, monkeypatch):
        """I1: MUNINN_META_PATH env var overrides config."""
        monkeypatch.setenv("MUNINN_META_PATH", str(tmp_path / "custom"))
        config = _load_sync_config()
        assert config["meta_path"] == str(tmp_path / "custom")


# ── I2: Migration tool ──────────────────────────────────────────

class TestI2Migration:
    def test_migrate_shared_to_git(self, tmp_path, monkeypatch):
        """I2: Migrate from shared_file to git."""
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()
        monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

        # Create source data
        backend = SharedFileBackend(meta_dir)
        local = _make_db(tmp_path, "local.db", edges=[
            ("python", "code", 10),
            ("memory", "compress", 5),
        ])
        backend.push(SyncPayload(repo_name="test", zone="dev"), local)
        local.close()

        # Migrate
        config = {"backend": "shared_file", "meta_path": str(meta_dir),
                  "git_path": str(tmp_path / "sync.git")}
        result = migrate_backend("shared_file", "git", config)
        assert result["edges"] >= 2

    def test_migrate_empty_source(self, tmp_path, monkeypatch):
        """I2: Migrate from empty source returns 0."""
        monkeypatch.setenv("MUNINN_META_PATH", str(tmp_path / "empty"))
        config = {"backend": "shared_file", "meta_path": str(tmp_path / "empty"),
                  "git_path": str(tmp_path / "sync.git")}
        result = migrate_backend("shared_file", "git", config)
        assert result["edges"] == 0


# ── I3: Hook verify ─────────────────────────────────────────────

class TestI3HookVerify:
    def test_verify_hooks_returns_dict(self):
        """I3: verify_hooks returns status dict."""
        result = verify_hooks()
        assert isinstance(result, dict)
        assert "factory_load" in result
        assert "payload_roundtrip" in result

    def test_factory_load_ok(self):
        """I3: Factory loads without error."""
        result = verify_hooks()
        assert result["factory_load"] is True

    def test_payload_roundtrip(self):
        """I3: SyncPayload serialization roundtrip works."""
        result = verify_hooks()
        assert result["payload_roundtrip"] is True

    def test_config_load_ok(self):
        """I3: Config loads without error."""
        result = verify_hooks()
        assert result["config_load"] is True

    def test_mycelium_import(self):
        """I3: Mycelium module is importable."""
        result = verify_hooks()
        assert result["mycelium_import"] is True


# ── I4: Doctor check ────────────────────────────────────────────

class TestI4Doctor:
    def test_sync_doctor_returns_dict(self):
        """I4: sync_doctor returns health dict."""
        result = sync_doctor()
        assert isinstance(result, dict)
        assert "backend" in result
        assert "disk_space" in result

    def test_backend_check(self):
        """I4: Backend check is OK."""
        result = sync_doctor()
        assert result["backend"]["ok"] is True

    def test_disk_space_check(self):
        """I4: Disk space check passes."""
        result = sync_doctor()
        assert result["disk_space"]["ok"] is True

    def test_config_check(self):
        """I4: Config check returns OK."""
        result = sync_doctor()
        assert "config" in result
        assert result["config"]["ok"] is True


# ── I5: Export/Import JSON ───────────────────────────────────────

class TestI5ExportImport:
    def test_export_creates_file(self, tmp_path, monkeypatch):
        """I5: Export creates a JSON file."""
        # Use empty meta
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        out = tmp_path / "export.json"
        result = export_meta_json(out)
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "edges" in data
        assert "fusions" in data

    def test_export_with_data(self, tmp_path, monkeypatch):
        """I5: Export includes real data."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir()

        # Create meta DB with data
        db = MyceliumDB(muninn_dir / "meta_mycelium.db")
        db.upsert_connection("python", "code", count=10)
        db.upsert_connection("memory", "tree", count=5)
        db.commit()
        db.close()

        out = tmp_path / "export.json"
        result = export_meta_json(out)
        assert result["edges"] == 2
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["edges"]) == 2

    def test_import_from_json(self, tmp_path, monkeypatch):
        """I5: Import restores data from JSON."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir()

        # Create export file
        export = {
            "version": 1,
            "edges": [
                {"a": "neural", "b": "network", "count": 15,
                 "first_seen": today_days(), "last_seen": today_days()},
            ],
            "fusions": [
                {"a": "neural", "b": "network", "form": "nn",
                 "strength": 0.9, "fused_at": today_days()},
            ],
            "meta": {"type": "meta", "repos": "test-repo"},
        }
        json_file = tmp_path / "import.json"
        json_file.write_text(json.dumps(export), encoding="utf-8")

        result = import_meta_json(json_file)
        assert result["edges"] == 1
        assert result["fusions"] == 1

        # Verify in DB
        db = MyceliumDB(muninn_dir / "meta_mycelium.db")
        assert db.has_connection("neural", "network")
        db.close()

    def test_roundtrip_export_import(self, tmp_path, monkeypatch):
        """I5: Export then import preserves data."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir()

        # Create source data
        db = MyceliumDB(muninn_dir / "meta_mycelium.db")
        db.upsert_connection("graph", "theory", count=20)
        db.upsert_connection("deep", "learning", count=8)
        db.commit()
        db.close()

        # Export
        out = tmp_path / "roundtrip.json"
        export_meta_json(out)

        # Delete DB
        (muninn_dir / "meta_mycelium.db").unlink()

        # Import
        result = import_meta_json(out)
        assert result["edges"] == 2

        # Verify
        db = MyceliumDB(muninn_dir / "meta_mycelium.db")
        assert db.has_connection("graph", "theory")
        assert db.has_connection("deep", "learning")
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
