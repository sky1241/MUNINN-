# MUNINN — Winter Tree (Carte Technique)

> Ce fichier est une CARTE DE NAVIGATION pour Claude. Pas un changelog.
> Objectif: savoir EXACTEMENT ou chercher quoi dans le code, avec les numeros de lignes.
> Mis a jour: 2026-04-22. Engine: ~22K lignes, 18 fichiers. UI: ~4900 lignes (+5197 ref), 20 fichiers. Tests: **2200+ collected, PASS, 27 skip, 0 FAIL**.
> **Cube L1: 71/80 SHA (88.8%) verified, 79-80/80 predicted (99-100%).** 20 fixes total (fixes 1-20). 175 -> 0 gap lines (100% anchor coverage). 8-language support (Go/Python/Rust/JSX/C/TS/COBOL/Kotlin). Smart formatter detection + auto-install (doctor --fix).
> Split: muninn.py (7959L -> 4 fichiers), cube.py (3273L -> 3 fichiers: cube.py 1553L, cube_providers.py 1952L, cube_analysis.py 1759L).
> Package: muninn/ pip-installable. _ProxyModule (getattr+setattr+delattr). conftest.py pre-load.
> UI: Phase 0-9 COMPLETE — 32 briques (B-UI-00..32), PyQt6 6.10.2 + pytest-qt, 152 UI tests PASS.
>
> **Leak Intel Battle Plan (2026-04-10): 16 chunks complete.**
> See CHANGELOG.md and docs/CLAUDE_CODE_LEAK_INTEL.md.
>
> Hooks: 4 -> **12 distinct scripts** registered under **10 hook events**:
>   UserPromptSubmit, PreCompact, SessionEnd, Stop, PostToolUseFailure,
>   SubagentStart, **PreToolUse (3 entries: bash-destructive + bash-secrets + edit-hardcode)**,
>   PostToolUse, Notification, ConfigChange.
>
> CLAUDE.md: 8 RULES -> **3 RULES** (chunks 9-10 measured each one with API,
> kept only those with proven causal effect on Opus 4.6: hardcode +100%,
> destructive +100%, secrets +20%). 173 lines, under Anthropic 200-line target.
>
> **Path-scoped rules**: `.claude/rules/python.md` and `.claude/rules/git.md`
> extend RULES with technical detail, loaded only when matching files are touched.
>
> Anti-Adversa clamp on injected content (refuses >30 chained shell commands).
> Anthropic native auto-memory disabled (single source of truth = Muninn).
>
> **Audit chunks 16+17 (2026-04-10)**: 10 bugs found and fixed.
> Chunk 16 (hand audit): 9 bugs in destructive patterns + payload type-checks.
> Chunk 17 (forge + Hypothesis property tests): BUG-101 found by adversarial
>   property testing — `_truncate_with_marker` was producing oversized output
>   when `max_chars < 100`. Hand-written tests in chunk 5 missed it because
>   they only used "reasonable" max_chars (≥1000).
> See BUGS.md BUG-092 to BUG-101. 88 new anti-regression tests added.
>
> **Audit brick 22 (2026-04-11)**: full pytest suite triage. 11 distinct
> failures fixed across 9 test files + 2 source modules:
>   - test_chunk13: bumped CLAUDE.md cap 200->300 (RULE 4+5 added in bricks 8+16)
>   - test_cube_real_api: opt-in env var MUNINN_RUN_REAL_API_TESTS=1 (was hanging)
>   - test_cube_real_llm: opt-in env var MUNINN_RUN_REAL_LLM_TESTS=1 (Ollama 500)
>   - test_phase4_tls: sys.path setup + BUG-091 isinstance fix
>   - test_tier2_b4 + test_tier2_wiring: @timeout(90) for real-DB calls
>   - test_ui_navi (4 fixes): timer 16->15ms, _tutorial_active=True at init,
>     show_first_launch button assertion
>   - test_ui_neuron_map (2 fixes): _cube_angle=0.0 to disable rotation
>   - test_ui_terminal (2 fixes): fake provider stub via monkeypatch
>   - **BUG-110**: pull_from_meta hung on user's 1.8GB home meta DB during
>     temp-repo tests. Fix: 100MB threshold guard mirrored in both trees.
>   Result: 2086 passed / 27 skipped / 0 fail (was hanging or failing on ~12 tests)
>
> **266 chunk tests / 0 regression** (was 178 before audit). Empirical eval
> harness in tests/eval_harness_chunk{9,11}.py. Hypothesis property tests
> in tests/test_audit_hypothesis_hooks.py + tests/test_props__secrets.py.

## Architecture

```
        [1285 tests, 0 FAIL]                +5 Cime (validation)
       /    \
    [.mn]  [.mn]                            +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                              +2 Branches (metadata arbre)
      |
   muninn.py 1532L (orchestrateur)          +1 Tronc
     muninn_layers.py 1294L (compression)
     muninn_tree.py 3649L (arbre+boot+intelligence)
     muninn_feed.py 1640L (feed+hooks)
      |
   [mycelium.py 3145L + db 1336L]            0 SOL — champignon vivant
      |
   [sync_backend.py 1128L]               -0.5 Sync federe (SharedFile/Git/TLS)
      |
   [vault.py + sync_tls.py 601L]           -1 Sous-sol — securite + reseau
      |
   cube.py 1553L (core+formatters+check)    -2 Fondations — resilience
     cube_providers.py 1952L (LLM+reconstruction+20 fixes)
     cube_analysis.py 1759L (analyse+CLI)
      |
   [wal_monitor 109L + tokenizer 43L]      -3 Racines — infrastructure
      |
   muninn/ui/ ~4470L (18 fichiers, +5197 ref) -4 Interface — desktop PyQt6
```

---

## muninn.py — Orchestrateur (1532 lignes)

Slim entry point: globals, scan, bootstrap, CLI, hooks, secrets.

### Globals & Config (1-114)
| Element | Lignes | Role |
|---------|--------|------|
| VERSION, _REPO_PATH, _CB... | 1-60 | Globals mutables (partages via _ModRef) |
| UNIVERSAL_RULES | 62-72 | Dict FR->EN compact (done, wip, fail...) |
| _SECRET_PATTERNS | 74-108 | Regex detection secrets (GitHub PAT, AWS, API keys, FR) |
| _COMPILED_SECRET_PATTERNS | 111 | P10: compiled regex cache |

### Scan & Bootstrap (115-407)
| Fonction | Lignes | Role |
|----------|--------|------|
| scan_repo | 115-275 | R5: auto-genere codebook local |
| analyze_file | 276-301 | Analyse fichier unique |
| bootstrap_mycelium | 302-357 | Cold start mycelium depuis repo |
| _bootstrap_branches | 358-407 | Genere branches depuis scan |

