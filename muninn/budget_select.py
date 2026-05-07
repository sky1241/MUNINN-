"""Compatibility shim — source of truth: engine/core/budget_select.py.

Part of BUG-091 resync (2026-05-07): drift was mostly line-endings +
shorter docstrings, zero logic difference. Re-exporting from
engine/core/ to converge.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from budget_select import *  # noqa: F401,F403
from budget_select import (  # explicit re-export
    has_fact_span,
    compute_idf,
    score_chunk,
    select_chunks,
    budget_select,
    stats,
)
