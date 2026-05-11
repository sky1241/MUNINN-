"""
CHUNK MCP B.2 — `tree_get_root` + `tree_get_branch` + `tree_list_branches` MCP tools.

Expose `.muninn/tree/{root.mn, bXX.mn, tree.json}` to Claude during generation
as 3 read-only MCP tools so Claude can actively explore the project memory tree.

Design contracts:
  - READ-ONLY STRICT : never call engine/core read_node() — it mutates
    access_count, last_access, calls save_tree() and reconsolidation.
    Use a private helper `_load_tree_for_repo()` instead.
  - 60K chars cap per tool result, sentinel `truncated: True` when reached.
  - Regex-validated branch_name to block path-traversal.
  - Missing branch returns `{error, available}` instead of raising — so
    Claude can recover by listing branches and retrying.

Tests (11 behavioural):
1. 3 tools registered in the FastMCP app
2. tree_get_root returns dict with content + metadata
3. tree_get_branch existing returns content byte-for-byte
4. tree_get_branch missing returns friendly error + available list (no raise)
5. tree_get_branch rejects path traversal (../../etc/passwd)
6. Output cap 60K chars enforced with truncated=True sentinel
7. Invalid repo_path raises ValueError mentioning muninn
8. Repo without tree dir raises ValueError friendly
9. All 3 tools output JSON-serializable
10. mycelium.db mtime untouched after all 3 tool calls (proof read-only)
11. tree_list_branches sorted by last_access DESC, excludes "root"
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))

mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


# ── Test fixture: a minimal Muninn-bootstrapped repo with a tree ─────────────


def _make_tree_repo(tmp_path):
    """Create tmp/.muninn/tree/{root.mn, b01.mn, b02.mn, tree.json, mycelium.db}.

    Returns the repo Path. Mtimes on tree.json carry the last_access ordering:
    b02 (newer) > b01 (older).
    """
    repo = tmp_path / "tree_repo"
    repo.mkdir()
    muninn_dir = repo / ".muninn"
    muninn_dir.mkdir()
    tree_dir = muninn_dir / "tree"
    tree_dir.mkdir()

    (tree_dir / "root.mn").write_text(
        "P:tree_repo|python|1234L|42files\n"
        "E:src/main.py\n"
        "S:bootstrap|2026-05-11|mycelium:100conn\n"
        "\n"
        "F:\n"
        "  src/main.py 500L\n"
        "\n"
        "K:python,test,muninn\n",
        encoding="utf-8",
    )
    (tree_dir / "b01.mn").write_text("# b01 content\nKEYWORD_b01_xyz\n", encoding="utf-8")
    (tree_dir / "b02.mn").write_text("# b02 content\nKEYWORD_b02_abc\n", encoding="utf-8")

    tree_json = {
        "version": 2,
        "created": "2026-05-11",
        "nodes": {
            "root": {
                "type": "root", "file": "root.mn", "lines": 8,
                "max_lines": 30, "last_access": "2026-05-11",
                "access_count": 0, "tags": ["python", "test"],
                "children": ["b01", "b02"],
            },
            "b01": {
                "type": "branch", "file": "b01.mn", "lines": 2,
                "max_lines": 150, "last_access": "2026-05-09",
                "access_count": 0, "tags": ["test"], "temperature": 0.3,
            },
            "b02": {
                "type": "branch", "file": "b02.mn", "lines": 2,
                "max_lines": 150, "last_access": "2026-05-11",
                "access_count": 0, "tags": ["python"], "temperature": 0.7,
            },
        },
    }
    (tree_dir / "tree.json").write_text(
        json.dumps(tree_json, indent=2), encoding="utf-8"
    )

    # Fake mycelium.db so we can pin its mtime
    (muninn_dir / "mycelium.db").write_bytes(b"SQLite stub")
    return repo


# ── Tool registration ─────────────────────────────────────────


def test_three_tools_registered():
    """tree_get_root, tree_get_branch, tree_list_branches all in list_tools()."""
    import asyncio
    from muninn.mcp import server
    app = server.create_server()
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    for required in ("tree_get_root", "tree_get_branch", "tree_list_branches"):
        assert required in names, (
            f"{required!r} not registered. Got: {sorted(names)}"
        )


# ── tree_get_root ─────────────────────────────────────────


def test_tree_get_root_returns_content_and_metadata(tmp_path):
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    r = server._tree_get_root_impl(repo_path=str(repo))
    assert isinstance(r, dict)
    for k in ("node", "content", "metadata", "truncated", "repo_path", "elapsed_ms"):
        assert k in r, f"missing key {k!r}, got {list(r.keys())}"
    assert r["node"] == "root"
    assert "P:tree_repo" in r["content"]
    assert isinstance(r["metadata"], dict)
    assert r["metadata"]["children"] == ["b01", "b02"]
    assert r["truncated"] is False


# ── tree_get_branch ─────────────────────────────────────────


def test_tree_get_branch_existing_returns_content(tmp_path):
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    r = server._tree_get_branch_impl(branch_name="b01", repo_path=str(repo))
    assert r["node"] == "b01"
    assert "KEYWORD_b01_xyz" in r["content"]
    assert r["metadata"]["lines"] == 2


def test_tree_get_branch_missing_returns_friendly_error(tmp_path):
    """branch_name absent must NOT raise — Claude needs to recover."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    r = server._tree_get_branch_impl(branch_name="b99", repo_path=str(repo))
    assert "error" in r
    assert "available" in r
    assert set(r["available"]) >= {"b01", "b02"}
    assert "b99" in r["error"]


