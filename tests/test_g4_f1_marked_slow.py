"""G.4 — F.1 uninstall tests must carry @pytest.mark.slow.

Problem: tests/test_chunk_mcp_f1_uninstall.py spawns real subprocesses
that hit the live repo's .claude/settings.local.json + systemd timer
location. Running them in the default `-m "not slow"` CI pass burns
~30s and pollutes the user's environment. G.4 pins the marker so they
only run when explicitly opted into.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "tests" / "test_chunk_mcp_f1_uninstall.py"


def test_g4_f1_uninstall_tests_marked_slow() -> None:
    assert TARGET.exists(), f"F.1 test file missing: {TARGET}"
    text = TARGET.read_text(encoding="utf-8")
    # Module-level pytestmark = pytest.mark.slow (most efficient: applies to ALL tests)
    match = re.search(r"^\s*pytestmark\s*=\s*pytest\.mark\.slow\b", text, re.M)
    assert match, (
        f"{TARGET} must declare `pytestmark = pytest.mark.slow` at module level."
    )
