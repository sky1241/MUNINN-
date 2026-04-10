"""PHASE B BRICK 9 — pin WINTER_TREE.md documenting the 3 new modules.

WINTER_TREE.md is the technical nav map Sky and Claude rely on to find
where things are in the codebase. If a new module is added but not
documented here, it's invisible — and the next session will re-scan
the entire engine/core/ to find it, wasting context.

This test fails if anyone removes the lexicons / dedup / budget_select
sections, or if the Phase B wirings table is gone.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WT = REPO_ROOT / "WINTER_TREE.md"


@pytest.fixture(scope="module")
def text():
    return WT.read_text(encoding="utf-8")


def test_winter_tree_exists(text):
    assert text


def test_winter_tree_has_lexicons_section(text):
    assert "## engine/core/lexicons.py" in text, (
        "WINTER_TREE missing lexicons.py section — brick 1 invisible to nav"
    )
    # Must mention the key constants
    assert "MIT_FILLERS_EN" in text
    assert "L2_TIER1_SAFE" in text
    assert "DANGEROUS_NEVER_ADD" in text


def test_winter_tree_has_dedup_section(text):
    assert "## engine/core/dedup.py" in text, (
        "WINTER_TREE missing dedup.py section — brick 2 invisible to nav"
    )
    assert "Charikar" in text or "SimHash" in text
    assert "dedup_lines" in text
    assert "hamming_distance" in text


def test_winter_tree_has_budget_select_section(text):
    assert "## engine/core/budget_select.py" in text, (
        "WINTER_TREE missing budget_select.py — brick 3 invisible to nav"
    )
    assert "BudgetMem" in text
    assert "score_chunk" in text
    assert "select_chunks" in text
    assert "has_fact_span" in text


def test_winter_tree_has_phase_b_wirings_table(text):
    """The Phase B Wirings table inside muninn_layers.py section
    must list the 3 wirings (lexicons, dedup, budget)."""
    assert "Phase B Wirings" in text
    assert "_LEXICONS_TIER1_PATTERNS" in text
    assert "_dedup_body_lines" in text
    assert "_l12_budget_pass" in text


def test_winter_tree_credits_paper(text):
    """The arxiv paper for BudgetMem must be cited."""
    assert "2511.04919" in text


def test_winter_tree_mentions_real_results(text):
    """The empirical headline numbers must be in the doc so future
    Claude doesn't have to re-discover them."""
    assert "PHASE_B_RESULTS.md" in text or "x8" in text or "x9" in text


def test_winter_tree_size_grew_after_phase_b(text):
    """Sanity floor: WINTER_TREE was already 600+ lines before Phase B,
    must be larger now."""
    n = text.count("\n")
    assert n > 700, f"WINTER_TREE shrunk: {n} lines (expected > 700)"
