"""Compatibility shim — source of truth: engine/core/dedup.py.

Part of BUG-091 resync (2026-05-07): drift was line-endings only
(CRLF on muninn side vs LF on engine/core side), zero logic difference.
Re-exporting from engine/core/ to converge.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from dedup import *  # noqa: F401,F403
from dedup import (  # explicit re-export
    simhash,
    hamming_distance,
    similar,
    dedup_lines,
    dedup_paragraphs,
    stats,
)
