"""PHASE B BRICK 5 — pin the SimHash dedup wiring into compress_section().

Locks the contract that compress_section() collapses near-duplicate body
lines via SimHash. If anyone removes the `_dedup_body_lines(body)` call
or breaks the import of `dedup.simhash`, this test fails immediately.
"""
import importlib
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


# ── Wiring presence ──────────────────────────────────────────


def test_dedup_module_loaded(ml):
    """The brick 5 import must have succeeded at module init."""
    assert hasattr(ml, "_DEDUP_AVAILABLE")
    assert ml._DEDUP_AVAILABLE is True, (
        "BRICK 5 BROKEN: dedup.py import failed at muninn_layers init"
    )


def test_dedup_helper_present(ml):
    """The _dedup_body_lines helper must exist and be callable."""
    assert hasattr(ml, "_dedup_body_lines")
    assert callable(ml._dedup_body_lines)


# ── End-to-end dedup behavior ────────────────────────────────


def test_dedup_collapses_near_duplicate_body_lines(ml):
    """Section with 5 near-duplicate lines + 2 unique → 3 kept."""
    lines = [
        "Sky deployed v2.3.1 to production on 2026-04-10 today.",
        "Sky deployed v2.3.1 to production on 2026-04-10 today!",  # near-dup
        "Sky deployed v2.3.1 to production on 2026-04-10 today.",  # exact
        "Muninn compression hit x4.5 ratio on transcripts today.",
        "Muninn compression hit x4.5 ratio on transcripts today!",  # near-dup
    ]
    deduped = ml._dedup_body_lines(lines)
    # Two unique facts + their near-dups → 2 kept
    assert len(deduped) == 2, (
        f"BRICK 5 BROKEN: expected 2 deduped lines, got {len(deduped)}: {deduped}"
    )


def test_dedup_preserves_facts(ml):
    lines = [
        "Sky deployed v2.3.1 on 2026-04-10 with commit abc1234 fixing BUG-101.",
        "Sky deployed v2.3.1 on 2026-04-10 with commit abc1234 fixing BUG-101!",
    ]
    out = ml._dedup_body_lines(lines)
    assert len(out) == 1
    # Critical info must survive
    for fact in ("v2.3.1", "2026-04-10", "abc1234", "BUG-101"):
        assert fact in out[0], (
            f"BRICK 5 BROKEN: fact {fact!r} lost during dedup"
        )


def test_dedup_preserves_unique_lines(ml):
    """Three completely different lines must all survive."""
    lines = [
        "Sky writes Muninn engine code in Python today carefully.",
        "The weather forecast says heavy rain in Paris tomorrow.",
        "Compression ratio hit x4.5 on the verbose memory benchmark.",
    ]
    out = ml._dedup_body_lines(lines)
    assert len(out) == 3, (
        f"BRICK 5 BROKEN: dropped unique lines: {out}"
    )


def test_dedup_preserves_tagged_lines(ml):
    """Lines with classification tags (B>, E>, F>, D>, A>) NEVER deduped."""
    lines = [
        "B> business critical line one detailed enough to be fingerprinted",
        "B> business critical line one detailed enough to be fingerprinted",
        "F> fact span important enough to never drop ever from the body",
        "F> fact span important enough to never drop ever from the body",
    ]
    out = ml._dedup_body_lines(lines)
    assert len(out) == 4, (
        f"BRICK 5 SAFETY NET BROKEN: tagged lines were deduped. "
        f"Got {len(out)} lines: {out}"
    )


def test_dedup_preserves_short_lines(ml):
    """Lines shorter than 20 chars are too noisy to fingerprint — pass through."""
    lines = ["ok", "ok", "ok", "x4.5"]
    out = ml._dedup_body_lines(lines)
    assert out == lines


def test_dedup_handles_empty_input(ml):
    assert ml._dedup_body_lines([]) == []
    assert ml._dedup_body_lines(None) == []


def test_dedup_handles_non_string_entries(ml):
    """Defensive: non-strings pass through unchanged."""
    lines = [
        "Sky writes Muninn engine code in Python today carefully always.",
        None,
        42,
        "Sky writes Muninn engine code in Python today carefully always.",
    ]
    out = ml._dedup_body_lines(lines)
    # The string near-dup should be collapsed; None and 42 pass through
    assert None in out
    assert 42 in out


# ── compress_section integration ─────────────────────────────


def test_compress_section_invokes_dedup(ml):
    """End-to-end: compress_section() must produce fewer lines than input
    when the input has near-duplicates."""
    header = "## Test session"
    lines = [
        "Sky deployed v2.3.1 to production on 2026-04-10 today.",
        "Sky deployed v2.3.1 to production on 2026-04-10 today!",
        "Sky deployed v2.3.1 to production on 2026-04-10 today.",
        "Muninn compression hit x4.5 ratio on transcripts today.",
        "Muninn compression hit x4.5 ratio on transcripts today!",
    ]
    out = ml.compress_section(header, lines)
    # Count newlines in body (each line becomes "\n  <line>")
    body_line_count = out.count("\n  ")
    assert body_line_count <= 2, (
        f"BRICK 5 BROKEN: expected ≤2 body lines, got {body_line_count}: {out}"
    )


def test_compress_section_preserves_section_when_no_dups(ml):
    """No near-dups → all input lines should survive."""
    header = "## Unique content session"
    lines = [
        "Sky writes Muninn engine code in Python today carefully always.",
        "The weather forecast says heavy rain in Paris tomorrow morning.",
        "Compression ratio hit x4.5 on the verbose memory benchmark today.",
    ]
    out = ml.compress_section(header, lines)
    # All 3 unique lines should be preserved
    assert "Sky" in out
    assert "weather" in out
    assert "x4.5" in out


# ── Graceful degradation ─────────────────────────────────────


def test_dedup_graceful_when_unavailable(ml):
    """If _DEDUP_AVAILABLE is False, _dedup_body_lines is identity."""
    saved = ml._DEDUP_AVAILABLE
    try:
        ml._DEDUP_AVAILABLE = False
        lines = ["a" * 30, "b" * 30, "a" * 30]
        out = ml._dedup_body_lines(lines)
        assert out == lines  # identity, no dedup
    finally:
        ml._DEDUP_AVAILABLE = saved


# ── Real measurement floor (proves it actually works) ────────


def test_brick5_measurable_savings(ml):
    """A section with 4 near-dups must collapse to fewer lines AND
    fewer chars than the same section with brick 5 disabled."""
    header = "## Measurement test"
    lines = [
        "Sky deployed v2.3.1 to production on 2026-04-10 with all tests passing.",
        "Sky deployed v2.3.1 to production on 2026-04-10 with all tests passing!",
        "Sky deployed v2.3.1 to production on 2026-04-10 with all tests passing.",
        "Sky deployed v2.3.1 to production on 2026-04-10 with all tests passing!",
        "Muninn compression ratio hit x4.5 on the verbose memory benchmark today.",
    ]
    out_on = ml.compress_section(header, lines)

    saved = ml._DEDUP_AVAILABLE
    try:
        ml._DEDUP_AVAILABLE = False
        out_off = ml.compress_section(header, lines)
    finally:
        ml._DEDUP_AVAILABLE = saved

    # Brick 5 must save AT LEAST 20% of chars on this dup-heavy input
    saved_chars = len(out_off) - len(out_on)
    pct = saved_chars / len(out_off)
    assert pct >= 0.20, (
        f"BRICK 5 not effective: only {pct:.1%} chars saved.\n"
        f"OFF ({len(out_off)} chars): {out_off!r}\n"
        f"ON  ({len(out_on)} chars): {out_on!r}"
    )
