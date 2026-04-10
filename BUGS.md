# BUGS — MUNINN-

> Format: each bug has an ID, status, symptom, root cause, fix, and test.
> This file is READ BY CLAUDE AT BOOT. Keep it accurate.

<!-- TEMPLATE
## BUG-XXX: [short description]
- **Status**: OPEN / FIXED / WONTFIX
- **Symptom**: what happens
- **Root cause**: WHY it happens (not just where)
- **Fix**: what was done (commit hash if fixed)
- **Test**: which test covers this (file:test_name)
- **Regression**: did the fix break anything else?
-->

## Status: 90+10+3 bugs fixed (90 from 12 audit passes 2026-03-18 + 10 from chunks 16+17 audit 2026-04-10 + BUG-102 forge no-isolation + BUG-105 L12 single-chunk destruction + BUG-106 mycelium spread_activation infinite hang on big graphs, all fixed 2026-04-10/11). **3 OPEN** (BUG-091 architectural smell, BUG-103 scrub_secrets false positives, BUG-104 L12 fact-span detection too narrow).

---

## CRITICAL — 2026-04-10 — BUG-102: forge --gen-props had no isolation

### BUG-102: forge --gen-props fuzzed destructive functions, corrupted 165 files
- **Status**: FIXED
- **Symptom**: ran `forge.py --gen-props engine/core/muninn.py`. Forge generated
  `tests/test_props_muninn.py` which contained Hypothesis property tests for
  every public function in the module — including `scrub_secrets(target_path,
  dry_run)`, `install_hooks(repo_path)`, `purge_secrets_db(repo_path)`,
  `bootstrap_mycelium(repo_path)`, `generate_root_mn(repo_path, ...)`, etc.
  When pytest collected this file, Hypothesis happily generated `target_path=''`
  / `target_path='.'` and `dry_run=False`. The test then walked the entire
  MUNINN- repo, applied the over-aggressive `_COMPILED_SECRET_PATTERNS`, and
  rewrote 165 source files in place with literal `[REDACTED]` substitutions.
  Things like `key TEXT PRIMARY KEY` became `key [REDACTED] PRIMARY KEY`,
  `r'AccountKey=...'` became `r'[REDACTED]`, breaking Python parsing across
  the whole repo. Took several hours to bisect because `git checkout HEAD --`
  appeared to work, but the next pytest run re-corrupted everything.
- **Root cause**: `forge.gen_props()` walked all public functions of the module
  and generated a smoke test for each one — with NO filtering for side effects.
  The generated tests had `try/except (ValueError, TypeError, ...)` blocks but
  `OSError` from filesystem writes was caught silently, and Hypothesis happily
  generated empty/dot strings as path arguments. Property-based fuzzing on a
  function with destructive side effects on the caller's filesystem is
  dangerous by design.
- **Fix**: added `_is_destructive_function(node, source)` helper to forge.py.
  Three layers of detection: (1) name patterns matching `^scrub_`,
  `^install_`, `^purge_`, `^bootstrap`, `^generate_`, `^observe`, `^feed`,
  `^migrate`, `^run_`, `_hook$`, etc. (~30 patterns). (2) AST scan of
  function body for known-destructive calls: `write_text`, `rmtree`,
  `subprocess.run`, `open(..., 'w')`, etc. (3) Path-like argument detection:
  if any arg is named `path`, `repo_path`, `target_path`, etc. AND the body
  calls `.walk()`, `.read_text()`, etc., flag as destructive (caller-supplied
  paths can't be fuzzed safely). gen_props() now skips these by default and
  emits a banner in the generated test file listing what was skipped and why.
  CLI flag `--include-destructive` exists for explicit override (with a loud
  warning). Fix mirrored to all 3 forge.py files (root, engine/core, muninn
  package) per BUG-091.
- **Test**: `tests/test_forge_destructive_skip.py` — 18 tests covering name
  patterns (scrub, install, purge, bootstrap, generate, hook), AST scan
  (write_text, subprocess.run, open('w'), rmtree, walk on path-like arg),
  pure-function negatives (string functions and read-only helpers must NOT
  be flagged), end-to-end gen_props on a fake module, override flag works,
  and the explicit muninn.py regression test (`test_gen_props_real_muninn_
  does_not_call_scrub`) — verifies that `forge --gen-props engine/core/
  muninn.py` produces a test file that contains ZERO calls to `scrub_secrets(`,
  `install_hooks(`, `bootstrap_mycelium(`, `generate_root_mn(`, etc.
- **Regression**: none. Pure functions like `redact_secrets_text`,
  `count_chained_commands`, `clamp_chained_commands` are still detected as
  safe and continue to be fuzzed normally.

### BUG-106: mycelium.spread_activation infinite hang on graphs > 500K edges
- **Status**: FIXED (commit pending — brick 15)
- **Symptom**: `tests/test_lazy_real.py::test_real_spread_activation` hung
  for 60+ seconds and timed out on Sky's real mycelium DB (180,852 concepts,
  15,560,444 edges, 1.8 GB on disk). The test asserts `dt < 60.0` so it
  reliably failed. Same hang pattern would hit `find_chain()` and any
  other caller of `_build_adj_cache()`.
