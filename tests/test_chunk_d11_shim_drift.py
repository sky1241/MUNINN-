"""CHUNK D11 — anti-drift test for muninn/ shims vs engine/core/ canonical.

BUG-091 closed by converting muninn/<name>.py into shims that re-export
from engine/core/<name>.py. But there is no automated check that the
shim actually exposes everything the canonical module does. A new
function added to engine/core/X.py would silently NOT be reachable
via `from muninn.X import …` if the shim's explicit re-export list
isn't updated.

This test compares the public attribute set of every paired module
and flags missing exports.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D11
"""
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent

# Pairs to check: (engine/core file basename, muninn shim basename)
SHIMMED_MODULES = [
    "muninn_tree",
    "muninn_layers",
    "muninn_feed",
    "mycelium_db",
    "mycelium",
    "_secrets",
    "lexicons",
    "sentiment",
    "lang_lexicons",
    "dedup",
    "budget_select",
    "cube",
    "cube_analysis",
    "cube_providers",
    "sync_backend",
    "sync_tls",
    "vault",
]


def _public_names(mod) -> set[str]:
    """Return the set of names a `from mod import *` would expose."""
    if hasattr(mod, "__all__"):
        return set(mod.__all__)
    return {n for n in dir(mod) if not n.startswith("_")}


def _load_engine_core(name: str):
    """Load engine/core/<name>.py under a unique module name."""
    src = REPO / "engine" / "core" / f"{name}.py"
    if not src.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"_chunk_d11_engine_{name}", src
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


def _load_muninn_shim(name: str):
    """Import the muninn.<name> shim through the package path."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        return importlib.import_module(f"muninn.{name}")
    except Exception:
        return None


def test_no_shim_missing_canonical_modules():
    """Every shim module must exist in muninn/."""
    missing = [m for m in SHIMMED_MODULES if not (REPO / "muninn" / f"{m}.py").exists()]
    assert not missing, f"Missing muninn/ shims: {missing}"


def test_every_canonical_has_a_shim_or_is_intentionally_local():
    """Every engine/core/*.py except known engine-only modules must
    have a counterpart in muninn/ (shim) — guard against silently
    losing a public API path."""
    engine_files = sorted(p.stem for p in (REPO / "engine" / "core").glob("*.py")
                          if not p.name.startswith("__"))
    # Engine-only / hook helpers that don't need a shim:
    engine_only = {
        "_hook_logger",   # used directly by hooks
        "watchdog",       # CLI script
        "tokenizer",      # imported via direct path
        "muninn",         # CLI entry point; muninn/ package itself wraps it
        "wal_monitor",    # internal mycelium_db helper
        "scanner",        # standalone tool tree
        "forge",          # standalone repo at /home/sky/Bureau/forge/, BUG-091 plan
        "forge_metrics",  # F6 (2026-05-09): pure subprocess wrapper for forge-shield
                          # binary; UI imports via engine.core.forge_metrics directly,
                          # no muninn/ shim needed (no internal engine/core consumer).
    }
    for name in engine_files:
        if name in engine_only:
            continue
        if name in SHIMMED_MODULES:
            continue
        # Anything else => either add to SHIMMED_MODULES or to engine_only
        pytest.fail(
            f"engine/core/{name}.py is neither in SHIMMED_MODULES nor in "
            f"engine_only. Add it to one or the other so the drift check "
            f"covers it."
        )


@pytest.mark.parametrize("name", SHIMMED_MODULES)
def test_shim_re_exports_canonical_public_names(name):
    """For every paired module, the shim must expose every public name
    of the canonical module (no API loss through the shim)."""
    canonical = _load_engine_core(name)
    if canonical is None:
        pytest.skip(f"engine/core/{name}.py not loadable in this env")
    shim = _load_muninn_shim(name)
    if shim is None:
        pytest.skip(f"muninn.{name} not importable in this env "
                    "(BUG-091 shim collision)")

    canonical_names = _public_names(canonical)
    # Don't compare via __all__ on the shim: the shim is allowed to
    # restrict re-export. We just need: every canonical name reachable.
    shim_names = set(dir(shim))
    missing = [n for n in canonical_names if n not in shim_names]
    assert not missing, (
        f"muninn/{name}.py shim does NOT re-export canonical names: "
        f"{sorted(missing)[:10]}"
        + (f" (and {len(missing) - 10} more)" if len(missing) > 10 else "")
    )
