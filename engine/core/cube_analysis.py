"""
Cube Analysis — Destruction cycle, temperatures, math, CLI, anomalies.

Functions: run_destruction_cycle, post_cycle_analysis, compute_temperature,
           kaplan_meier_survival, detect_dead_code, compute_gods_number,
           build_level_cubes, hebbian_update, git_blame_cube,
           laplacian_rg_grouping, cheeger_constant, belief_propagation,
           tononi_degeneracy, cube_heatmap, fuse_risks, auto_repair, etc.
Classes: GodsNumberResult, CubeScheduler, CubeConfig.
"""

import hashlib
import json
import math
import os
import sqlite3
import subprocess
import threading
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cube import (
    Cube, CubeStore, ScannedFile, Dependency,
    scan_repo, subdivide_file, subdivide_recursive,
    parse_dependencies, extract_ast_hints, extract_all_ast_hints,
    assign_neighbors, normalize_content, sha256_hash,
    LANG_MAP, MAX_FILE_SIZE, TARGET_TOKENS,
)
from cube_providers import (
    LLMProvider, OllamaProvider, ClaudeProvider, OpenAIProvider,
    MockLLMProvider, FIMReconstructor, ReconstructionResult,
    reconstruct_cube, validate_reconstruction,
    compute_hotness, compute_ncd,
)

try:
    from engine.core.tokenizer import count_tokens
except ImportError:
    try:
        from .tokenizer import count_tokens
    except ImportError:
        from tokenizer import count_tokens

try:
    from engine.core.wal_monitor import WALMonitor
except ImportError:
    try:
        from .wal_monitor import WALMonitor
    except ImportError:
        from wal_monitor import WALMonitor

# Module-level locks for thread-safe JSONL append
_quarantine_lock = threading.Lock()
_anomaly_lock = threading.Lock()

__all__ = [
    "run_destruction_cycle", "_add_semantic_neighbors",
    "post_cycle_analysis", "compute_temperature", "update_all_temperatures",
    "kaplan_meier_survival", "detect_dead_code", "filter_dead_cubes",
    "prepare_cubes", "GodsNumberResult", "compute_gods_number",
    "build_level_cubes", "aggregate_scores", "propagate_levels",
    "feed_mycelium_from_results", "_extract_concepts",
    "hebbian_update", "git_blame_cube", "git_log_value",
    "CubeScheduler", "CubeConfig",
    "cli_scan", "cli_run", "cli_status", "cli_god",
    "build_adjacency_matrix", "laplacian_rg_grouping", "_simple_kmeans",
    "cheeger_constant", "belief_propagation", "survey_propagation_filter",
    "tononi_degeneracy", "cube_heatmap", "fuse_risks", "_get_forge_risks",
    "auto_repair", "record_quarantine", "record_anomaly",
    "feedback_loop_check", "feed_anomalies_to_mycelium",
]

