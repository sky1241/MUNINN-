#!/usr/bin/env python3
"""Vendored word lists for L2 filler / hedge / weasel stripping.

PHASE B BRICK 1 (2026-04-10) — pure data module, no side effects.

The lists below are vendored verbatim from the MIT-licensed `words/*` repos
on GitHub (used by the unified compression literature in 2024–2026, e.g.
BudgetMem, CompactPrompt). They are kept as raw constants so we can audit
exactly what we add to Muninn's compression vocabulary, layer by layer.

Sources (all MIT-licensed):
- github.com/words/fillers   (80 English filler adverbs/hedges)
- github.com/words/hedges    (~150 English hedge words/phrases)
- github.com/words/weasels   (116 English weasel words)
- Cambridge dictionary discourse markers list (rhetorical scaffolding)

The MIT lists are intentionally NOT a drop-in replacement for the existing
hand-picked `_FILLER` in `muninn_layers.compress_line()`. Many words in the
raw lists carry semantic content in compression context — e.g.:

  - `all`, `most`, `few`, `several`, `many`         → quantifiers, change meaning
  - `back`, `down`, `up`, `over`                    → directions, often nouns
  - `find`, `say`, `tend`, `think`, `wanted`        → verbs that carry the action
  - `excellent`, `huge`, `tiny`, `vast`             → magnitudes that matter
  - `believe`, `assume`, `consider`, `understand`   → epistemic state, often the point

We therefore expose THREE tiers:

  TIER1_SAFE     — extra-conservative subset, safe for any text
  TIER2_MODERATE — adverbs of intensification, mostly safe
  TIER3_RAW      — full vendored MIT lists (USE AT YOUR OWN RISK)

Only TIER1_SAFE is intended for default L2 extension. TIER2 is opt-in for
chat-log / meeting compression where over-modulation is the dominant noise.
TIER3 is exposed for research and benchmarking only.

This module has ZERO side effects: no I/O, no global state mutation, no
network. forge.py --gen-props is safe here (BUG-102 detector should
correctly recognize all functions as pure).
"""

# ── Vendored verbatim from github.com/words/fillers (MIT) ──────────
# 80 English filler words. Order preserved from upstream `data.txt`.
MIT_FILLERS_EN: tuple = (
    "absolutely", "actual", "actually", "amazing", "anyway", "apparently",
    "approximately", "badly", "basically", "begin", "certainly", "clearly",
    "completely", "definitely", "easily", "effectively", "entirely",
    "especially", "essentially", "exactly", "extremely", "fairly", "frankly",
    "frequently", "fully", "generally", "hardly", "heavily", "highly",
    "hopefully", "just", "largely", "like", "literally", "maybe", "might",
    "most", "mostly", "much", "necessarily", "nicely", "obviously", "ok",
    "okay", "particularly", "perhaps", "possibly", "practically", "precisely",
    "primarily", "probably", "quite", "rather", "real", "really", "relatively",
    "right", "seriously", "significantly", "simply", "slightly", "so",
    "specifically", "start", "strongly", "stuff", "surely", "things", "too",
    "totally", "truly", "try", "typically", "ultimately", "usually", "very",
    "virtually", "well", "whatever", "whenever", "wherever", "whoever",
    "widely",
)

# ── Vendored verbatim from github.com/words/hedges (MIT) ───────────
# English hedge words and phrases. Multi-word entries are kept as-is and
# are matched as compiled phrase regex (whitespace-tolerant).
MIT_HEDGES_EN: tuple = (
    "a bit", "about", "actually", "allege", "alleged", "almost",
    "almost never", "always", "and all that", "and so forth", "apparent",
    "apparently", "appear", "appear to be", "appeared", "appears",
    "approximately", "around", "assume", "assumed", "assumes", "assumption",
    "at least", "basically", "be sure", "believe", "believed", "believes",
    "bunch", "can", "certain", "certainly", "clear", "clearly", "conceivably",
    "consider", "considered", "considers", "consistent with", "could",
    "couple", "definite", "definitely", "diagnostic", "don't know", "doubt",
    "doubtful", "effectively", "estimate", "estimated", "estimates",
    "et cetera", "evidently", "fairly", "few", "find", "finds", "found",
    "frequently", "generally", "guess", "guessed", "guesses", "hopefully",
    "if i'm understanding you correctly", "improbable", "in general",
    "in my mind", "in my opinion", "in my understanding", "in my view",
    "inconclusive", "indicate", "kind of", "largely", "like", "likely",
    "little", "look like", "looks like", "mainly", "many", "may", "maybe",
    "might", "more or less", "most", "mostly", "much", "must", "my impression",
    "my thinking is", "my understanding is", "necessarily", "occasionally",
    "often", "overall", "partially", "perhaps", "possibility", "possible",
    "possibly", "practically", "presumable", "presumably", "pretty",
    "probability", "probable", "probably", "quite", "quite clearly", "rare",
    "rarely", "rather", "read", "really", "roughly", "say", "says", "seem",
    "seemed", "seems", "seldom", "several", "should", "so far", "some",
    "somebody", "somehow", "someone", "something", "something or other",
    "sometimes", "somewhat", "somewhere", "sort of", "speculate",
    "speculated", "speculates", "suggest", "suggested", "suggestive",
    "suggests", "suppose", "supposed", "supposedly", "supposes", "surely",
    "tend", "their impression", "think", "thinks", "thought", "understand",
    "understands", "understood", "unlikely", "unsure", "usually", "virtually",
    "will", "would",
)

