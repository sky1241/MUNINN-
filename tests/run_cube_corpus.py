#!/usr/bin/env python3
"""
Run Cube full destruction on the multi-language corpus.
Direct Python script — no pytest buffering, real-time output.
"""
import os
import sys
import time
import tempfile
import shutil

from cube import (
    Cube, CubeStore, ClaudeProvider,
    subdivide_file, assign_neighbors,
    reconstruct_cube, compute_ncd,
)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "cube_corpus")

CORPUS_FILES = {
    "go": os.path.join(CORPUS_DIR, "server.go"),
    "python": os.path.join(CORPUS_DIR, "analytics.py"),
    "jsx": os.path.join(CORPUS_DIR, "components.jsx"),
    "rust": os.path.join(CORPUS_DIR, "cache.rs"),
    "typescript": os.path.join(CORPUS_DIR, "store.ts"),
    "kotlin": os.path.join(CORPUS_DIR, "pipeline.kt"),
    "c": os.path.join(CORPUS_DIR, "allocator.c"),
}


def p(s):
    """Print with flush + unicode safety."""
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode(), flush=True)


def build_cubes(file_path, target_tokens=112):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_test.db")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=target_tokens)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)
    return cubes, store, tmp


def run_lang(lang, file_path, provider):
    p(f"\n{'='*70}")
    p(f"  {lang.upper()} — {os.path.basename(file_path)}")
    p(f"{'='*70}")

    cubes, store, tmp = build_cubes(file_path)
    n = len(cubes)
    p(f"  {n} cubes")
    p(f"  {'─'*60}")

    results = []
    t0 = time.time()

    for i in range(n):
        target = cubes[i]
        neighbor_entries = store.get_neighbors(target.id)
        neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

        try:
            result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)
            results.append(result)
            p(f"  [{i+1:>4}/{n}] L{target.line_start}-{target.line_end} "
              f"SHA={'Y' if result.exact_match else 'N'} "
              f"NCD={result.ncd_score:.3f} "
              f"{'OK' if result.success else 'FAIL'}")
        except Exception as e:
            results.append(None)
            p(f"  [{i+1:>4}/{n}] ERROR: {e}")

    elapsed = time.time() - t0

    valid = [r for r in results if r is not None]
    exact = sum(1 for r in valid if r.exact_match)
    success = sum(1 for r in valid if r.success)
    errors = sum(1 for r in results if r is None)
    avg_ncd = sum(r.ncd_score for r in valid) / len(valid) if valid else 1.0
    min_ncd = min(r.ncd_score for r in valid) if valid else 1.0
    max_ncd = max(r.ncd_score for r in valid) if valid else 1.0

    p(f"\n  BILAN {lang.upper()}: {n} cubes, {elapsed:.1f}s")
    p(f"  SHA exact:  {exact}/{n} ({100*exact/n:.1f}%)")
    p(f"  NCD < 0.3:  {success}/{n} ({100*success/n:.1f}%)")
    p(f"  NCD avg:    {avg_ncd:.3f}  (min={min_ncd:.3f}, max={max_ncd:.3f})")
    p(f"  Errors:     {errors}")

    store.close()
    shutil.rmtree(tmp, ignore_errors=True)

    return {
        "lang": lang, "total": n, "exact": exact, "success": success,
        "errors": errors, "avg_ncd": avg_ncd, "min_ncd": min_ncd,
        "max_ncd": max_ncd, "elapsed": elapsed,
    }


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        p("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    p(f"API key: {key[:10]}...{key[-4:]}")
    provider = ClaudeProvider(model="claude-sonnet-4-6")
    p(f"Model: claude-sonnet-4-6")
    p(f"Corpus: {len(CORPUS_FILES)} files")

    all_stats = []
    total_t0 = time.time()

    for lang, fpath in CORPUS_FILES.items():
        if not os.path.exists(fpath):
            p(f"SKIP {lang}: {fpath} not found")
            continue
        stats = run_lang(lang, fpath, provider)
        all_stats.append(stats)

    total_time = time.time() - total_t0

    # Final report
    p(f"\n{'#'*70}")
    p(f"  RAPPORT FINAL — CORPUS COMPLET")
    p(f"{'#'*70}")
    p(f"  {'Lang':<12} {'Cubes':>6} {'Exact':>6} {'NCD<0.3':>8} {'Avg NCD':>8} {'Min':>6} {'Max':>6} {'Time':>7}")
    p(f"  {'─'*62}")

    total_cubes = total_exact = total_success = 0
    for s in all_stats:
        p(f"  {s['lang']:<12} {s['total']:>6} {s['exact']:>6} "
          f"{s['success']:>8} {s['avg_ncd']:>8.3f} "
          f"{s['min_ncd']:>6.3f} {s['max_ncd']:>6.3f} "
          f"{s['elapsed']:>6.1f}s")
        total_cubes += s["total"]
        total_exact += s["exact"]
        total_success += s["success"]

    global_avg = sum(s['avg_ncd'] for s in all_stats) / len(all_stats) if all_stats else 0
    p(f"  {'─'*62}")
    p(f"  {'TOTAL':<12} {total_cubes:>6} {total_exact:>6} "
      f"{total_success:>8} {global_avg:>8.3f} "
      f"{'':>6} {'':>6} {total_time:>6.1f}s")
    p(f"{'#'*70}")

    # Save to file
    report_path = os.path.join(CORPUS_DIR, "RESULTS.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Cube Reconstruction Report — {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Model: claude-sonnet-4-6\n")
        f.write(f"{'='*70}\n\n")
        f.write(f"{'Lang':<12} {'Cubes':>6} {'Exact':>6} {'NCD<0.3':>8} {'Avg NCD':>8} {'Min':>6} {'Max':>6} {'Time':>7}\n")
        f.write(f"{'─'*62}\n")
        for s in all_stats:
            f.write(f"{s['lang']:<12} {s['total']:>6} {s['exact']:>6} "
                    f"{s['success']:>8} {s['avg_ncd']:>8.3f} "
                    f"{s['min_ncd']:>6.3f} {s['max_ncd']:>6.3f} "
                    f"{s['elapsed']:>6.1f}s\n")
        f.write(f"{'─'*62}\n")
        f.write(f"{'TOTAL':<12} {total_cubes:>6} {total_exact:>6} "
                f"{total_success:>8} {global_avg:>8.3f} "
                f"{'':>6} {'':>6} {total_time:>6.1f}s\n")
    p(f"\nReport saved: {report_path}")


if __name__ == "__main__":
    main()
