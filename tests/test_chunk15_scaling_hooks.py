"""
CHUNK 15 — Tests for the 3 scaling/enterprise hooks.

These hooks are NOT activated by default in install_hooks(). They are
scaffolding for the Phase 3 enterprise pitch (compliance, audit, drift
detection). Sky activates them manually when a customer needs them.

Tests:
1. notification_audit_hook.py - Notification -> .muninn/audit_log.jsonl
2. post_tool_use_edit_log.py - PostToolUse Edit/Write -> .muninn/edits_log.jsonl
3. config_change_hook.py - ConfigChange -> .muninn/config_changes.jsonl
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def run_hook(script_name: str, payload: dict, timeout: int = 10) -> tuple[int, str, str]:
    hook_path = HOOKS_DIR / script_name
    assert hook_path.exists(), f"Hook script not found: {hook_path}"
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=timeout,
    )
    return (
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


# ── notification_audit_hook.py ─────────────────────────────────


HOOK_NOTIF = "notification_audit_hook.py"


def test_notification_creates_audit_log(tmp_path):
    (tmp_path / ".muninn").mkdir()
    payload = {
        "hook_event_name": "Notification",
        "notification_type": "permission_prompt",
        "message": "Claude needs Bash permission",
        "title": "Permission",
        "session_id": "sess-001",
        "cwd": str(tmp_path),
    }
    code, _, _ = run_hook(HOOK_NOTIF, payload)
    assert code == 0
    audit = tmp_path / ".muninn" / "audit_log.jsonl"
    assert audit.exists()
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["type"] == "permission_prompt"
    assert entry["session_id"] == "sess-001"
    assert "ts" in entry


def test_notification_appends_multiple(tmp_path):
    (tmp_path / ".muninn").mkdir()
    for i in range(3):
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "idle_prompt",
            "message": f"msg-{i}",
            "cwd": str(tmp_path),
        }
        run_hook(HOOK_NOTIF, payload)
    audit = tmp_path / ".muninn" / "audit_log.jsonl"
    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_notification_handles_invalid_json(tmp_path):
    hook_path = HOOKS_DIR / HOOK_NOTIF
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"not json",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


def test_notification_caps_at_10000(tmp_path):
    """Verify the cap behavior — pre-populate, then add one more."""
    (tmp_path / ".muninn").mkdir()
    audit = tmp_path / ".muninn" / "audit_log.jsonl"
    # Pre-populate with 10010 entries
    with audit.open("w", encoding="utf-8") as f:
        for i in range(10010):
            f.write(json.dumps({"ts": "2026-01-01T00:00:00", "type": "old", "msg": str(i)}) + "\n")

    payload = {
        "hook_event_name": "Notification",
        "notification_type": "auth_success",
        "message": "fresh",
        "cwd": str(tmp_path),
    }
    run_hook(HOOK_NOTIF, payload)

    lines = audit.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 10000
    # Newest entry should be in the result
    assert any("fresh" in line for line in lines[-5:])


# ── post_tool_use_edit_log.py ──────────────────────────────────


HOOK_EDIT = "post_tool_use_edit_log.py"


def test_edit_log_records_edit(tmp_path):
    (tmp_path / ".muninn").mkdir()
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/foo.py",
            "old_string": "def old(): pass",
            "new_string": "def new(): return 42",
        },
        "tool_use_id": "toolu_001",
        "cwd": str(tmp_path),
    }
    code, _, _ = run_hook(HOOK_EDIT, payload)
    assert code == 0
    log = tmp_path / ".muninn" / "edits_log.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["tool"] == "Edit"
    assert entry["file_path"] == "src/foo.py"
    assert entry["old_size"] == len("def old(): pass")
    assert entry["new_size"] == len("def new(): return 42")
    assert entry["delta"] == entry["new_size"] - entry["old_size"]


def test_edit_log_records_write(tmp_path):
    (tmp_path / ".muninn").mkdir()
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "new_file.py",
            "content": "x = 1\ny = 2\n",
        },
        "cwd": str(tmp_path),
    }
    run_hook(HOOK_EDIT, payload)
    log = tmp_path / ".muninn" / "edits_log.jsonl"
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["tool"] == "Write"
    assert entry["old_size"] == 0
    assert entry["new_size"] == len("x = 1\ny = 2\n")


def test_edit_log_ignores_non_edit_tools(tmp_path):
    (tmp_path / ".muninn").mkdir()
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": "foo.py"},
        "cwd": str(tmp_path),
    }
    code, _, _ = run_hook(HOOK_EDIT, payload)
    assert code == 0
    log = tmp_path / ".muninn" / "edits_log.jsonl"
    # Should NOT have created the log file
    assert not log.exists() or log.read_text() == ""


def test_edit_log_handles_invalid_json():
    hook_path = HOOKS_DIR / HOOK_EDIT
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"junk",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


def test_edit_log_caps_at_10000(tmp_path):
    (tmp_path / ".muninn").mkdir()
    log = tmp_path / ".muninn" / "edits_log.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for i in range(10010):
            f.write(json.dumps({"ts": "2026-01-01", "tool": "Edit", "file_path": f"old{i}.py"}) + "\n")
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": "fresh.py", "old_string": "a", "new_string": "b"},
        "cwd": str(tmp_path),
    }
    run_hook(HOOK_EDIT, payload)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 10000
    assert any("fresh.py" in line for line in lines[-5:])


# ── config_change_hook.py ──────────────────────────────────────


HOOK_CFG = "config_change_hook.py"


def test_config_change_logs_event(tmp_path):
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".claude").mkdir()
    # Create a valid settings.local.json with no hooks (so no missing paths)
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"hooks": {}}), encoding="utf-8"
    )
    payload = {
        "hook_event_name": "ConfigChange",
        "source": "local_settings",
        "cwd": str(tmp_path),
    }
    code, _, _ = run_hook(HOOK_CFG, payload)
    assert code == 0
    log = tmp_path / ".muninn" / "config_changes.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["source"] == "local_settings"
    assert entry["valid_after"] is True
    assert entry["missing_paths"] == []


def test_config_change_detects_missing_hook(tmp_path):
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".claude").mkdir()
    # Settings references a hook that doesn't exist
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({
            "hooks": {
                "Stop": [
                    {"type": "command", "command": 'python "/nonexistent/hook.py"'}
                ]
            }
        }),
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "ConfigChange",
        "source": "local_settings",
        "cwd": str(tmp_path),
    }
    run_hook(HOOK_CFG, payload)
    log = tmp_path / ".muninn" / "config_changes.jsonl"
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["valid_after"] is False
    assert any("nonexistent" in p for p in entry["missing_paths"])


def test_config_change_handles_invalid_settings_json(tmp_path):
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text("garbage{{", encoding="utf-8")
    payload = {
        "hook_event_name": "ConfigChange",
        "source": "local_settings",
        "cwd": str(tmp_path),
    }
    code, _, _ = run_hook(HOOK_CFG, payload)
    assert code == 0
    # Should still log the event
    log = tmp_path / ".muninn" / "config_changes.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["valid_after"] is False


def test_config_change_handles_invalid_json_input():
    hook_path = HOOKS_DIR / HOOK_CFG
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"junk",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


def test_config_change_supports_pre_tool_use_matcher_format(tmp_path):
    """The validator must walk the matcher-style format used by PreToolUse."""
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": 'python "/missing/x.py"'}
                        ]
                    }
                ]
            }
        }),
        encoding="utf-8",
    )
    payload = {
        "hook_event_name": "ConfigChange",
        "source": "local_settings",
        "cwd": str(tmp_path),
    }
    run_hook(HOOK_CFG, payload)
    log = tmp_path / ".muninn" / "config_changes.jsonl"
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["valid_after"] is False
    assert any("missing" in p for p in entry["missing_paths"])


# ── Existence sanity ──────────────────────────────────────────


def test_all_3_scaling_hooks_exist():
    for name in [HOOK_NOTIF, HOOK_EDIT, HOOK_CFG]:
        assert (HOOKS_DIR / name).exists(), f"Missing hook: {name}"
