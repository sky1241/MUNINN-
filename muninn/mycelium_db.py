"""Shim of engine/core/mycelium_db.py (BUG-091, 2026-05-07). Canonical
uses RLock (re-entrant) — this copy used Lock which deadlocked the
observe → transaction → _get_or_create_concept chain. Also has
exception-safe lock release in _Transaction.__enter__.
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
