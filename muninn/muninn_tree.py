"""Shim of engine/core/muninn_tree.py (BUG-091, 2026-05-07). Canonical
has 8 fixes (adaptive_boot, Windows locking, atomic writes, Ebbinghaus
timezone) — re-exporting brings them all back.
"""
import sys
from pathlib import Path

_engine_core = str(Path(__file__).resolve().parent.parent / "engine" / "core")

# CRIT-1 fix (2026-05-10): the shim may be loaded under the bare name
# "muninn_tree" via sys.path injection — Python registers us in
# sys.modules BEFORE executing this body, so `from muninn_tree import *`
# re-finds OURSELF (RecursionError). Pop self + force engine/core to [0].
if _engine_core in sys.path:
    sys.path.remove(_engine_core)
sys.path.insert(0, _engine_core)
sys.modules.pop('muninn_tree', None)

from muninn_tree import *  # noqa: F401,F403
from muninn_tree import __all__  # propagate __all__ so `from .muninn_tree import *` in muninn/_engine.py picks up privates listed there (e.g. _surface_insights_for_boot)
from muninn_tree import (  # explicit re-export — public API
    adaptive_boot_budget,
    cleanup_legacy_tree,
    cleanup_tmp_files,
    init_tree,
    load_tree,
    save_tree,
    compute_hash,
    compute_temperature,
    refresh_tree_metadata,
    read_node,
    build_tree,
    grow_branches_from_session,
    extract_tags,
    boot,
    recall,
    bridge,
    bridge_fast,
    predict_next,
    detect_session_mode,
    adapt_k,
    classify_session,
    huginn_think,
    prune,
    show_status,
    doctor,
    diagnose,
    inject_memory,
    spill_chunks_to_tree,  # BUG-104 fix 2026-05-10
    # Private functions referenced by some tests via `from muninn_tree import _X`
    _ebbinghaus_recall,
    _actr_activation,
    _atomic_text_write,
    _days_since,
)