### Generate & Registry (408-695)
| Fonction | Lignes | Role |
|----------|--------|------|
| generate_root_mn | 408-535 | Genere root.mn depuis scan |
| generate_winter_tree | 536-603 | Auto-genere WINTER_TREE.md |
| _repos_registry_path | 604-608 | Path vers repos.json |
| _load_repos_registry | 609-620 | Charge registre repos |
| _register_repo | 621-666 | Enregistre repo dans registre |
| _generate_bridge_hook | 686-808 | Genere bridge_hook.py (UserPromptSubmit) avec anti-Adversa clamp depuis chunk 4 |
| _generate_post_tool_failure_hook | 811-944 | CHUNK 4: genere post_tool_failure_hook.py — auto-feed errors.json (P18 real-time) |
| _generate_subagent_start_hook | 945-1076 | CHUNK 5: genere subagent_start_hook.py — inject Muninn boot dans sub-agents |

### Secrets & CLI (696-1509)
| Fonction | Lignes | Role |
|----------|--------|------|
| _shannon_entropy / _has_char_diversity | 696-720 | Detection secrets heuristique |
| _check_secrets | 721-748 | Check un texte pour secrets |
| install_hooks | 1077-1170 | Install 6 hooks: UserPromptSubmit + PreCompact + SessionEnd + Stop + PostToolUseFailure (chunk 4) + SubagentStart (chunk 5) |
| scrub_secrets | 884-957 | Scan+redact secrets dans .mn |
| purge_secrets_db | 958-1006 | Purge secrets dans DB mycelium |
| main() | 1007-1509 | CLI argparse: boot/feed/compress/prune/status/diagnose/inject/... |

---

## muninn_layers.py — Compression Pipeline (1294 lignes)

L0-L7 + L10-L11 + L9: toutes les couches de compression.

### Codebook & Utils (71-120)
| Fonction | Lignes | Role |
|----------|--------|------|
| load_codebook | 71-97 | Charge rules compression (universal + mycelium) |
| _safe_path | 98-110 | Sanitize paths display (max 3 segments) |
| get_codebook | 111-120 | Wrapper codebook avec cache |

### Compression L0-L7 (121-713)
| Fonction | Lignes | Role |
|----------|--------|------|
| _line_density | 121-167 | Score densite info par ligne (0=bruit, 1=fait) |
| _kicomp_filter | 168-244 | Drop lignes basse-densite si overflow budget |
| _ncd | 245-264 | Normalized Compression Distance (zlib) |
| compress_line | 265-469 | Pipeline: L1 markdown, L3 phrases, L2 fillers, L4 numbers, L5 rules, L6 mycelium, L7 kv |
| extract_facts | 470-577 | Extraction nombres, dates, identifiers, kv, code patterns |
| tag_memory_type | 578-590 | Tags P14: D>/B>/F>/E>/A> |
| compress_section | 591-713 | Compresse section (P14 tags + P26 line dedup + P27 read dedup) |

### Contradiction Resolution C7 (714-819)
| _resolve_contradictions | 714-819 | Skeleton dedup, last-writer-wins |

### Compression L10-L11 (820-1058)
| Fonction | Lignes | Role |
|----------|--------|------|
| _novelty_score | 820-885 | Score nouveaute (patterns connus vs nouveaux) |
| _generate_cue | 886-943 | Bartlett 1932: genere cue de rappel |
| _cue_distill | 944-991 | L10: remplace connaissances generiques par cues |
| _extract_rules | 992-1058 | L11: Kolmogorov factorisation patterns repetitifs |

### Compression L9 + File (1059-1294)
| Fonction | Lignes | Role |
|----------|--------|------|
| _llm_compress_chunk | 1059-1083 | L9: chunk unique via Claude Haiku |
| _llm_compress | 1084-1161 | L9: R1-Compress section-chunked API |
| compress_file | 1162-1216 | Pipeline complet fichier |
| decode_line | 1217-1229 | Decode ligne compressee |
| verify_compression | 1230-1294 | Verifie qualite (facts preserves, ratio) |

### Phase B Wirings (2026-04-10) — bricks 4, 5, 6
| Wiring | Lignes | Role |
|--------|--------|------|
| `_LEXICONS_TIER1_PATTERNS` (module-level) | ~9-18 | Brick 4: lexicons tier1 patterns cached at init from `lexicons.get_safe_filler_patterns("tier1")`. 43 patterns, intensifiers + epistemic hedges. Pure additive in `compress_line()` L2 block. |
| `_DEDUP_AVAILABLE` + `_simhash`/`_hamming` import | ~20-26 | Brick 5: SimHash + hamming distance imported from `dedup.py` for `compress_section()` body dedup. |
| `_dedup_body_lines(lines)` helper | ~28-72 | Brick 5: pure helper called from `compress_section()` after the body collection, BEFORE the join. Tagged lines (B>/E>/F>/D>/A>) and short lines (<20 chars) NEVER deduped. Strict defaults k=4 shingles, threshold=3. |
| `_BUDGET_SELECT_AVAILABLE` + `_budget_select_impl` import | ~74-82 | Brick 6: BudgetMem L12 chunk selection from `budget_select.py`. |
| `_l12_budget_pass(text)` helper | ~84-118 | Brick 6: reads `MUNINN_L12_BUDGET` env var, applies BudgetMem chunk selection on raw text BEFORE secret redaction. Tiktoken-aware (`tokenizer.count_tokens` callback). OFF by default for full backward compat. |
| `compress_line()` L2 inline tier1 loop | ~389-394 | 4-line addition: second `re.sub` loop using `_LEXICONS_TIER1_PATTERNS` after the existing `_FILLER` loop. Pure additive, no overlap with hand-picked list. |
| `compress_section()` body dedup call | ~717-722 | 1-line addition: `body = _dedup_body_lines(body)` after L0-L11 line compression, before the join. |
| `compress_file()` L12 pre-pass | ~1262-1268 | 1-line addition: `text = _l12_budget_pass(text)` after secret redaction, before section split. Wired here (not after L11) because raw text has `\n\n` paragraph separators that BudgetMem expects. |

---

## engine/core/lexicons.py — Vendored MIT word lists (Phase B brick 1)

Pure data module, ZERO side effects. Mirrored to `muninn/lexicons.py`.
Imported by `muninn_layers.py` to extend L2 filler stripping.