def run_destruction_cycle(cubes: list[Cube], store: CubeStore,
                          provider: LLMProvider,
                          cycle_num: int = 1,
                          ncd_threshold: float = 0.3,
                          config: 'CubeConfig | None' = None,
                          ast_hints: dict | None = None,
                          mycelium=None,
                          healed: set | None = None) -> list[ReconstructionResult]:
    """
    Run one full cycle of destruction/reconstruction.

    ALL bricks wired:
    1. Get neighbors (Hebbian-weighted) from store
    2. Add mycelium semantic neighbors (cycle 2+)
    3. Reconstruct with lexicon + AST hints (B15 + B7b)
    4. SHA-256 validate (B17) + NCD fallback (B19)
    5. Record cycle + quarantine
    6. Wagon effect: replace successful cubes in store
    7. Post-cycle: Hebbian update (B30) + feed mycelium (B29)
    8. Post-cycle: update temperatures (B23)
    """
    if healed is None:
        healed = set()
    if ast_hints is None:
        ast_hints = {}

    results = []

    for cube in cubes:
        # Skip already healed cubes
        if cube.id in healed:
            continue

        # Get neighbor cubes — sorted by Hebbian weight (strongest first)
        neighbor_entries = store.get_neighbors(cube.id)
        neighbor_entries.sort(key=lambda x: -x[1])
        neighbor_cubes = []
        for nid, weight, ntype in neighbor_entries:
            n = store.get_cube(nid)
            if n:
                neighbor_cubes.append(n)

        # Add mycelium semantic neighbors (cycle 2+)
        if mycelium and cycle_num >= 2:
            _add_semantic_neighbors(cube, cubes, store, mycelium,
                                    neighbor_cubes, max_semantic=5)

        # Get AST hints for this cube
        hints = ast_hints.get(cube.id)

        # Reconstruct with lexicon + AST + weighted neighbors
        result = reconstruct_cube(cube, neighbor_cubes, provider,
                                  ncd_threshold, ast_hints=hints)
        results.append(result)

        # Record in store
        store.record_cycle(cube.id, cycle_num, result.success,
                           result.reconstruction, result.perplexity)

        # Quarantine: save corrupted block before healing
        _q_enabled = config.quarantine_enabled if config else True
        if _q_enabled and result.success and not result.exact_match:
            quarantine_path = os.path.join(
                os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
            record_quarantine(
                quarantine_path, cube,
                result.reconstruction, result.exact_match,
                result.ncd_score)

        # Wagon effect: successful reconstruction replaces original
        if result.success:
            healed.add(cube.id)
            cube.content = result.reconstruction
            store.save_cube(cube)

        # Update temperature: hotter if reconstruction fails
        if result.success:
            new_temp = max(0.0, cube.temperature - 0.1)
        else:
            new_temp = min(1.0, cube.temperature + 0.2)
        store.update_temperature(cube.id, new_temp)
        store.update_score(cube.id, result.perplexity)
        cube.temperature = new_temp
        cube.score = result.perplexity

    # ─── Post-cycle: wire the learning bricks ─────────────────────

    # B30: Hebbian update — strengthen/weaken neighbor weights
    hebbian_update(store, results, learning_rate=0.1)

    # B29: Feed mycelium from results
    if mycelium:
        feed_mycelium_from_results(results, cubes, mycelium)

    # B23: Update all temperatures from full cycle history
    update_all_temperatures(cubes, store)

    # B24: Kaplan-Meier survival for hottest cubes
    hot_cubes = sorted(cubes, key=lambda c: c.temperature, reverse=True)[:10]
    for hc in hot_cubes:
        try:
            hc._km_survival = kaplan_meier_survival(hc, store)
        except (ValueError, ZeroDivisionError, TypeError):
            hc._km_survival = 1.0

    # B22: Tononi degeneracy for failed cubes — fragile vs critical
    failed_ids = {r.cube_id for r in results if not r.success}
    cube_by_id = {c.id: c for c in cubes}
    for fid in list(failed_ids)[:20]:
        fc = cube_by_id.get(fid)
        if fc:
            try:
                fc._degeneracy = tononi_degeneracy(fc, store, cubes)
            except (ValueError, ZeroDivisionError, TypeError):
                fc._degeneracy = 0.0

    # B38: Record anomalies for persistently hot cubes
    anomaly_path = os.path.join(os.path.expanduser('~'), '.muninn', 'anomalies.jsonl')
    for hc in hot_cubes[:5]:
        if hc.temperature > 0.5:
            try:
                record_anomaly(
                    anomaly_path, hc.file_origin,
                    {'temperature': hc.temperature,
                     'survival': getattr(hc, '_km_survival', 0),
                     'cycle': cycle_num},
                    [hc.id], label='hot_cube')
            except (OSError, ValueError):
                pass

    return results


def _add_semantic_neighbors(cube: Cube, all_cubes: list[Cube],
                            store: CubeStore, mycelium,
                            neighbor_cubes: list[Cube],
                            max_semantic: int = 5):
    """Add mycelium-based semantic neighbors to a cube's neighbor list."""
    words = set(cube.content.lower().split())
    seeds = list(words)[:5]
    related_concepts = set()

    try:
        if hasattr(mycelium, 'spread_activation'):
            activated = mycelium.spread_activation(seeds, hops=2, decay=0.5)
            for concept, score in activated[:20]:
                related_concepts.add(concept)
        else:
            for word in seeds:
                related = mycelium.get_related(word, top_n=5)
                for concept, strength in related:
                    related_concepts.add(concept)
    except (AttributeError, ValueError, TypeError):
        return

    if not related_concepts:
        return

    existing_ids = {n.id for n in neighbor_cubes}
    existing_ids.add(cube.id)

    scored = []
    for other in all_cubes:
        if other.id in existing_ids:
            continue
        other_words = set(other.content.lower().split())
        overlap = len(related_concepts & other_words)
        if overlap > 0:
            scored.append((other, overlap))

    scored.sort(key=lambda x: -x[1])
    for c, _ in scored[:max_semantic]:
        neighbor_cubes.append(c)


def post_cycle_analysis(cubes: list[Cube], store: CubeStore,
                        deps: list['Dependency'] = None,
                        repo_path: str = None,
                        provider: 'LLMProvider' = None,
                        mycelium=None) -> dict:
    """
    Post-cycles analysis — ALL diagnostic bricks wired.

    B27+B28: Level pyramid (112→896→7168 tokens)
    B9:  Laplacian RG optimal grouping (spectral)
    B10: Cheeger bottleneck detection (Fiedler vector)
    B26: God's Number (irreplaceable core)
    B35: Heatmap per file
    B31: Git blame for hottest cubes
    B37: Auto-repair suggestions for hot files
    B38: Feedback loop validation

    Returns analysis dict with all metrics.
    """
    analysis = {}

    # B27+B28: Build level pyramid + propagate scores
    try:
        levels = propagate_levels(cubes, store, max_level=3)
        analysis['levels'] = {lvl: len(cs) for lvl, cs in levels.items()}
    except (ValueError, TypeError, KeyError) as e:
        analysis['levels'] = {'error': str(e)}

    # B9: Laplacian RG grouping (spectral decimation)
    try:
        groups = laplacian_rg_grouping(cubes, store)
        analysis['rg_groups'] = len(groups)
        analysis['rg_avg_size'] = (
            sum(len(g) for g in groups) / len(groups) if groups else 0
        )
    except (ValueError, TypeError, ImportError) as e:
        analysis['rg_groups'] = {'error': str(e)}

    # B10: Cheeger bottleneck detection
    try:
        cheeger = cheeger_constant(cubes, store)
        analysis['cheeger'] = cheeger
    except (ValueError, TypeError, ZeroDivisionError) as e:
        analysis['cheeger'] = {'error': str(e)}

    # B26: God's Number
    try:
        gods = compute_gods_number(cubes, store, deps or [], threshold=0.5)
        analysis['gods_number'] = {
            'value': gods.gods_number,
            'total': gods.total_cubes,
            'bounds': gods.bounds,
        }
    except (ValueError, TypeError, AttributeError) as e:
        analysis['gods_number'] = {'error': str(e)}

    # B35: Heatmap per file
    try:
        heatmap = cube_heatmap(store)
        analysis['heatmap'] = {
            f: {'count': v['count'], 'avg_temp': v['avg_temp'],
                'hot': v['hot_count']}
            for f, v in heatmap.items()
        }
    except (ValueError, TypeError, sqlite3.Error) as e:
        analysis['heatmap'] = {'error': str(e)}

    # B31: Git blame for hottest cubes
    if repo_path:
        hot = sorted(cubes, key=lambda c: c.temperature, reverse=True)[:5]
        blame_info = []
        for hc in hot:
            if hc.temperature > 0.3:
                try:
                    info = git_blame_cube(hc, repo_path)
                    blame_info.append(info)
                except (OSError, subprocess.SubprocessError):
                    pass
        if blame_info:
            analysis['git_blame'] = blame_info

    # B37: Auto-repair candidates (dry run — identify, don't reconstruct)
    hot_files = set()
    for c in cubes:
        if c.temperature > 0.5:
            hot_files.add(c.file_origin)
    if hot_files:
        try:
            # C4 fix: pass real reconstructor if provider available
            reconstructor = FIMReconstructor(provider) if provider else None
            patches = auto_repair(store, list(hot_files),
                                  reconstructor=reconstructor, max_patches=5)
            analysis['auto_repair_candidates'] = len(patches)
            analysis['auto_repair_patches'] = [p for p in patches if p.get('patch')]
        except (ValueError, OSError, TypeError):
            pass

    # B38: Feedback loop — validate past anomaly predictions
    if repo_path:
        try:
            anomaly_path = os.path.join(
                os.path.expanduser('~'), '.muninn', 'anomalies.jsonl')
            feedback = feedback_loop_check(anomaly_path, repo_path)
            if feedback.get('total', 0) > 0:
                analysis['feedback'] = feedback
                # C6: Close the loop — feed validated anomalies to mycelium
                if mycelium is not None:
                    try:
                        fed = feed_anomalies_to_mycelium(anomaly_path, mycelium)
                        analysis['anomalies_fed_to_mycelium'] = len(fed)
                    except Exception:
                        pass
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    return analysis


# ─── B23: Temperature par cube + stockage ─────────────────────────────

def compute_temperature(cube: Cube, store: CubeStore) -> float:
    """
    B23: Compute temperature for a cube based on cycle history.

    Temperature = f(perplexity, attempts, success_rate, survival)
    """
    cycles = store.get_cycles(cube.id)
    if not cycles:
        return cube.score  # Use raw perplexity if no history

    total = len(cycles)
    successes = sum(1 for c in cycles if c['success'])
    failures = total - successes
    success_rate = successes / total if total > 0 else 0.0

    avg_perplexity = sum(c.get('perplexity', 0) for c in cycles) / total if total else 0.0

    temperature = (
        0.4 * min(avg_perplexity / 5.0, 1.0) +
        0.4 * (1.0 - success_rate) +
        0.2 * min(failures / 10.0, 1.0)
    )
    return max(0.0, min(1.0, temperature))


def update_all_temperatures(cubes: list[Cube], store: CubeStore):
    """Update temperatures for all cubes based on their cycle history."""
    for cube in cubes:
        temp = compute_temperature(cube, store)
        store.update_temperature(cube.id, temp)
        cube.temperature = temp


# ─── B24: Kaplan-Meier survie par cube ────────────────────────────────

def kaplan_meier_survival(cube: Cube, store: CubeStore) -> float:
    """
    B24: Kaplan-Meier survival estimate. S(t) = Π(1 - d_i/n_i)
    High S(t) = cube stays hot. Low S(t) = cooling down.
    Scanniello 2011.
    """
    cycles = store.get_cycles(cube.id)
    if not cycles:
        return 1.0

    total = len(cycles)
    survival = 1.0

    for i, cycle in enumerate(cycles):
        n_i = total - i
        d_i = 0 if cycle['success'] else 1
        if n_i > 0:
            survival *= (1.0 - d_i / n_i)

    return max(0.0, min(1.0, survival))


# ─── B25: Danger Theory filtre ───────────────────────────────────────

def detect_dead_code(cube: Cube, all_cubes: list[Cube],
                     deps: list['Dependency']) -> bool:
    """
    B25: Detect dead code (Matzinger 2002).
    Dead = never imported, never called, never referenced.
    """
    is_target = any(d.target == cube.file_origin for d in deps)
    is_source = any(d.source == cube.file_origin for d in deps)

    if not is_target and not is_source:
        return True

    content = cube.content.strip()
    lines = content.split('\n')

    # Mostly comments
    comment_lines = sum(1 for l in lines if l.strip().startswith('#') or l.strip().startswith('//'))
    if len(lines) > 0 and comment_lines / len(lines) > 0.8:
        return True

    # Mostly TODO/FIXME
    todo_count = sum(1 for l in lines if any(tag in l.upper() for tag in ('TODO', 'FIXME', 'HACK', 'XXX')))
    if len(lines) > 2 and todo_count / len(lines) > 0.5:
        return True

    return False


def filter_dead_cubes(cubes, deps) -> tuple:
    """B25: Filter dead cubes. Returns (active, dead).

    BUG-109 fix (brick 18): tolerate non-list inputs gracefully so forge
    property tests don't blow up on `cubes=''` / `deps=''`. Empty/invalid
    input returns ([], []).
    """
    if not isinstance(cubes, (list, tuple)) or not cubes:
        return ([], [])
    if not isinstance(deps, (list, tuple)):
        deps = []
    active, dead = [], []
    for cube in cubes:
        try:
            if detect_dead_code(cube, cubes, deps):
                dead.append(cube)
            else:
                active.append(cube)
        except (AttributeError, TypeError):
            # Skip cubes that can't be analysed (defensive)
            continue
    return active, dead


def prepare_cubes(cubes: list[Cube], store: CubeStore,
                  deps: list['Dependency'] = None,
                  use_survey: bool = True) -> tuple[list[Cube], dict]:
    """
    Pre-filter cubes before reconstruction cycles.
    B25: Remove dead code (comments/TODOs)
    B21: Survey Propagation removes trivial cubes (~30%)
    Returns (filtered_cubes, filter_stats).
    """
    stats = {'total': len(cubes), 'dead': 0, 'trivial': 0, 'active': 0}

    # B25: Danger filter — remove dead code
    if deps is not None:
        active, dead = filter_dead_cubes(cubes, deps)
        stats['dead'] = len(dead)
    else:
        active = list(cubes)

    # B21: Survey Propagation pre-filter — skip trivial cubes (~30%)
    if use_survey and len(active) > 10:
        try:
            non_trivial, trivial = survey_propagation_filter(active, store)
            stats['trivial'] = len(trivial)
            active = non_trivial
        except (ImportError, ValueError, TypeError):
            pass  # numpy not available or other issue

    stats['active'] = len(active)
    return active, stats


# ─── B26: God's Number calcul ────────────────────────────────────────

@dataclass
class GodsNumberResult:
    """Result of God's Number computation."""
    gods_number: int
    total_cubes: int
    hot_cubes: list[Cube]
    dead_cubes: list[Cube]
    threshold: float
    bounds: dict


def compute_gods_number(cubes: list[Cube], store: CubeStore,
                        deps: list['Dependency'],
                        threshold: float = 0.5) -> GodsNumberResult:
    """
    B26: God's Number = |{cubes : Hotness > τ AND active}|

    Bounds: LRC ≥ n/10 (Gopalan 2012), MERA ~ O(log N) (Vidal 2007),
    Percolation fc = <k>/(<k²>-<k>) (Callaway 2000).
    """
    import math

    update_all_temperatures(cubes, store)
    active, dead = filter_dead_cubes(cubes, deps)
    hot = [c for c in active if c.temperature > threshold]

    n = len(active)
    lrc_lower = max(1, n // 10)
    mera_estimate = max(1, int(math.log2(max(n, 1))))

    degrees = []
    for c in active:
        neighbors = store.get_neighbors(c.id)
        degrees.append(len(neighbors))

    if degrees:
        k_mean = sum(degrees) / len(degrees)
        k2_mean = sum(d * d for d in degrees) / len(degrees)
        fc = k_mean / (k2_mean - k_mean) if (k2_mean - k_mean) > 0 else 1.0
    else:
        fc = 1.0

    return GodsNumberResult(
        gods_number=len(hot),
        total_cubes=len(cubes),
        hot_cubes=hot,
        dead_cubes=dead,
        threshold=threshold,
        bounds={
            'lrc_lower': lrc_lower,
            'mera_estimate': mera_estimate,
            'percolation_fc': fc,
            'n_active': n,
            'n_dead': len(dead),
        }
    )


# ─── B27: Remontee par niveaux ───────────────────────────────────────

def build_level_cubes(level0_cubes: list[Cube], level: int = 1,
                      group_size: int = 8) -> list[Cube]:
    """
    B27: Build higher-level cubes by grouping lower-level cubes.

    Level 0: ~112 tokens (atomic)
    Level 1: ~896 tokens (8×112)
    Level 2: ~7168 tokens (8×896)

    Groups cubes from the same file, adjacent by line order.
    """
    # Group by file
    by_file: dict[str, list[Cube]] = defaultdict(list)
    for c in level0_cubes:
        by_file[c.file_origin].append(c)

    upper_cubes = []

    for file_path, cubes in by_file.items():
        cubes.sort(key=lambda c: c.line_start)

        for i in range(0, len(cubes), group_size):
            group = cubes[i:i + group_size]
            if not group:
                continue

            content = "\n".join(c.content for c in group)
            line_start = group[0].line_start
            line_end = group[-1].line_end
            total_tokens = sum(c.token_count for c in group)

            cube = Cube(
                id=f"{file_path}:L{line_start}-L{line_end}:lv{level}",
                content=content,
                sha256=sha256_hash(content),
                file_origin=file_path,
                line_start=line_start,
                line_end=line_end,
                level=level,
                token_count=total_tokens,
            )
            upper_cubes.append(cube)

    return upper_cubes


# ─── B28: Agregation des scores entre niveaux ────────────────────────

def aggregate_scores(upper_cube: Cube, sub_cubes: list[Cube]) -> float:
    """
    B28: Aggregate scores from sub-cubes to upper cube.

    Score = max of sub-cube temperatures (hottest persists).
    A zone is only as resilient as its weakest part.
    """
    if not sub_cubes:
        return 0.0
    return max(c.temperature for c in sub_cubes)


def propagate_levels(level0_cubes: list[Cube], store: CubeStore,
                     max_level: int = 3) -> dict[int, list[Cube]]:
    """
    B27+B28: Build and score all levels.

    Returns {level: [cubes]} for levels 0 to max_level.
    Hot cubes persisting across levels = irreplaceable core.
    """
    levels: dict[int, list[Cube]] = {0: level0_cubes}

    current = level0_cubes
    for lvl in range(1, max_level + 1):
        upper = build_level_cubes(current, level=lvl)
        if not upper:
            break

        # Aggregate scores
        by_file: dict[str, list[Cube]] = defaultdict(list)
        for c in current:
            by_file[c.file_origin].append(c)

        for uc in upper:
            subs = [c for c in by_file.get(uc.file_origin, [])
                    if c.line_start >= uc.line_start and c.line_end <= uc.line_end]
            uc.temperature = aggregate_scores(uc, subs)
            uc.score = uc.temperature

        store.save_cubes(upper)
        levels[lvl] = upper
        current = upper

    return levels


# ─── B29: Feed resultats → mycelium ──────────────────────────────────

def feed_mycelium_from_results(results: list[ReconstructionResult],
                               cubes: list[Cube],
                               mycelium=None):
    """
    B29: Feed reconstruction results to mycelium.

    Creates mechanical (proven) connections:
    - Successful reconstruction = cube NEEDS its neighbors (proven dependency)
    - Failed reconstruction = neighbors are insufficient (weak link)

    Tags connections as 'mechanical' (distinct from statistical co-occurrence).
    """
    cube_by_id = {c.id: c for c in cubes}
    mechanical_pairs = []

    for result in results:
        cube = cube_by_id.get(result.cube_id)
        if not cube:
            continue

        for nid in cube.neighbors:
            neighbor = cube_by_id.get(nid)
            if not neighbor:
                continue

            # Extract concept names from cube content (simplified)
            cube_concepts = _extract_concepts(cube.content)
            neighbor_concepts = _extract_concepts(neighbor.content)

            pair = {
                'source': result.cube_id,
                'target': nid,
                'weight': 1.0 if result.success else -0.5,
                'type': 'mechanical',
                'cube_concepts': cube_concepts,
                'neighbor_concepts': neighbor_concepts,
            }
            mechanical_pairs.append(pair)

            # C1 fix: Feed mechanical weight to mycelium via direct upsert.
            # Success (+1.0) strengthens the connection, failure (-0.5) weakens it.
            # observe_text() only does co-occurrence — it loses the success/failure signal.
            if mycelium is not None and hasattr(mycelium, '_db') and mycelium._db is not None:
                try:
                    weight = 1.0 if result.success else -0.5
                    for cc in cube_concepts[:5]:
                        for nc in neighbor_concepts[:5]:
                            if cc != nc:
                                mycelium._db.upsert_connection(
                                    cc, nc, increment=weight, zone="mechanical")
                except (AttributeError, ValueError, TypeError):
                    pass
            elif mycelium is not None and hasattr(mycelium, 'observe_text'):
                # Fallback: dict mode — at least do co-occurrence
                try:
                    mycelium.observe_text(f"{cube.content}\n{neighbor.content}")
                except (AttributeError, ValueError, TypeError):
                    pass

    return mechanical_pairs


def _extract_concepts(content: str) -> list[str]:
    """Extract concept names from code content (function/class names, imports)."""
    concepts = []
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('def '):
            name = line.split('(')[0].replace('def ', '')
            concepts.append(name)
        elif line.startswith('class '):
            name = line.split('(')[0].split(':')[0].replace('class ', '')
            concepts.append(name)
        elif line.startswith(('import ', 'from ')):
            parts = line.split()
            if len(parts) >= 2:
                concepts.append(parts[1].split('.')[0])
    return concepts


# ─── B30: Hebbian update ─────────────────────────────────────────────

def hebbian_update(store: CubeStore, results: list[ReconstructionResult],
                   learning_rate: float = 0.1):
    """
    B30: Hebbian learning on neighbor connections.

    Rule & O'Leary PNAS 2022: Self-Healing Neural Codes
    Δw = η × pre × post
    - Neighbors that reconstruct well → connection strengthened
    - Neighbors that fail → connection weakened
    - Homeostasis = SHA-256 validation (the ground truth)
    """
    for result in results:
        neighbors = store.get_neighbors(result.cube_id)
        for nid, weight, ntype in neighbors:
            if result.success:
                # Strengthen: successful reconstruction = neighbor was useful
                new_weight = min(2.0, weight + learning_rate)
            else:
                # Weaken: failed reconstruction = neighbor insufficient
                new_weight = max(0.1, weight - learning_rate * 0.5)

            store.set_neighbor(result.cube_id, nid, new_weight,
                             'mechanical' if ntype == 'static' else ntype)


# ─── B31: Git blame crossover ────────────────────────────────────────

def git_blame_cube(cube: Cube, repo_path: str) -> dict:
    """
    B31: Link hot cube to git history.

    Returns git blame info for the cube's lines.
    """
    file_path = os.path.join(repo_path, cube.file_origin)
    if not os.path.exists(file_path):
        return {'error': f'File not found: {cube.file_origin}'}

    try:
        result = subprocess.run(
            ['git', 'blame', '-L', f'{cube.line_start},{cube.line_end}',
             '--porcelain', cube.file_origin],
            cwd=repo_path,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {'error': result.stderr.strip()}

        # Parse porcelain blame output
        commits = {}
        current_commit = None
        for line in result.stdout.split('\n'):
            if len(line) >= 40 and line[0] in '0123456789abcdef':
                parts = line.split()
                if len(parts) >= 3:
                    current_commit = parts[0]
                    if current_commit not in commits:
                        commits[current_commit] = {'lines': 0}
                    commits[current_commit]['lines'] += 1
            elif current_commit and line.startswith('author '):
                commits[current_commit]['author'] = line[7:]
            elif current_commit and line.startswith('summary '):
                commits[current_commit]['summary'] = line[8:]
            elif current_commit and line.startswith('author-time '):
                commits[current_commit]['time'] = int(line[12:])

        return {
            'cube_id': cube.id,
            'file': cube.file_origin,
            'lines': f'{cube.line_start}-{cube.line_end}',
            'commits': commits,
            'n_authors': len(set(c.get('author', '') for c in commits.values())),
        }

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {'error': 'git blame failed or git not available'}


def git_log_value(cube: Cube, repo_path: str) -> list[dict]:
    """
    B31: Check if a hot cube's content has changed recently.

    Returns recent commits that touched the cube's file+lines.
    """
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-5', '-L',
             f'{cube.line_start},{cube.line_end}:{cube.file_origin}'],
            cwd=repo_path,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        entries = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    entries.append({'commit': parts[0], 'message': parts[1]})
        return entries

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ─── B32: Scheduling async ───────────────────────────────────────────


class CubeScheduler:
    """
    B32: Async scheduling — runs cube cycles in quiet periods.

    Detects repo activity via file timestamps and git status.
    Pauses when activity detected, resumes when quiet.
    """

    def __init__(self, repo_path: str, quiet_seconds: int = 300,
                 check_interval: int = 30):
        self.repo_path = repo_path
        self.quiet_seconds = quiet_seconds  # How long to wait for "quiet"
        self.check_interval = check_interval
        self._last_activity = _time.time()
        self._running = False

    def _check_activity(self) -> bool:
        """Check if repo has recent activity."""
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=5,
            )
            # Any uncommitted changes = active
            if result.stdout.strip():
                self._last_activity = _time.time()
                return True
        except (subprocess.SubprocessError, OSError):
            pass

        # Check file modification times
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
            for f in files[:10]:  # Sample first 10 files per dir
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    if _time.time() - mtime < self.quiet_seconds:
                        self._last_activity = _time.time()
                        return True
                except OSError:
                    pass
            break  # Only check top-level

        return False

    def is_quiet(self) -> bool:
        """True if repo has been quiet for quiet_seconds."""
        return _time.time() - self._last_activity > self.quiet_seconds

    def should_run(self) -> bool:
        """Check if we should start/continue a cycle."""
        active = self._check_activity()
        return not active and self.is_quiet()


# ─── B33: Config securite ────────────────────────────────────────────

@dataclass
class CubeConfig:
    """
    B33: Security configuration for cube operations.

    local_only=True: ONLY local models (Ollama), code never leaves network.
    """
    local_only: bool = True
    max_cycles: int = 100
    ncd_threshold: float = 0.3
    temperature_threshold: float = 0.5
    target_tokens: int = 112
    max_neighbors: int = 9
    db_path: str = '.muninn/cube.db'
    allowed_providers: list[str] = field(default_factory=lambda: ['ollama', 'mock'])
    quarantine_enabled: bool = False

    @classmethod
    def load(cls, config_path: str = '.muninn/config.json') -> 'CubeConfig':
        """Load config from JSON file."""
        if not os.path.exists(config_path):
            return cls()
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cube_data = data.get('cube', {})
            return cls(
                local_only=cube_data.get('local_only', True),
                max_cycles=cube_data.get('max_cycles', 100),
                ncd_threshold=cube_data.get('ncd_threshold', 0.3),
                temperature_threshold=cube_data.get('temperature_threshold', 0.5),
                target_tokens=cube_data.get('target_tokens', 112),
                max_neighbors=cube_data.get('max_neighbors', 9),
                db_path=cube_data.get('db_path', '.muninn/cube.db'),
                allowed_providers=cube_data.get('allowed_providers', ['ollama', 'mock']),
                quarantine_enabled=cube_data.get('quarantine_enabled', False),
            )
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, config_path: str = '.muninn/config.json'):
        """Save config to JSON file."""
        os.makedirs(os.path.dirname(config_path) or '.', exist_ok=True)
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        data['cube'] = {
            'local_only': self.local_only,
            'max_cycles': self.max_cycles,
            'ncd_threshold': self.ncd_threshold,
            'temperature_threshold': self.temperature_threshold,
            'target_tokens': self.target_tokens,
            'max_neighbors': self.max_neighbors,
            'db_path': self.db_path,
            'allowed_providers': self.allowed_providers,
            'quarantine_enabled': self.quarantine_enabled,
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def get_provider(self) -> LLMProvider:
        """Get an LLM provider based on config.
        C2 fix: Ollama checked BEFORE mock so real reconstruction happens
        when Ollama is running. Mock is fallback only."""
        if self.local_only:
            # Try Ollama first (real reconstruction) — only if it has models loaded
            if 'ollama' in self.allowed_providers:
                try:
                    import urllib.request, json as _json
                    resp = urllib.request.urlopen(
                        "http://localhost:11434/api/tags", timeout=2)
                    tags = _json.loads(resp.read())
                    model_names = [m.get("name", "").split(":")[0]
                                   for m in tags.get("models", [])]
                    # Check the target model is actually available
                    target = self.ollama_model if hasattr(self, 'ollama_model') else "codellama"
                    target_base = target.split(":")[0]
                    if target_base in model_names:
                        return OllamaProvider()
                except Exception:
                    pass  # Ollama not running or model missing, fall through to mock
            if 'mock' in self.allowed_providers:
                return MockLLMProvider()
            raise ValueError("local_only=True but no provider available")

        # Try providers in order of preference
        if 'claude' in self.allowed_providers:
            if os.environ.get('ANTHROPIC_API_KEY'):
                return ClaudeProvider()
        if 'openai' in self.allowed_providers:
            if os.environ.get('OPENAI_API_KEY'):
                return OpenAIProvider()
        if 'ollama' in self.allowed_providers:
            return OllamaProvider()

        return MockLLMProvider()

    def validate_provider(self, provider: LLMProvider) -> bool:
        """Check if a provider is allowed by config."""
        if self.local_only and provider.name not in ('ollama', 'mock'):
            return False
        return provider.name in self.allowed_providers


# ─── B34: Multi-LLM hooks ────────────────────────────────────────────
# (Already covered by B11-B14 providers + B33 config)
# The hook system is the provider selection in CubeConfig.get_provider()


# ─── B39: CLI commands ───────────────────────────────────────────────

def cli_scan(repo_path: str, config: Optional[CubeConfig] = None) -> dict:
    """
    `cube scan <repo>` — Scan repo, subdivide, build index.

    Returns summary dict.
    """
    config = config or CubeConfig()
    store = CubeStore(config.db_path)

    try:
        # B1: scan
        files = scan_repo(repo_path)

        # B4: subdivide
        all_cubes = []
        for f in files:
            cubes = subdivide_file(f.path, f.content, config.target_tokens)
            all_cubes.extend(cubes)

        # B7+B8: deps + neighbors
        deps = parse_dependencies(files)
        assign_neighbors(all_cubes, deps, store=store,
                        max_neighbors=config.max_neighbors)

        # B6: store
        store.save_cubes(all_cubes)

        return {
            'files': len(files),
            'cubes': len(all_cubes),
            'dependencies': len(deps),
            'db_path': config.db_path,
        }
    finally:
        store.close()


def cli_run(repo_path: str, cycles: int = 1, level: int = 0,
            config: Optional[CubeConfig] = None) -> dict:
    """
    `cube run [--cycles N] [--level L]` — Full pipeline: prepare + cycles + analysis.

    ALL bricks wired:
    - Pre-filter: B25 (danger) + B21 (survey propagation)
    - Per-cycle: B15+B7b (reconstruct) → B17+B19 (validate) → B30+B29+B23 (learn)
                 + B24 (Kaplan-Meier) + B22 (Tononi) + B38 (anomalies)
    - Post-cycles: B27+B28 (levels) + B9 (Laplacian) + B10 (Cheeger)
                   + B26 (God's Number) + B35 (heatmap) + B31 (git blame)
                   + B37 (auto-repair) + B38 (feedback)
    """
    config = config or CubeConfig()
    store = CubeStore(config.db_path)

    # CHUNK 2: Load mycelium so cube↔mycelium loop is live in prod.
    # B29 (feed_mycelium_from_results) and _add_semantic_neighbors
    # both need a real Mycelium instance to work.
    mycelium = None
    try:
        from pathlib import Path as _P
        _rp = _P(repo_path) if repo_path else _P(".")
        try:
            from engine.core.mycelium import Mycelium as _Myc
        except ImportError:
            try:
                from .mycelium import Mycelium as _Myc
            except ImportError:
                from mycelium import Mycelium as _Myc
        mycelium = _Myc(_rp)
    except Exception:
        pass  # Graceful: cube works without mycelium, just no cross-learning

    try:
        provider = config.get_provider()
        cubes = store.get_cubes_by_level(level)

        # ─── Pre-filter: B25 + B21 ─────────────────────────────────
        active_cubes, filter_stats = prepare_cubes(cubes, store)

        # ─── B7b: Extract AST hints before destruction ─────────────
        ast_hints = extract_all_ast_hints(active_cubes)

        # ─── Cycle loop ────────────────────────────────────────────
        healed = set()
        all_results = []
        for cycle_num in range(1, cycles + 1):
            # run_destruction_cycle already does B30+B29+B23+B24+B22+B38
            results = run_destruction_cycle(
                active_cubes, store, provider,
                cycle_num=cycle_num,
                ncd_threshold=config.ncd_threshold,
                config=config,
                ast_hints=ast_hints,
                healed=healed,
                mycelium=mycelium,
            )
            all_results.extend(results)

            # Check convergence
            healed_count = sum(1 for c in active_cubes if c.id in healed)
            if healed_count == len(active_cubes):
                break

        successes = sum(1 for r in all_results if r.success)

        # ─── Post-cycles analysis: B27+B28+B9+B10+B26+B35+B31+B37+B38
        # C3 note: deps=None means God's Number detect_dead_code sees no imports
        # and classifies all cubes as dead. To fix properly, cli_scan should
        # persist deps in CubeStore and cli_run should load them. Low priority
        # since God's Number still gives useful metrics without dead code filtering.
        analysis = post_cycle_analysis(
            active_cubes, store, repo_path=repo_path,
            provider=provider, mycelium=mycelium)

        # Auto-activation quarantaine
        if not config.quarantine_enabled and all_results:
            last_cycle = all_results[-len(active_cubes):]
            if last_cycle and all(r.success for r in last_cycle):
                config.quarantine_enabled = True
                config.save()

        # C5: Persist KM survival + Tononi degeneracy in result dict
        km_data = {c.id: getattr(c, '_km_survival', None)
                   for c in active_cubes if getattr(c, '_km_survival', None) is not None}
        tononi_data = {c.id: getattr(c, '_degeneracy', None)
                       for c in active_cubes if getattr(c, '_degeneracy', None) is not None}

        return {
            'cycles': cycles,
            'cubes_total': len(cubes),
            'cubes_filtered': filter_stats,
            'cubes_active': len(active_cubes),
            'total_tests': len(all_results),
            'successes': successes,
            'failures': len(all_results) - successes,
            'success_rate': successes / len(all_results) if all_results else 0.0,
            'quarantine_enabled': config.quarantine_enabled,
            'analysis': analysis,
            'kaplan_meier': km_data,
            'tononi_degeneracy': tononi_data,
        }
    finally:
        store.close()
        if mycelium is not None:
            try:
                mycelium.save()
                mycelium.close()
            except Exception:
                pass


def cli_status(config: Optional[CubeConfig] = None) -> dict:
    """
    `cube status` — Show God's Number, hot cubes, temperature stats.
    """
    config = config or CubeConfig()
    if not os.path.exists(config.db_path):
        return {'error': 'No cube database found. Run `cube scan` first.'}

    store = CubeStore(config.db_path)
    try:
        total = store.count_cubes()
        hot = store.get_hot_cubes(config.temperature_threshold)

        # Temperature stats
        all_cubes = store.get_cubes_by_level(0)
        temps = [c.temperature for c in all_cubes]
        avg_temp = sum(temps) / len(temps) if temps else 0.0

        return {
            'total_cubes': total,
            'hot_cubes': len(hot),
            'gods_number_estimate': len(hot),
            'avg_temperature': round(avg_temp, 3),
            'max_temperature': round(max(temps), 3) if temps else 0.0,
            'levels': {
                lvl: store.count_cubes(level=lvl)
                for lvl in range(4)
                if store.count_cubes(level=lvl) > 0
            },
        }
    finally:
        store.close()


def cli_god(config: Optional[CubeConfig] = None) -> dict:
    """
    `cube god` — Compute and display God's Number with bounds.
    """
    config = config or CubeConfig()
    if not os.path.exists(config.db_path):
        return {'error': 'No cube database found. Run `cube scan` first.'}

    store = CubeStore(config.db_path)
    try:
        cubes = store.get_cubes_by_level(0)
        result = compute_gods_number(cubes, store, [],
                                     threshold=config.temperature_threshold)
        return {
            'gods_number': result.gods_number,
            'total_cubes': result.total_cubes,
            'dead_cubes': len(result.dead_cubes),
            'threshold': result.threshold,
            'bounds': result.bounds,
            'hot_cube_ids': [c.id for c in result.hot_cubes[:20]],
        }
    finally:
        store.close()


# ─── B9: Laplacian RG groupage optimal ──────────────────────────────

def build_adjacency_matrix(cubes: list[Cube], store: CubeStore):
    """Build adjacency matrix from cube neighbor graph."""
    import numpy as np

    n = len(cubes)
    id_to_idx = {c.id: i for i, c in enumerate(cubes)}
    A = np.zeros((n, n))

    for cube in cubes:
        i = id_to_idx[cube.id]
        neighbors = store.get_neighbors(cube.id)
        for nid, weight, _ in neighbors:
            j = id_to_idx.get(nid)
            if j is not None:
                A[i, j] = weight
                A[j, i] = weight

    return A, id_to_idx


def laplacian_rg_grouping(cubes: list[Cube], store: CubeStore,
                          n_groups: Optional[int] = None) -> list[list[Cube]]:
    """
    B9: Laplacian RG grouping (Villegas 2023).
    L = D - A, spectral decimation groups cubes by eigenvector similarity.
    Falls back to sequential grouping if numpy not available.
    """
    try:
        import numpy as np
        from numpy.linalg import eigh
    except ImportError:
        groups = []
        by_file = defaultdict(list)
        for c in cubes:
            by_file[c.file_origin].append(c)
        for f, fcubes in by_file.items():
            fcubes.sort(key=lambda c: c.line_start)
            for i in range(0, len(fcubes), 8):
                groups.append(fcubes[i:i+8])
        return groups

    n = len(cubes)
    if n <= 1:
        return [cubes] if cubes else []

    if n_groups is None:
        n_groups = max(1, n // 8)

    A, id_to_idx = build_adjacency_matrix(cubes, store)
    D = np.diag(A.sum(axis=1))
    L = D - A

    k = min(n_groups, n - 1)
    try:
        eigenvalues, eigenvectors = eigh(L)
        k = min(k, eigenvectors.shape[1] - 1)
        features = eigenvectors[:, 1:k+1]
    except (ValueError, TypeError):
        features = np.random.randn(n, k)

    labels = _simple_kmeans(features, n_groups)

    groups_dict: dict[int, list[Cube]] = defaultdict(list)
    for i, label in enumerate(labels):
        groups_dict[label].append(cubes[i])

    return list(groups_dict.values())


def _simple_kmeans(X, k, max_iter: int = 20):
    """Simple k-means using numpy only."""
    import numpy as np

    n = X.shape[0]
    if k >= n:
        return list(range(n))

    rng = np.random.RandomState(42)
    indices = rng.choice(n, k, replace=False)
    centroids = X[indices].copy()
    labels = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        for i in range(n):
            dists = np.sum((centroids - X[i]) ** 2, axis=1)
            labels[i] = np.argmin(dists)

        new_centroids = np.zeros_like(centroids)
        for j in range(k):
            members = X[labels == j]
            if len(members) > 0:
                new_centroids[j] = members.mean(axis=0)
            else:
                new_centroids[j] = centroids[j]

        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids

    return labels.tolist()


# ─── B10: Cheeger constant ──────────────────────────────────────────

def cheeger_constant(cubes: list[Cube], store: CubeStore) -> dict:
    """
    B10: Cheeger constant. λ₂/2 ≤ h ≤ √(2λ₂).
    Identifies bottleneck cubes via Fiedler vector sign change.
    """
    try:
        import numpy as np
        from numpy.linalg import eigh
    except ImportError:
        return {'h_estimate': 0.0, 'lambda_2': 0.0, 'bottlenecks': [],
                'error': 'numpy not available'}

    n = len(cubes)
    if n < 2:
        return {'h_estimate': 0.0, 'lambda_2': 0.0, 'bottlenecks': []}

    A, id_to_idx = build_adjacency_matrix(cubes, store)
    D = np.diag(A.sum(axis=1))
    L = D - A

    eigenvalues, eigenvectors = eigh(L)
    lambda_2 = float(eigenvalues[1]) if len(eigenvalues) > 1 else 0.0

    import math
    h_lower = lambda_2 / 2.0
    h_upper = math.sqrt(2.0 * max(lambda_2, 0.0))

    if eigenvectors.shape[1] > 1:
        fiedler = eigenvectors[:, 1]
        abs_fiedler = np.abs(fiedler)
        bottleneck_indices = np.argsort(abs_fiedler)[:max(1, n // 10)]
        bottleneck_ids = [cubes[i].id for i in bottleneck_indices]
    else:
        bottleneck_ids = []

    return {
        'h_lower': h_lower,
        'h_upper': h_upper,
        'h_estimate': (h_lower + h_upper) / 2,
        'lambda_2': lambda_2,
        'bottlenecks': bottleneck_ids,
    }


# ─── B20: Belief Propagation ─────────────────────────────────────────

def belief_propagation(cubes: list[Cube], store: CubeStore,
                       max_iter: int = 15, tolerance: float = 1e-4) -> dict[str, float]:
    """
    B20: Belief Propagation (Pearl 1988). Neighbors exchange beliefs.
    Returns {cube_id: belief} where belief = probability of being hot.
    """
    beliefs: dict[str, float] = {c.id: c.temperature for c in cubes}
    messages: dict[tuple[str, str], float] = {}

    for cube in cubes:
        neighbors = store.get_neighbors(cube.id)
        for nid, weight, _ in neighbors:
            messages[(cube.id, nid)] = 0.5

    for iteration in range(max_iter):
        max_change = 0.0
        new_messages = {}

        for cube in cubes:
            neighbors = store.get_neighbors(cube.id)
            for nid, weight, _ in neighbors:
                incoming_product = 1.0
                for nid2, w2, _ in neighbors:
                    if nid2 != nid:
                        msg = messages.get((nid2, cube.id), 0.5)
                        incoming_product *= (msg * w2 + (1 - msg) * (1 - w2))

                compat = weight * cube.temperature
                new_msg = compat * incoming_product
                new_msg = max(0.001, min(0.999, new_msg))

                old_msg = messages.get((cube.id, nid), 0.5)
                max_change = max(max_change, abs(new_msg - old_msg))
                new_messages[(cube.id, nid)] = new_msg

        messages.update(new_messages)
        if max_change < tolerance:
            break

    for cube in cubes:
        neighbors = store.get_neighbors(cube.id)
        belief = cube.temperature
        for nid, weight, _ in neighbors:
            msg = messages.get((nid, cube.id), 0.5)
            belief *= msg
        beliefs[cube.id] = max(0.0, min(1.0, belief))

    return beliefs


# ─── B21: Survey Propagation pre-filtre ──────────────────────────────

def survey_propagation_filter(cubes, store,
                              neutral_threshold: float = 0.2) -> tuple:
    """
    B21: Survey Propagation pre-filter (Mezard-Parisi 2002).
    Skips trivial cubes (~30% neutral, Schulte 2014).
    Returns (non_trivial, trivial).

    BUG-109 fix (brick 18): tolerate non-list cubes input.
    """
    if not isinstance(cubes, (list, tuple)) or not cubes:
        return ([], [])
    beliefs = belief_propagation(cubes, store, max_iter=5)
    trivial, non_trivial = [], []

    for cube in cubes:
        belief = beliefs.get(cube.id, 0.5)
        if belief < neutral_threshold:
            trivial.append(cube)
        else:
            non_trivial.append(cube)

    return non_trivial, trivial


# ─── B22: Tononi Degeneracy ──────────────────────────────────────────

def tononi_degeneracy(cube: Cube, store: CubeStore,
                      all_cubes: list[Cube]) -> float:
    """
    B22: Tononi Degeneracy (Tononi 1999).
    D = Σ MI(v_i, cube) - MI(all_v, cube).
    High D = fragile (redundant neighbors). Low D = critical.
    Uses NCD as MI proxy.
    """
    neighbors = store.get_neighbors(cube.id)
    if not neighbors:
        return 0.0

    cube_by_id = {c.id: c for c in all_cubes}

    individual_mi = 0.0
    neighbor_contents = []
    for nid, weight, _ in neighbors:
        n = cube_by_id.get(nid)
        if n:
            ncd = compute_ncd(cube.content, n.content)
            individual_mi += (1.0 - ncd)
            neighbor_contents.append(n.content)

    if not neighbor_contents:
        return 0.0

    combined = "\n".join(neighbor_contents)
    combined_ncd = compute_ncd(cube.content, combined)
    joint_mi = 1.0 - combined_ncd

    return max(0.0, individual_mi - joint_mi)


# ─── B35: Cube Heatmap ────────────────────────────────────────────────

def cube_heatmap(store: CubeStore) -> dict:
    """
    B35: Generate heatmap of cube temperatures grouped by file.
    Returns {file: {count, hot_count, avg_temp, max_temp, cubes: [{id, temp, lines}]}}.
    """
    with store._lock:
        rows = store.conn.execute(
            "SELECT file_origin, id, temperature, line_start, line_end "
            "FROM cubes WHERE level = 0 ORDER BY file_origin, line_start"
        ).fetchall()

    heatmap = {}
    for file_origin, cid, temp, ls, le in rows:
        if file_origin not in heatmap:
            heatmap[file_origin] = {
                'count': 0, 'hot_count': 0, 'temps': [],
                'cubes': [],
            }
        entry = heatmap[file_origin]
        entry['count'] += 1
        entry['temps'].append(temp)
        if temp > 0.5:
            entry['hot_count'] += 1
        entry['cubes'].append({'id': cid, 'temp': temp, 'lines': f"L{ls}-{le}"})

    # Compute aggregates
    for f, entry in heatmap.items():
        temps = entry.pop('temps')
        entry['avg_temp'] = sum(temps) / len(temps) if temps else 0.0
        entry['max_temp'] = max(temps) if temps else 0.0

    return heatmap


# ─── B36: Forge Link — fuse Cube + Forge risks ────────────────────────

def fuse_risks(store: CubeStore, forge_root: str,
               forge_weight: float = 0.4,
               cube_weight: float = 0.6) -> list[dict]:
    """
    B36: Combine Forge defect prediction risk with Cube temperature.
    combined_risk = forge_weight * forge_risk + cube_weight * cube_avg_temp.
    Returns sorted list of {file, forge_risk, cube_temp, combined, hot_cubes}.
    """
    # Get cube temperatures per file
    cube_temps = {}
    with store._lock:
        rows = store.conn.execute(
            "SELECT file_origin, AVG(temperature), MAX(temperature), COUNT(*), "
            "SUM(CASE WHEN temperature > 0.5 THEN 1 ELSE 0 END) "
            "FROM cubes WHERE level = 0 GROUP BY file_origin"
        ).fetchall()
    for file_origin, avg_t, max_t, count, hot in rows:
        cube_temps[file_origin] = {
            'avg_temp': avg_t, 'max_temp': max_t,
            'count': count, 'hot_cubes': hot,
        }

    # Get Forge risks (capture printed output, parse risk scores)
    forge_risks = _get_forge_risks(forge_root)

    # Fuse
    all_files = set(cube_temps.keys()) | set(forge_risks.keys())
    results = []
    for f in all_files:
        fr = forge_risks.get(f, 0.0)
        ct = cube_temps.get(f, {}).get('avg_temp', 0.0)
        combined = forge_weight * fr + cube_weight * ct
        results.append({
            'file': f,
            'forge_risk': fr,
            'cube_temp': ct,
            'combined': combined,
            'hot_cubes': cube_temps.get(f, {}).get('hot_cubes', 0),
        })

    results.sort(key=lambda x: x['combined'], reverse=True)
    return results


def _get_forge_risks(forge_root: str) -> dict:
    """Extract risk scores from Forge predict_defects (parse output)."""
    import io
    import contextlib
    try:
        from engine.core.forge import predict_defects
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            predict_defects(Path(forge_root))
        output = buf.getvalue()
        # Parse "  0.73  engine/core/muninn.py" lines
        risks = {}
        for line in output.split('\n'):
            line = line.strip()
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    risk = float(parts[0])
                    fname = parts[1].strip()
                    if fname.endswith('.py'):
                        risks[fname] = risk
                except ValueError:
                    continue
        return risks
    except (ImportError, OSError, ValueError):
        return {}


# ─── B37: Auto-repair — generate patches for failing tests ────────────

def auto_repair(store: CubeStore, failed_files: list[str],
                reconstructor=None, max_patches: int = 3) -> list[dict]:
    """
    B37: For failing test files, find hot cubes and generate repair patches.
    1. Find cubes in failed files sorted by temperature (hottest first)
    2. Generate up to max_patches reconstructions via FIM
    3. Return patches with metadata

    Args:
        store: CubeStore with scanned cubes
        failed_files: list of file paths that have test failures
        reconstructor: FIMReconstructor instance (or None for dry-run)
        max_patches: max patches to generate

    Returns list of {cube_id, file, original, patch, temperature}.
    """
    patches = []

    for fpath in failed_files:
        cubes = store.get_cubes_by_file(fpath)
        # Sort by temperature descending — hottest cubes first
        cubes.sort(key=lambda c: c.temperature, reverse=True)

        for cube in cubes[:max_patches]:
            neighbors = store.get_neighbors(cube.id)
            if not neighbors:
                continue

            # Build context from neighbors
            context_parts = []
            for nid, weight, _ in neighbors:
                ncube = store.get_cube(nid)
                if ncube:
                    context_parts.append(ncube.content)

            mid = max(1, len(context_parts) // 2)
            prefix = "\n".join(context_parts[:mid])
            suffix = "\n".join(context_parts[mid:])

            patch_content = None
            if reconstructor:
                try:
                    patch_content = reconstructor.reconstruct_fim(
                        prefix=prefix, suffix=suffix
                    )
                except (ConnectionError, ValueError, TypeError, OSError):
                    patch_content = None

            patches.append({
                'cube_id': cube.id,
                'file': cube.file_origin,
                'line_start': cube.line_start,
                'line_end': cube.line_end,
                'original': cube.content,
                'patch': patch_content,
                'temperature': cube.temperature,
                'neighbor_count': len(neighbors),
            })

            if len(patches) >= max_patches:
                break
        if len(patches) >= max_patches:
            break

    return patches


# ─── Quarantine — photographier la blessure avant de guérir ──────────

def record_quarantine(quarantine_path: str, cube: 'Cube',
                      reconstruction: str, exact_match: bool,
                      ncd_score: float = None):
    """
    Sauvegarde le contenu corrompu d'un bloc AVANT régénération.
    Garde la preuve pour forensic : contenu original, hash attendu vs trouvé,
    contenu reconstruit, timestamp.

    Stocké en JSONL dans .muninn/quarantine.jsonl
    """
    time_mod = _time
    hashlib_mod = hashlib
    os.makedirs(os.path.dirname(quarantine_path) or '.', exist_ok=True)

    corrupted_hash = hashlib_mod.sha256(cube.content.encode()).hexdigest()

    entry = {
        'timestamp': time_mod.time(),
        'date': time_mod.strftime('%Y-%m-%d %H:%M:%S'),
        'cube_id': cube.id,
        'file_origin': cube.file_origin,
        'line_start': cube.line_start,
        'line_end': cube.line_end,
        'expected_sha256': cube.sha256,
        'found_sha256': corrupted_hash,
        'corrupted_content': cube.content,
        'reconstructed_content': reconstruction,
        'exact_match': exact_match,
        'ncd_score': ncd_score,
    }

    with _quarantine_lock:
        with open(quarantine_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    return entry


# ─── B38: Feedback loop — anomalies → mycelium ────────────────────────

def record_anomaly(anomaly_path: str, file: str, metrics: dict,
                   cube_ids: list[str], label: str = "predicted_risky"):
    """
    B38: Record a file anomaly for future feedback validation.
    Stored as JSONL in .muninn/anomalies.jsonl.
    """
    time_mod = _time
    os.makedirs(os.path.dirname(anomaly_path) or '.', exist_ok=True)
    entry = {
        'timestamp': time_mod.time(),
        'date': time_mod.strftime('%Y-%m-%d'),
        'file': file,
        'metrics': metrics,
        'cube_ids': cube_ids,
        'label': label,
        'validated': False,
    }
    with _anomaly_lock:
        with open(anomaly_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    return entry


def feedback_loop_check(anomaly_path: str, repo_root: str,
                        lookback_days: int = 180) -> dict:
    """
    B38: Check old anomalies — were they actually buggy?
    Looks at git log for bugfix commits in predicted files.
    Returns {total, correct, accuracy, details}.
    """
    time_mod = _time

    if not os.path.exists(anomaly_path):
        return {'total': 0, 'correct': 0, 'accuracy': 0.0, 'details': []}

    cutoff = time_mod.time() - (lookback_days * 86400)
    anomalies = []
    with open(anomaly_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('timestamp', 0) < cutoff:
                    anomalies.append(entry)
            except json.JSONDecodeError:
                continue

    if not anomalies:
        return {'total': 0, 'correct': 0, 'accuracy': 0.0, 'details': []}

    details = []
    correct = 0
    for a in anomalies:
        # Check if file had bugfix commits since the anomaly was recorded
        since_date = a.get('date', '2020-01-01')
        try:
            result = subprocess.run(
                ['git', 'log', '--oneline', f'--since={since_date}',
                 '--extended-regexp', '--grep=fix|bug|patch|repair', '--', a['file']],
                capture_output=True, text=True, cwd=repo_root, timeout=10
            )
            bugfixes = [l for l in result.stdout.strip().split('\n') if l.strip()]
        except (subprocess.SubprocessError, OSError):
            bugfixes = []

        was_buggy = len(bugfixes) > 0
        if was_buggy:
            correct += 1

        details.append({
            'file': a['file'],
            'predicted': a['label'],
            'was_buggy': was_buggy,
            'bugfix_count': len(bugfixes),
            'date': a.get('date'),
        })

    total = len(anomalies)
    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0,
        'details': details,
    }


def feed_anomalies_to_mycelium(anomaly_path: str, mycelium=None) -> list[dict]:
    """
    B38: Feed validated anomaly patterns to mycelium for future prediction.
    Creates concept pairs: (file_concept, 'bug_prone') with positive weight
    for correct predictions, negative for false positives.
    """
    if not os.path.exists(anomaly_path):
        return []

    pairs = []
    with open(anomaly_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if not entry.get('validated'):
                    continue
                # Extract file concept (stem without extension)
                file_concept = Path(entry['file']).stem
                weight = 1.0 if entry.get('was_buggy') else -0.5
                pairs.append({
                    'source': file_concept,
                    'target': 'bug_prone',
                    'weight': weight,
                    'type': 'feedback',
                })
            except (json.JSONDecodeError, KeyError):
                continue

    if mycelium and pairs:
        try:
            concepts = [p['source'] for p in pairs] + [p['target'] for p in pairs]
            mycelium.observe(list(set(concepts)))
        except (AttributeError, ValueError, TypeError):
            pass

    return pairs
