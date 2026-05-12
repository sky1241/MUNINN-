# Muninn Quickstart — Use it on your own repo in 10 steps

> **Audience** : a dev cloning the repo for the first time who wants Claude
> Code to actively use Muninn's memory tools during generation. No prior
> knowledge of the codebase required.
>
> **Tested with** : Python 3.13, Claude Code 1.x, Linux (Debian 12+, Ubuntu 22+).
> macOS works for the local toolchain ; the systemd timer step (Step 8) is
> Linux-only for now (cron fallback planned in a future chunk).
>
> **Time budget** : ~5 minutes if `pip` is already configured. Substitute
> `<PATH_TO_YOUR_REPO>` everywhere with the absolute path of the project you
> want Muninn to remember things about (e.g. `~/code/my-project`). Nothing
> in the runtime hardcodes this — paths resolve from the argument, the
> `MUNINN_REPO` env var, or the current working directory.

---

## 0. 5-second install (from PyPI) — start here if you don't need to hack on Muninn itself

If you just want to *use* Muninn (not modify the engine), the fastest path is :

```bash
pip install 'muninn-memory[all]'    # core + tokens + llm + mcp + quality
muninn                              # prints welcome banner with next 3 steps
cd <PATH_TO_YOUR_REPO>              # any code/text repo you want Muninn to remember
muninn init                         # creates .muninn/, installs Claude Code hooks
muninn doctor                       # 19+ checks, should print "ALL GREEN"
```

That's it. Skip to step 5 (configure Claude Code) if you went this route.

Want to see Muninn in action without configuring Claude Code first? Run :

```bash
python3 -m pip install muninn-memory[all]
# Then clone the repo just for the examples/ scripts:
git clone https://github.com/sky1241/MUNINN-.git muninn-examples
cd muninn-examples/examples && python3 quickstart_local.py
```

The rest of this doc walks through the **editable dev install** (clone +
`pip install -e .`) which is the right path if you plan to modify the
engine, run the test suite, or contribute back. The two paths are
identical after step 5.

---

## 1. Clone the repo (dev path — skip if you used step 0)

```bash
git clone https://github.com/sky1241/MUNINN-.git
cd MUNINN-
```

You'll need this checkout for the next two steps (editable install + MCP server).

## 2. Install with optional extras

```bash
pip install -e ".[mcp,tokens]"
```

- `[mcp]` adds the Model Context Protocol server (so Claude can call Muninn
  tools during generation).
- `[tokens]` adds `tiktoken` — required by `muninn doctor` to pass
  ALL GREEN. Skip it only if you have a strong reason to count tokens
  yourself.

Verify :

```bash
muninn --version    # should print "muninn 0.9.x"
muninn-mcp --help   # entry point installed by pip
```

## 3. Initialize Muninn on YOUR project

```bash
cd <PATH_TO_YOUR_REPO>
muninn init
```

This creates `.muninn/` (gitignored), scaffolds `tree.json`, registers
the repo in `~/.muninn/repos.json`, and writes 7 Claude Code hooks into
`.claude/settings.local.json`. Idempotent — safe to re-run.

## 4. Run the health check

```bash
muninn doctor
```

Expected output ends with **`ALL GREEN — N checks passed`**. If `tiktoken`
shows `FAIL`, re-install with `[tokens]` from step 2.

WARN-level lines (e.g. `cryptography not installed`) are fine — they only
affect optional features (vault encryption, L9 LLM compression).

## 5. Run your first bootstrap

```bash
muninn bootstrap .
```

This scans your repo, builds the mycelium graph from your code & docs,
and writes `.muninn/mycelium.db`. Time depends on repo size — typically
30s to 5min. Re-run after big refactors.

## 6. Wire the MCP server into Claude Code

Add this stanza to `~/.claude.json` (global) or `<PATH_TO_YOUR_REPO>/.mcp.json`
(per-project). Replace `<PATH_TO_YOUR_REPO>` with your actual path :

```json
{
  "mcpServers": {
    "muninn": {
      "command": "muninn-mcp",
      "env": {
        "MUNINN_REPO": "<PATH_TO_YOUR_REPO>"
      }
    }
  }
}
```

If `muninn-mcp` isn't on `$PATH` (typical with isolated venvs), use the
explicit Python path. Find it with `which python` then plug it in :

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