- **Root cause**: `_build_adj_cache()` did `SELECT a, b, count FROM edges`
  with NO LIMIT, loading all 15.5M rows into a Python dict. Each row
  generated 2 dict entries (a→b and b→a), so the result was ~31M tuples
  in a Python dict — multiple GB of RAM, multiple minutes of CPU just
  to load. Then `spread_activation` iterated over all of it.
- **Fix**: added a bounded BFS subgraph builder
  `_build_adj_subgraph(seeds, hops, fanout_cap)` to both
  `engine/core/mycelium.py` and `muninn/mycelium.py`. Per-node SQL
  query with `LIMIT fanout_cap` (default 64) so even hub seeds can't
  blow up the BFS:
  ```sql
  SELECT a, b, count FROM edges
  WHERE a = ? OR b = ?
  ORDER BY count DESC LIMIT ?
  ```
  Re-wired `spread_activation()` and `find_chain()` to use the bounded
  builder. The old `_build_adj_cache()` still exists but now refuses
  to load > `_ADJ_CACHE_HARD_LIMIT` (500,000) edges and emits a stderr
  warning, forcing future callers onto the bounded path.
- **Verification (real measurements on Sky's actual DB)**:
  - Pre-fix: hangs at 60s+ (test timeout fires), exact behavior
    documented in earlier session traceback (`mycelium.py:1302` in
    the normalization loop)
  - Post-fix run 1 (fanout_cap=200): 127 seconds — too slow, still
    hits the test timeout
  - Post-fix run 2 (fanout_cap=64, per-node SQL with LIMIT):
    **24.169 seconds**, 20 concepts activated, top result `muninn`
    with activation 1.0 — under the 60s test threshold
- **Test**: `tests/test_brick15_spread_activation_bounded.py` — 8 pin
  tests covering:
    - API surface: _build_adj_subgraph exists, hard limit constant
    - Empty / unknown seeds return empty
    - Real seeds produce non-empty subgraph with valid (str, float) entries
    - fanout_cap is respected per node
    - **spread_activation_under_60s_on_real_db** — full e2e on Sky's DB
    - **subgraph_builder_under_30s_on_real_db** — direct builder e2e
  Plus the original `test_lazy_real.py::test_real_spread_activation`
  now passes in 24.60s (was hanging).
- **Why this is critical**: spread_activation is used by Muninn's
  `boot()` for retrieval scoring (Collins & Loftus 1975 spreading
  activation through the mycelium semantic network). Pre-fix, ANY
  user with > 500K edges had a broken boot. Sky has 15.5M edges.

### BUG-105: L12 destroys files with no `\n\n` paragraph breaks (JSONL, logs)
- **Status**: FIXED (commit pending — this brick 13)
- **Symptom**: ran the Phase B brick 7 benchmark on a real Sky transcript:
  `c:/Users/ludov/.claude/projects/c--Users-ludov-MUNINN-/d00638e7-...jsonl`
  (22 MB, 5,839,925 BPE tokens, JSONL one-message-per-line, ZERO `\n\n`).
  L0-L11 alone produced 4.2M tokens (x1.38). L12 with ANY budget setting
  (b=2.9M, b=1.5M, b=583K) produced **8 tokens** for the entire 22MB file.
  Effective ratio x729,990. The "compressed" output was 8 tokens of
  garbage from cue distillation running on an empty input. The actual
  transcript content was completely deleted.
- **Root cause**: `engine/core/muninn_layers.py:_l12_budget_pass()` called
  `budget_select.budget_select()` without checking the chunk count first.
  `budget_select` splits on `\n\s*\n` to get paragraph chunks. JSONL files
  have only `\n` separators, so the split returns a SINGLE chunk for the
  entire 22MB file. BudgetMem then evaluates this one chunk:
    - Marks it as must-keep (it has fact spans)
    - Tries to fit it: chunk size (5.8M tok) >> budget (e.g. 1.5M tok)
    - Phase 1 packing: doesn't fit, skip
    - Phase 2 score-sorted: nothing else to pick from
    - Returns: empty string ""
  The rest of `compress_file()` runs on the empty string and produces
  ~8 tokens of metadata (codebook header, cue distill noise).
- **Fix**: added a chunk-count guard at the top of `_l12_budget_pass()`
  in BOTH `engine/core/muninn_layers.py` and `muninn/muninn_layers.py`:
  ```python
  chunks = _re.split(r"\n\s*\n", text)
  if len(chunks) < 2:
      return text  # nothing to select between, return as-is
  ```
  When the input has fewer than 2 paragraph chunks, L12 has nothing to
  do — return identity. This protects every JSONL / log / CSV / single-
  paragraph input from accidental destruction.
- **Verification (real, on the same 22MB transcript)**: post-fix,
  `_l12_budget_pass(text)` with `MUNINN_L12_BUDGET=1000` returns the
  full 23,359,701 chars unchanged. **Saved 23,359,701 chars from being
  collapsed to 8 tokens.** L12 still functions normally on multi-chunk
  markdown input — verified in the same test session with a 6-paragraph
  synthetic doc (508 → 80 chars, facts kept).
- **Test**: `tests/test_brick13_l12_bug_105_jsonl.py` — 9 pin tests:
    - JSONL / log / CSV / single-paragraph .md inputs all pass through
      L12 unchanged at any budget
    - Empty / None inputs handled
    - Multi-chunk markdown still compresses (BUG-105 is a guard, not a
      kill switch)
    - The exact real 22MB transcript from the benchmark passes through
      unchanged at budget=1000
    - PHASE_B_BIG_FILE_BENCHMARK.md doc exists and contains the headline
      numbers (23,359,701 chars saved, 8 tokens disaster pre-fix)
- **Why this is critical**: this is the EXACT primary use case Sky cares
  about (compressing his Claude Code transcripts). Phase B brick 7 ratios
  on small markdown benchmark files looked great (x8-x9), but the wiring
  silently destroyed any JSONL transcript fed to it. Without this fix,
  Sky shipping L12 to compress his transcripts would have lost data.
- **Future improvement**: emit a one-time stderr warning when the BUG-105
  guard fires, so users know L12 is being skipped (currently silent
  degradation). Not critical, file as enhancement not bug.

### BUG-104: L12 BudgetMem fact-recall loss at tight budgets (PARTIAL FIX brick 17)
- **Status**: PARTIAL FIX (brick 17 extended has_fact_span, but the
  benchmark numbers did not change — the actual root cause is different)
- **Symptom**: at `MUNINN_L12_BUDGET=500` on `verbose_memory.md` (1005 tok),
  fact recall drops from **15/15 (100%) to 6/15 (40%)** — a -60 point loss.
  At b=250 it goes to 5/15 (33%, -67 points). Sample_session.md has the
  same pattern at smaller swings (80% → 60% → 53%). See
  `tests/benchmark/PHASE_B_FACT_RECALL.md` for the full table.
- **Original (wrong) root cause analysis**: I assumed has_fact_span() was
  too narrow and missed soft facts (function names, paths, CamelCase,
  backticks). I implemented brick 17 to extend `_FACT_SPAN_RES` with
  4 new patterns and verified them on synthetic inputs (20 pin tests pass).
  THEN I re-ran the verbose_memory.md / sample_session.md benchmark and
  the numbers were UNCHANGED (still 6/15 at b=500, still 9/15 on session).
  Investigation showed that the chunks on those files ALREADY had hard
  facts (dates, version numbers) and were ALREADY marked must-keep —
  the new patterns were redundant for those specific files.
- **Actual root cause** (corrected analysis 2026-04-11): the must-keep
  rule fires correctly. The problem is that the must-keep CHUNKS are
  TOO BIG to all fit in the budget. Phase 1 packing (must-keep first)
  can only fit some of them; the rest are dropped. Questions about facts
  in dropped must-keep chunks fail. This is NOT a detector problem, it's
  a chunk granularity problem — the chunks are paragraph-sized and on
  technical content, paragraphs are too large to fit in tight budgets.
- **Real fix (TBD)**: split big must-keep chunks into sub-chunks before
  budget evaluation, OR run L0-L11 compression on must-keep chunks BEFORE
  budget evaluation so they take fewer tokens, OR document that L12 is
  only effective when budget >= largest_chunk_size.
- **Brick 17 partial fix (committed)**: extended `_FACT_SPAN_RES` with
  4 new patterns:
    - `\b[a-z_][a-zA-Z0-9_]{3,}\(`            — function call sites
    - `\b[a-zA-Z_][\w.\-]*/[\w.\-/]{3,}`      — file paths (3+ chars after /)
    - `\b[A-Z][a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+\b`  — proper CamelCase
    - `` `[^`\n]{3,50}` ``                     — backtick-quoted code
  These DO help on chunks that contain ONLY soft facts and no numbers
  (verified by `test_soft_only_chunk_marked_must_keep`). They DO NOT help
  on the existing benchmark files because those already have hard facts.
  The patterns are conservative enough to avoid false positives on
  ordinary prose ("Mycelium" alone does NOT match because it has no
  inner uppercase — only proper CamelCase like "BudgetSelector" matches).
- **Mitigation now**: L12 stays OPT-IN via env var (default OFF). The
  documented safe operating range in PHASE_B_FACT_RECALL.md is
  `MUNINN_L12_BUDGET >= compressed file size` — at that point L12 is
  effectively a no-op (correct behavior for safe default).
- **Test**: `tests/test_brick12_l12_fact_recall.py` — 8 tests pin both
  the no-regression contract (huge budget = identity) AND the BUG-104
  envelope at b=500 (3-12 facts kept on verbose, 6-13 on session). The
  BUG-104 envelope tests will FAIL the day this is fixed properly,
  signalling that PHASE_B_FACT_RECALL.md needs an update.
- **Why this is OPEN, not WONTFIX**: the user-facing impact is real
  whenever someone uses L12 at tight budget without reading the doc.
  Fixing the fact-span detector closes the gap entirely.

### BUG-103: scrub_secrets() regex patterns have false positives on plain SQL
- **Status**: OPEN (deferred — separate fix from BUG-102)
- **Symptom**: when BUG-102 corrupted the repo, the substitution pattern showed
  that `_COMPILED_SECRET_PATTERNS` matches innocuous SQL fragments. Examples
  observed in the diff: `key TEXT PRIMARY KEY` → `key [REDACTED] PRIMARY KEY`,
  `PRIMARY KEY (a, b)` → `PRIMARY KEY [REDACTED] b)`, `f"display of $-var
  matching secret name: {m.group(1)}"` → `... matching secret [REDACTED]`.
