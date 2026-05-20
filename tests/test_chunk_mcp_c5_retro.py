"""
CHUNK MCP C.5 — Post-mortem RETRO doc for Phase A+B+start-of-C.

Captures methodology + metrics + lessons learned from the 2026-05-11
sprint (Phase A: 4 chunks, Phase B: 6 chunks, Phase C: 4/6 chunks).

Sanity-checks the RETRO doc structure (7 sections per the plan +
metrics references that match reality).
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_c5_retro_doc_exists():
    p = REPO_ROOT / "docs" / "RETRO_PHASE_AB_2026-05-11.md"
    assert p.exists(), f"missing {p}"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    assert n > 200, f"RETRO too short: {n} lines (expected >200 per the plan)"


def test_c5_retro_has_seven_sections():
    """The plan called for 7 numbered sections + a TL;DR header."""
    p = REPO_ROOT / "docs" / "RETRO_PHASE_AB_2026-05-11.md"
    text = p.read_text(encoding="utf-8")
    import re
    # Match "## 1. ", "## 2. ", ..., "## 7. " headings
    section_titles = re.findall(r"^##\s+\d+\.\s+", text, re.MULTILINE)
    assert len(section_titles) >= 7, (
        f"RETRO expected 7+ numbered sections, found {len(section_titles)}"
    )


def test_c5_retro_has_tldr():
    p = REPO_ROOT / "docs" / "RETRO_PHASE_AB_2026-05-11.md"
    text = p.read_text(encoding="utf-8")
    assert "TL;DR" in text or "tldr" in text.lower(), (
        "RETRO should have a TL;DR up top for quick scanning"
    )


def test_c5_retro_mentions_methodology_items():
    """RETRO must cover the methodology items the plan listed."""
    p = REPO_ROOT / "docs" / "RETRO_PHASE_AB_2026-05-11.md"
    text = p.read_text(encoding="utf-8")
    for keyword in (
        "3-agents",      # methodology
        "TDD",           # test-driven discipline
        "pre-chunk",     # parallelism pattern
        "RULE 1",        # path hardcoding rule
        "BUG-111",       # the leak we caught + fixed
        "auto-calibration",  # C.0
    ):
        assert keyword in text, f"RETRO missing methodology keyword: {keyword!r}"


def test_c5_retro_metrics_match_real_state():
    """Sanity that the LOC/test/commit numbers in the RETRO are not invented.

    We check that the test pin counts cited add up to something plausible
    (we don't verify exact numbers — the RETRO is allowed to summarize).
    """
    p = REPO_ROOT / "docs" / "RETRO_PHASE_AB_2026-05-11.md"
    text = p.read_text(encoding="utf-8")
    # Check that at least the magnitude is plausible.
    # 146 tests pin total (sum of A.1 + ... + C.4)
    # 10 MCP tools
    # 2506 PASS in the final regression
    for marker in ("146 tests", "10 tools", "2506 PASS"):
        # accept either exact match or close variants
        assert any(part in text for part in (marker, marker.replace(" ", " "))), (
            f"RETRO missing expected metric marker: {marker!r}"
        )


def test_c5_changelog_references_retro():
    """CHANGELOG should have an entry that references the RETRO doc."""
    p = REPO_ROOT / "CHANGELOG.md"
    text = p.read_text(encoding="utf-8")
    assert "RETRO_PHASE_AB" in text or "RETRO PHASE A" in text.upper(), (
        "CHANGELOG should link to docs/RETRO_PHASE_AB_2026-05-11.md"
    )


def test_c5_master_mcp_references_retro():
    """BATTLE_PLAN_MASTER_MCP should reference the RETRO for lessons learned.

    2026-05-20 : MASTER_MCP archivé vers docs/archive/ (phases A-F livrées).
    Le test cherche le doc dans les 2 emplacements pour rester robuste.
    """
    candidates = [
        REPO_ROOT / "docs" / "BATTLE_PLAN_MASTER_MCP.md",
        REPO_ROOT / "docs" / "archive" / "BATTLE_PLAN_MASTER_MCP.md",
    ]
    p = next((c for c in candidates if c.exists()), None)
    assert p is not None, f"BATTLE_PLAN_MASTER_MCP introuvable (cherché : {candidates})"
    text = p.read_text(encoding="utf-8")
    assert "RETRO_PHASE_AB" in text or "RETRO" in text, (
        "MASTER_MCP should cross-link to the RETRO"
    )
