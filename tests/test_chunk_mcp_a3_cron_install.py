"""
CHUNK MCP A.3 — muninn install-cron sets up weekly systemd-user prune timer.

Le hook SessionEnd ne run prune que pendant les sessions. Si Sky n'utilise
pas le repo pendant des semaines, le mycelium accumule des connexions
mortes et le tree devient stale.

`muninn install-cron` génère 2 systemd-user units :
  - ~/.config/systemd/user/muninn-prune.service  (oneshot, calls muninn prune)
  - ~/.config/systemd/user/muninn-prune.timer    (OnCalendar=Sun *-*-* 04:00:00)

`muninn install-cron --uninstall` retire les 2 fichiers (idempotent).

Tests behaviouraux :
1. install_cron crée les 2 fichiers .service + .timer
2. .timer content matche Sundays 4am (OnCalendar=Sun *-*-* 04:00:00)
3. .service appelle bien `python -m muninn prune` avec --force
4. uninstall=True supprime les 2 fichiers
5. Idempotent (2 calls successifs)
6. Ne PAS invoquer systemctl (sandbox-safe)
7. Retourne dict (aligné A.2 wrapper pattern)
8. Skip propre si systemd absent
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))


def _patch_systemd_present(monkeypatch, present=True):
    """Patch shutil.which to simulate systemctl presence."""
    orig_which = shutil.which

    def fake_which(cmd):
        if cmd == "systemctl":
            return "/usr/bin/systemctl" if present else None
        return orig_which(cmd)

    monkeypatch.setattr(shutil, "which", fake_which)


# ── Signature / existence ────────────────────────────────────


def test_install_cron_exists():
    import muninn
    assert hasattr(muninn, "install_cron"), "muninn.install_cron missing"


def test_install_cron_signature():
    """install_cron(repo_path: Path, uninstall: bool = False) -> dict."""
    import inspect
    import muninn
    sig = inspect.signature(muninn.install_cron)
    params = list(sig.parameters.keys())
    assert "repo_path" in params
    assert "uninstall" in params


# ── Install behaviour ────────────────────────────────────────


def test_install_creates_service_and_timer(tmp_path, monkeypatch):
    """install_cron writes both .service and .timer in $HOME/.config/systemd/user/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    result = muninn.install_cron(repo)

    assert isinstance(result, dict)
    assert result["status"] in ("installed", "already_installed")
    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    tmr = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.timer"
    assert svc.exists(), f"service file not created: {svc}"
    assert tmr.exists(), f"timer file not created: {tmr}"


def test_timer_oncalendar_is_sunday_4am(tmp_path, monkeypatch):
    """The .timer must trigger on Sundays at 04:00."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_cron(repo)

    tmr = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.timer"
    content = tmr.read_text(encoding="utf-8")
    assert "OnCalendar=Sun *-*-* 04:00:00" in content
    assert "Persistent=true" in content


def test_service_calls_muninn_prune(tmp_path, monkeypatch):
    """The .service must invoke `python -m muninn prune` (or muninn.py prune) with --force."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_cron(repo)

    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    content = svc.read_text(encoding="utf-8")
    # Either `python -m muninn prune` or `python <muninn.py> prune`
    assert "muninn" in content and "prune" in content
    assert "--force" in content
    # Should reference the repo path
    assert str(repo) in content
    # Should be a oneshot service
    assert "Type=oneshot" in content


def test_install_returns_useful_dict(tmp_path, monkeypatch):
    """install_cron returns a dict with at least status, service_path, timer_path keys."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    result = muninn.install_cron(repo)

    assert "status" in result
    assert "service_path" in result
    assert "timer_path" in result
    # status is one of the documented values
    assert result["status"] in (
        "installed", "already_installed", "uninstalled",
        "skipped_no_systemd",
    )


# ── Uninstall + idempotence ──────────────────────────────────


def test_uninstall_removes_both_files(tmp_path, monkeypatch):
    """install_cron(uninstall=True) must delete both files."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_cron(repo)
    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    tmr = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.timer"
    assert svc.exists() and tmr.exists()

    result = muninn.install_cron(repo, uninstall=True)
    assert result["status"] == "uninstalled"
    assert not svc.exists()
    assert not tmr.exists()


def test_uninstall_idempotent_when_already_absent(tmp_path, monkeypatch):
    """Calling uninstall on a fresh repo (nothing installed) must not crash."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    # Never installed — uninstall should be a no-op
    result = muninn.install_cron(repo, uninstall=True)
    assert result["status"] == "uninstalled"


def test_install_idempotent(tmp_path, monkeypatch):
    """Calling install twice must produce same final state (same content)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    r1 = muninn.install_cron(repo)
    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    content1 = svc.read_text(encoding="utf-8")
    r2 = muninn.install_cron(repo)
    content2 = svc.read_text(encoding="utf-8")
    assert content1 == content2
    assert r1["status"] in ("installed", "already_installed")
    assert r2["status"] in ("installed", "already_installed")


# ── Safety / sandbox ─────────────────────────────────────────


def test_install_does_not_invoke_systemctl(tmp_path, monkeypatch):
    """install_cron must NOT call systemctl (test-friendly, sandbox-safe)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()

    with patch("subprocess.run") as mock_run, \
         patch("subprocess.check_call") as mock_cc, \
         patch("subprocess.check_output") as mock_co, \
         patch("subprocess.Popen") as mock_popen:
        muninn.install_cron(repo)
        for mock_obj in [mock_run, mock_cc, mock_co, mock_popen]:
            for call in mock_obj.call_args_list:
                args0 = call[0][0] if call[0] else ""
                args_str = args0 if isinstance(args0, str) else " ".join(map(str, args0))
                assert "systemctl" not in args_str, (
                    f"install_cron unexpectedly invoked systemctl: {args_str}"
                )


def test_skip_when_systemd_absent(tmp_path, monkeypatch):
    """If systemctl is not on PATH, return skipped_no_systemd without writing files."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=False)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    result = muninn.install_cron(repo)
    assert result["status"] == "skipped_no_systemd"
    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    tmr = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.timer"
    assert not svc.exists()
    assert not tmr.exists()


def test_service_uses_sys_executable_or_python(tmp_path, monkeypatch):
    """The .service ExecStart must reference a python binary (sys.executable or 'python')."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_cron(repo)

    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    content = svc.read_text(encoding="utf-8")
    # ExecStart line must reference python (either sys.executable absolute path or 'python')
    exec_lines = [l for l in content.splitlines() if l.startswith("ExecStart=")]
    assert exec_lines, "no ExecStart line in .service"
    exec_line = exec_lines[0]
    assert "python" in exec_line.lower(), f"ExecStart missing python: {exec_line}"


def test_perms_644(tmp_path, monkeypatch):
    """Systemd unit files must be 0o644 (rw-r--r--) — systemd ignores other perms."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _patch_systemd_present(monkeypatch, present=True)

    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_cron(repo)

    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    tmr = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.timer"
    # Mask owner+group+other read/write bits
    assert (svc.stat().st_mode & 0o777) == 0o644, (
        f"service perms: {oct(svc.stat().st_mode & 0o777)}"
    )
    assert (tmr.stat().st_mode & 0o777) == 0o644, (
        f"timer perms: {oct(tmr.stat().st_mode & 0o777)}"
    )
