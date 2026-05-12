"""H.6 — `muninn-mem init` must register the 3 defensive PreToolUse hooks.

Before H.6, `install_hooks()` already had the wiring code (lines ~956-987
of engine/core/muninn_install.py), but Sky's live settings.local.json was
generated before that wiring was complete and never got migrated.

This test pins the install_hooks() behaviour: on a FRESH `muninn-mem init`,
the resulting settings.local.json must include the 3 defensive PreToolUse
hooks (pre_tool_use_bash_destructive, pre_tool_use_bash_secrets,
pre_tool_use_edit_hardcode) wired under `hooks.PreToolUse`.

NB : Sky's live .claude/settings.local.json is gitignored and not touched
by this test (we run init in tmp_path). Sky needs to re-run
`muninn-mem init` in his own repos to get the defensive hooks active.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_init(cwd: Path) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("MUNINN_DEBUG", None)
    proc = subprocess.run(
        [sys.executable, "-m", "muninn._engine", "init"],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_h6_init_registers_defensive_hooks(tmp_path: Path) -> None:
    """After init, settings.local.json must include the 3 defensive hooks."""
    rc, out, err = _run_init(tmp_path)
    combined = out + err
    assert "Traceback" not in combined, (
        f"muninn-mem init crashed. Output:\n{combined}"
    )
    settings = tmp_path / ".claude" / "settings.local.json"
    assert settings.exists(), (
        f"init did not create {settings}. Output:\n{combined}"
    )
    data = json.loads(settings.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    pre_tool_use = hooks.get("PreToolUse", [])
    # Flatten the list of commands referenced under PreToolUse
    cmds = []
    for entry in pre_tool_use:
        for h in entry.get("hooks", []):
            cmds.append(h.get("command", ""))
    cmds_str = " | ".join(cmds)
    for required in (
        "pre_tool_use_bash_destructive.py",
        "pre_tool_use_bash_secrets.py",
        "pre_tool_use_edit_hardcode.py",
    ):
        assert required in cmds_str, (
            f"Defensive hook {required!r} not registered in settings.local.json. "
            f"PreToolUse commands found: {cmds_str}"
        )


def test_h6_hooks_copied_to_disk(tmp_path: Path) -> None:
    """The 3 .py hook scripts must be copied to .claude/hooks/."""
    _run_init(tmp_path)
    hooks_dir = tmp_path / ".claude" / "hooks"
    assert hooks_dir.exists(), f"{hooks_dir} not created by init"
    for required in (
        "pre_tool_use_bash_destructive.py",
        "pre_tool_use_bash_secrets.py",
        "pre_tool_use_edit_hardcode.py",
    ):
        assert (hooks_dir / required).exists(), (
            f"{required} not copied to {hooks_dir}"
        )
