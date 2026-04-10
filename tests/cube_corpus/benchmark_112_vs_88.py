#!/usr/bin/env python3
"""
Benchmark: 112-token [REDACTED] (QTM) vs 88-token [REDACTED] (HTM)
on analytics.py with Ollama deepseek-coder:6.7b.

Compares reconstruction success rates between cube sizes.
"""
import os
import sys
import time
import tempfile
import shutil
import json
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.cube import (
    Cube, CubeStore, OllamaProvider,
    subdivide_file, assign_neighbors,
    reconstruct_cube, compute_ncd, token_count,
)

CORPUS_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_FILE = os.path.join(CORPUS_DIR, "analytics.py")
OLLAMA_MODEL = "deepseek-coder:6.7b"


def p(s):
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode(), flush=True)


def ollama_available():
    try:
        url = 'http://localhost:11434/api/tags'
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = [m['name'] for m in data.get('models', [])]
            return OLLAMA_MODEL in models
    except Exception:
        return False


def run_benchmark(file_path, target_tokens, label, provider, max_cubes=None):
    """Run destruction/reconstruction on cubes of given size."""
    p(f"\n{'='*70}")
    p(f"  {label}: target_tokens={target_tokens}")
    p(f"{'='*70}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    total_tok = token_count(content)
    p(f"  File: {os.path.basename(file_path)} ({total_tok} tokens)")

    # Build cubes
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_bench.db")
    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=target_tokens)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)

    n = len(cubes)
    if max_cubes and n > max_cubes:
        p(f"  {n} cubes total, testing first {max_cubes}")
        n = max_cubes
    else:
        p(f"  {n} cubes total")

    sizes = [token_count(c.content) for c in cubes[:n]]
    avg_size = sum(sizes) / len(sizes)
    p(f"  Avg size: {avg_size:.1f} tokens, face: {avg_size/8:.1f} tok/face")
    p(f"  {'_'*60}")

    results = []
    t0 = time.time()

    for i in range(n):
        target = cubes[i]
        neighbor_entries = store.get_neighbors(target.id)
        neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

        try:
            result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)
            results.append(result)
            status = "OK" if result.success else "FAIL"
            p(f"  [{i+1:>3}/{n}] NCD={result.ncd_score:.3f} "
              f"SHA={'Y' if result.exact_match else 'N'} {status}")
        except Exception as e:
            results.append(None)
            p(f"  [{i+1:>3}/{n}] ERROR: {e}")

    elapsed = time.time() - t0

    valid = [r for r in results if r is not None]
    exact = sum(1 for r in valid if r.exact_match)
    success = sum(1 for r in valid if r.success)
    avg_ncd = sum(r.ncd_score for r in valid) / len(valid) if valid else 1.0
    min_ncd = min(r.ncd_score for r in valid) if valid else 1.0
    max_ncd = max(r.ncd_score for r in valid) if valid else 1.0

    store.close()
    shutil.rmtree(tmp, ignore_errors=True)

    stats = {
        "label": label,
        "target_tokens": target_tokens,
        "n_cubes": n,
        "avg_cube_size": avg_size,
        "tokens_per_face": avg_size / 8,
        "exact": exact,
        "success": success,
        "success_pct": 100 * success / n if n else 0,
        "avg_ncd": avg_ncd,
        "min_ncd": min_ncd,
        "max_ncd": max_ncd,
        "elapsed": elapsed,
    }

    p(f"\n  RESULT {label}:")
    p(f"  Cubes: {n}, Avg size: {avg_size:.1f} tok, Face: {avg_size/8:.1f} tok/face")
    p(f"  SHA exact: {exact}/{n} ({100*exact/n:.1f}%)")
    p(f"  NCD < 0.3: {success}/{n} ({100*success/n:.1f}%)")
    p(f"  NCD avg: {avg_ncd:.3f} (min={min_ncd:.3f}, max={max_ncd:.3f})")
    p(f"  Time: {elapsed:.1f}s")

    return stats


def main():
    if not ollama_available():
        p(f"ERROR: Ollama not available or model {OLLAMA_MODEL} not pulled")
        p("Run: ollama pull deepseek-coder:6.7b")
        sys.exit(1)

    if not os.path.exists(TEST_FILE):
        p(f"ERROR: {TEST_FILE} not found")
        sys.exit(1)

    provider = OllamaProvider(model=OLLAMA_MODEL)
    p(f"Model: {OLLAMA_MODEL}")
    p(f"File:  analytics.py")

    # Limit to 20 cubes each for speed (full benchmark = ~1h each)
    MAX_CUBES = 20

    # Run both benchmarks
    stats_88 = run_benchmark(TEST_FILE, target_tokens=88, label="HTM (88 tok)",
                             provider=provider, max_cubes=MAX_CUBES)
    stats_112 = run_benchmark(TEST_FILE, target_tokens=112, label="QTM (112 tok)",
                              provider=provider, max_cubes=MAX_CUBES)

    # Comparison
    p(f"\n{'#'*70}")
    p(f"  COMPARISON: HTM (88) vs QTM (112)")
    p(f"{'#'*70}")
    p(f"  {'Metric':<25} {'HTM (88)':>12} {'QTM (112)':>12} {'Delta':>10}")
    p(f"  {'_'*60}")
    p(f"  {'Cubes':<25} {stats_88['n_cubes']:>12} {stats_112['n_cubes']:>12} "
      f"{stats_112['n_cubes'] - stats_88['n_cubes']:>+10}")
    p(f"  {'Avg size (tok)':<25} {stats_88['avg_cube_size']:>12.1f} {stats_112['avg_cube_size']:>12.1f} "
      f"{stats_112['avg_cube_size'] - stats_88['avg_cube_size']:>+10.1f}")
    p(f"  {'Tok/face':<25} {stats_88['tokens_per_face']:>12.1f} {stats_112['tokens_per_face']:>12.1f} "
      f"{stats_112['tokens_per_face'] - stats_88['tokens_per_face']:>+10.1f}")
    p(f"  {'SHA exact':<25} {stats_88['exact']:>12} {stats_112['exact']:>12} "
      f"{stats_112['exact'] - stats_88['exact']:>+10}")
    p(f"  {'NCD < 0.3 (%)':<25} {stats_88['success_pct']:>11.1f}% {stats_112['success_pct']:>11.1f}% "
      f"{stats_112['success_pct'] - stats_88['success_pct']:>+9.1f}%")
    p(f"  {'Avg NCD':<25} {stats_88['avg_ncd']:>12.3f} {stats_112['avg_ncd']:>12.3f} "
      f"{stats_112['avg_ncd'] - stats_88['avg_ncd']:>+10.3f}")
    p(f"  {'Time (s)':<25} {stats_88['elapsed']:>12.1f} {stats_112['elapsed']:>12.1f} "
      f"{stats_112['elapsed'] - stats_88['elapsed']:>+10.1f}")

    verdict = "QTM WINS" if stats_112['success_pct'] > stats_88['success_pct'] else \
              "HTM WINS" if stats_88['success_pct'] > stats_112['success_pct'] else "TIE"
    p(f"\n  VERDICT: {verdict}")
    p(f"{'#'*70}")

    # Save results
    report = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "model": OLLAMA_MODEL,
        "file": "analytics.py",
        "max_cubes": MAX_CUBES,
        "htm_88": stats_88,
        "qtm_112": stats_112,
        "verdict": verdict,
    }
    report_path = os.path.join(CORPUS_DIR, "BENCHMARK_112_vs_88.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    p(f"\nResults saved: {report_path}")


if __name__ == "__main__":
    main()