| Constant / function | Lignes | Role |
|---------------------|--------|------|
| `MIT_FILLERS_EN`  | 47-63  | 83 entries verbatim from github.com/words/fillers (MIT) |
| `MIT_HEDGES_EN`   | 67-95  | 162 entries verbatim from github.com/words/hedges (MIT) |
| `MIT_WEASELS_EN`  | 99-119 | 116 entries verbatim from github.com/words/weasels (MIT) |
| `DISCOURSE_MARKERS_EN` | 123-138 | 50 Cambridge dictionary markers |
| `FRENCH_FILLERS`  | 142-149 | 22 French agent transcript fillers |
| `L2_TIER1_SAFE`   | 153-167 | 43 ultra-conservative — adverbs of intensification + non-factual hedges. **Default tier wired in compress_line()**. |
| `L2_TIER2_MODERATE` | 171-178 | 63 — adds soft quantifier-adjacent words for chat/meeting compression |
| `get_tier3_raw()` | 184-199 | Pure helper: de-duped union of all MIT lists, sorted by length desc |
| `DANGEROUS_NEVER_ADD` | 203-225 | Frozenset of 83 words that MUST NOT be in any tier (quantifiers, modals, action verbs, directional words, magnitudes) — safety net |
| `get_safe_filler_patterns(tier)` | 228-260 | Pure helper: returns regex patterns for tier1/tier2/tier3/discourse/french |
| `stats()` | 263-274 | Pure helper: returns counts for every list and tier |

Tests: `tests/test_brick1_lexicons.py` (28 tests pass) +
`tests/test_props_lexicons.py` (1 forge property test pass).
Forge BUG-102 detector confirmed: 0 destructive functions in this module.

---

## engine/core/dedup.py — SimHash near-duplicate detection (Phase B brick 2)

Charikar SimHash (STOC 2002) for line-level near-duplicate detection.
Pure-Python, zero deps (uses `hashlib.blake2b` from stdlib).
Mirrored to `muninn/dedup.py`. Imported by `muninn_layers.py` brick 5.

| Function | Lignes | Role |
|----------|--------|------|
| `_tokenize(text)` | 50-54 | Pure: lowercased word tokens via `\b\w+\b` |
| `_shingles(tokens, k=4)` | 57-66 | Pure: word k-grams sliding window, falls back to unigrams for short text |
| `_hash_feature(feature, bits)` | 73-81 | Pure: blake2b-based feature hash, configurable bit width (32/64/128) |
| `simhash(text, bits=64, shingle_size=4)` | 84-117 | Pure: Charikar fingerprint via +/-1 sum across all bit positions |
| `hamming_distance(a, b)` | 120-124 | Pure: bit_count of XOR — number of differing bits |
| `similar(a, b, threshold=3, ...)` | 127-141 | Pure: boolean wrapper around simhash + hamming |
| `dedup_lines(lines, threshold=3, ...)` | 147-188 | Pure: removes near-dups in-order, keeps FIRST occurrence, skips short lines |
| `dedup_paragraphs(text, threshold=3, ...)` | 191-211 | Pure: splits on `\n\n`, calls dedup_lines, rejoins |
| `stats(text=, lines=)` | 214-238 | Pure diagnostic: token count, shingle count, dedup ratio |

Operating range (empirically measured in tests):
- **STRICT** (defaults k=4, t=3): catches typo / punctuation / whitespace / case
- **LOOSE** (k=1, t=14): also catches polling-loop counter drifts
- **NOT CAUGHT**: prefix paraphrases, word-order changes, synonym swaps

Tests: `tests/test_brick2_dedup.py` (36 tests pass) +
`tests/test_props_dedup.py` (6 forge property tests pass).
Forge BUG-102 detector: 0 destructive functions.

---

## engine/core/budget_select.py — BudgetMem L12 chunk selection (Phase B brick 3)

Implementation of BudgetMem (arxiv 2511.04919, 2025) — training-free
chunk-level selective memory using interpretable features. Pure-Python,
zero deps. Mirrored to `muninn/budget_select.py`. Imported by
`muninn_layers.py` brick 6, opt-in via `MUNINN_L12_BUDGET` env var.

| Function | Lignes | Role |
|----------|--------|------|
| `_tokenize(text)` / `_tokenize_preserve_case(text)` | 47-58 | Pure: word tokens (lower / case-preserving) |
| `_DISCOURSE_MARKERS` constant | 63-72 | 26 multi-word discourse markers (Cambridge subset) |
| `_discourse_marker_count(text)` | 75-83 | Pure: count of discourse markers in lowercased text |
| `_FACT_SPAN_RES` | 89-99 | Compiled regexes: ISO date, semver, git hash, %, $money, JIRA, URL |
| `has_fact_span(chunk)` | 102-109 | Pure: True iff chunk contains any fact span (hard-rule trigger) |
| `compute_idf(chunks)` | 115-135 | Pure: returns `{term: idf}` map with smoothed IDF |
| `_entity_density(chunk)` | 141-167 | Pure: capitalized mid-sentence words proxy for NER (no spaCy needed). Splits on `[.!?]+\s+` to skip sentence-initial caps |
| `_tfidf_mean(chunk, idf_map)` | 170-184 | Pure: mean TF-IDF over chunk tokens |
| `_position_score(idx, total)` | 187-196 | Pure: 1.0 for first/last 20%, 0.5 for middle |
| `_number_density(chunk)` | 199-205 | Pure: fraction of tokens containing digits |
| `_question_presence(chunk)` | 208-210 | Pure: 1.0 if "?" in chunk else 0.0 |
| `_discourse_score(chunk)` | 213-215 | Pure: discourse marker count, capped at 1.0 |
| `score_chunk(chunk, idf_map, pos, total)` | 218-241 | Pure: 6-feature weighted sum (entity 0.20 + tfidf 0.20 + position 0.15 + number 0.15 + question 0.10 + discourse 0.10) — exact weights from BudgetMem paper |
| `_default_token_count(text)` | 247-249 | Pure: word count fallback when no tokenizer given |
| `select_chunks(chunks, budget, ...)` | 252-303 | Pure: 2-phase pack — must-keep facts first, then score-sorted others. Returns kept indices in original order |
| `budget_select(text, budget, ...)` | 306-326 | Pure: top-level — splits text by `\n\s*\n`, calls select_chunks, rejoins kept |
| `stats(text=, chunks=, budget=)` | 329-359 | Pure diagnostic: paragraph count, score distribution, selection ratio |

Tests: `tests/test_brick3_budget_select.py` (50 tests pass) +
`tests/test_props_budget_select.py` (6 forge property tests pass).
Forge BUG-102 detector: 0 destructive functions.

Real measured impact (`tests/benchmark/PHASE_B_RESULTS.md`):
- L0-L11 alone: x2-x4 ratio on real Muninn files
- +L12 at 50% budget: **x8-x9 ratio** (more than double)

---

## muninn_tree.py — Arbre + Boot + Intelligence (3608 lignes)

Tout l'arbre L-system, boot, recall, prune, diagnostics.

