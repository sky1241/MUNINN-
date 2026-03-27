# MUNINN — Winter Tree (Carte Technique)

> Ce fichier est une CARTE DE NAVIGATION pour Claude. Pas un changelog.
> Objectif: savoir EXACTEMENT ou chercher quoi dans le code, avec les numeros de lignes.
> Mis a jour: 2026-03-27. Engine: 17688 lignes, 11 fichiers + bridge_hook.py 107L. Tests: 105 fichiers, 918 tests, 0 FAIL.

## Architecture

```
        [80 test files, 607 tests]     +5 Cime (validation)
       /    \
    [.mn]  [.mn]                       +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                         +2 Branches (metadata arbre)
      |
   [muninn.py 7581L]                   +1 Tronc (moteur principal)
      |
   [mycelium.py 2695L + db 1012L]      0 SOL — champignon vivant (SQLite)
      |
   [vault.py 389L + sync_tls.py 313L] -1 Sous-sol — securite
      |
   [forge.py 2048L + cube.py 3264L]   -2 Fondations — debug + resilience
      |
   [wal_monitor 89L + tokenizer 43L]  -3 Racines — infrastructure
```

---

## muninn.py — Moteur Principal (7581 lignes)

### Globals & Config (1-191)
| Fonction | Lignes | Role |
|----------|--------|------|
| UNIVERSAL_RULES | 54-64 | Dict FR->EN compact (done, wip, fail...) |
| _SECRET_PATTERNS | 135-169 | Regex detection secrets (GitHub PAT, AWS, API keys, FR: cle/mdp/passphrase) |
| _safe_path | 172-182 | Sanitize paths display (max 3 segments) |
| load_codebook / get_codebook | 98-123 / 185-190 | Charge rules compression (universal + mycelium) |

### Scan Repo (195-354)
| scan_repo | 195-353 | R5: auto-genere codebook local (frequent words, entities, paths) |

### Tree I/O (356-519)
| Fonction | Lignes | Role |
|----------|--------|------|
| adaptive_boot_budget | 368-376 | Budget boot: 15% contexte, floor 15K, cap 100K |
| init_tree | 401-431 | Init arbre vide avec root node |
| load_tree | 434-459 | Charge tree.json + validation path traversal + recovery corruption |
| save_tree | 462-485 | Ecriture atomique via tempfile + os.replace |
| _safe_tree_path | 503-510 | Anti path-traversal (resolved path must stay in TREE_DIR) |
| compute_hash | 513-518 | SHA-256 fichier (8 hex chars) |

### Memory Intelligence (521-732)
| Fonction | Lignes | Role |
|----------|--------|------|
| _ebbinghaus_recall | 521-570 | Spaced repetition: p = 2^(-delta/h), A1 usefulness, V6B valence |
| _actr_activation | 573-619 | ACT-R base-level: B=ln(sum(t_j^(-d))), blend 70% Ebbinghaus + 30% ACT-R |
| compute_temperature | 630-648 | Score branche 0-1 (80% recall, 20% fill pressure) |
| refresh_tree_metadata | 651-662 | Recalcule hash + lines + temperature tous les noeuds |
| read_node | 665-731 | Lit .mn + P34 integrity + B1 reconsolidation si froid |

### Compression L0-L7 (736-1388)
| Fonction | Lignes | Role |
|----------|--------|------|
| _line_density | 736-780 | Score densite info par ligne (0=bruit, 1=fait) |
| _kicomp_filter | 783-855 | Drop lignes basse-densite si overflow budget |
| _ncd | 860-877 | Normalized Compression Distance (zlib, 0=identique, 1=different) |
| _tfidf_relevance | 887-941 | TF-IDF cosine similarity query vs documents |
| compress_line | 946-1145 | Pipeline: L1 markdown, L2 fillers, L3 phrases, L4 numbers, L5 rules, L6 mycelium, L7 kv |
| extract_facts | 1147-1253 | Extraction nombres, dates, identifiers, kv, code patterns |
| tag_memory_type | 1255-1266 | Tags P14: D>/B>/F>/E>/A> |
| compress_section | 1268-1388 | Compresse section (P14 tags + P26 line dedup + P27 read dedup) |
| _resolve_contradictions | 1391-1462 | C7: skeleton dedup, last-writer-wins |

