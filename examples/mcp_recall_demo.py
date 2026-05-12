"""mcp_recall_demo.py — see what Claude Code sees via the MCP server.

Wall-time: ~5s.

The MCP server (`muninn-mcp`) is what Claude Code talks to during generation
to fetch mycelium recall / tree branches / bug context. This script bypasses
the stdio transport and calls the underlying module-level implementation
functions directly (`_tree_get_root_impl`, `_recall_dual_impl`, …), so you
can see the exact JSON shape Claude Code receives.

Prereqs:
    pip install 'muninn-memory[mcp]'
    cd /your/repo && muninn init && muninn bootstrap .

If you skipped bootstrap, the recall result will be empty (mycelium is empty).

Why we call the `_impl` functions and not the `@app.tool()` ones:
    FastMCP registers tool functions as bound methods on the `app` instance
    inside `create_server()`. They are NOT exposed at the module level.
    The `_impl` helpers ARE module-level — they do the real work, the
    `@app.tool()` wrappers are thin MCP-protocol adapters around them.
    Same data, simpler import.
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

    # Import the module-level implementation helpers. These are the real
    # workhorses; the `@app.tool()` decorated versions in create_server()
    # just wrap them for the MCP stdio protocol.
    try:
        from muninn.mcp.server import (
            _tree_get_root_impl,
            _recall_dual_impl,
        )
    except ImportError as exc:
        print("Could not import muninn.mcp.server helpers.")
        print("Install the MCP extras: pip install 'muninn-memory[mcp]'")
        print(f"Original error: {exc}")
        sys.exit(1)

    print("─── _tree_get_root_impl (what Claude Code reads at session start) ───")
    try:
        root = _tree_get_root_impl(repo_path=str(repo))
        preview = json.dumps(root, indent=2)
        print(preview[:600] + ("..." if len(preview) > 600 else ""))
    except Exception as exc:
        print(f"[err] {type(exc).__name__}: {exc}")

    print("\n─── _recall_dual_impl('compression', scope='auto', top_k=5) ───")
    try:
        recall = _recall_dual_impl(
            query="compression",
            scope="auto",
            top_k=5,
            hops=2,
            repo_path=str(repo),
        )
        preview = json.dumps(recall, indent=2)
        print(preview[:800] + ("..." if len(preview) > 800 else ""))
    except Exception as exc:
        print(f"[err] {type(exc).__name__}: {exc}")

    print("\n✓ Done. These are the exact responses Claude Code consumes during generation.")


if __name__ == "__main__":
    main()