def test_tree_get_branch_rejects_path_traversal(tmp_path):
    """branch_name=../../../etc/passwd must raise (regex validated)."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    with pytest.raises(ValueError) as exc:
        server._tree_get_branch_impl(
            branch_name="../../../etc/passwd", repo_path=str(repo)
        )
    assert "branch_name" in str(exc.value).lower() or "invalid" in str(exc.value).lower()


# ── Cap + truncation ─────────────────────────────────────────


def test_cap_output_60k_truncates_with_sentinel(tmp_path):
    """A 100K-char branch must be capped to ~60K with truncated=True."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    (repo / ".muninn" / "tree" / "b03.mn").write_text("X" * 100_000, encoding="utf-8")
    # Add b03 to tree.json
    tree_json_path = repo / ".muninn" / "tree" / "tree.json"
    tree = json.loads(tree_json_path.read_text(encoding="utf-8"))
    tree["nodes"]["b03"] = {
        "type": "branch", "file": "b03.mn", "lines": 1,
        "max_lines": 150, "last_access": "2026-05-08",
        "access_count": 0, "tags": [], "temperature": 0.1,
    }
    tree_json_path.write_text(json.dumps(tree, indent=2), encoding="utf-8")

    r = server._tree_get_branch_impl(branch_name="b03", repo_path=str(repo))
    assert r["truncated"] is True
    assert len(r["content"]) <= 60_500, (
        f"content not capped: got {len(r['content'])} chars"
    )


# ── Error handling ─────────────────────────────────────────


def test_invalid_repo_path_raises(tmp_path):
    from muninn.mcp import server
    with pytest.raises(ValueError) as exc:
        server._tree_get_root_impl(repo_path="/this/does/not/exist/nope")
    msg = str(exc.value).lower()
    assert "muninn" in msg or "repo" in msg or "not found" in msg or "tree" in msg


def test_repo_without_tree_dir_raises(tmp_path):
    from muninn.mcp import server
    repo = tmp_path / "no_tree"
    repo.mkdir()
    (repo / ".muninn").mkdir()  # has .muninn but no .muninn/tree
    with pytest.raises(ValueError):
        server._tree_get_root_impl(repo_path=str(repo))


# ── JSON serializability ─────────────────────────────────────


def test_output_json_serializable(tmp_path):
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    for r in (
        server._tree_get_root_impl(repo_path=str(repo)),
        server._tree_get_branch_impl(branch_name="b01", repo_path=str(repo)),
        server._tree_list_branches_impl(repo_path=str(repo)),
    ):
        encoded = json.dumps(r)
        assert isinstance(encoded, str)


# ── Read-only proof ─────────────────────────────────────────


def test_tools_dont_touch_mycelium_db(tmp_path):
    """All 3 tools must NOT modify mycelium.db (mtime unchanged)."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    db = repo / ".muninn" / "mycelium.db"
    before_mtime = db.stat().st_mtime
    time.sleep(0.01)  # FS mtime granularity

    server._tree_get_root_impl(repo_path=str(repo))
    server._tree_get_branch_impl(branch_name="b01", repo_path=str(repo))
    server._tree_list_branches_impl(repo_path=str(repo))

    after_mtime = db.stat().st_mtime
    assert before_mtime == after_mtime, (
        f"mycelium.db mtime changed: {before_mtime} -> {after_mtime}"
    )


def test_tools_dont_touch_tree_json(tmp_path):
    """The 3 read-only tools must NOT modify tree.json (no access_count++)."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    tree_json = repo / ".muninn" / "tree" / "tree.json"
    before_mtime = tree_json.stat().st_mtime
    before_content = tree_json.read_text(encoding="utf-8")
    time.sleep(0.01)

    server._tree_get_root_impl(repo_path=str(repo))
    server._tree_get_branch_impl(branch_name="b01", repo_path=str(repo))
    server._tree_list_branches_impl(repo_path=str(repo))

    assert tree_json.stat().st_mtime == before_mtime
    assert tree_json.read_text(encoding="utf-8") == before_content


# ── tree_list_branches sort ──────────────────────────────────


def test_tree_list_branches_sorted_by_last_access_desc(tmp_path):
    """Most recently accessed branch comes first; root excluded."""
    from muninn.mcp import server
    repo = _make_tree_repo(tmp_path)
    r = server._tree_list_branches_impl(repo_path=str(repo))
    assert "branches" in r
    names = [b["name"] for b in r["branches"]]
    assert "root" not in names
    # b02 has last_access 2026-05-11, b01 has 2026-05-09 → b02 first
    assert names[0] == "b02", f"expected b02 first, got {names}"
    assert r["count"] == 2
