#!/usr/bin/env python3
"""
Muninn Benchmark — measures real fact retention after compression.

For each sample file:
1. Compress with muninn
2. For each factual question, check if the answer is findable in compressed text
3. Report: X/Y questions answered (Z%)

No API needed — pure text search.
"""
import json
import sys
from pathlib import Path

# Add engine to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine" / "core"))

from muninn import compress_file
from tokenizer import count_tokens


def run_benchmark(sample_path: Path, questions_path: Path) -> dict:
    """Run benchmark on a single sample."""
    original = sample_path.read_text(encoding="utf-8")
    compressed = compress_file(sample_path)

    with open(questions_path, encoding="utf-8") as f:
        questions = json.load(f)

    orig_tokens = count_tokens(original)[0]
    comp_tokens = count_tokens(compressed)[0]
    ratio = orig_tokens / max(comp_tokens, 1)

    results = []
    for q in questions:
        answer = q["answer"]
        # Check if answer is findable in compressed text (case-insensitive)
        found = answer.lower() in compressed.lower()
        # Also check without commas (e.g., "150,000" might become "150K")
        if not found:
            clean_answer = answer.replace(",", "")
            found = clean_answer.lower() in compressed.lower()
        # Check for shortened forms (e.g., "150,000" -> "150K", "12.4 million" -> "12.4M")
        if not found and any(c.isdigit() for c in answer):
            # Try to find just the significant digits
            digits = "".join(c for c in answer if c.isdigit() or c == ".")
            if digits and len(digits) >= 2:
                found = digits in compressed
        results.append({
            "question": q["question"],
            "answer": answer,
            "found": found,
        })

    answered = sum(1 for r in results if r["found"])
    total = len(results)

    return {
        "sample": sample_path.name,
        "orig_tokens": orig_tokens,
        "comp_tokens": comp_tokens,
        "ratio": ratio,
        "answered": answered,
        "total": total,
        "pct": answered / total * 100 if total > 0 else 0,
        "details": results,
    }


def main():
    benchmark_dir = Path(__file__).parent
    tests_dir = benchmark_dir.parent

    samples = [
        (benchmark_dir / "verbose_memory.md", benchmark_dir / "questions_verbose.json"),
        (benchmark_dir / "sample_session.md", benchmark_dir / "questions_session.json"),
        (benchmark_dir / "sample_compact.md", benchmark_dir / "questions_compact.json"),
    ]

    print("=" * 60)
    print("MUNINN BENCHMARK — Factual Question Retention")
    print("=" * 60)

    all_answered = 0
    all_total = 0

    for sample_path, questions_path in samples:
        if not sample_path.exists():
            print(f"\n  SKIP: {sample_path.name} not found")
            continue
        if not questions_path.exists():
            print(f"\n  SKIP: {questions_path.name} not found")
            continue

        result = run_benchmark(sample_path, questions_path)
        all_answered += result["answered"]
        all_total += result["total"]

        status = "PASS" if result["pct"] >= 80 else "WARN" if result["pct"] >= 60 else "FAIL"
        print(f"\n  {result['sample']}:")
        print(f"    Compression: {result['orig_tokens']} -> {result['comp_tokens']} tokens (x{result['ratio']:.1f})")
        print(f"    Questions: {result['answered']}/{result['total']} ({result['pct']:.0f}%) [{status}]")

        # Show missed questions
        missed = [r for r in result["details"] if not r["found"]]
        if missed:
            print(f"    Missed:")
            for m in missed:
                print(f"      - {m['question']} (expected: {m['answer']})")

    print(f"\n{'=' * 60}")
    overall_pct = all_answered / all_total * 100 if all_total > 0 else 0
    overall_status = "PASS" if overall_pct >= 80 else "WARN" if overall_pct >= 60 else "FAIL"
    print(f"  OVERALL: {all_answered}/{all_total} questions ({overall_pct:.0f}%) [{overall_status}]")
    print("=" * 60)

    return 0 if overall_pct >= 85 else 1


if __name__ == "__main__":
    sys.exit(main())
