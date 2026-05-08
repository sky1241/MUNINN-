# CHUNK D10 — Drift audit: muninn/_engine.py vs engine/core/muninn.py

**Date** : 2026-05-08
**Status** : 🟡 Audited; full shim reduction deferred to a dedicated PR.

## Numbers

| Metric | engine/core/muninn.py | muninn/_engine.py |
|---|---|---|
| Lines | 2064 | 2100 |
| Top-level functions | 23 | 23 |
| Classes | 0 | 0 |
| Diff lines (whole file) | — | 4166 |

**Surface parity**: identical 23 functions on both sides — no public API
loss in either direction. The drift is in the *implementation* of those
functions (whitespace, docstrings, occasional one-line behaviour deltas).

## What the drift contains (sampled)

A diff sample (`diff engine/core/muninn.py muninn/_engine.py | head -50`)
shows the headers diverge: `engine/core/muninn.py` was updated by CHUNK
C8 to read `__version__` via `importlib.metadata`, while `muninn/_engine.py`
still hardcodes `__version__ = "0.9.1"`.

The functions that were patched in Phase A/B/C touched
`engine/core/muninn.py` only, so any of those edits is now potential
drift on the muninn side.

## Why we don't fully shim it now

`muninn/_engine.py` is imported eagerly by `muninn/__init__.py:20`:

    from . import _engine  # noqa: F401 — loads globals + sub-modules

Reducing it to a raw `from engine.core.muninn import *` shim risks:
- breaking the `python -m muninn ...` entry point (which routes through
  `muninn._engine:main`)
- breaking 80+ test imports of the form `from muninn._engine import X`
- forcing `engine/core/` onto every CI runner's sys.path eagerly
  (currently lazy via the existing shims)

A safe migration plan needs:
1. A green pytest baseline that exercises the eager-import path.
2. A staged shim that selectively re-exports the 23 functions while
   keeping `main()` available as `muninn._engine.main`.
3. Validation that `pip install -e .` still wires the `muninn` console
   script to `muninn._engine:main`.
4. A separate PR with `git diff --stat` showing < 100 LOC change beyond
   the shim itself.

That's a multi-hour, multi-file refactor — too risky for the single-chunk
TDD cadence used in Phases A/B/C/D so far.

## What we ship instead

`tests/test_chunk_d10_engine_drift.py`:
- Locks in the 23-function surface parity.
- Caps the diff size at the current 4166 (any future blow-up fails CI).
- Asserts the shim's `__version__` is in sync with `engine/core/muninn.py`'s
  via `importlib.metadata` (CHUNK C8).

When Sky decides to fully reduce `_engine.py`, the test will go from
"both paths equivalent at the surface" to "shim re-exports only" — the
parity assert still holds, and the LOC cap drops dramatically.

## Suggested next-step plan

1. Open a branch `audit2/d10-engine-shim`.
2. `git mv muninn/_engine.py muninn/_engine.py.legacy` (kept for diff).
3. Write the new `_engine.py` as a shim that:
   - `from engine.core.muninn import *`
   - Re-exports `main` for the console script
   - Re-exports `__version__`
4. Run full pytest. Fix anything that breaks.
5. Delete `_engine.py.legacy` only when CI is green for 24 h.

This is exactly the playbook used for the other 17 BUG-091 shims in
docs/BATTLE_PLAN_BUG091_2026-05-07.md.
