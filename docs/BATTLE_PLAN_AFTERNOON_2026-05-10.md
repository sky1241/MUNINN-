# BATTLE PLAN — 2026-05-10 (après-midi, post-P3 split + forge sweep)

État de départ : **HEAD = abf4887, CI vert**. P1+P2+P3 livrés ce matin (6 commits + 1 CI fix). 2332 PASS, 47 skip, 0 fail. Forge `--gen-props` lancé sur les 30 modules engine/core, 101 property tests passent (17 modules avec props, 13 sub-modules sans fonction publique fuzzable — attendu).

---

## 📊 État objectif post-P3 (mesuré, pas claim)

| Métrique | Valeur réelle | Source |
|---|---|---|
| Tests pytest | **2332 passed, 47 skipped, 0 fail** | run local 11h05 |
| Property tests | **101 passed in 27.68s** | run local 11h07 |
| Q-modularity | **0.660** (good ≥ 0.30) | `forge --modularity` |
| Top risk Carmack | cube_providers (0.516), muninn (0.337), muninn_tree (0.328), cube (0.276) | `forge --carmack --weeks 4` |
| Engine total | **24 731 lignes** sur 26 fichiers core | `wc -l engine/core/*.py` |
| muninn_tree.py | 3929 → **2179L** (-45%) | post-P3 |
| CI HEAD | abf4887 vert sur 2 jobs (Validate 36m47s + forge_smoke 38s) | gh run view |

---

## 🔬 Inventaire forge gen-props (sweep complet 11h)

### 17 modules AVEC test_props_*.py (101 tests générés)

