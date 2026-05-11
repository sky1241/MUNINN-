# Muninn MCP Setup

> **Status** : chunk B.1 (scaffold + `mycelium_recall_local`) — Phase B in progress.
> See `docs/BATTLE_PLAN_MASTER_MCP.md` for the full roadmap.

Muninn exposes its memory (mycelium, tree, BUGS, runbook) to Claude Code/Desktop as
MCP (Model Context Protocol) tools, callable actively during generation.

## Install

Replace `<PATH_TO_MUNINN>` below with the absolute path where you cloned
Muninn (e.g. `~/Bureau/MUNINN-` on Sky's machine, `/opt/muninn` on a CI box).
Nothing in the runtime hardcodes this — paths are resolved from arguments,
the `MUNINN_REPO` env var, or the current working directory.

```bash
pip install -e "<PATH_TO_MUNINN>[mcp]"
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

Replace `<PATH_TO_YOUR_REPO>` with the absolute path of the project whose
Muninn memory you want exposed to Claude (typically the same repo you ran
`muninn init` in).

Add this stanza to `~/.claude.json` (global) or `<repo>/.mcp.json` (per-project):

```json
{
  "mcpServers": {
    "muninn": {
      "command": "muninn-mcp",
      "args": [],
      "env": {
        "MUNINN_REPO": "<PATH_TO_YOUR_REPO>"
      }
    }
  }
}
```

If `muninn-mcp` is not on `$PATH` (e.g. you installed into a venv that Claude Code
does not source), use the explicit Python path. Find your active interpreter with
`which python` then plug it in:

```json
{
  "mcpServers": {
    "muninn": {
      "command": "<OUTPUT_OF_WHICH_PYTHON>",
      "args": ["-m", "muninn.mcp"],
      "env": {
        "MUNINN_REPO": "<PATH_TO_YOUR_REPO>"
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

## Available tools (B.1 + B.2 + B.3)

| Tool | Args | Returns |
|---|---|---|
| `mycelium_recall_local` (B.1) | `query` (str), `top_k` (int=10), `repo_path`, `hops` (int=2) | `{query, results[{concept,activation,hops}], elapsed_ms, source="local", repo_path}` |
| `mycelium_recall_meta` (B.3) | `query` (str), `top_k` (int=10), `hops` (int=2) | `{query, results, elapsed_ms, source="meta", meta_path, [error?]}` — read-only on `~/.muninn/meta_mycelium.db` |
| `mycelium_recall` (B.3) | `query` (str), `scope` ∈ `auto`\|`local`\|`meta`\|`both` (default `auto`), `top_k`, `hops`, `repo_path` | `{query, scope, results, source, scope_used, fusion_used, strength_local, strength_meta, elapsed_ms, repo_path, meta_path}` |
| `tree_get_root` (B.2) | `repo_path` | `{node="root", content (str .mn), metadata{lines, children, tags, ...}, truncated, repo_path, elapsed_ms}` |
| `tree_get_branch` (B.2) | `branch_name` (str regex `^[A-Za-z0-9_]{1,64}$`), `repo_path` | Same shape as tree_get_root, or `{error, available, repo_path, elapsed_ms}` if branch absent (no raise) |
| `tree_list_branches` (B.2) | `repo_path` | `{branches[{name, lines, last_access, access_count, temperature, tags, children_count}], count, repo_path, elapsed_ms}` sorted by last_access DESC |
| `bugs_list` (B.4) | `repo_path`, `status_filter` (e.g. "OPEN"/"FIXED"/"WONTFIX"), `limit` (default 50) | `{bugs[{id, status, title, line}], count, total, status_filter, truncated, repo_path, elapsed_ms}` |
| `bugs_get` (B.4) | `bug_id` (regex `^BUG-\d{3,4}$`), `repo_path` | `{id, status, title, content, sections{Symptom, Root cause, Fix, Test, Regression}, line, truncated, repo_path, elapsed_ms}` — or `{error, bug_id, available_count, ...}` if absent |

### Tuning the dual-mycelium router (B.3)

`mycelium_recall(scope="auto")` uses a heuristic to decide if it needs to consult the meta-mycelium :

1. Query local mycelium first.
2. Compute `strength_local = sum(activation for each result)`.
3. If `strength_local >= THRESHOLD_LOCAL_STRONG`, return local-only (`scope_used="auto→local"`).
4. Otherwise, also query meta and merge via the configured fusion method (`scope_used="auto→merged"`).

5 env vars expose the defaults (validated by 11 sources : ACT-R, Weaviate, Pinecone, Cormack 2009 RRF, Liu 2024 lost-in-the-middle, Anthropic Contextual Retrieval, BEIR/MTEB) :

| Env var | Default | Source / rationale |
|---|---|---|
| `MUNINN_DUAL_LOCAL_STRONG` | `4.0` | 40 % of theoretical max (top_k=10). Aligns ACT-R log-odds τ=-0.5 → sigmoid 0.38 (Anderson 1983, ACT-R reference manual). FAISS/Qdrant "high confidence" range 0.3–0.7. |
| `MUNINN_DUAL_LOCAL_WEIGHT` | `0.7` | Weaviate hybrid search default α=0.75. Personalization papers (Teevan-Dumais 2005, Bing) bias 0.6–0.7 toward local. |
| `MUNINN_DUAL_META_WEIGHT` | `0.3` | Complement of local weight (sums to 1.0 with default α=0.7). |
| `MUNINN_DUAL_TOP_K` | `10` | NDCG@10 BEIR/MTEB standard. Anthropic Contextual Retrieval (2024) recommends top-20 only when a reranker is in the pipeline; without rerank, top-10 is the sweet spot before lost-in-the-middle (Liu 2024). |
| `MUNINN_DUAL_FUSION` | `linear` | Default = min-max normalize each side onto [0, 1] then `α·local + β·meta`. Alternative `rrf` (Cormack 2009 Reciprocal Rank Fusion) uses ranks only — robust to the ~80× magnitude gap between local (~94 k edges) and meta (~7.5 M edges). |

When to switch to `rrf` : if local and meta have very different score distributions (large repo + tiny local = magnitude bias). RRF ignores raw activations and ranks alone, so it's safer when the two sources are imbalanced.

When to calibrate empirically : `THRESHOLD_LOCAL_STRONG` is the most repo-specific value. Log `strength_local` over 20–30 real queries, recompute the 75th percentile, and set the threshold there.

Example invocations:
> Claude calls `mycelium_recall_local(query="BUG-104 spill tree", top_k=5)`
> → `{"results": [{"concept": "v9a", "activation": 0.87, "hops": 2}, ...], "elapsed_ms": 12.4, ...}`
>
> Claude calls `tree_list_branches()` → discovers `["b03", "b06", "b02", ...]`
>
> Claude calls `tree_get_branch(branch_name="b03")` → reads the bug-recovery branch.

Hard caps: B.1 `1 <= top_k <= 100`, `1 <= hops <= 3` (clamped). B.2 tools cap
content at 60K chars (~15K tokens) with `truncated: True` sentinel.

Fail-safe across all tools: invalid `repo_path` raises `ValueError` with a
user-friendly message; DB lock errors return empty results + error tag; B.2
tools are strictly **read-only** (no `access_count` mutation, no `tree.json`
write, no `mycelium.db` touch — proven by `test_tools_dont_touch_*`).

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
