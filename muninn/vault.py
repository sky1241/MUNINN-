"""Shim of engine/core/vault.py (BUG-091 B1, 2026-05-09). Canonical has
3 logic fixes the muninn/ copy was missing: 128-bit verify (was 64),
bytearray+wipe RAM after decrypt, audit log on partial failure. Bare
`from vault import …` already resolved to canonical via sys.path — this
shim closes the BUG-091 surface with zero prod behavior change. Old
passwords using the 64-bit verify need `vault rekey`.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from vault import *  # noqa: F401,F403
from vault import (  # explicit re-export (private + module constants)
    _SALT_FILE,
    _LOCK_EXT,
    _PBKDF2_ITERATIONS,
    _SENSITIVE_PATTERNS,
    _derive_key,
    _encrypt_bytes,
    _decrypt_bytes,
    _zero_bytes,
    _secure_delete,
    _audit_log,
    Vault,
)
