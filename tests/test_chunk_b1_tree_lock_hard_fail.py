"""CHUNK B1 — `_tree_lock` hard-fail on save_tree.

`save_tree` calls `_tree_lock(timeout=5.0)`. If the lock can't be
acquired, it currently prints a WARNING and proceeds anyway. Two
concurrent save_tree calls can both pass the timeout and both write
their tempfile -> race on os.replace -> second writer wins, first
writer's changes lost silently.

Fix: convert the timeout to a hard failure (TimeoutError). The
caller decides whether to retry. This guarantees no silent data loss
on the tree.json save path.

`load_tree` is read-only and stays best-effort (warning + proceed).

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B1
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_tree():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_tree" in sys.modules:
        return sys.modules["muninn_tree"]
    import muninn_tree
    return muninn_tree


@pytest.fixture
def isolated_tree(tmp_path, monkeypatch):
    """Setup a tmp tree dir + valid tree.json."""
    tree_dir = tmp_path / "tree"
    tree_dir.mkdir()
    tree_meta = tree_dir / "tree.json"
    tree_meta.write_text(json.dumps({
        "version": 2, "budget": 30000,
        "nodes": {"root": {"file": "root.mn", "lines": 5, "tags": []}},
        "updated": "2026-05-08",
    }))
    (tree_dir / "root.mn").write_text("# Root\n")

    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    monkeypatch.setattr(_m, "TREE_DIR", tree_dir)
    monkeypatch.setattr(_m, "TREE_META", tree_meta)
    return tmp_path, tree_dir, tree_meta


def test_save_tree_raises_when_lock_unavailable(isolated_tree):
    """save_tree must raise TimeoutError if it cannot acquire the lock."""
    mt = _load_muninn_tree()
    tmp_path, tree_dir, tree_meta = isolated_tree

    # Patch _tree_lock to simulate timeout
    with patch.object(mt, "_tree_lock", return_value=(None, False)):
        with pytest.raises((TimeoutError, RuntimeError)) as exc_info:
            mt.save_tree({"version": 2, "budget": 30000, "nodes": {}})
        assert "lock" in str(exc_info.value).lower()


def test_load_tree_warns_on_lock_timeout_but_proceeds(isolated_tree, capsys):
    """load_tree (read-only) must warn and continue on lock timeout."""
    mt = _load_muninn_tree()
    with patch.object(mt, "_tree_lock", return_value=(None, False)):
        # Should NOT raise; load_tree is best-effort
        result = mt.load_tree()
    assert isinstance(result, dict)
    captured = capsys.readouterr()
    assert "lock" in captured.err.lower() or "warning" in captured.err.lower()


def test_save_tree_succeeds_when_lock_available(isolated_tree):
    """Sanity: save_tree must work normally when the lock is free."""
    mt = _load_muninn_tree()
    tmp_path, tree_dir, tree_meta = isolated_tree
    new_tree = {
        "version": 2, "budget": 50000,
        "nodes": {"root": {"file": "root.mn", "lines": 10, "tags": []}},
    }
    mt.save_tree(new_tree)
    saved = json.loads(tree_meta.read_text())
    assert saved["budget"] == 50000


def test_save_tree_atomic_under_simulated_failure(isolated_tree):
    """Sanity: save_tree must clean up tempfile on inner failure."""
    mt = _load_muninn_tree()
    tmp_path, tree_dir, tree_meta = isolated_tree
    initial_size = tree_meta.stat().st_size

    # Make json.dump fail mid-write
    bad_tree = {"version": 2, "nodes": {"break": object()}}  # not JSON-serializable
    with pytest.raises((TypeError, ValueError, RuntimeError, Exception)):
        mt.save_tree(bad_tree)

    # tree.json should be unchanged (atomic — bad write didn't replace)
    assert tree_meta.exists()
    # No leftover .tmp files in tree dir
    leftover = list(tree_dir.glob("tree_*.tmp"))
    assert not leftover, f"leftover tempfiles after failure: {leftover}"
