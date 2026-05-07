"""Compatibility shim — source of truth: engine/core/muninn_tree.py.

Part of BUG-091 resync (2026-05-07): the canonical version has 8 fixes
that were missing or regressed in this copy:
  1. adaptive_boot_budget try/except on ValueError/TypeError around
     int(MUNINN_CONTEXT_SIZE)
  2. _tree_lock writes "L" byte before lock attempt (Windows file
     locking via msvcrt.locking)
  3. _tree_lock exception cleanup (close lock_f if acquire fails)
  4. load_tree/save_tree honor `acquired` flag (warn on lock timeout)
  5. _days_since uses datetime.now(timezone.utc) (timezone-stable
     Ebbinghaus decay)
  6. _atomic_json_write retries 3x on PermissionError (Windows
     transient lock robustness)
  7. os.path.normcase on path validation (case-insensitive on Windows
     for path traversal defense)
  8. _atomic_text_write function (atomic tempfile + os.replace pattern
     used by 10+ call sites)

Re-exporting from engine/core/ brings them all back.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

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
    # Private functions referenced by some tests via `from muninn_tree import _X`
    _ebbinghaus_recall,
    _actr_activation,
    _atomic_text_write,
    _days_since,
)
