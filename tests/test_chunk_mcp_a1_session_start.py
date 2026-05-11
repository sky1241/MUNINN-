"""
CHUNK MCP A.1 — SessionStart hook auto-bootes root + hot branches.

Pourquoi : sans ce hook, Claude demarre une session avec contexte vide.
Le hook SessionStart permet d'injecter additionalContext au demarrage —
on y met un boot Muninn (root.mn + branches chaudes) pour que la session
attaque deja avec la memoire de la session precedente.

Calque structurel : tests/test_chunk5_subagent_start_hook.py.

Tests behaviouraux (pas source-greppy sauf check de presence) :
1. _generate_session_start_hook cree le fichier
2. Le fichier genere a la structure attendue
3. install_hooks enregistre SessionStart dans settings.local.json
4. Handler subprocess avec source=startup -> JSON valide en sortie
5. Handler subprocess avec source=clear -> additionalContext vide
6. Handler subprocess avec stdin invalide -> exit 0 + JSON empty
7. Output JSON contient hookSpecificOutput.hookEventName == "SessionStart"
8. additionalContext capped a MAX_INJECT_CHARS_SESSION quand contenu trop gros
9. Handler n'invoque PAS muninn boot quand source not in {startup, resume}
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Generator (engine.muninn._generate_session_start_hook) ──────


def test_generator_creates_file(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    out = muninn._generate_session_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )
    assert out.exists()
    assert out.name == "session_start_hook.py"


def test_generated_file_contains_expected_structure(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    out = muninn._generate_session_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )
    content = out.read_text(encoding="utf-8")
    assert "def main" in content
    assert "_emit_empty" in content
    assert "MAX_INJECT_CHARS" in content
    assert "hookSpecificOutput" in content
    assert "SessionStart" in content
    # Source filter must be present (this is the contract)
    assert "startup" in content and "resume" in content


# ── install_hooks integration ────────────────────────────────────


def test_install_hooks_registers_session_start(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()

    muninn.install_hooks(repo)

    settings = json.loads(
        (repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    hooks = settings.get("hooks", {})
    assert "SessionStart" in hooks, (
        f"SessionStart not registered. Got: {list(hooks.keys())}"
    )
    entries = hooks["SessionStart"]
    assert isinstance(entries, list) and entries
    assert "session_start_hook.py" in entries[0].get("command", "")


def test_install_hooks_keeps_subagent_and_other_hooks(tmp_path):
    """install_hooks ne doit pas casser les hooks existants quand on ajoute SessionStart."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_hooks(repo)

    settings = json.loads(
        (repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    hooks = settings.get("hooks", {})
    # All previously-registered hooks must remain
    for required in [
        "UserPromptSubmit",
        "PreCompact",
        "SessionEnd",
        "Stop",
        "PostToolUseFailure",
        "SubagentStart",
        "SessionStart",  # new one
    ]:
        assert required in hooks, f"hook {required!r} missing after install"


# ── Subprocess behaviour ─────────────────────────────────────────


def _generate_in_tmp(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    out = muninn._generate_session_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )
    return repo, out


def test_handler_source_clear_emits_empty_additional_context(tmp_path):
    """source=clear -> hook noop (additionalContext == '')."""
    repo, hook_path = _generate_in_tmp(tmp_path)

    payload = {
        "hook_event_name": "SessionStart",
        "source": "clear",
        "cwd": str(repo),
        "session_id": "test-clear-001",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert data["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_source_compact_emits_empty_additional_context(tmp_path):
    """source=compact -> hook noop (PreCompact already handled compression)."""
    repo, hook_path = _generate_in_tmp(tmp_path)

    payload = {
        "hook_event_name": "SessionStart",
        "source": "compact",
        "cwd": str(repo),
        "session_id": "test-compact-001",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_invalid_json_emits_empty(tmp_path):
    """stdin invalide -> exit 0 + JSON empty (fail-safe)."""
    repo, hook_path = _generate_in_tmp(tmp_path)

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"not-a-json{",
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert data["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_empty_stdin_emits_empty(tmp_path):
    """stdin vide -> exit 0 + JSON empty."""
    repo, hook_path = _generate_in_tmp(tmp_path)

    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=b"",
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_source_startup_with_no_tree_emits_empty(tmp_path):
    """source=startup mais pas de .muninn/tree -> emit empty (fail-safe)."""
    repo, hook_path = _generate_in_tmp(tmp_path)
    # repo has no .muninn/tree directory

    payload = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "cwd": str(repo),
        "session_id": "test-startup-notree",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    # When no tree, hook should fall back to empty additionalContext
    assert data["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_source_startup_with_tree_emits_context(tmp_path):
    """source=startup + .muninn/tree/root.mn present -> additionalContext non-empty."""
    repo, hook_path = _generate_in_tmp(tmp_path)
    tree_dir = repo / ".muninn" / "tree"
    tree_dir.mkdir(parents=True)
    root_content = "P:test_repo|2026-05-11|42L\nF:test_fact_marker_xyz123\nK:python,muninn"
    (tree_dir / "root.mn").write_text(root_content, encoding="utf-8")

    payload = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "cwd": str(repo),
        "session_id": "test-startup-001",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"hook exited non-zero: stderr={result.stderr.decode('utf-8', errors='replace')!r}"
    )
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert ctx != "", "additionalContext should be non-empty when root.mn exists"
    # The injected context should mention the root content or at least confirm
    # boot was attempted (we're tolerant on exact format)
    assert "test_fact_marker_xyz123" in ctx or "test_repo" in ctx or "MUNINN" in ctx.upper()


def test_handler_source_resume_with_tree_emits_context(tmp_path):
    """source=resume same as startup -> boot triggered."""
    repo, hook_path = _generate_in_tmp(tmp_path)
    tree_dir = repo / ".muninn" / "tree"
    tree_dir.mkdir(parents=True)
    (tree_dir / "root.mn").write_text(
        "P:resume_test|2026-05-11|1L\nF:resume_marker", encoding="utf-8"
    )

    payload = {
        "hook_event_name": "SessionStart",
        "source": "resume",
        "cwd": str(repo),
        "session_id": "test-resume-001",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    assert data["hookSpecificOutput"]["additionalContext"] != ""


def test_handler_truncates_oversized_context(tmp_path):
    """root.mn enormement gros -> additionalContext capped a MAX_INJECT_CHARS."""
    repo, hook_path = _generate_in_tmp(tmp_path)
    tree_dir = repo / ".muninn" / "tree"
    tree_dir.mkdir(parents=True)
    # Write a 200KB root.mn (much larger than MAX_INJECT_CHARS = 40_000)
    big_content = "X" * 200_000
    (tree_dir / "root.mn").write_text(big_content, encoding="utf-8")

    payload = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "cwd": str(repo),
        "session_id": "test-big-001",
    }
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout.decode("utf-8"))
    ctx = data["hookSpecificOutput"]["additionalContext"]
    # MAX_INJECT_CHARS for session = 40_000 (larger than subagent's 20K but bounded).
    # Allow some headroom for the wrapper text.
    assert len(ctx) <= 45_000, (
        f"additionalContext not truncated: got {len(ctx)} chars"
    )


def test_handler_exit_code_always_zero(tmp_path):
    """Hook MUST exit 0 even on garbage stdin (no blocking the session)."""
    repo, hook_path = _generate_in_tmp(tmp_path)

    for stdin_bytes in [b"", b"{", b'{"source": null}', b"\x00\xff\xfe"]:
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            input=stdin_bytes,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"hook exited non-zero on input {stdin_bytes!r}: "
            f"stderr={result.stderr.decode('utf-8', errors='replace')!r}"
        )
