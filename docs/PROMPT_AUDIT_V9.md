# AUDIT V9 — Deep Scan Senior Dev Mode

Date: 2026-03-12
Engine: muninn.py v0.9.1 (4578 lines) + mycelium.py (~1250 lines) + mycelium_db.py
Commit base: 549c85a (post Battery V4)

---

## RESULTATS GLOBAUX

| Severity | Count |
|----------|-------|
| HIGH     | 4     |
| MEDIUM   | 14    |
| LOW      | 16    |
| **TOTAL** | **34** |

---

## HIGH — 4 bugs

### H1. prune() KeyError after sleep consolidation
- FILE: muninn.py L3573
- TYPE: CRASH
- WHAT: Cold branch re-compression loop does `node = nodes[name]` without checking if the node was already removed by `_sleep_consolidate`.
- WHY: `_sleep_consolidate` calls `nodes.pop(m, None)` for merged branches. But the `cold` list still contains those names. The dead deletion loop at L3759 has `if name not in nodes: continue` but the cold re-compression loop at L3573 does NOT.
- FIX: Add `if name not in nodes: continue` at top of loop at L3573.

### H2. id_to_name rebuilt O(N*M) per observe() in P41
- FILE: mycelium.py L366
- TYPE: PERF
- WHAT: Inside the per-concept loop in `observe()`, `id_to_name = {v: k for k, v in self._db._concept_cache.items()}` is rebuilt from scratch for EVERY concept. 50 concepts * 100K cache entries = 5M dict operations per call.
- FIX: Build `id_to_name` once before the loop.

### H3. upsert_connection() and upsert_fusion() never commit
- FILE: mycelium_db.py L216-257, L343-361
- TYPE: DATA_LOSS
- WHAT: `set_meta()` commits. `upsert_connection()` and `upsert_fusion()` do NOT. Callers in mycelium.py compensate by calling `self._db._conn.commit()` directly, but this is fragile. Any new caller will silently lose data on crash.
- FIX: Add `self._conn.commit()` to every write method, or document explicit commit requirement.

### H4. delete_connection() never commits
- FILE: mycelium_db.py L363-373
- TYPE: DATA_LOSS
- WHAT: Three DELETE statements executed but never committed. Same root cause as H3.
- FIX: Same as H3.

---

## MEDIUM — 14 bugs

### M1. _line_density max vs min for long narrative
- FILE: muninn.py L676-677
- TYPE: LOGIC
- WHAT: `score = max(score, 0.1)` should be `min(score, 0.1)`. Long narrative lines (>120 chars, no digits) should be CAPPED at 0.1 density, but `max()` only FLOORS. A long narrative with incidental key=value match keeps inflated score, so KIComp drops the wrong lines.

### M2. Causal protection regex trailing space
- FILE: muninn.py L882
- TYPE: SILENT_FAIL
- WHAT: `car |donc ` in the alternation has trailing space. Then `\s+\S+` requires ANOTHER space. So `"car raison"` (single space, normal French) is NOT protected. The causal connector may get stripped by L2.
- FIX: Remove trailing spaces from `car ` and `donc ` inside the alternation.

### M3. R1-Compress fallback chunker can produce 1 mega-chunk
- FILE: muninn.py L1683
- TYPE: LOGIC
- WHAT: When text has many short lines (e.g., 2000 lines, 8000 chars), `len(text) // 6000 = 1`, producing 1 chunk. The `len(chunks) >= 2` check fails, sending everything to a single API call.
- FIX: `max(2, len(text) // 6000)`.

### M4. Last chunk silently dropped in grow_branches fallback
- FILE: muninn.py L1912
- TYPE: DATA_LOSS
- WHAT: In the no-header fallback path, last chunk with <5 lines (`body.count("\n") >= 4` fails) is silently dropped. Content lost.

### M5. Missing branch file causes segment content to be silently lost
- FILE: muninn.py L1953
- TYPE: DATA_LOSS
- WHAT: When `should_merge=True` but target file is missing, code sets `merged=True` and breaks. The segment is neither merged nor created as new branch. Content vanishes.
- FIX: When file is missing, fall through to create new branch instead.

### M6. generate_winter_tree shows 0 connections in SQLite mode
- FILE: muninn.py L4212-4213
- TYPE: SILENT_FAIL
- WHAT: Reads `mycelium.data["connections"]` which is always `{}` in lazy mode. Should check `mycelium._db is not None` and use DB methods like `generate_root_mn` does.

### M7. adapt_k modifies throwaway Mycelium instance
- FILE: muninn.py L3063-3065
- TYPE: SILENT_FAIL
- WHAT: `adapt_k()` creates `m = Mycelium(repo)`, sets `m._sigmoid_k`, then discards `m`. Change has zero lasting effect.

### M8. feed_history re-compresses all transcripts every run
- FILE: muninn.py L5755
- TYPE: PERF
- WHAT: Marker check uses `jsonl_file.stem` but `compress_transcript` writes timestamp-based names. Stems never match, so every call re-compresses everything.
- FIX: Use a separate tracking file or match on content hash.

