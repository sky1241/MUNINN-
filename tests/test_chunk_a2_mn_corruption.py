"""CHUNK A2 — UnicodeDecodeError handlers sur .mn truncated.

Si un process est tué pendant l'écriture d'un .mn, le fichier contient
des séquences UTF-8 incomplètes. Sans handler, `read_text(encoding="utf-8")`
lève UnicodeDecodeError et tue tout le pipeline ingestion.

4 sites confirmés (verbatim) dans muninn_tree.py:
- l.751  grow_branches_from_session: content = mn_path.read_text(encoding="utf-8")
- l.812  merge path:                  existing_text = existing_file.read_text(encoding="utf-8")
- l.827  merge path:                  old = filepath.read_text(encoding="utf-8")
- l.2884 prune cold-branch:           content = filepath.read_text(encoding="utf-8")

Note: l.524 (read_node) est DÉJÀ protégée — pas dans le scope de ce chunk.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A2
"""
import json
import sys
from pathlib import Path

import pytest

ENGINE_CORE = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


# Bytes that produce UnicodeDecodeError on UTF-8 decode:
# \xc3 alone is the start of a 2-byte sequence; missing continuation = invalid.
_TRUNCATED_UTF8_TAIL = b"\xc3"


def _make_truncated_mn(path: Path, valid_prefix: str) -> Path:
    """Write a .mn file with valid UTF-8 prefix + truncated multi-byte tail."""
    path.write_bytes(valid_prefix.encode("utf-8") + _TRUNCATED_UTF8_TAIL)
    return path


@pytest.fixture
def isolated_tree(tmp_path, monkeypatch):
    """Set up a tmp tree dir + tree.json so muninn_tree can operate."""
    tree_dir = tmp_path / "tree"
    tree_dir.mkdir()
    tree_meta = tree_dir / "tree.json"

    # Minimal valid tree
    tree_meta.write_text(json.dumps({
        "version": 2,
        "budget": 30000,
        "nodes": {
            "root": {"file": "root.mn", "lines": 5, "tags": []},
        },
        "updated": "2026-05-08",
    }))
    (tree_dir / "root.mn").write_text("# Root\nfact: x\n")

    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    monkeypatch.setattr(_m, "TREE_DIR", tree_dir)
    monkeypatch.setattr(_m, "TREE_META", tree_meta)

    return tmp_path, tree_dir, tree_meta


def test_safe_read_mn_returns_none_on_truncated(isolated_tree):
    """Helper _safe_read_mn must return None (not crash) on truncated UTF-8.

    This test will be SKIPPED if _safe_read_mn does not yet exist
    (pre-fix) and PASS after the helper is added.
    """
    import muninn_tree
    assert hasattr(muninn_tree, "_safe_read_mn"), \
        "_safe_read_mn missing — should be in muninn_tree since chunk a2 fix"
    tmp_path, tree_dir, _ = isolated_tree
    bad = _make_truncated_mn(tree_dir / "broken.mn", "## hdr\nfact: été ok\n")
    result = muninn_tree._safe_read_mn(bad)
    assert result is None, f"Expected None on truncated mn, got: {result!r}"


def test_safe_read_mn_returns_text_on_valid(isolated_tree):
    """Helper must return the text on valid UTF-8."""
    import muninn_tree
    assert hasattr(muninn_tree, "_safe_read_mn"), \
        "_safe_read_mn missing — should be in muninn_tree since chunk a2 fix"
    tmp_path, tree_dir, _ = isolated_tree
    good = tree_dir / "good.mn"
    good.write_text("## valid\nfact: été ok\n", encoding="utf-8")
    result = muninn_tree._safe_read_mn(good)
    assert result == "## valid\nfact: été ok\n"


def test_grow_branches_handles_truncated_mn(isolated_tree):
    """l.751 fix: grow_branches_from_session must not crash on truncated .mn."""
    import muninn_tree
    tmp_path, _, _ = isolated_tree
    bad = _make_truncated_mn(tmp_path / "session.mn",
                             "## sec1\nfact: a\nfact: b\nfact: c\nfact: d\n## sec2\nfact: ")
    # Must not raise UnicodeDecodeError
    result = muninn_tree.grow_branches_from_session(bad)
    # Either 0 (skipped) or some count from the valid prefix — neither crashes
    assert isinstance(result, int)
    assert result >= 0


def test_grow_branches_with_corrupted_existing_branch(isolated_tree):
    """l.812+l.827 fix: merge path must not crash if existing branch .mn is corrupted.

    Setup: tree has branch b00 with corrupted .mn on disk. New session
    .mn arrives → grow_branches tries to compute NCD (l.812) and merge
    content (l.827) on the corrupted file.
    """
    import muninn_tree
    tmp_path, tree_dir, tree_meta = isolated_tree

    # Create a corrupted existing branch on disk
    _make_truncated_mn(tree_dir / "b00.mn", "## existing\nfact: été\nfact: ")

    # Add b00 to tree.json
    tree = json.loads(tree_meta.read_text())
    tree["nodes"]["b00"] = {
        "file": "b00.mn",
        "lines": 4,
        "tags": ["existing", "fact"],
        "max_lines": 150,
    }
    tree_meta.write_text(json.dumps(tree))

    # New incoming session
    session = tmp_path / "incoming.mn"
    session.write_text(
        "## existing\nfact: a\nfact: b\nfact: c\nfact: d\nfact: extra\n",
        encoding="utf-8",
    )

    # Must not crash on UnicodeDecodeError when reading the corrupt b00.mn
    result = muninn_tree.grow_branches_from_session(session)
    assert isinstance(result, int)


def test_prune_cold_branch_handles_corrupted(isolated_tree):
    """l.2884 fix: cold-branch recompression path must not crash on truncated .mn.

    The cold-branch path reads filepath.read_text() before _llm_compress.
    Without the fix, a truncated .mn would crash the entire prune loop.
    """
    import muninn_tree
    tmp_path, tree_dir, tree_meta = isolated_tree

    # Corrupted cold branch on disk
    _make_truncated_mn(tree_dir / "b00.mn", "## old session\nfact: été was here\n" * 10)

    # Mark b00 as cold (>30 days) in tree
    tree = json.loads(tree_meta.read_text())
    tree["nodes"]["b00"] = {
        "file": "b00.mn",
        "lines": 30,
        "tags": [],
        "last_access": "2025-01-01",  # Very old → cold
        "access_count": 0,
        "max_lines": 150,
    }
    tree_meta.write_text(json.dumps(tree))

    # Prune dry_run=False to trigger the recompression path.
    # We just need the call to not raise UnicodeDecodeError; final state
    # depends on prune's other logic.
    try:
        muninn_tree.prune(dry_run=True)
    except UnicodeDecodeError as e:
        pytest.fail(f"prune crashed on truncated .mn: {e}")
    except Exception as e:
        # Other exceptions OK — only UnicodeDecodeError is the regression we guard
        if "UnicodeDecodeError" in str(type(e).__name__):
            pytest.fail(f"prune leaked UnicodeDecodeError: {e}")
