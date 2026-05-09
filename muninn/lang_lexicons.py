"""Compatibility shim — source of truth: engine/core/lang_lexicons.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file was a byte-identical
copy of engine/core/lang_lexicons.py (1007L, md5 confirmed) — replacing
it with a 20-line shim removes the bomb-à-retardement of "modify one
side, forget to mirror".

Consumers all use bare `from lang_lexicons import …` (cube.py, cube_providers.py
on both engine and muninn sides) — they resolve via sys.path injection,
so the shim is transparent.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from lang_lexicons import *  # noqa: F401,F403
from lang_lexicons import (  # explicit re-export of public API
    LEXICONS,
    get_lexicon,
    format_lexicon_prompt,
    TOTAL_LANGUAGES,
    TOTAL_RULES,
)