### Compression L10-L11 (1465-1733)
| Fonction | Lignes | Role |
|----------|--------|------|
| _novelty_score | 1497-1560 | Score nouveaute (0=generique LLM, 1=fait unique) |
| _generate_cue | 1563-1618 | Compresse ligne connue en cue minimal (2-10 tokens) |
| _cue_distill | 1621-1661 | L10 Cue Distillation (Bartlett 1932) |
| _extract_rules | 1669-1733 | L11 Rule Extraction (Kolmogorov 1965) — factorise patterns kv |

### Compression L9 API (1736-1838)
| Fonction | Lignes | Role |
|----------|--------|------|
| _llm_compress_chunk | 1736-1759 | Un appel L9 Haiku avec retry + token budget |
| _llm_compress | 1761-1837 | L9 avec chunking (16K/appel) pour textes longs |

### File Compression & Tree Building (1839-2327)
| Fonction | Lignes | Role |
|----------|--------|------|
| compress_file | 1839-1894 | Pipeline complet: L0-L7 + L10 + L11 + secrets + (L9) |
| build_tree | 1896-1988 | Construit arbre L-system (recursive, balanced branching) |
| grow_branches_from_session | 1990-2177 | Pousse branches depuis session compressee (P3/P5/P6) |
| extract_tags | 2179-2237 | Extrait tags structurels + keywords |
| _load_virtual_branches | 2214-2326 | P20c: branches read-only depuis autres repos |

### Boot & Retrieval (2329-3284)
| Fonction | Lignes | Role |
|----------|--------|------|
| boot | 2329-2942 | **COEUR**: charge root + branches pertinentes (TF-IDF + spreading activation + Ebbinghaus + blind spots + predictions) |
| recall | 2944-3060 | P29: recherche mid-session (grep sessions + tree + errors) |
| bridge | 3065-3218 | P41: pont mycelium live (spreading activation + matches + fusions) |
| bridge_fast | 3221-3284 | P42: pont leger pour hooks (<0.5s, get_related) |

### Prediction & Analysis (3289-3529)
| Fonction | Lignes | Role |
|----------|--------|------|
| predict_next | 3289-3365 | B4: prediction prochaines branches (Endsley L3) |
| detect_session_mode | 3367-3421 | B5: convergent (1.5) vs divergent (0.5) |
| classify_session | 3441-3527 | B5: feature/debug/explore/refactor/review |

### Sleep & Consolidation (3544-3836)
| Fonction | Lignes | Role |
|----------|--------|------|
| _sleep_consolidate | 3544-3697 | Wilson & McNaughton 1994: merge branches froides NCD + dedup + L10+L11 |
| huginn_think | 3699-3779 | H3: genere insights depuis dreams (pattern extraction) |
| _light_prune | 3794-3836 | Prune rapide hot/cold/dead sans recompression |

### Prune (3838-4218)
| prune | 3867-4260 | **R4**: elagage complet — hot/cold/dead, sleep consolidation, **MYCELIUM DECAY** (4062-4075), optimal forgetting L9, dust removal, fact regen, dreams H1/H2 |

### Diagnostics (4223-4554)
| Fonction | Lignes | Role |
|----------|--------|------|
| show_status | 4223-4255 | Affiche arbre (noeuds, lignes, temperature, hash, tags) |
| doctor | 4258-4419 | Pre-flight check (<5s): Python, SQLite, tiktoken, Anthropic, mycelium |
| diagnose | 4421-4526 | Sante arbre (doublons, fichiers manquants, corruption) |
| verify_compression | 5049-5112 | Verifie qualite compression (fact retention, ratio, mycelium) |

