"""PHASE B BRICK 6 — pin the BudgetMem L12 wiring into compress_file().

This brick is OPT-IN via the MUNINN_L12_BUDGET environment variable.
When unset (default), compress_file() behavior is unchanged from
pre-brick-6 — full backward compatibility. When set to an integer,
compress_file() runs BudgetMem chunk selection AFTER L11 and BEFORE L9.

Tests the wiring contract end-to-end so it can never silently regress.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


@pytest.fixture(scope="module")
def ml():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import muninn  # noqa: F401
    import muninn_layers
    importlib.reload(muninn_layers)
    return muninn_layers


@pytest.fixture(autouse=True)
def _clean_env():
    """Make sure tests start with no MUNINN_L12_BUDGET set."""
    saved = os.environ.pop("MUNINN_L12_BUDGET", None)
    yield
    os.environ.pop("MUNINN_L12_BUDGET", None)
    if saved is not None:
        os.environ["MUNINN_L12_BUDGET"] = saved


# ── Wiring presence ──────────────────────────────────────────


def test_budget_select_available(ml):
    assert hasattr(ml, "_BUDGET_SELECT_AVAILABLE")
    assert ml._BUDGET_SELECT_AVAILABLE is True, (
        "BRICK 6 BROKEN: budget_select.py import failed at init"
    )


def test_l12_helper_present(ml):
    assert hasattr(ml, "_l12_budget_pass")
    assert callable(ml._l12_budget_pass)


# ── OFF-by-default behavior (no env var) ─────────────────────


def test_l12_no_op_when_env_unset(ml):
    """Without MUNINN_L12_BUDGET, _l12_budget_pass is identity."""
    text = "First.\n\nSecond critical: v2.3.1 on 2026-04-10.\n\nThird filler."
    out = ml._l12_budget_pass(text)
    assert out == text


def test_l12_no_op_when_env_invalid(ml):
    """Non-integer values must NOT crash, must NOT compress."""
    text = "First.\n\nSecond critical: v2.3.1.\n\nThird filler."
    for bad in ("not a number", "", "0", "-5", "1.5", "abc"):
        os.environ["MUNINN_L12_BUDGET"] = bad
        out = ml._l12_budget_pass(text)
        assert out == text, f"BRICK 6 BROKEN on bad value {bad!r}"


def test_l12_handles_empty_text(ml):
    os.environ["MUNINN_L12_BUDGET"] = "100"
    assert ml._l12_budget_pass("") == ""
    assert ml._l12_budget_pass(None) == ""


# ── ON behavior (env var set) ────────────────────────────────


def test_l12_drops_filler_under_tight_budget(ml):
    text = (
        "First filler paragraph completely empty of facts.\n\n"
        "Second critical: shipped v2.3.1 on 2026-04-10 fixing BUG-101.\n\n"
        "Third filler paragraph also empty no facts here.\n\n"
        "Fourth Muninn compression hit x4.5 ratio with commit abc1234.\n\n"
        "Fifth filler paragraph generic prose nothing important."
    )
    # Budget chosen to fit both fact paragraphs (~23 + ~18 = ~41 BPE tokens)
    # plus a small filler — but not all 5 paragraphs.
    os.environ["MUNINN_L12_BUDGET"] = "50"
    out = ml._l12_budget_pass(text)
    # Both fact-rich paragraphs MUST be in the output
    assert "v2.3.1" in out, "BRICK 6 dropped fact span v2.3.1!"
    assert "BUG-101" in out, "BRICK 6 dropped fact span BUG-101!"
    assert "abc1234" in out, "BRICK 6 dropped fact span abc1234!"
    assert "x4.5" in out, "BRICK 6 dropped fact span x4.5!"
    # At least one filler must have been dropped
    assert "Third filler paragraph" not in out or "Fifth filler paragraph" not in out, (
        "BRICK 6 should have dropped at least one mid-position filler"
    )


def test_l12_keeps_all_under_huge_budget(ml):
    text = "First.\n\nSecond.\n\nThird.\n\nFourth.\n\nFifth."
    os.environ["MUNINN_L12_BUDGET"] = "100000"
    out = ml._l12_budget_pass(text)
    # Huge budget should keep everything (or near-everything)
    for word in ("First", "Second", "Third", "Fourth", "Fifth"):
        assert word in out


def test_l12_zero_budget_returns_empty_or_unchanged(ml):
    """Budget=0 must NOT crash. Behavior: identity (per the helper rule)."""
    text = "First.\n\nSecond critical: v2.3.1.\n\nThird."
    os.environ["MUNINN_L12_BUDGET"] = "0"
    out = ml._l12_budget_pass(text)
    # 0 is invalid budget -> identity (helper guards against it)
    assert out == text


# ── Critical info preservation under tight budget ───────────


def test_l12_preserves_iso_dates(ml):
    """Budget must allow at least the fact-bearing chunk in BPE tokens."""
    text = (
        "Filler paragraph one with no facts whatsoever inside it at all.\n\n"
        "Critical: deployed on 2026-04-10 with full test coverage today.\n\n"
        "Filler paragraph three also empty of factual content here too."
    )
    # Fact chunk is ~17 BPE tokens; budget 25 fits it comfortably
    os.environ["MUNINN_L12_BUDGET"] = "25"
    out = ml._l12_budget_pass(text)
    assert "2026-04-10" in out


def test_l12_preserves_semvers(ml):
    text = (
        "Generic intro paragraph with nothing special at all to mention.\n\n"
        "Migration to v2.3.1 was completed yesterday by the team.\n\n"
        "Closing paragraph also nothing critical to record here."
    )
    # Fact chunk is ~15 BPE tokens
    os.environ["MUNINN_L12_BUDGET"] = "25"
    out = ml._l12_budget_pass(text)
    assert "v2.3.1" in out


def test_l12_preserves_jira_tickets(ml):
    text = (
        "Generic noise paragraph one nothing important to keep.\n\n"
        "BUG-101 was fixed by the auth team last week reportedly.\n\n"
        "Generic noise paragraph three also empty of facts."
    )
    # Fact chunk is ~13 BPE tokens
    os.environ["MUNINN_L12_BUDGET"] = "25"
    out = ml._l12_budget_pass(text)
    assert "BUG-101" in out


def test_l12_preserves_git_hashes(ml):
    text = (
        "Filler one with no specific information at all about anything.\n\n"
        "Commit abc1234 introduced the regression that broke the build.\n\n"
        "Filler three also empty no specific data points to record."
    )
    # Fact chunk is ~12 BPE tokens
    os.environ["MUNINN_L12_BUDGET"] = "25"
    out = ml._l12_budget_pass(text)
    assert "abc1234" in out


def test_l12_documents_must_keep_limitation(ml):
    """Documents the known limitation: if a fact-bearing chunk is LARGER
    than the entire budget (in BPE tokens), it cannot be kept. The hard
    rule is "must-keep when it fits", not "must-keep no matter what".
    Future improvement: compress fact chunks further before dropping."""
    text = (
        "Critical: deployed v2.3.1 on 2026-04-10 with commit abc1234 "
        "fixing BUG-101 and reaching x4.5 compression ratio finally.\n\n"
        "Tiny filler."
    )
    # Budget=8 — too small for the ~30-BPE-token fact chunk
    os.environ["MUNINN_L12_BUDGET"] = "8"
    out = ml._l12_budget_pass(text)
    # The fact chunk is too big to fit, so the small filler wins
    assert "Tiny filler" in out


# ── Graceful degradation ─────────────────────────────────────


def test_l12_graceful_when_unavailable(ml):
    """If _BUDGET_SELECT_AVAILABLE is False, helper is identity."""
    saved = ml._BUDGET_SELECT_AVAILABLE
    try:
        ml._BUDGET_SELECT_AVAILABLE = False
        os.environ["MUNINN_L12_BUDGET"] = "10"
        text = "alpha.\n\nbravo.\n\ncharlie."
        out = ml._l12_budget_pass(text)
        assert out == text
    finally:
        ml._BUDGET_SELECT_AVAILABLE = saved


# ── Real measurement floor ──────────────────────────────────


def test_l12_measurable_savings_on_filler_heavy(ml):
    """Filler-heavy text MUST be reduced when L12 is enabled.
    Budget chosen to fit both fact paragraphs (~23 + ~18 = ~41 BPE tokens)
    but not the 6 filler paragraphs."""
    text = "\n\n".join([
        "First filler paragraph completely generic without any specific facts.",
        "Second critical: shipped v2.3.1 on 2026-04-10 fixing BUG-101.",
        "Third filler paragraph also generic content with no information.",
        "Fourth filler paragraph repeating the same generic structure here.",
        "Fifth filler paragraph yet another generic verbose content block.",
        "Sixth Muninn compression hit x4.5 ratio with commit abc1234 today.",
        "Seventh filler paragraph empty content nothing useful inside this.",
        "Eighth filler paragraph generic prose absolutely no specific data.",
    ])
    os.environ["MUNINN_L12_BUDGET"] = "60"
    out = ml._l12_budget_pass(text)
    saved = len(text) - len(out)
    pct = saved / len(text)
    assert pct >= 0.40, (
        f"BRICK 6 not effective: only {pct:.1%} chars saved.\n"
        f"Input  ({len(text)}): {text!r}\n"
        f"Output ({len(out)}): {out!r}"
    )
    # All facts must survive
    for fact in ("v2.3.1", "2026-04-10", "BUG-101", "abc1234", "x4.5"):
        assert fact in out, f"BRICK 6 dropped fact {fact!r}"
