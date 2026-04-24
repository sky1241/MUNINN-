"""Sanity run — btree_google.go via ollama deepseek-coder:6.7b (Linux natif).

But: valider que la pipeline reconstruct_adaptive + anchors fonctionne avec un
LLM local GRATUIT apres la migration Linux. Baseline Claude Sonnet: 52/61 SHA
(9 irreductibles a x3). Cible: voir les auto-SHA tomber via anchor map
(model-agnostic), puis mesurer ce que deepseek-coder fait sur le reste.

Sanity != full run: 1 seul cycle (max_cycles=1) pour un premier verdict rapide.
Si auto-SHA OK + deepseek resout une partie -> feu vert full run (max_cycles=3).

Usage:
    python tests/run_sanity_btree.py
    python tests/run_sanity_btree.py 2>&1 | tee /tmp/muninn_sanity_btree.log
"""
import sys
import os
import time
import tempfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine', 'core'))

from engine.core.cube_providers import OllamaProvider, reconstruct_adaptive
from engine.core.mycelium import Mycelium


FILE = os.path.join(os.path.dirname(__file__), 'cube_corpus', 'btree_google.go')


def on_cube(cycle, level, cube_idx, status, attempts, ncd):
    if status == 'CYCLE_END':
        print(f'\n=== CYCLE {cycle} END — {int(ncd)} new SHA ===\n', flush=True)
    elif status == 'SHA':
        tag = 'AUTO-SHA' if attempts == 0 else f'SHA (attempt {attempts})'
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: {tag} <<<', flush=True)
    else:
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: NCD={ncd:.3f} ({attempts}a)',
              flush=True)


def main():
    with open(FILE, 'r') as fh:
        content = fh.read()

    model = os.environ.get('MUNINN_OLLAMA_MODEL', 'qwen2.5-coder:7b')
    provider = OllamaProvider(model=model,
                              base_url='http://localhost:11434')

    tmp = tempfile.mkdtemp()
    mycelium = Mycelium(os.path.join(tmp, 'myc.db'))

    print('=' * 60, flush=True)
    print(f'SANITY RUN — btree_google.go — {model} LOCAL', flush=True)
    print(f'File : {FILE}', flush=True)
    print(f'Model: {model} (ollama localhost:11434)', flush=True)
    print('Cost : $0.00', flush=True)
    print('Cycle: 1 (sanity — full run fera 3)', flush=True)
    print('Goal : auto-SHA via anchors + deepseek-coder sur le reste', flush=True)
    print('=' * 60, flush=True)
    print(flush=True)

    t0 = time.time()
    results = reconstruct_adaptive(
        file_path=FILE,
        content=content,
        provider=provider,
        base_tokens=112,
        max_cycles=1,
        attempts_per_cube=11,
        mycelium=mycelium,
        on_cube=on_cube,
    )
    elapsed = time.time() - t0

    print(flush=True)
    print('=' * 60, flush=True)
    print(f'SHA   : {results["sha_count"]}/{results["total_cubes"]} '
          f'({results["sha_pct"]:.1f}%)', flush=True)
    print(f'Cycles: {results["cycles"]}', flush=True)
    print(f'Crit. : {results["critical_cubes"]}', flush=True)
    print(f'Time  : {elapsed:.0f}s  |  Cost: $0.00', flush=True)
    for cy, info in results['per_cycle'].items():
        print(f'  Cycle {cy}: +{info["new_sha"]} SHA', flush=True)
        for lv, linfo in info['per_level'].items():
            print(f'    x{lv}: {linfo["tested"]} tested, {linfo["sha"]} SHA',
                  flush=True)
    print('=' * 60, flush=True)
    print(flush=True)
    print('Baseline Claude Sonnet (cycle 1, x1+x2+x3): 52/61 SHA '
          '(55 x1 + ... = 52 avant plateau)', flush=True)
    print('Verdict:', flush=True)
    print('  - auto-SHA (attempts=0) doit etre similaire a Claude '
          '(anchor logic identique)', flush=True)
    print('  - SHA avec attempts>0 = deepseek-coder performance reelle', flush=True)
    print('=' * 60, flush=True)

    mycelium.close()


if __name__ == '__main__':
    main()
