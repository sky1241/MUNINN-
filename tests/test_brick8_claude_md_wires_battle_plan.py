"""PHASE B BRICK 8 — pin the wiring of ANTI_BULLSHIT_BATTLE_PLAN.md
into CLAUDE.md.

The battle plan only works if every Claude session reads it at boot.
Boot loads CLAUDE.md verbatim. Therefore CLAUDE.md MUST contain a
direct reference to the battle plan and a copy of its core rule.

This test fails if anyone removes RULE 4, the sandwich entry, or the
relative path to docs/ANTI_BULLSHIT_BATTLE_PLAN.md.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
BATTLE_PLAN = REPO_ROOT / "docs" / "ANTI_BULLSHIT_BATTLE_PLAN.md"


@pytest.fixture(scope="module")
def claude_md_text():
    return CLAUDE_MD.read_text(encoding="utf-8")


def test_claude_md_exists(claude_md_text):
    assert claude_md_text, "CLAUDE.md missing or empty"


def test_battle_plan_doc_exists():
    assert BATTLE_PLAN.exists(), (
        f"docs/ANTI_BULLSHIT_BATTLE_PLAN.md missing — RULE 4 has no target"
    )
    assert BATTLE_PLAN.stat().st_size > 5000, (
        "battle plan suspiciously small — should be ~415 lines"
    )


def test_claude_md_references_battle_plan(claude_md_text):
    """RULE 4 must mention the battle plan doc by relative path."""
    assert "ANTI_BULLSHIT_BATTLE_PLAN.md" in claude_md_text, (
        "BRICK 8 BROKEN: CLAUDE.md does not reference the battle plan."
    )


def test_claude_md_has_rule_4(claude_md_text):
    """RULE 4 (no claim without command output) must be present."""
    assert 'RULE id="4"' in claude_md_text, (
        "BRICK 8 BROKEN: RULE 4 missing from MUNINN_RULES section."
    )
    assert "No claim without command output" in claude_md_text


def test_claude_md_has_5_rules(claude_md_text):
    """We must have exactly 5 RULES (1-3 empirical, 4 anti-bullshit, 5 forge).
    Brick 16 added RULE 5 (forge after every engine module touch)."""
    count = claude_md_text.count('<RULE id=')
    assert count == 5, f"expected 5 RULES, found {count}"


def test_claude_md_has_rule_5(claude_md_text):
    """Brick 16: RULE 5 (forge mandatory) must be present."""
    assert 'RULE id="5"' in claude_md_text
    assert "Forge after every engine module touch" in claude_md_text
    assert "forge.py --gen-props" in claude_md_text


def test_claude_md_sandwich_mentions_rule_5(claude_md_text):
    """The recency-bias sandwich at the bottom must include RULE 5."""
    start = claude_md_text.find("<MUNINN_SANDWICH_RECENCY>")
    end = claude_md_text.find("</MUNINN_SANDWICH_RECENCY>")
    sandwich = claude_md_text[start:end]
    assert "RULE 5" in sandwich
    assert "FORGE" in sandwich.upper()


def test_claude_md_sandwich_mentions_rule_4(claude_md_text):
    """The recency-bias sandwich at the bottom must include RULE 4."""
    # Find the sandwich block
    start = claude_md_text.find("<MUNINN_SANDWICH_RECENCY>")
    end = claude_md_text.find("</MUNINN_SANDWICH_RECENCY>")
    assert start != -1 and end != -1, "sandwich block missing"
    sandwich = claude_md_text[start:end]
    assert "RULE 4" in sandwich, (
        "BRICK 8 BROKEN: sandwich at bottom doesn't repeat RULE 4 — "
        "primacy/recency bias defense is incomplete"
    )
    # Sandwich should mention "ANTI_BULLSHIT_BATTLE_PLAN.md" too
    assert "ANTI_BULLSHIT_BATTLE_PLAN" in sandwich


def test_claude_md_has_forbidden_phrases_listed(claude_md_text):
    """RULE 4 must explicitly list the phrases that are now forbidden."""
    # At least one of the canonical forbidden phrases must appear
    forbidden_examples = ["c'est fait", "le test passe", "c'est pushé"]
    matches = sum(1 for p in forbidden_examples if p in claude_md_text)
    assert matches >= 2, (
        f"BRICK 8 BROKEN: RULE 4 must list at least 2 forbidden phrases, "
        f"found {matches}"
    )


def test_claude_md_size_reasonable(claude_md_text):
    """CLAUDE.md should not balloon out of control or shrink unexpectedly."""
    n_lines = claude_md_text.count("\n")
    assert 150 < n_lines < 350, (
        f"CLAUDE.md has {n_lines} lines — outside expected range 150-350"
    )


def test_battle_plan_has_section_4_questions():
    """The battle plan section 4 lists 10 verification questions Sky can
    use to catch lies. They must be present for the rule to have teeth."""
    text = BATTLE_PLAN.read_text(encoding="utf-8")
    assert "10 verification" in text or "10 questions" in text or "1. \"" in text
    # Count enumerated questions in the doc — should be >= 10
    q_count = sum(1 for line in text.split("\n") if line.strip().startswith(tuple(f"{i}." for i in range(1, 11))))
    assert q_count >= 10, (
        f"battle plan has only {q_count} enumerated items, expected ≥ 10"
    )


def test_battle_plan_has_sources_section():
    """Section 5 lists the sources that prove the pattern is real."""
    text = BATTLE_PLAN.read_text(encoding="utf-8")
    assert "## 5. Sources" in text or "## 5." in text
    # Must reference the master prompt path that started it all
    assert "CLAUDE_ONE_PAGE_MASTER_PROMPT" in text
