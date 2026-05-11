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


def create_server() -> FastMCP:
    """Build the Muninn FastMCP app and register the chunk-B.1 tools.

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
