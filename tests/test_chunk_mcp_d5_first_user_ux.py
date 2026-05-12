"""
CHUNK MCP D.5 — First-user UX polish + examples gallery.

Three surfaces improved for the fresh `pip install muninn-memory` user:

1. examples/ directory — 2-3 concrete runnable scripts so a new user can
   `cd examples && python3 quickstart_local.py` and see something happen.

2. docs/QUICKSTART.md — new "5-second install (from PyPI)" section at
   the top showing `pip install muninn-memory[all]` flow. The current
   QUICKSTART starts with `git clone`, which is dev-mode only.

3. muninn doctor — 3 new checks for pip-install health:
   - console scripts importable (catches the BUG-091 shim regression)
   - engine.core package shipped (regression test for D.1 fix)
   - mcp package availability (separate from anthropic check)
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
QUICKSTART = REPO_ROOT / "docs" / "QUICKSTART.md"
DOCTOR_PY = REPO_ROOT / "engine" / "core" / "muninn_tree_doctor.py"


def test_d5_examples_dir_exists():
    assert EXAMPLES.exists() and EXAMPLES.is_dir(), (
        "examples/ dir must exist with runnable scripts for first-time users"
    )


def test_d5_examples_has_readme():
    assert (EXAMPLES / "README.md").exists(), (
        "examples/README.md should index the examples + explain when to use each"
    )


def test_d5_examples_has_runnable_scripts():
    """At least 2 .py files in examples/, each starts with a docstring."""
    scripts = sorted(EXAMPLES.glob("*.py"))
    assert len(scripts) >= 2, (
        f"Need at least 2 example scripts, found {len(scripts)}"
    )
    for s in scripts:
        text = s.read_text(encoding="utf-8")
        assert text.startswith('"""') or text.startswith("'''"), (
            f"{s.name}: must start with a docstring explaining what it does"
        )


def test_d5_examples_scripts_parseable():
    """Every example script must at least parse as valid Python."""
    import ast
    for s in EXAMPLES.glob("*.py"):
        try:
            ast.parse(s.read_text(encoding="utf-8"))
        except SyntaxError as e:
            pytest.fail(f"{s.name}: syntax error {e}")


def test_d5_examples_scripts_run_without_attribute_errors(tmp_path):
    """E.2 (2026-05-12): every example script must RUN end-to-end without
    AttributeError / NameError / ImportError-for-required-deps.

    Catches the regression we hit in D.5 where mcp_recall_demo.py called
    `mcp_server.tree_get_root(...)` — a function that doesn't exist at the
    module level (it lives inside create_server() via @app.tool() decorator).
    Pre-E.2, only ast.parse() was tested → bug shipped silently.

    Strategy: subprocess.run each example with MUNINN_DEMO_REPO pointing at
    an initialized tmp_path repo. Allow ImportError-for-mcp-extras as a
    skip signal (the example handles it gracefully with sys.exit(1)).
    """
    import os
    import subprocess
    import sys

    # Initialize tmp_path so the demo can find a .muninn/ dir
    env = os.environ.copy()
    env["MUNINN_DEMO_REPO"] = str(tmp_path)
    init_r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "engine" / "core" / "muninn.py"), "init"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
        env={**env, "PYTHONPATH": str(REPO_ROOT / "engine" / "core")},
    )
    assert init_r.returncode == 0, f"setup failed: {init_r.stderr}"

    failures = []
    for s in sorted(EXAMPLES.glob("*.py")):
        r = subprocess.run(
            [sys.executable, str(s)],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        out = r.stdout + r.stderr
        # AttributeError / NameError = a real bug (missing module attribute).
        # ImportError specifically for the mcp/anthropic/tiktoken extras = an
        # opt-in dep absent in CI — we accept those because the script handles
        # them with a helpful "pip install [mcp]" message and exit(1).
        if "AttributeError" in out or "NameError" in out:
            failures.append(f"{s.name}: {out[-300:]}")
        elif r.returncode != 0:
            # Other non-zero exit: accept if it's a documented graceful exit
            # (the script printed a clear "install with [mcp]" hint).
            if "pip install" in out and "muninn-memory[" in out:
                continue  # acceptable graceful failure
            # Otherwise treat as a real crash
            if "Traceback" in out:
                failures.append(f"{s.name} crashed: {out[-300:]}")

    assert not failures, (
        "Example scripts have runtime bugs (E.2 strengthened test):\n  "
        + "\n  ".join(failures)
    )


def test_d5_quickstart_has_pip_install_section():
    """A 'pip install muninn-memory' section must be in the first 100 lines."""
    text = QUICKSTART.read_text(encoding="utf-8")
    lines = text.splitlines()
    head = "\n".join(lines[:100])
    assert "pip install muninn-memory" in head, (
        "QUICKSTART.md should show `pip install muninn-memory` in the first 100 lines"
    )


def test_d5_quickstart_links_examples():
    """QUICKSTART should point users to examples/ for runnable code."""
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "examples/" in text or "examples " in text, (
        "QUICKSTART should reference examples/ directory"
    )


def test_d5_doctor_checks_console_scripts():
    """doctor() must check that all console script entry points resolve."""
    text = DOCTOR_PY.read_text(encoding="utf-8")
    assert "console_script" in text.lower() or "muninn._engine" in text, (
        "doctor() should verify console script entry points are importable"
    )


def test_d5_doctor_checks_engine_package_shipped():
    """doctor() must check that engine.core is importable from the install."""
    text = DOCTOR_PY.read_text(encoding="utf-8")
    assert "engine.core" in text or "engine_package_shipped" in text, (
        "doctor() should verify engine.core package is importable "
        "(regression check for D.1 packaging fix)"
    )


def test_d5_doctor_checks_mcp_extra():
    """doctor() must surface mcp package status separately from anthropic."""
    text = DOCTOR_PY.read_text(encoding="utf-8")
    assert "import mcp" in text or "'mcp'" in text or "muninn-memory[mcp]" in text, (
        "doctor() should check mcp package availability for muninn-mcp script"
    )


def test_d5_doctor_runs_to_completion_in_clean_env(tmp_path):
    """Sanity: doctor() runs and produces output even in a tmp_path with no .muninn/."""
    import os
    cmd = [sys.executable, str(REPO_ROOT / "engine" / "core" / "muninn.py"), "doctor"]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "engine" / "core") + ":" + env.get("PYTHONPATH", "")
    r = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True, text=True, timeout=60, env=env)
    assert "MUNINN DOCTOR" in r.stdout or "MUNINN DOCTOR" in r.stderr, (
        f"doctor should print its header. stdout={r.stdout[:500]} stderr={r.stderr[:500]}"
    )
