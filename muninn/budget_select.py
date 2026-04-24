#!/usr/bin/env python3
"""Budget-driven chunk selection (BudgetMem-style L12).

PHASE B BRICK 3 (2026-04-10) — pure module, zero side effects, zero deps.

Implements the BudgetMem (arxiv 2511.04919) chunk-level selection algorithm
in pure Python. The 2024-2026 literature is unanimous: the largest gain
remaining for "regex + light NLP" compression comes from CHUNK SELECTION,
not from more token-level shaving. BudgetMem reports 72% memory savings
with only 1% quality loss on medium documents and 87% of LLMLingua's F1
on NarrativeQA — all training-free, all interpretable features.

Algorithm: split input into paragraph-sized chunks, score each chunk with
6 weighted features, then keep the highest-scoring chunks until a token
budget is reached. Hard rule: chunks containing fact spans (numbers,
dates, identifiers) are ALWAYS kept regardless of score.

Features (weights from the BudgetMem paper, exact values):

  entity_density   (0.20)  — capitalized mid-sentence words proxy for NER
                              (zero spaCy / no neural NER required)
  tfidf_mean       (0.20)  — mean TF-IDF over chunk tokens vs corpus
  position_score   (0.15)  — bonus for first/last 20% of section
  number_density   (0.15)  — fraction of tokens containing digits
  question_presence (0.10) — 1.0 if chunk has '?', else 0.0
  discourse_markers (0.10) — count of discourse markers, capped at 1.0

Total weight = 0.90; the remaining 0.10 budget is the must-keep boost
applied to chunks containing fact spans (always above any score-based cut).

This module has ZERO side effects: no I/O, no global state, no network.
forge.py --gen-props is safe here. The BUG-102 detector should not flag
any function as destructive (no path-like args, no write operations).

Sources:
- BudgetMem, arxiv 2511.04919 (2025) — the gold standard for training-free
  selective memory in long-context LLM workflows.
- Selective Context, EMNLP 2023 — the baseline for hard prompt compression.
- LongLLMLingua (2024) — long-context aware compression.
"""
import math
import re
from collections import Counter

# ── Tokenization (consistent with engine/core/dedup.py) ─────────

_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


def _tokenize(text: str) -> list:
    """Lowercased word tokens. Pure."""
    if not text or not isinstance(text, str):
        return []
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _tokenize_preserve_case(text: str) -> list:
    """Word tokens with original case. Pure. Used for entity proxy."""
    if not text or not isinstance(text, str):
        return []
    return [m.group(0) for m in _WORD_RE.finditer(text)]


# ── Discourse markers (subset of Cambridge dictionary list) ─────
# Multi-word markers come first to match before substrings.
_DISCOURSE_MARKERS = (
    "first of all", "to begin with", "in addition", "in conclusion",
    "in summary", "to summarize", "to sum up", "in other words",
    "for example", "for instance", "on the other hand", "as a result",
    "in any case", "by the way", "as a matter of fact", "needless to say",
    "firstly", "secondly", "thirdly", "moreover", "furthermore",
    "however", "nonetheless", "nevertheless", "additionally",
    "namely", "incidentally",
)


def _discourse_marker_count(text: str) -> int:
    """Count discourse markers in lowercased text. Pure."""
    if not text:
        return 0
    low = text.lower()
    count = 0
    for m in _DISCOURSE_MARKERS:
        if m in low:
            count += 1
    return count


# ── Fact span detection (delegated regex) ───────────────────────
# A chunk that contains ANY fact span is "must-keep" regardless of score.
# Same families as Muninn's L7 fact extraction — kept consistent on purpose.

_FACT_SPAN_RES = (
    # Hard facts (original)
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),                    # ISO date
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),              # slash date
    re.compile(r"\b\d+(?:\.\d+)?[KMGT]?\b"),                 # number with unit
    re.compile(r"\b\d+(?:\.\d+)?%\b"),                       # percentage
    re.compile(r"\b\$\d+(?:\.\d+)?[KMGT]?\b"),               # money
    re.compile(r"\b[a-f0-9]{7,40}\b"),                       # git hash / hex id
    re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-z]+)?\b"),     # semver
    re.compile(r"https?://\S+"),                             # url
    re.compile(r"\b[A-Z]{2,}-\d+\b"),                        # ticket id (JIRA)
    # BUG-104 fix (brick 17): soft facts
    re.compile(r"\b[a-z_][a-zA-Z0-9_]{3,}\("),               # function call site
    re.compile(r"\b[a-zA-Z_][\w.\-]*/[\w.\-/]{3,}"),         # file path
    re.compile(r"\b[A-Z][a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+\b"),  # CamelCase
    re.compile(r"`[^`\n]{3,50}`"),                           # backtick code
)