### M9. query_ids NameError in pull_from_meta when query_concepts=None
- FILE: mycelium.py L2229
- TYPE: CRASH
- WHAT: When `query_concepts` is None and `self._db is not None`, `query_ids` is never defined. Line 2229 `if self._db is not None and query_ids:` raises NameError.
- FIX: Initialize `query_ids = set()` before the if/else block.

### M10. _adj_cache never invalidated after observe/decay
- FILE: mycelium.py L71, L599-632
- TYPE: LOGIC
- WHAT: Adjacency cache built once, never cleared. After `observe()` adds edges or `decay()` removes them, `spread_activation()` uses stale graph data within the same session.
- FIX: Set `self._adj_cache = None` in `observe()` and `decay()`.

### M11. update_connection_count() never commits
- FILE: mycelium_db.py L375-385
- TYPE: DATA_LOSS
- WHAT: Same root cause as H3/H4. UPDATE without commit.

### M12. add_zone_to_edge() never commits
- FILE: mycelium_db.py L464-475
- TYPE: DATA_LOSS
- WHAT: Same root cause. INSERT without commit.

### M13. _get_or_create_concept swallows all sqlite3.Error
- FILE: mycelium_db.py L142-143
- TYPE: SILENT_FAIL
- WHAT: `except sqlite3.Error: pass` silently eats disk-full, corruption, and lock errors. Caller gets cryptic ValueError instead of the real error.

### M14. No foreign key enforcement, orphaned edge_zones possible
- FILE: mycelium_db.py L74-116
- TYPE: DATA_LOSS
- WHAT: `PRAGMA foreign_keys=ON` never set. Direct SQL deletes on `edges` table (mycelium.py L801) leave orphaned `edge_zones` rows.

---

## LOW — 16 bugs

### L1. except (ImportError, Exception) catches everything
- muninn.py L114 — `Exception` is superclass of `ImportError`, silently swallows real errors.

### L2. L5 rules with non-word chars never match
- muninn.py L992 — `\b##\ \b` never matches because # is non-word character.

### L3. blind_spots_total miscounts
- muninn.py L2649 — divides concept set size by 2, but concepts can appear in multiple pairs.

### L4. Variable m shadows mycelium instance
- muninn.py L2555 — V5B loop `for m in pop if m != n` shadows outer `m = Mycelium(...)`.

### L5. Bloom novelty threshold 5% vs 10% doc mismatch
- muninn.py L2583 — comment says 10%, code says 5%.

### L6. Session tail uses 4 chars/token, compressed text is 3
- muninn.py L2708 — overshoots budget by ~33%.

### L7. I3 line_counts vs fact_ratios from different sources
- muninn.py L3522 — metadata vs actual file line count.

### L8. _load_relevant_sessions budget reduction no effect
- muninn.py L5150 — `budget -= tokens` rebinds local int, caller unaffected.

### L9. Double-close fd in _register_repo error path
- muninn.py L4296 — caught by try/except but still logic error.

### L10. ingest char-based ratio inconsistent
- muninn.py L5926 — uses len ratio while rest of codebase uses tiktoken.

### L11. Dead connection removal unreachable
- mycelium.py L787-793 — `count / 2^n` never reaches 0, decay never deletes edges.

### L12. Inconsistent min word length 3 vs 4 chars
- mycelium.py L415/438 — "API", "GPU", "NCD" captured in small texts, dropped in large.

### L13. CLI simulate/detect read empty data stubs
- mycelium.py L2536 — `data["connections"]` always empty in lazy mode.

### L14. Migration INSERT OR REPLACE vs UPSERT
- mycelium_db.py L692 — REPLACE deletes+inserts, can orphan edge_zones.

### L15. Integer comparison fails on legacy TEXT values
- mycelium_db.py L532 — TEXT vs INTEGER mixed-type SQLite comparison.

### L16. upsert_fusion ON CONFLICT skips fused_at update
- mycelium_db.py L355 — re-fused concepts keep original date.

---

## TOP 5 BUGS PAR IMPACT

1. **H1 prune() KeyError** — CRASH en production apres sleep consolidation. 1 ligne a ajouter.
2. **H3+H4 missing commits** — DATA_LOSS silencieuse sur crash. Toutes les ecritures mycelium_db sauf set_meta().
3. **M9 query_ids NameError** — CRASH dans pull_from_meta(None) en mode SQLite. boot() path par defaut.
4. **M10 _adj_cache stale** — spreading activation utilise un graphe perime apres observe(). Affecte boot() scoring.
5. **M5 missing branch file** — contenu de segment perdu silencieusement pendant grow_branches merge.

## PATTERNS RECURRENTS

1. **Missing commits** (H3, H4, M11, M12): 4 methodes write dans mycelium_db n'appellent pas commit(). Root cause unique.
2. **Stale cache** (M10, M7): caches jamais invalides apres mutation.
3. **Silent data loss** (M4, M5): contenu perdu sans warning dans grow_branches.
4. **Dict/lazy mode disconnect** (M6, L13): code lit `data["connections"]` qui est vide en SQLite mode.

---

## ZERO BUGS FOUND IN

- tokenizer.py — clean, correct fallback logic
- sentiment.py — VADER wrapper, circumplex_map correct
