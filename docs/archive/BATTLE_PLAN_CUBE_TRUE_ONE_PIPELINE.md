# BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE

> **Date rédaction** : 2026-05-19
> **Status** : draft, en attente validation Sky avant tout code
> **Objectif** : wirer la détection du trou + ancres SHA dans `muninn-mem cube run`
> SANS casser les 2339 tests existants
> **Méthodologie** : 4 rounds d'audit (22 agents), output code copy-paste obligatoire
> **Workflow par chunk** : READ → TEST PIN → RED → FIX → GREEN → WIRE → END-TO-END → CLEAN → FORGE → COMMIT (1 commit atomique par chunk, push final unique)

---

## 0. TL;DR

`muninn-mem cube run` prend **6h pour 1000 lignes** alors que théoriquement 2-3 chunks modifiés devraient suffire. 4 causes vérifiées :

1. **`compute_delta()` jamais appelée** par cli_run (3/3 agents) — reconstruit TOUS les cubes même inchangés
2. **`healed` set vide à chaque run** (3/3 agents) — repart de zéro à chaque invocation
3. **BUG WAGON SHA-256** (vérifié output) — `cube.sha256` jamais updated après reconstruction → cycle 2+ jamais exact_match
4. **`record_cycle` non-batch** (vérifié output) — ~24s gaspillés par run de 1000 cubes

**Fix : 4 patches, ~46 lignes, gain estimé x50-x500.**

---

## 1. État vérifié du code (output direct, pas paraphrase)

### 1.1 Ce qui MARCHE (3/3 agents convergent)

