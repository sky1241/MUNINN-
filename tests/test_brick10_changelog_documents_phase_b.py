"""PHASE B BRICK 10 — pin CHANGELOG.md documenting Phase B + battle plan."""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"


@pytest.fixture(scope="module")
def text():
    return CHANGELOG.read_text(encoding="utf-8")


def test_changelog_exists(text):
    assert text


def test_changelog_has_phase_b_section(text):
    assert "## Phase B" in text or "Phase B (2026" in text


def test_changelog_has_anti_bullshit_section(text):
    assert "ANTI_BULLSHIT_BATTLE_PLAN" in text


def test_changelog_lists_all_phase_b_commits(text):
    """Each of the 10 phase B commits must be referenced by hash."""
    expected_hashes = [
        "11c8c97",  # brick 1 lexicons
        "d158363",  # brick 2 dedup
        "586dfa1",  # brick 3 budget_select
        "6e9bd40",  # brick 4 wire lexicons
        "86885dc",  # brick 5 wire dedup
        "fa1be1b",  # brick 6 wire budget initial
        "2765f1b",  # brick 6 fix + brick 7 benchmark
        "5ffd2e1",  # battle plan
        "cd8f51b",  # brick 8 wire RULE 4
        "f2d25b6",  # brick 9 winter tree
    ]
    missing = [h for h in expected_hashes if h not in text]
    assert not missing, f"missing commit hashes in CHANGELOG: {missing}"


def test_changelog_credits_papers(text):
    assert "BudgetMem" in text
    assert "2511.04919" in text


def test_changelog_lists_real_results(text):
    """The benchmark numbers must be in the doc."""
    assert "x8" in text or "x9" in text
    assert "PHASE_B_RESULTS" in text


def test_changelog_engine_summary_includes_new_files(text):
    """The engine summary line at the top must mention the 3 new modules."""
    # Find the Engine: line
    for line in text.split("\n"):
        if line.startswith("Engine:"):
            assert "lexicons.py" in line
            assert "dedup.py" in line
            assert "budget_select.py" in line
            return
    pytest.fail("no 'Engine:' summary line found")


def test_changelog_lists_battle_plan_defenses(text):
    """The 10 defenses must be enumerated in the changelog summary."""
    # At least one of the canonical defenses must be quoted
    needles = [
        "No claim without command output",
        "command output",
        "1 fix = 1 commit = 1 push",
        "verification questions",
    ]
    matches = sum(1 for n in needles if n in text)
    assert matches >= 2, (
        f"changelog summary of battle plan too thin: {matches}/4 needles found"
    )
