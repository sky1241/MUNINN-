# Muninn MCP Setup

> **Status** : chunk B.1 (scaffold + `mycelium_recall_local`) — Phase B in progress.
> See `docs/BATTLE_PLAN_MASTER_MCP.md` for the full roadmap.

Muninn exposes its memory (mycelium, tree, BUGS, runbook) to Claude Code/Desktop as
MCP (Model Context Protocol) tools, callable actively during generation.

## Install

```bash
pip install -e "/home/sky/Bureau/MUNINN-[mcp]"
# or once on PyPI:
pip install "muninn-memory[mcp]"
```

Then verify the server starts:

```bash
muninn-mcp &
# Or:
python -m muninn.mcp &
# Hit Ctrl-C to stop. Logs go to stderr.
```

## Wire it into Claude Code

Add this stanza to `~/.claude.json` (global) or `<repo>/.mcp.json` (per-project):

```json
{
  "mcpServers": {
    "muninn": {
      "command": "muninn-mcp",
      "args": [],
      "env": {
        "MUNINN_REPO": "/home/sky/Bureau/MUNINN-"
      }
    }
  }
}
```

If `muninn-mcp` is not on `$PATH` (e.g. you installed into a venv that Claude Code
does not source), use the explicit Python path:

```json
{
  "mcpServers": {
    "muninn": {
      "command": "/home/sky/.pyenv/versions/3.13.13/bin/python",
      "args": ["-m", "muninn.mcp"],
      "env": {
        "MUNINN_REPO": "/home/sky/Bureau/MUNINN-"
      }
    }
  }
}
```

Verify Claude Code sees the server:

```bash
claude mcp list
# Expected:  muninn  running
```

## Available tools (B.1)

| Tool | Args | Returns |
|---|---|---|
| `mycelium_recall_local` | `query` (str), `top_k` (int=10), `repo_path` (str=$MUNINN_REPO\|cwd), `hops` (int=2) | `{query, results[{concept,activation,hops}], elapsed_ms, source="local", repo_path}` |

Example invocation (from Claude during a session):
> Claude calls `mycelium_recall_local(query="BUG-104 spill tree", top_k=5)`
> → `{"results": [{"concept": "v9a", "activation": 0.87, "hops": 2}, ...], "elapsed_ms": 12.4, ...}`

Hard caps: `1 <= top_k <= 100`, `1 <= hops <= 3` (clamped silently).
Fail-safe: invalid `repo_path` raises `ValueError` with a user-friendly message ;
DB lock errors return an empty `results` list with `error: "db_unavailable"`.

## Coming next (Phase B roadmap)

- **B.2** : tool `tree_get_root` + `tree_get_branch` (3-5h)
- **B.3** : add `mycelium_recall_meta` + `mycelium_recall(scope="auto")` with smart
  routing between local and meta-mycelium (8h — spec gravée dans MASTER §B "Dual-
  mycelium routing")
- **B.4** : `bugs_list` + `bugs_get` (read-only access to BUGS.md) (6h)
- **B.5** : `runbook_get` (read CHANGELOG/WINTER/BATTLE_PLAN snippets) (6h)

See `docs/BATTLE_PLAN_MASTER_MCP.md` §Phase B for the full spec.

## Troubleshooting

- **`Module not found: mcp`** → `pip install 'muninn-memory[mcp]'` (the extras are NOT
  installed by default to keep the base Muninn lightweight).
- **Server starts but Claude Code shows no tools** → check `claude mcp list` ;
  if it shows `failed`, run the server manually (`muninn-mcp`) and watch stderr —
  any import error will surface there.
- **Output corrupted in Claude** → never `print()` to stdout in MCP tools — that
  pollutes the JSON-RPC wire. Use `logging.getLogger("muninn.mcp").info(...)`
  which writes to stderr.
- **Tests** : `pytest tests/test_chunk_mcp_b1_server_scaffold.py -v` should show
  10 PASS (9 unit + 1 stdio smoke).
