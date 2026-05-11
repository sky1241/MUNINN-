"""
CHUNK MCP A.4 — Test E2E "from scratch" pip install + muninn init + doctor.

Pin de Phase A complete : prouve que `pip install -e <repo>` dans un venv
vierge puis `muninn init` produit un repo Muninn fonctionnel avec :
  - .muninn/ + tree + mycelium scaffold
  - .claude/hooks/ avec SessionStart hook (chunk A.1)
  - .claude/settings.local.json avec hooks registered (A.1 SessionStart inclus)
  - muninn doctor returns ALL GREEN

Le test prend ~60-120s (pip install -e lent) -> opt-in via MUNINN_RUN_E2E=1,
fixture session-scope pour amortir l'install entre les 7 cases.

Linux-only pour ce chunk (Phase D adressera Windows + macOS).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skip the whole module unless the user opts in. pip install -e takes 60-120s ;
# we don't want to slow down every PR by that much.
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("MUNINN_RUN_E2E") != "1",
        reason="E2E pip-install test — set MUNINN_RUN_E2E=1 to opt in (~60-120s)",
    ),
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="E2E pin is Linux-only for this chunk (A.4) ; Phase D adds Win/macOS",
    ),
]


# ── Session-scoped fixture: 1 venv + pip install amortized across all tests ──


@pytest.fixture(scope="module")
def venv_with_muninn(tmp_path_factory):
    """Create a vierge venv and pip install -e the source repo.

    Yields (venv_dir, venv_python, venv_muninn_bin).
    """
    venv_dir = tmp_path_factory.mktemp("e2e_venv")

    # 1. Create venv
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True, timeout=60,
    )
    venv_py = venv_dir / "bin" / "python"
    venv_muninn = venv_dir / "bin" / "muninn"
    assert venv_py.exists(), f"venv python missing: {venv_py}"

    # 2. pip install -e <repo source>[tokens]
    # tiktoken is required at runtime for count_tokens (used by every compression
    # layer) — doctor marks its absence as FAIL. We install the [tokens] extra so
    # the test mirrors a real user install (`pip install muninn-memory[tokens]`).
    result = subprocess.run(
        [str(venv_py), "-m", "pip", "install", "--quiet", "-e",
         f"{REPO_ROOT}[tokens]"],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        pytest.fail(
            f"pip install -e failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout[-500:]}\n"
            f"stderr: {result.stderr[-500:]}"
        )

    # 3. Verify the entry point was created
    assert venv_muninn.exists(), (
        f"entry point `muninn` missing after pip install: {venv_muninn}"
    )

    yield venv_dir, venv_py, venv_muninn


@pytest.fixture(scope="module")
def initialized_repo(venv_with_muninn, tmp_path_factory):
    """Create a tmp repo and run `muninn init` inside it.

    Yields the tmp_repo Path. Session-scoped so all init-dependent tests
    reuse the same initialized repo.
    """
    venv_dir, venv_py, venv_muninn = venv_with_muninn

    tmp_repo = tmp_path_factory.mktemp("e2e_repo")
    (tmp_repo / "README.md").write_text("Test repo for muninn E2E init", encoding="utf-8")

    result = subprocess.run(
        [str(venv_muninn), "init"],
        cwd=str(tmp_repo),
        env={**os.environ, "MUNINN_SKIP_INTEGRITY": "1"},
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            f"muninn init failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout[-500:]}\n"
            f"stderr: {result.stderr[-500:]}"
        )

    yield tmp_repo


# ── Behavioural tests ────────────────────────────────────────


def test_venv_and_pip_install_succeed(venv_with_muninn):
    """pip install -e produces a working venv with muninn entry point."""
    venv_dir, venv_py, venv_muninn = venv_with_muninn
    assert venv_py.exists()
    assert venv_muninn.exists()
    # Smoke: --help exits 0 (no real command, just print usage)
    r = subprocess.run(
        [str(venv_muninn), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    # argparse exits 0 on --help. Some Python versions write to stdout, some to stderr.
    assert r.returncode == 0, (
        f"muninn --help failed (exit {r.returncode}): "
        f"stdout={r.stdout[-200:]!r} stderr={r.stderr[-200:]!r}"
    )


def test_muninn_init_creates_dot_muninn_layout(initialized_repo):
    """init creates .muninn/ with tree + mycelium."""
    repo = initialized_repo
    muninn_dir = repo / ".muninn"
    assert muninn_dir.exists() and muninn_dir.is_dir(), (
        f".muninn/ missing in {repo}"
    )
    # Either tree.json or memory/tree.json must exist
    tree_paths = [
        muninn_dir / "tree" / "root.mn",
        muninn_dir / "tree.json",
        repo / "memory" / "tree.json",
    ]
    assert any(p.exists() for p in tree_paths), (
        f"No tree found at any of: {[str(p) for p in tree_paths]}"
    )


def test_muninn_init_installs_hooks(initialized_repo):
    """init writes .claude/settings.local.json with the expected hooks (A.1 included)."""
    repo = initialized_repo
    settings = repo / ".claude" / "settings.local.json"
    assert settings.exists(), f"settings.local.json missing: {settings}"
    data = json.loads(settings.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    # Hooks registered before A.1
    required = ["UserPromptSubmit", "PreCompact", "SessionEnd", "Stop",
                "PostToolUseFailure", "SubagentStart"]
    for h in required:
        assert h in hooks, f"hook {h!r} missing. Got: {list(hooks.keys())}"
    # Chunk A.1: SessionStart hook must also be registered
    assert "SessionStart" in hooks, (
        f"SessionStart hook (chunk A.1) missing in fresh init. "
        f"Got: {list(hooks.keys())}"
    )


def test_session_start_hook_script_present(initialized_repo):
    """The .claude/hooks/session_start_hook.py file is created by init."""
    repo = initialized_repo
    hook = repo / ".claude" / "hooks" / "session_start_hook.py"
    assert hook.exists(), f"session_start_hook.py missing: {hook}"
    content = hook.read_text(encoding="utf-8")
    # Spot-check the structure (calque test_chunk_mcp_a1)
    assert "def main" in content
    assert "hookSpecificOutput" in content
    assert "SessionStart" in content


def test_muninn_doctor_all_green(venv_with_muninn, initialized_repo):
    """`muninn doctor` runs in the fresh repo and reports ALL GREEN (fail count = 0)."""
    _, venv_py, venv_muninn = venv_with_muninn
    repo = initialized_repo
    r = subprocess.run(
        [str(venv_muninn), "doctor"],
        cwd=str(repo),
        env={**os.environ, "MUNINN_SKIP_INTEGRITY": "1"},
        capture_output=True, text=True, timeout=60,
    )
    # doctor must exit 0 when no FAIL (WARN is tolerated)
    assert r.returncode == 0, (
        f"muninn doctor failed (exit {r.returncode}):\n"
        f"stdout: {r.stdout[-800:]}\n"
        f"stderr: {r.stderr[-400:]}"
    )
    # The output should contain a clear green signal
    output = r.stdout + r.stderr
    green_markers = ["ALL GREEN", "all green", "0 FAIL", "0 fail"]
    assert any(m in output for m in green_markers), (
        f"doctor output missing ALL GREEN signal. Last 500 chars:\n{output[-500:]}"
    )


def test_install_cron_subcommand_available(venv_with_muninn):
    """install-cron sub-command (chunk A.3) is registered in the CLI."""
    _, venv_py, venv_muninn = venv_with_muninn
    # `muninn install-cron --help` would print usage; we just check that the
    # subcommand parses (no "invalid choice" error).
    r = subprocess.run(
        [str(venv_muninn), "install-cron", "--repo", "/tmp/nonexistent_repo_e2e"],
        capture_output=True, text=True, timeout=30,
    )
    # We expect either:
    # - exit 1 with "is not a Muninn repo" (path doesn't exist) -> command exists
    # - exit 0 with "skipped_no_systemd" / "installed" -> command worked
    # What we MUST NOT see: argparse "invalid choice: 'install-cron'" error.
    assert "invalid choice" not in (r.stdout + r.stderr).lower(), (
        f"install-cron not registered as a valid subcommand:\n"
        f"stdout: {r.stdout[-300:]}\nstderr: {r.stderr[-300:]}"
    )


def test_help_lists_phase_a_commands(venv_with_muninn):
    """`muninn --help` mentions init, doctor, install-cron — anti-regression."""
    _, venv_py, venv_muninn = venv_with_muninn
    r = subprocess.run(
        [str(venv_muninn), "--help"],
        capture_output=True, text=True, timeout=30,
    )
    combined = r.stdout + r.stderr
    for cmd in ["init", "doctor", "install-cron"]:
        assert cmd in combined, (
            f"`muninn --help` does not mention {cmd!r}. Output:\n{combined[-500:]}"
        )