- **Root cause**: not yet fully isolated. Likely a pattern like `\b[A-Z]{4}\b`
  (4 uppercase letters = TOKEN-shaped) or a context-free trigger word match
  that fires on any word followed by ` (...)` or `name:`.
- **Fix**: TBD. Will require auditing every regex in `_SECRET_PATTERNS` and
  adding negative lookbehind for SQL keywords (`TEXT`, `PRIMARY KEY`, etc.).
- **Mitigation**: BUG-102 fix prevents `scrub_secrets()` from being called
  by accident — that's the destructive part of the chain. The remaining
  false positives are still wrong but no longer destructive.
- **Test**: TBD.

---

## Audit 2026-04-10 — chunk 16 — 9 bugs found and fixed

Full audit pass on the 9 hooks added in chunks 4, 5, 12, 14, 15. Each bug
caught by adversarial edge-case testing, fixed, and pinned by an
anti-regression test in `test_chunk12_pre_tool_use_hooks.py` or
`test_audit_dual_tree_sync.py`.

### BUG-092: pre_tool_use_bash_destructive missed `rm -rf foo/*` glob
- **Status**: FIXED
- **Symptom**: `rm -rf foo/*` (glob in subdir) was ALLOWED. Same for `rm -rf *.log`.
- **Root cause**: regex pattern `\brm\s+-rf?\s+\*` only matched literal `*`,
  not `*.log` or `foo/*`.
