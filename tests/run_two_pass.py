#!/usr/bin/env python3
"""
Cube Two-Pass Reconstruction — C1 sequential + C2 mycelium.

Pass 1 (C1): Sequential neighbors only. Build cube scan.
             Cube size scales with file size (bigger file = bigger cubes).
Between:     Feed scanned code into mycelium -> build co-occurrence network.
Pass 2 (C2): Failed cubes get mycelium semantic neighbors added.
             Spreading activation finds related cubes elsewhere in file.

Usage:
    python tests/run_two_pass.py                          # Ollama local
    python tests/run_two_pass.py --provider claude        # Sonnet API
    python tests/run_two_pass.py --file tests/cube_corpus/server.go
"""
import os
import sys
import time
import argparse
import tempfile
import shutil

from cube import (
    Cube, CubeStore, OllamaProvider, ClaudeProvider,
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


def cube_size_for_lines(total_lines):
    """Scale cube size with file size. Bigger file = bigger cubes = more context per cube."""
    if total_lines < 500:
        return 88
    elif total_lines < 1000:
        return 110
    elif total_lines < 2000:
        return 132
    else:
        return 160


def build_cubes(file_path):
    """Subdivide file into cubes with size scaled to file length."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    total_lines = content.count('\n') + 1
    target_tokens = cube_size_for_lines(total_lines)

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_2pass.db")
    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=target_tokens)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)

    return cubes, store, tmp, total_lines, target_tokens, content


def build_mycelium(content, file_path):
    """Feed file content into a fresh mycelium and return it."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
        from muninn.mycelium import Mycelium
        myc_tmp = tempfile.mkdtemp()
        myc_path = os.path.join(myc_tmp, "mycelium.json")
        myc = Mycelium(myc_path)
        # Observe the code file — paragraph chunking for semantics
        myc.observe(content, source=os.path.basename(file_path))
        p(f"  Mycelium: {myc.stats()['total_connections']} connections, "
          f"{myc.stats()['total_fusions']} fusions")
        return myc, myc_tmp
    except Exception as e:
        p(f"  Mycelium error: {e}")
        return None, None


def get_semantic_neighbors(cube, cubes, store, mycelium, max_semantic=5):
    """Find semantically related cubes via mycelium co-occurrence."""
    if mycelium is None:
        return []

    # Extract concepts from this cube's content
    words = set(cube.content.lower().split())
    # Get related concepts from mycelium
    related_concepts = set()
    for word in list(words)[:10]:  # Top 10 words
        try:
            related = mycelium.get_related(word, top_n=5)
            for concept, strength in related:
                related_concepts.add(concept)
        except Exception:
            pass

    if not related_concepts:
        return []

    # Find cubes that contain these related concepts
    scored = []
    existing_neighbor_ids = {nid for nid, _, _ in store.get_neighbors(cube.id)}
    existing_neighbor_ids.add(cube.id)

    for other in cubes:
        if other.id in existing_neighbor_ids:
            continue
        other_words = set(other.content.lower().split())
        overlap = len(related_concepts & other_words)
        if overlap > 0:
            scored.append((other, overlap))

    scored.sort(key=lambda x: -x[1])
    return [c for c, _ in scored[:max_semantic]]


def run_pass(cubes, store, provider, healed, pass_name, semantic_neighbors=None):
    """Run one reconstruction pass."""
    n = len(cubes)
    to_heal = [i for i in range(n) if cubes[i].id not in healed]

    if not to_heal:
        return 0, 0, [], healed

    success_count = 0
    exact_count = 0
    ncds = []

    for i in to_heal:
        target = cubes[i]
        neighbor_entries = store.get_neighbors(target.id)
        neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

        # Add semantic neighbors if available (C2)
        if semantic_neighbors and target.id in semantic_neighbors:
            neighbor_cubes.extend(semantic_neighbors[target.id])

        try:
            result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)
            ncds.append(result.ncd_score)

            if result.exact_match:
                status = "SHA!"
                exact_count += 1
                success_count += 1
                healed.add(target.id)
                target.content = result.reconstruction
                store.save_cube(target)
            elif result.success:
                status = "OK"
                success_count += 1
                healed.add(target.id)
                target.content = result.reconstruction
                store.save_cube(target)
            else:
                status = "FAIL"

            p(f"  {pass_name} [{i+1:>4}/{n}] L{target.line_start}-{target.line_end} "
              f"NCD={result.ncd_score:.3f} {status}")

        except Exception as e:
            p(f"  {pass_name} [{i+1:>4}/{n}] ERROR: {e}")
            ncds.append(1.0)

    return success_count, exact_count, ncds, healed


