# MUNINN — Winter Tree (Carte Technique)

> Ce fichier est une CARTE DE NAVIGATION pour Claude. Pas un changelog.
> Objectif: savoir EXACTEMENT ou chercher quoi dans le code, avec les numeros de lignes.
> Mis a jour: 2026-03-28. Engine: 18557 lignes, 14 fichiers. UI: ~3000 lignes, 9 fichiers. Tests: 1305 PASS (1210 engine + 95 UI), 0 FAIL.
> Split: muninn.py (7959L -> 4 fichiers), cube.py (3273L -> 3 fichiers).
> Package: muninn/ pip-installable. _ProxyModule (getattr+setattr+delattr). conftest.py pre-load.
> UI: Phase 0-5 DONE + AUDIT FIX — 16 briques (B-UI-00..15), PyQt6+pytest-qt, 95 tests PASS.

## Architecture

```
        [1285 tests, 0 FAIL]                +5 Cime (validation)
       /    \
    [.mn]  [.mn]                            +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                              +2 Branches (metadata arbre)
      |
   muninn.py 1509L (orchestrateur)          +1 Tronc
     muninn_layers.py 1294L (compression)
     muninn_tree.py 3608L (arbre+boot+intelligence)
     muninn_feed.py 1619L (feed+hooks)
      |
   [mycelium.py 2915L + db 1329L]            0 SOL — champignon vivant
      |
   [sync_backend.py 1128L]               -0.5 Sync federe (SharedFile/Git/TLS)
      |
   [vault.py + sync_tls.py 601L]           -1 Sous-sol — securite + reseau
      |
   cube.py 1056L (core)                    -2 Fondations — resilience
     cube_providers.py 580L (LLM)
     cube_analysis.py 1759L (analyse+CLI)
      |
   [wal_monitor 109L + tokenizer 43L]      -3 Racines — infrastructure
      |
   muninn/ui/ ~3000L (9 fichiers)           -4 Interface — desktop PyQt6
```

---

## muninn.py — Orchestrateur (1509 lignes)

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
| _generate_bridge_hook | 667-695 | Genere hook bridge inter-repos |

### Secrets & CLI (696-1509)
| Fonction | Lignes | Role |
|----------|--------|------|
| _shannon_entropy / _has_char_diversity | 696-720 | Detection secrets heuristique |
| _check_secrets | 721-748 | Check un texte pour secrets |
| install_hooks | 792-883 | Install hooks PreCompact/SessionEnd |
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

## muninn_feed.py — Feed Pipeline + Hooks (1619 lignes)

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

## cube.py — Cube Core (1056 lignes)

Scanner, dataclasses, subdivision, CubeStore, dependencies, neighbors.

### Scanner B1 (133-262)
| Fonction | Lignes | Role |
|----------|--------|------|
| ScannedFile (class) | 133-153 | Resultat scan fichier |
| scan_repo | 196-262 | Scan recursif fichiers source |

### Cube & Subdivision B3-B5 (263-545)
| Fonction | Lignes | Role |
|----------|--------|------|
| Cube (class) | 263-301 | id, content, sha256, file_origin, level, neighbors, temp |
| normalize_content | 302-339 | Normalise contenu pour hash |
| sha256_hash | 340-352 | SHA-256 sur contenu normalise |
| subdivide_file | 403-479 | B4: split fichier en cubes ~112 tokens |
| subdivide_recursive | 480-545 | B4: split recursif /8 par niveau |

### CubeStore B6 (546-749)
| CubeStore (class) | 546-749 | SQLite WAL, tables cubes/neighbors/cycles |

### Dependencies & Neighbors B7-B8 (750-1056)
| Fonction | Lignes | Role |
|----------|--------|------|
| parse_dependencies | 855-876 | B7: AST Python + regex JS/TS/Go/Java |
| extract_ast_hints | 877-954 | B7b: pre-destruction functions/classes/imports |
| assign_neighbors | 1025-1056 | B8: adjacence + deps, max 9 voisins |

---

## cube_providers.py — LLM Providers (580 lignes)

Providers, FIM reconstruction, validation, NCD.

### Providers B11-B14 (35-283)
| Classe | Lignes | Role |
|--------|--------|------|
| LLMProvider (ABC) | 35-76 | Interface abstraite |
| OllamaProvider | 77-171 | B12: Ollama local |
| ClaudeProvider | 172-229 | B13: Claude API |
| OpenAIProvider | 230-283 | B14: OpenAI compatible |

### FIM & Mock B15 (284-478)
| Classe | Lignes | Role |
|--------|--------|------|
| FIMReconstructor | 284-423 | B15: lexicon + AST + FIM/prompt |
| MockLLMProvider | 424-466 | Mock pour tests |
| ReconstructionResult | 467-478 | Resultat reconstruction |

### Reconstruction B16-B19 (479-580)
| Fonction | Lignes | Role |
|----------|--------|------|
| reconstruct_cube | 479-525 | B16: orchestre B15+B17+B18+B19 |
| validate_reconstruction | 526-536 | B17: SHA-256 compare |
| compute_hotness | 537-553 | B18: perplexite voisins |
| compute_ncd | 554-580 | B19: NCD zlib (seuil 0.3) |

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

## mycelium.py — Champignon Vivant (2915 lignes)

