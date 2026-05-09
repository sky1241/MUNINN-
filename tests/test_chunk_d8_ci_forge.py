"""CHUNK D8 — CI step: forge --gen-props matrix per module.

H4.2 (2026-05-09): the workflow IS merged. Tests no longer skip; they
verify the forge_smoke job is present and calls forge --gen-props.

Post-H1 (2026-05-09) note: the internal forge.py was deleted, the PyPI
binary `forge` is now the source of truth, so we accept both spellings
for `forge[.py] --gen-props` to keep older branches green during transition.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D8
"""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
PROPOSED = REPO / "docs" / "CI_PROPOSED_D8.md"


def _ci_text() -> str:
    return CI.read_text() if CI.exists() else ""


def test_proposed_doc_exists():
    assert PROPOSED.exists(), (
        "Missing docs/CI_PROPOSED_D8.md — see CHUNK D8"
    )


def test_proposed_doc_lists_engine_core_modules():
    src = PROPOSED.read_text()
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
    assert "forge_smoke" in _ci_text()


def test_ci_calls_forge_gen_props():
    src = _ci_text()
    assert "forge --gen-props" in src or "forge.py --gen-props" in src


def test_ci_runs_generated_props():
    assert "test_props_" in _ci_text()
