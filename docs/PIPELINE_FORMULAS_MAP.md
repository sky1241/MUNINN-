# PIPELINE FORMULAS MAP — Muninn (2026-05-10)

Carte exhaustive : pour chaque pipeline (compress / boot / prune / feed /
mycelium / forge), liste les algorithmes/formules dans l'**ordre d'exécution**,
avec **fichier:ligne** + **paper référence** + **paramètre clé**.

Source : audit deep 5 agents 2026-05-10 PM (post-P3 split + F5 hook wiring).

**Légende status** :
- ✅ ACTIVE : exécuté à chaque appel pipeline
- 🔵 OPT-IN : opt-in via env var ou flag CLI
- 🟡 SMOKE-ONLY : exécuté en CI, pas en prod runtime
- ❌ MISSING : claim doc mais pas appelé dans le code

---

## 1. PIPELINE COMPRESSION (`compress_file`, `compress_transcript`)

Ordre exécutif : L0 → L1 → ... → L11 → (L12 opt-in) + filtres P transversaux.

| # | Couche | Fichier:ligne | Formule / Paper | Status |
|---|---|---|---|---|
| 0 | **L0 tool_strip** | `muninn_feed.py:323,355` (parse_transcript) | regex strip tool output (keep name + 1-line summary) | ✅ |
| 1 | **L1 markdown_strip** | `muninn_layers.py:455` (compress_line) | regex headers/bold/backticks | ✅ |
| 2 | **L2 filler_removal** | `muninn_layers.py:536` | regex 40+ articles/connectors + learned fillers | ✅ |
| 3 | **L3 phrase_collapse** | `muninn_layers.py:487` | regex 23 patterns ("in order to" → "to") | ✅ |
| 4 | **L4 number_shortening** | `muninn_layers.py:578` | regex 1000→1K, 1000000→1M | ✅ |
| 5 | **L5 universal_rules** | `muninn_layers.py:589` | codebook text_rules (COMPLET→done) | ✅ |
| 6 | **L6 mycelium_fusion** | `muninn_layers.py:601` | drop short paired concept si strength≥10 | ✅ |
| 7 | **L7 key_value** | `muninn_layers.py:624` | regex `acc: 94.2%` → `acc=94.2%` | ✅ |
| 8 | **L9 LLM compress** | `muninn_layers.py:1279` (`_llm_compress`) | Claude Haiku API, chunk-aware, redacted, fallback identity | 🔵 (env `ANTHROPIC_API_KEY`) |
| 9 | **L10 cue_distill** | `muninn_layers.py:1131` (`_cue_distill`) | Predictive Coding (Rao & Ballard 1999) — novelty<0.35→retrieval cue | ✅ |
| 10 | **L11 rule_extract** | `muninn_layers.py:1179` (`_extract_rules`) | Kolmogorov 1965 — factorize repeated key=value sur pipes | ✅ |
| 11 | **L12 BudgetMem** | `muninn_layers.py:76` (`_l12_budget_pass`) → `budget_select.py` + `muninn_tree.py:spill_chunks_to_tree` | arxiv 2511.04919 + spill-to-tree (Shomrat & Levin 2013 calque V9A+) — paragraph scoring 6 features, dropped must-keep spillés en branches tree | 🔵 (env `MUNINN_L12_BUDGET`) — **BUG-104 FIXED 2026-05-10** |

### Filtres transversaux (P10-P38)