## 7. Verify Claude Code sees the server

In a fresh Claude Code session :

```bash
claude mcp list
```

You should see `muninn   running   10 tools`. If not, check
`~/Library/Logs/Claude/mcp*.log` (macOS) or `~/.cache/claude/mcp*.log`
(Linux) — the MCP server logs to stderr.

## 8. (Linux only) Install the weekly prune timer

```bash
cd <PATH_TO_YOUR_REPO>
muninn install-cron
```

This creates `~/.config/systemd/user/muninn-prune.{service,timer}` that
runs `muninn prune` every Sunday at 04:00 local time, with `Persistent=true`
so a missed run (machine off) catches up at next boot. Then activate :

```bash
systemctl --user daemon-reload
systemctl --user enable --now muninn-prune.timer
systemctl --user list-timers | grep muninn   # confirm next-run time
```

To remove later : `muninn install-cron --uninstall`. The hook is opt-in :
nothing in this step is auto-triggered.

## 9. First Claude session — verify the boot context

Open a new Claude Code session in `<PATH_TO_YOUR_REPO>` and ask :

> "What do you already know about this project without reading any file?"

If Step 3-5 ran correctly, Claude will respond with project-specific
context : top files, mycelium-derived concepts, recent commits — pulled
from `.muninn/tree/root.mn` by the `SessionStart` hook. You can verify
the same content with :

```bash
cat .muninn/tree/root.mn   # what the SessionStart hook injects
```

## 10. When to call which MCP tool

Claude can call any of these 10 tools mid-generation. Cheatsheet :

| Tool | Use case |
|---|---|
| `mycelium_recall_local(query, top_k=10)` | "What concepts are related to X in THIS repo?" |
| `mycelium_recall_meta(query, top_k=10)` | "What concepts are related to X across ALL my repos?" |
| `mycelium_recall(query, scope="auto")` | "Use both, pick whichever has signal" — auto-calibrates per repo (chunk C.0). |
| `tree_get_root(repo_path=None)` | "Show me the root.mn snapshot of this project." |
| `tree_get_branch("b03", repo_path=None)` | "Read branch b03 in full." |
| `tree_list_branches(repo_path=None)` | "Which branches exist? Sorted by recency." |
| `bugs_list(status_filter="OPEN", limit=20)` | "What bugs are open right now?" |
| `bugs_get("BUG-111", repo_path=None)` | "Read the full BUG-111 entry." |
| `runbook_list_sections("changelog")` | "What sections does the CHANGELOG have?" |
| `runbook_get("changelog", "2026-05-11-soir")` | "Read the CHANGELOG section for tonight." |

All read-only. None mutate `mycelium.db`, `tree.json`, `BUGS.md`, or any
runbook file (proven by test pins `test_tools_dont_touch_*`).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `muninn doctor` says `tiktoken FAIL` | `pip install -e ".[mcp,tokens]"` — `[tokens]` is the key extra |
| `claude mcp list` shows `muninn   failed` | Run `muninn-mcp` manually in a terminal, watch stderr for the import error. Most common : `[mcp]` extra missing. |
| Tools return empty `results` array | Mycelium has no signal for that query. Try `bootstrap` if you haven't, or expand the query. The auto-calibration (`MUNINN_DUAL_AUTO_CALIBRATE`) will adjust the local-strength threshold automatically after ~30 calls. |
| Tree `root.mn` content looks wrong | Re-run `muninn bootstrap <PATH_TO_YOUR_REPO>` to rebuild the tree from scratch. Existing branches `b01..bNN` are preserved. |
| `muninn install-cron` says `skipped_no_systemd` | systemctl not on PATH — typical in containers / WSL2 / macOS. The cron fallback is planned but not yet implemented. |

For deeper config (auto-calibration thresholds, RRF fusion, dual-mycelium
routing), see [`docs/MCP_SETUP.md`](MCP_SETUP.md).

For internals, see [`docs/BATTLE_PLAN_MASTER_MCP.md`](BATTLE_PLAN_MASTER_MCP.md)
(roadmap & methodology) and [`README.md`](../README.md) §Architecture.

For known issues, see [`BUGS.md`](../BUGS.md). All bugs are FIXED at the
time of writing — but check `bugs_list(status_filter="OPEN")` from Claude
to be sure.
