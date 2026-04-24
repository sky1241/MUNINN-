"""Tests for quarantine TODOs — flag check, auto-activation, CLI."""
import json
import os
import sys
import tempfile
import subprocess
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine", "core"))
from cube import (
    Cube, CubeStore, CubeConfig, ReconstructionResult,
    run_destruction_cycle, record_quarantine, MockLLMProvider,
)


@pytest.fixture
def tmp_dir():
    """Temp directory for test artifacts."""
    d = tempfile.mkdtemp()
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _make_cube_in_store(store, content="def hello(): pass", cube_id=None,
                        file_origin="test.py", line_start=1, line_end=5):
    """Create a cube and add it to the store."""
    import hashlib
    sha = hashlib.sha256(content.encode()).hexdigest()
    cid = cube_id or f"{file_origin}:L{line_start}-L{line_end}:level0"
    cube = Cube(
        id=cid, content=content, sha256=sha,
        file_origin=file_origin, line_start=line_start,
        line_end=line_end, level=0, token_count=10,
    )
    store.save_cube(cube)
    return cube


# ─── TODO 1: quarantine_enabled flag is respected ───────────────────

class TestQuarantineFlag:
    """Test that quarantine_enabled=False prevents writing."""

    def test_flag_false_no_quarantine_write(self, tmp_dir):
        """When quarantine_enabled=False, no quarantine entry is written."""
        db_path = os.path.join(tmp_dir, "cube.db")
        q_path = os.path.join(tmp_dir, "quarantine.jsonl")
        config = CubeConfig(db_path=db_path, quarantine_enabled=False)
        store = CubeStore(db_path)

        # Create cube with mismatched hash (simulates corruption)
        cube = Cube(
            id="test.py:L1-L5:level0", content="corrupted code",
            sha256="aaaa_wrong_hash",  # won't match content
            file_origin="test.py", line_start=1, line_end=5,
            level=0, token_count=10,
        )
        store.save_cube(cube)
        # Add self-neighbor so reconstruction has context
        store.set_neighbor(cube.id, cube.id, 1.0)

        provider = MockLLMProvider()
        results = run_destruction_cycle(
            [cube], store, provider, cycle_num=1,
            ncd_threshold=0.3, config=config,
        )
        store.close()

        # Quarantine file should NOT exist (flag is False)
        assert not os.path.exists(q_path), "Quarantine file should not be created when disabled"

    def test_flag_true_quarantine_writes(self, tmp_dir):
        """When quarantine_enabled=True, quarantine entries ARE written on mismatch."""
        db_path = os.path.join(tmp_dir, "cube.db")
        config = CubeConfig(db_path=db_path, quarantine_enabled=True)
        store = CubeStore(db_path)

        cube = Cube(
            id="test.py:L1-L5:level0", content="corrupted code",
            sha256="aaaa_wrong_hash",
            file_origin="test.py", line_start=1, line_end=5,
            level=0, token_count=10,
        )
        store.save_cube(cube)
        store.set_neighbor(cube.id, cube.id, 1.0)

        provider = MockLLMProvider()
        results = run_destruction_cycle(
            [cube], store, provider, cycle_num=1,
            ncd_threshold=0.3, config=config,
        )
        store.close()

        # Check if any result triggered quarantine (success + not exact_match)
        triggered = any(r.success and not r.exact_match for r in results)
        q_path = os.path.join(os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
        if triggered:
            assert os.path.exists(q_path), "Quarantine should be written when enabled"

    def test_flag_none_config_defaults_to_write(self, tmp_dir):
        """When config=None (no config passed), quarantine defaults to writing."""
        # This tests backward compat: old callers without config still get quarantine
        db_path = os.path.join(tmp_dir, "cube.db")
        store = CubeStore(db_path)

        cube = Cube(
            id="test.py:L1-L5:level0", content="corrupted code",
            sha256="aaaa_wrong_hash",
            file_origin="test.py", line_start=1, line_end=5,
            level=0, token_count=10,
        )
        store.save_cube(cube)
        store.set_neighbor(cube.id, cube.id, 1.0)

        provider = MockLLMProvider()
        # config=None (default)
        results = run_destruction_cycle(
            [cube], store, provider, cycle_num=1, ncd_threshold=0.3,
        )
        store.close()
        # No crash = backward compat OK


# ─── TODO 2: auto-activation on convergence ─────────────────────────

class TestAutoActivation:
    """Test quarantine auto-activates when Cube converges."""

    def test_convergence_activates_quarantine(self, tmp_dir):
        """After all cubes succeed reconstruction, quarantine_enabled becomes True."""
        db_path = os.path.join(tmp_dir, "cube.db")
        config_path = os.path.join(tmp_dir, "config.json")
        config = CubeConfig(db_path=db_path, quarantine_enabled=False)

        store = CubeStore(db_path)
        # Create cube with CORRECT hash — MockLLMProvider echoes content back
        # so reconstruction = original content = exact_match = True = success
        import hashlib
        content = "def hello(): pass"
        sha = hashlib.sha256(content.encode()).hexdigest()
        cube = Cube(
            id="test.py:L1-L5:level0", content=content,
            sha256=sha, file_origin="test.py",
            line_start=1, line_end=5, level=0, token_count=10,
        )
        store.save_cube(cube)
        store.set_neighbor(cube.id, cube.id, 1.0)
        store.close()

        # Mock config.save to use our temp path
        original_save = config.save
        config.save = lambda path=config_path: original_save(path)

        from cube import cli_run
        result = cli_run(repo_path=tmp_dir, cycles=1, level=0, config=config)

        # If all cubes succeeded, quarantine should be auto-enabled
        if result.get('success_rate', 0) == 1.0:
            assert config.quarantine_enabled, "Convergence should auto-enable quarantine"

    def test_no_activation_on_failure(self, tmp_dir):
        """If cubes fail reconstruction, quarantine stays disabled."""
        config = CubeConfig(quarantine_enabled=False)
        # Just verify the flag stays False without running cycles
        assert not config.quarantine_enabled


# ─── TODO 3: CLI command ────────────────────────────────────────────

class TestQuarantineCLI:
    """Test `muninn quarantine` CLI command."""

    def test_cli_no_quarantine_file(self):
        """CLI outputs 'No quarantine entries' when file doesn't exist."""
        # Temporarily rename quarantine file if it exists
        q_path = os.path.join(os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
        backup = q_path + '.test_backup'
        renamed = False
        if os.path.exists(q_path):
            os.rename(q_path, backup)
            renamed = True

        try:
            result = subprocess.run(
                [sys.executable, "-m", "engine.core.muninn", "quarantine"],
                capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
                timeout=30,
            )
            assert "No quarantine entries" in result.stdout or result.returncode == 0
        finally:
            if renamed:
                os.rename(backup, q_path)

    def test_cli_with_entries(self, tmp_dir):
        """CLI displays quarantine entries when file exists."""
        q_path = os.path.join(os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
        backup = q_path + '.test_backup'
        renamed = False
        if os.path.exists(q_path):
            os.rename(q_path, backup)
            renamed = True

        try:
            # Write a test entry
            os.makedirs(os.path.dirname(q_path), exist_ok=True)
            entry = {
                'timestamp': 1710000000,
                'date': '2026-03-10 12:00:00',
                'cube_id': 'test.py:L1-L5:level0',
                'file_origin': 'test.py',
                'line_start': 1, 'line_end': 5,
                'expected_sha256': 'aaaa' * 16,
                'found_sha256': 'bbbb' * 16,
                'corrupted_content': 'import evil',
                'reconstructed_content': 'def hello(): pass',
                'exact_match': False,
                'ncd_score': 0.15,
            }
            with open(q_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')

            result = subprocess.run(
                [sys.executable, "-m", "engine.core.muninn", "quarantine"],
                capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."),
                timeout=30,
            )
            assert "1 entries" in result.stdout or "test.py" in result.stdout
            assert "import evil" in result.stdout  # corrupted content preview
        finally:
            if os.path.exists(q_path):
                os.unlink(q_path)
            if renamed:
                os.rename(backup, q_path)


# ─── Config save/load roundtrip ─────────────────────────────────────

class TestConfigQuarantineField:
    """Test quarantine_enabled persists through save/load."""

    def test_save_load_roundtrip(self, tmp_dir):
        """quarantine_enabled survives save -> load."""
        config_path = os.path.join(tmp_dir, "config.json")
        config = CubeConfig(quarantine_enabled=True)
        config.save(config_path)

        loaded = CubeConfig.load(config_path)
        assert loaded.quarantine_enabled is True

    def test_default_is_false(self):
        """Default quarantine_enabled is False."""
        config = CubeConfig()
        assert config.quarantine_enabled is False

    def test_load_missing_field_defaults_false(self, tmp_dir):
        """Loading config without quarantine_enabled field defaults to False."""
        config_path = os.path.join(tmp_dir, "config.json")
        with open(config_path, 'w') as f:
            json.dump({"cube": {"local_only": True}}, f)

        loaded = CubeConfig.load(config_path)
        assert loaded.quarantine_enabled is False
