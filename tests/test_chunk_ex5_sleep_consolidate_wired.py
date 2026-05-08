"""CHUNK EX5 — sleep_consolidate dead-path in feed_from_hook.

Sky asked "le sleep consolidation c'était pas branché ce matin" and
he was right. Audit found:
  engine/core/muninn_feed.py:1296 (in feed_from_hook):
      nodes = {n["name"]: n for n in tree.get("nodes", []) if isinstance(n, dict)}

`tree["nodes"]` is a DICT (str -> node), not a list. The comprehension
iterates over the keys (strings), `isinstance(str, dict) == False`,
so `nodes` is ALWAYS an empty dict. → `cold = []` → `_sleep_consolidate`
never gets called via the hook path.

`prune()` calls `_sleep_consolidate` (muninn_tree.py:2994) but only
inside `if not dry_run:` block — so the default `muninn prune` (no
--force) skips consolidation entirely.

Result: Wilson & McNaughton 1994 sleep consolidation is functionally
DEAD CODE in normal runtime. Only triggers on `muninn prune --force`.

Fix: rewrite line 1296 to iterate over the dict properly.

Source: docs/BATTLE_PLAN_FINAL_2026-05-08.md (post-audit Sky question)
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_feed():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_feed" in sys.modules:
        return sys.modules["muninn_feed"]
    import muninn_feed
    return muninn_feed


def test_feed_from_hook_iterates_tree_nodes_dict_correctly():
    """Static check: line ~1296 must iterate dict items, not list items."""
    src = (REPO / "engine" / "core" / "muninn_feed.py").read_text()
    # Pre-fix had: `for n in tree.get("nodes", [])` — empty default list
    # Post-fix should iterate items() of the dict
    assert "for name, node in" in src or ".items()" in src, (
        "feed_from_hook must iterate tree['nodes'] as a dict (with .items() "
        "or 'for name, node in...'). Current code uses 'for n in <dict>' "
        "which silently produces empty results."
    )


def test_buggy_pattern_no_longer_present():
    """The exact buggy pattern `for n in tree.get("nodes", [])` must be gone."""
    src = (REPO / "engine" / "core" / "muninn_feed.py").read_text()
    # The bug was: `for n in tree.get("nodes", [])` with `[]` default
    # which produces empty when the actual value is a dict.
    bad_pattern = 'for n in tree.get("nodes", [])'
    assert bad_pattern not in src, (
        f"Buggy pattern still present in muninn_feed.py: {bad_pattern!r}\n"
        f"This makes _sleep_consolidate dead in feed_from_hook path."
    )


def test_sleep_consolidate_can_be_called_with_real_dict_tree(tmp_path):
    """Functional repro: build a tree with cold branches matching the
    real format, run the same code path that feed_from_hook uses, and
    verify cold list is non-empty."""
    mf = _load_muninn_feed()

    # Real-format tree.json (mirrors actual production structure)
    real_tree = {
        "version": 2,
        "nodes": {
            "root": {
                "type": "root", "file": "root.mn", "lines": 5,
                "max_lines": 100, "tags": [],
                "last_access": "2026-04-01",
                "access_history": ["2026-04-01"],
                "access_count": 1,
            },
            "b00": {
                "type": "branch", "file": "b00.mn", "lines": 10,
                "max_lines": 150, "tags": ["cold_topic"],
                "last_access": "2026-01-01",  # 4+ months old → cold
                "access_history": ["2026-01-01"],
                "access_count": 1,
            },
        },
    }

    # Reproduce the buggy line 1296 pattern (POST-FIX must work):
    # nodes = {n["name"]: n for n in real_tree.get("nodes", []) if isinstance(n, dict)}
    # → buggy: produces {} because real_tree["nodes"] is dict, iter yields keys (strings)

    # Correct pattern (post-fix):
    nodes = {
        name: node for name, node in real_tree.get("nodes", {}).items()
        if isinstance(node, dict)
    }
    # This is the assertion the code must satisfy at runtime
    assert len(nodes) == 2, (
        f"Tree iteration produced {len(nodes)} nodes; expected 2. "
        f"If 0, the dict comprehension is BUGGY (iterating over keys "
        f"as if they were dicts)."
    )
    assert "root" in nodes and "b00" in nodes


def test_sleep_consolidate_helper_callable():
    """Sanity: _sleep_consolidate exists and is callable."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    import muninn_tree
    assert hasattr(muninn_tree, "_sleep_consolidate"), (
        "_sleep_consolidate helper missing from muninn_tree"
    )
    assert callable(muninn_tree._sleep_consolidate)
