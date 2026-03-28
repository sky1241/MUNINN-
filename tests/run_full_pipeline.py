#!/usr/bin/env python3
"""
Cube Full Pipeline — ALL bricks wired together.

The wall, not bricks on the floor.

Cycle loop:
  1. Subdivide all corpus files into cubes
  2. Extract AST hints per cube (pre-destruction constraints)
  3. For each cycle:
     a. Reconstruct each unhealed cube (lexicon + AST + neighbors)
     b. SHA-256 verify
     c. Hebbian update (B30) — strengthen/weaken neighbor weights
     d. Feed mycelium (B29) — teach co-occurrence from results
     e. Update temperatures (B23) — track hot/cold cubes
     f. Wagon effect — successful reconstructions replace originals
  4. Between cycles:
     - Mycelium spreading activation for semantic neighbors
     - God's Number (B26) to track convergence
     - Kaplan-Meier survival (B24) per cube
     - Danger filter (B25) skips dead code
  5. Stop when 100% NCD<0.3 or no progress

Usage:
    python tests/run_full_pipeline.py                        # Ollama local
    python tests/run_full_pipeline.py --provider claude      # Sonnet API
    python tests/run_full_pipeline.py --provider haiku       # Haiku (cheap)
    python tests/run_full_pipeline.py --file tests/cube_corpus/server.go
    python tests/run_full_pipeline.py --cycles 10
"""
import os
import sys
import time
import argparse
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from cube import (
    Cube, CubeStore, OllamaProvider, ClaudeProvider,
    subdivide_file, assign_neighbors, parse_dependencies,
    reconstruct_cube, compute_ncd, run_destruction_cycle,
    extract_all_ast_hints, extract_ast_hints,
    feed_mycelium_from_results, hebbian_update,
    compute_temperature, update_all_temperatures,
    kaplan_meier_survival,
    filter_dead_cubes, compute_gods_number,
    build_level_cubes, propagate_levels,
    prepare_cubes, post_cycle_analysis,
    FIMReconstructor, ReconstructionResult,
    ScannedFile,
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
    "cobol": os.path.join(CORPUS_DIR, "banking.cob"),
}


def p(s):
    try:
        print(s, flush=True)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode(), flush=True)


def build_corpus(file_paths: dict[str, str], store: CubeStore):
    """
    Build cubes from all corpus files.
    Returns cubes list, ast_hints dict, file contents dict.
    """
    all_cubes = []
    all_contents = {}
    scanned_files = []

    for lang, fpath in file_paths.items():
        if not os.path.exists(fpath):
            p(f"  SKIP: {fpath} not found")
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        all_contents[fpath] = content
        cubes = subdivide_file(content=content, file_path=fpath, target_tokens=112)

        for cube in cubes:
            store.save_cube(cube)
        all_cubes.extend(cubes)

        ext = os.path.splitext(fpath)[1]
        scanned_files.append(ScannedFile(
            path=fpath, content=content, language=lang,
            extension=ext, size=len(content),
            lines=content.count('\n') + 1
        ))

        p(f"  {lang:<12} {os.path.basename(fpath):<20} {len(cubes):>4} cubes")

    # Assign neighbors (sequential, within same file)
    assign_neighbors(all_cubes, [], store, max_neighbors=9)

    # Extract AST hints BEFORE destruction (the constraints)
    ast_hints = extract_all_ast_hints(all_cubes)

    p(f"\n  TOTAL: {len(all_cubes)} cubes, {len(ast_hints)} AST hint sets")

    return all_cubes, ast_hints, all_contents, scanned_files


def build_mycelium_from_corpus(contents: dict[str, str]):
    """Build mycelium from all corpus file contents."""
    try:
        from mycelium import Mycelium
        myc_tmp = tempfile.mkdtemp()
        myc_path = os.path.join(myc_tmp, "mycelium.json")
        myc = Mycelium(myc_path)

        for fpath, content in contents.items():
            # observe() takes a list of concepts, not raw content
            words = list(set(content.lower().split()))[:200]
            myc.observe(words)

        stats = myc.stats()
        p(f"  Mycelium: {stats.get('total_connections', 0)} connections, "
          f"{stats.get('total_fusions', 0)} fusions")
        return myc, myc_tmp
    except Exception as e:
        p(f"  Mycelium init error: {e}")
        return None, None