- **Fix**: replaced with `\brm\s+-rf?\s+[^\s|;&]*\*` (any token containing `*`)
  + new pattern for `\.\.` (parent dir).
- **Test**: `test_destructive_blocks_rm_rf_glob_subdir`,
  `test_destructive_blocks_rm_rf_glob_extension`,
  `test_destructive_blocks_rm_rf_parent`.

### BUG-093: pre_tool_use_bash_destructive missed `git push -fu` combined flags
- **Status**: FIXED
- **Symptom**: `git push -fu origin main` (combined `-f` + `-u` short flags)
  was ALLOWED. Sky uses `-fu` to force push + set upstream in one go.
- **Root cause**: regex `\bgit\s+push\b[^|;&]*-f\b` matches `-f ` but not `-fu`
  because the `\b` at the end requires word boundary, and `-fu` has `u` after `f`.
- **Fix**: replaced with `\bgit\s+push\b[^|;&]*\s-[a-z]*f[a-z]*\b` matching any
  short-flag combo containing `f`.
- **Test**: `test_destructive_blocks_git_push_combined_short_flags`. Includes
  no-false-positive check for legit `git push -u origin feature`.

### BUG-094: pre_tool_use_bash_destructive missed eval/exec wrapping
- **Status**: FIXED
- **Symptom**: `eval 'rm -rf /'`, `bash -c 'git push --force'` were ALLOWED.
- **Root cause**: regex patterns checked for direct command, not for the
  destructive command being inside an eval/exec/sh -c wrapper.