### Mycelium (class, 54-2779)
| Methode | Lignes | Role |
|---------|--------|------|
| observe_text | ~200 | Observe co-occurrences (chunks par paragraphe) |
| observe_with_concepts | ~300 | Observe avec concepts externes (OpenAlex) |
| observe_latex | ~350 | Observe LaTeX (\section/\begin chunks) |
| spread_activation | ~500 | Collins & Loftus 1975: propagation semantique |
| decay | ~600 | Decay half-life (immortalite zones 3+) |
| adaptive_fusion_threshold | ~700 | A1: seuil adaptatif sqrt(n)*0.4 |
| adaptive_decay_half_life | ~750 | A2: half-life adaptatif (sessions/jours) |
| cleanup_orphan_concepts | ~800 | A3: vire concepts sans edges |
| vacuum_if_needed | ~850 | A4: auto-vacuum apres decay |
| adaptive_hops | ~900 | A5: hops adaptatif (sparse=3, dense=1) |
| detect_anomalies | ~1000 | B2: graph anomaly detection |
| detect_blind_spots | ~1100 | B3: structural holes (Burt 1992) |

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

---

## muninn/ui/ — Interface Desktop PyQt6 (~3000 lignes, 9 fichiers)

Phase 0-5 + audit fix. 95 tests PASS.

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

### main_window.py (219L) — MainWindow 4 Panels
| Element | Lignes | Role |
|---------|--------|------|
| PlaceholderPanel | 18-27 | Temp widget with min 200x150 |
| MainWindow.__init__ | 30-50 | Splitters, status bar, autosave 60s |
| _build_ui() | 52-80 | Nested QSplitters, handleWidth(6) |
| register/cancel_worker | 100-120 | Worker registry R13 |
| save/restore_state | 123-155 | QSettings, geometry safe R14 |
| closeEvent | 157-165 | Cancel workers, save, accept |
| main() | 168-219 | R7 entry: HiDPI, Fusion, excepthook, fonts |

### neuron_map.py (~960L) — Carte Neurones
| Element | Lignes | Role |
|---------|--------|------|
| Neuron dataclass | 39-54 | id, label, x, y, degree, category |
| DEGREE_GRADIENT + _degree_color | 77-102 | B-UI-03: cold blue -> red gradient |
| load_scan() | 202-253 | Parse scan JSON, build edges, launch Laplacian |
| _start_laplacian() | 307-333 | B-UI-03: QThread worker (R3, R12) |
| _build_kdtree() | 366-381 | B-UI-05: scipy cKDTree O(log n) |
| paintEvent | 406-420 | Background, edges, neurons, legend |
| _paint_edges() | 430-490 | B-UI-07: bezier quadTo, LOD, frustum culling, max 5000 |
| _paint_legend() | 530-560 | B-UI-03: degree color legend bottom-left |
| _hit_test_edge() | 764-781 | B-UI-07: edge click detection |
| _zoom_to_fit_animated() | 880-910 | B-UI-04: 300ms ease-out animation |
| _anim_tick() | 912-930 | Animated zoom tick |
| closeEvent | 197-200 | R4: cancel Laplacian + stop anim timer |

### workers.py (~210L) — QThread Workers
| Element | Lignes | Role |
|---------|--------|------|
| LaplacianWorker | 12-210 | B-UI-03: scipy eigsh spectral layout |
| Top-N filtering | 50-67 | Degree-based, N=1000 |
| _spring_layout | 165-198 | Fallback if eigsh fails |
| _grid_layout | 200-210 | Fallback for disconnected graphs |

### tree_view.py (~380L) — Arbre Botanique
| Element | Lignes | Role |
|---------|--------|------|
| TreeNode | 38-52 | id, label, status, x, y, radius |
| load_tree() | 95-139 | Load from scan + positions file |
| _center_on_node() | 175-185 | B-UI-11: 200ms center animation |
| _cross_fade() | 193-197 | B-UI-11: 200ms opacity cross-fade |
| paintEvent | 200-240 | R6: pixmap cache + nodes |
| _paint_nodes | 260-310 | Glow rings (done/wip/todo), highlight, labels |
| highlight_concept() | 340-360 | B-UI-11: center anim + cross-fade |
| hit test + click | 310-340 | Node selection, double-click open file |

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

### navi.py (~300L) — Fee Guide Navi
| Element | Lignes | Role |
|---------|--------|------|
| HELP_TEXTS | 29-38 | Contextual help dict (7 contexts, FRENCH) |
| _reduce_motion_enabled | 41-51 | Windows SPI_GETCLIENTAREAANIMATION |
| _tick() | 102-125 | 16ms lerp + idle float oscillation |
| _paint_orb | 184-232 | Radial gradient glow + wings + core |
| _load_bubble_frame | 234-238 | B-UI-14: lazy load PNG frame |
| _paint_bubble | 240-290 | B-UI-14: PNG frame + B-UI-15: scan button |
| mousePressEvent | 292-300 | B-UI-15: scan button click -> scan_requested signal |
| show_context_help | 145-154 | B-UI-15 contextual guide |
| show_first_launch | 156-159 | "Hey! Scanne un repo!" |

---

## Tests (1305 PASS)

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
| test_ui_*.py (8 files) | 95 | UI Phase 0-5: bootstrap, theme, window, neuron(26), tree(13), classifier, detail(12), navi(14) |
| Others | ~745 | Mycelium, feed, sync, vault, doctor, decay, etc. |