| # | Fonction | File:Line |
|---|---|---|
| 1 | SHA-256 calcul/validation (B17) | [cube_providers.py:975-976](../engine/core/cube_providers.py#L975-L976) |
| 2 | AST hints extraction | [cube_analysis.py:1113](../engine/core/cube_analysis.py#L1113) |
| 3 | Fix 20 anchors skip LLM si 100% | [cube_providers.py:855-861](../engine/core/cube_providers.py#L855-L861) |
| 4 | `compute_delta()` existe en cache.py (mais non branchée run) | [scanner/cache.py:88](../engine/core/scanner/cache.py#L88) |
| 5 | Healed set intra-cycle | [cube_analysis.py:105-107](../engine/core/cube_analysis.py#L105-L107) |
| 6 | Wagon effect `cube.content = reconstruction` | [cube_analysis.py:148](../engine/core/cube_analysis.py#L148) |
| 7 | Hebbian update post-cycle (B30) | [cube_analysis.py:164](../engine/core/cube_analysis.py#L164) |
| 8 | Mycelium semantic neighbors cycle 2+ | [cube_analysis.py:119-121](../engine/core/cube_analysis.py#L119-L121) |
| 9 | Convergence check break | [cube_analysis.py:1132-1134](../engine/core/cube_analysis.py#L1132-L1134) |
| 10 | record_cycle persistence | [cube.py:1005-1015](../engine/core/cube.py#L1005-L1015) |

### 1.2 Ce qui NE MARCHE PAS (3/3 agents convergent)

| # | Promesse non tenue | File:Line | Preuve |
|---|---|---|---|
| 1 | `compute_delta()` JAMAIS appelée par `cli_run` | [cube_analysis.py:1107](../engine/core/cube_analysis.py#L1107) | grep `compute_delta` → 0 hits dans cube_analysis.py |
| 2 | `healed = set()` recréé vierge à chaque run | [cube_analysis.py:1116](../engine/core/cube_analysis.py#L1116) | pas d'init depuis DB, pas de `get_successful_cubes()` |
| 3 | `get_cubes_by_level()` retourne TOUS cubes (pas de filtre delta) | [cube.py:936](../engine/core/cube.py#L936) | code copy-paste vérifié |
| 4 | Aucune fonction `filter_unchanged_cubes()` | grep absent | 0 hit dans engine/core/ |

### 1.3 Bugs spécifiques vérifiés output

#### 🔴 BUG WAGON SHA-256 (1 ligne, ROI énorme)

**Preuve :** `grep -rn "cube\.sha256\s*=" engine/core/` → **ZÉRO HIT** après l'initialisation à [cube_analysis.py:609](../engine/core/cube_analysis.py#L609).

Code coupable [cube_analysis.py:145-149](../engine/core/cube_analysis.py#L145-L149) :
```python
145    # Wagon effect: successful reconstruction replaces original
146    if result.success:
147        healed.add(cube.id)
148        cube.content = result.reconstruction   # ← NEW content
149        store.save_cube(cube)                  # ← persisté avec OLD sha
```

`save_cube` persiste `(cube.id, cube.sha256_OLD, cube.content_NEW, ...)`. **DB stocke incohérence**.

**Trace cycle 2** : `recon_sha256 = hash(NEW)` comparé à `cube.sha256 = OLD` → `exact_match` toujours False → cube re-traité à chaque cycle.

#### 🟠 Batch record_cycle (vérifié output)

Code [cube.py:1005-1015](../engine/core/cube.py#L1005-L1015) :
```python
def record_cycle(self, cube_id, cycle_num, success, ...):
    with self._lock:
        self.conn.execute("INSERT INTO cycles ...", (...))
        self.conn.commit()   # ← commit après CHAQUE ligne
```

vs `save_cubes` [cube.py:894-905](../engine/core/cube.py#L894-L905) qui utilise `executemany` (le pattern batch existe déjà).

Overhead : ~2.5ms par execute+commit × 1000 cubes × 10 cycles = **~25s gaspillés** par run.

### 1.4 Bullshit débunké (FAUX, mea culpa)

- ❌ **O(N²) `update_all_temperatures`** : code vérifié, c'est O(N) avec index `idx_cycles_cube`. 5000 cubes ≈ 5s, négligeable.
- ❌ **AST hints timing** : `prepare_cubes` et `survey_propagation_filter` n'utilisent PAS `ast_hints`. Réorganiser = zéro gain.

---

## 2. Plan exécutable — 4 chunks vérifiés

### Chunk 1 — Fix BUG WAGON SHA-256

**Sévérité** : 🔴 Haute
**LOC** : 1 ligne ajoutée
**Gain** : x2-x5 sur cycles 2+ (cubes healed via NCD deviennent à nouveau exact_match)
**Risk** : Bas

#### Workflow

1. **READ** [cube_analysis.py:140-165](../engine/core/cube_analysis.py#L140-L165)
2. **TEST PIN** : `tests/test_wagon_sha_updated.py` (NEW)
   - Fonction : `test_cube_sha256_updated_after_reconstruction`
   - **RED state** : crée cube avec sha=ABC, reconstruct via mock LLM qui retourne contenu NEW, assert `cube.sha256 == hash(NEW)` → FAIL (sha reste ABC)
   - **GREEN state** : après fix, assert passe
3. **RED** : `pytest tests/test_wagon_sha_updated.py -v` → 1 failed
4. **FIX** [cube_analysis.py:148-149](../engine/core/cube_analysis.py#L148-L149) :
   ```python
   if result.success:
       healed.add(cube.id)
       cube.content = result.reconstruction
       cube.sha256 = sha256_hash(result.reconstruction)   # ← LIGNE À AJOUTER
       store.save_cube(cube)
   ```
5. **GREEN** : `pytest tests/test_wagon_sha_updated.py -v` → 1 passed
6. **END-TO-END** : `pytest tests/test_cube_b16_b19.py tests/test_cube_wiring.py -q`
   - Expected : tous PASS (le fix ne casse rien)
7. **FORGE** : `forge --gen-props engine/core/cube_analysis.py` + `pytest tests/test_props_cube_analysis.py -q`
8. **COMMIT** : `fix(cube): wagon SHA-256 jamais updaté après reconstruction`

### Chunk 2 — Batch record_cycle

**Sévérité** : 🟠 Moyenne
**LOC** : ~15 lignes
**Gain** : x250 sur hot path (~24s économisés par run de 1000 cubes)
**Risk** : Moyen (touche cube.py + cube_analysis.py)

#### Workflow

1. **READ** [cube.py:1000-1030](../engine/core/cube.py#L1000-L1030) + [cube_analysis.py:130-160](../engine/core/cube_analysis.py#L130-L160)
2. **TEST PIN** : `tests/test_record_cycles_batch.py`
   - Fonction : `test_record_cycles_batch_uses_executemany`
   - **RED state** : grep `executemany` dans cube.py → vérifie qu'il existe sur cycles (FAIL aujourd'hui, n'existe que sur cubes)
   - **GREEN state** : après fix, executemany existe + record_cycles batch insère N rows en 1 transaction
3. **FIX cube.py** : créer nouvelle méthode `record_cycles(batch_data)` qui fait `executemany`
4. **FIX cube_analysis.py:130-160** : accumuler results dans liste, appeler `store.record_cycles(batch)` une seule fois après la boucle
5. **GREEN** : `pytest tests/test_record_cycles_batch.py -v`
6. **END-TO-END** : `pytest tests/test_cube_b16_b19.py tests/test_cube_b32_b39.py tests/test_cube_wiring.py -q`
7. **FORGE** : `forge --gen-props engine/core/cube.py engine/core/cube_analysis.py`
8. **COMMIT** : `perf(cube): batch record_cycle via executemany (~25s gain par run)`

### Chunk 3 — Wire compute_delta dans cli_run

**Sévérité** : 🔴 Haute
**LOC** : ~10 lignes wire + adaptation 6 sites rebuild-full
**Gain** : x10-x100 (skip files inchangés)
**Risk** : Moyen (adaptation 6 sites + colonne `cycles.skipped`)

#### Pré-requis : adaptation des 6 sites "rebuild-full"

Le skip naïf casse 6 sites identifiés round audit :

| Site | File:Line | Adaptation |
|---|---|---|
| S1 | [cube_analysis.py:148](../engine/core/cube_analysis.py#L148) `cube.content = ...` | Skip le bloc si `result.skip_reconstruction=True` |
| S2 | [cube_analysis.py:149](../engine/core/cube_analysis.py#L149) `store.save_cube(cube)` | Skip (rien à sauver) |
| S3 | [cube_analysis.py:156](../engine/core/cube_analysis.py#L156) `update_temperature` | Toujours exécuter, applique cooling -0.15 (récompense stabilité) |
| S4 | [cube_analysis.py:1132-1134](../engine/core/cube_analysis.py#L1132-L1134) convergence | `done = healed \| skipped`, break si `len(done) == len(active_cubes)` |
| S5+S6 | [cube_analysis.py:1155](../engine/core/cube_analysis.py#L1155), [cube.py:1017](../engine/core/cube.py#L1017) | Record cycle avec `success=NULL` + `skip_reason='sha_stable'`. KM treat `success=None` comme censored (no event) |

#### Migration SQL

```sql
ALTER TABLE cycles ADD COLUMN skip_reason TEXT DEFAULT NULL;
```

Backward-compat : default NULL, anciennes queries fonctionnent.

#### Workflow

1. **READ** [cube_analysis.py:1105-1130](../engine/core/cube_analysis.py#L1105-L1130) + [scanner/cache.py:88](../engine/core/scanner/cache.py#L88)
2. **TEST PIN** : `tests/test_cli_run_delta_skip.py`
   - Fonction : `test_cli_run_skips_unchanged_files_via_delta`
   - **RED state** : run 1 = reconstruit 3 cubes, run 2 sans modif disque = expect 0 LLM calls, actually 3 calls → FAIL
   - **GREEN state** : run 2 = 0 LLM calls, 3 cubes skipped (cycles.skip_reason='sha_stable')
3. **FIX cube_analysis.py:1107-1110** : appeler `compute_delta(disk_hashes, scan_cache_path)` avant `prepare_cubes`, filtrer `cubes` où `c.file_origin in delta.to_scan`. Pour les cubes filtrés OUT, marquer `result.skip_reconstruction=True` et enregistrer `record_cycle(success=None, skip_reason='sha_stable')`
4. **FIX 6 sites rebuild-full** selon tableau ci-dessus
5. **GREEN** : `pytest tests/test_cli_run_delta_skip.py -v`
6. **END-TO-END** : `pytest tests/ -q --tb=line` → baseline maintenue
7. **FORGE** : `forge --gen-props engine/core/cube_analysis.py`
8. **COMMIT** : `feat(cube): wire compute_delta + skip SHA-stable cubes (gain x10-x100)`

### Chunk 4 — Healed persistent cross-run

**Sévérité** : 🟠 Moyenne
**LOC** : ~15 lignes
**Gain** : x3-x5 (skip cubes 100% success rate cross-run)
**Risk** : Bas (dépend de Chunk 3 pour skip_reason colonne)

#### Workflow

1. **READ** [cube_analysis.py:1116](../engine/core/cube_analysis.py#L1116) + [cube.py:1017-1026 get_cycles](../engine/core/cube.py#L1017-L1026)
2. **TEST PIN** : `tests/test_healed_persistent.py`
   - Fonction : `test_healed_loaded_from_db_skips_cubes_with_full_success`
   - **RED state** : run 1 healed 3 cubes, run 2 expects healed pre-populated with these 3 IDs → FAIL (vide)
   - **GREEN state** : run 2, healed initialisé avec cubes 100% success → 0 retraitement
3. **FIX cube.py** : ajouter `CubeStore.get_healed_cubes(min_success_count=3, min_success_rate=1.0) -> set[str]`
   - Query : `SELECT cube_id FROM cycles GROUP BY cube_id HAVING COUNT(*) >= ? AND MAX(success)=1 AND MIN(success)=1`
4. **FIX cube_analysis.py:1116** : `healed = store.get_healed_cubes()`
5. **GREEN** : `pytest tests/test_healed_persistent.py -v`
6. **END-TO-END** : `pytest tests/test_cube_*.py -q`
7. **FORGE** : `forge --gen-props engine/core/cube.py`
8. **COMMIT** : `feat(cube): healed set persistant cross-run depuis DB`

---

## 3. No-touch zones (ce qui DOIT rester intact)

### 3.1 Tests critiques (15)

| Test | File | Casse si on touche |
|---|---|---|
| test_mini_pipeline | tests/test_cube_wiring.py:348 | Signature cli_run, JSON output |
| test_cli_run_with_mock | tests/test_cube_b32_b39.py:168 | Format JSON output |
| test_b26_gods_number | tests/test_cube_wiring.py:257 | Calcul God's Number |
| test_b23_temperature_updated | tests/test_cube_wiring.py:190 | update_all_temperatures |
| test_b24_km_survival_set | tests/test_cube_wiring.py:176 | Kaplan-Meier |
| test_b22_degeneracy_set_on_failed | tests/test_cube_wiring.py:183 | Tononi degeneracy |
| test_b30_hebbian_runs | tests/test_cube_wiring.py:197 | hebbian_update |
| test_cli_scan | tests/test_cube_b32_b39.py:142 | subdivide_file, save_cubes |
| test_full_pipeline | tests/test_cube_b32_b39.py:197 | E2E scan+run+god |
| test_cycle_records_history | tests/test_cube_wiring.py:211 | Schema DB cycles (! adapter pour skip_reason) |
| test_returns_dict | tests/test_cube_wiring.py:216 | post_cycle_analysis keys |
| test_props_cube_analysis | tests/test_props_cube_analysis.py | Property invariants |
| test_props_cube_providers | tests/test_props_cube_providers.py | FIM invariants |
| test_h0_no_orphan_engine_module | tests/test_h0_no_orphan.py:96 | Import discipline |
| test_scan_b12 (compute_delta tests) | tests/scanner/test_scan_b12.py | DeltaResult format |

### 3.2 Contrats publics

- **Signature `cli_run(repo_path, cycles, level, config)` → dict** : ne PAS changer paramètres ni retour
- **Clés JSON output** : `cycles`, `cubes_total`, `cubes_active`, `successes`, `failures`, `success_rate`, `analysis`, `kaplan_meier`, `tononi_degeneracy`, `quarantine_enabled`
- **`CubeStore` méthodes publiques** : `save_cube`, `save_cubes`, `get_cubes_by_level`, `get_neighbors`, `record_cycle`, `update_temperature`, `update_score`, `get_cycles`

### 3.3 Test H.0 critical

[tests/test_h0_no_orphan.py:96](../tests/test_h0_no_orphan.py#L96) — tout fichier `engine/core/*.py` DOIT être importé par du code shipped. Si Chunk 3 crée un nouveau module, l'importer dans `cube_analysis.py` ou `muninn.py` AVANT commit.

---

## 4. Migration SQL safe (pattern mycelium_db.py)

Pour Chunk 3 (skip_reason) :

1. **Pattern** : `PRAGMA user_version` + `_migrate_schema()` idempotent
2. **Backup** obligatoire : `cp .muninn/cube.db .muninn/cube.db.pre-v2-backup`
3. **Migration step** :
   ```sql
   ALTER TABLE cycles ADD COLUMN skip_reason TEXT DEFAULT NULL;
   PRAGMA user_version = 2;
   ```
4. **Backward-compat** : `success` reste INTEGER NOT NULL si on garde 0/1 ; sinon évoluer en `INTEGER` (NULL pour skip) + `success` reste = passe à `INTEGER` (compat sqlite : changement type non-strict)
5. **`PRAGMA integrity_check`** avant migration

---

## 5. Risques + mitigations

| Risque | Mitigation | Sévérité |
|---|---|---|
| Skip naïf casse 6 sites rebuild-full | Colonne `cycles.skip_reason` + adapter convergence (Chunk 3) | 🔴 Critique |
| Corruption cube.db pendant migration | Backup avant + integrity_check + idempotent | 🔴 Critique |
| Test H.0 fail si nouveau module orphelin | Import avant commit | 🟠 Haut |
| KM sparse data après skip | Treat `success=None` comme censored (no event) | 🟡 Moyen |
| Régression sur tests existants | Run full suite après Chunk 3 (point de non-retour) | 🟡 Moyen |

---

## 6. Checkpoints CI

| Après chunk | Commande | Output attendu |
|---|---|---|
| 1 | `pytest tests/test_cube_b16_b19.py tests/test_props_cube_analysis.py -q` | All passed |
| 2 | `pytest tests/test_cube_wiring.py tests/test_cube_b32_b39.py -q` | All passed |
| 3 | `pytest tests/ -q --tb=line` | ~2339 PASS (baseline) — **point de non-retour** |
| 4 | `pytest tests/ -q --tb=short -x` | Full suite, fail fast |

**Pas de push intermédiaire**. Push final unique après Chunk 4 vert.

---

## 7. Estimation

| Chunk | Coding | Tests | CI | Total |
|---|---|---|---|---|
| 1 BUG WAGON SHA-256 | 5min | 10min | 5min | **20min** |
| 2 Batch record_cycle | 30min | 20min | 10min | **1h** |
| 3 Wire compute_delta + 6 sites | 90min | 30min | 30min | **2h30** |
| 4 Healed persistent | 30min | 15min | 15min | **1h** |
| **Total** | | | | **~5h** |

---

## 8. Problème orthogonal — Mode collapse LLM

**Pas dans le scope de ce battle plan** mais observé en parallèle :

`qwen2.5-coder:1.5b` boucle sur certains tokens (`unconstrained`, `returning`...) = **mode collapse classique**. Documenté dans [STATUS_2026-05-18_RECO_GEOMETRY.md:78](STATUS_2026-05-18_RECO_GEOMETRY.md#L78).

**Solutions** (à traiter séparément) :

| Solution | Effort | Gain |
|---|---|---|
| Ajouter `repetition_penalty=1.15` dans appel Ollama | 1 ligne config | Stoppe boucles |
| Temperature > 0 (0.2-0.4) | 1 ligne | Casse déterminisme |
| Upgrade qwen2.5-coder:7b | ollama pull | x10 qualité, x4 RAM |
| qwen2.5-coder:14b | ollama pull ~9GB | qualité prod, lent |

**Indépendant des 4 chunks ci-dessus.** Le pipeline fonctionne logiquement, c'est le LLM qui produit de la merde.

---

## 9. Phase 2 (optionnel, après cette première vague)

Si Phase 1 (les 4 chunks) passe verte :

| # | Chunk | Effort | Gain attendu |
|---|---|---|---|
| 5 | Mycelium seed cold start (K.1 lexicon ~946 mots dev-vocab) | ~80 LOC | Qualité reconstructions premier run |
| 6 | QCM Registry 14 stratégies (cube_strategies.py NEW) | ~180 LOC | Observabilité méthodes + sémantique "GN > 14 = obsolète" |
| 7 | Forge wire pré-cycle (`get_repo_risk()` priority boost) | ~10 LOC | Cible zones suspectes en premier |
| 8 | UX progress (--verbose flag, tqdm fallback) | ~30 LOC | Sky voit ce qui se passe pendant 6h |
| 9 | LLM repetition_penalty config | 1 ligne | Stoppe mode collapse |
| 10 | Tests e2e (SHA stable, gap partial, unrepairable) | ~250 LOC | Régression check |

Décisions par Sky avant attaque Phase 2.

---

## 10. Convergence audits — méthodologie de vérification

Ce plan tient sur 4 rounds d'audit (22 agents) :

| Round | Agents | Mission | Convergence |
|---|---|---|---|
| 1 | 10 | Audit large pipeline (briques, hooks, contrats) | Identifie 8 bugs câblage |
| 2 | 5 | Plans détaillés (gaps, mycelium seed, QCM, tests, UX) | Esquisse code agents |
| 3 | 4 | Vérification claims non-convergents (BUG WAGON, O(N²), batch, double FIM) | Confirme 2 VRAIS, 2 FAUX |
| 4 | 3 | Audit identique en parallèle (test convergence) | 3/3 sur compute_delta, healed, get_cubes_by_level |

**Règle anti-bullshit appliquée** ([ANTI_BULLSHIT_BATTLE_PLAN.md](ANTI_BULLSHIT_BATTLE_PLAN.md)) :
- Chaque claim = file:line + code copy-paste verbatim
- Aucune paraphrase optimiste
- Bullshit identifié explicitement (O(N²) temperature, AST timing)

---

## 11. Mes erreurs reconnues (session 2026-05-14/15)

Pour traçabilité :

1. **J'ai loupé le BUG WAGON SHA-256** pendant 4+ rounds d'audit malgré avoir lu le code → trouvé par 1 agent vérification
2. **J'ai relayé le claim O(N²) temperature** sans vérifier → bullshit confirmé
3. **J'ai inflaté le plan à 204 lignes / 10 chunks** alors que **46 lignes / 4 fixes suffisent**
4. **Mon "Plan A détection trou" (~120 lignes nouveau fichier)** était inutilement complexe
5. **J'ai trop fait confiance aux docs** (BATTLEPLAN_SCANNER promettait "delta x100" → code n'en faisait rien)

---

## 12. Décisions Sky requises avant code

1. **Validation du plan** : OK pour les 4 chunks dans cet ordre ? Ou réordonner ?
2. **Mode collapse LLM** : on traite en parallèle de Phase 1, ou on attend Phase 2 ?
3. **Backup cube.db** : OK pour Chunk 3 migration ? Où stocker le backup ?
4. **Push intermédiaire** : strictement final unique, ou OK après chaque chunk vert ?
5. **Phase 2** : décision après Phase 1, ou pré-validation maintenant ?

---

## 13. Sources

- Round 1 audit (10 agents, 2026-05-14) : no-touch zones, points d'insertion, SQL safe, battle plan ordonné
- Round 2 audit (5 agents, 2026-05-14) : gaps, mycelium seed, QCM, tests, UX
- Round 3 vérification (4 agents, 2026-05-14) : BUG WAGON confirmé, O(N²) débunké, batch confirmé, AST débunké
- Round 4 convergence (3 agents, 2026-05-15) : 3/3 sur compute_delta, healed, get_cubes_by_level
- [docs/ANTI_BULLSHIT_BATTLE_PLAN.md](ANTI_BULLSHIT_BATTLE_PLAN.md) — discipline preuve
- [docs/STATUS_2026-05-18_RECO_GEOMETRY.md](STATUS_2026-05-18_RECO_GEOMETRY.md) — mode collapse documenté
- [CLAUDE.md](../CLAUDE.md) — RULES 1-5, état projet 2339 PASS

---

Co-Authored-By: Claude Opus 4.7 (1M context)
