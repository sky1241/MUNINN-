"""Compatibility shim — source of truth: engine/core/muninn_secrets.py.

Re-exports the scrub/purge CLI functions extracted in chunk C.1 split
(2026-05-11 nuit). Renamed from the obvious `_secrets.py` because
`muninn/_secrets.py` already exists as the shim for `engine/core/_secrets.py`
(the secret-redaction patterns). This file is the *CLI layer* on top of it.

Mirror obligatoire BUG-091 (engine/core/ ↔ muninn/ duplicated tree).
"""
from __future__ import annotations
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from muninn_secrets import *  # noqa: F401,F403
from muninn_secrets import (  # noqa: F401 — explicit re-export of privates
    _SCRUB_EXTENSIONS,
    _TRIGGER_VALUE_PATTERNS,
    _handle_scrub_command,
    _handle_purge_secrets_command,
)
