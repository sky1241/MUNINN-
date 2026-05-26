"""Hook generator template smoke — catch f-string escaping bugs at install time.

R11 lesson learned (commit f8bb86d fail → 49087f1 hotfix):
PC1 changed `\\n` → `\n` inside the triple-quoted string templates in
muninn_install.py used to GENERATE post_tool_failure_hook.py and
subagent_start_hook.py. The `\n` was interpreted as literal newline at template
parse time → real newline written into the hook file → SyntaxError
"unterminated f-string literal" when CI ran the regenerated hook.

This test re-runs the hook generators and verifies the OUTPUT files compile.
Would have caught f8bb86d before push.
"""
import importlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.expanduser("~/Bureau/MUNINN-/engine/core"))


@pytest.fixture
def temp_repo():
    """Isolated repo path to regenerate hooks into."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / ".claude" / "hooks").mkdir(parents=True)
        yield repo


def _import_muninn_install():
    import muninn_install
    importlib.reload(muninn_install)
    return muninn_install


def test_post_tool_failure_hook_generated_compiles(temp_repo):
    """Regenerated post_tool_failure_hook.py must `py_compile` without error.

    Catches f-string escaping bugs in the template (e.g. R11 \\n vs \n).
    """
    mi = _import_muninn_install()
    engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
    out_path = mi._generate_post_tool_failure_hook(temp_repo, engine_core)
    assert out_path.exists(), f"hook not generated: {out_path}"

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"post_tool_failure_hook.py compile failed: {result.stderr[-300:]}"
    )


def test_subagent_start_hook_generated_compiles(temp_repo):
    """Regenerated subagent_start_hook.py must `py_compile` without error."""
    mi = _import_muninn_install()
    engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
    out_path = mi._generate_subagent_start_hook(temp_repo, engine_core)
    assert out_path.exists(), f"hook not generated: {out_path}"

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"subagent_start_hook.py compile failed: {result.stderr[-300:]}"
    )


def test_generated_hooks_runnable_with_empty_input(temp_repo):
    """Generated hook must accept empty JSON stdin and exit 0 (hook contract)."""
    mi = _import_muninn_install()
    engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
    hook = mi._generate_post_tool_failure_hook(temp_repo, engine_core)

    result = subprocess.run(
        [sys.executable, str(hook)],
        input='{}', capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"hook crashed on empty payload (exit={result.returncode}): {result.stderr[-300:]}"
    )
