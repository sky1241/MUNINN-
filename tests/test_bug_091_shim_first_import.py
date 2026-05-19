"""CHUNK D2 (2026-05-19 remediation) — BUG-091 shim first-import tests.

Verifies that each of muninn.{cube, cube_providers, cube_analysis} can be
imported on a FRESH Python (no pre-warmed sibling modules in sys.modules).
Pre-D2 : `from muninn.cube_providers import OllamaProvider` raised
ImportError on cold start because of the engine/core circular chain
cube_providers → cube → cube_analysis → cube_providers.

Each test spawns its own subprocess so the warmup-from-prior-test
contamination is impossible.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _subprocess_import(snippet: str) -> subprocess.CompletedProcess:
    """Run `python -c snippet` in a fresh interpreter inside REPO_ROOT."""
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
    )


def test_muninn_cube_first_import():
    """Cold start : `from muninn.cube import Cube` must succeed."""
    r = _subprocess_import("from muninn.cube import Cube; print('OK')")
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    assert "OK" in r.stdout


def test_muninn_cube_providers_first_import():
    """D2 regression : cold-start import of muninn.cube_providers must NOT
    raise the circular ImportError."""
    r = _subprocess_import(
        "from muninn.cube_providers import OllamaProvider; print('OK')"
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    assert "OK" in r.stdout


def test_muninn_cube_analysis_first_import():
    """Cold start : `from muninn.cube_analysis import fuse_risks` must succeed."""
    r = _subprocess_import(
        "from muninn.cube_analysis import fuse_risks; print('OK')"
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    assert "OK" in r.stdout


def test_muninn_cube_providers_first_import_dataclasses():
    """ReconstructionResult + WaveResult must also resolve cold."""
    r = _subprocess_import(
        "from muninn.cube_providers import ReconstructionResult, WaveResult; "
        "print('OK')"
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    assert "OK" in r.stdout
