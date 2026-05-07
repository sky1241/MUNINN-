"""Compatibility shim — source of truth: engine/core/cube_analysis.py.

Part of BUG-091 resync (2026-05-07): the canonical version has fixes
that were missing from this copy:
  - C1: feed mechanical weight (success/failure) to mycelium via direct
    upsert instead of just observe_text() (preserves the +1.0/-0.5 signal)
  - C4: real FIMReconstructor passed to auto_repair() when provider
    available (this copy always passed reconstructor=None)
  - C6: feed_anomalies_to_mycelium() called from post_cycle_analysis()
    when mycelium provided (close the loop on validated anomalies)
  - post_cycle_analysis() signature: this copy lost the `provider` and
    `mycelium` parameters that drive the C4/C6 fixes
Re-exporting from engine/core/ brings them all back.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from cube_analysis import *  # noqa: F401,F403
from cube_analysis import (  # explicit re-export
    run_destruction_cycle,
    post_cycle_analysis,
    compute_temperature,
    update_all_temperatures,
    kaplan_meier_survival,
    detect_dead_code,
    filter_dead_cubes,
    prepare_cubes,
    GodsNumberResult,
    compute_gods_number,
    build_level_cubes,
    aggregate_scores,
    propagate_levels,
    feed_mycelium_from_results,
    hebbian_update,
    git_blame_cube,
    git_log_value,
    CubeScheduler,
    CubeConfig,
    cli_scan,
    cli_run,
    cli_status,
    cli_god,
    build_adjacency_matrix,
    laplacian_rg_grouping,
    cheeger_constant,
    belief_propagation,
    survey_propagation_filter,
    tononi_degeneracy,
    cube_heatmap,
    fuse_risks,
    auto_repair,
    record_quarantine,
    record_anomaly,
    feedback_loop_check,
    feed_anomalies_to_mycelium,
)
