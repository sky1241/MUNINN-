#!/usr/bin/env python3
"""
MUNINN Encoder/Decoder v0.1
Usage:
    python muninn.py encode "S-2 pipeline complet, 459 chunks, p=3.4e-12"
    python muninn.py decode "枝✓ | 块459 | 值3.4e-12"
    python muninn.py stats
"""
import json
import sys
import re
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
CODEBOOK_PATH = ROOT / "CODEBOOK.json"


def load_codebook():
    with open(CODEBOOK_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_index(codebook):
    """Build fast lookup: concept → symbol and symbol → concept."""
    sym_to_concept = {}
    concept_to_sym = {}
    for sym, data in codebook["symbols"].items():
        if not isinstance(data, dict) or "concept" not in data:
            continue
        concept = data["concept"]
        sym_to_concept[sym] = data
        concept_to_sym[concept] = sym
    return sym_to_concept, concept_to_sym


def encode(text: str, codebook: dict) -> str:
    """
    Naive encode: replace known concept keywords with sinogrammes.
    Production version needs proper NLP — this is a demo.
    """
    sym_to_concept, concept_to_sym = build_index(codebook)

    # Simple keyword substitution map (concept keywords → symbol)
    keyword_map = {
        "S0": "根", "S1": "茎", "S2": "枝", "S3": "叶",
        "S4": "花", "S5": "果", "S6": "天",
        "P1": "桥", "P2": "密", "P3": "爆", "P4": "洞", "P5": "死",
        "complete": "✓", "complet": "✓", "COMPLET": "✓",
        "running": "⟳", "en cours": "⟳",
        "failed": "✗", "échec": "✗",
        "chunk": "块", "chunks": "块",
        "papers": "纸",
        "p=": "值=", "p =": "值=",
        "d=": "效=", "cohen": "效",
        "mirror pairs": "对",
        "bug": "误", "fix": "修",
        "seed": "种", "graine": "种",
        "warning": "警", "attention": "警",
        "decision": "决", "décision": "决",
        "session start": "始", "session end": "末",
        "yggdrasil": "龙", "muninn": "鸦",
        "infernal": "轮", "p=np": "等",
    }

    result = text
    for keyword, symbol in sorted(keyword_map.items(), key=lambda x: -len(x[0])):
        result = re.sub(re.escape(keyword), symbol, result, flags=re.IGNORECASE)

    return result


def decode(text: str, codebook: dict) -> str:
    """Decode sinogrammes back to concepts."""
    sym_to_concept, _ = build_index(codebook)
    result = text
    for sym, data in sym_to_concept.items():
        if sym in result:
            result = result.replace(sym, f"[{data['concept']}]")
    return result


def stats(codebook: dict):
    """Show codebook stats."""
    symbols = {k: v for k, v in codebook["symbols"].items()
               if isinstance(v, dict) and "concept" in v}

    domain_count = {}
    for data in symbols.values():
        d = data.get("domain", "*")
        domain_count[d] = domain_count.get(d, 0) + 1

    print(f"MUNINN Codebook v{codebook['meta']['version']}")
    print(f"Total symbols: {len(symbols)}")
    print(f"\nBy domain:")
    for d, count in sorted(domain_count.items()):
        print(f"  {d:12s} {count:3d} symbols")

    if "compression_examples" in codebook:
        ex = codebook["compression_examples"]
        orig = len(ex["texte_brut"])
        comp = len(ex["muninn"])
        print(f"\nCompression example:")
        print(f"  Original : {ex['texte_brut']}")
        print(f"  Muninn   : {ex['muninn']}")
        print(f"  Ratio    : {orig} → {comp} chars ({100*(orig-comp)//orig}% reduction)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    codebook = load_codebook()
    cmd = sys.argv[1]

    if cmd == "encode" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        print(encode(text, codebook))

    elif cmd == "decode" and len(sys.argv) >= 3:
        text = " ".join(sys.argv[2:])
        print(decode(text, codebook))

    elif cmd == "stats":
        stats(codebook)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
