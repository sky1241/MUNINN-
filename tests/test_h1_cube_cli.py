"""H.1 — Wire `muninn-mem cube` CLI sub-command.

Until H.1 ships, the 5597 LOC of engine/core/cube_*.py + cube/ are
unreachable from the CLI — cli_scan/run/status/god live in
cube_analysis.py but never get called outside test suites.

Contract :
  - `muninn-mem cube` (default action=status) returns a status dict
  - `muninn-mem cube --cube-action scan --repo PATH` calls cli_scan(PATH)
  - `muninn-mem cube --cube-action run --cycles N --level L` calls cli_run
  - `muninn-mem cube --cube-action god` calls cli_god
  - All four delegate to the existing cube_analysis functions (no
    duplication)
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNINN_PY = REPO_ROOT / "engine" / "core" / "muninn.py"


def _muninn_choices() -> list[str]:
    """Parse engine/core/muninn.py argparse to extract the `command` choices."""
    src = MUNINN_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "command"):
            for kw in node.keywords:
                if kw.arg == "choices" and isinstance(kw.value, ast.List):
                    return [
                        e.value for e in kw.value.elts
                        if isinstance(e, ast.Constant)
                    ]
    return []


def test_h1_cube_in_command_choices() -> None:
    """The `cube` sub-command must be declared in argparse choices."""
    assert "cube" in _muninn_choices(), (
        "`cube` missing from argparse choices in engine/core/muninn.py"
    )


def test_h1_cube_handler_exists() -> None:
    """Handler `if args.command == "cube":` must exist in muninn.py."""
    src = MUNINN_PY.read_text(encoding="utf-8")
    assert 'args.command == "cube"' in src, (
        "No handler for `cube` command in engine/core/muninn.py main()"
    )


def test_h1_cube_uses_cli_functions() -> None:
    """The handler must import the cli_scan/run/status/god functions —
    don't re-implement, delegate."""
    src = MUNINN_PY.read_text(encoding="utf-8")
    # Look for the handler block (loosely) referencing the cli_* names
    assert "cli_scan" in src and "cli_run" in src and "cli_status" in src \
        and "cli_god" in src, (
        "muninn.py cube handler must delegate to cube_analysis.cli_{scan,run,status,god}"
    )


def test_h1_cube_default_action_is_status(tmp_path: Path) -> None:
    """`muninn-mem cube` without --cube-action must default to status."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("MUNINN_DEBUG", None)
    rc = subprocess.run(
        [sys.executable, "-m", "muninn._engine", "cube"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
    )
    combined = rc.stdout + rc.stderr
    # Either it prints a status-like report or it cleanly says "no cube db"
    assert rc.returncode in (0, 1), (
        f"cube default-action exit code = {rc.returncode}. Output:\n{combined}"
    )
    assert "Traceback" not in combined, (
        f"cube status must not raise. Got:\n{combined}"
    )


def test_h1_mirror_engine_muninn(tmp_path: Path) -> None:
    """BUG-091 mirror discipline: muninn/_engine.py must mirror the cube wiring."""
    mirror_src = (REPO_ROOT / "muninn" / "_engine.py").read_text(encoding="utf-8")
    assert 'args.command == "cube"' in mirror_src, (
        "muninn/_engine.py missing cube handler (BUG-091 mirror)"
    )
    assert '"cube"' in mirror_src, (
        "muninn/_engine.py missing 'cube' in argparse choices"
    )


def test_h1_cube_action_choices_complete() -> None:
    """The --cube-action flag must declare all 4 actions."""
    src = MUNINN_PY.read_text(encoding="utf-8")
    # Look for cube_action argument with all 4 values
    for action in ("scan", "run", "status", "god"):
        assert f'"{action}"' in src or f"'{action}'" in src, (
            f"--cube-action choice '{action}' missing from muninn.py"
        )
