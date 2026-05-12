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
