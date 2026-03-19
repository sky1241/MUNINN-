#!/usr/bin/env python3
"""
Cube Convergence Test — multi-cycle destruction/reconstruction.
Proves the WAGON EFFECT: successful reconstructions improve neighbors,
which improves THEIR reconstruction in the next cycle.

Cycle 1: reconstruct all cubes from originals
Cycle 2: failed cubes retry with improved neighbors (successful cubes replaced)
Cycle N: convergence toward 100%
"""
import os
import sys
import time
import tempfile
import shutil
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from cube import (
    Cube, CubeStore, ClaudeProvider,
    subdivide_file, assign_neighbors,
    reconstruct_cube, compute_ncd,
)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "cube_corpus")


def p(s):
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode(), flush=True)


def run_convergence(file_path, lang, provider, max_cycles=5):
    """Run multi-cycle destruction/reconstruction. Track convergence."""
    p(f"\n{'#'*70}")
    p(f"  CONVERGENCE TEST — {lang.upper()} — {os.path.basename(file_path)}")
    p(f"  Max cycles: {max_cycles}")
    p(f"{'#'*70}")

    # Build cubes
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_conv.db")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=88)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)

    n = len(cubes)
    p(f"  {n} cubes\n")

    # Track state: original content for each cube, and whether it's been "healed"
    original_content = {cube.id: cube.content for cube in cubes}
    healed = set()  # cube IDs that have been successfully reconstructed
    cycle_stats = []

    total_t0 = time.time()

    for cycle in range(1, max_cycles + 1):
        p(f"  {'='*60}")
        p(f"  CYCLE {cycle}")
        p(f"  {'='*60}")

        # Which cubes still need healing?
        to_heal = [i for i in range(n) if cubes[i].id not in healed]

        if not to_heal:
            p(f"  ALL CUBES HEALED — convergence reached at cycle {cycle-1}!")
            break

        p(f"  {len(to_heal)} cubes to heal ({len(healed)}/{n} already healed)")

        cycle_success = 0
        cycle_exact = 0
        cycle_ncds = []
        t0 = time.time()

        for i in to_heal:
            target = cubes[i]
            neighbor_entries = store.get_neighbors(target.id)
            neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

            try:
                result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)
                cycle_ncds.append(result.ncd_score)

                status = "FAIL"
                if result.exact_match:
                    cycle_exact += 1
                    cycle_success += 1
                    healed.add(target.id)
                    status = "SHA!"
                    # Update the cube content in the store with the reconstruction
                    target.content = result.reconstruction
                    store.save_cube(target)
                elif result.success:  # NCD < 0.3
                    cycle_success += 1
                    healed.add(target.id)
                    status = "OK"
                    # Update the cube content — this is the WAGON EFFECT
                    # The reconstructed cube becomes a better neighbor for adjacent cubes
                    target.content = result.reconstruction
                    store.save_cube(target)

                p(f"    [{i:>4}] NCD={result.ncd_score:.3f} {status}")

            except Exception as e:
                p(f"    [{i:>4}] ERROR: {e}")
                cycle_ncds.append(1.0)

        elapsed = time.time() - t0
        total_healed = len(healed)
        avg_ncd = sum(cycle_ncds) / len(cycle_ncds) if cycle_ncds else 1.0

        stats = {
            "cycle": cycle,
            "attempted": len(to_heal),
            "success": cycle_success,
            "exact": cycle_exact,
            "total_healed": total_healed,
            "total_cubes": n,
            "pct_healed": 100 * total_healed / n,
            "avg_ncd": avg_ncd,
            "elapsed": elapsed,
        }
        cycle_stats.append(stats)

        p(f"\n  CYCLE {cycle} BILAN:")
        p(f"    This cycle:   {cycle_success}/{len(to_heal)} healed ({cycle_exact} SHA exact)")
        p(f"    Cumulative:   {total_healed}/{n} ({stats['pct_healed']:.1f}%)")
        p(f"    Avg NCD:      {avg_ncd:.3f}")
        p(f"    Time:         {elapsed:.1f}s")

        if total_healed == n:
            p(f"\n  *** 100% CONVERGENCE at cycle {cycle}! ***")
            break

    total_time = time.time() - total_t0

    # Final convergence curve
    p(f"\n{'#'*70}")
    p(f"  CONVERGENCE CURVE — {lang.upper()}")
    p(f"{'#'*70}")
    p(f"  {'Cycle':>6} {'Attempted':>10} {'Healed':>8} {'Cumul':>8} {'%':>8} {'Avg NCD':>8} {'Time':>7}")
    p(f"  {'─'*58}")
    for s in cycle_stats:
        p(f"  {s['cycle']:>6} {s['attempted']:>10} {s['success']:>8} "
          f"{s['total_healed']:>8} {s['pct_healed']:>7.1f}% "
          f"{s['avg_ncd']:>8.3f} {s['elapsed']:>6.1f}s")
    p(f"  {'─'*58}")
    p(f"  Total time: {total_time:.1f}s")
    p(f"{'#'*70}")

    store.close()
    shutil.rmtree(tmp, ignore_errors=True)

    return cycle_stats


def main():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        p("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    provider = ClaudeProvider(model="claude-sonnet-4-6")
    p(f"Model: claude-sonnet-4-6")

    # Run convergence on Go (91 cubes — good size, 48.4% cycle 1)
    target = os.path.join(CORPUS_DIR, "server.go")
    stats = run_convergence(target, "go", provider, max_cycles=5)

    # Save convergence data
    report_path = os.path.join(CORPUS_DIR, "CONVERGENCE.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Cube Convergence Test — {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"File: server.go (Go) — 1306 lines\n")
        f.write(f"Model: claude-sonnet-4-6\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"WAGON EFFECT: successful reconstructions replace original cubes,\n")
        f.write(f"becoming better neighbors for adjacent cubes in the next cycle.\n\n")
        f.write(f"{'Cycle':>6} {'Attempted':>10} {'Healed':>8} {'Cumul':>8} {'%':>8} {'Avg NCD':>8}\n")
        f.write(f"{'─'*50}\n")
        for s in stats:
            f.write(f"{s['cycle']:>6} {s['attempted']:>10} {s['success']:>8} "
                    f"{s['total_healed']:>8} {s['pct_healed']:>7.1f}% "
                    f"{s['avg_ncd']:>8.3f}\n")
    p(f"\nConvergence report saved: {report_path}")


if __name__ == "__main__":
    main()