# ── Vendored verbatim from github.com/words/weasels (MIT) ──────────
# 116 English weasel words. Several entries overlap with hedges/fillers
# (e.g. "actually") which is fine — duplicates are de-duped at use time.
MIT_WEASELS_EN: tuple = (
    "a lot", "about", "acts", "again", "all", "almost", "already", "also",
    "anyway", "appeared", "appears", "are a number", "arguably", "back",
    "be able to", "began", "believed", "better", "bit", "clearly", "close",
    "combats", "completely", "considered", "could", "decided", "down",
    "effective", "efficient", "enough", "even", "ever", "exceedingly",
    "excellent", "expert", "experts", "extremely", "fairly", "far", "felt",
    "few", "gains", "heard", "helps", "huge", "improved", "interestingly",
    "is a number", "is like", "just", "knew", "largely", "like", "linked to",
    "literally", "looked", "looks", "lots", "many", "might", "most", "mostly",
    "not rocket science", "noticed", "often", "only", "outside the box",
    "over", "own", "pretty", "probably", "quite", "rather", "real",
    "realised", "realized", "really", "recognised", "recognized", "relatively",
    "remarkably", "reportedly", "saw", "seemed", "seems", "several",
    "significantly", "smelled", "so", "some", "somehow", "sort", "started",
    "still", "substantially", "supports", "supposed", "surprisingly", "that",
    "then", "thought", "tiny", "touched", "understood", "up", "useful",
    "various", "vast", "very", "virtually", "wanted", "watched", "well",
    "wished", "wondered", "works",
)

# ── Discourse markers (Cambridge dictionary, rhetorical scaffolding) ──
# Multi-word phrases that introduce a structural beat in the text but
# carry no factual content on their own. Safe to drop in 99% of cases.
DISCOURSE_MARKERS_EN: tuple = (
    "first of all", "firstly", "to begin with", "to start with",
    "in the first place", "for one thing", "to start", "first",
    "secondly", "thirdly", "in addition", "moreover", "furthermore",
    "what is more", "on top of that", "additionally",
    "in conclusion", "in summary", "to summarize", "to sum up",
    "to conclude", "all in all", "all things considered", "in short",
    "in brief", "in other words", "that is to say", "namely",
    "for example", "for instance", "such as", "as an example",
    "on the other hand", "in contrast", "by contrast", "however",
    "nonetheless", "nevertheless", "even so",
    "as a matter of fact", "as it happens", "as a result",
    "in any case", "in any event", "at any rate",
    "by the way", "incidentally", "speaking of",
    "needless to say", "of course",
)

# ── French fillers (community list, FOLKLORE per the deep research) ──
# These tics work on transcripts of French native speakers (Sky's case).
# Conservative subset — multi-word entries handled at use time.
FRENCH_FILLERS: tuple = (
    "quoi", "bon", "ben", "bah", "hein", "euh",
    "en gros", "en fait", "du coup", "tu vois", "tu sais",
    "t'as vu", "t'as compris", "tu comprends",
    "genre", "voilà", "là",
    "et puis", "mais alors", "enfin", "après",
    "bref",
)

# ── TIER 1 — extra-conservative, safe for any text ────────────────
# These are the words from the MIT lists that:
#   1. Carry NO factual content
#   2. Have NO common alternative meaning (noun/verb usage in our domain)
#   3. Are NOT already in Muninn's hand-picked _FILLER
#   4. Were not flagged as risky by the over-modulation studies
# When stripped, the remaining text reads as more direct without losing
# any information. Tier 1 is the only tier auto-applied to L2 by default.
L2_TIER1_SAFE: tuple = (
    # Adverbs of intensification (zero info)
    "absolutely", "amazingly", "completely", "definitely", "entirely",
    "extremely", "frankly", "fully", "literally", "particularly",
    "precisely", "remarkably", "seriously", "strongly", "totally",
    "truly", "ultimately", "virtually", "widely", "exceedingly",
    "interestingly", "surprisingly", "noticeably", "substantially",
    # Hedges with no factual content
    "apparently", "evidently", "hopefully", "presumably", "supposedly",
    "reportedly", "arguably", "conceivably",
    # Discourse fillers (zero info)
    "frankly speaking", "to be honest", "to be fair",
    "in my opinion", "in my view", "in my mind",
    "needless to say", "as a matter of fact", "as it happens",
    "by the way", "incidentally",
)

