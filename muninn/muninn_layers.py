"""Compatibility shim — source of truth: engine/core/muninn_layers.py.

Part of BUG-091 resync (2026-05-07): minor drift (mostly shorter
docstrings on muninn side, no real logic difference). Re-exporting from
engine/core/ to stop drift accumulation. See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from muninn_layers import *  # noqa: F401,F403
from muninn_layers import (  # explicit re-export
    load_codebook,
    get_codebook,
    compress_line,
    extract_facts,
    tag_memory_type,
    compress_section,
    compress_file,
    decode_line,
    verify_compression,
)
