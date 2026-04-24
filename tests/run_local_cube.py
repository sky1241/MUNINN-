#!/usr/bin/env python3
"""
Cube reconstruction via LOCAL LLM (Ollama + DeepSeek-Coder).
Zero cost. FIM natif. Tourne sur RX 5700 XT / CPU.

Usage:
    python tests/run_local_cube.py
    python tests/run_local_cube.py --model deepseek-coder:6.7b
    python tests/run_local_cube.py --file tests/cube_corpus/server.go
    python tests/run_local_cube.py --cycles 5  # convergence test
"""
import os
import sys
import time
import argparse
import tempfile
import shutil

from cube import (
    Cube, CubeStore, OllamaProvider,
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
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode(), flush=True)


def build_cubes(file_path, target_tokens=112):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_local.db")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=target_tokens)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)
    return cubes, store, tmp


def run_single_cycle(cubes, store, provider, healed=None):
    """Run one destruction/reconstruction cycle. Returns stats."""
    if healed is None:
        healed = set()
    n = len(cubes)
    to_heal = [i for i in range(n) if cubes[i].id not in healed]

    if not to_heal:
        return {"attempted": 0, "success": 0, "exact": 0, "ncds": [], "healed": healed}

    cycle_success = 0
    cycle_exact = 0
    cycle_ncds = []

    for i in to_heal:
        target = cubes[i]
        neighbor_entries = store.get_neighbors(target.id)
        neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

        try:
            result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)
            cycle_ncds.append(result.ncd_score)

            if result.exact_match:
                status = "SHA!"
                cycle_exact += 1
                cycle_success += 1
                healed.add(target.id)
                target.content = result.reconstruction
                store.save_cube(target)
            elif result.success:
                status = "OK"
                cycle_success += 1
                healed.add(target.id)
                target.content = result.reconstruction
                store.save_cube(target)
            else:
                status = "FAIL"

            p(f"  [{i+1:>4}/{n}] L{target.line_start}-{target.line_end} "
              f"NCD={result.ncd_score:.3f} {status}"
              f"{' (FIM)' if provider.supports_fim else ''}")

        except Exception as e:
            p(f"  [{i+1:>4}/{n}] ERROR: {e}")
            cycle_ncds.append(1.0)

    return {
        "attempted": len(to_heal),
        "success": cycle_success,
        "exact": cycle_exact,
        "ncds": cycle_ncds,
        "healed": healed,
    }


def run_file(file_path, lang, provider, max_cycles=1):
    """Run destruction/reconstruction on a file."""
    p(f"\n{'='*70}")
    p(f"  {lang.upper()} — {os.path.basename(file_path)}")
    p(f"  Model: {provider.model} ({'FIM' if provider.supports_fim else 'prompt'})")
    p(f"  Cycles: {max_cycles}")
    p(f"{'='*70}")

    cubes, store, tmp = build_cubes(file_path)
    n = len(cubes)
    p(f"  {n} cubes\n")

    healed = set()
    cycle_stats = []
    total_t0 = time.time()

    for cycle in range(1, max_cycles + 1):
        p(f"  --- Cycle {cycle} ({len(healed)}/{n} healed) ---")
        t0 = time.time()

        stats = run_single_cycle(cubes, store, provider, healed)
        healed = stats["healed"]
        elapsed = time.time() - t0

        avg_ncd = sum(stats["ncds"]) / len(stats["ncds"]) if stats["ncds"] else 0
        pct = 100 * len(healed) / n

        cycle_stats.append({
            "cycle": cycle,
            "attempted": stats["attempted"],
            "success": stats["success"],
            "exact": stats["exact"],
            "total_healed": len(healed),
            "pct": pct,
            "avg_ncd": avg_ncd,
            "elapsed": elapsed,
        })

        p(f"\n  Cycle {cycle}: {stats['success']}/{stats['attempted']} healed "
          f"({stats['exact']} SHA), cumul {len(healed)}/{n} ({pct:.1f}%), "
          f"NCD avg={avg_ncd:.3f}, {elapsed:.1f}s")

        if len(healed) == n:
            p(f"\n  *** 100% CONVERGENCE at cycle {cycle}! ***")
            break

        if stats["attempted"] > 0 and stats["success"] == 0:
            p(f"  No progress — stopping early.")
            break

    total_time = time.time() - total_t0

    # Summary
    p(f"\n  {'Cycle':>6} {'Try':>5} {'OK':>5} {'SHA':>5} {'Cumul':>6} {'%':>7} {'NCD':>7} {'Time':>7}")
    p(f"  {'─'*52}")
    for s in cycle_stats:
        p(f"  {s['cycle']:>6} {s['attempted']:>5} {s['success']:>5} {s['exact']:>5} "
          f"{s['total_healed']:>6} {s['pct']:>6.1f}% {s['avg_ncd']:>7.3f} {s['elapsed']:>6.1f}s")
    p(f"  Total: {total_time:.1f}s")

    store.close()
    shutil.rmtree(tmp, ignore_errors=True)

    return cycle_stats


def main():
    parser = argparse.ArgumentParser(description="Cube local LLM reconstruction")
    parser.add_argument("--model", default="deepseek-coder:6.7b", help="Ollama model")
    parser.add_argument("--file", help="Single file to test (default: all corpus)")
    parser.add_argument("--lang", help="Single language from corpus (go/python/jsx/rust/typescript/kotlin/c)")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles (default: 1)")
    parser.add_argument("--url", default="http://localhost:11434", help="Ollama URL")
    args = parser.parse_args()

    provider = OllamaProvider(model=args.model, base_url=args.url)
    p(f"Provider: Ollama ({args.model})")
    p(f"FIM: {provider.supports_fim}")
    p(f"Cost: $0.00")

    # Check Ollama is running
    try:
        models = provider.list_models()
        p(f"Available models: {models}")
    except Exception as e:
        p(f"ERROR: Cannot connect to Ollama at {args.url}")
        p(f"  Start Ollama first: ollama serve")
        sys.exit(1)

    if args.file:
        ext = os.path.splitext(args.file)[1].lstrip('.')
        run_file(args.file, ext, provider, max_cycles=args.cycles)
    elif args.lang:
        if args.lang in CORPUS_FILES:
            run_file(CORPUS_FILES[args.lang], args.lang, provider, max_cycles=args.cycles)
        else:
            p(f"Unknown lang: {args.lang}. Available: {list(CORPUS_FILES.keys())}")
    else:
        # All corpus files
        for lang, fpath in CORPUS_FILES.items():
            if os.path.exists(fpath):
                run_file(fpath, lang, provider, max_cycles=args.cycles)


if __name__ == "__main__":
    main()