### Bootstrap & Init (4556-4947)
| Fonction | Lignes | Role |
|----------|--------|------|
| bootstrap_mycelium | 4556-4610 | Cold start: scan -> mycelium -> root.mn -> branches |
| generate_root_mn | 4662-4788 | Genere root.mn depuis fichiers scannes |
| install_hooks | 4984-5044 | Installe hooks Claude Code (PreCompact, SessionEnd, Stop) |

### Transcript Parsing & Feed (5116-5800)
| Fonction | Lignes | Role |
|----------|--------|------|
| _compress_code_blocks | 5116-5146 | P17: compresse blocs code (garde signatures, drop bodies) |
| parse_transcript | 5253-5384 | Parse JSONL/JSON/MD, L0 tool strip, P28 tics, P27 read dedup |
| feed_from_transcript | 5492-5570 | Feed mycelium, **GRACEFUL TIMEOUT** (check every msg, save progress + exit at 60s), resumable via feed_progress.json |
| _semantic_rle | 5573-5667 | Collapse boucles debug/retry (detecte lignes quasi-identiques) |
| compress_transcript | 5669-5800 | Pipeline complet transcript -> .mn |

### Session Index & Errors (5762-6170)
| Fonction | Lignes | Role |
|----------|--------|------|
| _update_session_index | 5762-5855 | P22: index sessions avec metadata |
| _load_relevant_sessions | 5857-5908 | Charge sessions passees par TF-IDF |
| _extract_error_fixes | 5970-6013 | P18: paires erreur/fix -> errors.json |
| _surface_known_errors | 6015-6038 | Surface erreurs connues au boot |
| _MuninnLock | 6198-6310 | Self-healing mutex: PID check + heartbeat + max age (1h) |

### Feed Hooks (6241-6787)
| Fonction | Lignes | Role |
|----------|--------|------|
| _hook_log | 6241-6250 | Log invocation hook dans .muninn/hook.log |
| feed_from_hook | 6252-6328 | Hook PreCompact/SessionEnd: stdin -> compress -> grow -> sync meta |
| feed_from_stop_hook | 6330-6371 | P32: hook Stop debounced (30s grace) |
| feed_history | 6441-6583 | Rattrape tous les transcripts passes (idempotent) |
| feed_watch | 6585-6710 | Poll-based: process transcripts qui ont grandi |
| ingest | 6712-6787 | Ingere fichiers/dossiers externes dans l'arbre |

### Secret Scrub (7032-7128)
| Fonction | Lignes | Role |
|----------|--------|------|
| _SCRUB_EXTENSIONS | 7032-7037 | Extensions cibles: .jsonl, .json, .md, .mn, .txt, .log, .csv, .yaml, .yml, .toml, .ini, .cfg, .env, .py, .js, .ts, .sh, .bash, .zsh, .ps1 |
| _TRIGGER_VALUE_PATTERNS | 7039-7046 | Keyword+value redaction: cle/key/password/mdp/secret/token + value |
| scrub_secrets | 7048-7128 | Universal secret redaction (dry-run/force). Protected files: .credentials.json, .env, settings.json, config.json |

### Live Injection & CLI (6789-7535)
| inject_memory | 6789-6877 | B7: injection live fait -> branche + mycelium |
| main | 6882-7535 | CLI argparse: init/status/doctor/boot/feed/prune/recall/bridge/inject/scrub/... |

---

## mycelium.py — Champignon Vivant (2695 lignes)

### Init & Load (60-271)
| Methode | Lignes | Role |
|---------|--------|------|
| __init__ | 60-73 | Init SQLite lazy-mode (repo_path, federated, zone) |
| _load | 75-137 | Auto-detect: SQLite -> JSON migration -> fresh |
| _load_from_sqlite | 139-165 | Load meta depuis SQLite, connections sur disque (lazy) |
| save | 174-262 | Persiste SQLite + meta + translations flush |
| close | 264-271 | Ferme handle DB persistant (cleanup/tests) |