def has_fact_span(chunk: str) -> bool:
    """Return True if `chunk` contains any fact span. Pure."""
    if not chunk:
        return False
    for r in _FACT_SPAN_RES:
        if r.search(chunk):
            return True
    return False


# ── IDF computation ─────────────────────────────────────────────


def compute_idf(chunks) -> dict:
    """Build a {term: idf_score} map from a list of chunks. Pure.

    IDF formula: idf(t) = log((1 + N) / (1 + df(t))) + 1
    The +1 smoothing avoids zero on terms appearing in every chunk.
    """
    if not chunks:
        return {}
    chunks_list = [c for c in chunks if isinstance(c, str) and c]
    n = len(chunks_list)
    if n == 0:
        return {}
    df = Counter()
    for c in chunks_list:
        seen = set(_tokenize(c))
        for t in seen:
            df[t] += 1
    idf = {}
    for term, freq in df.items():
        idf[term] = math.log((1 + n) / (1 + freq)) + 1.0
    return idf


# ── Per-chunk scoring (the heart of BudgetMem) ──────────────────


def _entity_density(chunk: str) -> float:
    """Proxy for NER: capitalized mid-sentence words / total tokens.

    Pure. Skips first token of each sentence (sentence-initial cap is
    grammatical, not entity-like) and very short tokens (single capital
    letters are usually not entities).

    Sentence boundaries are detected from the ORIGINAL chunk text using
    the regex `[.!?]+\\s+` — the word-tokenizer strips punctuation, so
    we have to look at the source text to find sentence starts.
    """
    if not chunk:
        return 0.0
    # Walk the original text, not the tokens, to find sentence boundaries.
    sentences = re.split(r"[.!?]+\s+", chunk)
    total_tokens = 0
    entity_count = 0
    for sent in sentences:
        sent_tokens = _tokenize_preserve_case(sent)
        if not sent_tokens:
            continue
        total_tokens += len(sent_tokens)
        # Skip the first token of every sentence (grammatical capital)
        for t in sent_tokens[1:]:
            if len(t) >= 2 and t[0].isupper() and t[0].isalpha():
                entity_count += 1
    if total_tokens == 0:
        return 0.0
    return entity_count / total_tokens


def _tfidf_mean(chunk: str, idf_map: dict) -> float:
    """Mean TF-IDF over chunk tokens. Pure."""
    if not chunk or not idf_map:
        return 0.0
    tokens = _tokenize(chunk)
    if not tokens:
        return 0.0
    tf = Counter(tokens)
    n = len(tokens)
    tfidf_sum = 0.0
    for term, count in tf.items():
        tf_score = count / n
        idf_score = idf_map.get(term, 0.0)
        tfidf_sum += tf_score * idf_score
    return tfidf_sum / len(tf) if tf else 0.0


def _position_score(position_idx: int, total: int) -> float:
    """Bonus for first/last 20% of the document. Pure.

    Returns 1.0 for the edge zones, 0.5 for the middle.
    """
    if total <= 1:
        return 1.0
    pos_ratio = position_idx / (total - 1)
    if pos_ratio < 0.2 or pos_ratio > 0.8:
        return 1.0
    return 0.5


def _number_density(chunk: str) -> float:
    """Fraction of tokens containing at least one digit. Pure."""
    tokens = _tokenize(chunk)
    if not tokens:
        return 0.0
    digit_tokens = sum(1 for t in tokens if any(c.isdigit() for c in t))
    return digit_tokens / len(tokens)


def _question_presence(chunk: str) -> float:
    """1.0 if chunk has a '?', else 0.0. Pure."""
    return 1.0 if chunk and "?" in chunk else 0.0


def _discourse_score(chunk: str) -> float:
    """Discourse marker count, capped at 1.0 (saturating). Pure."""
    return min(_discourse_marker_count(chunk) / 3.0, 1.0)


def score_chunk(
    chunk: str,
    idf_map: dict,
    position_idx: int = 0,
    total_chunks: int = 1,
) -> float:
    """6-feature BudgetMem salience score in [0, ~1]. Pure.

    Args:
        chunk: the text chunk to score.
        idf_map: dict from compute_idf() over the same corpus.
        position_idx: 0-based index of this chunk in the document.
        total_chunks: total chunks in the document.

    Returns:
        float salience score. Higher = more important.
    """
    if not chunk or not isinstance(chunk, str):
        return 0.0
    return (
        0.20 * _entity_density(chunk)
        + 0.20 * _tfidf_mean(chunk, idf_map)
        + 0.15 * _position_score(position_idx, total_chunks)
        + 0.15 * _number_density(chunk)
        + 0.10 * _question_presence(chunk)
        + 0.10 * _discourse_score(chunk)
    )