| Filtre | Fichier:ligne | Effet | Status |
|---|---|---|---|
| P10 secret_redact | `muninn_feed.py:563`, `muninn_layers.py:1410` | regex 49 patterns redact (GH/AWS/Bearer/PII) | ✅ |
| P14 tag_memory | `muninn_feed.py:655` | classifier D>/B>/F>/E>/A> tags | ✅ |
| P16 session_log | `muninn_feed.py:761` | append 1-line summary à root.mn | ✅ |
| P17 code_compress | `muninn_feed.py:302` (parse_transcript) → `_compress_code_blocks:78` | keep signatures + ellipsis | ✅ |
| P18 error_extract | `muninn_feed.py:764` | extract error/fix pairs auto-surface | ✅ |
| P20 meta_sync | `muninn_feed.py:1269,1279,1425` | sync to meta-mycelium cross-repo | ✅ |
| P22 index_session | `muninn_feed.py:772` (`_update_session_index:786`) | index .muninn/session_index.json | ✅ |
| P24 causal_protect | `muninn_layers.py:471` | protect "because/since/due to" du filler removal | ✅ |
| P25 priority_survive | `muninn_feed.py:664` | tag priority D>=5/B>=4/E>=3/F>=3/A>=2, keep on budget hit | ✅ |
| P26 dedup_lines | `muninn_feed.py:623` | exact + normalized fuzzy match | ✅ |
| P27 dedup_reads | `muninn_feed.py:268,329,362` | keep last Read par file_path | ✅ |
| P28 tics_strip | `muninn_feed.py:250,305` | regex drop "Let me", "I'll", "Here's" | ✅ |
| P38 format_detect | `muninn_feed.py:171,229` | auto-detect JSONL/JSON/markdown | ✅ |

---

## 2. PIPELINE BOOT (`muninn_tree_boot.py:boot()`)

Ordre exécutif : pré-warm query → expand → score chaque branche → dedup → load.

### Pré-warm query (ligne 266-330)

| # | Algo | Ligne | Effet | Status |
|---|---|---|---|---|
| 1 | A6 git diff pre-warm | `boot:266` | `git diff HEAD~1` → concepts as query si query absent | ✅ |
| 2 | P23 auto-continue | `boot:285` | session_index.json → last concepts si pas de query | ✅ |

### Expansion query (ligne 280-320)

| # | Algo | Paper | Ligne | Param |
|---|---|---|---|---|
| 3 | P15 query expansion | mycelium.get_related | `boot:306` | strength≥3 |
| 4 | P20b cross-repo meta-pull | mycelium.pull_from_meta | `boot:312` | guard 100MB DB |

### Scoring chaque branche (ligne 340-620)

Formule de base : `total = w_recall*recall + w_relevance*relevance + w_activation*activation + w_usefulness*usefulness + w_rehearsal*rehearsal_need` (poids ajustés B6).

| # | Algo | Paper | Ligne | Effet sur score |
|---|---|---|---|---|
| 5 | A2 ACT-R activation | Anderson 1993 | `boot:519` | sigmoid base-level → blended `0.7×Ebbinghaus + 0.3×ACT-R` |
| 6 | Ebbinghaus baseline | Settles & Meeder 2016 | `tree.py:412` | `p = 2^(-Δ/h)`, h doubles avec reviews, h₀=7j |
| 7 | TF-IDF relevance | cosine sim | `boot:341` | `_tfidf_relevance()` → `w_relevance=0.40` |
| 8 | B5 session mode detect | `detect_session_mode()` | `boot:343` | influence pondération B6 |
| 9 | Spreading activation | Collins & Loftus 1975 | `boot:352` | `mycelium.spread_activation` hops=2, decay=0.5 → bonus `w_activation=0.20` |
| 10 | V3A transitive inference | Wynne 1995, Paz-y-Mino 2004 | `boot:373` | `mycelium.transitive_inference` max_hops=3, β=0.5 → bonus +0.10 |
| 11 | B3 blind spots | Burt 1992 (struct holes) | `boot:393` | `mycelium.detect_blind_spots` → bonus +0.05 si tags ∩ blind_spots |
| 12 | B4 predict next | `predict_next` | `boot:404` | bonus +0.03 × score |
| 13 | V3B BToM | Baker, Saxe, Tenenbaum 2009 | `boot:412` | sigmoid posterior `(α/(α+1))*prior` → bonus +0.04 |
| 14 | B6 session classify | `classify_session()` | `boot:456` | ajuste poids debug/explore/review |
| 15 | V11B Boyd-Richerson | Boyd & Richerson 1985 | `boot:484` | 3 biais culturels : conformist + prestige + guided variation (β=0.3, μ=0.1) |
| 16 | V7B ACO pheromone | Dorigo, Maniezzo, Colorni 1996 | `boot:542` | `τ¹ × η²` (τ=usefulness×recall, η=relevance) → bonus +0.05 |
| 17 | V5A quorum sensing | Waters & Bassler 2005 | `boot:594` | Hill `n^k/(K^k+n^k)`, K=2, n_hill=3 → bonus +0.03 |
| 18 | V1A coupled oscillator | Yekutieli 2005 | `boot:608` | temperature coupling via tag-shared neighbours → ±0.02 (cap) |
| 19 | V5B cross-inhibition | Seeley et al. 2012 (Science) | `boot:628` | Lotka-Volterra dynamics post-rank, β=0.05, K=1.0, max_iter=5 |

