# AUDIT V6 — Real Execution Audit

## Method

V6 ran every command on real data. No mock-only tests. Every function
executed against the production tree (2106 branches, 877K edges, 53K concepts).
Profiled with cProfile. Found what V1-V5 couldn't: the code WORKS on small data
but BREAKS on production scale.

## Performance Results

| Command | Before V6 | After V6 | Speedup |
|---------|-----------|----------|---------|
| boot() | **62s** | **17.2s** | 3.6x |
| prune() | **486s** (8 min) | **1.1s** | **442x** |

## Bugs Fixed

### BUG 17 — CRITICAL/FUNCTIONAL: spread_activation returns zero discrimination
**File**: mycelium.py:1015-1024
**Symptom**: All activation values ~0.50 +/- 0.003. Spreading activation
contributes ZERO useful signal to boot() scoring. Collins & Loftus 1975 = dead.
**Root cause**: A3 sigmoid (k=10, x0=median) receives tiny raw activations
(0.001-0.003 range after edge normalization). sigmoid(10 * 0.001) = 0.5025.
The sigmoid can't discriminate when inputs are clustered near x0.
**Fix**: Replaced sigmoid with min-max normalization [0, 1]. Now: top=1.0,
bottom=0.0, spread=0.40. Real discrimination restored.

### BUG 18 — CRITICAL/PERF: prune() I2 = O(n^2) NCD on ALL branches
**File**: muninn.py:3375-3410
**Symptom**: 486s for 2106 branches. 4.4M NCD calls x 3 zlib each = 13M zlib.
**Root cause**: I2 Competitive Suppression computed NCD for EVERY branch pair,
including 1983 hot branches that will never be pruned.
**Fix**: Only apply I2 to at-risk branches (recall < 0.4, capped at 500).
Also use symmetric NCD (compute once, apply both directions).

### BUG 19 — HIGH/PERF: boot() transitive_inference re-scans 877K edges per call
**Files**: mycelium.py:589-621, mycelium.py:1068-1107
**Symptom**: spread_activation + transitive_inference each scan all edges.
5 transitive_inference calls = 5 * 877K edge reads = 10.4s.
**Fix**: Added `_build_adj_cache()` — adjacency built once, reused by both
spread_activation and transitive_inference. 10.4s -> 0.1s.

### BUG 20 — MEDIUM/INTEGRITY: root.mn duplicate session entries
**File**: muninn.py:5112-5114
**Symptom**: "2026-03-12 x7.9..." appears twice in root.mn R: section.
**Root cause**: Both PreCompact and Stop hooks process same transcript,
both call _append_session_log. No dedup on write.
**Fix**: Dedup check before append + retroactive dedup of existing entries.

### BUG 21 — CRITICAL/PERF: _kicomp_filter = O(n^2) tiktoken calls
**File**: muninn.py:681-713
**Symptom**: 35.5s in boot() — 50% of total time. Called token_count() 1116
times, each re-encoding the ENTIRE remaining text (31ms per call).
**Root cause**: While loop drops one line at a time, re-counts ALL tokens
after each drop. O(n * text_length) tiktoken calls.
**Fix**: Estimate tokens per line (len//4), maintain running total. Drop
in one pass. Single final token_count for accuracy. 35.5s -> <0.1s.

### BUG 22 — MEDIUM/PERF: predict_next creates redundant Mycelium instance
**File**: muninn.py:2903
**Symptom**: boot() already has a Mycelium instance but predict_next creates
a second one, re-building the adjacency cache (4.5s wasted).
**Fix**: Pass existing mycelium via `_mycelium` parameter from boot().

### Also fixed from V5 (applied in this session):
- BUG 9 (CRITICAL): _MuninnLock mutual exclusion
- BUG 10 (MEDIUM): _semantic_rle retry loop condition
- BUG 11 (MEDIUM): _ncd identical string short-circuit
- BUG 12 (LOW): extract_tags adaptive thresholds
- BUG 15 (MEDIUM): grow_branches duplicate-instead-of-skip
- BUG 16 (LOW): prune I3 false anomaly on zero-fact branches

## Test Results

```
301 passed, 1 warning in 218.47s
```

Zero regressions. All fixes verified on real production data.

## What V1-V5 missed and why

V1-V5 audited code quality and correctness on small/mock data. V6 revealed that
the code was correct but CATASTROPHICALLY slow at production scale:

- `_kicomp_filter` was O(n * text_size) — invisible on 10-line tests, 35s on 2000 lines
- I2 was O(n^2) — fine on 5 test branches, 486s on 2106 real branches
- spread_activation sigmoid worked perfectly on test data (large raw spreads),
  failed silently on production data (877K edges = tiny normalized weights)
- adj cache irrelevant on mock data (3 edges), critical on 877K edges

The lesson: **performance bugs ARE correctness bugs when they block production**.

## Cumulative Audit Stats (V1-V6)

| Batch | Bugs | Key Finds |
|-------|------|-----------|
| V1 (batches 1-6) | ~10 | Foundation fixes |
| V2 (convergence) | 3 | Cross-validation |
| V4 (extermination) | 3 | Learned fillers data loss, hub domination |
| V5 (deep systems) | 6 | Lock exclusion, NCD identity, RLE condition |
| V6 (real execution) | 6 | **boot 62->17s, prune 486->1.1s, spread_activation restored** |
| **Total** | **~28** | |
