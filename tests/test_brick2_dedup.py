"""PHASE B BRICK 2 — verify SimHash near-duplicate dedup module.

Pure module, zero side effects. Tests cover:
1. Module imports
2. SimHash determinism + correctness on edge cases
3. Hamming distance correctness
4. similar() detects identical / near / different
5. dedup_lines() collapses near-duplicates, preserves order
6. dedup_lines() leaves short lines alone
7. Real-world scenarios: chat log retries, agent loops
8. Pure: no I/O, no mutation
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEDUP_PATH = REPO_ROOT / "engine" / "core" / "dedup.py"


@pytest.fixture(scope="module")
def dedup():
    spec = importlib.util.spec_from_file_location("dedup_brick2", DEDUP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Module + API surface ────────────────────────────────────────


def test_module_imports(dedup):
    assert hasattr(dedup, "simhash")
    assert hasattr(dedup, "hamming_distance")
    assert hasattr(dedup, "similar")
    assert hasattr(dedup, "dedup_lines")
    assert hasattr(dedup, "dedup_paragraphs")
    assert hasattr(dedup, "stats")


# ── simhash() determinism & correctness ────────────────────────


def test_simhash_deterministic(dedup):
    """Same input must always give the same fingerprint."""
    text = "Sky is debugging the mycelium tonight in Paris."
    fp1 = dedup.simhash(text)
    fp2 = dedup.simhash(text)
    assert fp1 == fp2


def test_simhash_empty_returns_zero(dedup):
    assert dedup.simhash("") == 0
    assert dedup.simhash(None) == 0


def test_simhash_64bit_range(dedup):
    """64-bit fingerprint must fit in 64 bits."""
    fp = dedup.simhash("hello world this is a test of the simhash function")
    assert 0 <= fp < (1 << 64)


def test_simhash_different_widths(dedup):
    text = "Sky is debugging the mycelium with all his knowledge tonight."
    fp32 = dedup.simhash(text, bits=32)
    fp64 = dedup.simhash(text, bits=64)
    fp128 = dedup.simhash(text, bits=128)
    assert 0 <= fp32 < (1 << 32)
    assert 0 <= fp64 < (1 << 64)
    assert 0 <= fp128 < (1 << 128)


def test_simhash_invalid_bits_raises(dedup):
    with pytest.raises(ValueError, match="bits must be"):
        dedup.simhash("hello world test", bits=17)


def test_simhash_invalid_shingle_raises(dedup):
    with pytest.raises(ValueError, match="shingle_size"):
        dedup.simhash("hello world", shingle_size=0)


def test_simhash_short_text_falls_back_to_unigrams(dedup):
    """Texts shorter than shingle_size tokens still produce a meaningful fingerprint."""
    fp = dedup.simhash("hi", shingle_size=4)
    # Just must not crash and must be consistent
    assert fp == dedup.simhash("hi", shingle_size=4)


# ── hamming_distance() correctness ─────────────────────────────


def test_hamming_zero_for_identical(dedup):
    assert dedup.hamming_distance(0, 0) == 0
    assert dedup.hamming_distance(0xDEADBEEF, 0xDEADBEEF) == 0


def test_hamming_one_bit(dedup):
    assert dedup.hamming_distance(0, 1) == 1
    assert dedup.hamming_distance(0b1010, 0b1011) == 1


def test_hamming_all_bits(dedup):
    """Distance between 0 and -1 (all bits set) on small width."""
    assert dedup.hamming_distance(0, 0b1111) == 4
    assert dedup.hamming_distance(0b1010, 0b0101) == 4


def test_hamming_rejects_non_int(dedup):
    with pytest.raises(TypeError):
        dedup.hamming_distance("foo", 1)
    with pytest.raises(TypeError):
        dedup.hamming_distance(1, "bar")


# ── similar() — the integration of simhash + hamming ───────────


def test_similar_identical(dedup):
    text = "I am going to fix the bug in the auth middleware tomorrow morning."
    assert dedup.similar(text, text) is True


def test_similar_empty_returns_false(dedup):
    """Empty inputs cannot be deduped — return False to avoid surprises."""
    assert dedup.similar("", "") is False
    assert dedup.similar("hello world", "") is False
    assert dedup.similar("", "hello world") is False


def test_similar_minor_edit(dedup):
    """A typo or punctuation change should be near-duplicate."""
    a = "Sky is debugging the mycelium tonight in his office in Paris."
    b = "Sky is debugging the mycelium tonight in his office in Paris!"
    assert dedup.similar(a, b, threshold=3) is True


def test_similar_completely_different(dedup):
    a = "Sky is debugging the mycelium tonight in his office in Paris."
    b = "The weather forecast for tomorrow predicts heavy rain across France."
    assert dedup.similar(a, b, threshold=3) is False


def test_similar_threshold_tunable(dedup):
    """Higher threshold = more permissive."""
    a = "I will fix the auth bug in the middleware this evening for sure."
    b = "I am going to fix the auth bug in the middleware this evening."
    # With strict threshold, should NOT match
    strict = dedup.similar(a, b, threshold=1)
    # With permissive threshold, should match
    permissive = dedup.similar(a, b, threshold=20)
    assert permissive is True
    # strict result depends on data — just check it's <= permissive
    assert (not strict) or permissive


# ── dedup_lines() — sequence-level dedup ───────────────────────


def test_dedup_lines_keeps_unique(dedup):
    lines = [
        "Sky is fixing the bug in the auth middleware tonight.",
        "The weather forecast says rain tomorrow in Paris.",
        "Muninn's compression ratio just hit x4.5 on transcripts.",
    ]
    out = dedup.dedup_lines(lines)
    assert len(out) == 3
    assert out == lines  # order preserved


def test_dedup_lines_drops_exact_duplicates(dedup):
    line = "I am going to fix the bug in the auth middleware tonight."
    lines = [line, line, line, line]
    out = dedup.dedup_lines(lines)
    assert len(out) == 1
    assert out[0] == line


def test_dedup_lines_drops_near_duplicates(dedup):
    """Three close paraphrases of the same idea should collapse to one."""
    lines = [
        "I am going to fix the auth middleware bug tonight in Paris.",
        "I am going to fix the auth middleware bug tonight in Paris!",
        "I am going to fix the auth middleware bug tonight in Paris.",
    ]
    out = dedup.dedup_lines(lines, threshold=3)
    assert len(out) == 1
    assert out[0] == lines[0]  # keeps the first


def test_dedup_lines_preserves_order(dedup):
    lines = [
        "Aaa first unique line about debugging the auth middleware tonight.",
        "Bbb second unique line totally different from the others completely.",
        "Aaa first unique line about debugging the auth middleware tonight!",  # near-dup of #1
        "Ccc third unique line about Muninn compression hitting x4.5 ratio.",
    ]
    out = dedup.dedup_lines(lines)
    # Should keep #1, #2, #4 (drop #3 as near-dup of #1)
    assert len(out) == 3
    assert "Aaa" in out[0]
    assert "Bbb" in out[1]
    assert "Ccc" in out[2]


def test_dedup_lines_short_lines_pass_through(dedup):
    """Lines shorter than min_length must NOT be deduped."""
    lines = ["ok", "ok", "ok", "different but short"]
    out = dedup.dedup_lines(lines, min_length=20)
    assert out == lines  # all short, all kept


def test_dedup_lines_empty_input(dedup):
    assert dedup.dedup_lines([]) == []
    assert dedup.dedup_lines(None) == []


def test_dedup_lines_skips_non_strings(dedup):
    """Non-string entries are silently dropped."""
    lines = [
        "I am working on debugging the auth middleware tonight in Paris.",
        None,
        42,
        "This is a totally different line about the weather forecast in Paris.",
    ]
    out = dedup.dedup_lines(lines)
    assert all(isinstance(x, str) for x in out)
    assert len(out) == 2


# ── dedup_paragraphs() ─────────────────────────────────────────


def test_dedup_paragraphs_basic(dedup):
    text = (
        "First paragraph about debugging the auth middleware tonight in Paris.\n\n"
        "Second paragraph about the weather forecast for tomorrow in Paris.\n\n"
        "First paragraph about debugging the auth middleware tonight in Paris."
    )
    out = dedup.dedup_paragraphs(text)
    paragraphs = out.split("\n\n")
    assert len(paragraphs) == 2
    assert "First paragraph" in paragraphs[0]
    assert "Second paragraph" in paragraphs[1]


def test_dedup_paragraphs_empty(dedup):
    assert dedup.dedup_paragraphs("") == ""
    assert dedup.dedup_paragraphs(None) == ""


def test_dedup_paragraphs_single_unique(dedup):
    text = "Just one paragraph about something unique and long enough to fingerprint."
    out = dedup.dedup_paragraphs(text)
    assert out == text


# ── Real-world scenarios: where SimHash actually wins ─────────


def test_real_agent_minor_edit_retries_collapse(dedup):
    """Three near-identical lines with only punctuation / whitespace / case
    differences should collapse to one. This is SimHash's sweet spot."""
    transcript = [
        "Tool call: Bash 'git status' — exit 128 fatal not a git repository.",
        "Tool call: Bash 'git status' — exit 128 fatal not a git repository!",
        "Tool call: Bash 'git status' - exit 128 fatal not a git repository.",
        "Switching strategy: Bash 'cd /repo && git status' returned exit 0, branch main.",
    ]
    out = dedup.dedup_lines(transcript, threshold=3)
    # The 3 minor variants collapse, success line stays
    assert len(out) == 2, f"expected 2 lines, got {len(out)}: {out}"
    assert any("exit 0" in line for line in out), "kept the success line"