### Charge + dedup (ligne 660-770)

| # | Algo | Ligne | Effet |
|---|---|---|---|
| 20 | Bloom novelty filter | `boot:660` | skip si <5% concepts nouveaux |
| 21 | C3 auto-preload | `boot:683` | top 3 predictions ≥0.3 score |
| 22 | P20c virtual branches | `boot:719` | `_load_virtual_branches` cross-repo si remaining_budget>500 |
| 23 | C2 boot feedback log | `boot:727` | blind_spots covered/uncovered → boot_feedback.json |
| 24 | P19 NCD dedup | `boot:762` | NCD<0.4 sur dernières 3 → skip |

### Surface session/errors/insights (ligne 800-900)

| # | Algo | Ligne | Effet |
|---|---|---|---|
| 25 | last_session load | `boot:800` | charge dernière .mn (tail si trop gros) |
| 26 | P22 session search | `boot:817` | `_load_relevant_sessions` (top 2 par concept overlap) |
| 27 | P18 known errors | `boot:825` | `_surface_known_errors` (≥2 word match) |
| 28 | H3 huginn surface | `boot:832` | `_surface_insights_for_boot` (top 3 insights) |
| 29 | V8B active sensing | Yang et al. 2016 | `boot:838` | si top 3 scores within 10% → suggest concept max-entropy |

### Filtre overflow + warning (ligne 880+)

| # | Algo | Ligne | Effet |
|---|---|---|---|
| 30 | P36 boot manifest | `boot:868` | save last_boot.json + v8b_clarify hint |
| 31 | KIComp filter | `boot:883` | si total > budget → drop low-info lines (density score) |
| 32 | A8 prune warning | `boot:889` | warn si cold>45% branches |

---

## 3. PIPELINE PRUNE (`muninn_tree_prune.py:prune()`)

Ordre exécutif : protect → suppress similar → detect anomalies → classify → recompress cold → consolidate → trip → dream → regen facts → delete dead.

### Protection / suppression (ligne 280-340)

