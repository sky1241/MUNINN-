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

_engine_core = str(Path(__file__).resolve().parent.parent / "engine" / "core")

# CRIT-1 fix (2026-05-10): same circular-import dance as muninn/mycelium.py.
# When Python loads us under the bare name "sync_backend" (because muninn/ is
# in sys.path[0]), it registers us in sys.modules['sync_backend'] BEFORE
# executing this body. The bare `from sync_backend import *` below would then
# find us (partially initialized) instead of engine/core/sync_backend.py.
# TWO actions: (1) force engine/core to sys.path[0] via remove+insert (not
# naive `if not in`), (2) pop ourselves from sys.modules so the next import
# re-scans. After canonical loads, sys.modules['sync_backend'] = canonical;
# `from muninn.sync_backend import X` still works via the explicit re-exports
# below (sys.modules['muninn.sync_backend'] is untouched).
if _engine_core in sys.path:
    sys.path.remove(_engine_core)
sys.path.insert(0, _engine_core)
sys.modules.pop('sync_backend', None)

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
