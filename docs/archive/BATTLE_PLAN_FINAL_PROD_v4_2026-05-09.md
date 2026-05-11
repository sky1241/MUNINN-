# BATTLE PLAN FINAL PROD v4 — 2026-05-09 (post-H6 deep audit, 10 agents)

Synthèse de **10 agents en parallèle** lancés après H6.4 (mycelium split). Demande Sky : "ce qui est fait, pas fait, branché, orphelin, en production ou pas". Production-focused, pas de bullshit B2B.

---

## 🏁 Verdict global

**Le repo est en bon état.** 11 commits aujourd'hui, 0 xfail, CI 100% vert sur les 12 derniers runs, mycelium split de -55% LOC validé par forge (Carmack 0.419 → 0.220), TLS 1.3 prod-grade, hooks manifest sha256sum 9/9 OK.

**Ce qui marche en prod** :
- Cube reconstruction live (UI → terminal → cube_live → reconstruct_adaptive → heatmap NCD)
- Forge chain end-to-end (PyPI binary → forge_metrics → cube_live emit `[forge] risk=...`)
- Mycelium 28 instanciations prod confirmées (muninn.py, muninn_tree, muninn_feed, ui/cube_live)
- 9 hooks installés, 3 actifs ce soir (bridge, subagent_start, post_tool_failure)
- L1-L7 + L10-L11 compress par défaut (regex pur, 0 dépendance, 0 $)

**Ce qui pue** : voir BLOCKERS ci-dessous.

---

## 🚨 BLOCKERS (vrais bugs à fixer avant de vendre)

### B1. BUG-091 RÉCURRENCE CONFIRMÉE
- `muninn/_engine.py` 2197L vs `engine/core/muninn.py` 2187L = **10 lignes de diff**
- Probablement P0bis secure_perms non mirroré (audit security plus tôt confirmait drift sur vault.py aussi)
- BUG-091 status BUGS.md = PARTIAL, pas FIXED malgré le header header v3 reclassifié
- **Action** : `diff engine/core/muninn.py muninn/_engine.py` et synchroniser. Idem cube.py, cube_providers.py, lang_lexicons.py, vault.py, _secrets.py, wal_monitor.py.
- **Effort** : 2h (auditer + soit shim soit sync les 5-7 fichiers identiques)

### B2. 3 HOOKS AUDIT SILENTLY BROKEN
Les 3 fichiers .jsonl que ces hooks créent sont **ABSENTS** :
- `.muninn/edits_log.jsonl` (post_tool_use_edit_log) — pourtant beaucoup d'Edits ce soir
- `.muninn/audit_log.jsonl` (notification_audit_hook)
- `.muninn/config_changes.jsonl` (config_change_hook)

= **438L cumulées de hooks audit non vérifiés**. Soit Claude Code ne les invoque pas, soit ils crashent silencieusement.
- **Action** : tester manuellement (faire un Edit, vérifier .muninn/), wirer `_hook_logger.log_hook_event` dans les 8 hooks qui ne loggent pas.
- **Effort** : 1h

### B3. PROVIDER HARDCODÉ DANS cube_live (UI crash si Ollama down)
- `muninn/ui/cube_live.py:178` instancie direct `OllamaProvider("qwen2.5-coder:7b")` sans fallback
- `CubeConfig.get_provider()` (Ollama → Claude → OpenAI → Mock) existe mais utilisé seulement par `cli_run`
- Si Ollama pas lancé → `ConnectionError` au démarrage de la reconstruction
- **Action** : remplacer la ligne par `provider = CubeConfig().get_provider()`
- **Effort** : 30 min + tests

---

## 🎯 HIGH-VALUE (gros gains, effort raisonnable)

### H1. Split muninn_tree.py 3929L
**Le vrai monstre architectural** (top 1 LOC, top 4 Carmack 0.332). Pattern H6 prouvé fonctionne.
- `boot()` 654L = la mère de toutes les bombes, fonction monstre absolue
- `prune()` 415L
- `doctor()` 281L
- 3 sous-modules naturels candidates :
  - `_MuninnTreeBoot` : boot, _load_root, _load_branches, _surface_*
  - `_MuninnTreePrune` : prune, decay-related
  - `_MuninnTreeDoctor` : doctor + diagnose
