"""Overnight full reconstruct run with all CHUNK 1-9 fixes active.

Runs reconstruct_adaptive on btree_google.go with:
- Fix 20 reordered before FIM (CHUNK 1)
- Real 847 MB mycelium bound (CHUNK 2 — uses Mycelium(REPO_ROOT))
- Ollama num_ctx=16384 (CHUNK 9)
- 3 cycles, 11 attempts/cube, qwen2.5-coder:7b

Logs everything to /tmp/muninn_overnight_2026_04_30.log so Sky can read
the full result the next morning.

Usage:
    PYTHONPATH=$(pwd) python tests/run_overnight_2026_04_30.py 2>&1 \
        | tee /tmp/muninn_overnight_2026_04_30.log
"""
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine', 'core'))

from engine.core.cube_providers import OllamaProvider, reconstruct_adaptive
from engine.core.mycelium import Mycelium

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "tests" / "cube_corpus" / "btree_google.go"


def on_cube(cycle, level, cube_idx, status, attempts, ncd):
    if status == 'CYCLE_END':
        print(f'\n=== CYCLE {cycle} END — {int(ncd)} new SHA this cycle ===\n',
              flush=True)
    elif status == 'SHA':
        tag = 'AUTO-SHA' if attempts == 0 else f'SHA (attempt {attempts})'
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: {tag} <<<',
              flush=True)
    else:
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: NCD={ncd:.3f} ({attempts}a)',
              flush=True)


def main():
    if not TARGET.exists():
        print(f'FATAL: {TARGET} not found.', flush=True)
        return 1
    content = TARGET.read_text(encoding='utf-8')

    model = os.environ.get('MUNINN_OLLAMA_MODEL', 'qwen2.5-coder:7b')
    provider = OllamaProvider(model=model)

    # CHUNK 2 fix: bind the real 847 MB mycelium
    mycelium = Mycelium(REPO_ROOT)

    print('=' * 70, flush=True)
    print(f'OVERNIGHT FULL RUN — {TARGET.name}', flush=True)
    print(f'Model      : {model}', flush=True)
    print(f'Mycelium   : {mycelium.db_path} '
          f'({mycelium.db_path.stat().st_size:,} bytes)', flush=True)
    print(f'Cycles max : 3', flush=True)
    print(f'Attempts   : 11/cube', flush=True)
    print(f'num_ctx    : {provider.NUM_CTX} (CHUNK 9)', flush=True)
    print(f'Started at : {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
    print('=' * 70, flush=True)
    print(flush=True)

    t0 = time.time()
    results = reconstruct_adaptive(
        file_path=str(TARGET),
        content=content,
        provider=provider,
        base_tokens=112,
        max_cycles=3,
        attempts_per_cube=11,
        mycelium=mycelium,
        on_cube=on_cube,
    )
    elapsed = time.time() - t0

    print(flush=True)
    print('=' * 70, flush=True)
    print(f'FINAL RESULTS — elapsed {elapsed:.0f}s ({elapsed/60:.1f} min)',
          flush=True)
    print('=' * 70, flush=True)
    print(f'SHA       : {results["sha_count"]}/{results["total_cubes"]} '
          f'({results["sha_pct"]:.1f}%)', flush=True)
    print(f'Cycles run: {results["cycles"]}', flush=True)
    print(f'Critical  : {len(results["critical_cubes"])} cubes never resolved',
          flush=True)
    print(f'Cost      : $0.00 (local qwen via Ollama)', flush=True)
    print(flush=True)

    print('Per-cycle breakdown:', flush=True)
    for cy, info in results['per_cycle'].items():
        print(f'  Cycle {cy}: +{info["new_sha"]} new SHA', flush=True)
        for lv, linfo in info['per_level'].items():
            print(f'    x{lv}: tested={linfo["tested"]}  '
                  f'sha={linfo["sha"]}', flush=True)

    print(flush=True)
    print('Reference benchmarks:', flush=True)
    print('  Sonnet API on this file : 53/61 (87%)', flush=True)
    print('  qwen UX before CHUNK 1  :  1/10 (10%)', flush=True)
    print('  qwen CLI cycle 1 x1     : 39/61 (64%) — measured 2026-04-30', flush=True)
    print('  qwen full overnight     : <see above>', flush=True)
    print('=' * 70, flush=True)

    # Save JSON summary alongside the log
    summary_path = Path('/tmp/muninn_overnight_2026_04_30_summary.json')
    summary = {
        'date': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'file': str(TARGET),
        'model': model,
        'mycelium_db': str(mycelium.db_path),
        'mycelium_size_bytes': mycelium.db_path.stat().st_size,
        'num_ctx': provider.NUM_CTX,
        'elapsed_sec': elapsed,
        'sha_count': results['sha_count'],
        'total_cubes': results['total_cubes'],
        'sha_pct': results['sha_pct'],
        'cycles_run': results['cycles'],
        'critical_cubes_count': len(results['critical_cubes']),
        'per_cycle': {str(k): v for k, v in results['per_cycle'].items()},
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str),
                            encoding='utf-8')
    print(f'\nSummary JSON saved -> {summary_path}', flush=True)

    mycelium.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
