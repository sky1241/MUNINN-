"""
CHUNK 5 — Verifie le SubagentStart hook qui inject le boot Muninn dans les sub-agents.

Pourquoi : sans ce hook, les sub-agents (Explore, Plan, custom) bootent vides.
Le hook SubagentStart permet d'injecter additionalContext dans le contexte du
sub-agent des son spawn — on y met un boot Muninn allege (cap ~5K tokens) pour
que le sub-agent ait acces a la racine + branches pertinentes.

Tests :
1. _generate_subagent_start_hook cree un fichier
2. Le fichier genere a la structure attendue
3. install_hooks enregistre SubagentStart dans settings
4. Handler subprocess avec payload valide -> JSON valide en sortie
5. Handler subprocess avec stdin invalide -> exit 0 + JSON empty additionalContext
6. Handler exit 0 toujours
7. Output JSON contient hookSpecificOutput.hookEventName = "SubagentStart"
8. Output JSON contient additionalContext (string)
9. additionalContext capped a MAX_INJECT_CHARS quand le boot est gros
10. Format hookSpecificOutput strict (3 cles attendues)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Generator (engine.muninn._generate_subagent_start_hook) ──────


def test_generator_creates_file(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    out = muninn._generate_subagent_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )
    assert out.exists()
    assert out.name == "subagent_start_hook.py"


def test_generated_file_contains_expected_structure(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    out = muninn._generate_subagent_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )
    content = out.read_text(encoding="utf-8")
    assert "def main" in content
    assert "_emit_empty" in content
    assert "MAX_INJECT_CHARS" in content
    assert "hookSpecificOutput" in content
    assert "SubagentStart" in content


# ── install_hooks integration ────────────────────────────────────


def test_install_hooks_registers_subagent_start(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()

    muninn.install_hooks(repo)

    settings = json.loads(
        (repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    hooks = settings.get("hooks", {})
    assert "SubagentStart" in hooks, (
        f"SubagentStart not registered. Got: {list(hooks.keys())}"
    )
    entries = hooks["SubagentStart"]
    assert isinstance(entries, list) and entries
    assert "subagent_start_hook.py" in entries[0].get("command", "")


def test_install_hooks_keeps_all_other_hooks(tmp_path):
    """install_hooks ne doit pas casser les hooks existants."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    muninn.install_hooks(repo)

    settings = json.loads(
        (repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")
    )
    hooks = set(settings.get("hooks", {}).keys())
    expected = {
        "UserPromptSubmit",
        "PreCompact",
        "SessionEnd",
        "Stop",
        "PostToolUseFailure",
        "SubagentStart",
    }
    missing = expected - hooks
    assert not missing, f"Hooks missing after install: {missing}"


# ── Subprocess smoke tests ───────────────────────────────────────


def _generate_handler(tmp_path):
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    return repo, muninn._generate_subagent_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )


def test_handler_subprocess_valid_payload(tmp_path):
    repo, hook = _generate_handler(tmp_path)
    payload = {
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-test-001",
        "agent_type": "Explore",
        "cwd": str(repo),
    }
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"Hook exit code {result.returncode}, stderr: {result.stderr.decode()}"
    )
    # stdout must be valid JSON
    out = json.loads(result.stdout.decode("utf-8"))
    assert "hookSpecificOutput" in out
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "SubagentStart"
    assert "additionalContext" in spec
    assert isinstance(spec["additionalContext"], str)


def test_handler_subprocess_invalid_stdin(tmp_path):
    """Handler exit 0 + emits empty JSON sur stdin invalide."""
    repo, hook = _generate_handler(tmp_path)
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=b"this is not JSON {{{",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_subprocess_empty_stdin(tmp_path):
    repo, hook = _generate_handler(tmp_path)
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=b"",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    # Should emit empty additionalContext via _emit_empty
    out = json.loads(result.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_subprocess_no_engine_dir(tmp_path):
    """Si engine/core et muninn/ n'existent pas, fail-safe vers empty."""
    repo, hook = _generate_handler(tmp_path)
    payload = {
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-test",
        "agent_type": "Explore",
        "cwd": str(tmp_path / "totally_other_dir"),  # no engine here
    }
    (tmp_path / "totally_other_dir").mkdir()
    result = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["additionalContext"] == ""


def test_handler_truncates_oversized_boot(tmp_path, monkeypatch):
    """Si muninn.boot retourne un texte > MAX_INJECT_CHARS, il doit etre tronque.

    On evite d'appeler le vrai boot (lent sur gros tree) en testant le contrat
    de _truncate_with_marker importe directement depuis le fichier genere.
    """
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    hook_file = muninn._generate_subagent_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )

    # Import the generated hook as a module to access _truncate_with_marker
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "generated_subagent_hook", str(hook_file)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Tiny text passes unchanged
    short = "tiny boot output"
    assert mod._truncate_with_marker(short, 100) == short

    # Oversized text gets truncated with marker
    long_text = "x" * 50000
    capped = mod._truncate_with_marker(long_text, 1000)
    assert len(capped) <= 1000
    assert "truncated" in capped.lower()


def test_handler_format_with_mocked_boot(tmp_path):
    """Verify the hook output JSON format using a deterministic muninn.boot stub.

    This avoids depending on the real boot's performance characteristics
    while still validating the full subprocess pipeline.
    """
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    import muninn

    repo = tmp_path / "fake_repo"
    repo.mkdir()
    # Create minimal fake engine/core inside fake repo with a stub muninn.py
    fake_engine = repo / "engine" / "core"
    fake_engine.mkdir(parents=True)
    stub = fake_engine / "muninn.py"
    stub.write_text(
        "from pathlib import Path\n"
        "_REPO_PATH = None\n"
        "def _refresh_tree_paths():\n"
        "    pass\n"
        "def boot(query=''):\n"
        "    return f'STUB boot result for query={query!r}'\n",
        encoding="utf-8",
    )

    hook_file = muninn._generate_subagent_start_hook(
        repo, REPO_ROOT / "engine" / "core"
    )

    payload = {
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-stub",
        "agent_type": "Explore",
        "cwd": str(repo),
    }
    result = subprocess.run(
        [sys.executable, str(hook_file)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"Hook stderr: {result.stderr.decode()}"
    )
    out = json.loads(result.stdout.decode("utf-8"))
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "SubagentStart"
    ctx = spec["additionalContext"]
    assert "MUNINN BOOT" in ctx
    assert "Explore" in ctx
    assert "STUB boot result" in ctx
    assert "query='Explore'" in ctx