- **Fix**: new pattern matching `\b(?:eval|exec|sh\s+-c|bash\s+-c)\b`
  followed by a quoted string containing destructive markers.
- **Test**: `test_destructive_blocks_eval_wrapped`.

### BUG-095 to BUG-100: 6 hooks crashed on non-dict payload
- **Status**: FIXED (all 6)
- **Symptom**: When stdin contained a JSON value that wasn't an object
  (e.g. `[1,2,3]`, `"string"`, `42`, `null`), the hooks crashed with
  `AttributeError: 'list' object has no attribute 'get'` and exited 1.
  This violates the contract "hooks NEVER raise, always exit 0 or 2".
- **Root cause**: `payload.get("cwd")` was called BEFORE checking
  `isinstance(payload, dict)`. The `try/except` block protected the
  downstream function call, not the `.get()` itself.
- **Affected hooks**:
  - bridge_hook.py
  - post_tool_failure_hook.py
  - notification_audit_hook.py
  - post_tool_use_edit_log.py
  - config_change_hook.py
  - + the 2 generators in `engine/core/muninn.py` and `muninn/_engine.py`
    (so the bug would resurface on next `install_hooks()`)
- **Fix**: added `if not isinstance(payload, dict): sys.exit(0)` after
  `json.loads()` and before any `.get()`. Also tightened `bridge_hook.py`
  `prompt = ... .get("prompt", "")` with `isinstance(prompt, str)` check.
- **Test**: parametrized test `test_audit_all_hooks_robust_to_malformed_payloads`
  in `tests/test_chunk12_pre_tool_use_hooks.py` runs 9 hooks × 6 malformed
  payloads = 54 cases. All exit 0.

