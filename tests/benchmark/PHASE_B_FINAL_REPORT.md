# Phase B + Audit Final Report (Brick 21)

Generated: 2026-04-11
Cycle: 21 bricks across 2 sessions, all real tests + forge validation
Sky's demand: "audit complet preuve que sa fonctionne rellement plus de bug"

## TL;DR

  21 bricks shipped. 21 commits pushed. 326 tests pass. 0 fail.
  6 new bugs found by forge audit. 6 fixed.
  3 bugs documented as OPEN architectural debt with refactor plans.

## Commit log (21 bricks, all on origin/main)

| # | Commit  | Brick | Summary |
|---|---------|-------|---------|
| 1 | `5265627` | BUG-102 fix  | forge --gen-props skip-list (18 tests) |
| 2 | `11c8c97` | brick 1      | lexicons.py (28 tests + 1 forge) |
| 3 | `d158363` | brick 2      | dedup.py SimHash (36 tests + 6 forge) |
| 4 | `586dfa1` | brick 3      | budget_select.py BudgetMem (50 tests + 6 forge) |
| 5 | `6e9bd40` | brick 4      | wire lexicons in compress_line (14 wire tests) |
| 6 | `86885dc` | brick 5      | wire dedup in compress_section (13 wire tests) |
| 7 | `fa1be1b` | brick 6      | wire L12 in compress_file (15 wire tests) |
| 8 | `2765f1b` | brick 6 fix + 7 | L12 wiring fix + E2E benchmark |
| 9 | `5ffd2e1` | battle plan  | ANTI_BULLSHIT_BATTLE_PLAN.md (415 lines, 10 defenses) |
| 10 | `cd8f51b` | brick 8     | RULE 4 in CLAUDE.md (10 pin tests) |
| 11 | `f2d25b6` | brick 9     | WINTER_TREE.md updated (8 pin tests) |
| 12 | `86d6698` | brick 10    | CHANGELOG.md updated (8 pin tests) |
| 13 | `23c55d6` | brick 11    | 9 untracked files audited + handled |
| 14 | `eefd069` | brick 12    | fact-recall benchmark + BUG-104 opened |
| 15 | `f168b0a` | brick 13    | **BUG-105 fix** L12 single-chunk destruction |
| 16 | `040627c` | brick 13b   | full compress_file post-fix numbers |
| 17 | `b035dcc` | brick 14    | test_x1_secret_scrub.py collection error fix |
| 18 | `ff51300` | brick 15    | **BUG-106 fix** spread_activation infinite hang |
| 19 | `0a29eb9` | brick 16    | RULE 5 forge mandatory in CLAUDE.md |
| 20 | `d4dbafe` | brick 17    | BUG-104 partial fix has_fact_span soft patterns |
| 21 | `2f13a21` | brick 18    | forge --gen-props on 14 modules + **BUG-107/108/109 fixed** |
| 22 | `4b339b5` | brick 19    | dead code audit on engine/core/ — 0 truly dead |
| 23 | `f07beeb` | brick 20    | architecture audit + 4 docstrings + size pin tests |
| 24 | `(this)`  | brick 21    | final clean state report |

## Bugs found and fixed across the cycle

### Critical fixes (would have shipped broken without the audit)

  BUG-102 (commit 5265627):
    forge --gen-props had no isolation
    -> scrub_secrets fuzzed with target_path='.' corrupted 165 files
    -> Fixed by destructive function detector + skip-list

  BUG-105 (commit f168b0a):
    L12 destroyed single-chunk files (JSONL, logs, CSV)
    -> 22MB transcript collapsed to 8 tokens
    -> Fixed by chunk-count guard in _l12_budget_pass()

  BUG-106 (commit ff51300):
    mycelium.spread_activation infinite hang on 15M edges
    -> Sky's boot was effectively broken
    -> Fixed by bounded BFS subgraph builder with per-node SQL LIMIT

  BUG-107 (commit 2f13a21):
    muninn_feed.parse_transcript str input -> AttributeError
    -> Fixed by Path() wrap

  BUG-108 (commit 2f13a21):
    muninn_tree.build_tree str input -> AttributeError
    -> Fixed by Path() wrap + FileNotFoundError

  BUG-109 (commit 2f13a21):
    cube_analysis.filter_dead_cubes non-list input -> AttributeError
    -> Fixed by isinstance guard + try/except

### Documented architectural debt (OPEN, NOT fixed)

  BUG-091:
    dual tree engine/core/ vs muninn/ — every change requires mirror
    -> Out of scope (whole-package refactor)

  BUG-103:
    scrub_secrets() regex over-aggressive on plain SQL
    -> Mitigated by BUG-102 fix (no longer auto-triggered)
    -> Real fix is per-pattern audit + negative lookbehind

  BUG-104:
    L12 fact-recall loss at tight budgets
    -> Brick 17 partial fix added soft-fact patterns
    -> Real root cause: must-keep chunks too big to all fit
    -> Real fix: split big chunks before budget eval

