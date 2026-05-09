"""Compatibility shim — source of truth: engine/core/cube.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file was a byte-identical
copy (1558L, md5 confirmed) of engine/core/cube.py. Replacing it with a
shim removes drift risk on the cube core (scan/subdivide/store).

cube.py itself re-exports cube_providers and cube_analysis at its tail
(`from cube_providers import *`, `from cube_analysis import *`), so this
shim transitively re-exports ~65 public symbols + 2 private helpers
used by 14 test files (`from muninn.cube import …`).

The `sys.modules.setdefault('cube', …)` trick at the bottom of the
canonical file handles the cube/cube_providers/cube_analysis circular
import — preserved here transitively via `from cube import *`.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from cube import *  # noqa: F401,F403

# Explicit re-export for the union of names test files import directly.
# Includes private names (_get_forge_risks, _extract_concepts) that
# `from cube import *` skips. 65 symbols total.
from cube import (  # noqa: F401
    # Constants
    BINARY_EXTENSIONS, SKIP_DIRS, LANG_MAP, MAX_FILE_SIZE,
    TARGET_TOKENS, TOLERANCE_MIN, TOLERANCE_MAX, MAX_NEIGHBORS,
    CUBE_DB_SCHEMA,
    # Dataclasses + storage
    ScannedFile, Cube, CubeStore, Dependency, GodsNumberResult,
    ReconstructionResult, CubeConfig, CubeScheduler,
    # LLM providers
    LLMProvider, OllamaProvider, ClaudeProvider, OpenAIProvider,
    MockLLMProvider, FIMReconstructor,
    # Scan + subdivide + hash
    scan_repo, normalize_content, format_code, sha256_hash,
    subdivide_file, subdivide_recursive,
    check_formatters, install_formatters,
    # Reconstruction
    reconstruct_cube, validate_reconstruction, compute_hotness,
    compute_ncd, extract_all_ast_hints,
    # Dependencies + neighbors
    parse_dependencies, build_neighbor_graph, build_adjacency_matrix,
    assign_neighbors,
    # Temperature + hebbian + analysis
    compute_temperature, update_all_temperatures, hebbian_update,
    # Cube cycle
    prepare_cubes, run_destruction_cycle, post_cycle_analysis,
    record_anomaly, feedback_loop_check, feed_anomalies_to_mycelium,
    feed_mycelium_from_results,
    # Forensic analysis (B9-B38, dormant in prod CLI but tested)
    laplacian_rg_grouping, cheeger_constant, belief_propagation,
    survey_propagation_filter, tononi_degeneracy,
    compute_gods_number, build_level_cubes, propagate_levels,
    aggregate_scores, kaplan_meier_survival,
    # Risk fusion (forge integration)
    cube_heatmap, fuse_risks, auto_repair,
    detect_dead_code, filter_dead_cubes,
    git_blame_cube, git_log_value,
    # CLI helpers (test-only, not wired to muninn CLI)
    cli_run, cli_scan, cli_god, cli_status,
    # Private (used by tests directly)
    _get_forge_risks, _extract_concepts,
)
