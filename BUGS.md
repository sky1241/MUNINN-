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

## Status: 90+9 bugs fixed (90 from 12 audit passes 2026-03-18 + 9 from chunk 16 audit 2026-04-10). **1 OPEN** (BUG-091 architectural smell).

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

