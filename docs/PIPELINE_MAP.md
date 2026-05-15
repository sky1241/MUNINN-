# MUNINN — Pipeline Map

> **Status**: v1 in-progress (2026-05-15). Incremental — sections added as
> Claude reads the code. Each section cites `file:line` for every claim.
>
> **Why this doc exists**: Sky sensed "leaks" in the pipeline (features
> claimed wired but not actually called at runtime, or doing something
> different from what the docs promised). This is the read-only audit of
> what *actually* happens during each user action, sourced from the code
> as of 2026-05-15.

---

## Action 1 — SessionStart boot (when a new Claude session opens in the repo)

**Entry point**: `.claude/hooks/session_start_hook.py`

**Trigger**: Claude Code emits a `SessionStart` event with payload
`{hook_event_name, session_id, source, cwd}` on stdin.

**Call chain** (verbatim from the code):

```
Claude Code SessionStart event
  └── .claude/hooks/session_start_hook.py:main()       [line 136]
        ├── reads stdin payload                         [line 138]
        ├── filters source ∈ {startup, resume}          [line 170]
        │   (skips "clear" and "compact" — exits empty)
        ├── _find_tree_dir(repo_path)                  [line 186 → 86]
        │   └── checks repo_path/.muninn/tree
        │       (fallback: repo_path/memory)
        ├── _read_root(tree_dir)                       [line 192 → 98]
        │   └── reads .muninn/tree/root.mn
        ├── _find_recent_branches(tree_dir, n=5)       [line 193 → 109]
        │   └── glob *.mn (excluding root.mn)
        │       sort by st_mtime desc                   [line 126]
        │       take top 5
        ├── concat into "[MUNINN SESSION BOOT]\n
        │                 === root.mn ===\n...
        │                 === branch: X ===\n..."       [line 199-212]
        ├── _truncate_with_marker(..., MAX=40000)      [line 213 → 69]
        └── prints JSON {"hookSpecificOutput":
              {"hookEventName": "SessionStart",
               "additionalContext": <injected>}}        [line 215]
```

**What the hook does NOT do** (explicit per docstring line 18):
- ❌ No engine import (no Python import of `muninn.*` or `engine.core.*`)
- ❌ No subprocess (no call to `muninn-mem` binary)
- ❌ No mycelium queries (no `m.spread_activation`, no `m.get_related`)
- ❌ No relevance scoring (the "hot" proxy is just `st_mtime`, ie. the
  most-recently-modified files — NOT the most semantically relevant
  to whatever Claude is about to be asked)

**Performance target**: <500ms (per docstring line 19).

**Output to Claude**: at most 40 000 characters (~10K tokens) injected
as `additionalContext`.

**Practical implication / observed drift**:
- If yesterday you worked on B42 wiring → `.mn` files for that area
  have the most recent mtime → Claude boots today with B42 context.
- If today you intend to switch to COBOL scanning → Claude has no idea
  unless you tell it in your first message.
- The "hot memory by mtime" proxy fails for **topic switches between
  sessions**.
- The promise of "boot loads branches *pertinent* to the query" in
  `CLAUDE.md` (root MUNINN doc) is NOT implemented at SessionStart —
  it would require knowing the query, which doesn't exist yet at boot.
  Mycelium-driven selection happens later in `bridge_hook.py` (mid-
  session UserPromptSubmit), not here.

**No drift on the basic mechanism**: root.mn + 5 recent branches IS
injected, the 40K cap IS enforced, the format IS as expected. The
"leak" is in the *selection heuristic* (mtime instead of mycelium
spread_activation), which is a known design choice for the LIGHT
MODE hook, but means the boot context is less "smart" than the
project name suggests.

---

## Action 2 — UserPromptSubmit bridge (mid-session, each Sky message)

**Entry point**: `.claude/hooks/bridge_hook.py`

**Trigger**: Claude Code emits a `UserPromptSubmit` event with payload
`{prompt, cwd, ...}` every time Sky sends a message during a session.

**Call chain** (verbatim from the code):

