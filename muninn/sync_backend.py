"""Compatibility shim — source of truth: engine/core/sync_backend.py.

Part of BUG-091 resync (2026-05-07): the canonical version has manual
`db._lock.acquire()` + `_lock.release()` around the sync push (H1 fix)
that was missing from this copy. Re-exporting from engine/core/ removes
the data corruption risk on concurrent sync_push() calls.

The canonical also has the P2 fix: `check_disk_space` returns False on
probe failure (was True = "assume OK", now refuses).
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from sync_backend import *  # noqa: F401,F403
from sync_backend import (  # explicit re-export
    check_disk_space,
    SyncEdge,
    SyncFusion,
    SyncPayload,
    SyncBackend,
    SharedFileBackend,
    get_sync_backend,
    GitBackend,
    save_sync_config,
    sync_metrics,
    migrate_backend,
    verify_hooks,
    sync_doctor,
    export_meta_json,
    import_meta_json,
    _load_sync_config,  # used by tests/test_phase1_sync.py
)
