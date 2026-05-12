"""G.3 — Friendly error handling at the CLI boundary.

Problem: `muninn-mem feed /nonexistent.jsonl` returns a raw Python
traceback — terrible UX for first-time users.

Fix: wrap `main()` calls with a friendly-error handler that catches the
common filesystem/lookup errors and prints a short message instead of
a stack trace. `MUNINN_DEBUG=1` re-raises for engine devs.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_muninn(args: list[str], cwd: Path | None = None,
                env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Invoke `python -m muninn._engine <args>` and return (rc, stdout, stderr)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    # G.3 escape hatch off by default
    env.pop("MUNINN_DEBUG", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-m", "muninn._engine", *args],
        cwd=str(cwd or REPO_ROOT),
        env=env, capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _assert_no_traceback(combined: str) -> None:
    assert "Traceback" not in combined, (
        f"Friendly handler should suppress 'Traceback'; got:\n{combined}"
    )


def test_g3_feed_nonexistent_friendly(tmp_path: Path) -> None:
    """feed on a missing file → friendly error, no traceback, exit 1."""
    missing = tmp_path / "nope.jsonl"
    rc, out, err = _run_muninn(["feed", str(missing)], cwd=tmp_path)
    combined = out + err
    _assert_no_traceback(combined)
    assert rc != 0, f"Expected non-zero exit, got {rc}. Output:\n{combined}"
    # Friendly hint must mention the missing path or 'not found'
    assert ("not found" in combined.lower()
            or "does not exist" in combined.lower()
            or str(missing) in combined), (
        f"Expected friendly 'not found' hint; got:\n{combined}"
    )


def test_g3_compress_invalid_path(tmp_path: Path) -> None:
    missing = tmp_path / "ghost.md"
    rc, out, err = _run_muninn(["compress", str(missing)], cwd=tmp_path)
    combined = out + err
    _assert_no_traceback(combined)
    assert rc != 0


def test_g3_bootstrap_nonexistent_repo(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-repo"
    rc, out, err = _run_muninn(["bootstrap", str(missing)], cwd=tmp_path)
    combined = out + err
    _assert_no_traceback(combined)
    assert rc != 0


def test_g3_muninn_debug_env_shows_traceback(tmp_path: Path) -> None:
    """With MUNINN_DEBUG=1 the friendly handler must re-raise → traceback visible."""
    missing = tmp_path / "nope.jsonl"
    rc, out, err = _run_muninn(
        ["feed", str(missing)], cwd=tmp_path,
        env_extra={"MUNINN_DEBUG": "1"},
    )
    combined = out + err
    assert "Traceback" in combined, (
        f"MUNINN_DEBUG=1 must reveal Traceback (escape hatch). Got:\n{combined}"
    )
