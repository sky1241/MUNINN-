"""CHUNK E7 — _hook_logger.swallow() must have at least 1 production caller.

Run-4 audit found that D9 helpers (swallow + log_engine_event) were
shipped but had ZERO production callers. They were dead code.

E7 wires `swallow()` into the existing _query_mycelium try/except in
cube_providers.py (B5 site). This kills the dead-code finding and
also exercises the context-manager pattern in a real call path.

Source: docs/BATTLE_PLAN_AUDIT3_2026-05-08.md §E7
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def test_swallow_is_imported_in_production():
    """Static check: at least one production module (engine/core/, not
    tests/) must `from _hook_logger import swallow`."""
    matches = []
    for py in (REPO / "engine" / "core").rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from _hook_logger import .*swallow|import _hook_logger\b.*swallow", text):
            matches.append(py.name)
    assert matches, (
        "No production caller imports _hook_logger.swallow() — D9 helper "
        "is still dead code. Migrate at least one try/except site (e.g. "
        "cube_providers._query_mycelium per CHUNK E7)."
    )


def test_cube_providers_uses_swallow():
    """cube_providers._query_mycelium must use swallow() — E7 migration."""
    src = (REPO / "engine" / "core" / "cube_providers.py").read_text(encoding="utf-8")
    # Find the function and its body
    m = re.search(
        r"def _query_mycelium\(.*?\n(?P<body>(?:    .*\n|\n)+?)(?=\ndef |\nclass |\Z)",
        src,
    )
    assert m is not None, "_query_mycelium not found"
    body = m.group("body")
    assert "swallow(" in body, (
        "_query_mycelium must call swallow() (CHUNK E7 migration). "
        f"Body excerpt: {body[:300]!r}"
    )


def test_log_engine_event_or_swallow_used_in_production():
    """At least one of log_engine_event() / swallow() must have a real
    production import. D9 ships both as a pair."""
    found_swallow = 0
    found_engine_event = 0
    for py in (REPO / "engine" / "core").rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        # Production callers (not the _hook_logger module itself)
        if py.name == "_hook_logger.py":
            continue
        if "swallow(" in text:
            found_swallow += 1
        if "log_engine_event(" in text:
            found_engine_event += 1
    assert found_swallow + found_engine_event > 0, (
        "Neither swallow() nor log_engine_event() has any production "
        "caller — D9 helpers are dead code despite the E7 migration."
    )


def test_brick19_dead_code_audit_does_not_flag_d9_helpers():
    """The brick19 audit must not flag swallow / log_engine_event as
    dead anymore (they're now imported by production code)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_brick19_dead_code_audit.py::test_dead_code_set_matches_documented",
         "-q", "--tb=line"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    output = result.stdout + result.stderr
    # Test passes if brick19 itself passes
    assert result.returncode == 0, (
        f"test_brick19 fails — D9 helpers may still appear as dead:\n"
        f"{output[-1000:]}"
    )
