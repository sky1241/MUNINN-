"""CHUNK C12 — CI runs standard pytest collection.

Pre-fix: ci.yml had only inline `python3 -` heredoc scripts that
sanity-checked individual subsystems. The pytest suite (2200+ tests)
was never collected by CI. New tests added by Phase A/B/C didn't
gate merges.

Fix: add a `pytest` job before `validate` that runs `pytest tests/`
with `-m "not slow"` and ignores the heavy UI / real-API directories.
Also adds explicit `permissions: contents: read` (least privilege).

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C12
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
PROPOSED_DOC = REPO / "docs" / "CI_PROPOSED_C12.md"


def _ci_text() -> str:
    return CI.read_text() if CI.exists() else ""


def _workflow_change_merged() -> bool:
    """Returns True once the CHUNK C12 changes are present in ci.yml.

    The agent that ships this fix can't modify .github/workflows/
    without the `workflow` GitHub scope, so the YAML diff lives in
    docs/CI_PROPOSED_C12.md and Sky merges it manually with a
    properly-scoped token.
    """
    src = _ci_text()
    return ("permissions:" in src
            and "contents: read" in src
            and "pytest tests/" in src
            and "constraints.txt" in src)


def test_ci_workflow_exists():
    assert CI.exists()


def test_proposed_doc_exists():
    """The diff to apply must be committed even if the workflow isn't yet."""
    assert PROPOSED_DOC.exists(), (
        "Missing docs/CI_PROPOSED_C12.md (the workflow diff for Sky to apply)"
    )


def test_ci_has_explicit_permissions():
    if not _workflow_change_merged():
        pytest.skip("workflow change not merged yet (CHUNK C12 doc)")
    src = _ci_text()
    assert "permissions:" in src and "contents: read" in src


def test_ci_runs_pytest():
    if not _workflow_change_merged():
        pytest.skip("workflow change not merged yet (CHUNK C12 doc)")
    assert "pytest tests/" in _ci_text() or "pytest tests" in _ci_text()


def test_ci_skips_slow_marker():
    if not _workflow_change_merged():
        pytest.skip("workflow change not merged yet (CHUNK C12 doc)")
    src = _ci_text()
    assert '-m "not slow"' in src or "-m 'not slow'" in src


def test_ci_uses_constraints_file():
    if not _workflow_change_merged():
        pytest.skip("workflow change not merged yet (CHUNK C12 doc)")
    assert "constraints.txt" in _ci_text()


def test_ci_disables_real_api_tests():
    if not _workflow_change_merged():
        pytest.skip("workflow change not merged yet (CHUNK C12 doc)")
    assert "MUNINN_RUN_REAL_API_TESTS" in _ci_text()
