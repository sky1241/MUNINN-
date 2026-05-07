"""Compatibility shim — source of truth: engine/core/sync_tls.py.

Part of BUG-091 resync (2026-05-07): the canonical version has the
CHUNK 8 fix (pull fusions from TLS server) that was missing from this
copy. Re-exporting from engine/core/ brings back full fusion sync.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from sync_tls import *  # noqa: F401,F403
from sync_tls import (  # explicit re-export
    generate_certs,
    RateLimiter,
    SyncServer,
    SyncClient,
    TLSBackend,
    serve_cli,
)
