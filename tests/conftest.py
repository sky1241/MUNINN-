"""Conftest — ensure muninn package is loaded before any test collection."""
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so `import muninn` finds the package
_REPO = str(Path(__file__).resolve().parent.parent)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Pre-import the package so engine/core/muninn.py can never shadow it
import muninn  # noqa: E402,F401


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
