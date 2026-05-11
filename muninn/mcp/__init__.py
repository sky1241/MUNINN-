"""Muninn MCP (Model Context Protocol) integration.

Exposes Muninn data (mycelium, tree, BUGS, runbook) to Claude Code/Desktop
as MCP tools, callable actively during generation. Chunk B.1 of
docs/BATTLE_PLAN_MASTER_MCP.md.

Default transport: stdio (spawned by Claude Code).
Entry points: `muninn-mcp` (console_script) and `python -m muninn.mcp`.
"""
from muninn.mcp.server import create_server, main

__all__ = ["create_server", "main"]
