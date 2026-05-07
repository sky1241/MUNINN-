"""Compatibility shim — source of truth: engine/core/muninn_feed.py.

Part of BUG-091 resync (2026-05-07): the canonical version has fixes
that were missing from this copy:
  - m.close() in feed_from_transcript (prevents SQLite connection leak)
  - atomic write with tempfile + os.replace in compress_transcript
    (prevents corruption on crash)
  - try/except around old_file.unlink() (graceful on locked files)
Re-exporting from engine/core/ brings them all back.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from muninn_feed import *  # noqa: F401,F403
from muninn_feed import (  # explicit re-export — public API
    parse_transcript,
    feed_from_transcript,
    compress_transcript,
    feed_from_hook,
    feed_from_stop_hook,
    feed_history,
    feed_watch,
    ingest,
    _hook_log,
    _log_sync_error,
)
