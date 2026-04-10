#!/usr/bin/env python3
"""SimHash near-duplicate detection for line/paragraph-level dedup.

PHASE B BRICK 2 (2026-04-10) — pure module, zero side effects, zero deps.

Charikar's SimHash (STOC 2002) is a locality-sensitive hash that maps
similar inputs to similar fingerprints. Unlike Muninn's existing P26/P27
filters which only catch EXACT duplicates by hash, SimHash catches PARAPHRASES,
"the same idea re-said with different words", and other semantic-near
duplicates. This is exactly the regime where regex-only systems leak the
most information in agent transcripts and chat logs.

The 2024-2026 literature (BudgetMem, CompactPrompt, text-dedup) consistently
treats SimHash as the right primitive for "training-free" semantic dedup
in pre-LLM compression pipelines.

Algorithm (Charikar 2002):
  1. Extract features from the text (word k-shingles in our case).
  2. Hash each feature to a B-bit integer (blake2b, in stdlib).
  3. For each bit position 0..B-1, sum +1 or -1 based on the feature's bit.
  4. Fingerprint bit_i = 1 if sum_i > 0 else 0.
  5. Two texts are near-duplicates iff hamming_distance(fp_a, fp_b) <= k.

Default parameters:
  - bits = 64    (sweet spot per the literature)
  - shingle_size = 4   (word 4-grams; lower = stricter, higher = noisier)
  - threshold = 3      (max hamming distance for "near duplicate")

A threshold of 3 on 64-bit fingerprints corresponds roughly to "two texts
share 95% of their semantic features" — empirically a good operating point
for Muninn's transcript / chat-log use case (validated in tests).

This module has ZERO side effects: no I/O, no global state, no network.
forge.py --gen-props is safe here. The BUG-102 detector should not flag
any function as destructive.

Sources:
- Charikar 2002, "Similarity Estimation Techniques from Rounding Algorithms"
- text-dedup (PyPI Dec 2025) — modern reference, MIT
- seomoz/simhash-py — C++ extension if perf becomes an issue
"""
import hashlib
import re

# ── Tokenization ─────────────────────────────────────────────────

# Word boundary regex — same as Muninn's L7 fact extraction (consistency).
_WORD_RE = re.compile(r"\b\w+\b", re.UNICODE)


