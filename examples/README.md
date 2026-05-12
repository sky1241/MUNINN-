# Muninn — examples gallery

Runnable scripts to see Muninn in action without reading the source.
Assumes you ran `pip install muninn-memory[all]` already.

| Script | What it shows | When to read it |
|---|---|---|
| [quickstart_local.py](quickstart_local.py) | Bootstrap Muninn on a fresh repo, observe a transcript, query the mycelium back. Pure local, no MCP, no API key. | First example to run. ~30s wall-time. |
| [mcp_recall_demo.py](mcp_recall_demo.py) | Call the MCP tools (`mycelium_recall_local`, `tree_get_root`) from a Python client, the way Claude Code calls them during generation. | When you want to see what the MCP server actually returns. |

## Run order

```bash
# 1. Install (skip if already done)
pip install muninn-memory[all]

# 2. Pick a target repo (any directory with some Python/code files)
export MUNINN_DEMO_REPO=~/code/my-project   # or /tmp/some-dir, whatever

# 3. Run the local quickstart
python3 quickstart_local.py

# 4. Try the MCP-style recall
python3 mcp_recall_demo.py
```

## What to expect

`quickstart_local.py` prints :
- The `.muninn/` layout it created (tree.json, mycelium.db, sessions/)
- The 5 most-activated concepts after feeding a sample transcript
- A recall query result for the seed "compression"

`mcp_recall_demo.py` prints the JSON shape of each MCP tool response (the same shape Claude Code sees during generation).

## Troubleshooting

If a script crashes with `ModuleNotFoundError`, run :

```bash
muninn doctor
```

It will tell you which optional extra is missing (`[mcp]`, `[llm]`, `[tokens]`).

## Related docs

- [QUICKSTART.md](../docs/QUICKSTART.md) — full 10-step setup for Claude Code integration
- [MCP_SETUP.md](../docs/MCP_SETUP.md) — MCP tool catalog + tuning env vars
- [README.md](../README.md) — project overview