### Tree I/O (43-306)
| Fonction | Lignes | Role |
|----------|--------|------|
| adaptive_boot_budget | 43-54 | Budget boot: 15% contexte, floor 15K, cap 100K |
| _get_tree_dir / _get_tree_meta | 55-66 | Resolve tree paths |
| _refresh_tree_paths | 67-73 | Refresh TREE_DIR/TREE_META |
| cleanup_legacy_tree / cleanup_tmp_files | 74-129 | Nettoyage legacy + tmp |
| init_tree | 130-162 | Init arbre vide avec root node |
| _tree_lock / _tree_unlock | 163-213 | Locking concurrent tree access |
| load_tree | 214-243 | Charge tree.json + validation + recovery |
| save_tree | 244-273 | Ecriture atomique via tempfile + os.replace |
| _atomic_json_write | 274-288 | JSON write atomique generique |
| _safe_tree_path | 289-298 | Anti path-traversal |
| compute_hash | 299-306 | SHA-256 fichier (8 hex chars) |

### Memory Intelligence (307-521)
| Fonction | Lignes | Role |
|----------|--------|------|
| _ebbinghaus_recall | 307-358 | Spaced repetition: p=2^(-delta/h), A1 usefulness |
| _actr_activation | 359-407 | ACT-R: B=ln(sum(t_j^(-d))), blend 70/30 |
| _days_since | 408-415 | Calcul jours depuis date |
| compute_temperature | 416-436 | Score branche 0-1 (80% recall, 20% fill) |
| refresh_tree_metadata | 437-450 | Recalcule hash+lines+temperature |
| read_node | 451-521 | Lit .mn + P34 integrity + B1 reconsolidation |

### TF-IDF & Tree Build (522-868)
| Fonction | Lignes | Role |
|----------|--------|------|
| _tokenize_words | 522-526 | Tokenise texte en mots |
| _tfidf_relevance | 527-585 | TF-IDF cosine similarity query vs docs |
| build_tree | 586-679 | Construit arbre depuis fichiers .mn |
| grow_branches_from_session | 680-868 | Cree/merge branches depuis session compressee |

### Boot (869-1694)
| Fonction | Lignes | Role |
|----------|--------|------|
| extract_tags | 869-931 | Extrait tags pour scoring |
| _load_virtual_branches | 932-1046 | Charge branches virtuelles cross-repo |
| boot | 1047-1694 | BOOT COMPLET: TF-IDF + Spreading Activation + Ebbinghaus + Park et al. |

### Recall & Bridge (1695-2039)
| Fonction | Lignes | Role |
|----------|--------|------|
| recall | 1695-1815 | Mid-session memory search (grep sessions+tree+errors) |
| bridge | 1816-1971 | Bridge inter-repos |
| bridge_fast | 1972-2039 | Bridge rapide (sans arbre) |

### Session Intelligence (2040-2279)
| Fonction | Lignes | Role |
|----------|--------|------|
| predict_next | 2040-2117 | B4 Endsley L3: prediction spreading activation |
| detect_session_mode | 2118-2173 | Convergent/divergent mode |
| adapt_k | 2174-2191 | C4: sigmoid k adaptatif |
| classify_session | 2192-2279 | RPD type: debug/feature/explore/refactor/review |

### Sleep & Huginn (2280-2579)
| Fonction | Lignes | Role |
|----------|--------|------|
| _sleep_consolidate | 2280-2440 | Wilson & McNaughton 1994: NCD grouping + dedup + L10+L11 |
| huginn_think | 2441-2522 | Meta-cognition: structural insights |
| _surface_insights_for_boot | 2523-2535 | Surface insights at boot |
| _light_prune | 2536-2579 | Prune leger (hook) |
| _auto_backup_tree | 2580-2603 | A7: backup avant prune |

### Prune (2604-3016)
| prune | 2604-3016 | PRUNE COMPLET: backup + sleep consolidation + decay + R4 temperature + I2/I3 immune |

### Diagnostics (3017-3516)
| Fonction | Lignes | Role |
|----------|--------|------|
| show_status | 3017-3051 | Affiche etat arbre |
| doctor | 3052-3228 | Diagnostic complet (37 checks) |
| diagnose | 3229-3333 | C6: diagnostic CLI |
| _load_relevant_sessions | 3334-3386 | Charge sessions pertinentes |
| _append_session_log | 3387-3446 | Ajoute entree session log |
| _extract_error_fixes | 3447-3491 | P18: extraction error/fix pairs |
| _surface_known_errors | 3492-3516 | Surface erreurs connues au boot |

### Inject (3517-3608)
| inject_memory | 3517-3608 | B7: injection memoire live |

---

## muninn_feed.py — Feed Pipeline + Hooks (1640 lignes)

Ingestion transcripts, compression, hooks PreCompact/SessionEnd.

### Parsing (27-296)
| Fonction | Lignes | Role |
|----------|--------|------|
| _compress_code_blocks | 27-59 | P17: compresse blocs de code |
| _parse_json_conversation | 60-94 | Parse JSON transcript |
| _parse_markdown_conversation | 95-119 | Parse Markdown transcript |
| _detect_transcript_format | 120-163 | Auto-detect format |
| parse_transcript | 164-296 | L0 + parsing complet |

### Feed & Compression (297-917)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_from_transcript | 297-381 | Feed mycelium depuis transcript |
| _semantic_rle | 382-477 | Semantic RLE: collapse debug/retry loops |
| compress_transcript | 478-692 | Pipeline complet transcript -> .mn |
| _update_session_index | 693-787 | P22: session search index |
| _update_usefulness | 788-917 | Met a jour usefulness branches |

### Lock & Hooks (918-1260)
| Fonction | Lignes | Role |
|----------|--------|------|
| _MuninnLock (class) | 918-1051 | Lock fichier cross-process (fcntl/msvcrt) |
| _hook_log | 1052-1062 | Log hook events |
| feed_from_hook | 1063-1143 | Hook PreCompact |
| feed_from_stop_hook | 1144-1186 | Hook SessionEnd entry |
| _feed_from_stop_hook_locked | 1187-1260 | Hook SessionEnd locked |

### History & Watch (1261-1619)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_history | 1261-1414 | Rattrape tous les transcripts passes |
| feed_watch | 1415-1544 | Watch mode: feed auto |
| ingest | 1545-1619 | Ingest fichiers externes |

---

## cube.py — Cube Core (1553 lignes)

Scanner, dataclasses, subdivision, CubeStore, dependencies, neighbors,
format_code (4 formatters), check_formatters, install_formatters.

### Scanner B1 (128-257)
| Fonction | Lignes | Role |
|----------|--------|------|
| ScannedFile (class) | 128-148 | Resultat scan fichier |
| scan_repo | 191-257 | Scan recursif fichiers source |

