"""
Test QTM God's Number cube size: 112 tokens = 14 × 8
Verify each cube is within tolerance [92, 132] and averages ~112.
Compare with previous 88-token [REDACTED] (35.9% reconstruction).
"""
import sys, os, statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.cube import (
    subdivide_file, subdivide_recursive, token_count,
    TARGET_TOKENS, TOLERANCE_MIN, TOLERANCE_MAX
)

# ─── Test files ───────────────────────────────────────────────────────
CORPUS_DIR = os.path.join(os.path.dirname(__file__))
TEST_FILES = [
    "analytics.py",
]

# Also grab real project files for broader test
PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
REAL_FILES = [
    "engine/core/tokenizer.py",
    "forge.py",
]


def test_constants():
    """Verify constants are QTM-based."""
    assert TARGET_TOKENS == 112, f"TARGET_TOKENS should be 112 (QTM: 14×8), got {TARGET_TOKENS}"
    assert TOLERANCE_MIN == 92, f"TOLERANCE_MIN should be 92, got {TOLERANCE_MIN}"
    assert TOLERANCE_MAX == 132, f"TOLERANCE_MAX should be 132, got {TOLERANCE_MAX}"
    print(f"[PASS] Constants: TARGET={TARGET_TOKENS}, MIN={TOLERANCE_MIN}, MAX={TOLERANCE_MAX}")


def _cube_sizes(file_path: str, label: str):
    """Test that cubes from a file are ~112 tokens."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    total_tokens = token_count(content)
    cubes = subdivide_recursive(file_path, content, target_tokens=TARGET_TOKENS)

    sizes = [token_count(c.content) for c in cubes]
    avg = statistics.mean(sizes) if sizes else 0
    median = statistics.median(sizes) if sizes else 0
    in_tolerance = sum(1 for s in sizes if TOLERANCE_MIN <= s <= TOLERANCE_MAX)
    pct_in_tolerance = (in_tolerance / len(sizes) * 100) if sizes else 0

    # Check faces: 112 / 8 = 14 tokens per face
    tokens_per_face = avg / 8

    print(f"\n{'='*60}")
    print(f"[{label}] {os.path.basename(file_path)}")
    print(f"  Total tokens: {total_tokens}")
    print(f"  Cubes created: {len(cubes)}")
    print(f"  Sizes: min={min(sizes)}, max={max(sizes)}, avg={avg:.1f}, median={median:.1f}")
    print(f"  In tolerance [{TOLERANCE_MIN}-{TOLERANCE_MAX}]: {in_tolerance}/{len(sizes)} ({pct_in_tolerance:.1f}%)")
    print(f"  Tokens per face (avg/8): {tokens_per_face:.1f} (target: 14.0)")
    print(f"  Size distribution:")

    # Histogram
    buckets = {"<92": 0, "92-102": 0, "103-112": 0, "113-122": 0, "123-132": 0, ">132": 0}
    for s in sizes:
        if s < 92:
            buckets["<92"] += 1
        elif s <= 102:
            buckets["92-102"] += 1
        elif s <= 112:
            buckets["103-112"] += 1
        elif s <= 122:
            buckets["113-122"] += 1
        elif s <= 132:
            buckets["123-132"] += 1
        else:
            buckets[">132"] += 1

    for bucket, count in buckets.items():
        bar = "#" * count
        print(f"    {bucket:>8}: {count:3d} {bar}")

    return {
        "file": os.path.basename(file_path),
        "total_tokens": total_tokens,
        "n_cubes": len(cubes),
        "avg_size": avg,
        "median_size": median,
        "min_size": min(sizes) if sizes else 0,
        "max_size": max(sizes) if sizes else 0,
        "pct_in_tolerance": pct_in_tolerance,
        "tokens_per_face": tokens_per_face,
        "cubes": cubes,
        "sizes": sizes,
    }


def main():
    print("=" * 60)
    print("QTM GOD'S NUMBER CUBE TEST")
    print(f"Target: {TARGET_TOKENS} tokens = 14 faces × 8 tokens/face")
    print(f"Tolerance: [{TOLERANCE_MIN}, {TOLERANCE_MAX}]")
    print("=" * 60)

    test_constants()

    results = []

    # Test corpus files
    for fname in TEST_FILES:
        fpath = os.path.join(CORPUS_DIR, fname)
        if os.path.exists(fpath):
            r = _cube_sizes(fpath, "CORPUS")
            results.append(r)

    # Test real project files
    for fname in REAL_FILES:
        fpath = os.path.join(PROJECT_ROOT, fname)
        if os.path.exists(fpath):
            r = _cube_sizes(fpath, "PROJECT")
            results.append(r)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_sizes = []
    total_cubes = 0
    for r in results:
        all_sizes.extend(r["sizes"])
        total_cubes += r["n_cubes"]
        print(f"  {r['file']:30s}: {r['n_cubes']:4d} cubes, avg={r['avg_size']:.1f}, "
              f"face={r['tokens_per_face']:.1f}, in_tol={r['pct_in_tolerance']:.1f}%")

    if all_sizes:
        global_avg = statistics.mean(all_sizes)
        global_in_tol = sum(1 for s in all_sizes if TOLERANCE_MIN <= s <= TOLERANCE_MAX)
        print(f"\n  GLOBAL: {total_cubes} cubes, avg={global_avg:.1f} tokens, "
              f"face={global_avg/8:.1f} tok/face, "
              f"in_tolerance={global_in_tol}/{len(all_sizes)} ({global_in_tol/len(all_sizes)*100:.1f}%)")

        # Verdict
        face_ok = 13.0 <= global_avg / 8 <= 15.0
        tol_ok = (global_in_tol / len(all_sizes)) > 0.7
        print(f"\n  Face target (14.0 ± 1.0): {'PASS' if face_ok else 'FAIL'} ({global_avg/8:.1f})")
        print(f"  Tolerance (>70% in range): {'PASS' if tol_ok else 'FAIL'} ({global_in_tol/len(all_sizes)*100:.1f}%)")


if __name__ == "__main__":
    main()