# ── TIER 2 — moderate, mostly safe for chat / meetings ────────────
# Adds quantifier-adjacent words and softer hedges. Still avoids true
# quantifiers (`all`, `many`, `few`, `some` etc.) which CHANGE meaning.
L2_TIER2_MODERATE: tuple = L2_TIER1_SAFE + (
    "actually", "basically", "essentially", "obviously", "really",
    "simply", "clearly", "certainly", "generally", "typically",
    "usually", "frequently", "occasionally", "sometimes", "rarely",
    "approximately", "roughly", "more or less", "kind of", "sort of",
)

# ── TIER 3 — full raw vendored lists (research only) ──────────────
# Use this only when benchmarking against the literature or when you
# explicitly want maximum-aggressive stripping and accept the meaning
# changes. Includes quantifiers, magnitudes, and ambiguous tokens.
def get_tier3_raw() -> tuple:
    """Return de-duped union of all vendored MIT lists.

    Pure function. Returns a tuple. The result is sorted by descending
    length so multi-word phrases are matched before their substrings
    (regex matching order matters).
    """
    seen = set()
    out = []
    for word in MIT_FILLERS_EN + MIT_HEDGES_EN + MIT_WEASELS_EN:
        if word not in seen:
            seen.add(word)
            out.append(word)
    out.sort(key=len, reverse=True)
    return tuple(out)


# ── Words that must NEVER be added to any tier — for sanity tests ──
# These are in the MIT lists but ARE meaningful in compression context.
# The Muninn-curated tiers MUST NOT contain any of these.
DANGEROUS_NEVER_ADD: frozenset = frozenset({
    # Quantifiers (change cardinality)
    "all", "any", "each", "every", "none", "many", "few", "several",
    "some", "most", "all", "both", "either", "neither",
    # Magnitudes (carry the metric)
    "huge", "vast", "tiny", "excellent", "useful", "effective",
    # Verbs that carry the action
    "find", "found", "say", "says", "tend", "think", "thinks", "thought",
    "wanted", "knew", "saw", "noticed", "decided", "looked", "watched",
    "began", "started", "felt", "smelled", "touched", "heard",
    "believe", "believes", "believed", "assume", "assumed", "assumes",
    "consider", "considered", "considers", "understand", "understands",
    "understood", "guess", "guessed",
    # Modals (epistemic state)
    "can", "could", "may", "might", "should", "will", "would", "must",
    # Directional / positional
    "back", "down", "up", "over", "out", "in", "off", "on", "around",
    # Negation-adjacent
    "improbable", "unlikely", "doubtful", "inconclusive", "unsure",
    # Logical connectors
    "but", "and", "or", "if", "then", "that", "which",
})


def get_safe_filler_patterns(tier: str = "tier1") -> list:
    """Return a list of compiled-friendly regex patterns for a given tier.

    Pure function. Builds `\\b<word>\\b` patterns for single words and
    `\\b<word1>\\s+<word2>\\b` patterns for multi-word phrases. The caller
    is responsible for compilation and `re.IGNORECASE` flag.

    tier: one of "tier1", "tier2", "tier3", "discourse", "french".
    """
    import re as _re
    if tier == "tier1":
        words = L2_TIER1_SAFE
    elif tier == "tier2":
        words = L2_TIER2_MODERATE
    elif tier == "tier3":
        words = get_tier3_raw()
    elif tier == "discourse":
        words = DISCOURSE_MARKERS_EN
    elif tier == "french":
        words = FRENCH_FILLERS
    else:
        raise ValueError(
            f"unknown tier {tier!r}; expected one of "
            "tier1, tier2, tier3, discourse, french"
        )

    patterns = []
    for w in words:
        if " " in w or "'" in w:
            # Multi-word: tolerate variable whitespace, escape apostrophes
            parts = [_re.escape(p) for p in w.split()]
            pattern = r"\b" + r"\s+".join(parts) + r"\b"
        else:
            pattern = r"\b" + _re.escape(w) + r"\b"
        patterns.append(pattern)
    return patterns


def stats() -> dict:
    """Return counts for every list and tier. Pure, no side effects."""
    return {
        "mit_fillers_en": len(MIT_FILLERS_EN),
        "mit_hedges_en": len(MIT_HEDGES_EN),
        "mit_weasels_en": len(MIT_WEASELS_EN),
        "discourse_markers_en": len(DISCOURSE_MARKERS_EN),
        "french_fillers": len(FRENCH_FILLERS),
        "tier1_safe": len(L2_TIER1_SAFE),
        "tier2_moderate": len(L2_TIER2_MODERATE),
        "tier3_raw_unique": len(get_tier3_raw()),
        "dangerous_never_add": len(DANGEROUS_NEVER_ADD),
    }