### Cube & Subdivision B3-B5 (258-838)
| Fonction | Lignes | Role |
|----------|--------|------|
| Cube (class) | 258-296 | id, content, sha256, file_origin, level, neighbors, temp |
| normalize_content | 297-348 | Normalise contenu pour hash (rstrip, collapse blanks) |
| format_code | 350-419 | Appelle gofmt/black/rustfmt/prettier avant SHA. shutil.which + fallback paths. gofmt=stdout, rustfmt=in-place |
| _EXT_TO_FORMATTER | 425-429 | Mapping extension -> formateur |
| _FORMATTER_INFO | 431-480 | Per-formatter: binary, fallback paths, install cmds per OS |
| _resolve_formatter | 482-494 | Trouve un binaire formateur (which + fallback) |
| check_formatters | 496-565 | Detecte quels formateurs sont necessaires vs installes |
| install_formatters | 567-630 | Auto-installe les formateurs manquants (black via pip, etc) |
| sha256_hash | 632-634 | SHA-256 sur format_code + normalize |
| subdivide_file | 695-771 | B4: split fichier en cubes ~112 tokens |
| subdivide_recursive | 772-838 | B4: split recursif /8 par niveau |

### CubeStore B6 (839-1042)
| CubeStore (class) | 839-1042 | SQLite WAL, tables cubes/neighbors/cycles |

### Dependencies & Neighbors B7-B8 (1043-1553)
| Fonction | Lignes | Role |
|----------|--------|------|
| parse_dependencies | 1148-1168 | B7: AST Python + regex JS/TS/Go/Java |
| extract_ast_hints | 1170-1366 | B7b: pre-destruction hints. RAID adaptatif, identifiers (36-word filter), strings, type_sigs, anchors, first/last line. Uses normalize_content for line indexing |
| deduce_imports_from_file | 1367-1417 | Scan pkg.Symbol usage across full file |
| enrich_hints_with_file_context | 1419-1450 | Adds deduced_imports + constant_lines to hints |
| assign_neighbors | 1522-1553 | B8: adjacence + deps, max 9 voisins |

---

## cube_providers.py — LLM Providers + Reconstruction (1952 lignes)

Providers, FIM reconstruction, anchor forcing (fixes 6-20), validation,
NCD, die-and-retry waves, progressive levels. Language-specific forcing
for Python, Rust, JSX, C, COBOL, TypeScript.

### Providers B11-B14 (38-357)
| Classe | Lignes | Role |
|--------|--------|------|
| LLMProvider (ABC) | 38-86 | Interface abstraite |
| OllamaProvider | 88-209 | B12: Ollama local |
| ClaudeProvider | 211-283 | B13: Claude API |
| OpenAIProvider | 285-357 | B14: OpenAI compatible |

### FIM Reconstruction B15 (359-939)
| Classe/Fonction | Lignes | Role |
|--------|--------|------|
| FIMReconstructor | 359-939 | B15: FIM prompt + smart hints + post-processing |
| reconstruct_with_neighbors | 404-939 | Core: FIM prompt, 20 anchor forcing rules, language-specific |
| Fix 20: skip LLM | 450-480 | If 100% anchored, return original (zero API) |
| Anchor forcing block | 606-860 | Fixes 6-13, 14-18 (language), 19 (keywords) |
| _RETURN_KEYWORDS | 750-780 | Expanded keyword set (Go/Python/Rust/JS/TS/COBOL) |

### Post-processing (1436-1662)
| Fonction | Lignes | Role |
|----------|--------|------|
| _is_continuation | 1436-1490 | Line wrap scoring (0.0-1.0, COBOL col7 check first) |
| _adjust_line_count | 1492-1548 | Smart join: score-based continuation detection |
| _insert_missing_blanks | 1550-1662 | 3-tier blank insertion (anchors > block-end > statements) |
| _annealing_schedule | 1396-1434 | Cold-hot-cold temperature curve (Kirkpatrick 1983) |

### Mock & Results (941-995)
| Classe | Lignes | Role |
|--------|--------|------|
| MockLLMProvider | 941-983 | Mock pour tests |
| ReconstructionResult | 985-995 | Resultat reconstruction |

### Reconstruction B16-B19 (997-1117)
| Fonction | Lignes | Role |
|----------|--------|------|
| reconstruct_cube | 997-1060 | B16: orchestre B15+B17+B18+B19 |
| validate_reconstruction | 1062-1071 | B17: SHA-256 compare |
| compute_hotness | 1073-1088 | B18: perplexite voisins |
| compute_ncd | 1090-1117 | B19: NCD zlib (seuil 0.3) |

### Die-and-retry B40 (1303-1834)
| Element | Lignes | Role |
|---------|--------|------|
| WaveResult | 1303-1313 | Resultat d'une wave |
| LevelResult | 1315-1326 | Resultat d'un level progressif |
| _query_mycelium | 1328-1352 | Spreading activation on cube identifiers |
| reconstruct_cube_waves | 1690-1834 | B40: Best-of-N + annealing + targeted feedback |

### Progressive levels B41 (1837-1952)
| Fonction | Lignes | Role |
|----------|--------|------|
| run_progressive_levels | 1837-1952 | B41: x1->x2->...->x11, mycelium accumulation |

---

## cube_analysis.py — Analyse + CLI (1759 lignes)

Destruction cycle, temperatures, math, niveaux, git, scheduling, anomalies.

### Destruction Cycle (78-252)
| Fonction | Lignes | Role |
|----------|--------|------|
| run_destruction_cycle | 78-210 | CYCLE COMPLET: reconstruit + B30+B29+B23+B24+B22+B38 |
| _add_semantic_neighbors | 211-252 | Mycelium spreading activation (cycle 2+) |

### Analysis & Temperature (253-458)
| Fonction | Lignes | Role |
|----------|--------|------|
| post_cycle_analysis | 253-360 | B27+B28+B9+B10+B26+B35+B31+B37+B38 diagnostics |
| compute_temperature | 361-385 | B23: 0.4*perplexity + 0.4*(1-success) + 0.2*failures |
| update_all_temperatures | 386-395 | B23: batch update |
| kaplan_meier_survival | 396-419 | B24: S(t)=prod(1-d_i/n_i) |
| detect_dead_code / filter_dead_cubes | 420-458 | B25: vire commentaires/TODOs |
| prepare_cubes | 459-492 | B25+B21 pre-filtre |

### God's Number & Levels (493-647)
| Fonction | Lignes | Role |
|----------|--------|------|
| compute_gods_number | 503-551 | B26: cubes chauds irremplacables |
| build_level_cubes | 552-599 | B27: groupe 8 cubes lv0 -> 1 lv1 |
| propagate_levels | 612-647 | B28: remontee temperature max |

### Mycelium & Hebbian (648-744)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_mycelium_from_results | 648-697 | B29: succes=+1.0, echec=-0.5 |
| hebbian_update | 718-744 | B30: Δw=±η*0.1 |

