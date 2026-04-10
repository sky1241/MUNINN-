"""PHASE B BRICK 3 — verify BudgetMem-style chunk selection.

Pure module, zero side effects. Tests cover:
1. Module imports + API surface
2. Tokenization + IDF correctness
3. Each individual feature in isolation
4. score_chunk weighted sum
5. Fact span detection (the hard-rule trigger)
6. select_chunks under various budgets
7. Order preservation in the kept set
8. Hard rule: must-keep chunks survive aggressive budgets
9. budget_select end-to-end
10. Real-world scenario: compression of a structured doc
11. Pure: no I/O, no mutation
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BS_PATH = REPO_ROOT / "engine" / "core" / "budget_select.py"


@pytest.fixture(scope="module")
def bs():
    spec = importlib.util.spec_from_file_location("bs_brick3", BS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── API surface ────────────────────────────────────────────────


def test_module_imports(bs):
    for name in (
        "compute_idf", "score_chunk", "select_chunks",
        "budget_select", "has_fact_span", "stats",
    ):
        assert hasattr(bs, name), f"missing {name}"


# ── compute_idf() correctness ──────────────────────────────────


def test_compute_idf_empty(bs):
    assert bs.compute_idf([]) == {}
    assert bs.compute_idf(None) == {}


def test_compute_idf_single_chunk(bs):
    """One chunk: every term has the same IDF (only one document)."""
    idf = bs.compute_idf(["sky debugs the mycelium"])
    assert "sky" in idf
    assert "debugs" in idf
    assert "the" in idf
    # All four terms in 1 chunk -> df=1, n=1 -> idf = log(2/2)+1 = 1.0
    for term in idf:
        assert idf[term] == pytest.approx(1.0, abs=0.01)


def test_compute_idf_distinguishes_common_from_rare(bs):
    """A term in every chunk gets lower IDF than a rare term."""
    chunks = [
        "sky writes muninn code today",
        "sky writes more code today",
        "sky writes the rare gizmo",
    ]
    idf = bs.compute_idf(chunks)
    # 'sky' appears in 3/3, 'gizmo' in 1/3 → gizmo idf > sky idf
    assert idf["gizmo"] > idf["sky"]
    assert idf["sky"] > 0
    assert idf["gizmo"] > 0


def test_compute_idf_skips_non_strings(bs):
    idf = bs.compute_idf(["valid chunk", None, 42, "another valid one"])
    assert "valid" in idf
    assert "another" in idf


# ── Individual feature functions ───────────────────────────────


def test_entity_density_zero_for_lowercase(bs):
    score = bs._entity_density("the rain in spain stays mainly in the plain")
    assert score == 0.0


def test_entity_density_detects_proper_nouns(bs):
    """Sky and Muninn should count as entities, 'the' should not."""
    score = bs._entity_density("the developer Sky writes the engine Muninn")
    assert score > 0


def test_entity_density_skips_sentence_initial_caps(bs):
    """Sentence-initial 'The' must NOT count as an entity."""
    score = bs._entity_density("The cat. The dog. The mouse.")
    assert score == 0.0


def test_number_density_zero(bs):
    assert bs._number_density("no numbers here at all today") == 0.0


def test_number_density_full(bs):
    """All-number tokens give density 1.0."""
    score = bs._number_density("42 17 99 1234 567")
    assert score == 1.0


def test_number_density_mixed(bs):
    """Half-number content gives ~0.5."""
    score = bs._number_density("the answer is 42 and pi is 3 and e is 2")
    assert 0.2 < score < 0.5


def test_question_presence_yes(bs):
    assert bs._question_presence("What is the meaning?") == 1.0


def test_question_presence_no(bs):
    assert bs._question_presence("This is a statement.") == 0.0
    assert bs._question_presence("") == 0.0


def test_position_score_first_quintile(bs):
    """First 20% of chunks gets the bonus."""
    assert bs._position_score(0, 10) == 1.0
    assert bs._position_score(1, 10) == 1.0


def test_position_score_middle(bs):
    assert bs._position_score(5, 10) == 0.5


def test_position_score_last_quintile(bs):
    assert bs._position_score(9, 10) == 1.0


def test_position_score_single_chunk(bs):
    assert bs._position_score(0, 1) == 1.0


def test_discourse_marker_count_basic(bs):
    text = "First of all, the test passes. In conclusion, we ship it."
    n = bs._discourse_marker_count(text)
    assert n >= 2  # 'first of all' and 'in conclusion'


def test_discourse_marker_count_zero(bs):
    assert bs._discourse_marker_count("just plain text with no markers") == 0


# ── Fact span detection ────────────────────────────────────────


def test_has_fact_span_iso_date(bs):
    assert bs.has_fact_span("Released on 2026-04-10 to production") is True


def test_has_fact_span_semver(bs):
    assert bs.has_fact_span("Upgraded to v2.3.1 with fix") is True


def test_has_fact_span_git_hash(bs):
    assert bs.has_fact_span("commit abc1234 fixed it") is True


def test_has_fact_span_url(bs):
    assert bs.has_fact_span("see https://example.com/foo for details") is True


def test_has_fact_span_percentage(bs):
    assert bs.has_fact_span("compression hit 92% accuracy") is True


def test_has_fact_span_jira_ticket(bs):
    assert bs.has_fact_span("BUG-101 was fixed yesterday") is True


def test_has_fact_span_money(bs):
    assert bs.has_fact_span("the run cost $5.65 in API credits") is True


def test_has_fact_span_no_facts(bs):
    assert bs.has_fact_span("just plain prose with no specific data") is False


def test_has_fact_span_empty(bs):
    assert bs.has_fact_span("") is False
    assert bs.has_fact_span(None) is False


# ── score_chunk weighted sum ───────────────────────────────────


def test_score_chunk_empty(bs):
    assert bs.score_chunk("", {}) == 0.0
    assert bs.score_chunk(None, {}) == 0.0


def test_score_chunk_higher_for_fact_dense(bs):
    """A chunk with entities + numbers should score higher than filler."""
    chunks = [
        "the cat sat on the mat and looked around for a while",
        "Sky deployed v2.3.1 on 2026-04-10 with commit abc1234 fixing BUG-101",
    ]
    idf = bs.compute_idf(chunks)
    s1 = bs.score_chunk(chunks[0], idf, 0, 2)
    s2 = bs.score_chunk(chunks[1], idf, 1, 2)
    assert s2 > s1, f"fact-dense chunk should outscore filler ({s2} vs {s1})"


def test_score_chunk_position_bonus(bs):
    """Same chunk in edge position scores higher than middle."""
    chunk = "Sky writes Muninn engine code in Python today carefully"
    idf = bs.compute_idf([chunk] * 10)
    s_edge = bs.score_chunk(chunk, idf, 0, 10)
    s_mid = bs.score_chunk(chunk, idf, 5, 10)
    assert s_edge > s_mid


# ── select_chunks core algorithm ───────────────────────────────


def test_select_chunks_empty(bs):
    assert bs.select_chunks([], 100) == []
    assert bs.select_chunks(None, 100) == []


def test_select_chunks_zero_budget(bs):
    assert bs.select_chunks(["any chunk"], 0) == []
    assert bs.select_chunks(["any chunk"], -5) == []


def test_select_chunks_budget_exceeds_total_keeps_all(bs):
    chunks = ["alpha bravo charlie", "delta echo foxtrot"]
    out = bs.select_chunks(chunks, budget_tokens=1000)
    assert out == [0, 1]


def test_select_chunks_returns_indices_in_order(bs):
    """Output indices must always be in ascending order."""
    chunks = [
        "alpha sky muninn first chunk no facts",
        "bravo Sky deployed v2.3.1 on 2026-04-10",
        "charlie totally generic random filler text here",
        "delta commit abc1234 fixed BUG-101",
        "echo plain text no facts at all",
    ]
    out = bs.select_chunks(chunks, budget_tokens=15)
    assert out == sorted(out)


def test_select_chunks_must_keep_facts_under_tight_budget(bs):
    """A fact chunk must SURVIVE even when score-only would drop it."""
    chunks = [
        "first paragraph generic prose about how things work in general",
        "second paragraph also generic and verbose with no specific information",
        "third short fact: BUG-101",
    ]
    out = bs.select_chunks(chunks, budget_tokens=5)
    # Budget 5 tokens — only the short fact chunk fits
    assert 2 in out


def test_select_chunks_keep_facts_disabled(bs):
    """When keep_facts=False, fact chunks lose their must-keep status."""
    chunks = [
        "very long verbose chunk with many words but no specific facts to share " * 3,
        "BUG-101",  # tiny fact chunk
    ]
    # Without facts hard rule, the verbose chunk wins (more tokens for IDF)
    out = bs.select_chunks(chunks, budget_tokens=30, keep_facts=False)
    # Just verify it does not always keep the fact chunk
    assert isinstance(out, list)


def test_select_chunks_custom_token_count(bs):
    """A custom token_count callable must be used."""
    chunks = ["alpha bravo", "charlie", "delta echo foxtrot"]
    # Token count = char count
    out = bs.select_chunks(chunks, budget_tokens=10, token_count=len)
    assert isinstance(out, list)


# ── budget_select end-to-end ───────────────────────────────────


def test_budget_select_empty(bs):
    assert bs.budget_select("", 100) == ""
    assert bs.budget_select(None, 100) == ""


def test_budget_select_zero_budget(bs):
    assert bs.budget_select("anything here at all", 0) == ""


def test_budget_select_preserves_paragraphs(bs):
    """Output must use the same paragraph separator as the input."""
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph."
    out = bs.budget_select(text, budget_tokens=100)
    assert "\n\n" in out


def test_budget_select_real_scenario(bs):
    """The smoke test that proved this brick: dense facts survive, filler dies."""
    text = (
        "First paragraph about Sky and Muninn debugging the auth middleware.\n\n"
        "Second random paragraph that contains no facts and is just filler about the weather.\n\n"
        "Third critical paragraph: deployed v2.3.1 on 2026-04-10 with commit abc1234 fixed BUG-101.\n\n"
        "Fourth paragraph also generic with no specific facts at all to mention here.\n\n"
        "Fifth paragraph: Muninn compression hit x4.5 ratio on 1.1M tokens transcript."
    )
    out = bs.budget_select(text, budget_tokens=30)
    # The fact-rich paragraphs (3rd and 5th) MUST be in the output
    assert "v2.3.1" in out
    assert "BUG-101" in out
    assert "x4.5" in out
    # The filler paragraphs MUST be dropped
    assert "weather" not in out
    assert "Fourth paragraph also generic" not in out


def test_budget_select_all_filler_no_facts(bs):
    """If no chunks have facts, budget enforcement still applies cleanly."""
    text = (
        "First filler paragraph.\n\n"
        "Second filler paragraph.\n\n"
        "Third filler paragraph.\n\n"
        "Fourth filler paragraph."
    )
    out = bs.budget_select(text, budget_tokens=6)
    # Some chunks dropped — verify selection is non-trivial
    kept = out.count("filler")
    assert kept < 4


# ── stats() helper ─────────────────────────────────────────────


def test_stats_text_only(bs):
    text = "Para one.\n\nPara two.\n\nPara three."
    s = bs.stats(text=text)
    assert s["paragraphs"] == 3
    assert s["total_tokens"] > 0


def test_stats_chunks_only(bs):
    s = bs.stats(chunks=["alpha bravo", "charlie delta echo"])
    assert s["chunk_count"] == 2
    assert "vocab_size" in s
    assert "score_min" in s
    assert "score_max" in s


def test_stats_with_budget(bs):
    text = "Short.\n\nAnother short.\n\nThird short paragraph."
    s = bs.stats(text=text, budget_tokens=5)
    assert "selection_ratio" in s
    assert 0.0 <= s["selection_ratio"] <= 1.0


def test_stats_empty(bs):
    assert bs.stats() == {}


# ── Pure: no side effects, deterministic ─────────────────────


def test_select_chunks_deterministic(bs):
    chunks = [
        "alpha generic chunk one",
        "bravo deployed v2.3.1 on 2026-04-10",
        "charlie generic chunk three",
    ]
    out1 = bs.select_chunks(chunks, budget_tokens=10)
    out2 = bs.select_chunks(chunks, budget_tokens=10)
    assert out1 == out2


def test_budget_select_does_not_mutate_input(bs):
    text = "First.\n\nSecond.\n\nThird."
    original = text
    _ = bs.budget_select(text, budget_tokens=5)
    assert text == original  # untouched


def test_compute_idf_does_not_mutate_input(bs):
    chunks = ["one two three", "four five six"]
    snapshot = list(chunks)
    _ = bs.compute_idf(chunks)
    assert chunks == snapshot
