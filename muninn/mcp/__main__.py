"""Run the Muninn MCP server: `python -m muninn.mcp`.

Equivalent to the `muninn-mcp` console_script entry point.
"""
from muninn.mcp.server import main

if __name__ == "__main__":
    main()