### BUG-101: _truncate_with_marker oversized output when max_chars < 100
- **Status**: FIXED
- **Symptom**: `_truncate_with_marker(text="x"*500, max_chars=50)` returned
  509 chars instead of ≤50. The truncated output was longer than the input
  AND larger than the cap.
- **Root cause**: `text[: max_chars - 100]` produces a NEGATIVE slice when
  max_chars < 100. Negative slice in Python takes everything except the
  last N chars, so the result was `text[:-50]` = almost all of text. Then
  the marker (~60 chars) was appended on top, exceeding max_chars by ~10x.
- **Discovery method**: Hypothesis property test
  `test_truncate_with_marker_no_crash` in `tests/test_audit_hypothesis_hooks.py`
  with the invariant `len(result) <= max_chars when len(text) > max_chars`.
  Hypothesis found the falsifying example automatically: `text="0"*500, max_chars=50`.
- **Fix**: clamp slice index at 0, account for marker length, and if
  `max_chars <= len(marker)` return marker truncated. Applied in:
  - `.claude/hooks/subagent_start_hook.py`
  - `engine/core/muninn.py` template (BUG-091 sync)
  - `muninn/_engine.py` template (BUG-091 sync)
- **Test**: `test_truncate_with_marker_no_crash` (200 random inputs).
- **Lesson**: this bug had been in the code since chunk 5 (4 commits before
  the audit). The 11 hand-written tests in `test_chunk5_subagent_start_hook.py`
  did NOT catch it because they only used "reasonable" max_chars values
  (1000+, 20000). Hypothesis caught it on the FIRST run with random integers
  in [50, 100000]. This validates Sky's complaint "tu n'as pas utilisé forge
  correctement" — adversarial property testing finds bugs that example-based
  testing misses.

### BUG-091: engine/core/ vs muninn/ pkg fully duplicated [STILL OPEN]
- **Status**: OPEN (unchanged from before audit)
- **Audit progress**: chunk 16 added `tests/test_audit_dual_tree_sync.py`
  which checks that 12 specific markers from today's modifs are mirrored
  in BOTH trees. This is NOT a fix — it's a tripwire. If a future change
  breaks the mirror on these markers, the test fails. Doesn't help for
  files that diverged BEFORE today (16 of 19 file pairs are still
  diverged, see audit output).
- **Real fix is still TODO**: pick one source of truth, delete the other.

---

## Status: 90 bugs fixed across 12 audit passes (2026-03-18). 0 OPEN (pre-audit).

## BUG-091: engine/core/ and muninn/ package fully duplicated
- **Status**: OPEN
- **Symptom**: Modifying a file in `engine/core/` does NOT affect code paths
  that `import muninn` (the pip package). Discovered during chunk 4 of leak
  intel battle plan: chunk 3's anti-Adversa clamp had to be mirrored from
  `engine/core/_secrets.py` to `muninn/_secrets.py` to be picked up by tests.
- **Root cause**: Two parallel trees exist after the pip-package refactor
  (commit history mentions `_ProxyModule`). The proxy bridges some functions
  but NOT new ones added in either location after the refactor. Files affected:
  - engine/core/muninn.py vs muninn/_engine.py
  - engine/core/_secrets.py vs muninn/_secrets.py
  - engine/core/muninn_tree.py vs muninn/muninn_tree.py
  - engine/core/muninn_layers.py vs muninn/muninn_layers.py
  - engine/core/muninn_feed.py vs muninn/muninn_feed.py
  - engine/core/mycelium.py vs muninn/mycelium.py
  - (and ~10 others)
- **Workaround used by chunks 3-5**: every modif applied in BOTH trees by hand.
  This is unsustainable for non-trivial changes.