```
Claude Code UserPromptSubmit event
  └── .claude/hooks/bridge_hook.py:main()              [line 70]
        ├── reads stdin JSON, extracts prompt           [line 81]
        ├── skip if prompt empty or <10 chars           [line 82]
        ├── _check_secrets(prompt)                      [line 89 → 42]
        │   ├── matches GitHub/OpenAI/AWS/Bearer regex patterns
        │   ├── if trigger word + high-entropy nearby word → WARN
        │   └── if any standalone >=10char high-entropy string → WARN
        │   (warning goes to STDERR, not stdout — line 91-92)
        ├── sets muninn._REPO_PATH = cwd                [line 104]
        ├── muninn._refresh_tree_paths()                [line 105]
        ├── muninn.bridge_fast(prompt)                  [line 106]
        │   ↓
        │   engine/core/muninn_tree.py:bridge_fast()    [line 1511]
        │     ├── regex extract: [A-Za-zÀ-ɏ]{4,} lowercase  [line 1522]
        │     ├── filter 68 hardcoded stopwords (32 EN + 36 FR)        [line 1523-1536]
        │     ├── take FIRST 5 concepts only (concepts[:5])           [line 1573]
        │     ├── for each seed: m.get_related(seed, top_n=5)         [line 1574]
        │     │     ↑ **NOT spread_activation()** — see drift note below
        │     ├── format "[MYCELIUM BRIDGE]\n  seed -> n1, n2, ..."   [line 1582-1585]
        │     └── _secrets.clamp_chained_commands(output)              [line 1597]
        ├── _secrets.clamp_chained_commands(result)     [line 112-113]
        └── print(result)                                [line 116]
                ↑ becomes additionalContext for Claude
```

**Performance target**: <0.5s total (per docstring line 8).

**Mycelium reads**: yes, `m.get_related()` (direct neighbors, 1-hop).
**Mycelium writes**: **NO**. Comment line 1587-1588:
> *"Skip observe+save in fast path — too slow for hooks. The full
> bridge() or feed hooks handle persistence."*

**Drift #2 — promise vs reality**:

The CLAUDE.md root doc and `mycelium.py:89` mention **Spreading Activation
(Collins & Loftus 1975)** as a core feature: a multi-hop BFS that
propagates activation through the graph, finds *related* concepts
(not just direct neighbors), and ranks them by accumulated activation
across paths.

`bridge_fast()` explicitly does NOT use this. The comment lines 1514-1515
say:
> *"Uses get_related() (direct neighbors) instead of spread_activation()
> (full graph traversal). 300x faster on large myceliums."*

So in production, what Claude receives mid-session per message is:
- max 5 seed concepts (the first 5 long-enough words from your prompt)
- max 5 direct neighbors per seed (1-hop, weighted by edge weight)
- max ~25 concept pairs total injected as `[MYCELIUM BRIDGE]\n...`

NOT a multi-hop semantic activation. The full `spread_activation()`
exists in `mycelium_activation.py:386-501` and IS called from
`muninn_tree_boot.py:358` and `muninn/mcp/server.py:300`, but NOT from
this hot path. So 99% of the "live mycelium injection" you see during
sessions is actually 1-hop neighbors.

**Drift #3 — observe-on-prompt missing**:

The bridge hook does NOT feed the user's prompt back into the mycelium
(`observe+save` is explicitly skipped, line 1587-1588 of bridge_fast).
That means concepts Sky types live during a session are NOT learned
by the mycelium until the next PreCompact or SessionEnd hook fires.
If those hooks fail or are skipped, a session's vocabulary is lost.

---

## Action 3 — PreCompact / SessionEnd / Stop (where mycelium actually learns)

**Entry point**: NOT a `.claude/hooks/*.py` file. Wired DIRECTLY in
`.claude/settings.json` to a subprocess invocation:
- `PreCompact` → `python engine/core/muninn.py feed --repo ${CLAUDE_PROJECT_DIR}` (timeout 180s)
- `SessionEnd` → idem (timeout 180s)
- `Stop` → `python ... feed --repo ... --trigger stop` (timeout 120s)

**Dispatch**: `engine/core/muninn.py:1244` (`args.command == "feed"`)
- Default (no `--trigger`): calls `feed_from_hook(repo)` → `engine/core/muninn_feed.py:1340`
- `--trigger stop`: calls `feed_from_stop_hook(repo)` → `engine/core/muninn_feed.py:1473`

**Call chain for PreCompact/SessionEnd** (verbatim from
`muninn_feed.py:1340-1469`):

