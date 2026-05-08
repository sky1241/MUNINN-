"""Conftest — ensure muninn package is loaded before any test collection.

CHUNK F4 (2026-05-08): pre-load engine/core canonical modules under
their bare names so tests using `import mycelium`, `import cube_providers`
etc. always hit the same module object that `muninn/<X>.py` shims will
re-export. This eliminates the BUG-091 "shim circular import" skips
that were occurring whenever a test using `importlib.spec_from_file_location`
ran AFTER another test that had already registered the bare name in
sys.modules.

Critical detail: we DON'T put engine/core on sys.path (that would shadow
the muninn/ package by `import muninn`). Instead we use
importlib.util.spec_from_file_location and explicitly register the
loaded module in sys.modules under its bare name. This decouples the
bare-name registration from sys.path resolution.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `import muninn` finds the PACKAGE
# (muninn/__init__.py), not the engine/core/muninn.py CLI module.
_REPO = Path(__file__).resolve().parent.parent
_REPO_STR = str(_REPO)
if _REPO_STR not in sys.path:
    sys.path.insert(0, _REPO_STR)

# Pre-import the package so engine/core/muninn.py can never shadow it
import muninn  # noqa: E402,F401

# CHUNK F4: pre-load canonical engine/core modules under their bare
# names without touching sys.path. Each module is registered in
# sys.modules BEFORE exec to handle circular imports gracefully.
_ENGINE_CORE_DIR = _REPO / "engine" / "core"


def _preload_bare(name: str) -> None:
    """Register engine/core/<name>.py in sys.modules under bare `name`."""
    if name in sys.modules:
        return  # Already loaded by a previous import; respect that.
    src = _ENGINE_CORE_DIR / f"{name}.py"
    if not src.exists():
        return
    spec = importlib.util.spec_from_file_location(name, src)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # MUST be set before exec for cyclic imports
    try:
        spec.loader.exec_module(mod)
    except Exception:
        # Failure: remove the half-loaded module so a future test can
        # try again cleanly.
        sys.modules.pop(name, None)


# Order matters: dependencies before consumers.
_PRELOAD_ORDER = [
    "tokenizer",
    "_secrets",
    "_hook_logger",
    "wal_monitor",
    "lexicons",
    "lang_lexicons",
    "sentiment",
    "dedup",
    "budget_select",
    "mycelium_db",
    "mycelium",
    "cube",
    "cube_analysis",
    "cube_providers",
    "sync_tls",
    "sync_backend",
    "muninn_layers",
    "muninn_feed",
    "muninn_tree",
]
for _mod_name in _PRELOAD_ORDER:
    _preload_bare(_mod_name)


# CHUNK B7 (2026-05-08): autouse fixture to prevent _REPO_PATH leakage
# across tests. Pre-fix, a test that crashed before restoring its own
# muninn._REPO_PATH would silently pollute the next test (and pytest -n
# made it order-dependent across workers). The fixture snapshots both
# muninn._REPO_PATH and the dependent TREE_DIR / TREE_META resolved by
# _refresh_tree_paths(), restoring them after every test.
@pytest.fixture(autouse=True)
def _repo_path_isolate():
    orig_repo = getattr(muninn, "_REPO_PATH", None)
    orig_tree_dir = getattr(muninn, "TREE_DIR", None)
    orig_tree_meta = getattr(muninn, "TREE_META", None)
    try:
        yield
    finally:
        muninn._REPO_PATH = orig_repo
        if orig_tree_dir is not None:
            muninn.TREE_DIR = orig_tree_dir
        if orig_tree_meta is not None:
            muninn.TREE_META = orig_tree_meta
        # Best-effort: refresh dependent globals if helper exists
        if hasattr(muninn, "_refresh_tree_paths"):
            try:
                muninn._refresh_tree_paths()
            except Exception:
                pass
