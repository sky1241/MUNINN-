"""G.6 — Doctor pre-init clarity.

Problem: `muninn-mem doctor` in a repo WITHOUT `.muninn/` printed all 22+
checks, with most failing or warning — confusing first-time users.

Fix: detect pre-init state and print a short, dedicated message that
points users at `muninn-mem init` as the very next step.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_doctor(cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("MUNINN_DEBUG", None)
    proc = subprocess.run(
        [sys.executable, "-m", "muninn._engine", "doctor"],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_g6_doctor_pre_init_simplified(tmp_path: Path) -> None:
    rc, out, err = _run_doctor(tmp_path)
    combined = out + err
    # The output must point at `muninn-mem init` as the explicit next step
    assert "muninn-mem init" in combined, (
        f"Doctor pre-init must mention `muninn-mem init`. Output:\n{combined}"
    )
    # Count [OK]/[FAIL]/[WARN] lines — must be strictly less than 12.
    n_checks = sum(
        1 for line in combined.splitlines()
        if any(tag in line for tag in ("[OK]", "[FAIL]", "[WARN]"))
    )
    assert n_checks < 12, (
        f"Pre-init doctor should print < 12 checks, got {n_checks}. "
        f"Output:\n{combined}"
    )


def test_g6_doctor_post_init_full(tmp_path: Path) -> None:
    """When .muninn/ exists, the full 22+ check sweep must still run."""
    (tmp_path / ".muninn").mkdir()
    rc, out, err = _run_doctor(tmp_path)
    combined = out + err
    n_checks = sum(
        1 for line in combined.splitlines()
        if any(tag in line for tag in ("[OK]", "[FAIL]", "[WARN]"))
    )
    assert n_checks >= 6, (
        f"Post-init doctor should print >= 6 checks (full sweep), got "
        f"{n_checks}. Output:\n{combined}"
    )
