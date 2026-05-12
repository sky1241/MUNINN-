"""mcp_recall_demo.py — see what Claude Code sees via the MCP server.

Wall-time: ~5s.

The MCP server (`muninn-mcp`) is what Claude Code talks to during generation
to fetch mycelium recall / tree branches / bug context. This script bypasses
the stdio transport and calls the underlying tool functions directly, so you
can see the exact JSON shape Claude Code receives.

Prereqs:
    pip install muninn-memory[mcp]
    cd /your/repo && muninn init && muninn bootstrap .

If you skipped bootstrap, the recall result will be empty (mycelium is empty).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    repo = Path(os.environ.get("MUNINN_DEMO_REPO", ".")).expanduser().resolve()
    if not (repo / ".muninn").exists():
        print(f"No .muninn/ in {repo}.")
        print("Run `muninn init` first, then `muninn bootstrap .` to populate the mycelium.")
        print("Or set $MUNINN_DEMO_REPO to point at an initialized repo.")
        sys.exit(1)

    print(f"Target repo: {repo}\n")

    # Import the MCP server module — it exposes the tool functions
    # (`mycelium_recall_local`, `tree_get_root`, etc.) as Python callables
    # via the `@app.tool()` decorator on a FastMCP instance.
    try:
        from muninn.mcp import server as mcp_server
    except ImportError as exc:
        print("Could not import muninn.mcp.server.")
        print("Install the MCP extras: pip install 'muninn-memory[mcp]'")
        print(f"Original error: {exc}")
        sys.exit(1)

    # The MCP server registers tools on a FastMCP app. The underlying Python
    # callables live in the module namespace with the same name.
    print("─── tree_get_root (the entry point Claude Code reads at session start) ───")
    try:
        root = mcp_server.tree_get_root(repo_path=str(repo))
        # Print a compact preview — first 400 chars of the JSON
        preview = json.dumps(root, indent=2)[:400]
        print(preview + ("..." if len(json.dumps(root)) > 400 else ""))
    except Exception as exc:
        print(f"[err] {type(exc).__name__}: {exc}")

    print("\n─── mycelium_recall_local('compression', scope='auto') ───")
    try:
        recall = mcp_server.mycelium_recall(
            query="compression",
            repo_path=str(repo),
            scope="auto",
            top_k=5,
        )
        print(json.dumps(recall, indent=2)[:600])
    except Exception as exc:
        print(f"[err] {type(exc).__name__}: {exc}")

    print("\n✓ Done. These are the exact responses Claude Code consumes during generation.")


if __name__ == "__main__":
    main()
