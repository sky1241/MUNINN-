"""Compatibility shim — source of truth: engine/core/sentiment.py.

Part of BUG-091 resync (2026-05-07): this file was a near-identical
copy of engine/core/sentiment.py with imports tweaked for the muninn
package layout. To stop drift, it now re-exports everything from the
canonical engine/core/ version. See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from sentiment import *  # noqa: F401,F403
from sentiment import (  # explicit re-export so static analysis sees them
    score_sentiment,
    score_session,
    circumplex_map,
    _get_analyzer,
)
