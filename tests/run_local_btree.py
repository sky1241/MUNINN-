"""Run adaptive pipeline on btree — local deepseek-coder:6.7b via WSL2."""
import sys, os, time, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine', 'core'))

from engine.core.cube_providers import OllamaProvider, reconstruct_adaptive
from engine.core.mycelium import Mycelium

f = os.path.join(os.path.dirname(__file__), 'cube_corpus', 'btree_google.go')
with open(f, 'r') as fh:
    content = fh.read()

# Connect to WSL2 Ollama
provider = OllamaProvider(model='deepseek-coder:6.7b', base_url='http://localhost:11434')
tmp = tempfile.mkdtemp()
mycelium = Mycelium(os.path.join(tmp, 'myc.db'))


def on_cube(cycle, level, cube_idx, status, attempts, ncd):
    if status == 'CYCLE_END':
        print(f'\n=== CYCLE {cycle} END — {int(ncd)} new SHA ===\n', flush=True)
    elif status == 'SHA':
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: SHA! (attempt {attempts}) <<<',
              flush=True)
    else:
        print(f'  c{cycle} x{level} cube {cube_idx:>2}: NCD={ncd:.3f} ({attempts}a)',
              flush=True)


print('=== btree_google.go — deepseek-coder:6.7b WSL2 LOCAL — $0.00 ===', flush=True)
print('Bugfix: get_perplexity skip on SHA match', flush=True)
print('Features: learned anchors + 1-pass restart cycles', flush=True)
print(flush=True)

t0 = time.time()
results = reconstruct_adaptive(
    file_path=f,
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
print('=' * 60, flush=True)
print(f'SHA: {results["sha_count"]}/{results["total_cubes"]} ({results["sha_pct"]:.1f}%)',
      flush=True)
print(f'Cycles: {results["cycles"]}', flush=True)
print(f'Critical: {results["critical_cubes"]}', flush=True)
print(f'Time: {elapsed:.0f}s | Cost: $0.00', flush=True)
for cy, info in results['per_cycle'].items():
    print(f'  Cycle {cy}: +{info["new_sha"]} SHA', flush=True)
    for lv, linfo in info['per_level'].items():
        print(f'    x{lv}: {linfo["tested"]} tested, {linfo["sha"]} SHA', flush=True)
print('=' * 60, flush=True)

mycelium.close()
