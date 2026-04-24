#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B32-B39.

B32: Scheduling async
B33: Config securite
B34: Multi-LLM hooks (covered by config)
B39: CLI commands (scan, run, status, god)
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    CubeScheduler, CubeConfig,
    CubeStore, MockLLMProvider, OllamaProvider,
    cli_scan, cli_run, cli_status, cli_god,
    sha256_hash, Cube,
)


@pytest.fixture
def mini_repo(tmp_path):
    """Create a minimal repo for testing."""
    (tmp_path / "main.py").write_text(
        "from utils import helper\n\ndef run():\n    helper(42)\n\nrun()\n"
    )
    (tmp_path / "utils.py").write_text(
        "def helper(x):\n    return x * 2\n"
    )
    return tmp_path


@pytest.fixture
def config(tmp_path):
    """Create test config."""
    db_path = str(tmp_path / "cube.db")
    return CubeConfig(
        local_only=False,
        db_path=db_path,
        allowed_providers=['mock', 'ollama'],
    )


# ═══════════════════════════════════════════════════════════════════════
# B32: Scheduling
# ═══════════════════════════════════════════════════════════════════════

class TestB32Scheduling:
    def test_scheduler_exists(self, tmp_path):
        """CubeScheduler initializes."""
        sched = CubeScheduler(str(tmp_path))
        assert sched.repo_path == str(tmp_path)

    def test_not_quiet_initially(self, tmp_path):
        """Scheduler is not quiet right after init."""
        sched = CubeScheduler(str(tmp_path), quiet_seconds=300)
        assert sched.is_quiet() is False

    def test_quiet_after_wait(self, tmp_path):
        """Scheduler reports quiet after quiet_seconds."""
        sched = CubeScheduler(str(tmp_path), quiet_seconds=0)
        import time
        sched._last_activity = time.time() - 1
        assert sched.is_quiet() is True

    def test_should_run_respects_quiet(self, tmp_path):
        """should_run returns False when not quiet."""
        sched = CubeScheduler(str(tmp_path), quiet_seconds=9999)
        # With very long quiet_seconds, should not run
        assert sched.should_run() is False


# ═══════════════════════════════════════════════════════════════════════
# B33: Config securite
# ═══════════════════════════════════════════════════════════════════════

class TestB33Config:
    def test_default_local_only(self):
        """Default config is local_only=True."""
        cfg = CubeConfig()
        assert cfg.local_only is True

    def test_save_load(self, tmp_path):
        """Config saves and loads from JSON."""
        config_path = str(tmp_path / "config.json")
        cfg = CubeConfig(local_only=False, max_cycles=50, ncd_threshold=0.2)
        cfg.save(config_path)

        loaded = CubeConfig.load(config_path)
        assert loaded.local_only is False
        assert loaded.max_cycles == 50
        assert loaded.ncd_threshold == 0.2

    def test_load_nonexistent(self):
        """Loading nonexistent config returns defaults."""
        cfg = CubeConfig.load("/nonexistent/config.json")
        assert cfg.local_only is True

    def test_local_only_blocks_api(self):
        """local_only=True blocks non-local providers."""
        cfg = CubeConfig(local_only=True, allowed_providers=['ollama', 'mock'])
        from muninn.cube import ClaudeProvider
        provider = ClaudeProvider()
        assert cfg.validate_provider(provider) is False

    def test_local_only_allows_ollama(self):
        """local_only=True allows Ollama."""
        cfg = CubeConfig(local_only=True)
        provider = OllamaProvider()
        assert cfg.validate_provider(provider) is True

    def test_local_only_allows_mock(self):
        """local_only=True allows Mock."""
        cfg = CubeConfig(local_only=True)
        provider = MockLLMProvider()
        assert cfg.validate_provider(provider) is True

    def test_get_provider_returns_mock_fallback(self):
        """get_provider falls back to mock when no API keys."""
        cfg = CubeConfig(local_only=False, allowed_providers=['mock'])
        provider = cfg.get_provider()
        assert provider.name == 'mock'

    def test_allowed_providers(self):
        """Custom allowed_providers list."""
        cfg = CubeConfig(allowed_providers=['ollama', 'claude'])
        assert 'ollama' in cfg.allowed_providers
        assert 'claude' in cfg.allowed_providers


# ═══════════════════════════════════════════════════════════════════════
# B39: CLI commands
# ═══════════════════════════════════════════════════════════════════════

class TestB39CLI:
    def test_cli_scan(self, mini_repo, config):
        """cube scan produces correct summary."""
        result = cli_scan(str(mini_repo), config)
        assert result['files'] == 2
        assert result['cubes'] >= 2
        assert result['dependencies'] >= 1

    def test_cli_scan_creates_db(self, mini_repo, config):
        """cube scan creates SQLite database."""
        cli_scan(str(mini_repo), config)
        assert os.path.exists(config.db_path)

    def test_cli_status_no_db(self, tmp_path):
        """cube status with no DB returns error."""
        cfg = CubeConfig(db_path=str(tmp_path / "nonexistent.db"))
        result = cli_status(cfg)
        assert 'error' in result

    def test_cli_status_after_scan(self, mini_repo, config):
        """cube status after scan returns stats."""
        cli_scan(str(mini_repo), config)
        result = cli_status(config)
        assert result['total_cubes'] >= 2
        assert 'avg_temperature' in result
        assert 'levels' in result

    def test_cli_run_with_mock(self, mini_repo, config):
        """cube run with mock provider completes."""
        config.allowed_providers = ['mock']
        cli_scan(str(mini_repo), config)
        result = cli_run(str(mini_repo), cycles=1, config=config)
        assert result['cycles'] == 1
        assert result['cubes_active'] >= 0
        assert 'success_rate' in result

    def test_cli_god_no_db(self, tmp_path):
        """cube god with no DB returns error."""
        cfg = CubeConfig(db_path=str(tmp_path / "nonexistent.db"))
        result = cli_god(cfg)
        assert 'error' in result

    def test_cli_god_after_scan(self, mini_repo, config):
        """cube god after scan returns God's Number."""
        cli_scan(str(mini_repo), config)
        result = cli_god(config)
        assert 'gods_number' in result
        assert 'bounds' in result
        assert result['gods_number'] >= 0


# ═══════════════════════════════════════════════════════════════════════
# Integration: full pipeline scan → run → status → god
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB32B39:
    def test_full_pipeline(self, mini_repo, config):
        """scan → run → status → god full pipeline."""
        config.allowed_providers = ['mock']

        # Scan
        scan_result = cli_scan(str(mini_repo), config)
        assert scan_result['cubes'] >= 2

        # Run 2 cycles
        run_result = cli_run(str(mini_repo), cycles=2, config=config)
        assert run_result['total_tests'] > 0

        # Status
        status = cli_status(config)
        assert status['total_cubes'] >= 2

        # God's Number
        god = cli_god(config)
        assert god['gods_number'] >= 0
        assert 'lrc_lower' in god['bounds']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
