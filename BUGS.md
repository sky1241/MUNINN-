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

## Status: 90 bugs fixed across 12 audit passes (2026-03-18). **1 OPEN** (architectural smell, 2026-04-10).

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

