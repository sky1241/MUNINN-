# Phase B Brick 20 — Architecture Audit (Senior Dev Pass)

Generated: 2026-04-11
Method: pure-Python AST scan, manual review of findings

## Method

For every `.py` file under `engine/core/`:

1. **Module size sanity** — count physical lines per file. Threshold:
   - WARN at > 2500 lines
   - CRITICAL at > 3500 lines (refactor candidate)

2. **Function size sanity** — count lines per top-level function.
   - WARN at > 200 lines
   - CRITICAL at > 400 lines

3. **Public API docstring coverage** — every public function (no
   leading underscore) should have a docstring. CLI `main()` is
   conventionally exempt.

The audit does NOT check:
   - Cyclomatic complexity (would need radon or mccabe)
   - Coupling between modules (would need pydeps)
   - Type hint coverage (would need mypy --strict)
   - Test coverage (would need coverage.py)

These are valid future audits but out of scope for brick 20.

## Findings

### Module sizes (top 10)

| Lines | File | Status |
|-------|------|--------|
|  3673 | `engine/core/muninn_tree.py` | **CRITICAL** — over 3500 |
|  3040 | `engine/core/mycelium.py` | WARN — over 2500, just under critical |
|  2185 | `engine/core/forge.py` | OK |
|  2000 | `engine/core/muninn.py` | OK |
|  1775 | `engine/core/cube_analysis.py` | OK |
|  1661 | `engine/core/muninn_feed.py` | OK |
|  1447 | `engine/core/muninn_layers.py` | OK |
|  1337 | `engine/core/mycelium_db.py` | OK |
|  1131 | `engine/core/sync_backend.py` | OK |
|  1054 | `engine/core/cube.py` | OK |

### Function sizes (top 10)

| Lines | Function | Status |
|-------|----------|--------|
|   646 | `muninn_tree.py::boot` | **CRITICAL** — 1.5x over threshold |
|   503 | `muninn.py::main` | CRITICAL — but CLI dispatcher, expected |
|   478 | `scanner/bible_scraper.py::_core_bible` | CRITICAL — private helper |
|   409 | `muninn_tree.py::prune` | CRITICAL — barely over |
|   370 | `scanner/orchestrator.py::scan` | WARN |
|   228 | `muninn_feed.py::compress_transcript` | WARN |
|   208 | `muninn_layers.py::compress_line` | WARN |
|   198 | `forge.py::gen_props` | OK (just under) |
|   185 | `muninn_tree.py::grow_branches_from_session` | OK |
|   175 | `muninn_tree.py::doctor` | OK |

### Missing docstrings (12 public functions)

| File | Function | Brick 20 action |
|------|----------|-----------------|
| `forge.py::main` | CLI dispatcher | exempt |
| `muninn.py::main` | CLI dispatcher | exempt |
| `mycelium.py::main` | CLI dispatcher | exempt |
| `watchdog.py::main` | CLI dispatcher | exempt |
| `muninn.py::analyze_file` | NOT exempt | TODO future brick |
| `muninn_tree.py::init_tree` | NOT exempt | TODO future brick |
| `muninn_tree.py::load_tree` | NOT exempt | TODO future brick |
| `muninn_tree.py::show_status` | NOT exempt | TODO future brick |
| `muninn_layers.py::get_codebook` | **FIXED** | added in brick 20 |
| `muninn_layers.py::compress_section` | **FIXED** | added in brick 20 |
| `muninn_layers.py::compress_file` | **FIXED** | added in brick 20 |
| `muninn_layers.py::decode_line` | **FIXED** | added in brick 20 |

## Architectural debt acknowledged but not fixed in brick 20

### `muninn_tree.py` is too big (3673 lines)

This file holds: tree I/O, memory intelligence (recall scoring, ACT-R,
Ebbinghaus), TF-IDF, tree build, boot, prune, diagnostics, doctor,
status, inject, grow_branches, _bridge. It has been split before
(`muninn.py` 7959 -> 4 files commit `8d1485d`) but `muninn_tree.py`
is the part that grew back. Future split would be:

  muninn_tree.py        -> tree I/O, init, save/load only (~600 lines)
  muninn_recall.py      -> ebbinghaus, ACT-R, temperature (~500 lines)
  muninn_boot.py        -> the 646-line boot function (~700 lines)
  muninn_prune.py       -> the 409-line prune function (~500 lines)
  muninn_grow.py        -> grow_branches, bridge, etc. (~700 lines)

This is a 1-2 day refactor. Risk: wide blast radius (every test that
imports muninn_tree). Out of scope for brick 20 — documented here so
the next session knows it's a known smell.

### `boot()` is 646 lines

The boot function does: load tree, score branches via TF-IDF +
spreading activation + Ebbinghaus, pick branches under budget, load
mn files, expand session memory, format output. It's a single
sequential pipeline that's hard to split without losing data flow.

Future fix: extract 4-5 helper functions for the main phases:
  _boot_score_branches(query, tree)
  _boot_pick_under_budget(scores, budget)
  _boot_load_mn_files(branches)
  _boot_format_output(loaded, query)

Documented as architectural debt, not a bug.

### `mycelium.py` is 3040 lines (WARN)

Holds the entire Mycelium class (observe, fusion, decay, federation,
zones, anomalies, bridges, BFS subgraph builder). Class methods are
hard to extract without breaking the API. Future fix would be a mixin
split. Out of scope.

## Brick 20 action items SHIPPED

1. Architecture audit script + report (this doc)
2. 4 docstrings added to public functions in `muninn_layers.py`:
   - `get_codebook()`
   - `compress_section(header, lines)`
   - `compress_file(filepath)`
   - `decode_line(line)`
3. Pin test `tests/test_brick20_architecture.py` to lock the size
   thresholds. If anyone adds a 4000-line file or a 700-line function,
   the test fails and forces a discussion.

## Action items for future bricks

- BRICK 22 candidate: split muninn_tree.py into 4 files
- BRICK 23 candidate: refactor boot() into 5 helper functions
- BRICK 24 candidate: add docstrings to remaining 4 non-main public functions
- BRICK 25 candidate: cyclomatic complexity audit via radon
- BRICK 26 candidate: type hint coverage audit via mypy --strict

## How to reproduce

```bash
cd c:/Users/ludov/MUNINN-
python tests/test_brick20_architecture.py
# OR via pytest
python -m pytest tests/test_brick20_architecture.py -v
```