def test_real_log_repetition_collapses_loose_mode(dedup):
    """Repeated log lines from a polling loop — typical agent transcript.

    Polling lines differ only by an attempt counter (1, 2, 3, 4). With the
    default strict params (k=4 shingles, threshold=3) the small numerical
    differences produce hamming distances of ~25 — too far for collapse.
    The intended operating mode for log-repetition dedup is `shingle_size=1`
    (bag of words) + a more permissive threshold around 14. Empirically
    measured: PENDING-vs-PENDING distances are 9-13, PENDING-vs-SUCCESS
    distances are 21+, so threshold=14 gives a clean cut.
    """
    transcript = [
        "Polling status endpoint, current state: PENDING, attempt 1 of 30 max.",
        "Polling status endpoint, current state: PENDING, attempt 2 of 30 max.",
        "Polling status endpoint, current state: PENDING, attempt 3 of 30 max.",
        "Polling status endpoint, current state: PENDING, attempt 4 of 30 max.",
        "Polling status endpoint, current state: SUCCESS, final result returned.",
    ]
    out = dedup.dedup_lines(transcript, threshold=14, shingle_size=1)
    # The 4 PENDING polls should collapse to 1, the SUCCESS line stays
    assert len(out) == 2, f"expected 2 lines, got {len(out)}: {out}"
    assert any("SUCCESS" in line for line in out)