### Git & Scheduling (745-982)
| Fonction | Lignes | Role |
|----------|--------|------|
| git_blame_cube | 745-794 | B31: lie cubes chauds a git |
| git_log_value | 795-825 | Git log pour scoring |
| CubeScheduler (class) | 826-884 | B32: async — run quand repo quiet |
| CubeConfig (class) | 885-982 | B33: config YAML + get_provider() |

### CLI (983-1155)
| Fonction | Lignes | Role |
|----------|--------|------|
| cli_scan | 983-1019 | B1+B4+B7+B8+B6 |
| cli_run | 1020-1094 | FULL PIPELINE: prepare+cycles+analysis |
| cli_status | 1095-1128 | God's Number + temp stats |
| cli_god | 1129-1155 | Compute + display God's Number |

### Graph Algorithms (1156-1414)
| Fonction | Lignes | Role |
|----------|--------|------|
| laplacian_rg_grouping | 1176-1224 | B9: spectral clustering |
| cheeger_constant | 1260-1305 | B10: bottleneck (Fiedler vector) |
| belief_propagation | 1306-1357 | B20: BP Pearl 1988 |
| survey_propagation_filter | 1358-1379 | B21: pre-filtre triviaux |
| tononi_degeneracy | 1380-1414 | B22: fragilite cube |

### Diagnostics & Feedback (1415-1759)
| Fonction | Lignes | Role |
|----------|--------|------|
| cube_heatmap | 1415-1450 | B35: temperatures par fichier |
| fuse_risks | 1451-1494 | B36: forge defect + cube temp |
| auto_repair | 1525-1593 | B37: patches FIM pour cubes chauds |
| record_quarantine | 1594-1632 | Sauvegarde contenu corrompu |
| record_anomaly | 1633-1655 | B38: enregistre anomalies |
| feedback_loop_check | 1656-1720 | B38: anomalies -> validation git |
| feed_anomalies_to_mycelium | 1721-1759 | B38: anomalies -> mycelium |

---

## mycelium.py — Champignon Vivant (3145 lignes)

### Mycelium (class, 54-2779)
| Methode | Lignes | Role |
|---------|--------|------|
| observe_text | ~200 | Observe co-occurrences (chunks par paragraphe) |
| observe_with_concepts | ~300 | Observe avec concepts externes (OpenAlex) |
| observe_latex | ~350 | Observe LaTeX (\section/\begin chunks) |
| spread_activation | ~500 | Collins & Loftus 1975: propagation semantique |
| decay | ~969 | Decay half-life (immortalite zones 3+). BUG-M8: auto-cleanup orphans |
| get_compression_rules | ~1270 | BUG-M6: filtre hubs+min_strength+max_rules (was 445K, now 5K) |
| get_related | ~1296 | BUG-M4: filtre stopwords par defaut (filter_stopwords=True) |
| adaptive_fusion_threshold | ~1088 | A1: seuil adaptatif sqrt(n)*0.4 |
| adaptive_decay_half_life | ~1100 | A2: half-life adaptatif (sessions/jours) |
| cleanup_orphan_concepts | ~800 | A3: vire concepts sans edges |
| vacuum_if_needed | ~850 | A4: auto-vacuum apres decay |
| adaptive_hops | ~900 | A5: hops adaptatif (sparse=3, dense=1) |
| detect_anomalies | ~1000 | B2: graph anomaly detection |
| detect_blind_spots | ~1100 | B3: structural holes (Burt 1992) |
| _bfs_zones | ~2180 | BUG-M2/M3: bounded subgraph + deque (was OOM on 11.7M edges) |
| dream | ~2236 | BUG-M1: sampled via top_connections+all_degrees (was OOM) |
| trip | ~2032 | BUG-M2: bounded conn_set via zone concepts only |

### CLI (2780-2915)
| main | 2780-2915 | CLI: observe/spread/decay/zones/detect/blind_spots |

---

## mycelium_db.py — SQLite Backend (1329 lignes)

### Date Utils (30-60)
| date_to_days / days_to_date / today_days | 30-60 | Epoch-days (int since 2020-01-01) |

### MyceliumDB (class, 61-1097)
| Methode | Lignes | Role |
|---------|--------|------|
| __init__ | ~70 | SQLite WAL + tables concepts/edges/fusions/meta |
| _get_or_create_concept | ~120 | Concept -> int ID (cache) |
| record_cooccurrence | ~200 | Batch increment edges |
| get_neighbors | ~300 | Voisins tries par count |
| fuse / get_fusions | ~400 | Gestion fusions |
| degree_filter | ~500 | S3: top 5% = stopwords |
| transaction() | ~600 | Context manager ACID |
| migrate_from_json | ~700 | S1: JSON -> SQLite migration |

### ConceptTranslator (1098-1329)
| Methode | Lignes | Role |
|---------|--------|------|
| translate | ~1150 | S4: tiktoken detection + Haiku API batch |
| _translate_batch | ~1200 | Batch API call + SQLite cache |

---

## Autres Fichiers

### sync_tls.py (601L) — Sync TLS
P2O: TLS mTLS server/client, push/pull, rate limiting.

### sync_backend.py (1128L) — Sync Backend
SharedFile/Git/TLS backends, auto-detection.

### wal_monitor.py (109L) — WAL Monitor
Passive WAL size monitoring, adaptive flush.

### tokenizer.py (43L) — Tokenizer
tiktoken wrapper with len()//4 fallback.

### lang_lexicons.py (1007L) — Language Lexicons
Multi-language lexicons for cube reconstruction (B15).

### _secrets.py (133L) — Shared Secret Redaction + Anti-Adversa
| Function | Lignes | Role |
|---|---|---|
| _SECRET_PATTERNS | 9-46 | 24+ regex patterns (Git, AWS, AI keys, DB URIs, Bearer, etc.) |
| redact_secrets_text | 51-61 | Defense-in-depth secret stripping before observe_text() |
| MAX_CHAINED_COMMANDS | 84 | CHUNK 3: anti-Adversa default cap (30, below 50 threshold) |
| count_chained_commands | 99-110 | CHUNK 3: counts && and \|\| in text (canonical shell chain markers) |
| clamp_chained_commands | 113-133 | CHUNK 3: refuses content with too many chained commands |