### Observation (277-522)
| Methode | Lignes | Role |
|---------|--------|------|
| observe | 283-435 | Enregistre co-occurrences, DELTA MODE (skip paires deja vues cette session), congestion detect (decay d'urgence si batch > 2s), V6A arousal boost + _check_fusions |
| observe_text | 437-485 | Extrait concepts du texte, chunk par paragraphes |
| observe_latex | 487-514 | Chunk par \section/\begin pour arXiv |
| observe_with_concepts | 516-547 | Observe avec liste externe (OpenAlex 65K) |
| start_session | 1229-1233 | Reset _session_seen (delta tracking) + session counter |

### Fusion & Decay (524-903)
| Methode | Lignes | Role |
|---------|--------|------|
| _check_fusions | 524-609 | Detecte paires > FUSION_THRESHOLD, bloque hubs S3 |
| _get_high_degree_concepts | 646-712 | S3: top 5% degre = stopwords universels |
| decay | 768-852 | Halve poids stale, skip immortels (3+ zones), saturation A4 |
| effective_weight | 854-884 | P20.3: TF-IDF inverse federated |

### Retrieval (905-1182)
| Methode | Lignes | Role |
|---------|--------|------|
| get_fusions | 905-912 | Tous les blocs fusionnes |
| get_compression_rules | 914-938 | Rules {pattern: replacement} pour compression |
| get_related | 940-982 | Top-N voisins, zone-aware boost |
| spread_activation | 984-1074 | Collins & Loftus 1975: propagation semantique (hops, decay, hub penalty) |
| transitive_inference | 1076-1137 | V3A: inference A->C via A->B->C, Dijkstra-like |

### Zones & Anomalies (1188-1639)
| Methode | Lignes | Role |
|---------|--------|------|
| detect_zones | 1188-1342 | Spectral clustering (Laplacian + KMeans), auto-name, spectral_gap A5 |
| detect_anomalies | 1445-1507 | B2: isolated (degre<=1), hubs (mean+2sigma), weak zones |
| detect_blind_spots | 1511-1639 | B3: trous structurels (Burt 1992), same-zone gaps + transitive gaps |

### Sleep & Dreams (1647-2016)
| Methode | Lignes | Role |
|---------|--------|------|
| trip | 1647-1773 | H1: BARE Wave model — lower beta, dream connections cross-cluster |
| dream | 1847-1995 | H2: consolidation — strong pairs, absences, validated dreams |

### Sync & Federation (2034-2390)
| Methode | Lignes | Role |
|---------|--------|------|
| _load_meta_dir | 2038-2055 | Config meta_path: ~/.muninn/config.json -> shared dir (NAS/OneDrive) |
| meta_path / meta_db_path | 2057-2065 | Chemin meta-mycelium configurable (defaut ~/.muninn/) |
| sync_to_meta | 2067-2195 | Push local -> meta-mycelium partage (SQLite) |
| pull_from_meta | 2197-2215 | Pull connections pertinentes depuis meta |
| _pull_from_meta_sqlite | 2217-2333 | Pull SQLite (M9 fix: query_ids init) |

### Constantes Cles
- FUSION_THRESHOLD = 5, DECAY_HALF_LIFE = 30 jours
- MAX_CONNECTIONS = 0 (unlimited), MIN_CONCEPT_LEN = 3
- IMMORTAL_ZONE_THRESHOLD = 3, DEGREE_FILTER_PERCENTILE = 0.05

---

## mycelium_db.py — Backend SQLite (1012 lignes)

### Schema & Init (67-132)
- Tables: concepts (id, name), edges (a, b, count, first_seen, last_seen), fusions (a, b, form, strength), edge_zones (a, b, zone)
- Pragmas: WAL mode, FK, mmap 64MB, page_size 4096

### CRUD (134-618)
| Methode | Lignes | Role |
|---------|--------|------|
| _get_or_create_concept | 134-159 | Get/create concept ID + cache |
| upsert_connection | 224-267 | Insert/increment edge |
| get_connection | 197-222 | Fetch edge + zones |
| delete_connection | 376-388 | Remove edge + fusion + zones |
| neighbors | 599-618 | Voisins + counts (optionnel top-N) |
| batch_upsert_connections | 622-644 | Batch insert atomique + WAL on_write |
| batch_delete_connections | 646-662 | Batch delete atomique + WAL on_write |

### Migration (679-781)
| migrate_from_json | 679-781 | [static] JSON -> SQLite, batch 5K rows, rename .bak |

### ConceptTranslator S4 (803-1012)
| Methode | Lignes | Role |
|---------|--------|------|
| is_english | 848-863 | 1 token BPE = anglais |
| translate_batch | 883-916 | Batch Haiku API + cache SQLite |
| normalize_concepts | 991-1012 | Traduit non-EN -> EN |

---

## cube.py — Resilience par Destruction (3264 lignes)

### Scan & Structure (43-492)
| Fonction | Lignes | Role |
|----------|--------|------|
| B1: scan_repo | 176-237 | Scan recursif fichiers source |
| B3: Cube dataclass | 251-286 | id, content, sha256, file_origin, lines, level, neighbors, temp |
| B4: subdivide_file | 383-457 | Split fichier en cubes ~88 tokens (semantic boundaries) |
| B4: subdivide_recursive | 460-481 | Split recursif /8 par niveau |
| B5: sha256_hash | 320-323 | SHA-256 sur contenu normalise |
| B6: CubeStore | 493-720 | SQLite WAL, tables cubes/neighbors/cycles |

### AST & Neighbors (721-933)
| Fonction | Lignes | Role |
|----------|--------|------|
| B7: parse_dependencies | 820-837 | AST Python + regex JS/TS/Go/Java |
| B7b: extract_ast_hints | 849-922 | Pre-destruction: functions, classes, imports, indent |
| B8: assign_neighbors | 934-1017 | Adjacence sequentielle + deps, max 9 voisins |

### LLM Providers (1018-1453)
- B11: LLMProvider ABC (1018-1062), B12: OllamaProvider (1063-1159)
- B13: ClaudeProvider (1160-1217), B14: OpenAIProvider (1218-1271)
- B15: FIMReconstructor (1272-1400): lexicon + AST hints + FIM/prompt
- MockLLMProvider (1403-1442)

### Reconstruction & Cycle (1454-1745)
| Fonction | Lignes | Role |
|----------|--------|------|
| B16: reconstruct_cube | 1460-1502 | Orchestre B15+B17+B18+B19 |
| B17: validate_reconstruction | 1507-1513 | SHA-256 compare |
| B18: compute_hotness | 1518-1530 | Perplexite voisins |
| B19: compute_ncd | 1535-1559 | NCD zlib (seuil 0.3) |
| run_destruction_cycle | 1562-1700 | CYCLE COMPLET: reconstruit + B30+B29+B23+B24+B22+B38 |
| _add_semantic_neighbors | 1703-1743 | Mycelium spreading activation (cycle 2+) |

### Orchestration (1746-1981)
| Fonction | Lignes | Role |
|----------|--------|------|
| post_cycle_analysis | 1746-1850 | B27+B28+B9+B10+B26+B35+B31+B37+B38 — toutes les diagnostiques |
| B23: compute_temperature | 1854-1876 | 0.4*perplexity + 0.4*(1-success_rate) + 0.2*failures |
| B24: kaplan_meier_survival | 1889-1908 | S(t) = prod(1-d_i/n_i) |
| B25: filter_dead_cubes | 1911-1959 | Vire commentaires/TODOs |
| prepare_cubes | 1952-1981 | B25 + B21 pre-filtre (~30% trivial) |

### Metrics & Levels (1983-2234)
| Fonction | Lignes | Role |
|----------|--------|------|
| B26: compute_gods_number | 1983-2041 | Cubes chauds irremplacables + bornes LRC/MERA |
| B27: build_level_cubes | 2043-2088 | Groupe 8 cubes lv0 -> 1 cube lv1 (88->704->5632) |
| B28: propagate_levels | 2091-2136 | Remontee temperature max entre niveaux |
| B29: feed_mycelium_from_results | 2139-2207 | Connexions "mechanical" succes=+1.0, echec=-0.5 |
| B30: hebbian_update | 2209-2234 | Δw = ±η*0.1 (renforce/affaiblit voisins) |

### External Tools (2236-2475)
| Fonction | Lignes | Role |
|----------|--------|------|
| B31: git_blame_cube | 2238-2319 | Lie cubes chauds a l'historique git |
| B32: CubeScheduler | 2320-2380 | Async — run quand repo quiet (5min) |
| B33: CubeConfig | 2382-2473 | Config YAML + get_provider() |

### CLI (2481-2652)
| Fonction | Lignes | Role |
|----------|--------|------|
| cli_scan | 2483-2517 | B1+B4+B7+B8+B6 |
| cli_run | 2520-2592 | FULL PIPELINE: prepare + cycles + analysis (ALL bricks) |
| cli_status | 2595-2627 | God's Number + temperature stats |
| cli_god | 2629-2652 | Compute + display God's Number |

### Graph Algorithms (2654-2911)
| Fonction | Lignes | Role |
|----------|--------|------|
| B9: laplacian_rg_grouping | 2676-2722 | Spectral clustering (Laplacien + k-means) |
| B10: cheeger_constant | 2758-2802 | Bottleneck detection (Fiedler vector) |
| B20: belief_propagation | 2804-2853 | BP inference Pearl 1988 |
| B21: survey_propagation_filter | 2856-2875 | Pre-filtre cubes triviaux (~30%) |
| B22: tononi_degeneracy | 2878-2911 | Fragilite cube (voisins redondants vs critiques) |

### Diagnostics & Feedback (2913-3264)
| Fonction | Lignes | Role |
|----------|--------|------|
| B35: cube_heatmap | 2913-2946 | Temperatures groupees par fichier |
| B36: fuse_risks | 2948-3019 | Forge defect + Cube temperature |
| B37: auto_repair | 3021-3087 | Patches FIM pour cubes chauds |
| B38: record_anomaly + feedback_loop | 3132-3264 | Anomalies -> validation git -> mycelium |
| Quarantine | 3090-3129 | Sauvegarde contenu corrompu avant guerison |

---

## forge.py — Debug Universel (2048 lignes)

### Commandes
| Commande | Fonction | Lignes | Papier |
|----------|----------|--------|--------|
| (default) | run_tests | 139-202 | pytest capture |
| --predict | predict_defects | 973-1108 | Hassan 2009 (Kalman + wavelet) |
| --heatmap | show_heatmap | 430-493 | Kaner 2003 (Pareto) |
| --locate | fault_locate | 1507-1609 | Abreu 2007 (Ochiai SBFL) |
| --gen-props | gen_props | 1282-1449 | Claessen & Hughes 2000 (Hypothesis) |
| --minimize | minimize_input | 1204-1281 | Zeller 2002 (ddmin) |
| --bisect | bisect_test | 494-576 | Zeller 1999 |
| --flaky | detect_flaky | 373-429 | Luo 2014 |
| --mutate | run_mutation | 1450-1506 | DeMillo 1978 |
| --anomaly | detect_anomalies | 1610-1709 | Kalman timeseries |
| --robustness | measure_robustness | 1710-1834 | Newman Q-modularity |
| --fast | run_fast | 684-740 | Impact analysis |
| --snapshot | snapshot_capture/check | 741-840 | Golden files |

---

## vault.py — Coffre-Fort (389 lignes)

| Fonction | Lignes | Role |
|----------|--------|------|
| _derive_key | 55-63 | PBKDF2-HMAC-SHA256, 600K iter |
| _encrypt_bytes / _decrypt_bytes | 66-81 | AES-256-GCM (nonce 12B + tag 16B) |
| _secure_delete | 96-132 | 3-pass overwrite + random rename + unlink |
| _audit_log | 135-155 | OWASP JSONL audit trail |
| Vault.init | 171-197 | Setup salt + verify hash |
| Vault.lock / unlock | 263-308 | Encrypt/decrypt tous fichiers sensibles |
| Vault.rekey | 334-389 | Re-chiffre avec nouvelle cle (preserves old key on partial failure) |

---

## sync_tls.py — Sync TLS (313 lignes)

| Classe/Fonction | Lignes | Role |
|-----------------|--------|------|
| generate_certs | 42-92 | RSA 2048 self-signed, 365 jours |
| RateLimiter | 124-143 | Token bucket per-IP |
| SyncServer | 149-263 | TLS 1.3, mTLS optionnel, dispatch push/pull/ping |
| SyncClient | 269-313 | Client TLS, verify configurable |

---

## wal_monitor.py — WAL Flush Adaptatif (89 lignes)

| Classe/Fonction | Lignes | Role |
|-----------------|--------|------|
| WALConfig | 15-39 | check_every=50, threshold=1000 pages, emergency=50K, max_interval=90s |
| WALMonitor.on_write | 84-89 | Appele apres chaque commit, checkpoint si necessaire |
| WALMonitor.checkpoint | 70-82 | PRAGMA wal_checkpoint(PASSIVE), log duree |

Integre dans: CubeStore.__init__ (cube.py) et MyceliumDB.__init__ (mycelium_db.py)

---

## bridge_hook.py — Secret Sentinel + Live Bridge (107 lignes)

| Fonction | Lignes | Role |
|----------|--------|------|
| _shannon_entropy | 17-24 | Shannon entropy d'une string (haute = probable secret) |
| _has_char_diversity | 26-30 | 3+ classes de caracteres (upper, lower, digit, special) |
| main | 32-107 | P42 UserPromptSubmit: mycelium bridge + Secret Sentinel 3 niveaux |

### Secret Sentinel — 3 niveaux de detection
1. **API key patterns**: regex structurels (_SECRET_PATTERNS) — match direct
2. **Trigger + entropy**: mot-cle (key/password/token/mdp...) + valeur entropy > 2.8 + char diversity
3. **Standalone high-entropy**: strings >= 10 chars, entropy > 3.5, char diversity (sans trigger)

### Fixes Passe 15
- `sys.stdout.flush()` apres warning print: `import muninn` (ligne 35-36) remplace sys.stdout avec wrapper UTF-8, buffer non-flushe etait perdu
- `sys.stdin.buffer.read().decode("utf-8")` pour encodage Windows correct
- Template dans `_generate_bridge_hook()` (muninn.py:4950) synchronise avec hook live

---

## Ou chercher quoi (index thematique)

| Je cherche... | Fichier | Lignes |
|---------------|---------|--------|
| Compression texte | muninn.py | 946-1145 (L1-L7), 1465-1733 (L10-L11), 1736-1837 (L9) |
| Boot/chargement memoire | muninn.py | 2329-2942 (boot), 368-376 (budget) |
| Arbre load/save | muninn.py | 434-485 (load/save), 401-431 (init) |
| Elagage/prune | muninn.py | 3838-4218 |
| Feed transcript | muninn.py | 5253-5384 (parse), 5492-5570 (feed+timeout), 5669-5800 (compress), 6426-6504 (hook) |
| Injection live | muninn.py | 6789-6877 |
| Co-occurrences | mycelium.py | 283-435 (observe, delta+congestion), 549-634 (fusions) |
| Spreading activation | mycelium.py | 984-1074 |
| Zones/clusters | mycelium.py | 1188-1342 |
| Blind spots | mycelium.py | 1511-1639 |
| Dreams/trip | mycelium.py | 1647-1773 (trip), 1847-1995 (dream) |
| Sync cross-repo | mycelium.py | 2034-2390 |
| Team shared meta config | ~/.muninn/config.json | {"meta_path": "//nas/shared"} |
| SQLite operations | mycelium_db.py | 134-662 |
| Migration JSON->SQLite | mycelium_db.py | 679-781 |
| Traduction concepts | mycelium_db.py | 803-1012 |
| Encryption | vault.py | 55-93 (crypto), 263-308 (lock/unlock) |
| TLS sync | sync_tls.py | 149-263 (server), 269-313 (client) |
| Defect prediction | forge.py | 973-1108 |
| Fault localization | forge.py | 1507-1609 |
| Property tests | forge.py | 1282-1449 |
| Cube destruction cycle | cube.py | 1562-1700 |
| God's Number | cube.py | 1983-2041 |
| Spectral clustering | cube.py 2676-2722 / mycelium.py 1188-1342 |
| WAL checkpoints | wal_monitor.py | 70-89 |
| Spaced repetition | muninn.py | 521-570 (_ebbinghaus_recall) |
| Path security | muninn.py | 503-510 (_safe_tree_path), 172-182 (_safe_path) |
| Secret filtering | muninn.py | 135-169 (_SECRET_PATTERNS) |
| Secret scrub (files) | muninn.py | 7032-7128 (scrub_secrets), CLI: `muninn scrub <path>` |
| Secret sentinel (live) | bridge_hook.py | 17-66 (Shannon entropy + 3 levels) |

## Constantes critiques

| Constante | Valeur | Fichier | Ligne |
|-----------|--------|---------|-------|
| BUDGET max_loaded_tokens | 50K | muninn.py | 365 |
| FUSION_THRESHOLD | 5 | mycelium.py | ~280 |
| DECAY_HALF_LIFE | 30 jours | mycelium.py | ~770 |
| DEGREE_FILTER_PERCENTILE | 0.05 (top 5%) | mycelium.py | ~650 |
| LOCK MAX_AGE_SECONDS | 3600 (1h) | muninn.py | 6202 |
| LOCK HEARTBEAT_STALE | 120s | muninn.py | 6201 |
| WAL auto-checkpoint | 50MB | mycelium.py | ~375 |
| FEED_TIMEOUT max_seconds | 60s | muninn.py | 5492 |
| CONGESTION_THRESHOLD | 2.0s | mycelium.py | ~370 |
| WAL check_every | 50 commits | wal_monitor.py | 19 |
| WAL emergency_threshold | 50000 pages (~200MB) | wal_monitor.py | 25 |
| PBKDF2 iterations | 600K | vault.py | 58 |
| AES nonce size | 12 bytes | vault.py | 68 |
| TLS minimum version | 1.3 | sync_tls.py | ~38 |
| TARGET_TOKENS (cube) | 4K | cube.py | ~337 |

## Mycelium Health System (2026-03-27)

**Problem**: MuninnWatch crash loop since 2026-03-21. Mycelium grew to 14.9M edges / 1.3GB. observe_text() too slow, process killed by timeout every 15 min. Tree empty (0 branches), session index frozen.

**4 briques fix**:
1. **Delta observe** (mycelium.py:323-358): _session_seen set skips pairs already upserted this session. ~90% write reduction.
2. **Decay in prune** (muninn.py:4062-4075): decay() wired into prune(). Was NEVER called before — dead code. Removes edges with count < 0.01 after DECAY_HALF_LIFE days.
3. **Congestion detect** (mycelium.py:366-382): First batch timed. If > 2s, emergency decay() runs inline. Checked once per instance.
4. **Graceful timeout** (muninn.py:5555-5568): feed_from_transcript checks time after EVERY message (not just every 50). Saves progress to feed_progress.json and exits cleanly. Next cycle resumes. Always progresses.

**Key insight**: decay() had 0 effect (all edges < 21 days old). Real bottleneck = DB size (1.3GB) makes individual upserts slow. Delta mode + timeout = the actual fix.

## Audit Debug (2026-03-18)

12 passes, 90 bugs fixes, convergence atteinte (0 bug en passe 12 finale).
Outils: forge --predict/--heatmap/--anomaly/--locate/--gen-props/--robustness + 8 agents deep audit.
Details: voir CHANGELOG.md section "Debug Audit — Extermination Totale".

## Scan 15 — Secret Hardening (2026-03-21)

- scrub_secrets(): redaction universelle secrets dans fichiers (JSONL/JSON/MD/YAML/logs/code)
- Secret Sentinel: detection temps-reel dans bridge_hook.py (3 niveaux: regex, trigger+entropy, high-entropy)
- FR patterns ajoutes a _SECRET_PATTERNS (cle/mdp/passphrase)
- Fix: bridge_hook stdout flush + stdin Windows encoding