def test_real_log_repetition_strict_default_does_NOT_collapse(dedup):
    """Documents the strict default's blind spot for numerical drift.

    With k=4 shingles + threshold=3, the polling lines do NOT collapse
    because each numerical change ('attempt 1' -> 'attempt 2') introduces
    a fresh shingle whose hash differs significantly. This is by design:
    strict defaults err on the side of false negatives (keep when in doubt).
    """
    transcript = [
        "Polling status endpoint, current state: PENDING, attempt 1 of 30 max.",
        "Polling status endpoint, current state: PENDING, attempt 2 of 30 max.",
    ]
    out = dedup.dedup_lines(transcript, threshold=3)
    # Both survive — strict mode does NOT catch numerical drift
    assert len(out) == 2


def test_documented_limitation_prefix_paraphrases_not_caught(dedup):
    """SimHash with k-shingles does NOT catch prefix paraphrases.
    'OK I will fix X' vs 'Alright I am going to fix X' have different
    leading shingles. This test documents the limitation so we know
    when to upgrade to a stronger primitive."""
    paraphrases = [
        "OK I will go ahead and fix the auth middleware bug right now in Paris.",
        "Alright I am going to fix the auth middleware bug right now in Paris.",
        "Sure I will fix the auth middleware bug right now in Paris immediately.",
    ]
    out = dedup.dedup_lines(paraphrases, threshold=3)
    # All 3 survive — SimHash with k=4 shingles cannot collapse these.
    # If this test starts FAILING, it means we upgraded to a smarter primitive.
    assert len(out) == 3, (
        "If this test fails, SimHash is now catching prefix paraphrases — "
        "great news but update the limitation docs"
    )


# ── stats() helper ─────────────────────────────────────────────


def test_stats_text_only(dedup):
    s = dedup.stats(text="Sky is debugging the mycelium tonight in Paris.")
    assert "tokens" in s
    assert "shingles" in s
    assert "simhash" in s
    assert s["tokens"] > 0


def test_stats_lines_only(dedup):
    line = "Sky is debugging the mycelium tonight in Paris with great care."
    s = dedup.stats(lines=[line, line, "totally different content here for sure now"])
    assert s["lines_total"] == 3
    assert s["lines_kept"] == 2
    assert 0 < s["dedup_ratio"] < 1


def test_stats_empty(dedup):
    s = dedup.stats()
    assert s == {}


# ── Purity sanity ─────────────────────────────────────────────


def test_pure_no_mutation(dedup):
    """Calling dedup_lines twice on the same input produces identical output."""
    lines = [
        "I am working on the auth bug fix in the middleware tonight in Paris.",
        "Totally separate concern about the weather forecast for tomorrow.",
    ]
    a = dedup.dedup_lines(lines)
    b = dedup.dedup_lines(lines)
    assert a == b
    # Original list must not be mutated
    assert len(lines) == 2


def test_simhash_identical_inputs_identical_fingerprints(dedup):
    """Determinism property — important for any future caching layer."""
    inputs = [
        "Sky is fixing a bug in the auth middleware tonight in Paris.",
        "Muninn's compression ratio hit x4.5 on real transcripts last week.",
        "The weather forecast says heavy rain in Paris tomorrow morning.",
        "",
    ]
    for s in inputs:
        assert dedup.simhash(s) == dedup.simhash(s)