def run_two_pass(file_path, lang, provider):
    """Full two-pass reconstruction on one file."""
    p(f"\n{'#'*70}")
    p(f"  TWO-PASS: {lang.upper()} — {os.path.basename(file_path)}")
    p(f"{'#'*70}")

    # Build cubes with scaled size
    cubes, store, tmp, total_lines, target_tokens, content = build_cubes(file_path)
    n = len(cubes)
    p(f"  {total_lines} lines, {n} cubes (target={target_tokens} tok)")

    healed = set()
    total_t0 = time.time()

    # ─── C1: Sequential neighbors only ───────────────────────
    p(f"\n  {'='*60}")
    p(f"  C1 — Sequential neighbors")
    p(f"  {'='*60}")
    t0 = time.time()
    c1_success, c1_exact, c1_ncds, healed = run_pass(
        cubes, store, provider, healed, "C1")
    c1_time = time.time() - t0
    c1_avg = sum(c1_ncds) / len(c1_ncds) if c1_ncds else 0

    p(f"\n  C1 BILAN: {c1_success}/{n} healed ({c1_exact} SHA), "
      f"NCD avg={c1_avg:.3f}, {c1_time:.1f}s")
    p(f"  Cumul: {len(healed)}/{n} ({100*len(healed)/n:.1f}%)")

    if len(healed) == n:
        p(f"\n  100% at C1! No C2 needed.")
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)
        return

    # ─── Build mycelium from code ────────────────────────────
    p(f"\n  {'='*60}")
    p(f"  MYCELIUM BUILD")
    p(f"  {'='*60}")
    mycelium, myc_tmp = build_mycelium(content, file_path)

    # ─── Find semantic neighbors for failed cubes ────────────
    failed_indices = [i for i in range(n) if cubes[i].id not in healed]
    semantic_map = {}
    if mycelium:
        p(f"  Finding semantic neighbors for {len(failed_indices)} failed cubes...")
        for i in failed_indices:
            sem_neighbors = get_semantic_neighbors(cubes[i], cubes, store, mycelium)
            if sem_neighbors:
                semantic_map[cubes[i].id] = sem_neighbors
        p(f"  {len(semantic_map)}/{len(failed_indices)} cubes got semantic neighbors")

    # ─── C2: Sequential + mycelium neighbors ─────────────────
    p(f"\n  {'='*60}")
    p(f"  C2 — Sequential + Mycelium neighbors")
    p(f"  {'='*60}")
    t0 = time.time()
    c2_success, c2_exact, c2_ncds, healed = run_pass(
        cubes, store, provider, healed, "C2", semantic_neighbors=semantic_map)
    c2_time = time.time() - t0
    c2_avg = sum(c2_ncds) / len(c2_ncds) if c2_ncds else 0

    p(f"\n  C2 BILAN: {c2_success}/{len(failed_indices)} healed ({c2_exact} SHA), "
      f"NCD avg={c2_avg:.3f}, {c2_time:.1f}s")
    p(f"  Cumul: {len(healed)}/{n} ({100*len(healed)/n:.1f}%)")

    total_time = time.time() - total_t0

    # ─── Final report ────────────────────────────────────────
    p(f"\n{'#'*70}")
    p(f"  FINAL — {lang.upper()}")
    p(f"{'#'*70}")
    p(f"  {'Pass':<8} {'Try':>5} {'OK':>5} {'SHA':>5} {'NCD':>7}")
    p(f"  {'─'*35}")
    p(f"  {'C1':<8} {n:>5} {c1_success:>5} {c1_exact:>5} {c1_avg:>7.3f}")
    p(f"  {'C2':<8} {len(failed_indices):>5} {c2_success:>5} {c2_exact:>5} {c2_avg:>7.3f}")
    p(f"  {'─'*35}")
    p(f"  Total healed: {len(healed)}/{n} ({100*len(healed)/n:.1f}%)")
    c1_pct = 100 * c1_success / n if n else 0
    c2_pct = 100 * (c1_success + c2_success) / n if n else 0
    p(f"  C1: {c1_pct:.1f}% -> C1+C2: {c2_pct:.1f}% (+{c2_pct - c1_pct:.1f}%)")
    p(f"  Time: {total_time:.1f}s")
    p(f"{'#'*70}")

    # Cleanup
    store.close()
    shutil.rmtree(tmp, ignore_errors=True)
    if myc_tmp:
        shutil.rmtree(myc_tmp, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Cube two-pass reconstruction")
    parser.add_argument("--provider", default="ollama", choices=["ollama", "claude"],
                        help="LLM provider (default: ollama)")
    parser.add_argument("--model", help="Model override")
    parser.add_argument("--file", help="Single file to test")
    parser.add_argument("--lang", help="Single language from corpus")
    args = parser.parse_args()

    if args.provider == "claude":
        model = args.model or "claude-sonnet-4-6"
        provider = ClaudeProvider(model=model)
        p(f"Provider: Claude ({model}) — API cost applies")
    else:
        model = args.model or "deepseek-coder:6.7b"
        provider = OllamaProvider(model=model)
        p(f"Provider: Ollama ({model}) — $0.00")
        p(f"FIM: {provider.supports_fim}")

    if args.file:
        ext = os.path.splitext(args.file)[1].lstrip('.')
        run_two_pass(args.file, ext, provider)
    elif args.lang:
        if args.lang in CORPUS_FILES:
            run_two_pass(CORPUS_FILES[args.lang], args.lang, provider)
    else:
        for lang, fpath in CORPUS_FILES.items():
            if os.path.exists(fpath):
                run_two_pass(fpath, lang, provider)


if __name__ == "__main__":
    main()