def run_cycle(cubes, store, provider, ast_hints, healed, cycle_num,
              mycelium=None, all_cubes=None):
    """
    Run one full destruction/reconstruction cycle.
    Delegates to cube.run_destruction_cycle() — all bricks wired inside the engine.
    """
    n = len(cubes)
    to_heal_count = sum(1 for c in cubes if c.id not in healed)

    if to_heal_count == 0:
        return [], healed

    # The engine handles everything: lexicon, AST, Hebbian, mycelium, wagon
    results = run_destruction_cycle(
        cubes, store, provider,
        cycle_num=cycle_num,
        ncd_threshold=0.3,
        ast_hints=ast_hints,
        mycelium=mycelium,
        healed=healed,
    )

    # Print per-cube results
    for result in results:
        status = "SHA!" if result.exact_match else ("OK" if result.success else "FAIL")
        p(f"    [{result.cube_id[:50]:<50}] NCD={result.ncd_score:.3f} {status}")

    # Stats
    exact_count = sum(1 for r in results if r.exact_match)
    success_count = sum(1 for r in results if r.success)

    p(f"\n    Cycle {cycle_num}: {success_count}/{to_heal_count} healed "
      f"({exact_count} SHA exact), cumul {len(healed)}/{n} "
      f"({100*len(healed)/n:.1f}%)")

    return results, healed


