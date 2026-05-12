"""
CHUNK MCP C.2 — CI speedup (pytest-xdist + forge_smoke matrix parallel).

The plan: parallelize the validate pytest step via pytest-xdist (-n auto),
and split the forge_smoke shell `for f in ...` loop into a GitHub Actions
strategy.matrix so the 17 modules run in parallel jobs.

These tests pin the structure of .github/workflows/ci.yml + constraints.txt
so a future refactor can't silently un-parallelize the suite.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CONSTRAINTS = REPO_ROOT / "constraints.txt"


def test_c2_pytest_xdist_pinned_in_constraints():
    """pytest-xdist must be pinned in constraints.txt for reproducible CI."""
    text = CONSTRAINTS.read_text(encoding="utf-8")
    assert "pytest-xdist" in text, (
        "pytest-xdist must be pinned in constraints.txt to enable "
        "parallel pytest execution in CI"
    )


def test_c2_pytest_xdist_installed_in_ci():
    """pytest-xdist must be in the `pip install` line in the validate job."""
    text = CI_YML.read_text(encoding="utf-8")
    # We expect pytest-xdist to be installed alongside pytest etc.
    assert "pytest-xdist" in text, (
        "pytest-xdist must be installed in .github/workflows/ci.yml"
    )


def test_c2_pytest_runs_with_dash_n_auto():
    """The pytest step must use `-n auto` (or `-n <number>`) for parallelism."""
    text = CI_YML.read_text(encoding="utf-8")
    # Accept "-n auto", "-n=auto", or explicit worker counts like "-n 4"
    import re
    assert re.search(r"-n\s+(auto|\d+)", text) or "-n=auto" in text, (
        "Pytest must be invoked with -n auto (pytest-xdist parallelism)"
    )


def test_c2_forge_smoke_uses_strategy_matrix():
    """forge_smoke must use strategy.matrix to parallelize across modules."""
    text = CI_YML.read_text(encoding="utf-8")
    # forge_smoke job header + strategy.matrix syntax
    assert "forge_smoke:" in text, "forge_smoke job must exist"
    assert "strategy:" in text, "strategy block must exist in CI"
    assert "matrix:" in text, "strategy.matrix block must exist"


def test_c2_forge_smoke_matrix_has_fail_fast_false():
    """fail-fast: false → all matrix jobs run even if one fails (better debug)."""
    text = CI_YML.read_text(encoding="utf-8")
    assert "fail-fast: false" in text, (
        "forge_smoke matrix should set fail-fast: false to see all module "
        "failures, not abort on first"
    )


def test_c2_forge_smoke_matrix_lists_all_critical_modules():
    """The matrix must list the 17 engine modules forge knows how to props-gen.

    These are the modules with test_props_<name>.py files. Adding a new
    one without updating the matrix would silently drop CI coverage.
    """
    text = CI_YML.read_text(encoding="utf-8")
    # Critical modules that MUST be in the matrix (subset, not exhaustive).
    # If any are missing, forge_smoke regression coverage is reduced.
    required_modules = [
        "muninn_tree",
        "muninn_layers",
        "muninn_feed",
        "mycelium_db",
        "mycelium",
        "_secrets",
        "cube",
        "cube_providers",
        "cube_analysis",
        "sync_backend",
        "_hook_logger",
        "budget_select",
        "dedup",
        "forge_metrics",
        "lang_lexicons",
        "lexicons",
        "sentiment",
    ]
    missing = [m for m in required_modules if m not in text]
    assert not missing, (
        f"forge_smoke matrix is missing required modules: {missing}. "
        f"Each must appear as a matrix entry."
    )


def test_c2_forge_smoke_matrix_runs_one_module_per_job():
    """Each matrix job must invoke `forge --gen-props` on ONE module via the matrix variable.

    The old shell `for f in ...` loop is forbidden — it serializes execution.
    """
    text = CI_YML.read_text(encoding="utf-8")
    # The matrix must use ${{ matrix.<varname> }} in the forge command.
    # Accept module or path as the matrix variable name.
    import re
    assert re.search(r"\$\{\{\s*matrix\.\w+\s*\}\}", text), (
        "forge_smoke must reference the matrix variable (e.g. "
        "${{ matrix.module }}) in the forge invocation"
    )


def test_c2_forge_smoke_no_legacy_shell_for_loop():
    """The old `for f in engine/core/...; do forge --gen-props "$f"; done` pattern is forbidden.

    Detecting it as a string would be brittle. We check that the literal
    "for f in engine/core" doesn't appear (which the legacy pattern used).
    """
    text = CI_YML.read_text(encoding="utf-8")
    assert "for f in engine/core" not in text, (
        "The legacy shell `for f in engine/core/...` loop must be removed — "
        "replaced by strategy.matrix"
    )
