"""Compatibility shim — source of truth: engine/core/wal_monitor.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file had a cosmetic
drift (unused `field` import + CRLF line endings) on 109 LOC. Replacing
with a 20-line shim seals the BUG-091 surface for this module.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from wal_monitor import *  # noqa: F401,F403
from wal_monitor import (  # explicit re-export
    WALConfig,
    WALMonitor,
)
