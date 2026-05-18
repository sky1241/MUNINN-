# Pipeline Trace — Removal Manifest

> **Status**: TEMPORARY observability scaffolding. This whole apparatus
> exists to let Claude `tail -f .muninn/pipeline_trace.jsonl` while Sky
> performs actions, so we can map what *actually* executes vs what the
> docs promise (see `docs/PIPELINE_MAP.md`).
>
> **Removal**: when the audit is over, this file is the contract for
> getting the codebase back to clean. Every chunk below has a `git revert`
> hash and a sed-based purge command. Run either path.

## Sentinel convention

Every line added by this campaign ends with the trailing comment
`  # PIPELINE_TRACE`. That is how we grep them all back:

```bash
grep -rln "# PIPELINE_TRACE" --include="*.py"
```

The infra file itself (`engine/core/pipeline_trace.py`) does NOT carry
the marker line-by-line because the whole file is the marker — it gets
deleted as one unit.

## Per-chunk manifest

| Chunk | Commit hash | Files touched | Lines added | Revert |
|---|---|---|---|---|
| 0 | `2bcd3c4` + CI-fix (this commit) | `engine/core/pipeline_trace.py` (NEW, ~140L) + `docs/PIPELINE_TRACE_REMOVAL.md` (NEW, this file) + 2 whitelist entries in `tests/test_h0_no_orphan.py` + `tests/test_chunk_d11_shim_drift.py` | ~195 | `git revert` both chunk-0 commits |
| 1 | _pending_ | 9 hooks in `.claude/hooks/` (session_start, bridge, subagent_start, post_tool_failure, post_tool_use_edit_log, pre_tool_use_bash_destructive, pre_tool_use_bash_secrets, pre_tool_use_edit_hardcode, pre_tool_use_task_throttle) + regenerated `.claude/hooks/hooks.sha256sum` | ~150 (9×~8 import block + ~25 call sites) | `git revert <hash>` |
| 2 | _pending_ | `engine/core/muninn_tree.py` (`bridge_fast` +5 events, `recall` +7 events) + 7-line import block + new `tests/test_props_muninn_tree.py` (14 forge props, generated, kept) | ~25 | `git revert <hash>` |
| 3 | _pending_ | `engine/core/muninn_feed.py` (`feed_from_hook`, `feed_from_stop_hook`) | _TBD_ | `git revert <hash>` |
| 4 | _pending_ | engine downstream (compress, grow, refresh, prune, sleep_consolidate, sync) | _TBD_ | `git revert <hash>` |
| 5 | _pending_ | `engine/core/mycelium.py`, `engine/core/mycelium_activation.py` | _TBD_ | `git revert <hash>` |
| 6 | _pending_ | `engine/core/muninn.py` (32 CLI subcommands) | _TBD_ | `git revert <hash>` |
| 7 | _pending_ | `muninn/ui/*.py` (main_window, cube_live, tree_view, search, command_palette, terminal, navi) | _TBD_ | `git revert <hash>` |
| 8 | _pending_ | `muninn/mcp/server.py` (10 `_*_impl`) | _TBD_ | `git revert <hash>` |
| 9 | _pending_ | sandbox `Dockerfile`, `entrypoint.sh`, `run.sh` (NOT in repo) | _TBD_ | `git revert <hash>` |
| 10 | n/a | (verification, no code) | 0 | n/a |

Each row is updated in the same commit that creates the chunk — the
commit hash, file count, and line delta are written as part of the chunk
itself. Forge runs that follow engine touches are documented in their
commit messages.

## Full removal — global recipe

**Path A — git revert (cleanest, preserves history):**

```bash
# Run from repo root, in reverse chunk order.
# Read the table above to get the commit hashes.
git revert --no-edit <chunk 10 hash>  # n/a (no commit)
git revert --no-edit <chunk 9 hash>
git revert --no-edit <chunk 8 hash>
git revert --no-edit <chunk 7 hash>
git revert --no-edit <chunk 6 hash>
git revert --no-edit <chunk 5 hash>
git revert --no-edit <chunk 4 hash>
git revert --no-edit <chunk 3 hash>
git revert --no-edit <chunk 2 hash>
git revert --no-edit <chunk 1 hash>
git revert --no-edit <chunk 0 hash>
git push
```

**Path B — sed purge (faster, rewrites no history):**

```bash
# 1. List every file that carries the sentinel.
grep -rln "# PIPELINE_TRACE" --include="*.py" .

# 2. Strip the sentinel lines in-place from each file.
grep -rln "# PIPELINE_TRACE" --include="*.py" . | xargs sed -i '/# PIPELINE_TRACE/d'

# 3. Delete the infra + this manifest.
rm engine/core/pipeline_trace.py docs/PIPELINE_TRACE_REMOVAL.md

# 4. Delete the trace artifact (gitignored, but the local file lingers).
rm -f .muninn/pipeline_trace.jsonl

# 5. Verify nothing imports the gone module.
grep -rn "pipeline_trace\|log_event" --include="*.py" . | grep -v '^Binary'
# (expected output: empty)

# 6. One commit to record the cleanup.
git add -A && git commit -m "chore: remove pipeline_trace instrumentation"
git push
```

**Path C — sandbox-only removal (the Docker bump in chunk 9):**

The sandbox files live in `/home/sky/Bureau/muninn-sandbox/` and are
NOT in this repo. Revert that chunk separately by hand-editing
`Dockerfile`, `entrypoint.sh`, `run.sh` back to the snapshot recorded
in the chunk 9 commit message.

## Performance budget

The hot-path constraint is the `UserPromptSubmit` bridge hook, capped at
~500ms by Claude Code. `log_event(...)` must therefore stay under ~1ms
per call to leave room for the actual bridge work. Measurement command:

```bash
python -m engine.core.pipeline_trace
```

prints `avg_us / p50_us / p99_us` from 1000 self-bench calls. The chunk
0 commit message records the numbers from the machine that built it.

## What this file is NOT

- It is not user-facing documentation. It is operational.
- It does not document the events themselves. For the event catalog,
  read the chunk commit messages and `docs/PIPELINE_MAP.md`.
- It does not promise that the instrumentation captures every code path
  — only the ones listed per chunk. New blind spots discovered during
  observation get added as new chunks, never silently.
