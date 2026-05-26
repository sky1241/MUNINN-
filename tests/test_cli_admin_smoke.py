"""Smoke tests for admin CLI commands that previously had no test coverage.

R12 audit finding (sky-master): 2 admin CLI commands lacked dedicated tests:
  - `muninn purge-secrets` (sensitive: scrubs secret concepts from meta DB)
  - `muninn upgrade-hooks` (regenerates .claude/hooks/*.py templates)

These tests are SMOKE only — verify the command parses, dispatches, and exits 0
on --help. Full behavior is exercised via test_r3_003 (purge_secrets path) and
test_chunk4/5 (hook regeneration).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MUNINN_CLI = REPO / "engine" / "core" / "muninn.py"


def _run_muninn(args, timeout=15):
    """Invoke `python <muninn.py> <args>` from repo root."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "engine" / "core") + ":" + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, str(MUNINN_CLI), *args],
        capture_output=True, text=True, timeout=timeout, cwd=str(REPO), env=env,
    )


def test_purge_secrets_help():
    """`muninn purge-secrets --help` parses and exits 0."""
    result = _run_muninn(["purge-secrets", "--help"])
    assert result.returncode == 0, (
        f"purge-secrets --help failed (exit={result.returncode}). "
        f"stderr: {result.stderr[-300:]}"
    )


def test_upgrade_hooks_help():
    """`muninn upgrade-hooks --help` parses and exits 0."""
    result = _run_muninn(["upgrade-hooks", "--help"])
    assert result.returncode == 0, (
        f"upgrade-hooks --help failed (exit={result.returncode}). "
        f"stderr: {result.stderr[-300:]}"
    )


def test_muninn_cli_exists():
    """Sanity: engine/core/muninn.py exists and is executable as a script."""
    assert MUNINN_CLI.exists(), f"missing {MUNINN_CLI}"
    result = _run_muninn(["--help"])
    assert result.returncode == 0, f"muninn --help fails: {result.stderr[-200:]}"