### .claude/hooks/ — Hook Handlers (6 files)
Installed by `install_hooks()` in `engine/core/muninn.py` and mirrored
in `muninn/_engine.py`. Self-contained, never raise, exit 0 always.
The first 3 are generated by f-string templates, the last 3 are static
files copied from the repo source.
| File | Lignes | Role |
|---|---|---|
| `bridge_hook.py` | ~115 | UserPromptSubmit: secret sentinel + bridge_fast(prompt). CHUNK 3 anti-Adversa clamp on output. |
| `post_tool_failure_hook.py` | ~135 | CHUNK 4: PostToolUseFailure -> append entry to .muninn/errors.json (P18 schema, dedup, cap 500) |
| `subagent_start_hook.py` | ~120 | CHUNK 5: SubagentStart -> inject muninn.boot(query=agent_type) capped at 20K chars into sub-agent context |
| `pre_tool_use_bash_destructive.py` | ~115 | **CHUNK 12**: PreToolUse(Bash) -> blocks force-push, rm -rf /, DROP TABLE, --no-verify, etc. Exit 2 with stderr feedback. Enforces RULE 2. |
| `pre_tool_use_bash_secrets.py` | ~125 | **CHUNK 12**: PreToolUse(Bash) -> blocks echo $TOKEN, cat .env, env|grep TOKEN. Allows safe checks like `[ -n "$VAR" ]`. Enforces RULE 3. |
| `pre_tool_use_edit_hardcode.py` | ~135 | **CHUNK 12**: PreToolUse(Edit\|Write) -> blocks Edit/Write to engine/core/ or muninn/ that introduces hardcoded `C:/Users/.../MUNINN-` in code lines. Allows in tests/, docs/, comments. Enforces RULE 1. |

### .claude/rules/ — Path-scoped extension rules (CHUNK 13, 2 files)
Anthropic Claude Code recommendation: rules with YAML frontmatter `paths:`
load only when Claude touches matching files. Enriches CLAUDE.md without
bloating the always-loaded context.
| File | paths: | Role |
|---|---|---|
| `python.md` | `engine/**/*.py`, `muninn/**/*.py`, `tests/**/*.py`, `*.py` | Extends RULE 1 with 4 path patterns used in repo, BUG-091 dual-maintenance, test conventions, Windows encoding, secrets in Python |
| `git.md` | `**/.gitignore`, `**/.gitattributes`, `**/.git/**` | Extends RULES 2 and 3 with git-specific cases, list of blocked operations, pre-commit checklist |

---

## muninn/ui/ — Interface Desktop PyQt6 (~4470 lignes + 5197 ref, 18+2 fichiers)

Phase 0-9 COMPLETE. 32 briques. 152 UI tests PASS (PyQt6 6.10.2).

### __init__.py (62L) — Package + Fonts
| Element | Lignes | Role |
|---------|--------|------|
| _FONTS_DIR, _ASSETS_DIR... | 10-17 | Paths (PyInstaller support) |
| load_fonts() | 32-48 | Load TTF into QFontDatabase |
| get_font_families() | 51-62 | Verify loaded families |

### theme.py (314L) — QSS Cyberpunk
| Element | Lignes | Role |
|---------|--------|------|
| Color tokens | 14-30 | BG_0DP..ERROR, Material dark elevation |
| load_theme() | 43-50 | Cached QSS string |
| _build_qss() | 53-260 | Full QSS (minimal selectors, no border-image) |
| get_palette() | 263-285 | QPalette for dynamic colors (avoids GDI leak) |

### main_window.py (584L) — MainWindow Fully Wired
| Element | Lignes | Role |
|---------|--------|------|
| MainWindow.__init__ | 39-59 | Splitters, status bar, autosave 60s, _install_extras |
| _build_ui() | 61-131 | Search bar + forest toggle toolbar, Navi overlay, command palette |
| _wire_signals() | 133-156 | All panel signals: neuron/tree/detail bidirectional |
| _install_extras() | 158-183 | Shortcuts, context menus, drag-drop, search/forest/palette wiring, tray |
| _on_search_changed/confirmed/cleared | 184-200 | Search -> neuron map highlight (B-UI-25) |
| _on_mode_changed + _load_forest | 201-240 | Forest toggle -> MetaMyceliumWorker QThread (B-UI-17) |
| _on_palette_action() | 243-268 | Dispatch 12 command palette actions |
| _scan_folder() | 290-310 | Run muninn scan via subprocess, load results (B-UI-22) |
| _on_neuron_selected() | 320-350 | Tree highlight + detail panel + status bar |
| load_scan() | 400-430 | Load scan JSON + feed search bar + Navi context |
| register/cancel_worker | 440-460 | Worker registry R13 |
| save/restore_state | 465-510 | QSettings, geometry safe R14 |
| closeEvent | 510-520 | Cancel workers, save, accept |
| main() | 525-572 | R7 entry: HiDPI, Fusion, excepthook, fonts |

### neuron_map.py (~1036L) — Carte Neurones + Cube 3D
| Element | Lignes | Role |
|---------|--------|------|
| Neuron dataclass | 39-55 | id, label, x, y, z, degree, category |
| DEGREE_GRADIENT + _degree_color | 77-107 | B-UI-03: green->yellow->red 10-step gradient |
| 3D cube rotation | ~185-250 | _cube_tick, _project_3d (Y+X rot, perspective fov=3.5) |
| _paint_cube_wireframe | ~250-275 | 12 cyan wireframe edges, 8 corners |
| _world_to_screen | ~280-295 | 3D projection -> screen coords (wz param) |
| load_scan() | ~210-260 | Parse scan JSON, build edges, launch Laplacian |
| _layout_random() | ~325 | 3D positions in [-0.8, 0.8] cube space |
| _start_laplacian() | ~340-370 | B-UI-03: QThread worker (R3, R12) |
| _build_kdtree() | ~400-420 | B-UI-05: scipy cKDTree O(log n) |
| paintEvent | ~450-470 | Cube wireframe + edges + neurons + legend |
| _paint_neurons | ~480-560 | Depth sort, depth-based sizing/alpha, labels hovered/selected only |
| _paint_edges() | ~570-640 | B-UI-07: bezier quadTo, LOD, frustum culling |
| closeEvent | ~200-210 | R4: cancel Laplacian + stop anim + cube timer |

### workers.py (~210L) — QThread Workers
| Element | Lignes | Role |
|---------|--------|------|
| LaplacianWorker | 12-210 | B-UI-03: scipy eigsh spectral layout |
| Top-N filtering | 50-67 | Degree-based, N=1000 |
| _spring_layout | 165-198 | Fallback if eigsh fails |
| _grid_layout | 200-210 | Fallback for disconnected graphs |

### tree_view.py (~469L) — Arbre Botanique + Auto-Layout
| Element | Lignes | Role |
|---------|--------|------|
| TreeNode | 38-52 | id, label, status, x, y, radius |
| load_tree() | 95-170 | Load from scan, uses JSON x/y or auto_layout |
| _auto_layout() | ~180-220 | Generate tree-shaped positions from depth/level |
| _get_image_rect() | ~340-350 | Image-relative coordinates after aspect scaling |
| _center_on_node() | ~260-270 | B-UI-11: 200ms center animation (image-relative) |
| _cross_fade() | ~285-290 | B-UI-11: 200ms opacity cross-fade |
| paintEvent | ~295-325 | R6: pixmap cache + nodes |
| _paint_nodes | ~335-385 | Glow rings, image-relative coords, highlight, labels |
| highlight_concept() | ~430-450 | B-UI-11: center anim + cross-fade |
| hit test + click | ~405-425 | Image-relative hit testing |

