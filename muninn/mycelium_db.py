"""Compatibility shim — source of truth: engine/core/mycelium_db.py.

Part of BUG-091 resync (2026-05-07): the canonical version uses
threading.RLock() (re-entrant) where this copy used threading.Lock()
which would deadlock on the chain
  observe() -> transaction() -> _get_or_create_concept().
Also has try/except in _Transaction.__enter__ that releases the lock
on entry failure (this copy left it locked forever).
Re-exporting from engine/core/ removes both deadlock risks.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from mycelium_db import *  # noqa: F401,F403
from mycelium_db import (  # explicit re-export
    date_to_days,
    days_to_date,
    today_days,
    MyceliumDB,
    ConceptTranslator,
)
