#!/usr/bin/env python3
"""
Test L8 (LLMLingua-2) ordering: does it work better on raw text or pre-compressed?

Pipeline A: L1-L7 -> L8 (current order)
Pipeline B: L8 first -> L1-L7 after
Pipeline C: L8 alone (no regex layers)

Measures ratio AND fact retention for each pipeline.
Requires: pip install llmlingua (~1GB model)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine" / "core"))

from tokenizer import count_tokens
from muninn import compress_file, extract_facts

# Check if LLMLingua is available
try:
    from llmlingua import PromptCompressor
    HAS_LLMLINGUA = True
except ImportError:
    HAS_LLMLINGUA = False


def run_llmlingua(text: str, rate: float = 0.5) -> str:
    """Run LLMLingua-2 on text."""
    compressor = PromptCompressor(
        model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
        use_llmlingua2=True,
        device_map="cpu",
    )
    result = compressor.compress_prompt([text], rate=rate)
    return result["compressed_prompt"]


def measure(original: str, compressed: str, label: str):
    """Measure and print compression stats."""
    orig_tokens = count_tokens(original)[0]
    comp_tokens = count_tokens(compressed)[0]
    ratio = orig_tokens / max(comp_tokens, 1)

    orig_facts = extract_facts(original)
    preserved = sum(1 for f in orig_facts if f in compressed)
    fact_pct = preserved / max(len(orig_facts), 1) * 100

    print(f"  {label}:")
    print(f"    {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f})")
    print(f"    Facts: {preserved}/{len(orig_facts)} ({fact_pct:.0f}%)")
    return {"ratio": ratio, "fact_pct": fact_pct, "tokens": comp_tokens}


def main():
    if not HAS_LLMLINGUA:
        print("SKIP: llmlingua not installed (pip install llmlingua)")
        return 0

    sample = ROOT / "tests" / "benchmark" / "verbose_memory.md"
    if not sample.exists():
        print(f"SKIP: {sample} not found")
        return 0

    original = sample.read_text(encoding="utf-8")
    print("=" * 60)
    print("L8 ORDERING TEST — verbose_memory.md")
    print("=" * 60)

    # Pipeline A: L1-L7 -> L8 (current)
    print("\nPipeline A: L1-L7 then L8 (current order)")
    regex_compressed = compress_file(sample)
    a_result = run_llmlingua(regex_compressed)
    a_stats = measure(original, a_result, "A: L1-L7 -> L8")

    # Pipeline B: L8 first -> L1-L7 after
    print("\nPipeline B: L8 first then L1-L7")
    b_l8_first = run_llmlingua(original)
    # Save to temp file for compress_file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        # Add a fake ## header so compress_file can parse it
        f.write(f"## L8 pre-compressed\n{b_l8_first}")
        tmp_path = f.name
    import os
    try:
        b_result = compress_file(Path(tmp_path))
    finally:
        os.unlink(tmp_path)
    b_stats = measure(original, b_result, "B: L8 -> L1-L7")

    # Pipeline C: L8 alone
    print("\nPipeline C: L8 alone (no regex)")
    c_result = run_llmlingua(original)
    c_stats = measure(original, c_result, "C: L8 only")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"  A (L1-L7 -> L8): x{a_stats['ratio']:.1f}, {a_stats['fact_pct']:.0f}% facts")
    print(f"  B (L8 -> L1-L7): x{b_stats['ratio']:.1f}, {b_stats['fact_pct']:.0f}% facts")
    print(f"  C (L8 only):     x{c_stats['ratio']:.1f}, {c_stats['fact_pct']:.0f}% facts")

    # Determine winner
    best = max(
        [("A", a_stats), ("B", b_stats), ("C", c_stats)],
        key=lambda x: x[1]["ratio"] * (x[1]["fact_pct"] / 100)
    )
    print(f"\n  WINNER: Pipeline {best[0]} (best ratio*facts tradeoff)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