### classifier.py (159L) — Auto-Classification
| Element | Lignes | Role |
|---------|--------|------|
| ScanMetrics | 15-25 | concentration, depth, breadth, dispersion, external_deps |
| extract_metrics() | 28-65 | 5 metriques depuis scan JSON |
| classify_repo() | 68-140 | Score 6 familles, domain hints, stats hints |
| classify_scan_file() | 143-150 | Convenience: file path -> family |

### detail_panel.py (~280L) — Panel Details
| Element | Lignes | Role |
|---------|--------|------|
| ClickableLabel | 24-36 | QLabel with clicked signal |
| DetailPanel._build_ui | 66-155 | Title, status, LOC, info, zone, neighbors, files |
| show_empty() | 157-163 | R8 empty state |
| show_neuron() | 165-265 | B-UI-12 basic (LOC) + B-UI-13 extended (zone, last_modified) |
| Cross-fade | 54-61 | QGraphicsOpacityEffect 200ms |

### navi.py (~593L) — Fee Guide Navi Evolved
| Element | Lignes | Role |
|---------|--------|------|
| TUTORIAL_STEPS | 30-85 | 7-step guided tutorial (welcome->scan->explore) |
| HELP_TEXTS | 87-98 | Contextual help dict (FRENCH) |
| _reduce_motion_enabled | 100-110 | Windows SPI_GETCLIENTAREAANIMATION |
| __init__ | 115-170 | Tutorial state, flight patterns, WA_TransparentForMouseEvents=False |
| _tick() | 172-255 | 16ms, 5 flight patterns, geostationary when bubble visible, tutorial auto-advance |
| _advance_tutorial | 295-300 | Step progression + on_scan_complete hook |
| _paint_orb | 350-490 | 3 glow layers + 6 crescent wings (Bezier) + iridescent core |
| _load_bubble_frame | 493-510 | PNG frame with black pixels made transparent (pixel alpha) |
| _paint_bubble | 512-570 | x2.5 size (600x180), centered cyan text, interactive button |
| mousePressEvent | 575-585 | Button click -> scan_requested, else event.ignore() (forward) |

### terminal.py (363L) — Terminal + LLM Streaming
| Element | Lignes | Role |
|---------|--------|------|
| TerminalWidget | 20-180 | B-UI-19: QTextEdit(read-only) + QLineEdit, cmd history, /clear, /help |
| LLMWorker | 180-230 | B-UI-20: Anthropic streaming in QThread, fallback echo |
| Breathing indicator | 155-175 | Pulsing dot InOutSine 2s, stop button |

### forest.py (~170L) — Solo/Forest Toggle + Meta-Mycelium
| Element | Lignes | Role |
|---------|--------|------|
| ZONE_COLORS | 25-39 | 13 QColors for zone differentiation |
| MetaMyceliumWorker | 42-119 | B-UI-17: top 200 per zone from meta_mycelium.db, QThread |
| ForestToggle | 122-170 | B-UI-16: SOLO/FOREST button, mode_changed signal |

### search.py (~100L) — Search Bar
| Element | Lignes | Role |
|---------|--------|------|
| SearchBar | 16-99 | B-UI-25: 200ms debounce, substring match on neurons |
| Signals | 23-25 | search_changed(set), search_confirmed(str), search_cleared() |

### shortcuts.py (~110L) — Global Keyboard Shortcuts
| Element | Lignes | Role |
|---------|--------|------|
| install_shortcuts() | 12-48 | B-UI-26: Ctrl+F, Ctrl+1-4, Space, Escape, F11, Ctrl+Shift+S/P |
| Helpers | 51-110 | _focus_search, _toggle_mode, _escape, _export_screenshot |

### command_palette.py (~128L) — Command Palette
| Element | Lignes | Role |
|---------|--------|------|
| ACTIONS | 16-29 | 12 predefined actions with shortcuts |
| CommandPalette | 32-128 | B-UI-29: frameless overlay, fuzzy search, Enter/Escape |

### context_menu.py (~135L) — Right-Click Menus
| Element | Lignes | Role |
|---------|--------|------|
| install_context_menu() | 11-22 | B-UI-27: install on any widget |
| _build_neuron_menu | 47-75 | Copy, view in tree, open file, zoom to fit |
| _build_tree_menu | 78-93 | Copy, open file, copy path |
| _build_terminal_menu | 96-104 | Copy, clear |
| _copy_text | 116-127 | R9 clipboard retry (5x 50ms) |

### drag_drop.py (~40L) — Drag and Drop
| Element | Lignes | Role |
|---------|--------|------|
| install_drag_drop() | 12-40 | B-UI-28: drop folder -> window._scan_folder() |

### system_tray.py (~60L) — System Tray
| Element | Lignes | Role |
|---------|--------|------|
| MuninnTray | 14-55 | B-UI-30: icon, Show/Quit menu, double-click, notify() |

### about_dialog.py (~60L) — About Dialog
| Element | Lignes | Role |
|---------|--------|------|
| AboutDialog | 18-60 | B-UI-32: version, credits, themed OK button |

---

## Tests (1305+ PASS)

### Fichiers tests (par module)
| Fichier | Tests | Scope |
|---------|-------|-------|
| test_tier1_*.py (6 files) | 36 | A1-A5, B1 reconsolidation |
| test_tier2_*.py (4 files) | 32 | B2-B7, session mode, wiring |
| test_tier3_*.py (4 files) | 21 | S1-S4, C3-C4, C6-C7 |
| test_huginn_*.py (3 files) | ~24 | H1-H3 meta-cognition |
| test_immune_*.py (3 files) | ~15 | I1-I3 immune system |
| test_cube_*.py (10 files) | ~250 | B1-B39 cube briques |
| test_phase*.py (7 files) | ~120 | Phase 1-7 audit |
| test_x*.py (2 files) | ~26 | X3-X16 bug fixes |
| test_quarantine*.py (2 files) | ~25 | Quarantine system |
| test_ui_*.py (14 files) | ~157 | UI Phase 0-9: bootstrap, theme, window(13), neuron(26), tree(13), classifier, detail(12), navi(14), terminal(12), forest(12), search(11), shortcuts(7), cmd_palette(10), context_menu(12), extras(10) |
| Others | ~745 | Mycelium, feed, sync, vault, doctor, decay, etc. |
