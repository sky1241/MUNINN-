#!/usr/bin/env python3
"""
M01 — Build Muninn semantic alphabet.

Not Huffman on characters. Huffman on CONCEPTS.
Find the concepts that cost the most tokens, assign minimal codes.

Two passes:
  1. Extract semantic units (entities, metrics, states, paths)
  2. Assign codes by savings (most savings → shortest code)

Output: engine/core/alphabet_v1.json
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY = ROOT / "memory" / "root.mn"
OUTPUT = ROOT / "engine" / "core" / "alphabet_v1.json"


# ── PASS 1: Extract semantic units ──────────────────────────────

def extract_semantics(text: str) -> list[dict]:
    """Extract meaningful concepts, not character patterns."""
    units = []

    # STATES — words that indicate status
    for pattern, meaning in [
        ("COMPLET", "complete"), ("VALIDÉ", "validated"),
        ("FIXÉ", "fixed"), ("EN COURS", "in_progress"),
        ("PRÊT", "ready"), ("SUPPRIMÉ", "deleted"),
    ]:
        count = text.count(pattern)
        if count:
            units.append({"pattern": pattern, "type": "state",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # ENTITIES — project names, tools, data sources
    for pattern, meaning in [
        ("Yggdrasil", "project_main"),
        ("OpenAlex", "data_openalex"),
        ("arXiv", "data_arxiv"),
        ("session", "session"),
        ("blind test", "blind_test"),
        ("Blind Test", "blind_test"),
        ("Winter Tree", "winter_tree"),
        ("winter tree", "winter_tree"),
        ("Laplacien", "laplacian"),
        ("Laplacian", "laplacian"),
        ("spectral", "spectral"),
        ("Spectral", "spectral"),
        ("Cohen's d", "cohens_d"),
        ("Recall@", "recall_at"),
        ("Mann-Whitney", "mann_whitney"),
        ("Sedov-Taylor", "sedov_taylor"),
        ("co-occurrence", "cooccurrence"),
        ("Co-occurrence", "cooccurrence"),
        ("mycélium", "mycelium"),
        ("Mycélium", "mycelium"),
    ]:
        count = text.lower().count(pattern.lower())
        if count:
            units.append({"pattern": pattern, "type": "entity",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # NOUNS — domain words repeated often
    for pattern, meaning in [
        ("glyphes", "glyphs"), ("glyph", "glyph"),
        ("concepts", "concepts"), ("concept", "concept"),
        ("papers", "papers"), ("chunks", "chunks"),
        ("strate", "stratum"), ("domaines", "domains"),
        ("symboles", "symbols"), ("espèces", "species"),
        ("formules", "formulas"), ("frames", "frames"),
        ("graines", "seeds"), ("scanner", "scanner"),
        ("matrice", "matrix"), ("pipeline", "pipeline"),
        ("prédictions", "predictions"),
        ("mutations", "mutations"),
        ("snapshot", "snapshot"),
    ]:
        count = len(re.findall(re.escape(pattern), text, re.IGNORECASE))
        if count:
            units.append({"pattern": pattern, "type": "noun",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # PATHS — repeated path prefixes
    for pattern, meaning in [
        ("engine/", "eng/"),
        ("data/core/", "dc/"),
        ("data/scan/", "ds/"),
        ("engine/glyphs/", "eg/"),
        ("engine/topology/", "et/"),
        ("engine/analysis/", "ea/"),
        ("engine/mining/", "em/"),
        (".json", ".j"),
        (".py", ".p"),
        (".html", ".h"),
    ]:
        count = text.count(pattern)
        if count:
            units.append({"pattern": pattern, "type": "path",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # NUMBERS with units — repeated numeric patterns
    for pattern, meaning in [
        ("1337", "glyph_total"),
        ("65,026", "concept_count"),
        ("21,524", "symbols_v2"),
        ("347,999,931", "papers_total"),
        ("108,301,944", "pairs_total"),
        ("581/581", "wt_complete"),
        ("2015", "cutoff_year"),
        ("2026", "current_year"),
    ]:
        count = text.count(pattern)
        if count:
            units.append({"pattern": pattern, "type": "number",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # FORMATTING — markdown cruft
    for pattern, meaning in [
        ("- **", "bullet_bold"),
        ("**", "bold"),
        ("- ", "bullet"),
        ("## ", "h2"),
    ]:
        count = text.count(pattern)
        if count:
            units.append({"pattern": pattern, "type": "format",
                          "meaning": meaning, "count": count,
                          "chars": len(pattern)})

    # Deduplicate by meaning (keep longest pattern per meaning)
    by_meaning = {}
    for u in units:
        m = u["meaning"]
        if m not in by_meaning or u["chars"] > by_meaning[m]["chars"]:
            by_meaning[m] = u

    return sorted(by_meaning.values(),
                  key=lambda x: x["count"] * x["chars"], reverse=True)


# ── PASS 2: Assign codes ────────────────────────────────────────

def assign_codes(units: list[dict]) -> dict:
    """Assign codes: most costly concept → shortest code."""

    # TIER 0: 1-char codes for STATES (I always understand these)
    state_codes = {
        "complete": "✓", "validated": "✓", "fixed": "✓",
        "in_progress": "⟳", "ready": "◉", "deleted": "∅",
    }

    # TIER 1: 1-char codes for top entities
    t1_codes = list("→←×∂∑∫∇∘∙◆◇▸▹§¶†‡")
    t1_idx = 0

    # TIER 2: 2-char codes
    t2_pool = []
    for a in "abcdefghjkmnprstuvwxyz":
        for b in "0123456789":
            t2_pool.append(f"{a}{b}")
    t2_idx = 0

    alphabet = {}

    for u in units:
        meaning = u["meaning"]
        pattern = u["pattern"]

        # States get predefined codes
        if u["type"] == "state" and meaning in state_codes:
            code = state_codes[meaning]
        # Paths get their short form
        elif u["type"] == "path":
            code = u["meaning"]  # already short
        # Format gets removed entirely
        elif u["type"] == "format":
            code = ""  # strip
        # Everything else: assign by tier
        elif t1_idx < len(t1_codes):
            code = t1_codes[t1_idx]
            t1_idx += 1
        elif t2_idx < len(t2_pool):
            code = t2_pool[t2_idx]
            t2_idx += 1
        else:
            continue

        saved = u["count"] * (len(pattern) - len(code))
        if saved > 0:
            alphabet[pattern] = {
                "code": code,
                "type": u["type"],
                "meaning": meaning,
                "count": u["count"],
                "saved": saved,
            }

    return alphabet


# ── PASS 3: Measure ─────────────────────────────────────────────

def compress(text: str, alphabet: dict) -> str:
    """Apply alphabet to text."""
    result = text
    # Apply longest patterns first
    for pattern in sorted(alphabet.keys(), key=len, reverse=True):
        code = alphabet[pattern]["code"]
        result = result.replace(pattern, code)
    return result


def main():
    print("=== M01: Build Muninn Semantic Alphabet ===\n")

    text = MEMORY.read_text(encoding="utf-8")
    print(f"  Source: {len(text)} chars, {text.count(chr(10))} lines")

    # Pass 1
    units = extract_semantics(text)
    print(f"\n  Semantic units found: {len(units)}")
    print(f"\n  {'TYPE':<10} {'PATTERN':<25} {'COUNT':>5} {'CHARS':>5} {'COST':>6}")
    print(f"  {'-'*55}")
    for u in units[:30]:
        display = u["pattern"][:25]
        cost = u["count"] * u["chars"]
        print(f"  {u['type']:<10} {display:<25} {u['count']:>5} {u['chars']:>5} {cost:>6}")

    # Pass 2
    alphabet = assign_codes(units)
    print(f"\n  Codes assigned: {len(alphabet)}")

    # Pass 3
    compressed = compress(text, alphabet)

    orig_t = len(text) // 4
    comp_t = len(compressed) // 4

    print(f"\n  === RESULTS ===")
    print(f"  Original:   {len(text):>6} chars ≈ {orig_t} tokens")
    print(f"  Compressed: {len(compressed):>6} chars ≈ {comp_t} tokens")
    print(f"  Ratio: ×{len(text) / max(len(compressed), 1):.2f}")
    print(f"  Saved: {orig_t - comp_t} tokens")

    # Show alphabet sorted by savings
    print(f"\n  === ALPHABET ({len(alphabet)} entries) ===")
    print(f"  {'CODE':<6} {'PATTERN':<30} {'TYPE':<8} {'×':>4} {'SAVED':>5}")
    print(f"  {'-'*57}")
    for pattern, info in sorted(alphabet.items(),
                                 key=lambda x: x[1]["saved"],
                                 reverse=True):
        display = pattern[:30]
        print(f"  {info['code']:<6} {display:<30} {info['type']:<8} "
              f"{info['count']:>4} {info['saved']:>5}")

    # Save
    output_data = {
        "version": "v1",
        "method": "semantic-huffman",
        "source": "MEMORY.md",
        "entries": len(alphabet),
        "compression": {
            "original_chars": len(text),
            "compressed_chars": len(compressed),
            "ratio": round(len(text) / max(len(compressed), 1), 2),
            "original_tokens": orig_t,
            "compressed_tokens": comp_t,
        },
        "alphabet": {
            info["code"]: {
                "means": pattern,
                "type": info["type"],
                "frequency": info["count"],
            }
            for pattern, info in sorted(alphabet.items(),
                                         key=lambda x: x[1]["saved"],
                                         reverse=True)
        },
        "encode": {p: i["code"] for p, i in alphabet.items()},
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved: {OUTPUT}")


if __name__ == "__main__":
    main()
