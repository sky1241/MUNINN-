"""Compatibility shim — source of truth: engine/core/vault.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file diverged in LOGIC
from engine/core/vault.py — engine canonical had 3 fixes that muninn/
copy was missing (audit found this on 2026-05-09):

  1. `verify = sha256(self._key)[:32]` (engine, 128-bit verify)
     muninn was `[:16]` (64-bit, weaker)
  2. H1 fix: `bytearray(fp.read_bytes())` so `_zero_bytes()` can wipe RAM
     after decrypt (mutable). muninn passed bytes (immutable, can't wipe).
  3. `failed_files = []` accumulator + audit log entry on partial failure.
     muninn returned silent {decrypted, total_bytes} only.

In practice muninn/vault.py was DEAD code: every consumer (muninn.py
line 1565, _engine.py line 1603, tests/test_vault.py, tests/muninn_test_intelligence.py)
imports via the bare `from vault import …` form which resolves to
engine/core/vault.py through sys.path injection. Replacing the muninn/
copy with a shim is therefore zero-impact prod (no behavioral change)
+ closes the BUG-091 surface.

If anyone ever did initialize a vault via `from muninn.vault import Vault`
(unlikely per the grep), the verify-hash upgrade 64→128 bits will refuse
to unlock with the old password — `vault rekey` solves that.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
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