```
Claude Code PreCompact or SessionEnd event
  └── subprocess: muninn.py feed --repo $REPO     [settings.json]
        └── feed_from_hook(repo_path)              [muninn_feed.py:1340]
              ├── reads JSON from stdin (transcript_path)        [line 1348]
              ├── _validate_transcript_path(jsonl_path)          [line 1362]
              │   (refuse anything outside ~/.claude/projects/ — CHUNK A4)
              ├── _MuninnLock(repo_path, "hook", timeout=120)    [line 1374]
              │   (prevents race with concurrent Stop hook)
              │
              ├── 1. _update_usefulness(repo_path, jsonl_path)   [line 1376]
              │     (P36: refresh tree node usefulness scores)
              │
              ├── 2. feed_from_transcript(jsonl_path, repo_path) [line 1379]
              │     ↓ this is where mycelium learns
              │     reads transcript .jsonl
              │     extracts texts from messages
              │     for each text: mycelium.observe_text(text)
              │     ↑ here is the REAL learning step
              │     returns (count, parsed_texts)
              │
              ├── 3. compress_transcript(jsonl_path, repo_path)  [line 1383]
              │     ↓ applies L0..L11 layers to the transcript
              │     writes .muninn/sessions/<session_id>.mn
              │     returns (mn_path, session_sentiment)
              │
              ├── 4. grow_branches_from_session(mn_path, ...)    [line 1388]
              │     (Brique 3 — auto-segment .mn into branches)
              │     (V6B — valence-modulated decay using sentiment)
              │
              ├── 5. load_tree → refresh_tree_metadata → save    [line 1391-1393]
              │     (update temperatures, hot/cold)
              │
              ├── 6. if branch_count > 150: _light_prune()       [line 1398-1400]
              │     (kills dead + dust branches only)
              │
              └── 7. _register_repo(repo_path)                   [line 1403]
                    (cross-repo meta discovery)

  IN finally (always runs, even on crash):
        ├── 8. m.decay()                                          [line 1421]
        │     ↑ ONLY if hook_event == "SessionEnd" (not PreCompact!)
        │     uses self.DECAY_HALF_LIFE = 30 days HARDCODED
        │     (NOT adaptive_decay_half_life() — see drift below)
        │
        ├── 9. _sleep_consolidate(cold_branches, nodes)          [line 1451]
        │     (merge cold branches with Ebbinghaus recall < 0.15)
        │     ONLY runs on SessionEnd (same condition as decay)
        │     (CHUNK EX5 fix 2026-05-08: was functionally DEAD before
        │      — iterating dict keys instead of .items() — Sky's
        │      "Sleep Consolidation Wilson & McNaughton 1994" promise
        │      was dead for some time before this fix)
        │
        └── 10. _sync_to_meta_guarded(repo, hook_event)          [line 1463]
              (push new edges to ~/.muninn/meta_mycelium.db)
              (with timeout, opt-out via MUNINN_SKIP_META_SYNC=1)
```

**Trigger condition matrix** (which steps run when):

| Step                          | PreCompact | SessionEnd | Stop |
|-------------------------------|------------|------------|------|
| feed_from_transcript          | ✅         | ✅         | ✅* |
| compress_transcript           | ✅         | ✅         | ✅* |
| grow_branches_from_session    | ✅         | ✅         | ✅* |
| refresh_tree_metadata         | ✅         | ✅         | ✅* |
| light_prune (if > 150 branch) | ✅         | ✅         | ✅* |
| `m.decay()` (30-day half-life)| ❌         | ✅         | ❌  |
| _sleep_consolidate            | ❌         | ✅         | ❌  |
| _sync_to_meta_guarded         | ✅         | ✅         | ✅  |

*Stop hook uses a different code path (`feed_from_stop_hook`) — same
intent, debounced execution. Not fully verified in this section.

**Drift #4 — `m.decay()` uses HARDCODED 30 days, not adaptive**:

Line 1421 calls `m.decay()` with NO argument. In `mycelium.py:1004`,
the default is `days = self.DECAY_HALF_LIFE` which is `30` (class
constant `mycelium.py:74`).