| Module | Props | LOC | Notes |
|---|---|---|---|
| budget_select | 6 | 413 | OK |
| cube | 11 | 1558 | top risk #6 |
| cube_analysis | 25 | 1915 | + 1 deadline=None manuel (révert si forge l'écrase) |
| cube_providers | 7 | 2124 | top risk #2 + 1 deadline=None manuel |
| dedup | 6 | 244 | OK |
| forge_metrics | 4 | 344 | + 3 deadline=None manuels (subprocess shell-out) |
| _hook_logger | 3 | ~250 | OK |
| lang_lexicons | 2 | 1007 | OK |
| lexicons | 1 | 285 | minimal API |
| muninn_feed | 1 | 1817 | **sous-testé** (juste 1 prop sur 1817L) |
| muninn_layers | 6 | 1547 | OK |
| muninn_tree | 14 | 2179 | OK post-P3 |
| mycelium_db | 2 | 1401 | **sous-testé** (juste 2 props sur 1401L) |
| _secrets | 3 | ~600 | OK |
| sentiment | 3 | ~300 | OK |
| sync_backend | 2 | 1149 | sous-testé |
| tokenizer | 2 | 48 | adequat |

### 13 modules SANS test_props_*.py (justifiés)

| Module | Raison | Status |
|---|---|---|
| muninn.py | CLI dispatcher 503L `main()` | engine_only — pas fuzzable |
| muninn_tree_boot.py | sub-module P3.3, 0 fonction publique | OK (engine_only) |
| muninn_tree_doctor.py | sub-module P3.1, doctor() zero-arg | OK (engine_only) |
| muninn_tree_prune.py | sub-module P3.2, fonctions destructive | OK (engine_only) |
| mycelium_activation.py | mixin H6.3 | OK (engine_only) |
| mycelium_dream.py | mixin H6.4 | OK (engine_only) |
| mycelium_meta.py | mixin H6.1 | OK (engine_only) |
| mycelium_zones.py | mixin H6.2 | OK (engine_only) |
| mycelium.py | "No testable functions" — Mycelium class via mixins | acceptable |
| sync_tls.py | "No testable functions" — TLS opt-in | acceptable |
| vault.py | crypto interne, fonctions destructive | acceptable |
| wal_monitor.py | helper interne mycelium_db | acceptable |
| watchdog.py | CLI script standalone | acceptable |

**Conclusion forge** : couverture saine. Les "sous-testés" (muninn_feed:1, mycelium_db:2) sont liés à `compress_transcript` et `MyceliumDB` qui sont state-heavy → fuzzable mais peu rentable en property test.

---

## 🎯 CHUNKS À EXÉCUTER (priorité, sévérité, effort)

### CHUNK F1 — `numpy` non pinné dans constraints.txt **(CRIT)**

**Symptôme** : `numpy` utilisé dans `cube_analysis.py`, `mycelium_zones.py`, `scanner/propagation.py`, `muninn/ui/`. Installé en CI sans version → builds non reproductibles.

**Fix** (5 min) :
- Ajouter `numpy==X.Y.Z` dans `constraints.txt` (utiliser version locale tested via `python -c 'import numpy; print(numpy.__version__)'`)
- Re-run pytest local pour confirmer 2332 PASS toujours
- Commit `ci(F1): pin numpy in constraints.txt`

**Tests touchés** : 0 (pure CI fix)

---

### CHUNK F2 — Doc drift CHANGELOG.md ligne 3 **(DRIFT)**

**Symptôme** : audit doc-drift montre claim 22 771L vs réel 24 731L. 4 fichiers mycelium_*.py sous-comptés (zones 339→383, activation 496→545, meta 393→428, dream 529→561).

**Fix** (10 min) :
- Recalculer `wc -l engine/core/*.py` pour chaque fichier listé
- Mettre à jour CHANGELOG.md ligne 3 avec les vraies tailles
- Commit `docs(F2): sync CHANGELOG ligne 3 avec wc -l réel post-P3`

**Tests touchés** : 0

---

### CHUNK F3 — Doc drift CLAUDE.md "État du projet" **(DRIFT)**

**Symptôme** : 
- Claim "24 434 lignes, 19 fichiers core" → réel 24 731L, 26 fichiers (+7 post-P3)
- Claim "Q-modularity: 0.673" → réel 0.660 post-P3

**Fix** (5 min) :
- Update CLAUDE.md section "État du projet (mai 2026, post-H1-H5.2)" → renommer "post-P3" + chiffres réels
- Commit `docs(F3): sync CLAUDE.md état projet post-P3`

**Tests touchés** : 0

---

### CHUNK F4 — Doc drift BATTLE_PLAN_TOMORROW_2026-05-10.md **(DRIFT)**

**Symptôme** : ligne 5 dit P3 "en cours d'inspection" alors que P3 est LIVRÉ + pushé. Table "VRAIMENT FAIT" n'inclut pas P3.

**Fix** (5 min) :
- Marquer P3 fait dans le wrap-up + ajouter ligne table
- Commit `docs(F4): sync BATTLE_PLAN — P3 done`

**Tests touchés** : 0

---

### CHUNK F5 — Wire `_hook_logger` dans les 8 hooks **(DETTE — P4 reportée)**

**Symptôme** : `engine/core/_hook_logger.py:125 def log_hook_event` existe + 5 property tests passent + module testé chunk a8. **Mais 0 caller dans `.claude/hooks/*.py`**. Audit log claim mais features pas wirées.

**Fix** (~2h, mais peut être chunk-é) :
- Lister les hooks réels (`.claude/hooks/*.py`) + scrub_hooks.py + bridge_hook.py
- Pour chaque hook, remplacer le pattern `try: ... except Exception: pass` (qui swallow silencieusement) par un appel à `log_hook_event`
- Tester chaque hook isolé avant de commit
- 1 commit par hook (granularité fine pour rollback)

**Tests touchés** : potentiellement test_chunk_a8_hook_logger.py + test_audit_bugs (à vérifier)

---

### CHUNK F6 — forge_smoke CI matrix incomplet **(DETTE)**

**Symptôme** : `.github/workflows/ci.yml` forge_smoke matrix teste 11 modules. Mais 6 modules ont test_props_*.py et NE sont PAS dans le matrix : budget_select, dedup, forge_metrics, lang_lexicons, lexicons, sentiment.

**Risque** : si forge change de format, ces 6 ne seront pas re-vérifiés en CI. Régressions possibles non détectées.

**Fix** (10 min) :
- Ajouter les 6 modules dans la matrix `module: [...]` du job `forge_smoke` dans ci.yml
- Push + attendre CI (35 min)
- Commit `ci(F6): add 6 missing modules to forge_smoke matrix`

**Tests touchés** : 0 local. Le job CI lui-même valide.

---

### CHUNK F7 — Tests fragiles : 18 source-grep dans 2 fichiers **(FRAGILITÉ)**

**Symptôme** : audit fragilité a trouvé 18 occurrences `chr(10).join(.*read_text` dans :
- `tests/test_decay_in_prune.py`
- `tests/test_huginn_h3.py`

J'avais patché ces 2 fichiers ce matin pour P3 (concat list +muninn_tree_boot.py +muninn_tree_prune.py). Vérifier si les 18 sont des occurrences post-mes-patches ou si j'en ai loupé.

**Fix** (15-30 min selon scope) :
- Re-grep `chr(10).join.*read_text` sur tests/ pour confirmer fichiers
- Si occurrences couvrent les 4 sous-modules nouveaux (boot/prune/doctor + mycelium mixins) → OK
- Sinon ajouter les fichiers manquants

**Tests touchés** : test_decay_in_prune + test_huginn_h3 (eux-mêmes)

---

### ~~CHUNK F8 — `_REPO_PATH` cleanup~~ → **VALIDÉ NON-ACTION (2026-05-10 PM)**

**Audit révisé** : `tests/conftest.py` L91-109 contient déjà une fixture autouse
`_repo_path_isolate` (ajoutée CHUNK B7 le 2026-05-08) qui snapshot
`muninn._REPO_PATH` + `TREE_DIR` + `TREE_META` au début de CHAQUE test et les
restore en `finally`. Donc même si un test crash sans cleanup explicite, la
fixture protège la session pytest.

Les 31 occurrences `muninn._REPO_PATH = Path(...)` flaggées par mon audit du
midi sont SAFE → pas d'action.

---

### ~~CHUNK F9 — `Path.home()` cleanup~~ → **VALIDÉ NON-ACTION (2026-05-10 PM)**

**Audit révisé** : sur 10 occurrences `Path.home()` dans tests/ :
- 9 sont READ-ONLY (assertions ou construction de path pour grep)
- 1 est explicitement monkeypatchée (test_phase1_sync.py:347)
- **0 écriture réelle vers `$HOME`** (ni `.write_text` ni `.mkdir` ni `.unlink`).

Pas de pollution possible du runner CI. Pas d'action.

---

### CHUNK F10 — Node 20 deprecation Actions **(LONG TERME)**

**Symptôme** : juin 2026, GitHub force Node 24. `actions/checkout@v4` + `actions/setup-python@v5` utilisent Node 20.

**Fix** (15 min) :
- Vérifier si `setup-python@v5.2+` ou `@v6` supporte Node 24
- Bumper si dispo
- Commit `ci(F10): bump actions to Node 24-compatible versions`

**Tests touchés** : 0, juste CI

---

## 🚦 ORDRE D'EXÉCUTION RECOMMANDÉ

**Phase 1 — Doc + CI cleanup (30 min total, 5 commits, 0 risque)**
1. F1 numpy pinned (5 min) — CRIT
2. F2 CHANGELOG sync (10 min)
3. F3 CLAUDE.md sync (5 min)
4. F4 BATTLE_PLAN_TOMORROW sync (5 min)
5. F6 forge_smoke matrix +6 modules (10 min)

→ commit groupé `chore(F1-F6): doc drift fix + numpy pin + forge_smoke complete`
→ push, attendre CI vert (~35 min)

**Phase 2 — Tests fragiles (1-2h, optionnel selon énergie Sky)**
6. F7 source-grep audit (15-30 min)
7. F8 _REPO_PATH cleanup (1h-2h, peut être fractionné)
8. F9 Path.home() cleanup (30 min)

**Phase 3 — Big chantier (~2h, à scheduler quand reposé)**
9. F5 wire _hook_logger dans 8 hooks (2h)

**Phase 4 — Long terme (à faire un autre jour)**
10. F10 Node 24 actions bump

---

## ⚠️ POINTS DE GARDE communs

- **Forge regen écrase les `deadline=None` manuels** (cube_analysis, cube_providers, forge_metrics). Si on régénère ces 3 fichiers, immédiatement `git diff` + restaurer les `@settings(deadline=None)`. Confirmé ce midi : 4 fails post-régen, fix = `git checkout` ces 3 fichiers.
- **Jamais de claim sans run de commande** (RULE 4 CLAUDE.md). Pour chaque commit : `pytest -q` + paste output dans message.
- **Mirror muninn/ shim après chaque modif `engine/core/*.py`** (RULE 1 + B1 protocole).

---

## 📋 ESTIMATION TOTALE

| Phase | Effort Sky-réel | Risque |
|---|---|---|
| Phase 1 (doc + CI) | 30 min + CI 35min | bas |
| Phase 2 (tests fragiles) | 1-2h | moyen |
| Phase 3 (_hook_logger) | 2h | moyen |
| Phase 4 (Node 24) | 15 min | bas (peut-être plus tard) |
| **Total atteignable aujourd'hui** | **~3h focused** | — |

---

## 🎯 CIBLE FIN DE JOURNÉE

- 5+ commits propres, CI vert sur HEAD
- 0 drift doc identifiable
- numpy pinné = builds reproductibles
- forge_smoke CI couvre 17/17 modules avec props
- BUG-104 reste OPEN (opt-in, pas urgent)
- Node 24 actions reportées à un autre jour (pas critique)
