"""CHUNK C12 — CI runs standard pytest collection.

Pre-fix: ci.yml had only inline `python3 -` heredoc scripts that
sanity-checked individual subsystems. The pytest suite (2300+ tests)
was never collected by CI. New tests added by Phase A/B/C didn't
gate merges.

Fix: add a `pytest` job that runs `pytest tests/` with `-m "not slow"`
and ignores heavy UI / real-API directories. Also adds explicit
`permissions: contents: read` (least privilege).

H4.1 (2026-05-09): the workflow IS merged (commit bf3858a + this commit
adds the missing C12 bits — permissions, -m "not slow", real-API env).
The skip-once-not-merged gate is therefore retired.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C12
"""
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
PROPOSED_DOC = REPO / "docs" / "CI_PROPOSED_C12.md"


def _ci_text() -> str:
    return CI.read_text() if CI.exists() else ""


def test_ci_workflow_exists():
    assert CI.exists()


def test_proposed_doc_exists():
    """The original diff doc kept as historical record."""
    assert PROPOSED_DOC.exists(), (
        "Missing docs/CI_PROPOSED_C12.md (historical workflow diff)"
    )


def test_ci_has_explicit_permissions():
    src = _ci_text()
    assert "permissions:" in src and "contents: read" in src


def test_ci_runs_pytest():
    assert "pytest tests/" in _ci_text() or "pytest tests" in _ci_text()


def test_ci_skips_slow_marker():
    src = _ci_text()
    assert '-m "not slow"' in src or "-m 'not slow'" in src


def test_ci_uses_constraints_file():
    assert "constraints.txt" in _ci_text()


def test_ci_disables_real_api_tests():
    assert "MUNINN_RUN_REAL_API_TESTS" in _ci_text()