| # | Algo | Paper | Ligne | Effet |
|---|---|---|---|---|
| 1 | A7 auto-backup | (custom) | `prune:240` | tar.gz pre-prune (last 5 backups kept) |
| 2 | V9B Reed-Solomon | Reed & Solomon 1960 | `prune:283` | sole carriers (1 branche carrier d'1 concept) → cold pas dead |
| 3 | I2 competitive suppression | Perelson 1989 | `prune:297` | `recall -= α × Σ NCD_sim × recall_j` (NCD<0.4), α=0.1, cap 500 branches at-risk |
| 4 | I3 negative selection | Forrest 1994 | `prune:339` | distance > 2.0 sur 2 metrics (lines + fact_ratio) → demote cold |

### Classification (ligne 380-440)

| # | Algo | Paper | Ligne | Effet |
|---|---|---|---|---|
| 5 | I1 Danger Theory boost | Greensmith 2008 | `tree.py:450` | `h *= (1 + γ × danger_score)`, γ=1.0 implicit |
| 6 | V4B EWC Fisher | Kirkpatrick 2017 | `tree.py:446` | `h *= (1 + λ_ewc × F_i)`, λ=0.5 |
| 7 | V6B valence-arousal | Talmi 2013 | `tree.py:441` | `h *= (1 + 0.3×|v| + 0.2×a)` |
| 8 | A1 usefulness modulation | GARCH (Bollerslev 1986) | `tree.py:420` | `h *= usefulness^β`, β=0.5 |
| 9 | R4 hot/cold/dead | (custom thresholds) | `prune:264` | recall ≥0.4 hot / <0.05 dead / 0.05-0.15 cold |
| 10 | B14 dust cleanup | (custom) | `prune:417` | lines≤3 + temp<0.3 → dead (sauf V9B sole carriers) |

### Re-compression cold (ligne 450-460)

| # | Algo | Ligne | Status |
|---|---|---|---|
| 11 | L9 cold recompression | `prune:452` | 🔵 (API key) |
| 12 | A2 safe truncated read | `prune:_safe_read_mn` | ✅ skip si UnicodeDecodeError |

### Consolidation + trip + dream (ligne 460-510)

| # | Algo | Paper | Ligne | Effet |
|---|---|---|---|---|
| 13 | H10 snapshot-rollback | (custom) | `prune:461` | json.dumps tree pré-consolidate |
| 14 | Sleep consolidation | Wilson & McNaughton 1994 | `_sleep_consolidate` | NCD<0.6 → merge similar cold (top-20 par recall, MAX_NCD_BRANCHES) |
| 15 | X9 access immortality fix | (custom) | `_sleep_consolidate:162` | `max(access_count)` not sum (anti-spike) |
| 16 | Mycelium decay | Ebbinghaus on edges | `prune:475` | `count / 2^(age/half_life)`, half_life=30j default |
| 17 | H1 trip (psilocybine) | "BARE Wave" ❓ + Carhart-Harris 2014 | `prune:491` | `dn/dt = α·n − β·n·ρ`, intensity=0.5, max_dreams=15 |
| 18 | H2 dream synthesis | (custom + Wilson&McNaughton) | `prune:503` | strong_pair / absence / imbalance insights → insights.json |

### Régénération facts (ligne 513-650)

| # | Algo | Paper | Ligne | Effet |
|---|---|---|---|---|
| 19 | V9A+ fact regen | Shomrat & Levin 2013 | `prune:513` | Extract D>/B>/F>/E>/A> tags des dead → inject best survivor (proximity / overlap / recency) |
| 20 | M3 tag cache | (perf fix) | `prune:527` | pre-cache `_surv_tags` |
| 21 | P34 boot integrity post-regen | (custom) | `prune:626` | update `hash + lines` du survivor |
| 22 | M7 per-branch error isolation | (custom) | `prune:645` | continue sur exception V9A+ |

### Sécurité / housekeeping

| # | Algo | Ligne | Effet |
|---|---|---|---|
| 23 | P8 NCD O(n²) cap | `_sleep_consolidate:57` | MAX_NCD_BRANCHES=20 (anti-explosion sur 2000+ branches) |
| 24 | B15 light prune | `_light_prune` | R<0.05 OR (≤3 lines + cold) — fast pour hooks, <1s |

---

## 4. PIPELINE FEED (`muninn_feed.py:feed_from_hook` / `compress_transcript`)

| # | Algo | Paper | Ligne | Effet |
|---|---|---|---|---|
| 1 | A4 transcript path validation | (security) | `muninn_feed.py:1186` `_validate_transcript_path` | reject hors `~/.claude/projects/` |
| 2 | P38 format auto-detect | — | `muninn_feed.py:171,229` | JSONL/JSON/markdown |
| 3 | I1 Danger Theory compute | Greensmith 2008 | `muninn_feed.py:835` | `0.4×err_rate + 0.3×retry + 0.2×switch + 0.1×chaos_ratio` |
| 4 | P22 session index update | `_update_session_index` | `muninn_feed.py:786` | json.append + cap 5000 entries |
| 5 | P18 error/fix extract | `_extract_error_fixes` | `muninn_tree.py:_extract_error_fixes` | ratio compression triggers |
| 6 | P16 session log | `_append_session_log` | `muninn_tree.py:_append_session_log` | append 1-line à root.mn R: |

---

## 5. MYCELIUM (le champignon — réseau de co-occurrences)

5 fichiers post-H6 split via mixins :

### Core (`mycelium.py`)

| # | Méthode | Paper / formule | Ligne | Effet |
|---|---|---|---|---|
| 1 | `decay` | Ebbinghaus | `mycelium.py:756` | `count / 2^(age/half_life)`, half_life=30j default |
| 2 | `adaptive_fusion_threshold` | A1 — `max(2, √N×0.4)` | `mycelium.py:875` | concepts↑→fuse moins agressif |
| 3 | `adaptive_decay_half_life` | A2 — sessions/jour | `mycelium.py:893` | range [15, 90] jours |
| 4 | `cleanup_orphan_concepts` | A3 — > 20% orphans | `mycelium.py:916` | bulk delete edges-less |
| 5 | `cleanup_orphan_zones` | P2 — orphan zone tags | `mycelium.py:949` | delete edge_zones manquantes |
| 6 | `vacuum_if_needed` | P3 — PRAGMA optimize | `mycelium.py:970` | si decay > 10s |
| 7 | `observe_text` / `observe_latex` | NFC normalize + tokenize | `mycelium.py:?` | feed concepts par paire |
| 8 | `pull_from_meta` | F4 sync_backend | `mycelium_meta.py:184` | query-filtered, max=1000, BUG-110 guard 100MB |
| 9 | `push_to_meta` / `sync_to_meta` | F4 — merge MAX(count) MIN(first) MAX(last) | `mycelium_meta.py:92` | atomic transaction, union(zones) |

### Activation (`mycelium_activation.py`)

| # | Méthode | Paper | Ligne | Effet |
|---|---|---|---|---|
| 10 | `spread_activation` | Collins & Loftus 1975 | `:386` | hops=adaptive, decay=0.5 → ranked concepts |
| 11 | `transitive_inference` | Wynne 1995, Paz-y-Mino 2004 | `:483` | `V(A→C) = strength(A,B) × strength(B,C) × β^hops`, max_hops=3, β=0.5 |
| 12 | `adaptive_hops` | A5 — degree adaptif | `:359` | dense (μ_deg>10) → 1, sparse (<3) → 3 |

### Zones (`mycelium_zones.py`)

| # | Méthode | Paper / formule | Ligne | Effet |
|---|---|---|---|---|
| 13 | `detect_zones` | Spectral clustering Laplacien sym | `:55` | k=√(N/10) clamped [2,12] |
| 14 | `auto_label_zones` | P20.5+6 spectral | `:207` | tag edges, fanout=64 |
| 15 | `_graph_entropy` | Shannon `H = −Σ p×log₂(p)` | `:301` | health metric (max=log₂(N)) |
| 16 | `_bfs_zones` | fallback (no scipy) | `:319` | DFS/BFS deque O(1), fanout=32 |

### Dream (`mycelium_dream.py`)

| # | Méthode | Paper | Ligne | Effet |
|---|---|---|---|---|
| 17 | `detect_anomalies` | mean+2σ for hubs | `:36` | isolated (deg≤1), hubs (>μ+2σ) |
| 18 | `detect_blind_spots` | Burt 1992 (structural holes) | `:98` | A-C missing si A-B & B-C strong |
| 19 | `trip` | "BARE Wave" ❓ + Carhart-Harris 2014 | `:231` | `dn/dt = α·n − β·n·ρ`, α=0.04(1+I), β=0.02(1−0.8I) |
| 20 | `dream` | Wilson & McNaughton 1994 | `:371` | strong pair / absence / imbalance → top 20 insights |

### Meta (`mycelium_meta.py`)

| # | Méthode | Paper | Ligne | Effet |
|---|---|---|---|---|
| 21 | `pull_from_meta` | F4 sync | `:184` | (déjà listé ci-dessus dans core) |
| 22 | `sync_to_meta` | F4 sync | `:92` | (idem) |

### DB (`mycelium_db.py`)

| # | Méthode | Effet | Ligne |
|---|---|---|---|
| 23 | `check_integrity` | A3 — PRAGMA integrity_check + WAL checkpoint | `:?` |
| 24 | SQLite tier3 schema | edges + concepts + edge_zones | toute la classe |

### 5.1 Cross-validation scientifique du mycelium (10 papers peer-reviewed)

Source : `sky1241/tree/docs/CROSSVAL_REPORT.md` (15.6KB, 386L) — **26 tests vs
10 papers, 25 MATCH, 1 FAIL expliqué** (différence config model vs Erdős-Rényi
sur C_random vs Towlson 2013 — mathématiquement correct, pas un bug).

Les 10 papers cités dans `sky1241/tree/CROSSVAL_REPORT.md` valident des
propriétés que MUNINN- mycelium reproduit implicitement (small-world,
betweenness, efficiency, meshedness). MUNINN- ne les invoque pas par nom
dans le code mais s'inscrit dans cette tradition réseau biologique.

| Paper | Journal | DOI / réf | Métrique cross-validée | Méthode MUNINN qui en bénéficie |
|---|---|---|---|---|
| **Bebber et al. 2007** | Proc R Soc B 274:2307 | `10.1098/rspb.2007.0459` | Meshedness α (sur *Phanerochaete velutina*, vrai champignon) | structure générale du graphe co-occurrence |
| **Watts & Strogatz 1998** | Nature 393:440 | `10.1038/30918` | Small-world networks (C élevé + L court) | `spread_activation` exploite cette topologie |
| **Latora & Marchiori 2001** | Phys Rev Lett 87:198701 | — | E_global efficiency | health metric implicite via `_graph_entropy` |
| **Tero et al. 2010** | Science 327:439 | `10.1126/science.1177894` | *Physarum polycephalum* (slime mold) — graphe optimisé self-organized | `decay` + reinforcement co-occurrence ressemble au pattern slime mold |
| **Newman 2003** | SIAM Review 45:167 | `10.1137/S003614450342480` | Network theory générale | base théorique de Newman-Girvan Q (forge --modularity) + `detect_zones` |
| **Humphries & Gurney 2008** | PLOS ONE 3:e0002051 | `10.1371/journal.pone.0002051` | Small-world σ quantification | propriété attendue du mycelium MUNINN (vérifiée par CROSSVAL) |
| **Towlson et al. 2013** | J Neurosci 33:6380 | `10.1523/JNEUROSCI.3784-12.2013` | C. elegans connectome — référence empirique réseau biologique | benchmark de comparaison pour `detect_zones` + `_graph_entropy` |
| **Freeman 1977** | Sociometry 40:35 | (fondamental) | Betweenness centrality | utilisé indirectement par `detect_blind_spots` (structural holes Burt 1992 = forme spécialisée de BC) |
| **Buhl et al. 2004** | J R Soc Interface 1:71 | `10.1098/rsif.2004.0009` | Ant trail networks (graphes auto-organisés) | parallèle conceptuel avec V7B ACO pheromone (Dorigo) — cf. boot scoring |
| **Haggett & Chorley 1969** | livre, Network Analysis in Geography | — | Formule α (meshedness) | propriété graphe MUNINN testable via le même α |

**À retenir** :
- Le mycelium MUNINN n'est pas une invention isolée — il s'inscrit dans
  une tradition mesurée de **40 ans** de papers réseau biologique
- 25/26 propriétés des papers ci-dessus sont **reproduites par les valeurs
  MUNINN** sur les graphes synthétiques + le vrai champignon Bebber 2007
- Le seul "FAIL" est mathématiquement attendu (pas un bug) : MUNINN utilise
  Erdős-Rényi pour le random baseline, Towlson utilise config model. Les 2
  formules donnent des C différents par design — MUNINN matche la valeur ER
  théorique (C ≈ p)
- Pour la doc complète des 26 tests + tableaux match-by-match → voir
  [`sky1241/tree/docs/CROSSVAL_REPORT.md`](https://github.com/sky1241/tree/blob/main/docs/CROSSVAL_REPORT.md)

**Action recommandée future** : si on veut rendre cette cross-validation
runnable depuis MUNINN- aussi (pas juste sky1241/tree), on pourrait porter
les 26 tests dans `tests/test_mycelium_crossval.py` qui appelle des fonctions
mycelium MUNINN-, calcule les métriques, et compare aux valeurs publiées.
Effort : ~1 jour (16h).

---

## 6. FORGE (forge-shield 1.1.x PyPI)

Forge est appelé via subprocess depuis `engine/core/forge_metrics.py`. PyPI binaire installé via `pip install forge-shield` (constraints.txt: `git+https://github.com/sky1241/forge.git@v1.1.1` en CI).

### Sous-commandes utilisées

| # | Commande | Paper / formule | Caller MUNINN | Status |
|---|---|---|---|---|
| 1 | `forge --gen-props <file>` | Hypothesis (Hughes 2000 QuickCheck) + BUG-102 destructive detector | CI smoke matrix 17 modules + RULE 5 CLAUDE.md | ✅ |
| 2 | `forge --locate` | Tarantula (Jones 2002) — Ochiai coefficient | `forge_metrics.py:262` (`_run_forge`) | ✅ |
| 3 | `forge --carmack --weeks 4` | Kalman + Wavelet + Kaplan-Meier + Newman-Girvan Q | `forge_metrics.py:261` | ✅ |
| 4 | `forge --modularity` | Newman-Girvan Q + Louvain (Blondel 2008) | `forge_metrics.py:263` + CHANGELOG (baseline 0.660) | ✅ |
| 5 | `forge --paths-to-mutate FILE` | libcst AST mutations | (cycle 5, design only) | 🔵 |
| 6 | `forge --fast-deep` | BFS transitive impact (Bazel/Buck-style) | (design only) | 🔵 |

### Helpers Python (`forge_metrics.py`)

| # | Fonction | Effet | Ligne |
|---|---|---|---|
| 7 | `_run_forge(args)` | subprocess wrapper, timeout 120s, graceful degrade | `:124` |
| 8 | `_parse_carmack` | regex extract (0..1 risk scores) | `:155` |
| 9 | `_parse_locate` | regex extract Ochiai scores | `:160` |
| 10 | `_parse_modularity_q` | regex extract global Q | `:171` |
| 11 | `_fuse(carmack, locate, modularity)` | `0.5×carmack + 0.4×locate + 0.1×coupling_penalty` | `:180` |
| 12 | `get_repo_risk(repo)` | public API, cache 24h `.muninn/forge_cache.json` | `:235` |
| 13 | `forge_score_for_path(repo, file)` | UI Qt couleur risque par fichier | (cube_live consumer) |
| 14 | `forge_color_for_path(repo, file, default)` | mapping score → hex couleur | (idem) |

### Intégration cube_analysis

| # | Fonction | Effet | Ligne |
|---|---|---|---|
| 15 | `fuse_risks()` | combine cube temperature (Hebbian decay) + forge risk | `cube_analysis.py:1544` |
| 16 | `_get_forge_risks()` | `from forge import predict_defects` parse output | `cube_analysis.py:1588` |

### Property tests générés (forge --gen-props sweep 2026-05-10)

**101 tests** sur 17 modules :

| Module | Props | Module | Props |
|---|---|---|---|
| budget_select | 6 | _hook_logger | 3 |
| cube | 11 | lang_lexicons | 2 |
| cube_analysis | 25 | lexicons | 1 |
| cube_providers | 7 | muninn_feed | 1 |
| dedup | 6 | muninn_layers | 6 |
| forge_metrics | 4 | muninn_tree | 14 |
| _secrets | 3 | mycelium_db | 2 |
| sentiment | 3 | sync_backend | 2 |
| tokenizer | 2 | (forge external) | 4 |

**13 modules sans props** (sub-modules + mixins + CLI + crypto interne) — justifiés.

---

## 7. ❌ MISSING / DRIFT (claims doc ≠ code)

| # | Claim | Source | Réalité |
|---|---|---|---|
| 1 | `forge --predict` (churn rank defect prediction) | `BATTLE_PLAN_PROD_FINAL_2026-05-09.md:9` | NOT CALLED in MUNINN code |
| 2 | `forge --anomaly` | `BATTLE_PLAN_PROD_FINAL_2026-05-09.md:10` | NOT CALLED |
| 3 | `forge --diff` (regression detection) | `BATTLEPLAN_SCANNER.md` | NOT CALLED |
| 4 | `forge --incremental-mutate` libcst AST-diff | `BATTLE_PLAN_AFTERNOON_2026-05-10.md` | OPT-IN future |
| 5 | "BARE Wave model" pour H1 trip | `mycelium_dream.py:trip` doc + IMMUNE_FORMULAS-style | Paper référence non vérifiable (probablement custom name pour le modèle d'exploration). Le vrai paper documenté est Carhart-Harris 2014 (psilocybine entropy). |
| 6 | "Cell Systems 2017" pour A2 non-Markov | `tree.py:470` doc | Référence vague, à préciser ou retirer |
| 7 | F6 forge_smoke matrix CI | `BATTLE_PLAN_AFTERNOON_2026-05-10.md` | ✅ 17/17 modules depuis commit `d464ce2` (était 11) |

**Action recommandée** : 
- Décision sur 1-4 : soit implémenter (si valeur), soit retirer des battle plans (drift doc)
- Décision sur 5-6 : préciser les references ou marquer "(custom)" dans le code

---

## 8. RÉCAP HIÉRARCHIQUE

```
COMPRESS pipeline (31 algos)
├── L0-L11 regex (8 actives)
├── L9 LLM compress (opt-in)
├── L10-L11 carmack-style (Bartlett 1932 + Kolmogorov 1965)
├── L12 BudgetMem (opt-in, BUG-104)
└── P10-P38 filtres transversaux (13 actifs)

BOOT pipeline (32 algos)
├── Pré-warm (A6 git diff + P23 auto-continue)
├── Expansion (P15 mycelium + P20b cross-repo)
├── Scoring (15 algos: TF-IDF, ACT-R, Spreading, V3A/B, B3/4/6, V11B, V7B, V5A, V1A, V5B, etc.)
├── Charge dedup (Bloom + C3 + P20c + P19 NCD)
├── Surface (P22 + P18 + H3 + V8B)
└── Filtre overflow (KIComp + A8 warning)

PRUNE pipeline (24 algos)
├── Backup (A7) + protection (V9B Reed-Solomon)
├── Suppression (I2 Perelson) + selection (I3 Forrest)
├── Classification (Ebbinghaus + I1 + V4B + V6B + A1 + R4 + B14)
├── L9 cold recompress (opt-in)
├── Consolidation (H10 + Sleep + X9 + Decay + H1 trip + H2 dream)
├── Regen facts (V9A+ Shomrat & Levin)
└── Housekeeping (P8 + B15)

FEED pipeline (6 algos)
├── A4 path validation
├── P38 format detect
├── I1 danger compute
├── P22 index update
├── P18 error extract
└── P16 session log

MYCELIUM (24 méthodes)
├── Core: decay + adaptive (A1/A2/A3) + vacuum (P3)
├── Activation: spread + transitive + adaptive_hops
├── Zones: spectral + Shannon entropy + BFS fallback
├── Dream: anomalies + blind spots + trip + dream
├── Meta: pull/push federation
└── DB: integrity + WAL

FORGE (16 entrées)
├── 4 sous-commandes ACTIVE (gen-props CI + locate + carmack + modularity)
├── 2 sous-commandes OPT-IN future (paths-to-mutate + fast-deep)
├── Helpers Python (forge_metrics.py 14 fonctions)
└── 101 property tests générés (17 modules)
```

---

## 9. TOTAUX OBJECTIFS

| Catégorie | Count | Source |
|---|---|---|
| Algorithmes wirés en prod | **117** | sum 31+32+24+6+24 (sans forge) |
| Sous-commandes forge ACTIVE | 4 | gen-props/locate/carmack/modularity |
| Papers cités explicitement | 22+ | Bartlett, Kolmogorov, Collins-Loftus, Wynne, Paz-y-Mino, Settles, Park, Anderson, Boyd-Richerson, Dorigo, Yekutieli, Seeley, Waters-Bassler, Yang, Greensmith, Perelson, Forrest, Reed-Solomon, Shomrat-Levin, Wilson-McNaughton, Carhart-Harris, Burt, Kirkpatrick, Talmi, Bollerslev, Rao-Ballard, Newman-Girvan, Blondel, Hughes, Jones |
| Papers cross-validés mycelium (CROSSVAL_REPORT) | 10 | Bebber, Watts-Strogatz, Latora-Marchiori, Tero, Newman, Humphries-Gurney, Towlson, Freeman, Buhl, Haggett-Chorley — voir §5.1 + `sky1241/tree/docs/CROSSVAL_REPORT.md` |
| Property tests générés | **101** | sweep 2026-05-10 sur 17 modules |
| MISSING (claim sans code) | 6 | listé section 7 |

**Q-modularity actuel** : 0.660 (post-P3 split, "good ≥ 0.30").

---

*Source : audit deep 5 agents en parallèle 2026-05-10 PM. Mise à jour à
chaque modification structurelle (split, ajout/retrait algo, change paper ref).*