- **Fix (proposed, out of scope for chunk 5)**: pick one source of truth
  (probably `muninn/` since it's the pip-installable package), delete the
  other, and update all import paths to go through the package. The `engine/core`
  path should become a symlink, an alias, or simply removed.
- **Test**: NONE yet. A test that compares both files for byte-equality
  would catch this regression: `test_engine_muninn_sync.py`.
- **Regression risk**: tests that hardcode `engine/core/` paths (there are
  some) need updating.

---

## Status (2026-03-18): 90 bugs fixed across 12 audit passes. 0 OPEN.

All bugs below were found and fixed during the exhaustive debug audit using Forge
(--predict, --heatmap, --anomaly, --locate, --gen-props) + manual deep audit.

## BUG-001: shlex.split() mangles Windows backslash paths
- **Status**: FIXED
- **Symptom**: Forge file paths broken on Windows (backslashes split as escape chars)
- **Root cause**: shlex.split() defaults to posix=True, which treats \ as escape
- **Fix**: `shlex.split(cmd, posix=(os.name != "nt"))` in forge.py (fa2180d)
- **Test**: forge --predict on Windows paths
- **Regression**: None

## BUG-002: bisect_test() leaves repo on detached HEAD after timeout
- **Status**: FIXED
- **Symptom**: Forge bisect hangs forever on slow tests, repo left in bad state
- **Root cause**: subprocess.run without timeout, no try/except TimeoutExpired
- **Fix**: Wrapped in try/except, treat timeout as FAIL (fa2180d)
- **Test**: forge --bisect with slow tests
- **Regression**: None

## BUG-003: vault rekey() wipes old key even on partial failure
- **Status**: FIXED
- **Symptom**: If rekey fails on file N of M, old key is destroyed, remaining files unreadable
- **Root cause**: _zero_bytes(old_key) called unconditionally
- **Fix**: Track failed files, preserve old key if any fail (fa2180d)
- **Test**: vault rekey with simulated failure
- **Regression**: None

## BUG-004: sync_to_meta n_synced UnboundLocalError
- **Status**: FIXED
- **Symptom**: Crash in mycelium sync_to_meta if exception before n_synced assignment
- **Root cause**: n_synced = 0 was inside try block after potential failure point
- **Fix**: Move `n_synced = 0` before try block (fa2180d)
- **Test**: mycelium sync operations
- **Regression**: None

## BUG-005: read_node() only catches FileNotFoundError
- **Status**: FIXED
- **Symptom**: Crash on corrupted/locked/non-UTF8 branch files
- **Root cause**: Only FileNotFoundError caught, not UnicodeDecodeError/PermissionError/OSError
- **Fix**: Broader except (UnicodeDecodeError, PermissionError, OSError) (fa2180d)
- **Test**: read_node with various file errors
- **Regression**: None

## BUG-006: gen-props catches class methods as top-level functions
- **Status**: FIXED
- **Symptom**: Forge gen-props generates broken tests for class methods (missing self)
- **Root cause**: ast.walk(tree) traverses into class bodies
- **Fix**: ast.iter_child_nodes(tree) — only top-level functions (9e73edc)
- **Test**: forge --gen-props on files with classes
- **Regression**: None

## BUG-007: gen-props missing deadline=None
- **Status**: FIXED
- **Symptom**: False DeadlineExceeded on slow functions (boot, prune)
- **Root cause**: Hypothesis default 200ms deadline too short for I/O functions
- **Fix**: @settings(max_examples=50, deadline=None) (cdb20dc)
- **Test**: forge --gen-props on muninn.py
- **Regression**: None

## BUG-008: batch_upsert/delete missing WAL on_write()
- **Status**: FIXED
- **Symptom**: WAL monitor unaware of batch operations, delayed checkpoints
- **Root cause**: on_write() call missing after batch commit (all other writes had it)
- **Fix**: Added self._wal_monitor.on_write() after batch ops (passe 12)
- **Test**: test_wal_monitor.py
- **Regression**: None

## BUG-009: sync_tls accept loop conn leak
- **Status**: FIXED
- **Symptom**: If Thread().start() fails, accepted connection never closed (FD leak)
- **Root cause**: No try/except around thread creation in accept loop
- **Fix**: try/except with conn.close() on failure (passe 12)
- **Test**: test_sync_tls.py
- **Regression**: None

## BUG-010: SQLite conn leak in mycelium _load()
- **Status**: FIXED
- **Symptom**: If exception between connect and close, conn leaked (Windows file lock)
- **Root cause**: No try/finally around migration check query
- **Fix**: try/finally ensuring conn.close() (passe 12)
- **Test**: mycelium load operations
- **Regression**: None

