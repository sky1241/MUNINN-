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


# CHUNK D4 (2026-05-19 remediation) — shim must re-export the C10 + D3
# helpers (`_extract_gap_lines`, `_extract_unknown_identifiers`). Pre-D4,
# `from cube_providers import *` skipped them (PEP 8 underscore rule)
# and the explicit re-export block didn't list them.

def test_d4_shim_exposes_extract_gap_lines():
    """D4 regression : _extract_gap_lines reachable via the shim."""
    r = _subprocess_import(
        "from muninn.cube_providers import _extract_gap_lines; "
        "result = _extract_gap_lines({0: 'x'}, 3); "
        "print('result:', result)"
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    assert "[1, 2]" in r.stdout  # gaps = lines NOT in anchor_map


def test_d4_shim_exposes_extract_unknown_identifiers():
    """D4 regression : _extract_unknown_identifiers reachable via the shim."""
    r = _subprocess_import(
        "from muninn.cube_providers import _extract_unknown_identifiers; "
        "result = _extract_unknown_identifiers('def foo(): magic_var', {'identifiers': ['foo']}); "
        "print('result:', result)"
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-500:]}"
    # D3 fix : 'def' filtered (keyword), 'magic_var' kept
    assert "magic_var" in r.stdout
    assert "'def'" not in r.stdout


# CHUNK E2 (REMEDIATION-2) — fix R2 bare engine/core import circular.
# Audit a flag : `python -c "import sys; sys.path.insert(0,'engine/core');
# from cube_providers import OllamaProvider"` crashait avec ImportError
# parce que le D2 fix (pre-import dans muninn/cube_providers.py) ne
# couvrait QUE le path muninn.cube_providers. Tests/scripts/hooks qui
# font bare import depuis engine/core crashaient.

def test_e2_bare_engine_core_cube_providers_first_import():
    """E2 regression : bare `from cube_providers import X` après mettre
    engine/core sur sys.path (sans `import cube` warmup) doit succeed."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'engine/core'); "
         "from cube_providers import OllamaProvider; print('OK')"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-700:]}"
    assert "OK" in r.stdout


def test_e2_bare_engine_core_cube_providers_dataclasses():
    """E2 regression : ReconstructionResult + WaveResult resolve cold via
    bare engine/core import."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'engine/core'); "
         "from cube_providers import ReconstructionResult, WaveResult; print('OK')"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-700:]}"


def test_e2_bare_engine_core_cube_analysis_first_import():
    """E2 regression : bare `from cube_analysis import X` doit succeed cold."""
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'engine/core'); "
         "from cube_analysis import fuse_risks; print('OK')"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, f"stderr: {r.stderr[-700:]}"
