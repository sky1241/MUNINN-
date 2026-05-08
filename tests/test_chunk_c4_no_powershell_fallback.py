"""CHUNK C4 — remove PowerShell ANTHROPIC_API_KEY fallback.

`_llm_compress` had a PowerShell subprocess fallback to read
ANTHROPIC_API_KEY from the User environment on Windows. Sky is on
Linux now and the fallback adds:
  - 5s subprocess timeout latency on every L9 call when env is unset
  - Stdout capture risk (key could leak to logs/captured output)
  - Untrustworthy code path on a non-Windows system that cannot
    execute powershell anyway

Fix: remove the PowerShell branch. Read only os.environ. If the env
var is missing, return text unchanged (existing behavior).

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C4
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def test_no_powershell_in_llm_compress():
    """Static check: no `powershell` invocation remains in the L9 module."""
    src = (REPO / "engine" / "core" / "muninn_layers.py").read_text()
    # Allow the word `powershell` in comments/docstrings if needed, but
    # there must be no `'powershell'` string literal in code.
    code_lines = [
        line for line in src.splitlines()
        if not line.strip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert "'powershell'" not in code_only and '"powershell"' not in code_only, (
        "PowerShell fallback still present in muninn_layers.py — must be removed"
    )


def test_llm_compress_unchanged_when_no_api_key(monkeypatch):
    """When ANTHROPIC_API_KEY is unset, L9 returns text unchanged
    immediately (no subprocess spawn)."""
    import sys
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_layers" not in sys.modules:
        import muninn_layers  # noqa: F401
    import muninn_layers
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(muninn_layers._m, "_SKIP_L9", False)
    text = "x" * 5000  # Above 4000 threshold
    result = muninn_layers._llm_compress(text, context="test")
    assert result == text


def test_llm_compress_does_not_spawn_subprocess(monkeypatch):
    """Calling _llm_compress without a key must NOT call subprocess.run."""
    import sys
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    import muninn_layers
    import subprocess

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(muninn_layers._m, "_SKIP_L9", False)

    calls = []
    real_run = subprocess.run

    def _track_run(*args, **kwargs):
        calls.append((args, kwargs))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _track_run)

    muninn_layers._llm_compress("y" * 5000, context="test")

    # Ensure no subprocess was spawned (powershell call would do that)
    powershell_calls = [
        c for c in calls
        if any("powershell" in str(arg) for arg in c[0])
    ]
    assert not powershell_calls, (
        f"PowerShell subprocess was spawned: {powershell_calls}"
    )
