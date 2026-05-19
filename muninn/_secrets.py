"""Shim of engine/core/_secrets.py (BUG-091 B1, 2026-05-09). Re-exports
public + private names (8 consumer sites: engine/core/ + muninn/).
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
