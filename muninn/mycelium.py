"""Compatibility shim — source of truth: engine/core/mycelium.py.

Part of BUG-091 resync (2026-05-07): the canonical version has fixes
that were missing from this copy:
  - _session_lock = threading.Lock() protecting _session_seen across
    threads (this copy lost the lock entirely)
  - unicodedata.normalize("NFC", ...) on observed concepts so non-Latin
    characters get canonical normalization (this copy did .lower().strip()
    only, leading to duplicate concepts)
  - corrupt DB recovery uses .rename(.db.corrupt) so a forensic copy
    survives (this copy did .unlink() = destroy the corrupt file)
Re-exporting from engine/core/ brings them all back.
See docs/BATTLE_PLAN_BUG091_2026-05-07.md.
"""
import sys
from pathlib import Path

_engine_core = str(Path(__file__).resolve().parent.parent / "engine" / "core")

# CRIT-1 fix (2026-05-10): the shim was loaded under the bare name "mycelium"
# (e.g. `from mycelium import Mycelium` — bare absolute, with muninn/ in
# sys.path[0] from _engine.py:80). Python registered us in sys.modules
# ['mycelium'] BEFORE executing this body. Without intervention, the next
# `from mycelium import *` re-finds OURSELF via sys.modules → ImportError
# "partially initialized" or RecursionError.
# TWO actions needed:
#   1. Pop ourselves from sys.modules['mycelium'] so the next import re-scans.
#   2. Force engine/core to sys.path[0] (remove+insert, not naive `if not in`),
#      because muninn/ is also in sys.path[0] and otherwise wins the lookup.
# After the canonical loads, we leave sys.modules['mycelium'] pointing at it.
# `sys.modules['muninn.mycelium']` still points here so explicit
# `from muninn.mycelium import X` keeps working through the re-exports below.
if _engine_core in sys.path:
    sys.path.remove(_engine_core)
sys.path.insert(0, _engine_core)
sys.modules.pop('mycelium', None)

from mycelium import *  # noqa: F401,F403
from mycelium import (  # explicit re-export
    Mycelium,
    main,
    # Re-exported by engine/core/mycelium.py from mycelium_db (consumed
    # by tests/test_decay_in_prune.py via `from muninn.mycelium import today_days`):
    today_days,
    days_to_date,
    date_to_days,
    MyceliumDB,
)
