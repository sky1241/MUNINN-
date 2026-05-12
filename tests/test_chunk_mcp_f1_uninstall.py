"""
CHUNK MCP F.1 — `muninn-mem uninstall` command for clean removal.

Sky's question (2026-05-12) :
  "le client aime pas, pip uninstall garde rien sauf le mycelium ?"

The honest answer at the time : pip uninstall removes the package code
and binaries, but leaves orphaned .claude/hooks/*.py files in the user's
repo + settings.local.json entries pointing at them. The hooks then
fail silently every Claude Code session (they exit 0 fail-safe but the
mycelium isn't fed anymore).

F.1 adds a proper `muninn-mem uninstall [--purge-data]` command :
- Removes hook files created by install_hooks()
- Strips muninn-owned entries from .claude/settings.local.json
- Uninstalls systemd timer (install-cron --uninstall)
- BY DEFAULT keeps .muninn/ (user data)
- --purge-data flag for nuclear option
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# G.4 (2026-05-12): F.1 tests spawn real subprocesses + write to the live
# repo's .claude/settings.local.json — they shell out to engine/core/muninn.py,
# trigger hook installation, and uninstall. Each test is ~3-5s, and they hit
# the user's home dir for the systemd timer side-effects. Default CI run
# (-m "not slow") skips them; F.1 surface is still covered by the unit-level
# helpers exercised in test_chunk_mcp_f1_*_helpers.py.
pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNINN_CLI = REPO_ROOT / "engine" / "core" / "muninn.py"


def _run_muninn(args, cwd, env=None, timeout=30):
    """Run `python3 engine/core/muninn.py <args>` in cwd."""
    e = os.environ.copy()
    e["PYTHONPATH"] = str(REPO_ROOT / "engine" / "core") + ":" + e.get("PYTHONPATH", "")
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(MUNINN_CLI), *args],
        cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=e,
    )


def _init_repo(repo: Path) -> None:
    """muninn init the repo, sanity-check hooks created."""
    r = _run_muninn(["init"], cwd=repo)
    assert r.returncode == 0, f"init failed:\n{r.stderr}"
    assert (repo / ".muninn").exists(), "init should create .muninn/"
    assert (repo / ".claude" / "hooks").exists(), "init should create .claude/hooks/"


def test_f1_uninstall_removes_hook_files(tmp_path):
    """`muninn-mem uninstall` removes the .py files install_hooks() created."""
    _init_repo(tmp_path)

    hook_files_before = sorted(p.name for p in (tmp_path / ".claude" / "hooks").iterdir())
    assert "bridge_hook.py" in hook_files_before, "init should create bridge_hook.py"

    r = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r.returncode == 0, f"uninstall failed:\n{r.stderr}"
    assert "Muninn uninstalled" in r.stdout, f"missing success banner:\n{r.stdout}"

    # The muninn-installed hooks must be gone
    hooks_dir = tmp_path / ".claude" / "hooks"
    if hooks_dir.exists():
        remaining = sorted(p.name for p in hooks_dir.iterdir())
    else:
        remaining = []
    assert "bridge_hook.py" not in remaining, "uninstall should remove bridge_hook.py"
    assert "session_start_hook.py" not in remaining, "uninstall should remove session_start_hook.py"


def test_f1_uninstall_preserves_user_data_by_default(tmp_path):
    """Default uninstall MUST leave .muninn/ alone (user data not ours)."""
    _init_repo(tmp_path)
    # Write a marker file inside .muninn/ to prove it survives
    user_data = tmp_path / ".muninn" / "user_marker.txt"
    user_data.write_text("important user data", encoding="utf-8")

    r = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r.returncode == 0

    # .muninn/ must still exist + user marker intact
    assert (tmp_path / ".muninn").exists(), "Default uninstall removed .muninn/ — data loss"
    assert user_data.exists(), "Default uninstall touched user data inside .muninn/"
    assert user_data.read_text(encoding="utf-8") == "important user data"


def test_f1_uninstall_purge_data_removes_muninn_dir(tmp_path):
    """With --purge-data, .muninn/ MUST be removed (explicit nuclear option)."""
    _init_repo(tmp_path)
    assert (tmp_path / ".muninn").exists()

    r = _run_muninn(["uninstall", "--purge-data"], cwd=tmp_path)
    assert r.returncode == 0, f"uninstall --purge-data failed:\n{r.stderr}"
    assert "purged: True" in r.stdout or "purged: true" in r.stdout.lower(), (
        f"--purge-data should report data_purged=True. stdout:\n{r.stdout}"
    )
    assert not (tmp_path / ".muninn").exists(), "--purge-data should remove .muninn/"


def test_f1_uninstall_strips_settings_local_json(tmp_path):
    """`.claude/settings.local.json` should no longer reference removed hooks."""
    _init_repo(tmp_path)

    settings_path = tmp_path / ".claude" / "settings.local.json"
    before = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks_before = before.get("hooks", {})
    assert hooks_before, "init should have populated settings.local.json hooks"

    r = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r.returncode == 0

    after = json.loads(settings_path.read_text(encoding="utf-8"))
    hooks_after = after.get("hooks", {})
    # Search for any remaining muninn-installed hook references
    for event, entries in hooks_after.items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if isinstance(e, dict) and "hooks" in e:  # matcher format
                for h in e["hooks"]:
                    cmd = h.get("command", "")
                    assert "bridge_hook.py" not in cmd
                    assert "session_start_hook.py" not in cmd
                    assert "subagent_start_hook.py" not in cmd
                    assert "post_tool_failure_hook.py" not in cmd
            elif isinstance(e, dict):
                cmd = e.get("command", "")
                assert "bridge_hook.py" not in cmd
                assert "session_start_hook.py" not in cmd
                assert "subagent_start_hook.py" not in cmd
                assert "post_tool_failure_hook.py" not in cmd


def test_f1_uninstall_idempotent(tmp_path):
    """Running uninstall twice should be safe (second run is a no-op)."""
    _init_repo(tmp_path)

    r1 = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r1.returncode == 0

    r2 = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r2.returncode == 0, f"2nd uninstall failed:\n{r2.stderr}"
    # 2nd run should report 0 hooks removed
    assert "Hook files removed: 0" in r2.stdout, (
        f"2nd uninstall should be no-op. stdout:\n{r2.stdout}"
    )


def test_f1_uninstall_on_uninit_repo_doesnt_crash(tmp_path):
    """`muninn-mem uninstall` on a repo that was never `init`d must not crash."""
    # No init — just an empty dir
    r = _run_muninn(["uninstall"], cwd=tmp_path)
    assert r.returncode == 0, f"uninstall on uninit repo crashed:\n{r.stderr}"
    assert "Muninn uninstalled" in r.stdout


def test_f1_uninstall_command_in_choices():
    """argparse must accept 'uninstall' as a valid subcommand."""
    r = _run_muninn(["uninstall", "--help"], cwd=REPO_ROOT)
    # argparse exits 0 for --help, our handler runs after parse so it actually
    # tries to uninstall in REPO_ROOT — but that's fine, it's idempotent.
    # We just want to confirm the subcommand is recognized (no "invalid choice").
    assert "invalid choice" not in (r.stdout + r.stderr).lower(), (
        "uninstall should be a recognized subcommand"
    )