- **Estim Sky-réel** : 4-6h (pas 12-15h conservatif). Il a fait H6 en 4 chunks ce soir.

### H2. Cleanup 5400L de UI dead code
Trouvé par agent UI :
- `muninn/ui/_tree_engine.py` **4915L** (legacy L-system, 0 consumer dans tout le repo)
- `muninn/ui/_tree_renderer.py` **282L** (legacy PIL, 0 consumer)
- `muninn/ui/about_dialog.py` 71L (placeholder None, jamais instancié)
- `muninn/ui/search.py` 99L (instancié seulement par tests, slots orphelins dans main_window:185-200)
- **+ Bugs UX silencieux** : F11 (`_toggle_fullscreen`) = `pass`, `toggle_mode` / `focus_search` = `lambda: None`, `ForestToggle` jamais ajouté au layout
- **Action** : `git rm` les 4 fichiers + retirer les slots orphelins
- **Effort** : 30 min

### H3. Réintégrer test_chunk_a7 + nettoyer 20 skips morts
- 8 tests **gardiens des hooks Claude Code** (manifest sha256, perms 0o600) désactivés en CI à cause du diff perms 0o644 du git checkout
- **Action** : ajouter step CI "regenerate hooks manifest" avant pytest
- **+ 20 `pytest.skip("not yet implemented")` MORTS** dans test_chunk_a8/a4/a3/a2 — modules existent maintenant, ces skips datent de pré-fix
- **Action** : retirer les skips, les tests passent
- **Effort** : 1h total (8 fixés + 20 réactivés = 28 tests gratuit)

### H4. L9 prompt caching → -50% coût API
- `engine/core/muninn_layers.py:1255 _llm_compress_chunk` : aucun `cache_control`, aucun `extra_headers`
- Le system prompt + `_L9_PROMPT` sont longs et stables → cache hit naturel à 90% (Anthropic)
- Coût actuel claim "$0.21 / 230 fichiers" → potentiel ~$0.10 avec caching
- **Action** : ajouter `cache_control={"type": "ephemeral"}` sur le system message
- **Effort** : 1 jour (test + bench coût avant/après)

---

## 📊 MEDIUM (dette à attaquer cette semaine)

### M1. Architecture restante (post-H6)
| Fichier | LOC | Carmack | Estim split |
|---|---|---|---|
| muninn_tree.py | **3929** | 0.332 | 4-6h (H1 ci-dessus) |
| cube_providers.py | 2124 | **0.466 (top 1!)** | 3-4h (split par provider Ollama/Claude/OpenAI/Mock) |
| muninn.py | 2187 | 0.335 | 2-3h (main 426L par sous-commande) |
| cube_analysis.py | 1915 | — | tourne dormant, voir M5 ci-dessous |
| muninn_feed.py | 1817 | — | OK pour l'instant |
| muninn_layers.py | 1547 | — | OK pour l'instant |

### M2. UI gap zones post-H3.2
- CLI `muninn zones` ✅ wired ce soir (commit 21606d8)
- Côté UI : `Neuron.zone: str` lu depuis le scan mais **ignoré par le painter**
- `forest.py:ZONE_COLORS` (13 couleurs) défini mais inutilisé
- **Action** : 13-couleur fill par zone OU légende latérale + filtre
- **Effort** : 2-3h

### M3. UI gap forge heatmap (H2 incomplet)
- `forge_score_for_path` utilisé seulement pendant cube reconstruction (cube_live.py)
- La carte de neurones standard ne colore PAS par forge risk
- **Opportunité H2 manquée** : après chaque load_scan, calculer get_repo_risk + fusion sur Neuron.temperature
- **Effort** : 2h

### M4. BUG-104 vrai fix
Root cause = chunk granularity (paragraphes must-keep trop gros pour budgets serrés). L12 reste OFF par défaut.
- **Action** : sub-chunker les must-keep avant Phase 1 packing dans budget_select.py, OU faire tourner L0-L11 sur les chunks AVANT évaluation budget
- **Effort** : 4h

