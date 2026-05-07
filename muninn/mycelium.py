"""Compatibility shim — source of truth: engine/core/mycelium.py.

Part of BUG-091 resync (2026-05-07): the canonical version has fixes
that were missing from this copy:
  - _session_lock = threading.Lock() protecting _session_seen across
    threads (this copy lost the lock entirely)
  - unicodedata.normalize("NFC", ...) on observed concepts so non-Latin
    characters get canonical normalization (this copy did .lower().strip()
    only, leading to duplicate concepts)
  - corrupt DB recovery uses .rename(.db.corrupt) so a forensic copy
    survives (this copy did .unlink() = destroy the corrupt file)
Re-exporting from engine/core/ brings them all back.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from mycelium import *  # noqa: F401,F403
from mycelium import (  # explicit re-export
    Mycelium,
    main,
    # Re-exported by engine/core/mycelium.py from mycelium_db (consumed
    # by tests/test_decay_in_prune.py via `from muninn.mycelium import today_days`):
    today_days,
    days_to_date,
    date_to_days,
    MyceliumDB,
)