def _tokenize(text: str) -> list:
    """Split text into lowercased word tokens. Pure."""
    if not text:
        return []
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _shingles(tokens: list, k: int = 4) -> list:
    """Return k-shingles (sliding windows of k tokens). Pure.

    For texts shorter than k tokens, fall back to token-level features
    so the fingerprint is still meaningful.
    """
    if not tokens:
        return []
    if len(tokens) < k or k <= 1:
        return list(tokens)
    return [" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]


# ── SimHash core ─────────────────────────────────────────────────

# Using blake2b from hashlib (stdlib, fast, secure-enough for hashing).
def _hash_feature(feature: str, bits: int) -> int:
    """Hash a string feature to a `bits`-bit integer. Pure.

    blake2b is in the stdlib and supports an arbitrary digest_size up to 64.
    For 64-bit hashes we read 8 bytes; for 128-bit, 16 bytes.
    """
    digest_bytes = (bits + 7) // 8
    h = hashlib.blake2b(feature.encode("utf-8"), digest_size=digest_bytes)
    return int.from_bytes(h.digest(), "big")


def simhash(text: str, bits: int = 64, shingle_size: int = 4) -> int:
    """Compute Charikar SimHash fingerprint of `text`.

    Pure function. Returns an integer in [0, 2^bits).
    Empty text returns 0.

    Args:
        text: input string.
        bits: fingerprint width (32, 64, or 128). Default 64.
        shingle_size: word k-gram size for feature extraction. Default 4.
    """
    if not isinstance(text, str) or not text:
        return 0
    if bits not in (32, 64, 128):
        raise ValueError(f"bits must be 32, 64, or 128; got {bits}")
    if shingle_size < 1:
        raise ValueError(f"shingle_size must be >= 1; got {shingle_size}")

    tokens = _tokenize(text)
    features = _shingles(tokens, k=shingle_size)
    if not features:
        return 0

    # Sum +/-1 for each bit position across all feature hashes.
    sums = [0] * bits
    for feat in features:
        h = _hash_feature(feat, bits)
        for i in range(bits):
            if (h >> i) & 1:
                sums[i] += 1
            else:
                sums[i] -= 1

    # Fingerprint: bit_i = 1 iff sum_i > 0
    fp = 0
    for i in range(bits):
        if sums[i] > 0:
            fp |= 1 << i
    return fp


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two integers. Pure."""
    if not isinstance(a, int) or not isinstance(b, int):
        raise TypeError("hamming_distance requires int inputs")
    return (a ^ b).bit_count()


def similar(
    a: str,
    b: str,
    threshold: int = 3,
    bits: int = 64,
    shingle_size: int = 4,
) -> bool:
    """Return True iff a and b are near-duplicates (hamming <= threshold).

    Pure. Empty inputs return False (cannot dedup empty content).
    """
    if not a or not b:
        return False
    fp_a = simhash(a, bits=bits, shingle_size=shingle_size)
    fp_b = simhash(b, bits=bits, shingle_size=shingle_size)
    return hamming_distance(fp_a, fp_b) <= threshold


# ── Sequence-level dedup ─────────────────────────────────────────


def dedup_lines(
    lines,
    threshold: int = 3,
    bits: int = 64,
    shingle_size: int = 4,
    min_length: int = 20,
) -> list:
    """Remove near-duplicate lines from a sequence, keeping the FIRST occurrence.

    Pure function. Order is preserved for the kept lines.

    Args:
        lines: iterable of strings.
        threshold: max hamming distance for "duplicate" classification.
        bits: SimHash width.
        shingle_size: word k-gram size.
        min_length: lines shorter than this (in chars) are not deduped — too
            short means too few shingles means meaningless fingerprint.

    Returns:
        list[str] of kept lines, in original order.
    """
    if lines is None:
        return []
    out = []
    seen_fps = []  # list of (fp, original_idx) — small N expected (<10K)
    for line in lines:
        if not isinstance(line, str):
            continue
        if len(line) < min_length:
            # Short lines pass through unchanged — too noisy to fingerprint
            out.append(line)
            continue
        fp = simhash(line, bits=bits, shingle_size=shingle_size)
        is_dup = False
        for prev_fp in seen_fps:
            if hamming_distance(fp, prev_fp) <= threshold:
                is_dup = True
                break
        if not is_dup:
            seen_fps.append(fp)
            out.append(line)
    return out


def dedup_paragraphs(
    text: str,
    threshold: int = 3,
    bits: int = 64,
    shingle_size: int = 4,
    min_length: int = 50,
) -> str:
    """Split text into paragraphs (by blank lines), dedup, rejoin.

    Pure. Returns a string with the same paragraph separator (\\n\\n).
    """
    if not isinstance(text, str) or not text:
        return text or ""
    paragraphs = re.split(r"\n\s*\n", text)
    kept = dedup_lines(
        paragraphs,
        threshold=threshold,
        bits=bits,
        shingle_size=shingle_size,
        min_length=min_length,
    )
    return "\n\n".join(kept)


def stats(text: str = None, lines = None) -> dict:
    """Return diagnostic stats. Pure.

    If `text` is given: returns simhash + token / shingle counts.
    If `lines` is given: returns dedup ratio (kept / total) without mutation.
    """
    out = {}
    if text is not None:
        tokens = _tokenize(text)
        shingles = _shingles(tokens)
        out["tokens"] = len(tokens)
        out["shingles"] = len(shingles)
        out["simhash"] = simhash(text)
    if lines is not None:
        lines_list = list(lines)
        kept = dedup_lines(lines_list)
        out["lines_total"] = len(lines_list)
        out["lines_kept"] = len(kept)
        out["dedup_ratio"] = (
            len(kept) / len(lines_list) if lines_list else 0.0
        )
    return out