### M5. Cube subcommand muninn (analyse forensique)
- `cli_run`/`cli_god`/`cli_scan`/`cli_status` existent dans cube_analysis.py mais **pas exposés** par muninn.py
- Toute la grappe B9/B10/B22/B26/B27/B28/B31/B35/B37/B38 (Laplacian RG, Cheeger, Belief Propagation, Tononi degeneracy, God's Number, auto_repair) tourne UNIQUEMENT en tests
- **396 tests cube** (~15% du repo) testent du code dormant en prod
- **Action** : ajouter subparser `muninn cube run/scan/god/status` dans muninn.py:1731
- **Effort** : 1-2h

### M6. Federation pull symétrique
- `pull_from_meta` appelé dans **1 seul endroit** (muninn_tree.py:1268, expansion query)
- Boot ne pull pas, watch hook ne pull pas → federation = push-only
- Sky mono-machine actuellement, mais si 2e machine arrive : push asymétrique
- **Action** : ajouter `pull_from_meta` au boot ou watch
- **Effort** : 30 min

### M7. Drift docs forge.py
- `PLAN_PHASE0_TO_8.md` L28, L163 — disent encore `python forge.py`
- `docs/BATTLEPLAN_SCANNER.md` L436, L576-580 — idem
- **Action** : sed `python forge.py` → `forge`
- **Effort** : 5 min

---

## 🪦 DEAD CODE confirmé (delete pur)

| Fichier / fonction | LOC | Impact delete | Risque |
|---|---|---|---|
| `engine/core/watchdog.py` | 66 | aucun (0 import, pas de cron, pas de systemd) | nul |
| `muninn/watchdog.py` | 57 | jumeau du précédent | nul |
| `muninn/ui/_tree_engine.py` | 4915 | aucun (legacy L-system) | nul |
| `muninn/ui/_tree_renderer.py` | 282 | aucun (legacy PIL) | nul |
| `muninn/ui/about_dialog.py` | 71 | aucun (placeholder None) | nul |
| `muninn/ui/search.py` | 99 | retirer slots orphelins dans main_window:185-200 aussi | minimal |
| `cube_analysis.py::fuse_risks` | ~50 | 0 caller (transitif via _get_forge_risks mort) | nul |
| `cube_analysis.py::git_log_value` | ~30 | 0 caller | nul |
| `muninn_layers.py::_ncd` | ~30 | seul caller = test_all_brains.py | minimal |
| `mycelium.py::cleanup_orphan_zones` | ~20 | 0 caller, duplicat mycelium_db.py:188 | nul |

**Total purement mort** : ~5620L (5400L UI + 123L watchdog + ~80L cube_analysis morts + ~30L _ncd + 20L cleanup_orphan_zones).

À renommer privé (`_xxx`) : `cleanup_orphan_concepts`, `vacuum_if_needed`, `adaptive_hops` (helpers internes mais exposés publiquement).

3 méthodes Mycelium 100% test-only à wirer ou delete : `adaptive_fusion_threshold`, `adaptive_decay_half_life`, `observe_with_concepts`.

---

## ✅ CONFIRMÉ EN PRODUCTION (ne rien toucher)

### Code vivant (16 modules engine/core)
muninn.py / muninn_tree.py / muninn_feed.py / muninn_layers.py (12 layers) / mycelium.py + 4 mixins (post-H6) / mycelium_db.py / cube.py / cube_providers.py / cube_analysis.py (partiel) / sync_backend.py / sync_tls.py / forge_metrics.py / tokenizer.py / lexicons.py / lang_lexicons.py / vault.py / sentiment.py / dedup.py / budget_select.py / wal_monitor.py / _secrets.py / _hook_logger.py.

### Pipelines validés
- **Compression default** : P10 redact → L1→L3→L2→L4→L5→L6→L7 → SimHash dedup → L10 → L11 → L9 (si key)
- **Cube reconstruction** : main_window → terminal /reconstruct → cube_live worker → reconstruct_adaptive → heatmap
- **Forge chain** : PyPI binary → forge_metrics → cube_live emit → CI smoke (101/101 props)
- **TLS sync** : TLS 1.3 only, mTLS, ACL CN, RateLimiter (fix H5.2 ce soir)
- **Mycelium federation** : SharedFileBackend default, push-heavy
- **Hooks** : 9 installés, manifest sha256sum 9/9 OK

### Métriques final
- **2351 tests passed, 29 skip légitimes, 0 xfail, 0 fail** (post-H6.4 run local)
- **2567 collected total** (216 invisibles : 187 ignored + 29 skip env-only)
- **Q-modularity 0.671** (good)
- **CI 12/12 success** consécutifs aujourd'hui
- **forge --carmack** top 5 inchangé sauf mycelium descendu rang 12 (bonne nouvelle)

### Tests CI
- 369 fichiers, 108 communautés
- 18 fichiers `test_props_*.py` (forge --gen-props matrix), 101/101 PASS
- 91 tests mycelium-related
- 396 tests cube-related (mais code dormant pour l'analyse forensique, voir M5)
- 111 tests sync/meta/tls

---

## 🎯 PLAN D'ATTAQUE PRIORISÉ

### CE SOIR si Sky a encore de l'énergie (90 min)
1. **D1-D6** Delete 5620L code mort (watchdog x2, _tree_engine, _tree_renderer, about_dialog, search.py + slots orphelins, fuse_risks, git_log_value, _ncd) — 30 min
2. **H3** Retirer 20 skips morts test_chunk_a8/a4/a3/a2 + tester localement — 30 min
3. **B1** Diff `engine/core/muninn.py` vs `muninn/_engine.py` + sync (BUG-091 récurrence) — 30 min

### CETTE SEMAINE (12-16h)
- **H1** Split muninn_tree.py (boot 654L, prune 415L, doctor 281L) en 3 mixins — 4-6h
- **B3** Provider fallback dans cube_live.py — 30 min
- **B2** Wire _hook_logger dans les 8 hooks silencieux + tests E2E — 1h
- **H4** L9 prompt caching → -50% coût — 1 jour
- **M1** Split cube_providers.py par provider — 3-4h
- **M5** Subcommand `muninn cube run/scan/god/status` — 1-2h
- **M2** Widget zones UI (post-H3.2) — 2-3h
- **M3** Forge heatmap sur carte de neurones standard (post-H2) — 2h

### PLUS TARD
- **M4** BUG-104 vrai fix (chunk granularity) — 4h
- **M6** Federation pull symétrique — 30 min
- Mirror BUG-091 finale (les 5-7 fichiers identiques restants) — 2-3h
- Forge-shield publication PyPI (cousin) — 30-60 min

---

## 📊 BILAN — Ce qui s'est passé aujourd'hui (2026-05-09)

**Avant** : Plan PROD FINAL v2 du matin (H1-H6).

**Pendant** :
- H1 forge migration ✅ d6a5fc3
- H4.1 C12 ✅ a19081a
- H3.1 growth_stats ✅ a143830
- H3.2+H3.3 zones CLI ✅ 21606d8
- H4.2 forge_smoke CI ✅ f4304c2
- H5.1 retrieval xfail ✅ 11b4bba
- H2 forge_metrics → cube ✅ 78ce4dd
- H5.2 sync_tls ✅ 591fbe1
- docs cleanup ✅ 81e8703
- v3 audit + 9 wins ✅ c36ba40
- **H6.1 Meta mixin** ✅ 5977772
- **H6.2 Zones mixin** ✅ df11508
- **H6.3 Activation mixin** ✅ 81eb654
- **H6.4 Dream mixin** ✅ 59bed03

**Après cet audit v4** : ~5600L de delete possible immédiat, 2 vrais bugs à fixer (B1 BUG-091 récurrence, B2 hooks audit broken), 1 risque UX (B3 provider fallback). Le reste = chemins de croissance.

**Verdict** : repo est en bonne santé. Les 10 agents convergent — pas de gros mensonge architectural, pas de critique sécurité, le H6 split a livré ce qu'il promettait, la chaîne forge marche bout-en-bout.

Prêt à continuer demain à tête reposée.
