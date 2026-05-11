"""Muninn MCP server — FastMCP scaffold + first tool `mycelium_recall_local`.

Chunk B.1 of docs/BATTLE_PLAN_MASTER_MCP.md. First step of Phase B (MCP
server core, the killer feature). This module is a PURE ADAPTER over
Mycelium.spread_activation — no new algorithmic logic, hence no forge
property tests required (RULE 5 N/A : not under engine/core/).

Architecture:
  - FastMCP app named "muninn"
  - Transport: stdio (Claude Code spawns the process)
  - 1 tool exposed: mycelium_recall_local (this chunk B.1)
  - Future chunks will add: mycelium_recall_meta (B.3), mycelium_recall
    with auto routing (B.3), tree_get_root (B.4), bugs_list (B.5), etc.

Logging: stderr ONLY. stdout is reserved for the MCP JSON-RPC protocol —
any stray print() to stdout corrupts the wire format.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "muninn.mcp requires the 'mcp' package. "
        "Install with: pip install 'muninn-memory[mcp]'"
    ) from exc


# stderr-only logger (stdout = MCP protocol, must stay clean)
_log = logging.getLogger("muninn.mcp")
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [muninn.mcp] %(levelname)s: %(message)s"
    ))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)


# Hard caps — protect Claude's context window and avoid pathological queries.
TOP_K_MAX = 100
TOP_K_MIN = 1
HOPS_MAX = 3
HOPS_MIN = 1

# Tool result cap — a tool response lives in the current message (not the
# system prompt cache), so Claude tolerates a bit more than the SessionStart
# hook (40K). We cap at 60K chars (~15K tokens) with a truncated sentinel.
TREE_TOOL_MAX_CHARS = 60_000

# Branch name validation — anti path-traversal. Matches the Muninn convention
# `root` / `bNN` / arbitrary safe identifiers.
_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _resolve_repo_path(repo_path: str | None) -> Path:
    """Resolve the target repo: explicit arg > MUNINN_REPO env > cwd."""
    if repo_path:
        return Path(repo_path).resolve()
    env_repo = os.environ.get("MUNINN_REPO")
    if env_repo:
        return Path(env_repo).resolve()
    return Path.cwd().resolve()


def _tokenize_query(query: str) -> list[str]:
    """Extract word-like tokens (>=3 chars) from the free-text query.

    Same heuristic as muninn boot's query expansion (Park et al. 2023 style).
    """
    return [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]{3,}", query or "")]


def _recall_local_impl(
    query: str,
    top_k: int = 10,
    repo_path: str | None = None,
    hops: int = 2,
) -> dict:
    """Pure-Python implementation of the mycelium_recall_local tool.

    Factored out of the FastMCP @tool wrapper so that tests can call it
    directly without spinning up a stdio subprocess.

    Returns a JSON-serializable dict:
      {
        "query": str,
        "results": [{"concept": str, "activation": float, "hops": int}],
        "elapsed_ms": float,
        "source": "local",
        "repo_path": str,
      }

    Raises:
        ValueError if repo_path is not a Muninn-bootstrapped project
            (i.e. no .muninn/ directory).
    """
    start = time.time()

    # Clamp bounds so the tool can never blow up Claude's context window.
    top_k = max(TOP_K_MIN, min(TOP_K_MAX, int(top_k)))
    hops = max(HOPS_MIN, min(HOPS_MAX, int(hops)))

    repo = _resolve_repo_path(repo_path)
    if not (repo / ".muninn").exists():
        raise ValueError(
            f"{repo} is not a Muninn-bootstrapped project (no .muninn/ "
            f"directory). Run `muninn init` in the repo first."
        )

    # Lazy-import Mycelium so the bare `import muninn.mcp` does not load
    # the entire engine (~24K LOC). Server boot stays fast.
    _engine_core = Path(__file__).resolve().parent.parent.parent / "engine" / "core"
    if str(_engine_core) not in sys.path:
        sys.path.insert(0, str(_engine_core))
    from mycelium import Mycelium  # noqa: E402

    seeds = _tokenize_query(query)
    results: list[dict] = []

    if not seeds:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round(elapsed_ms, 2),
            "source": "local",
            "repo_path": str(repo),
        }

    try:
        m = Mycelium(repo)
    except (sqlite3.OperationalError, OSError) as exc:
        _log.warning("mycelium open failed: %s", exc)
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round(elapsed_ms, 2),
            "source": "local",
            "repo_path": str(repo),
            "error": f"db_unavailable: {type(exc).__name__}",
        }

    try:
        activated = m.spread_activation(seeds, hops=hops, top_n=top_k)
    except sqlite3.OperationalError as exc:
        # DB locked by another writer — degrade gracefully.
        _log.warning("mycelium db locked: %s", exc)
        activated = []
    except Exception as exc:  # noqa: BLE001 — never crash the MCP tool
        _log.exception("spread_activation failed: %s", exc)
        activated = []
    finally:
        try:
            m.close()
        except Exception:
            pass

    for concept, activation in activated[:top_k]:
        results.append({
            "concept": str(concept),
            "activation": round(float(activation), 4),
            "hops": hops,
        })

    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "query": query,
        "results": results,
        "elapsed_ms": round(elapsed_ms, 2),
        "source": "local",
        "repo_path": str(repo),
    }


# ── Chunk B.2 tree tools (read-only) ─────────────────────────────────────────


def _load_tree_for_repo(repo: Path) -> dict:
    """Load <repo>/.muninn/tree/tree.json read-only (no side-effects).

    Deliberately bypasses engine/core/muninn_tree.read_node() which mutates
    `access_count`, updates `last_access`, calls `save_tree`, and triggers
    reconsolidation. The MCP tree tools must NOT change the Muninn state
    of Sky's repo just because Claude queried it.

    Raises:
        ValueError if repo is not Muninn-bootstrapped or tree.json missing.
    """
    tree_dir = repo / ".muninn" / "tree"
    if not tree_dir.exists() or not tree_dir.is_dir():
        raise ValueError(
            f"{repo} has no .muninn/tree/ directory — not a Muninn-bootstrapped "
            f"project. Run `muninn init` in the repo first."
        )
    tree_json = tree_dir / "tree.json"
    if not tree_json.exists():
        raise ValueError(
            f"{repo}/.muninn/tree/tree.json is missing. Re-run `muninn init` "
            f"or `muninn bootstrap` to regenerate."
        )
    try:
        return json.loads(tree_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{tree_json} is not valid JSON: {exc}") from exc


def _cap_with_marker(content: str, max_chars: int) -> tuple[str, bool]:
    """Truncate at last newline before max_chars + marker. Returns (text, truncated)."""
    if len(content) <= max_chars:
        return content, False
    marker = "\n…[truncated, content exceeds %d chars]" % max_chars
    slice_end = max(0, max_chars - len(marker))
    # Snap to the last newline to avoid cutting mid-line.
    cut = content.rfind("\n", 0, slice_end)
    if cut > 0:
        slice_end = cut
    return content[:slice_end] + marker, True


def _read_branch_file(repo: Path, file_name: str) -> str:
    """Read <repo>/.muninn/tree/<file_name>. Path traversal already guarded by
    branch_name regex upstream, but we double-check resolved path stays inside
    the tree dir as a belt-and-suspenders.
    """
    tree_dir = (repo / ".muninn" / "tree").resolve()
    target = (tree_dir / file_name).resolve()
    if not str(target).startswith(str(tree_dir)):
        raise ValueError(f"branch file {file_name!r} escapes the tree dir")
    if not target.exists():
        raise FileNotFoundError(str(target))
    return target.read_text(encoding="utf-8")


def _tree_get_root_impl(repo_path: str | None = None) -> dict:
    """Read-only fetch of <repo>/.muninn/tree/root.mn + its metadata."""
    start = time.time()
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    root_meta = nodes.get("root")
    if root_meta is None:
        raise ValueError(f"{repo}/.muninn/tree/tree.json has no 'root' node")
    file_name = root_meta.get("file", "root.mn")
    try:
        content = _read_branch_file(repo, file_name)
    except FileNotFoundError as exc:
        raise ValueError(f"root.mn not found: {exc}") from exc
    capped, truncated = _cap_with_marker(content, TREE_TOOL_MAX_CHARS)
    metadata = {
        "lines": root_meta.get("lines"),
        "max_lines": root_meta.get("max_lines"),
        "last_access": root_meta.get("last_access"),
        "access_count": root_meta.get("access_count"),
        "tags": list(root_meta.get("tags", [])),
        "children": list(root_meta.get("children", [])),
        "hash": root_meta.get("hash"),
        "temperature": root_meta.get("temperature"),
    }
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "node": "root",
        "content": capped,
        "metadata": metadata,
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _tree_get_branch_impl(branch_name: str, repo_path: str | None = None) -> dict:
    """Read-only fetch of <repo>/.muninn/tree/<branch_name>.mn + metadata.

    `branch_name` is validated against ^[A-Za-z0-9_]{1,64}$ — anti path-traversal.
    If the branch doesn't exist, returns {error, available} instead of raising
    so Claude can recover (typically by calling tree_list_branches).
    """
    start = time.time()
    if not isinstance(branch_name, str) or not _BRANCH_NAME_RE.match(branch_name):
        raise ValueError(
            f"invalid branch_name {branch_name!r}: must match ^[A-Za-z0-9_]{{1,64}}$"
        )
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    if branch_name not in nodes:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "error": f"branch {branch_name!r} not in tree",
            "available": sorted(n for n in nodes.keys() if n != "root"),
            "repo_path": str(repo),
            "elapsed_ms": round(elapsed_ms, 2),
        }
    meta = nodes[branch_name]
    file_name = meta.get("file", f"{branch_name}.mn")
    try:
        content = _read_branch_file(repo, file_name)
    except FileNotFoundError:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "error": f"branch {branch_name!r} file {file_name!r} missing on disk",
            "available": sorted(n for n in nodes.keys() if n != "root"),
            "repo_path": str(repo),
            "elapsed_ms": round(elapsed_ms, 2),
        }
    capped, truncated = _cap_with_marker(content, TREE_TOOL_MAX_CHARS)
    metadata = {
        "lines": meta.get("lines"),
        "max_lines": meta.get("max_lines"),
        "last_access": meta.get("last_access"),
        "access_count": meta.get("access_count"),
        "tags": list(meta.get("tags", [])),
        "hash": meta.get("hash"),
        "temperature": meta.get("temperature"),
        "usefulness": meta.get("usefulness"),
    }
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "node": branch_name,
        "content": capped,
        "metadata": metadata,
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _tree_list_branches_impl(repo_path: str | None = None) -> dict:
    """List all branches sorted by last_access DESC. Excludes 'root'.

    Lets Claude discover what branches exist before querying with tree_get_branch.
    """
    start = time.time()
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    branches = []
    for name, meta in nodes.items():
        if name == "root":
            continue
        if not isinstance(meta, dict):
            continue
        branches.append({
            "name": name,
            "lines": meta.get("lines"),
            "last_access": meta.get("last_access", ""),
            "access_count": meta.get("access_count", 0),
            "temperature": meta.get("temperature"),
            "tags": list(meta.get("tags", []))[:5],
            "children_count": len(meta.get("children", [])),
        })
    branches.sort(key=lambda b: b.get("last_access") or "", reverse=True)
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "branches": branches,
        "count": len(branches),
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def create_server() -> FastMCP:
    """Build the Muninn FastMCP app and register the chunk-B.1 + B.2 tools.

    Factored from main() so tests can introspect the registered tools
    without spawning a stdio process.
    """
    app = FastMCP("muninn")

    @app.tool()
    def mycelium_recall_local(
        query: str,
        top_k: int = 10,
        repo_path: str | None = None,
        hops: int = 2,
    ) -> dict:
        """Search Sky's *local* mycelium for concepts semantically related to query.

        Uses Collins & Loftus 1975 spreading activation over the project's
        .muninn/mycelium.db (NOT the meta-mycelium). Latency target <50ms.

        Args:
            query: free-text question or keywords ("BUG-104 spill tree").
            top_k: max results returned (1..100, default 10).
            repo_path: absolute path to a Muninn-bootstrapped project.
                       Defaults to $MUNINN_REPO env, then cwd.
            hops: spreading-activation propagation depth (1..3, default 2).

        Returns:
            {
              "query": str,
              "results": [{"concept": str, "activation": float, "hops": int}],
              "elapsed_ms": float,
              "source": "local",
              "repo_path": str,
            }

        Raises:
            ValueError if repo_path is not a Muninn-bootstrapped project.
        """
        return _recall_local_impl(
            query=query, top_k=top_k, repo_path=repo_path, hops=hops,
        )

    # ── Chunk B.2 tree tools (read-only access to .muninn/tree/) ──

    @app.tool()
    def tree_get_root(repo_path: str | None = None) -> dict:
        """Read Muninn's root.mn — the project's compressed summary.

        Returns the content of <repo>/.muninn/tree/root.mn (the ~200 token
        machine-optimal snapshot listing project name, language, line count,
        focal file, mycelium state, top files, top keywords, recent commits)
        plus its metadata (children branches, tags, hash, last_access).

        Args:
            repo_path: absolute path to a Muninn-bootstrapped project. Defaults
                       to $MUNINN_REPO env, then cwd.

        Returns:
            {
              "node": "root",
              "content": str,                # the literal root.mn text
              "metadata": {
                "lines": int, "max_lines": int,
                "last_access": str, "access_count": int,
                "tags": [str], "children": [str],
                "hash": str, "temperature": float,
              },
              "truncated": bool,             # True if content > 60K chars
              "repo_path": str,
              "elapsed_ms": float,
            }

        Read-only: this tool does NOT update access_count or last_access on
        disk (unlike engine/core read_node). Safe to call from a query path.

        Raises:
            ValueError if repo_path is not a Muninn-bootstrapped project
            (no .muninn/tree/tree.json).
        """
        return _tree_get_root_impl(repo_path=repo_path)

    @app.tool()
    def tree_get_branch(branch_name: str, repo_path: str | None = None) -> dict:
        """Read one branch .mn (typically bNN) from Muninn's tree.

        Companion to tree_get_root. Use tree_list_branches first if you
        don't know which branches exist in this repo.

        Args:
            branch_name: branch identifier (e.g. "b02", "b07"). Must match
                         the regex ^[A-Za-z0-9_]{1,64}$ — anti path-traversal.
            repo_path: absolute path to a Muninn-bootstrapped project.

        Returns the same shape as tree_get_root, but `metadata` carries
        `usefulness` and `temperature` (no `children`). If the branch is
        absent, returns `{error, available, repo_path, elapsed_ms}` WITHOUT
        raising — so you can recover by listing branches and retrying.

        Read-only: no tree.json or mycelium.db modification.

        Raises:
            ValueError on invalid branch_name (path traversal attempt) or
            on a non-Muninn repo.
        """
        return _tree_get_branch_impl(branch_name=branch_name, repo_path=repo_path)

    @app.tool()
    def tree_list_branches(repo_path: str | None = None) -> dict:
        """List Muninn tree branches sorted by last_access DESC (hot first).

        Returns:
            {
              "branches": [
                {"name": "b02", "lines": 47, "last_access": "2026-05-11",
                 "access_count": 3, "temperature": 0.8, "tags": [...],
                 "children_count": 0},
                ...
              ],
              "count": int,
              "repo_path": str,
              "elapsed_ms": float,
            }

        Excludes "root" (use tree_get_root for that). Read-only.

        Raises:
            ValueError on non-Muninn repo.
        """
        return _tree_list_branches_impl(repo_path=repo_path)

    return app


def main() -> None:
    """Entry point for the `muninn-mcp` console_script and `python -m muninn.mcp`.

    Runs the FastMCP server over stdio (Claude Code spawns the process and
    talks JSON-RPC over stdin/stdout).
    """
    _log.info("Muninn MCP server starting (stdio transport)")
    app = create_server()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
