"""Compatibility shim — source of truth: engine/core/_secrets.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file was a byte-identical
copy of engine/core/_secrets.py (md5 confirmed) which is a recipe for
silent drift the next time someone edits one side without the other.

8 sites in engine/core/ + muninn/ consume `from _secrets import …` (or
`from muninn._secrets import …` from `muninn/vault.py`) — the shim
preserves all of them by re-exporting the public + private names that
external callers reach for explicitly.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from _secrets import *  # noqa: F401,F403
from _secrets import (  # explicit re-export (private names not picked by *)
    _SECRET_PATTERNS,
    _COMPILED_PATTERNS,
    _STRONG_SHELL_SEP,
    redact_secrets_text,
    count_chained_commands,
    clamp_chained_commands,
    secure_perms,
    MAX_CHAINED_COMMANDS,
)