# ── Selection under a budget ────────────────────────────────────


def _default_token_count(text: str) -> int:
    """Crude word-based token count. Pure. Used when no tokenizer is given."""
    return len(_tokenize(text))


def select_chunks(
    chunks,
    budget_tokens: int,
    token_count=None,
    keep_facts: bool = True,
) -> list:
    """Select chunks under a token budget, returning the kept INDICES.

    Pure function. The selection algorithm:
      1. Compute IDF over the chunks.
      2. Score every chunk.
      3. Mark must-keep chunks (those with fact spans, if keep_facts=True).
      4. Sort the rest by score descending.
      5. Add chunks (must-keep first, then by score) until the next chunk
         would exceed `budget_tokens`.
      6. Return kept indices in ORIGINAL ORDER (preserves readability).

    Args:
        chunks: iterable of strings.
        budget_tokens: max total tokens to keep.
        token_count: optional callable(text) -> int. Defaults to word count.
        keep_facts: if True, chunks with fact spans bypass the score filter.

    Returns:
        sorted list[int] of indices of chunks to keep.
    """
    if not chunks:
        return []
    if budget_tokens <= 0:
        return []
    if token_count is None:
        token_count = _default_token_count
    chunks_list = [c if isinstance(c, str) else "" for c in chunks]
    n = len(chunks_list)
    if n == 0:
        return []

    idf_map = compute_idf(chunks_list)
    scores = [
        score_chunk(c, idf_map, i, n)
        for i, c in enumerate(chunks_list)
    ]
    sizes = [token_count(c) for c in chunks_list]

    must_keep = set()
    if keep_facts:
        for i, c in enumerate(chunks_list):
            if has_fact_span(c):
                must_keep.add(i)

    # Phase 1: must-keep chunks first, capped at budget
    kept = set()
    used = 0
    for i in sorted(must_keep, key=lambda j: -scores[j]):
        if used + sizes[i] <= budget_tokens:
            kept.add(i)
            used += sizes[i]

    # Phase 2: fill remaining budget with score-sorted others
    others = [
        i for i in range(n) if i not in kept
    ]
    others.sort(key=lambda j: -scores[j])
    for i in others:
        if used + sizes[i] <= budget_tokens:
            kept.add(i)
            used += sizes[i]

    return sorted(kept)


def budget_select(
    text: str,
    budget_tokens: int,
    token_count=None,
    keep_facts: bool = True,
    separator: str = "\n\n",
) -> str:
    """Apply chunk selection to a text, returning the compressed result.

    Pure function. Splits the text into paragraphs (default `\\n\\n`),
    runs select_chunks(), and rejoins the kept chunks in original order.
    """
    if not isinstance(text, str) or not text:
        return text or ""
    if budget_tokens <= 0:
        return ""
    chunks = re.split(r"\n\s*\n", text)
    kept_indices = select_chunks(
        chunks,
        budget_tokens=budget_tokens,
        token_count=token_count,
        keep_facts=keep_facts,
    )
    return separator.join(chunks[i] for i in kept_indices)


def stats(text: str = None, chunks = None, budget_tokens: int = None) -> dict:
    """Diagnostic stats. Pure.

    If `text` is given: returns paragraph count + total tokens.
    If `chunks` is given: returns IDF map size + score distribution.
    If `budget_tokens` is given (with text or chunks): returns selection
    ratio without mutation.
    """
    out = {}
    chunks_list = None
    if text is not None:
        chunks_list = re.split(r"\n\s*\n", text)
        out["paragraphs"] = len(chunks_list)
        out["total_tokens"] = sum(_default_token_count(c) for c in chunks_list)
    if chunks is not None:
        chunks_list = [c if isinstance(c, str) else "" for c in chunks]
        out["chunk_count"] = len(chunks_list)
        idf = compute_idf(chunks_list)
        out["vocab_size"] = len(idf)
        scores = [
            score_chunk(c, idf, i, len(chunks_list))
            for i, c in enumerate(chunks_list)
        ]
        if scores:
            out["score_min"] = min(scores)
            out["score_max"] = max(scores)
            out["score_mean"] = sum(scores) / len(scores)
    if budget_tokens is not None and chunks_list is not None:
        kept = select_chunks(chunks_list, budget_tokens)
        out["kept_count"] = len(kept)
        out["selection_ratio"] = (
            len(kept) / len(chunks_list) if chunks_list else 0.0
        )
    return out