def run_full_pipeline(file_paths: dict[str, str], provider, max_cycles=10):
    """
    Full pipeline: all bricks, all cycles, all learning.
    """
    p(f"\n{'#'*70}")
    p(f"  CUBE FULL PIPELINE")
    p(f"  Provider: {provider.name}")
    p(f"  Max cycles: {max_cycles}")
    p(f"{'#'*70}\n")

    # Setup
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_full.db")
    store = CubeStore(db_path)

    # ─── Phase 1: Build corpus ─────────────────────────────────────
    p("  === PHASE 1: BUILD CORPUS ===")
    all_cubes, ast_hints, contents, scanned_files = build_corpus(file_paths, store)
    n_total = len(all_cubes)

    if n_total == 0:
        p("  No cubes built. Nothing to do.")
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)
        return

    # ─── Phase 2: Build mycelium ───────────────────────────────────
    p("\n  === PHASE 2: BUILD MYCELIUM ===")
    mycelium, myc_tmp = build_mycelium_from_corpus(contents)

    # ─── Phase 3: Pre-filter (B25 danger + B21 survey prop) ────────
    p("\n  === PHASE 3: PRE-FILTER (B25 + B21) ===")
    deps = parse_dependencies(scanned_files)
    # If no cross-file deps found (standalone corpus files), skip dead filter
    # — B25 would mark ALL cubes as dead since they don't import each other
    use_deps = deps if deps else None
    # On cold start (no cycle history), skip survey prop — all cubes are cold
    # B21 survey propagation is useful after N cycles, not on first run
    active_cubes, filter_stats = prepare_cubes(all_cubes, store, use_deps,
                                                use_survey=False)
    dead_count = filter_stats['dead']
    trivial_count = filter_stats['trivial']
    if dead_count or trivial_count:
        p(f"  {dead_count} dead cubes (comments/TODOs)")
        p(f"  {trivial_count} trivial cubes (survey propagation)")
        p(f"  {len(active_cubes)} active cubes to reconstruct")
    else:
        p(f"  All {len(all_cubes)} cubes are active")

    # ─── Phase 4: Cycle loop ──────────────────────────────────────
    healed = set()
    all_cycle_stats = []
    total_t0 = time.time()

    for cycle in range(1, max_cycles + 1):
        p(f"\n  {'='*60}")
        p(f"  CYCLE {cycle} — {len(healed)}/{len(active_cubes)} healed")
        p(f"  {'='*60}")

        t0 = time.time()
        results, healed = run_cycle(
            active_cubes, store, provider, ast_hints, healed, cycle,
            mycelium=mycelium, all_cubes=all_cubes,
        )
        elapsed = time.time() - t0

        # Compute cycle stats
        ncds = [r.ncd_score for r in results]
        exact_count = sum(1 for r in results if r.exact_match)
        success_count = sum(1 for r in results if r.success)
        avg_ncd = sum(ncds) / len(ncds) if ncds else 1.0

        stats = {
            'cycle': cycle,
            'attempted': len(results),
            'success': success_count,
            'exact': exact_count,
            'total_healed': len(healed),
            'total_cubes': len(active_cubes),
            'pct': 100 * len(healed) / max(1, len(active_cubes)),
            'avg_ncd': avg_ncd,
            'elapsed': elapsed,
        }
        all_cycle_stats.append(stats)

        # B26: God's Number
        try:
            gods = compute_gods_number(active_cubes, store, deps, threshold=0.5)
            p(f"    God's Number: {gods.gods_number} hot cubes "
              f"(LRC>={gods.bounds['lrc_lower']}, "
              f"MERA~{gods.bounds['mera_estimate']})")
        except Exception:
            pass

        # B24: Kaplan-Meier survival for worst cubes
        worst = sorted(active_cubes, key=lambda c: c.temperature, reverse=True)[:5]
        if worst and cycle > 1:
            p(f"    Hottest cubes (hardest to reconstruct):")
            for w in worst:
                surv = kaplan_meier_survival(w, store)
                p(f"      {w.id[:50]:<50} T={w.temperature:.2f} S={surv:.2f}")

        # Check convergence
        if len(healed) == len(active_cubes):
            p(f"\n  *** 100% CONVERGENCE at cycle {cycle}! ***")
            break

        # Check no progress
        if len(results) > 0 and success_count == 0 and cycle > 2:
            p(f"  No progress at cycle {cycle} — stopping.")
            break

    total_time = time.time() - total_t0

    # ─── Phase 5: Post-cycle analysis (ALL remaining bricks) ──────
    p(f"\n  === PHASE 5: POST-CYCLE ANALYSIS ===")
    analysis = post_cycle_analysis(active_cubes, store, deps)

    if 'levels' in analysis and not isinstance(analysis['levels'], dict) or \
       (isinstance(analysis.get('levels'), dict) and 'error' not in analysis.get('levels', {})):
        p(f"  B27+B28 Levels: {analysis.get('levels', {})}")
    if isinstance(analysis.get('rg_groups'), int):
        p(f"  B9 Laplacian RG: {analysis['rg_groups']} spectral groups "
          f"(avg size {analysis.get('rg_avg_size', 0):.1f})")
    if isinstance(analysis.get('cheeger'), dict) and 'h_estimate' in analysis['cheeger']:
        p(f"  B10 Cheeger: h={analysis['cheeger']['h_estimate']:.3f} "
          f"(lambda2={analysis['cheeger']['lambda_2']:.3f})")
    if isinstance(analysis.get('gods_number'), dict) and 'value' in analysis['gods_number']:
        gn = analysis['gods_number']
        p(f"  B26 God's Number: {gn['value']} hot / {gn['total']} total")
    if isinstance(analysis.get('heatmap'), dict):
        p(f"  B35 Heatmap: {len(analysis['heatmap'])} files")
    if analysis.get('auto_repair_candidates'):
        p(f"  B37 Auto-repair candidates: {analysis['auto_repair_candidates']}")

    # ─── Final report ─────────────────────────────────────────────
    p(f"\n{'#'*70}")
    p(f"  FINAL REPORT — FULL PIPELINE")
    p(f"{'#'*70}")
    p(f"  {'Cycle':>6} {'Try':>5} {'OK':>5} {'SHA':>5} {'Cumul':>6} "
      f"{'%':>7} {'NCD':>7} {'Time':>7}")
    p(f"  {'─'*55}")
    for s in all_cycle_stats:
        p(f"  {s['cycle']:>6} {s['attempted']:>5} {s['success']:>5} "
          f"{s['exact']:>5} {s['total_healed']:>6} {s['pct']:>6.1f}% "
          f"{s['avg_ncd']:>7.3f} {s['elapsed']:>6.1f}s")
    p(f"  {'─'*55}")
    p(f"  Total: {total_time:.1f}s")
    p(f"  Final: {len(healed)}/{len(active_cubes)} healed "
      f"({100*len(healed)/max(1, len(active_cubes)):.1f}%)")

    p(f"  Pre-filter: {filter_stats['dead']} dead, "
      f"{filter_stats['trivial']} trivial, "
      f"{len(active_cubes)} active / {len(all_cubes)} total")

    p(f"{'#'*70}")

    # Save report
    report_path = os.path.join(CORPUS_DIR, "FULL_PIPELINE.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"Cube Full Pipeline — {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Provider: {provider.name}\n")
        f.write(f"Cubes: {len(active_cubes)} active / {len(all_cubes)} total "
                f"({filter_stats['dead']} dead, {filter_stats['trivial']} trivial)\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"{'Cycle':>6} {'Try':>5} {'OK':>5} {'SHA':>5} {'Cumul':>6} "
                f"{'%':>7} {'NCD':>7}\n")
        f.write(f"{'─'*45}\n")
        for s in all_cycle_stats:
            f.write(f"{s['cycle']:>6} {s['attempted']:>5} {s['success']:>5} "
                    f"{s['exact']:>5} {s['total_healed']:>6} {s['pct']:>6.1f}% "
                    f"{s['avg_ncd']:>7.3f}\n")
        f.write(f"\nTotal time: {total_time:.1f}s\n")
        f.write(f"\n--- Post-Cycle Analysis ---\n")
        for key, val in analysis.items():
            f.write(f"{key}: {val}\n")
    p(f"\n  Report saved: {report_path}")

    # Cleanup
    store.close()
    shutil.rmtree(tmp, ignore_errors=True)
    if myc_tmp:
        shutil.rmtree(myc_tmp, ignore_errors=True)

    return all_cycle_stats


def main():
    parser = argparse.ArgumentParser(description="Cube Full Pipeline")
    parser.add_argument("--provider", default="ollama",
                        choices=["ollama", "claude", "haiku"],
                        help="LLM provider")
    parser.add_argument("--model", help="Model override")
    parser.add_argument("--file", help="Single file to test")
    parser.add_argument("--lang", help="Single language from corpus")
    parser.add_argument("--cycles", type=int, default=10, help="Max cycles")
    parser.add_argument("--url", default="http://localhost:11434",
                        help="Ollama URL")
    args = parser.parse_args()

    # Provider setup
    if args.provider == "claude":
        model = args.model or "claude-sonnet-4-6"
        provider = ClaudeProvider(model=model)
        p(f"Provider: Claude ({model}) — API cost")
    elif args.provider == "haiku":
        model = args.model or "claude-haiku-4-5-20251001"
        provider = ClaudeProvider(model=model)
        p(f"Provider: Haiku ({model}) — cheap API")
    else:
        model = args.model or "qwen2.5-coder:7b"
        provider = OllamaProvider(model=model, base_url=args.url)
        p(f"Provider: Ollama ({model}) — $0.00")
        p(f"FIM: {provider.supports_fim}")

    # Select files
    if args.file:
        ext = os.path.splitext(args.file)[1].lstrip('.')
        files = {ext: args.file}
    elif args.lang:
        if args.lang in CORPUS_FILES:
            files = {args.lang: CORPUS_FILES[args.lang]}
        else:
            p(f"Unknown lang: {args.lang}. Available: {list(CORPUS_FILES.keys())}")
            sys.exit(1)
    else:
        files = {lang: fpath for lang, fpath in CORPUS_FILES.items()
                 if os.path.exists(fpath)}

    run_full_pipeline(files, provider, max_cycles=args.cycles)


if __name__ == "__main__":
    main()
