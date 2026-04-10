---
paths:
  - "engine/**/*.py"
  - "muninn/**/*.py"
  - "tests/**/*.py"
  - "*.py"
---

<!-- ================================================================ -->
<!-- Path-scoped rules: only loaded when Claude touches Python files. -->
<!-- These EXTEND CLAUDE.md RULE 1 with Python-specific guidance.     -->
<!-- HTML comments are stripped before injection (free maintainer notes).-->
<!-- ================================================================ -->

# Python rules for the MUNINN- repo

These rules are loaded by Claude Code only when working with `.py` files
in this project. They extend (do not replace) the universal RULES in
the root `CLAUDE.md`.

## RULE 1 extended — paths in Python code

CLAUDE.md RULE 1 says "Never bake `C:/Users/ludov/MUNINN-` into a function
body". For Python specifically, here are the established patterns in this
repo. Use whichever fits the situation:

**Pattern A — Module global resolved at import time**
```python
from pathlib import Path
MODULE_DIR = Path(__file__).resolve().parent
REPO_ROOT = MODULE_DIR.parent.parent  # adjust depth to your file
```
Used in: `engine/core/muninn.py`, `engine/core/muninn_tree.py`.

**Pattern B — Function argument**
```python
def load_tree(repo_path: Path) -> dict:
    tree_file = Path(repo_path) / "memory" / "tree.json"
    return json.loads(tree_file.read_text(encoding="utf-8"))
```
Used in: most engine functions that operate on a target repo.

**Pattern C — Mutable module global (`_REPO_PATH`)**
```python
import muninn
muninn._REPO_PATH = Path(repo_path).resolve()
muninn._refresh_tree_paths()
```
Used in: `bridge_hook.py`, `subagent_start_hook.py`. The hooks set
`_REPO_PATH` from the `cwd` field of the Claude Code payload, then call
`_refresh_tree_paths()` to refresh dependent globals.

**Pattern D — Environment variable fallback**
```python
import os
repo = os.environ.get("MUNINN_REPO") or os.getcwd()
```
Used in: ad-hoc scripts and CLI entry points.

## File creation in `engine/core/` and `muninn/`

The `engine/core/` and `muninn/` package directories are FULLY DUPLICATED
because of the pip-package refactor (BUG-091 in `BUGS.md`). When you add or
modify a function in one of these:

1. Make the change in the file Sky asked for (usually `engine/core/`)
2. Mirror the EXACT same change in the other tree (`muninn/_engine.py`,
   `muninn/_secrets.py`, etc.)
3. Run the tests of any chunk that imports `muninn` to verify both paths
   resolve to the new behavior

This is annoying and error-prone. If you can avoid touching these files,
do. If you must touch them, mirror immediately, don't promise to do it
"later".

## Test conventions in this repo

- `pytest` is used everywhere. Tests live in `tests/`.
- Each chunk has its own `test_chunkN_*.py`.
- The numbered chunks are documented in `CHANGELOG.md`.
- Sanity tests for the eval harnesses (chunk 9, chunk 11) are pytest
  modules. The harnesses themselves (`tests/eval_harness_chunk*.py`)
  are runnable scripts that call the API and cost money — never run
  them as part of `pytest tests/`.
- A test must NOT call the Anthropic API unless explicitly justified by
  Sky and budgeted. Use stubs and recorded fixtures.
- A test must NOT modify the real `.claude/settings.local.json` of the
  repo it lives in. Use `tmp_path` fixtures.

## Encoding on Windows

Sky is on Windows 11 with `PYTHONIOENCODING=utf-8` set. When you write
Python that prints French text to stdout, prefer:
```python
sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
```
over `print(text)` for diagnostic scripts that may hit `cp1252` codec.

## Secrets in Python code

CLAUDE.md RULE 3 says never display secrets. For Python:
- Never put a token in a test fixture, even a fake-looking one. Use
  the constant `"REDACTED_FAKE_TOKEN_FOR_TEST"` instead.
- Never `print()` an environment variable that might contain a secret.
  Use `repr()` of its length: `print(f"len(VAR)={len(os.environ.get('VAR', ''))}")`.
- The `_secrets.py` module has `redact_secrets_text(text)` and
  `clamp_chained_commands(text)` for defense in depth — use them when
  building any string that gets injected into Claude's context.
