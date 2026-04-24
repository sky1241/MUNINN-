"""
CHUNK 12 — Tests for the 3 PreToolUse enforcement hooks.

These hooks block Claude from violating CLAUDE.md RULES 1, 2, 3 in a way
that doesn't depend on Claude's good will. They are the enforcement layer.

Tests:
1. pre_tool_use_bash_destructive.py - blocks force-push, rm -rf, DROP TABLE
2. pre_tool_use_bash_secrets.py - blocks echo $TOKEN, cat .env
3. pre_tool_use_edit_hardcode.py - blocks Edit/Write with C:/Users/.../MUNINN-

Each hook is tested via subprocess:
- Send a JSON payload on stdin
- Check exit code (0 = allow, 2 = block)
- Check stderr message when blocked
- Verify no false positives on legitimate cases
- Verify no crash on malformed input
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
    """Run a hook with the given payload, return (exit_code, stdout, stderr)."""
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


# ── pre_tool_use_bash_destructive.py ───────────────────────────


HOOK_DESTRUCTIVE = "pre_tool_use_bash_destructive.py"


def test_destructive_blocks_force_push():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main --force"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2, f"Expected block (exit 2), got {code}. stderr: {stderr}"
    assert "Blocked destructive" in stderr or "BLOCKED" in stderr.upper()


def test_destructive_blocks_force_push_short():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push -f origin main"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_reset_hard():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git reset --hard HEAD~3"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_rm_rf_root():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /tmp/foo && rm -rf /"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_drop_table():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "sqlite3 db.sqlite 'DROP TABLE users;'"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_no_verify():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit --no-verify -m 'fix'"},
    }
    code, _, stderr = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


# ── Audit 2026-04-10 — bugs caught and fixed ───────────────────


def test_destructive_blocks_rm_rf_glob_subdir():
    """BUG-D1: rm -rf foo/* was allowed, should block."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf foo/*"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2, "rm -rf foo/* should be blocked"


def test_destructive_blocks_rm_rf_glob_extension():
    """rm -rf *.log should also block."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf *.log"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_rm_rf_parent():
    """rm -rf ../other should block (parent dir)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf ../other"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 2


def test_destructive_blocks_git_push_combined_short_flags():
    """BUG-D3: git push -fu / -uf (combined short flags) was allowed."""
    for cmd in ["git push -fu origin main", "git push -uf origin feature"]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
        }
        code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
        assert code == 2, f"Should block: {cmd}"


def test_destructive_blocks_eval_wrapped():
    """BUG-D2: eval-wrapped destructive commands were allowed."""
    for cmd in [
        "eval 'rm -rf /'",
        "bash -c 'git push --force'",
        "sh -c 'rm -rf /tmp/* --no-preserve-root'",
    ]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": cmd},
        }
        code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
        assert code == 2, f"Should block eval-wrapped: {cmd}"


def test_destructive_no_false_positive_legit_push_short_u():
    """git push -u origin feature (set-upstream short) should NOT block.

    The new combined-short-flag pattern needs to NOT trigger on lone -u.
    """
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push -u origin feature"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0, "git push -u should be allowed (set-upstream is not destructive)"


def test_destructive_no_false_positive_rm_specific_file():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm tests/temp.txt"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0


def test_destructive_no_false_positive_rm_build_dir():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf build/"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    # build/ is technically a dir name, no glob, no dangerous location
    # → should NOT block (developers do this all the time)
    assert code == 0


def test_destructive_allows_normal_git_push():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0


def test_destructive_allows_ls():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0


def test_destructive_allows_rm_specific_file():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "rm tests/test_chunk6_compress_claude_md.py"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0


def test_destructive_ignores_non_bash_tool():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"command": "git push --force"},
    }
    code, _, _ = run_hook(HOOK_DESTRUCTIVE, payload)
    assert code == 0  # not a Bash call, hook should ignore


def test_destructive_handles_invalid_json():
    hook_path = HOOKS_DIR / HOOK_DESTRUCTIVE
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"this is not JSON {{{",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0  # never crash


# ── pre_tool_use_bash_secrets.py ───────────────────────────────


HOOK_SECRETS = "pre_tool_use_bash_secrets.py"


def test_secrets_blocks_echo_token():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo $GITHUB_TOKEN"},
    }
    code, _, stderr = run_hook(HOOK_SECRETS, payload)
    assert code == 2


def test_secrets_blocks_echo_aws_secret():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo $AWS_SECRET_KEY"},
    }
    code, _, stderr = run_hook(HOOK_SECRETS, payload)
    assert code == 2


def test_secrets_blocks_cat_dotenv():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat .env"},
    }
    code, _, stderr = run_hook(HOOK_SECRETS, payload)
    assert code == 2


def test_secrets_blocks_cat_credentials():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "cat ~/.aws/credentials"},
    }
    code, _, stderr = run_hook(HOOK_SECRETS, payload)
    assert code == 2


def test_secrets_blocks_env_grep_secret():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "env | grep TOKEN"},
    }
    code, _, stderr = run_hook(HOOK_SECRETS, payload)
    assert code == 2


def test_secrets_allows_existence_check():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": '[ -n "$GITHUB_TOKEN" ] && echo "set" || echo "unset"'},
    }
    code, _, _ = run_hook(HOOK_SECRETS, payload)
    assert code == 0


def test_secrets_allows_length_check():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": 'echo "length: ${#GITHUB_TOKEN}"'},
    }
    code, _, _ = run_hook(HOOK_SECRETS, payload)
    assert code == 0


def test_secrets_allows_normal_echo():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo Hello world"},
    }
    code, _, _ = run_hook(HOOK_SECRETS, payload)
    assert code == 0


def test_secrets_allows_curl_with_auth():
    """curl with bearer is OK — token is sent to API, not displayed."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": 'curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user'
        },
    }
    code, _, _ = run_hook(HOOK_SECRETS, payload)
    assert code == 0  # curl uses but does not echo the token


def test_secrets_ignores_non_bash():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"command": "echo $TOKEN"},
    }
    code, _, _ = run_hook(HOOK_SECRETS, payload)
    assert code == 0


def test_secrets_handles_invalid_json():
    hook_path = HOOKS_DIR / HOOK_SECRETS
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"garbage",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


# ── pre_tool_use_edit_hardcode.py ──────────────────────────────


HOOK_HARDCODE = "pre_tool_use_edit_hardcode.py"


def test_hardcode_blocks_edit_engine_with_path():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "engine/core/muninn.py",
            "old_string": "def foo():",
            "new_string": 'def foo():\n    path = "C:/Users/ludov/MUNINN-/tree.json"',
        },
    }
    code, _, stderr = run_hook(HOOK_HARDCODE, payload)
    assert code == 2
    assert "hardcode" in stderr.lower() or "Hardcoded" in stderr or "RULE 1" in stderr


def test_hardcode_blocks_write_muninn_package():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "muninn/foo.py",
            "content": 'PATH = "C:/Users/ludov/MUNINN-/tree.json"\n',
        },
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 2


def test_hardcode_allows_path_in_test_file():
    """Tests can have hardcoded paths — they're test fixtures."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "tests/test_foo.py",
            "old_string": "def test():",
            "new_string": 'def test():\n    path = "C:/Users/ludov/MUNINN-/tree.json"',
        },
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 0


def test_hardcode_allows_path_in_doc_file():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "docs/SETUP.md",
            "old_string": "old",
            "new_string": "Set repo to C:/Users/ludov/MUNINN-",
        },
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 0


def test_hardcode_allows_path_in_comment():
    """A path in a Python comment is allowed (counter-example doc)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "engine/core/muninn.py",
            "old_string": "def foo():",
            "new_string": 'def foo():\n    # Note: never hardcode "C:/Users/ludov/MUNINN-"\n    pass',
        },
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 0  # path is in comment, not in code


def test_hardcode_allows_clean_engine_edit():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "engine/core/muninn.py",
            "old_string": "def foo():",
            "new_string": "def foo(repo_path):\n    path = Path(repo_path) / 'tree.json'",
        },
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 0


def test_hardcode_ignores_bash_tool():
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo C:/Users/ludov/MUNINN-/tree.json"},
    }
    code, _, _ = run_hook(HOOK_HARDCODE, payload)
    assert code == 0  # only checks Edit/Write


def test_hardcode_handles_invalid_json():
    hook_path = HOOKS_DIR / HOOK_HARDCODE
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"junk",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


# ── install_hooks integration ──────────────────────────────────


@pytest.mark.parametrize("hook_name", [
    "post_tool_failure_hook.py",
    "subagent_start_hook.py",
    "notification_audit_hook.py",
    "post_tool_use_edit_log.py",
    "config_change_hook.py",
    "pre_tool_use_bash_destructive.py",
    "pre_tool_use_bash_secrets.py",
    "pre_tool_use_edit_hardcode.py",
    "bridge_hook.py",
])
@pytest.mark.parametrize("payload_label,payload_bytes", [
    ("list", b"[1, 2, 3]"),
    ("string", b'"just a string"'),
    ("int", b"42"),
    ("null", b"null"),
    ("invalid_json", b"garbage{{{"),
    ("empty", b""),
])
def test_audit_all_hooks_robust_to_malformed_payloads(hook_name, payload_label, payload_bytes):
    """Audit 2026-04-10: every hook must exit 0 on any malformed payload.

    Bugs caught and fixed during this audit:
    - post_tool_failure_hook.py: crashed on list payload (AttributeError on .get)
    - notification_audit_hook.py: same
    - post_tool_use_edit_log.py: same
    - config_change_hook.py: same
    - bridge_hook.py: same
    Plus the 2 generators in engine/core/muninn.py and muninn/_engine.py.

    The contract is: hooks NEVER crash. They exit 0 (silent skip) on bad
    input. A crash would block the corresponding Claude operation silently.
    """
    hook_path = HOOKS_DIR / hook_name
    if not hook_path.exists():
        pytest.skip(f"Hook not present: {hook_name}")
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=payload_bytes,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"{hook_name} crashed on {payload_label} payload "
        f"(exit={result.returncode}). Hooks must NEVER crash."
    )


def test_install_hooks_copies_pre_tool_use_hooks(tmp_path):
    """install_hooks should copy the 3 pre_tool_use hooks to target repo."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_hooks(repo)

    # The 3 PreToolUse scripts should be present in the target
    expected = [
        "pre_tool_use_bash_destructive.py",
        "pre_tool_use_bash_secrets.py",
        "pre_tool_use_edit_hardcode.py",
    ]
    target_hooks_dir = repo / ".claude" / "hooks"
    for name in expected:
        assert (target_hooks_dir / name).exists(), f"Missing: {name}"

    # And settings.local.json should declare PreToolUse with matchers
    settings_path = repo / ".claude" / "settings.local.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "PreToolUse" in settings.get("hooks", {}), (
        f"PreToolUse not registered. Got: {list(settings.get('hooks', {}).keys())}"
    )
    pre_tool = settings["hooks"]["PreToolUse"]
    assert isinstance(pre_tool, list)
    assert len(pre_tool) == 3, f"Expected 3 PreToolUse entries, got {len(pre_tool)}"
    # Each entry should have matcher + hooks
    for entry in pre_tool:
        assert "matcher" in entry
        assert "hooks" in entry
        assert isinstance(entry["hooks"], list)
        assert len(entry["hooks"]) >= 1
        assert "command" in entry["hooks"][0]