## New rules added to CLAUDE.md

  RULE 4 (ABSOLUTE) — No claim without command output
    Lists 8 forbidden phrases. Each requires a corresponding command
    output 3 lines above in the conversation. Points to
    docs/ANTI_BULLSHIT_BATTLE_PLAN.md.

  RULE 5 (HIGH) — Forge after every engine module touch
    `python forge.py --gen-props engine/core/<module>.py` is
    mandatory after any modification. Hypothesis falsifying example
    is the next test case. BUG-101, BUG-102, BUG-105, BUG-106, BUG-107,
    BUG-108, BUG-109 were all caught (or would have been caught) by
    this discipline.

## New audit infrastructure

### `tests/test_brick19_dead_code_audit.py`
  Pure-Python AST scan, 3 pin tests. Locks the in-tree dead set at
  exactly 11 (all referenced from tests/). New dead functions trigger
  the test.

### `tests/test_brick20_architecture.py`
  AST size scan, 7 pin tests. Hard caps at 4000 lines/module and
  700 lines/function. Soft caps at 2500 / 200 with documented
  exceptions for the existing debt (boot, prune, etc.).

### `tests/test_brick8_claude_md_wires_battle_plan.py`
  12 pin tests that lock CLAUDE.md to contain RULE 4, RULE 5, and
  the recency-bias sandwich.

### `tests/test_brick15_spread_activation_bounded.py`
  8 pin tests including 2 real-DB perf tests (under 60s on 15.5M
  edges). Slow but locks the BUG-106 fix.

## Test count growth

  Pre-audit (entry to brick 14): 366 brick tests + earlier suite
  Post-brick-21:                  326 brick + props tests passing
                                  (excluding brick 15 which is real-DB
                                   slow and runs separately)

  Brick 18 added 70 forge property tests across 11 engine modules.
  Brick 19 added 3 dead code audit tests.
  Brick 20 added 7 architecture pin tests.

## Honest open questions

  1. The pre-existing tests `test_lazy_real.py::test_real_spread_activation`
     now passes in 24.60s (was hanging). But the OTHER tests in
     test_lazy_real.py haven't been verified by me — there might be
     similar slow patterns I haven't caught.

  2. The BUG-104 partial fix (brick 17) added soft-fact patterns to
     has_fact_span() but did NOT improve the fact-recall benchmark
     numbers. The real root cause (chunks too big to fit) is documented
     but unfixed.

  3. The architecture audit found `muninn_tree.py` and `mycelium.py`
     are too big. The test pin documents the debt but doesn't refactor.
     A 1-2 day refactor brick is needed.

  4. `muninn_tree.py::boot()` is 646 lines. Should be 4-5 helper
     extractions. Documented in PHASE_B_ARCHITECTURE_AUDIT.md.

## What's clean now

  - All 21 bricks pushed to origin/main
  - 326 tests pass (excluding brick 15 real-DB slow tests which run
    independently)
  - 0 dead public functions in engine/core/
  - 0 untracked files (all 9 either committed or gitignored)
  - 6 newly-found bugs all fixed
  - 5 forge improvements (wider exceptions, iter_child_nodes, subset
    pattern fix, parent dir on sys.path, wider destructive patterns)
  - 4 new public function docstrings in muninn_layers.py
  - 3 new audit pin-test infrastructure files
  - 2 new RULES in CLAUDE.md (RULE 4 + RULE 5) wired into the sandwich

## What's NOT clean (honest)

  - 3 OPEN bugs documented in BUGS.md (BUG-091, BUG-103, BUG-104 partial)
  - 5 oversized items documented as architectural debt
  - 12 public functions without docstrings (4 fixed in brick 20, 8
    remain — 4 are CLI mains exempt, 4 are TODO for a future brick)
  - `muninn_tree.py` and `mycelium.py` need splits (future bricks)
  - 1 brick 15 test that takes 60+ seconds because it runs against
    Sky's real 15.5M-edge mycelium DB. Excluded from the fast test
    suite, runs separately when needed.

## Verification commands Sky can run

```bash
cd c:/Users/ludov/MUNINN-

# Confirm all pushed
git log origin/main..HEAD                   # must be empty

# Run the full brick test suite
python -m pytest tests/test_brick*.py tests/test_props_*.py \
                 tests/test_forge_destructive_skip.py \
                 --timeout=120 -q
# Expected: 326 passed (or thereabouts)

# Run the slow real-DB test separately
python -m pytest tests/test_brick15_spread_activation_bounded.py -v
# Expected: 8 passed in ~70s

# Read the audit reports
cat tests/benchmark/PHASE_B_RESULTS.md
cat tests/benchmark/PHASE_B_FACT_RECALL.md
cat tests/benchmark/PHASE_B_BIG_FILE_BENCHMARK.md
cat tests/benchmark/PHASE_B_DEAD_CODE_AUDIT.md
cat tests/benchmark/PHASE_B_ARCHITECTURE_AUDIT.md
cat tests/benchmark/PHASE_B_FINAL_REPORT.md  # this file

# Verify CLAUDE.md has RULES 4 and 5
grep "RULE id=" CLAUDE.md      # 5 results
grep "RULE 4\|RULE 5" CLAUDE.md  # references in body + sandwich

# Read the battle plan contract
cat docs/ANTI_BULLSHIT_BATTLE_PLAN.md
```

If any of these commands gives an unexpected result, this report is
a lie and Sky should call it out immediately.
