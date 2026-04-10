"""PHASE B BRICK 4 — pin the lexicons tier1 wiring into compress_line().

This test exists so that if anyone removes the lexicons import or the
inline tier1 stripping in compress_line(), CI catches it immediately.
The wiring is small (4 lines) but easy to lose in a refactor.

Uses ONLY engine/core/muninn_layers.py to avoid the muninn package
import which carries heavier dependencies.
"""
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


@pytest.fixture(scope="module")
def ml():
    """Load engine/core/muninn_layers.py with the muninn module loaded first."""
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    # muninn must be loaded first (muninn_layers references it via _ModRef)
    import muninn  # noqa: F401
    import muninn_layers
    importlib.reload(muninn_layers)
    return muninn_layers


# ── Wiring presence ──────────────────────────────────────────


def test_lexicons_patterns_loaded_at_module_init(ml):
    """The module-level constant must exist and be non-empty."""
    assert hasattr(ml, "_LEXICONS_TIER1_PATTERNS")
    assert isinstance(ml._LEXICONS_TIER1_PATTERNS, list)
    assert len(ml._LEXICONS_TIER1_PATTERNS) >= 30, (
        f"only {len(ml._LEXICONS_TIER1_PATTERNS)} tier1 patterns loaded — "
        "wiring may be broken"
    )


def test_lexicons_module_actually_imported(ml):
    """A sample tier1 pattern must compile."""
    import re
    sample = ml._LEXICONS_TIER1_PATTERNS[0]
    re.compile(sample, re.IGNORECASE)  # must not raise


# ── End-to-end stripping ─────────────────────────────────────


def test_intensifier_absolutely_stripped(ml):
    out = ml.compress_line("Sky is absolutely committed to fixing this bug.")
    assert "absolutely" not in out.lower(), (
        f"BRICK 4 BROKEN: 'absolutely' not stripped. Output: {out!r}"
    )


def test_intensifier_literally_stripped(ml):
    out = ml.compress_line("This is literally the best fix we shipped.")
    assert "literally" not in out.lower(), (
        f"BRICK 4 BROKEN: 'literally' not stripped. Output: {out!r}"
    )


def test_intensifier_totally_stripped(ml):
    out = ml.compress_line("The migration is totally tested and ready to ship.")
    assert "totally" not in out.lower()


def test_hedge_apparently_stripped(ml):
    out = ml.compress_line("Apparently the test suite passes on Windows now.")
    assert "apparently" not in out.lower()


def test_hedge_supposedly_stripped(ml):
    out = ml.compress_line("Supposedly the cron job runs every 5 minutes.")
    assert "supposedly" not in out.lower()


def test_hedge_presumably_stripped(ml):
    out = ml.compress_line("Presumably the deploy will land before Friday.")
    assert "presumably" not in out.lower()


def test_multiple_tier1_words_in_one_line(ml):
    src = (
        "Sky is absolutely committed to literally fixing this. Frankly, this "
        "is totally a great idea — apparently the tests pass, supposedly all "
        "144 of them, and presumably we ship tomorrow."
    )
    out = ml.compress_line(src)
    for w in ("absolutely", "literally", "frankly", "totally",
              "apparently", "supposedly", "presumably"):
        assert w not in out.lower(), (
            f"BRICK 4 BROKEN: {w!r} survived stripping. Output: {out!r}"
        )


# ── Critical info preserved ──────────────────────────────────


def test_critical_info_preserved_under_brick4(ml):
    """Numbers, names, semvers, ticket IDs MUST survive tier1 stripping."""
    src = (
        "Sky shipped v2.3.1 on 2026-04-10 with commit abc1234 fixing BUG-101 "
        "absolutely properly literally on the first try."
    )
    out = ml.compress_line(src)
    # Facts must survive
    assert "v2.3.1" in out
    assert "2026-04-10" in out
    assert "abc1234" in out
    assert "BUG-101" in out
    assert "Sky" in out
    # Tier1 words must be gone
    assert "absolutely" not in out.lower()
    assert "literally" not in out.lower()


def test_quantifiers_NOT_stripped_by_brick4(ml):
    """The DANGEROUS_NEVER_ADD safety net must hold end-to-end.

    'all', 'many', 'few', 'some' must SURVIVE compress_line() (the
    existing _FILLER may strip some of them, but tier1 must NOT
    introduce new false-positives on these words)."""
    # Use words that aren't in the existing _FILLER either
    src = "Many tests pass and several edge cases were covered well."
    out = ml.compress_line(src)
    # 'many' and 'several' are in DANGEROUS_NEVER_ADD, must survive tier1
    assert "many" in out.lower(), f"'many' wrongly stripped. Output: {out!r}"
    assert "several" in out.lower(), f"'several' wrongly stripped. Output: {out!r}"


def test_action_verbs_NOT_stripped_by_brick4(ml):
    """Action verbs in DANGEROUS_NEVER_ADD must survive."""
    src = "We find that tests tend to pass when developers think clearly."
    out = ml.compress_line(src)
    for verb in ("find", "tend", "think"):
        assert verb in out.lower(), (
            f"BRICK 4 SAFETY NET BROKEN: action verb {verb!r} stripped. "
            f"Output: {out!r}"
        )


# ── No-op when lexicons module is missing ────────────────────


def test_compress_line_works_when_lexicons_unavailable(ml):
    """If _LEXICONS_TIER1_PATTERNS is empty (degraded mode), compress_line
    must still function normally — graceful degradation per the wiring."""
    saved = ml._LEXICONS_TIER1_PATTERNS
    try:
        ml._LEXICONS_TIER1_PATTERNS = []
        out = ml.compress_line("Sky shipped v2.3.1 on 2026-04-10.")
        # Existing _FILLER still runs
        assert "v2.3.1" in out
        assert "2026-04-10" in out
    finally:
        ml._LEXICONS_TIER1_PATTERNS = saved


# ── Measurement check (proves it actually compresses) ───────


def test_measurable_compression_on_intensifier_heavy_text(ml):
    """The wiring must REDUCE the character count on text with tier1 words.
    This test fails if the wiring is removed or no-op'd."""
    src = (
        "Sky absolutely literally totally definitely completely truly "
        "particularly seriously frankly entirely fully shipped the fix."
    )
    out = ml.compress_line(src)
    reduction = 1 - len(out) / len(src)
    assert reduction > 0.30, (
        f"BRICK 4 not effective: only {reduction:.1%} reduction. "
        f"Input ({len(src)}): {src!r}\nOutput ({len(out)}): {out!r}"
    )
