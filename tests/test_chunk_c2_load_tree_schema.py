"""CHUNK C2 — schema validation in load_tree.

`load_tree` catches JSONDecodeError but accepts any *valid* JSON.
A poisoned tree.json containing `{"foo": "bar"}` parses fine, then
the rest of the pipeline crashes on `tree["nodes"][...]` accesses.

Fix: post-parse, validate that the loaded value is a dict and has
the required top-level keys (`version`, `nodes`). If not, backup
the corrupt file and call init_tree() — same recovery path as
JSONDecodeError.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C2
"""
import json
import sys
from pathlib import Path

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
def tree_setup(tmp_path, monkeypatch):
    tree_dir = tmp_path / "tree"
    tree_dir.mkdir()
    tree_meta = tree_dir / "tree.json"

    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    monkeypatch.setattr(_m, "TREE_DIR", tree_dir)
    monkeypatch.setattr(_m, "TREE_META", tree_meta)
    return tmp_path, tree_dir, tree_meta


def test_load_tree_accepts_valid_schema(tree_setup):
    """Sanity: a well-formed tree.json loads cleanly."""
    mt = _load_muninn_tree()
    _, _, tree_meta = tree_setup
    valid = {
        "version": 2, "budget": 30000,
        "nodes": {"root": {"file": "root.mn", "lines": 5, "tags": []}},
        "updated": "2026-05-08",
    }
    tree_meta.write_text(json.dumps(valid))
    result = mt.load_tree()
    assert result["version"] == 2
    assert "root" in result["nodes"]


def test_load_tree_rejects_missing_nodes_key(tree_setup):
    """tree.json without "nodes" key must be backed up and re-initialized."""
    mt = _load_muninn_tree()
    _, tree_dir, tree_meta = tree_setup
    tree_meta.write_text(json.dumps({"version": 2, "budget": 30000}))
    result = mt.load_tree()
    # Must have re-initialized (init_tree always provides "nodes")
    assert "nodes" in result, "load_tree should have called init_tree()"
    # And a backup file should exist
    backups = list(tree_dir.glob("tree*.corrupted.*.json"))
    assert backups, "expected a .corrupted.<ts>.json backup file"


def test_load_tree_rejects_missing_version_key(tree_setup):
    """tree.json without "version" key must be backed up and re-init."""
    mt = _load_muninn_tree()
    _, tree_dir, tree_meta = tree_setup
    tree_meta.write_text(json.dumps({"nodes": {}, "budget": 30000}))
    result = mt.load_tree()
    assert "version" in result
    backups = list(tree_dir.glob("tree*.corrupted.*.json"))
    assert backups


def test_load_tree_rejects_list_payload(tree_setup):
    """tree.json that deserializes to a list must be backed up + re-init."""
    mt = _load_muninn_tree()
    _, tree_dir, tree_meta = tree_setup
    tree_meta.write_text(json.dumps(["not", "a", "tree"]))
    result = mt.load_tree()
    assert isinstance(result, dict)
    assert "nodes" in result
    backups = list(tree_dir.glob("tree*.corrupted.*.json"))
    assert backups


def test_load_tree_rejects_string_payload(tree_setup):
    """A string-serialized tree.json must trigger recovery."""
    mt = _load_muninn_tree()
    _, tree_dir, tree_meta = tree_setup
    tree_meta.write_text(json.dumps("oops"))
    result = mt.load_tree()
    assert isinstance(result, dict)
    assert "nodes" in result
    backups = list(tree_dir.glob("tree*.corrupted.*.json"))
    assert backups


def test_load_tree_path_traversal_still_sanitized(tree_setup):
    """Regression: existing path-traversal protection in load_tree still works."""
    mt = _load_muninn_tree()
    _, _, tree_meta = tree_setup
    poisoned = {
        "version": 2, "budget": 30000,
        "nodes": {
            "root": {"file": "root.mn", "lines": 1, "tags": []},
            "evil": {"file": "../../etc/passwd", "lines": 1, "tags": []},
        },
    }
    tree_meta.write_text(json.dumps(poisoned))
    result = mt.load_tree()
    # The sanitizer must have rewritten the evil node
    assert result["nodes"]["evil"]["file"] != "../../etc/passwd"
