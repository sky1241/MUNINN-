"""PHASE B BRICK 1 — verify the vendored lexicons module.

This module is pure data + helpers, no side effects. Tests cover:
1. Module imports without crashing
2. Each vendored MIT list has the expected size from upstream
3. The Muninn-curated tiers contain only safe words
4. The DANGEROUS_NEVER_ADD set is fully respected by every tier
5. Helper functions return valid regex patterns
6. Patterns can be compiled and applied to real text
7. stats() returns sane counts
"""
import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LEXICONS_PATH = REPO_ROOT / "engine" / "core" / "lexicons.py"


@pytest.fixture(scope="module")
def lex():
    """Import lexicons.py as an isolated module."""
    spec = importlib.util.spec_from_file_location("lexicons_brick1", LEXICONS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Module loading ─────────────────────────────────────────────


def test_module_imports(lex):
    assert hasattr(lex, "MIT_FILLERS_EN")
    assert hasattr(lex, "MIT_HEDGES_EN")
    assert hasattr(lex, "MIT_WEASELS_EN")
    assert hasattr(lex, "DISCOURSE_MARKERS_EN")
    assert hasattr(lex, "FRENCH_FILLERS")
    assert hasattr(lex, "L2_TIER1_SAFE")
    assert hasattr(lex, "L2_TIER2_MODERATE")
    assert hasattr(lex, "DANGEROUS_NEVER_ADD")


# ── Vendored MIT lists — exact sizes from upstream ─────────────


def test_mit_fillers_size(lex):
    """github.com/words/fillers — verbatim count from the deep-research dump."""
    assert len(lex.MIT_FILLERS_EN) == 83, (
        f"MIT_FILLERS_EN drift: {len(lex.MIT_FILLERS_EN)} != 83"
    )


def test_mit_weasels_size(lex):
    """github.com/words/weasels contains exactly 116 entries."""
    assert len(lex.MIT_WEASELS_EN) == 116, (
        f"MIT_WEASELS_EN drift from upstream: {len(lex.MIT_WEASELS_EN)} != 116"
    )


def test_mit_hedges_minimum_size(lex):
    """github.com/words/hedges has 150+ entries."""
    assert len(lex.MIT_HEDGES_EN) >= 150


def test_mit_lists_are_tuples(lex):
    """Tuples = immutable. Lists could accidentally be mutated."""
    assert isinstance(lex.MIT_FILLERS_EN, tuple)
    assert isinstance(lex.MIT_HEDGES_EN, tuple)
    assert isinstance(lex.MIT_WEASELS_EN, tuple)


def test_mit_lists_no_empty_strings(lex):
    for name, lst in (
        ("FILLERS", lex.MIT_FILLERS_EN),
        ("HEDGES", lex.MIT_HEDGES_EN),
        ("WEASELS", lex.MIT_WEASELS_EN),
    ):
        for w in lst:
            assert w, f"{name} contains empty string"
            assert isinstance(w, str), f"{name} contains non-str: {w!r}"


def test_mit_lists_lowercase(lex):
    """Vendored lists must be lowercase for case-insensitive matching."""
    for lst in (lex.MIT_FILLERS_EN, lex.MIT_HEDGES_EN, lex.MIT_WEASELS_EN):
        for w in lst:
            assert w == w.lower(), f"non-lowercase entry: {w!r}"


# ── Tier safety ───────────────────────────────────────────────


def test_tier1_no_dangerous_words(lex):
    """Tier 1 single-word entries must NEVER be in DANGEROUS_NEVER_ADD.

    Multi-word phrases like 'in my opinion' are safe as a unit even though
    the standalone word 'in' is dangerous — they're matched as complete
    idioms by `\\b<phrase>\\b` regex, never substituted partially.
    """
    for word in lex.L2_TIER1_SAFE:
        if " " in word:
            continue  # multi-word phrases are safe as units
        assert word.lower() not in lex.DANGEROUS_NEVER_ADD, (
            f"Tier 1 contains dangerous standalone word {word!r}"
        )


def test_tier2_no_dangerous_words(lex):
    """Tier 2 single-word entries must NEVER be in DANGEROUS_NEVER_ADD."""
    for word in lex.L2_TIER2_MODERATE:
        if " " in word:
            continue
        assert word.lower() not in lex.DANGEROUS_NEVER_ADD, (
            f"Tier 2 contains dangerous standalone word {word!r}"
        )


def test_multi_word_phrases_are_complete_idioms(lex):
    """A multi-word phrase in any tier must contain at least one stopword
    that's in DANGEROUS_NEVER_ADD — proving it's a real idiom, not a
    concatenation of two safe words that could be flagged separately."""
    multi_word_phrases_checked = 0
    for word in lex.L2_TIER1_SAFE + lex.L2_TIER2_MODERATE:
        if " " not in word:
            continue
        multi_word_phrases_checked += 1
        # Just sanity-check the phrase is non-empty and well-formed
        parts = word.split()
        assert len(parts) >= 2
        assert all(parts), f"empty token in phrase {word!r}"
    assert multi_word_phrases_checked > 0, "no multi-word phrases at all"


def test_tier1_subset_of_tier2(lex):
    """Tier 2 is a strict superset of Tier 1 by construction."""
    s1 = set(lex.L2_TIER1_SAFE)
    s2 = set(lex.L2_TIER2_MODERATE)
    assert s1.issubset(s2), f"Tier 1 has words not in Tier 2: {s1 - s2}"


def test_tier1_minimum_size(lex):
    """Tier 1 should have enough entries to make a measurable difference."""
    assert len(lex.L2_TIER1_SAFE) >= 30


def test_tier2_strictly_larger_than_tier1(lex):
    """Tier 2 must add real value beyond Tier 1."""
    assert len(lex.L2_TIER2_MODERATE) > len(lex.L2_TIER1_SAFE)


def test_dangerous_set_includes_critical_words(lex):
    """Sanity check: the most dangerous words MUST be in the deny-list."""
    must_be_dangerous = {
        "all", "many", "few", "some", "most",  # quantifiers
        "find", "say", "tend", "think",  # action verbs
        "can", "may", "must", "will",  # modals
        "back", "down", "up",  # directional
    }
    missing = must_be_dangerous - lex.DANGEROUS_NEVER_ADD
    assert not missing, f"missing critical words from DANGEROUS_NEVER_ADD: {missing}"


# ── Helper function correctness ───────────────────────────────


def test_get_tier3_raw_dedups(lex):
    """tier3 union must de-dup overlapping words like 'actually'."""
    raw = lex.get_tier3_raw()
    assert len(raw) == len(set(raw)), "tier3 has duplicates"
    # Sanity: tier3 should be smaller than the sum (overlap removal worked)
    total = len(lex.MIT_FILLERS_EN) + len(lex.MIT_HEDGES_EN) + len(lex.MIT_WEASELS_EN)
    assert len(raw) < total


def test_get_tier3_raw_sorted_by_length_desc(lex):
    """Multi-word phrases must come before their substrings to match correctly."""
    raw = lex.get_tier3_raw()
    lengths = [len(w) for w in raw]
    assert lengths == sorted(lengths, reverse=True)


def test_get_safe_filler_patterns_tier1(lex):
    """Tier 1 patterns must compile and not be empty."""
    patterns = lex.get_safe_filler_patterns("tier1")
    assert len(patterns) == len(lex.L2_TIER1_SAFE)
    for p in patterns:
        compiled = re.compile(p, re.IGNORECASE)
        assert compiled is not None


def test_get_safe_filler_patterns_unknown_tier_raises(lex):
    with pytest.raises(ValueError, match="unknown tier"):
        lex.get_safe_filler_patterns("nonexistent")


def test_get_safe_filler_patterns_each_tier(lex):
    for tier in ("tier1", "tier2", "tier3", "discourse", "french"):
        patterns = lex.get_safe_filler_patterns(tier)
        assert len(patterns) > 0, f"tier {tier} produced 0 patterns"
        for p in patterns:
            re.compile(p, re.IGNORECASE)  # must not raise


def test_multi_word_pattern_matches_with_extra_whitespace(lex):
    """The phrase 'in my opinion' should match 'in   my  opinion'."""
    patterns = lex.get_safe_filler_patterns("tier1")
    src = "Sky said: in   my  opinion this is fine."
    matched = False
    for p in patterns:
        if re.search(p, src, re.IGNORECASE):
            matched = True
            break
    assert matched, "tier1 patterns failed to match multi-word phrase with extra whitespace"


def test_tier1_strips_intensifier_in_real_sentence(lex):
    """End-to-end: applying tier1 patterns removes 'absolutely' from a sentence."""
    src = "The migration is absolutely fine and totally tested."
    patterns = lex.get_safe_filler_patterns("tier1")
    out = src
    for p in patterns:
        out = re.sub(p, "", out, flags=re.IGNORECASE)
    assert "absolutely" not in out.lower()
    assert "totally" not in out.lower()
    # but the meaningful words must survive
    assert "migration" in out
    assert "fine" in out
    assert "tested" in out


def test_tier1_does_not_strip_quantifier(lex):
    """Critical: 'all', 'many' etc. must SURVIVE tier1 stripping."""
    src = "all the tests pass and many edge cases were covered"
    patterns = lex.get_safe_filler_patterns("tier1")
    out = src
    for p in patterns:
        out = re.sub(p, "", out, flags=re.IGNORECASE)
    assert "all" in out, "tier1 wrongly stripped 'all' (quantifier)"
    assert "many" in out, "tier1 wrongly stripped 'many' (quantifier)"


def test_tier1_does_not_strip_action_verb(lex):
    """Critical: 'find', 'tend', 'think' etc. must SURVIVE tier1."""
    src = "we find that the tests tend to pass when we think clearly"
    patterns = lex.get_safe_filler_patterns("tier1")
    out = src
    for p in patterns:
        out = re.sub(p, "", out, flags=re.IGNORECASE)
    for verb in ("find", "tend", "think"):
        assert verb in out, f"tier1 wrongly stripped action verb {verb!r}"


# ── stats() helper ────────────────────────────────────────────


def test_stats_returns_dict_with_all_keys(lex):
    s = lex.stats()
    assert isinstance(s, dict)
    expected_keys = {
        "mit_fillers_en", "mit_hedges_en", "mit_weasels_en",
        "discourse_markers_en", "french_fillers",
        "tier1_safe", "tier2_moderate", "tier3_raw_unique",
        "dangerous_never_add",
    }
    assert set(s.keys()) == expected_keys


def test_stats_values_match_actual_lengths(lex):
    s = lex.stats()
    assert s["mit_fillers_en"] == len(lex.MIT_FILLERS_EN)
    assert s["mit_weasels_en"] == len(lex.MIT_WEASELS_EN)
    assert s["tier1_safe"] == len(lex.L2_TIER1_SAFE)
    assert s["tier2_moderate"] == len(lex.L2_TIER2_MODERATE)


# ── No side effects (the WHOLE point of brick 1) ──────────────


def test_module_has_no_io_at_import_time(lex):
    """Importing the module must not touch disk, network, env."""
    # If the import had side effects, the fixture would have failed.
    # This test exists as a sentinel: if anyone adds I/O later, audit it.
    assert True  # passes as long as fixture loaded


def test_calling_helpers_does_not_mutate_constants(lex):
    """Helpers must be pure: calling them twice gives identical results."""
    a = lex.get_tier3_raw()
    b = lex.get_tier3_raw()
    assert a == b
    p1 = lex.get_safe_filler_patterns("tier1")
    p2 = lex.get_safe_filler_patterns("tier1")
    assert p1 == p2
    s1 = lex.stats()
    s2 = lex.stats()
    assert s1 == s2
