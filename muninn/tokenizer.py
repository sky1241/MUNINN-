"""Compatibility shim — source of truth: engine/core/tokenizer.py.

Part of BUG-091 resync (2026-05-07): the canonical version has a
`_tok_lock = threading.Lock()` + double-check pattern (M1 fix) that was
missing from this copy. Re-exporting from engine/core/ removes the race
condition where two threads could both call tiktoken.get_encoding()
concurrently. See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from tokenizer import *  # noqa: F401,F403
from tokenizer import (  # explicit re-export
    count_tokens,
    token_count,
)
