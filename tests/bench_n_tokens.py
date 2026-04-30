"""Bench N tokens sweep — measure SHA score per cube target size.

Tests N ∈ {80, 88, 96, 112, 128} with the FULL pipeline (Fix 20 + FIM +
mycelium) on btree_google.go. Outputs a table comparing:
- total cubes generated
- auto-SHA (Fix 20, no LLM)
- LLM-SHA (FIM/fallback succeeded)
- final score = (auto-SHA + LLM-SHA) / total
- elapsed time

Run AFTER CHUNK 1 + CHUNK 2 are merged (otherwise biased by bypassed Fix 20
or empty mycelium).

Usage:
    PYTHONPATH=$(pwd) python tests/bench_n_tokens.py
    PYTHONPATH=$(pwd) MUNINN_BENCH_N="80,112" python tests/bench_n_tokens.py  # subset
    PYTHONPATH=$(pwd) MUNINN_OLLAMA_MODEL=deepseek-coder:6.7b python tests/bench_n_tokens.py
"""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine', 'core'))

from engine.core.cube_providers import OllamaProvider, reconstruct_cube
from engine.core.cube import (
    subdivide_file, extract_ast_hints, enrich_hints_with_file_context,
)
from engine.core.mycelium import Mycelium

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "tests" / "cube_corpus" / "btree_google.go"
DEFAULT_NS = (80, 88, 96, 112, 128)


def _parse_ns():
    raw = os.environ.get("MUNINN_BENCH_N", "")
    if not raw:
        return DEFAULT_NS
    try:
        return tuple(int(x) for x in raw.split(",") if x.strip())
    except ValueError:
        return DEFAULT_NS


def bench_one(n_tokens: int, content: str, provider, mycelium) -> dict:
    """Bench reconstruct for one cube size on the test file."""
    cubes = subdivide_file(str(TARGET), content,
                           target_tokens=n_tokens, level=0)
    total = len(cubes)

    # Trace which path each cube took (auto-SHA vs LLM-SHA vs fail)
    fim_calls, gen_calls = [], []
    orig_fim = OllamaProvider.fim_generate
    orig_gen = OllamaProvider.generate
    OllamaProvider.fim_generate = (
        lambda s, *a, **k: (fim_calls.append(1), orig_fim(s, *a, **k))[1]
    )
    OllamaProvider.generate = (
        lambda s, *a, **k: (gen_calls.append(1), orig_gen(s, *a, **k))[1]
    )

    auto_sha = 0
    llm_sha = 0
    fail = 0

    t0 = time.time()
    try:
        for c in cubes:
            fim_calls.clear()
            gen_calls.clear()
            hints = extract_ast_hints(c)
            hints['_raw_content'] = c.content
            hints = enrich_hints_with_file_context(hints, content)
            neighbors = [x for x in cubes if x.id != c.id][:9]
            r = reconstruct_cube(
                c, neighbors, provider,
                ncd_threshold=0.0, ast_hints=hints,
                mycelium=mycelium,
            )
            if r.exact_match:
                if not fim_calls and not gen_calls:
                    auto_sha += 1
                else:
                    llm_sha += 1
            else:
                fail += 1
    finally:
        OllamaProvider.fim_generate = orig_fim
        OllamaProvider.generate = orig_gen

    elapsed = time.time() - t0
    sha_total = auto_sha + llm_sha
    return {
        'n_tokens': n_tokens,
        'total': total,
        'auto_sha': auto_sha,
        'llm_sha': llm_sha,
        'fail': fail,
        'sha_total': sha_total,
        'pct': sha_total / total if total else 0.0,
        'elapsed': elapsed,
    }


def main():
    if not TARGET.exists():
        print(f"FATAL: {TARGET} not found.", flush=True)
        return 1
    content = TARGET.read_text(encoding='utf-8')
    model = os.environ.get('MUNINN_OLLAMA_MODEL', 'qwen2.5-coder:7b')
    provider = OllamaProvider(model=model)
    mycelium = Mycelium(REPO_ROOT)

    ns = _parse_ns()
    print(f"=== bench_n_tokens — model={model} — file={TARGET.name} ===",
          flush=True)
    print(f"Mycelium: {mycelium.db_path} "
          f"({mycelium.db_path.stat().st_size:,} bytes)", flush=True)
    print(f"Sweep N tokens: {ns}", flush=True)
    print(flush=True)

    results = []
    for n in ns:
        print(f"--- N = {n} tokens ---", flush=True)
        r = bench_one(n, content, provider, mycelium)
        results.append(r)
        print(f"  total={r['total']:>3}  "
              f"auto-SHA={r['auto_sha']:>3}  "
              f"LLM-SHA={r['llm_sha']:>3}  "
              f"fail={r['fail']:>3}  "
              f"score={r['sha_total']:>3}/{r['total']:<3} "
              f"({r['pct']*100:>5.1f}%)  "
              f"time={r['elapsed']:>6.0f}s",
              flush=True)
        print(flush=True)

    # Summary table
    print("=" * 78, flush=True)
    print(f"{'N':>5} | {'total':>5} | {'auto':>5} | {'LLM':>5} | "
          f"{'fail':>5} | {'score':>9} | {'time':>7}", flush=True)
    print("-" * 78, flush=True)
    for r in results:
        print(f"{r['n_tokens']:>5} | {r['total']:>5} | {r['auto_sha']:>5} | "
              f"{r['llm_sha']:>5} | {r['fail']:>5} | "
              f"{r['sha_total']:>3}/{r['total']:<3} ({r['pct']*100:>4.1f}%) | "
              f"{r['elapsed']:>6.0f}s",
              flush=True)
    print("=" * 78, flush=True)

    best = max(results, key=lambda r: r['pct'])
    print(f"Best N = {best['n_tokens']} "
          f"({best['sha_total']}/{best['total']} = {best['pct']*100:.1f}%)",
          flush=True)
    mycelium.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
