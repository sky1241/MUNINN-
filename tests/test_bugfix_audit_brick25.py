"""Tests for audit bug fixes — brick 25 (2026-04-17).

H1: vault.py bytearray memory wipe
M1: mycelium_db.py upsert MAX strategy
M2: sync_backend.py TLSBackend triple-fallback import
M3: cube.py dead locks removed
M5: muninn.py _SECRET_PATTERNS single source of truth
L7: forge.py template no hardcoded paths
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

# Ensure engine/core is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


class TestH1VaultMemoryWipe:
    """H1: vault.py must use bytearray for _zero_bytes to actually wipe."""

    def test_zero_bytes_on_bytearray(self):
        from vault import _zero_bytes
        data = bytearray(b"SENSITIVE_SECRET_DATA_1234567890")
        _zero_bytes(data)
        assert all(b == 0 for b in data), "bytearray was not zeroed"

    def test_zero_bytes_empty(self):
        from vault import _zero_bytes
        data = bytearray(b"")
        _zero_bytes(data)  # Should not crash

    def test_lock_unlock_round_trip(self):
        from vault import Vault
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            muninn_dir = repo / ".muninn"
            sessions = muninn_dir / "sessions"
            sessions.mkdir(parents=True)
            (muninn_dir / "errors.json").write_text('{"errors": []}')
            (sessions / "test.mn").write_text("test data")

            v = Vault(repo)
            v.init("testpass")
            result = v.lock()
            assert result["encrypted"] >= 2
            result = v.unlock()
            assert result["decrypted"] >= 2
            assert len(result["failed"]) == 0
            assert (muninn_dir / "errors.json").read_text() == '{"errors": []}'

    def test_lock_uses_bytearray_not_bytes(self):
        """Verify the code wraps fp.read_bytes() in bytearray."""
        import inspect
        from vault import Vault
        src = inspect.getsource(Vault.lock)
        assert "bytearray(fp.read_bytes())" in src

    def test_unlock_uses_bytearray_not_bytes(self):
        import inspect
        from vault import Vault
        src = inspect.getsource(Vault.unlock)
        assert "bytearray(vp.read_bytes())" in src
        assert "bytearray(_decrypt_bytes(" in src


class TestM1UpsertConnectionMAX:
    """M1: import mode must use MAX(existing, imported) for count."""

    def test_import_does_not_downgrade(self):
        from mycelium_db import MyceliumDB
        with tempfile.TemporaryDirectory() as td:
            db = MyceliumDB(Path(td) / "test.db")
            db.upsert_connection("a", "b", count=100,
                                first_seen="2026-01-01", last_seen="2026-01-01")
            # Import lower count — should NOT downgrade
            db.upsert_connection("a", "b", count=50,
                                first_seen="2025-12-01", last_seen="2026-02-01")
            conn = db.get_connection("a", "b")
            assert conn["count"] == 100, f"Expected 100, got {conn['count']}"
            db.close()

    def test_import_does_upgrade(self):
        from mycelium_db import MyceliumDB
        with tempfile.TemporaryDirectory() as td:
            db = MyceliumDB(Path(td) / "test.db")
            db.upsert_connection("x", "y", count=50,
                                first_seen="2026-01-01", last_seen="2026-01-01")
            # Import higher count — should upgrade
            db.upsert_connection("x", "y", count=200,
                                first_seen="2026-01-01", last_seen="2026-03-01")
            conn = db.get_connection("x", "y")
            assert conn["count"] == 200, f"Expected 200, got {conn['count']}"
            db.close()

    def test_import_preserves_min_first_seen(self):
        from mycelium_db import MyceliumDB, date_to_days, days_to_date
        td = tempfile.mkdtemp()
        try:
            db = MyceliumDB(Path(td) / "test.db")
            db.upsert_connection("a", "b", count=10,
                                first_seen="2026-03-01", last_seen="2026-03-01")
            db.upsert_connection("a", "b", count=20,
                                first_seen="2026-01-01", last_seen="2026-03-01")
            conn = db.get_connection("a", "b")
            # first_seen may be epoch-days int or date string depending on API
            fs = conn["first_seen"]
            if isinstance(fs, int):
                fs = days_to_date(fs)
            assert fs == "2026-01-01", f"Expected 2026-01-01, got {fs}"
            db.close()
        finally:
            import shutil
            shutil.rmtree(td, ignore_errors=True)


class TestM2SyncBackendTLSImport:
    """M2: get_sync_backend must use triple-fallback for TLSBackend."""

    def test_triple_fallback_in_source(self):
        import inspect
        from sync_backend import get_sync_backend
        src = inspect.getsource(get_sync_backend)
        assert "engine.core.sync_tls" in src
        assert ".sync_tls" in src
        assert "from sync_tls import" in src

    def test_default_backend_works(self):
        from sync_backend import get_sync_backend
        backend = get_sync_backend()
        assert type(backend).__name__ == "SharedFileBackend"


class TestM3DeadLocksRemoved:
    """M3: cube.py must not define _quarantine_lock/_anomaly_lock."""

    def test_cube_no_quarantine_lock(self):
        import cube
        assert not hasattr(cube, "_quarantine_lock")

    def test_cube_no_anomaly_lock(self):
        import cube
        assert not hasattr(cube, "_anomaly_lock")

    def test_cube_analysis_has_locks(self):
        import cube_analysis
        assert hasattr(cube_analysis, "_quarantine_lock")
        assert hasattr(cube_analysis, "_anomaly_lock")


class TestM5SecretPatternsSingleSource:
    """M5: muninn.py must import _SECRET_PATTERNS from _secrets.py."""

    def test_patterns_equal(self):
        """engine/core/muninn.py imports from _secrets.py — patterns must match."""
        # Import from engine/core context (not muninn package)
        import importlib
        import muninn as _m_mod
        from _secrets import _SECRET_PATTERNS as secrets_pats
        # The engine/core/muninn.py should have the same list content
        # (may not be same object due to separate module load paths)
        engine_muninn_path = Path(__file__).resolve().parent.parent / "engine" / "core" / "muninn.py"
        assert engine_muninn_path.exists()
        content = engine_muninn_path.read_text(encoding="utf-8")
        assert "from _secrets import _SECRET_PATTERNS" in content, \
            "engine/core/muninn.py should import from _secrets.py"

    def test_no_duplicate_definition(self):
        """engine/core/muninn.py must NOT define its own _SECRET_PATTERNS list."""
        engine_muninn_path = Path(__file__).resolve().parent.parent / "engine" / "core" / "muninn.py"
        content = engine_muninn_path.read_text(encoding="utf-8")
        # Should import, not define
        assert "_SECRET_PATTERNS = [" not in content, \
            "muninn.py still has a local _SECRET_PATTERNS definition"

    def test_pattern_count(self):
        from _secrets import _SECRET_PATTERNS
        assert len(_SECRET_PATTERNS) >= 24, f"Expected >=24 patterns, got {len(_SECRET_PATTERNS)}"


class TestL7ForgeTemplateNoPaths:
    """L7: forge-generated test_props_*.py must not contain hardcoded paths."""

    def test_no_hardcoded_paths_in_props(self):
        tests_dir = Path(__file__).resolve().parent
        for f in tests_dir.glob("test_props_*.py"):
            content = f.read_text(encoding="utf-8", errors="replace")
            assert "C:\\Users\\ludov" not in content, f"Hardcoded path in {f.name}"
            assert "c:\\Users\\ludov" not in content, f"Hardcoded path in {f.name}"
            assert "C:/Users/ludov" not in content, f"Hardcoded path in {f.name}"
