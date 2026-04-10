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

## Status: 90+10+1 bugs fixed (90 from 12 audit passes 2026-03-18 + 10 from chunks 16+17 audit 2026-04-10 + BUG-102 forge no-isolation fixed 2026-04-10). **3 OPEN** (BUG-091 architectural smell, BUG-103 scrub_secrets false positives, BUG-104 L12 fact-span detection too narrow).

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

### BUG-104: L12 BudgetMem fact-span detector misses soft facts under tight budget
- **Status**: OPEN (deferred — empirically measured 2026-04-10, brick 12)
- **Symptom**: at `MUNINN_L12_BUDGET=500` on `verbose_memory.md` (1005 tok),
  fact recall drops from **15/15 (100%) to 6/15 (40%)** — a -60 point loss.
  At b=250 it goes to 5/15 (33%, -67 points). Sample_session.md has the
  same pattern at smaller swings (80% → 60% → 53%). See
  `tests/benchmark/PHASE_B_FACT_RECALL.md` for the full table.
- **Root cause**: `engine/core/budget_select.py:has_fact_span()` only matches
  a finite set of regex (ISO date, semver, git hash, %, $money, JIRA ticket,
  URL). It does NOT detect:
    - Function / class names (`compress_line`, `Mycelium`)
    - File paths (`engine/core/muninn.py`)
    - Verbose facts ("the test was created on Tuesday")
    - Identifiers in backticks
  When a chunk only has these "soft facts", BudgetMem's must-keep hard rule
  doesn't fire, so the chunk competes on the score-only path and loses to
  position-bias filler chunks.
- **Fix (TBD)**: extend `_FACT_SPAN_RES` with patterns for:
    - `\b[a-z][a-zA-Z0-9_]+\(\)` (function call sites)
    - `\b[A-Z][a-zA-Z0-9_]*[a-z]` (CamelCase identifiers, ≥4 chars)
    - `[a-zA-Z_]+/[a-zA-Z_]+/[a-zA-Z_.]+` (path segments)
    - `\` `[^\`]{3,30}\` `` (backtick-quoted code)
  Risk: false positives on prose containing camelCase or paths in markdown
  example blocks. Need to test on the existing fact-recall benchmark before
  shipping.
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

