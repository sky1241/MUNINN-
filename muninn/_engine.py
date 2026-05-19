"""Compatibility shim — source of truth: engine/core/muninn.py.

Part of the BUG-091 closeout: this file used to be a 1801-line mirror of
engine/core/muninn.py (drifted on 2026-05-18 with CHUNK 10 work that
re-duplicated the SCAN_NOISE_EXTENSIONS / iter_scannable_files block).
Replaced 2026-05-19 with a shim — same pattern as muninn/cube.py and
the 23 other muninn/<X>.py shims.

CLI entry point preserved: `muninn-mem = muninn._engine:main`
(pyproject.toml console_scripts). The canonical `main()` is re-exported
below so the entry point keeps working.

Implementation note: the canonical file is named `muninn.py` (same name
as the package we're currently initializing). A naive `from muninn import *`
would resolve to the partially-loaded package, not the canonical file.
We therefore load it explicitly via importlib.spec_from_file_location
under a unique private name.
"""
import importlib.util
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
_canonical_path = _engine_core / "muninn.py"

# engine/core/ must be on sys.path because the canonical module uses bare
# imports (`from tokenizer import ...`, `from _secrets import ...`).
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

_spec = importlib.util.spec_from_file_location(
    "_muninn_engine_canonical", _canonical_path,
)
_canonical = importlib.util.module_from_spec(_spec)
sys.modules["_muninn_engine_canonical"] = _canonical
_spec.loader.exec_module(_canonical)

# Re-export EVERY attribute (public + private) because muninn/__init__.py
# wraps the package in a _ProxyModule that forwards all getattr/setattr
# to muninn._engine — including private helpers like `_safe_path`,
# `_redact_secrets_text`, etc. Dunder attrs (`__name__`, `__file__`...)
# stay on the shim itself.
for _attr in dir(_canonical):
    if not (_attr.startswith("__") and _attr.endswith("__")):
        globals()[_attr] = getattr(_canonical, _attr)

# CLI entry point (referenced by pyproject.toml console_scripts).
main = _canonical.main


# Support `python -m muninn._engine <args>` (used by some tests + dev workflows).
# The canonical wraps `main` in `_friendly_run` (G.3 friendly errors —
# suppresses traceback on user-facing exceptions like FileNotFoundError).
# We mirror that pattern here, otherwise raw tracebacks leak.
if __name__ == "__main__":
    _canonical._friendly_run(_canonical.main)
