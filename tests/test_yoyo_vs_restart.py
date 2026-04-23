"""A/B test: yo-yo descent vs restart x1 — fair comparison."""
import sys, os, time, tempfile
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine', 'core'))

from engine.core.cube_providers import ClaudeProvider, reconstruct_cube_waves
from engine.core.cube import (subdivide_file, CubeStore, assign_neighbors,
                               extract_ast_hints, normalize_content,
                               enrich_hints_with_file_context)
from engine.core.mycelium import Mycelium

f = os.path.join(os.path.dirname(__file__), 'cube_corpus', 'btree_google.go')
with open(f, 'r') as fh:
    content = fh.read()
provider = ClaudeProvider(model='claude-sonnet-4-6')

# SHA sets from the full adaptive run
x1_sha = {0,1,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,
           27,30,31,32,33,34,35,36,37,38,40,41,42,43,44,45,46,47,48,49,50,51,
           52,53,54,55,56,59,60}
x2_sha = {0,2,3,5,6,7,8,9,10,11,12,13,16,18,19,25,26,27,28,29,31}
x3_sha = {3,4,5,6,7,8,11,16,17,18,19}

x1_fails = [2, 26, 28, 29, 39, 57, 58]
x2_fails = [1, 4, 14, 15, 17, 20, 21, 22, 23, 24, 30]
x3_fails = [1, 2, 9, 10, 12, 13, 14, 15, 20]

cubes_x1 = subdivide_file(content=content, file_path=f, target_tokens=112)
cubes_x2 = subdivide_file(content=content, file_path=f, target_tokens=224)
cubes_x3 = subdivide_file(content=content, file_path=f, target_tokens=336)


def feed_mycelium(myc):
    """Feed all known SHA cubes to mycelium."""
    for i in x1_sha:
        if i < len(cubes_x1):
            myc.observe_text(cubes_x1[i].content)
    for i in x2_sha:
        if i < len(cubes_x2):
            myc.observe_text(cubes_x2[i].content)
    for i in x3_sha:
        if i < len(cubes_x3):
            myc.observe_text(cubes_x3[i].content)


def run_pass(cubes, fails, myc, label):
    """Run 1 pass of 11 attempts on fail cubes. Returns new SHA count."""
    tmp = tempfile.mkdtemp()
    store = CubeStore(os.path.join(tmp, 'cubes.db'))
    for c in cubes:
        store.save_cube(c)
    assign_neighbors(cubes, [], store, max_neighbors=9)

    new_sha = 0
    for i in fails:
        if i >= len(cubes):
            continue
        tc = cubes[i]
        ne = store.get_neighbors(tc.id)
        nc = [store.get_cube(nid) for nid, _, _ in ne if store.get_cube(nid)]
        hints = extract_ast_hints(tc)
        hints['_raw_content'] = tc.content
        hints = enrich_hints_with_file_context(hints, content)
        wr = reconstruct_cube_waves(
            tc, nc, provider, attempts_per_wave=11, max_waves=1,
            ast_hints=hints, mycelium=myc)
        if wr.sha_matched:
            new_sha += 1
            myc.observe_text(wr.best_reconstruction)
            print(f'  {label} cube {i:>2}: SHA! (attempt {wr.attempt_in_wave}) <<<',
                  flush=True)
        else:
            print(f'  {label} cube {i:>2}: NCD={wr.best_ncd:.3f}', flush=True)
    store.close()
    return new_sha


# ============================================================
# TEST A: YO-YO DESCENT (Claude)
# ============================================================
print('=' * 60, flush=True)
print('TEST A: YO-YO DESCENT (x3 -> x2 -> x1)', flush=True)
print('=' * 60, flush=True)

tmp_a = tempfile.mkdtemp()
myc_a = Mycelium(os.path.join(tmp_a, 'myc.db'))
feed_mycelium(myc_a)

sha_a_x2 = run_pass(cubes_x2, x2_fails, myc_a, 'A x2')
sha_a_x1 = run_pass(cubes_x1, x1_fails, myc_a, 'A x1')
myc_a.close()

total_a = sha_a_x2 + sha_a_x1
print(f'\nTEST A RESULT: +{total_a} SHA (x2: +{sha_a_x2}, x1: +{sha_a_x1})',
      flush=True)

# ============================================================
# TEST B: RESTART x1 (Sky)
# ============================================================
print(flush=True)
print('=' * 60, flush=True)
print('TEST B: RESTART x1 -> x2 -> x3 (Sky)', flush=True)
print('=' * 60, flush=True)

tmp_b = tempfile.mkdtemp()
myc_b = Mycelium(os.path.join(tmp_b, 'myc.db'))
feed_mycelium(myc_b)

sha_b_x1 = run_pass(cubes_x1, x1_fails, myc_b, 'B x1')
sha_b_x2 = run_pass(cubes_x2, x2_fails, myc_b, 'B x2')
sha_b_x3 = run_pass(cubes_x3, x3_fails, myc_b, 'B x3')
myc_b.close()

total_b = sha_b_x1 + sha_b_x2 + sha_b_x3
print(f'\nTEST B RESULT: +{total_b} SHA (x1: +{sha_b_x1}, x2: +{sha_b_x2}, x3: +{sha_b_x3})',
      flush=True)

# ============================================================
# VERDICT
# ============================================================
print(flush=True)
print('=' * 60, flush=True)
print(f'TEST A (yo-yo descent):  +{total_a} SHA', flush=True)
print(f'TEST B (restart x1):     +{total_b} SHA', flush=True)
if total_a > total_b:
    print('WINNER: Claude (yo-yo descent)', flush=True)
elif total_b > total_a:
    print('WINNER: Sky (restart x1)', flush=True)
else:
    print('TIE', flush=True)
print('=' * 60, flush=True)
