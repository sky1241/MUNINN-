"""
CHUNK 4 — Verifie le PostToolUseFailure hook qui auto-feed errors.json.

Pourquoi : aujourd'hui P18 (error/fix pairs) scrappe le transcript apres
coup pour extraire les erreurs. Le hook PostToolUseFailure (Claude Code)
donne l'erreur en temps reel, structuree, avec tool_name + tool_input +
error message + tool_use_id. Auto-feed direct, plus de scraping.

Tests :
1. feed_errors_json sur payload valide cree une entree
2. Schema P18 respecte (error/fix/date)
3. Dedup : meme erreur 2x le meme jour = 1 entree
4. Dedup ne bloque pas erreurs differentes
5. Cap a 500 entries
6. Payload malforme = no-op silencieux
7. _generate_post_tool_failure_hook cree un fichier executable
8. install_hooks enregistre PostToolUseFailure dans settings
9. Le handler subprocess ne crash pas sur stdin valide
10. Le handler subprocess exit 0 toujours
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "post_tool_failure_hook.py"


def _import_hook_module():
    """Import the hook script as a module for direct function testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "post_tool_failure_hook", str(HOOK_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a fake repo with .muninn/ for isolated tests."""
    (tmp_path / ".muninn").mkdir()
    return tmp_path


# ── feed_errors_json (pure function) ─────────────────────────────


def test_feed_creates_entry(tmp_repo):
    mod = _import_hook_module()
    payload = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": "npm test"},
        "error": "Command exited with code 1: test failed",
        "tool_use_id": "toolu_abc123",
    }
    result = mod.feed_errors_json(payload, tmp_repo)
    assert result is True

    errors_path = tmp_repo / ".muninn" / "errors.json"
    assert errors_path.exists()
    data = json.loads(errors_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    entry = data[0]
    assert "error" in entry
    assert "fix" in entry
    assert "date" in entry
    assert "Bash" in entry["error"]
    assert "Command exited" in entry["error"]
    assert entry["fix"] == ""  # filled later by reflect cycle


def test_p18_schema_strict(tmp_repo):
    """Le format doit etre exactement {error, fix, date} — meme cles que P18."""
    mod = _import_hook_module()
    payload = {"tool_name": "Edit", "error": "file not found"}
    mod.feed_errors_json(payload, tmp_repo)

    data = json.loads((tmp_repo / ".muninn" / "errors.json").read_text(encoding="utf-8"))
    entry = data[0]
    assert set(entry.keys()) == {"error", "fix", "date"}, (
        f"Schema drift! Got {set(entry.keys())}"
    )


def test_dedup_same_error_same_day(tmp_repo):
    mod = _import_hook_module()
    payload = {"tool_name": "Bash", "error": "same failure"}
    mod.feed_errors_json(payload, tmp_repo)
    mod.feed_errors_json(payload, tmp_repo)  # should be skipped
    mod.feed_errors_json(payload, tmp_repo)  # also skipped

    data = json.loads((tmp_repo / ".muninn" / "errors.json").read_text(encoding="utf-8"))
    assert len(data) == 1


def test_dedup_does_not_block_distinct_errors(tmp_repo):
    mod = _import_hook_module()
    mod.feed_errors_json({"tool_name": "Bash", "error": "error A"}, tmp_repo)
    mod.feed_errors_json({"tool_name": "Bash", "error": "error B"}, tmp_repo)
    mod.feed_errors_json({"tool_name": "Edit", "error": "error A"}, tmp_repo)

    data = json.loads((tmp_repo / ".muninn" / "errors.json").read_text(encoding="utf-8"))
    assert len(data) == 3


def test_cap_500_entries(tmp_repo):
    mod = _import_hook_module()
    # Pre-populate with 510 entries (oldest -> newest)
    errors_path = tmp_repo / ".muninn" / "errors.json"
    initial = [
        {"error": f"old error {i}", "fix": "", "date": "2025-01-01"}
        for i in range(510)
    ]
    errors_path.write_text(json.dumps(initial), encoding="utf-8")

    payload = {"tool_name": "Bash", "error": "fresh new error"}
    mod.feed_errors_json(payload, tmp_repo)

    data = json.loads(errors_path.read_text(encoding="utf-8"))
    assert len(data) <= 500
    # The fresh entry must be in the result
    assert any("fresh new error" in e["error"] for e in data)
    # The oldest must have been dropped
    assert not any("old error 0" == e.get("error") for e in data)


def test_malformed_payload_no_crash(tmp_repo):
    mod = _import_hook_module()
    # Various malformed inputs
    assert mod.feed_errors_json(None, tmp_repo) is False
    assert mod.feed_errors_json("not a dict", tmp_repo) is False
    assert mod.feed_errors_json({}, tmp_repo) is False
    assert mod.feed_errors_json({"random": "key"}, tmp_repo) is False
    # No errors.json created since nothing was added
    errors_path = tmp_repo / ".muninn" / "errors.json"
    assert not errors_path.exists()


def test_summary_truncated_long_error(tmp_repo):
    mod = _import_hook_module()
    long_error = "x" * 1000
    mod.feed_errors_json({"tool_name": "Bash", "error": long_error}, tmp_repo)
    data = json.loads((tmp_repo / ".muninn" / "errors.json").read_text(encoding="utf-8"))
    assert len(data[0]["error"]) <= 250  # tool name + " | " + 200 max + ...


def test_multiline_error_keeps_first_line_only(tmp_repo):
    mod = _import_hook_module()
    multiline = "first line failure\nsecond line stack trace\nthird line"
    mod.feed_errors_json({"tool_name": "Bash", "error": multiline}, tmp_repo)
    data = json.loads((tmp_repo / ".muninn" / "errors.json").read_text(encoding="utf-8"))
    summary = data[0]["error"]
    assert "first line failure" in summary
    assert "second line" not in summary


# ── _generate_post_tool_failure_hook ─────────────────────────────


def test_generator_creates_file(tmp_path):
    """install_hooks generates a self-contained handler in .claude/hooks/."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    engine_core = REPO_ROOT / "engine" / "core"
    out = muninn._generate_post_tool_failure_hook(repo, engine_core)
    assert out.exists()
    assert out.name == "post_tool_failure_hook.py"
    content = out.read_text(encoding="utf-8")
    assert "def feed_errors_json" in content
    assert "def main" in content
    assert "PostToolUseFailure" in content
    assert "MAX_ENTRIES = 500" in content


def test_generated_handler_runs_via_subprocess(tmp_path):
    """Smoke test : le fichier genere doit etre executable et exit 0."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    engine_core = REPO_ROOT / "engine" / "core"
    hook_file = muninn._generate_post_tool_failure_hook(repo, engine_core)

    payload = {
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": "fake test command"},
        "error": "fake error for subprocess test",
        "cwd": str(repo),
    }

    result = subprocess.run(
        [sys.executable, str(hook_file)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"Hook exit code {result.returncode}, stderr: {result.stderr.decode()}"
    )

    # Verify it actually wrote
    errors_path = repo / ".muninn" / "errors.json"
    assert errors_path.exists()
    data = json.loads(errors_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert "fake error" in data[0]["error"]


def test_generated_handler_silent_on_invalid_stdin(tmp_path):
    """Hook doit exit 0 meme sur stdin invalide (jamais bloquer Claude)."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    hook_file = muninn._generate_post_tool_failure_hook(
        repo, REPO_ROOT / "engine" / "core"
    )

    result = subprocess.run(
        [sys.executable, str(hook_file)],
        input=b"this is not valid JSON {{{",
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0


# ── install_hooks integration ────────────────────────────────────


def test_install_hooks_registers_post_tool_failure(tmp_path):
    """install_hooks doit ajouter PostToolUseFailure au registry."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()

    muninn.install_hooks(repo)

    settings = json.loads(
        (repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    hooks = settings.get("hooks", {})
    assert "PostToolUseFailure" in hooks, (
        f"PostToolUseFailure not registered. Got: {list(hooks.keys())}"
    )
    entries = hooks["PostToolUseFailure"]
    assert isinstance(entries, list) and entries
    cmd = entries[0].get("command", "")
    assert "post_tool_failure_hook.py" in cmd
