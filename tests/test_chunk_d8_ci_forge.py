"""CHUNK D8 — proposed CI step: forge --gen-props matrix per module.

Same constraint as C12: the agent token cannot edit
.github/workflows/ci.yml without the `workflow` scope, so the diff
lives in docs/CI_PROPOSED_D8.md and Sky merges it manually. These
tests pytest.skip() until the diff lands.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D8
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
PROPOSED = REPO / "docs" / "CI_PROPOSED_D8.md"


def _ci_text() -> str:
    return CI.read_text() if CI.exists() else ""


def _forge_step_merged() -> bool:
    src = _ci_text()
    return "forge_smoke" in src and "forge.py --gen-props" in src


def test_proposed_doc_exists():
    assert PROPOSED.exists(), (
        "Missing docs/CI_PROPOSED_D8.md — see CHUNK D8"
    )


def test_proposed_doc_lists_engine_core_modules():
    src = PROPOSED.read_text()
    # The diff must explicitly run forge on at least these critical modules
    must_list = [
        "muninn_tree", "muninn_layers", "muninn_feed",
        "mycelium_db", "mycelium",
    ]
    for m in must_list:
        assert m in src, f"Proposed CI doc must reference engine/core/{m}.py"


def test_proposed_doc_runs_pytest_after():
    """The proposed CI step must also execute the generated props."""
    src = PROPOSED.read_text()
    assert "test_props_*.py" in src or "test_props_" in src


def test_ci_runs_forge_smoke():
    if not _forge_step_merged():
        pytest.skip("CI workflow change not merged yet (D8 doc)")
    assert "forge_smoke" in _ci_text()


def test_ci_calls_forge_gen_props():
    if not _forge_step_merged():
        pytest.skip("CI workflow change not merged yet (D8 doc)")
    assert "forge.py --gen-props" in _ci_text()


def test_ci_runs_generated_props():
    if not _forge_step_merged():
        pytest.skip("CI workflow change not merged yet (D8 doc)")
    assert "test_props_" in _ci_text()