The function `adaptive_decay_half_life()` exists at `mycelium.py:1141`
and computes a smarter value based on `sessions_per_day` (15 days for
very active repos like Sky's, 60 days for inactive). **This function
is never called by `decay()`**. `grep -rn "adaptive_decay_half_life"`
returns only the definition and the test we fixed today.

So Sky's repo (very active, 850 commits in 73 days) is decaying old
edges at the same rate as a low-traffic repo. The "A2 adapts" comment
on line 74 of mycelium.py is aspirational, not wired.

**Drift #5 — Sleep Consolidation was DEAD until recently**:

The CHUNK EX5 fix dated 2026-05-08 (line 1429-1436 comment) reveals
that for some time prior, `_sleep_consolidate` was never invoked
because of a bug iterating over dict keys (strings) instead of
`.items()` (tuples). The check `isinstance(str, dict)` was always
False, so `cold` was always `[]`, so consolidation never ran.

This means the "Sleep Consolidation (Wilson & McNaughton 1994)"
feature advertised in MUNINN's CLAUDE.md was a no-op for an unknown
period before 2026-05-08. The current code path is fixed but the
prior `mycelium.db` state for the period before that date may have
accumulated cold branches that should have been merged but weren't.

**Drift #6 — Stop hook may run a different code path**:

`feed_from_stop_hook` at `muninn_feed.py:1473` is a separate function.
Same broad intent (feed mycelium + compress) but I haven't read it in
detail in this audit. Mark as `?` — could be a drift between PreCompact
behavior and Stop behavior. Worth a focused read in step 2 of the
observability plan.

---

## Action 4 — `muninn-mem recall "<query>"` (CLI mid-session memory search)

**Entry point**: `engine/core/muninn.py:1306` (`args.command == "recall"`)
- calls `recall(args.file)` (where `args.file` = the query string)
- `recall()` is defined in `engine/core/muninn_tree.py:1234`

**Call chain** (verbatim from `muninn_tree.py:1234-1328`):

```
muninn-mem recall "<query>"
  └── muninn.py:1306-1317 dispatch
        └── recall(query)                              [muninn_tree.py:1234]
              ├── extract query_words = re [A-Za-z]{4,}  [line 1241]
              │   (4+ chars only, lowercase; NO stopword filter here)
              │
              ├── 1. Search session_index.json          [line 1247-1267]
              │     for each entry:
              │       overlap = |query_words ∩ entry.concepts|
              │       if overlap > 0: add tagged lines + session marker
              │
              ├── 2. Grep top 10 most-recent .mn        [line 1269-1285]
              │     in .muninn/sessions/*.mn (sorted reverse)
              │     for each line: keep if |query ∩ line_words| >= 2
              │
              ├── 3. Grep ALL tree branches             [line 1287-1305]
              │     in .muninn/tree/*.mn (skip root.mn)
              │     same overlap >= 2 threshold
              │     also: matched_branches.add(...)
              │
              ├── 4. _surface_known_errors(repo, query) [line 1308]
              │     (searches error/fix memory log)
              │
              ├── 5. P37 warmup of matched branches     [line 1316-1328]
              │     (increment access_count, update last_access,
              │      append to access_history[-10:])
              │
              └── return formatted top-N matches
```

**Drift #7 — `recall()` does NOT use the mycelium graph at all**:

The function name and docstring ("mid-session memory search") strongly
suggest semantic recall using the co-occurrence graph. In reality,
recall is **plain text search via bag-of-words overlap**:
- query is tokenized to 4+ char lowercase words
- each line of each `.mn` file is tokenized the same way
- a line "matches" if overlap ≥ 2 words

No call to `m.get_related()`, no `spread_activation()`, no concept
expansion. If you query *"COBOL legacy banking"*, the function finds
lines that literally contain ≥2 of those exact tokens (after the
4+ char filter — so "COBOL"=ok, "of"=skipped).

Concepts that the mycelium *learned* are related (e.g. "COBOL" co-
occurs with "mainframe" in your fed transcripts) are NEVER expanded
into the recall. Result: recall misses contextually relevant content
unless it shares literal word overlap.

This explains why your test query *"comment marche le bootstrap"*
earlier in this session returned only 1 match (branch `b86` because
it contains the literal string *"Comment ca marche"*). Plenty of
mycelium content about bootstrap concepts exists; the recall mechanism
just can't see it.

**Drift #8 — no stopword filter in recall**:

Unlike `bridge_fast()` (which has 68 hardcoded stopwords), `recall()`
filters only by length (≥4 chars). So words like `"have"`, `"this"`,
`"that"`, `"with"` count toward the overlap threshold. A query like
*"have you seen this"* matches almost any English line because of
common-word overlap. The result is noise (4 words >= 2 threshold = false
matches on stopword overlap).

---

## Action 5 — Cube live UX flow (muninn-ui desktop app)

(Skipped detailed walkthrough — `muninn/ui/cube_live.py` is 304L,
`muninn/ui/main_window.py` is 626L, `muninn/ui/_tree_engine.py`
is 4559L. A faithful walkthrough deserves its own dedicated session.
What's verified so far via grep:

- `muninn/ui/cube_live.py:277` calls `reconstruct_adaptive` (B43)
- B40 `reconstruct_cube_waves` is called BY B43 internally
  (`engine/core/cube_providers.py:1888, 2086`)
- B42 `reconstruct_line_by_line` is NEVER called outside of tests —
  see Phase L plan section L0 for details, and Action 5 follow-up
  in a future session.)

---

## Summary of drifts identified so far

| # | Where | Promise | Reality |
|---|-------|---------|---------|
| 1 | SessionStart hook | "loads pertinent branches" | loads 5 most-recent-mtime branches |
| 2 | UserPromptSubmit bridge | "spreading activation Collins & Loftus" | 1-hop `get_related()` only — 300× faster but no multi-hop |
| 3 | UserPromptSubmit bridge | "live learning from prompts" | explicitly skips observe+save — mycelium learns only at PreCompact/SessionEnd |
| 4 | PreCompact/SessionEnd | "adaptive decay (A2)" | `m.decay()` uses hardcoded 30 days, `adaptive_decay_half_life()` exists but never called by `decay()` |
| 5 | PreCompact/SessionEnd | "Sleep Consolidation Wilson & McNaughton 1994" | Was a no-op until CHUNK EX5 fix 2026-05-08. Now wired, but historical mycelium.db has gaps |
| 6 | Stop hook | (separate code path) | `feed_from_stop_hook` not audited in this pass — possible drift `?` |
| 7 | `muninn-mem recall` | "semantic memory search" | plain bag-of-words overlap on `.mn` files. Mycelium graph NEVER queried |
| 8 | `muninn-mem recall` | (no explicit promise) | no stopword filter → common English words inflate overlap → false positives |
| 9 | B42 `reconstruct_line_by_line` | (Phase L: 5-10× speedup, smart router by anchored %) | Never wired into the pipeline. Only called from a smoke test |

**Pattern**: 9 drifts out of ~5 audited entry points. The majority are
"the simple/fast path is what runs, the smart/promised path exists but
isn't on the hot route". This is exactly what you sensed as "leaks" —
the code that delivers the marketing-level capability is written but
dormant; what actually executes is a simpler degraded version.

---

**End of v1 PIPELINE_MAP.** Remaining for future session:
- Action 5: full muninn-ui cube_live walkthrough (~1.5h)
- Action 6: SubagentStart hook + subagent context injection (~30min)
- Action 7: `feed_from_stop_hook` to verify Drift #6
- Action 8: `compress_transcript` L0-L11 pipeline detail (~1h)
- Instrumentation phase (= step 2 of original plan) — add
  `log_event("pipeline.X.start", ...)` at each verified entry point
  so live tail can show what runs when.

---

# v2 REVISIONS — after Sky's pushback "tout était wired"

**Why this section exists**: Sky read v1 and said the drifts I listed
were actually wired. I re-verified each one with direct `grep` and
cross-referenced with git commits, tests, and the battle plans. Several
of my v1 claims were too strong because I audited the **hot/fast paths
only** and missed the **full paths** wired elsewhere. This section
corrects them per file:line with proof.

## Revised drift table

| # | v1 claim | v2 verdict | Why |
|---|---|---|---|
| 1 | SessionStart mtime selection | **CONFIRMED but BY DESIGN** | `session_start_hook.py:126` sort by `st_mtime` is intentional ("LIGHT MODE: pure file I/O" line 18). Full path exists via `muninn-mem boot [query]` (`muninn_tree_boot.py:358`) but is NOT auto-invoked by the hook (see Drift #10 below) |
| 2 | spread_activation absent | **PARTIALLY WRONG** | spread_activation IS wired in `muninn_tree_boot.py:358`, `cube_analysis.py:220`, `muninn_tree.py:1420` (bridge), `_hook_logger.py:210`, `mcp/server.py:300` (recall_local), `cube_providers.py:1295`. The accurate claim is narrower: spread_activation is NOT on the live UserPromptSubmit hot path because `bridge_fast` uses 1-hop `get_related()` instead. But it IS wired elsewhere |
| 3 | bridge_fast skip observe+save | **CONFIRMED** | Comment `muninn_tree.py:1587-1588` explicit. By design (hook <0.5s). PreCompact/SessionEnd batches do the learning |
| 4 | adaptive_decay never called | **CONFIRMED** | Re-grep: `adaptive_decay_half_life` called in 4 test sites (`test_phase7_intelligence.py`), 0 prod sites. All 4 prod `m.decay()` calls (`muninn_tree_prune.py:487`, `mycelium.py:504`, `mycelium.py:1561`, `muninn_feed.py:1421`) pass NO argument → default `DECAY_HALF_LIFE = 30` hardcoded |
| 5 | _sleep_consolidate was dead | **HISTORICAL** | CHUNK EX5 fix 2026-05-08 (`muninn_feed.py:1429-1436` comment). Currently wired correctly. Past mycelium.db state may have accumulated cold branches that should have been consolidated but weren't |
| 6 | Stop hook separate path | **UNVERIFIED** | I marked it `?` in v1 — not actually a confirmed drift, drop from the count |
| 7 | recall not mycelium-aware | **WRONG** | Audited the wrong recall. The CLI `recall()` in `muninn_tree.py:1234` IS bag-of-words grep — that part is correct. But the production-facing recall is via MCP: `_recall_local_impl` in `mcp/server.py:228` calls `m.spread_activation()` line 300. There's also `_recall_meta_impl:416` and `_recall_dual_impl:629` for cross-repo meta recall. All mycelium-aware. The CLI recall is essentially legacy |
| 8 | recall no stopwords | **NARROW** | Only the CLI `recall()` lacks stopwords. The MCP `_tokenize_query` likely filters (need to verify) |
| 9 | B42 orphan | **PROBABLY CONFIRMED** | Direct callers = test smoke only. `muninn/cube_providers.py:33` re-exports the symbol (shim, not a caller). No dynamic dispatch found via `getattr` grep. But the helper `_fill_one_gap_with_retries` is documented as "used by reconstruct_line_by_line" — that internal pair is dead together if B42 is dead. Matches Phase L L0 conclusion |

## New drift found during v2

### Drift #10 — Documentation drift between CLAUDE.md and SessionStart hook

The repo's `CLAUDE.md` says:

> *"`muninn-mem boot [query]` (auto-invoked par le hook SessionStart) charge automatiquement la racine de l'arbre [...] les branches pertinentes (chargees selon la query) [...] le dernier transcript compresse (.mn) de la session precedente"*

The actual `session_start_hook.py` does NOT invoke `muninn-mem boot`
as a subprocess. It does pure file I/O in Python directly (`_read_root`
line 98, `_find_recent_branches` line 109 sorting by mtime). The
docstring of the hook itself line 18-19 says explicitly *"LIGHT MODE:
pure file I/O. No engine import, no subprocess, no mycelium queries."*

So the CLAUDE.md description is **inconsistent with the code**. The
"smart" boot exists (`muninn_tree_boot.py:358` with TF-IDF + spread_
activation + B5 session mode + V3A transitive inference) but it's only
invoked when Sky runs `muninn-mem boot [query]` manually from a shell
— never automatically on session start.

This is the documentation drift Sky has been sensing as "the code
doesn't do what I told it to do". The hook was likely simplified
into LIGHT MODE at some point (probably for the <500ms timeout) and
the CLAUDE.md description wasn't updated to match.

### Drift #11 — `bridge()` (HippoRAG + Collins & Loftus) is total orphan

`engine/core/muninn_tree.py:1355` defines `bridge(text, top_n=10,
hops=2)`. Its docstring lines 1357-1369 explicitly cite:

> *"Theory: HippoRAG (Gutierrez & Shu 2024) + Collins & Loftus 1975
> Pattern: FLARE/DRAGIN mid-conversation retrieval"*

The function calls `m.spread_activation(concepts, hops=hops, top_n=top_n)`
on line 1420 — exactly what the CLAUDE.md doc promises for live mid-
session retrieval.

**But `grep -rn "\.bridge(" --include="*.py"` returns zero production
callers**. The function was created by commit `21528de P42: Live
Mycelium Bridge` then immediately superseded by `655c386 P42 phase 2:
auto-hook UserPromptSubmit + bridge_fast (0.35s)` which created the
fast 1-hop replacement. The original `bridge()` was never removed, but
never called again either.

This is the textbook pattern Sky has been sensing: a function with a
beautiful papered scientific reference (HippoRAG paper from 2024),
fully implemented, that is **completely abandoned in favor of a
degraded faster version** because of an external constraint (the
500ms hook budget). The "live mycelium bridge with multi-hop
activation" advertised in MUNINN's marketing is, in production,
1-hop direct neighbors via `bridge_fast`.

## Cross-reference with git history (what each "wire" looked like over time)

- **2026-03-14** `21528de` — bridge() created (P42 phase 1, multi-hop)
- **2026-03-14** `655c386` — bridge_fast() created (P42 phase 2, 1-hop, replaces bridge in hooks)
- **2026-04-10** `b630ba5` — PostToolUseFailure hook
- **2026-04-10** `da1048d` — SubagentStart hook
- **2026-05-08** `bf3858a` — pytest wired into CI (where many test paths come from)
- **2026-05-08** CHUNK EX5 — `_sleep_consolidate` fix (was dead before)
- **2026-05-10** `024da87` — CRIT-1 fix circular imports on mycelium/sync_backend shims
- **2026-05-12** `4065b8b` — MCP console scripts renamed (mcp.E3)
- **2026-05-12** PROMPT_EXEC_PHASE_H launched ("Light Up Everything") — wire 20K+ dormant LOC
- **2026-05-13** various wire commits: `21606d8` zones, `78ce4dd` forge_metrics in cube, `e45341c` muninn-mem cube CLI, `cf25a78` prune --include-dreams (Sleep Consolidation)

The pattern across commits: Sky has run multiple "wire dormant LOC"
campaigns (Phase H, then Phase L), each of which catches some
orphans but doesn't catch all of them in one pass. `bridge()` and
`adaptive_decay_half_life()` are two examples of features that
survived multiple wire campaigns without being either wired or
deleted.

## What this means concretely for Sky

Of the v1 list, the **actually unwired features** as of 2026-05-15
HEAD are:

1. **`bridge()`** — P42 full, multi-hop, HippoRAG-cited. Zero callers.
   Two paths forward: wire it back into UserPromptSubmit (will exceed
   the 0.5s budget — would need to make the hook async), or delete it
   from the codebase (one less orphan to confuse future Claudes).

2. **`adaptive_decay_half_life()`** — A2 promise. Zero prod callers.
   One-line fix: in `mycelium.py:1421` and the other `m.decay()` call
   sites, pass `m.decay(days=m.adaptive_decay_half_life())`. After
   that the very-active-repo decay constant becomes meaningful (15
   days floor for Sky's repo instead of 30).

3. **B42 `reconstruct_line_by_line`** — Phase L pépite as you said.
   Two paths: wire it via the smart router from Phase L L2 (cube
   anchored ≥80% → B42, else B40), or delete it.

4. **CLAUDE.md doc drift on SessionStart auto-boot** — either update
   the doc to say "LIGHT MODE, file I/O only, full boot must be
   manually invoked via `muninn-mem boot [query]`", OR actually wire
   the subprocess into the hook (will break the <500ms target).

The rest of the v1 list either was a misreading on my part (drifts
#2, #7, #8) or describes intentional design choices (light vs full
path, drift #1 #3), or describes already-fixed historical issues
(drift #5).

So the actual fix-worthy items are **3 unwired features + 1 doc
drift**. Much smaller list than v1 suggested. Sky's intuition that
"tout était wired" was mostly right.

I owe you the apology for the alarming first version.
