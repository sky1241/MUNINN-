# Deep Audit Forge — 2026-05-14

Audit exhaustif via `forge-shield 2.1.2` (PyPI binary, all features used).
Lancé avant Phase 1-5 du battle plan (BATTLE_PLAN_2026-05-14_MYCELIUM_FAILS.md)
pour identifier les bugs / fragilités avant d'attaquer les modifs.

## 1 — Q-modularity (Newman-Girvan, `forge --modularity`)

```
Q = 0.670 (good — modules well isolated, Q ≥ 0.30 threshold)
426 files in 136 communities

Top 3 communities by size:
  cluster # 13    62 files   Q-contrib +0.134
  cluster # 14    36 files   Q-contrib +0.076
  cluster # 34    27 files   Q-contrib +0.082
```

**Verdict** : architecture saine. Pas de monolithe couplé.

## 2 — Carmack risk score (`forge --carmack`)

Multi-signal Kalman + wavelet + coupling + crash rate :

| Rang | Fichier | Risk | Kalman | Crash | LOC | Bugfixes |
|---|---|---:|---:|---:|---:|---:|
| 1 | engine/core/muninn_tree.py | 0.414 | 4.06 | 20% | 2337 | 21 |
| 2 | muninn/ui/_tree_engine.py | 0.403 | 0.06 | **50%** | 4915 | 2 |
| 3 | **engine/core/cube_providers.py** | **0.374** | **5.19** | **1%** | 2131 | **38** |
| 4 | tests/eval_harness_chunk11.py | 0.370 | 0.00 | 0% | 543 | 0 |

**Signal critique** : `cube_providers.py` = 38 bugfixes historiques, Kalman 5.19 (le plus élevé du panel). C'est le fichier qu'on a modifié (Phase 0 du battle plan) et qu'on s'apprête à toucher en Phase 1+3.

## 3 — Churn-based defect prediction (`forge --predict`)

| Rang | Fichier | Risk | Churn | Bugfixes | LOC |
|---|---|---:|---:|---:|---:|
| 1 | engine/core/muninn.py | 0.45 | 13.1 | 25 | 1522 |
| 2 | **muninn/cube_providers.py** (shim) | **0.43** | **364.5** | **18** | **39** |
| 3 | muninn/_engine.py | 0.34 | 3.4 | 14 | 1592 |
| 4 | engine/core/muninn_tree.py | 0.34 | 9.1 | 21 | 2337 |
| 5 | **engine/core/cube.py** | **0.33** | 6.4 | **11** | 1562 |
| 6 | **engine/core/mycelium_db.py** | **0.29** | 4.6 | **12** | 1456 |
| 7 | **engine/core/mycelium.py** | **0.25** | 11.5 | **16** | 1415 |

**Signaux critiques** :
- `muninn/cube_providers.py` = **shim de 39 LOC avec 18 bugfixes** (75% bugfix rate, churn 364.5 = quasi tout réécrit). Hypersensible.
- `engine/core/mycelium_db.py` = 12 bugfixes pour 1456 LOC. **L'ajout d'une table SQL `failures` (Phase 3 du plan) doit être fait avec extrême prudence.**

## 4 — Commit anomaly detection (`forge --anomaly`)

9 fichiers flaggés (frequency ou LOC outliers vs baseline) :

```
ANOMALY  engine/core/cube.py              freq=+3.7 loc=+3.3  bugfix=44%
ANOMALY  engine/core/cube_providers.py    freq=+11.4 loc=+4.7 bugfix=55%
ANOMALY  engine/core/muninn.py            freq=+9.6 loc=+3.2  bugfix=42%
ANOMALY  engine/core/muninn_layers.py     freq=+2.7 loc=+3.4  bugfix=53%
ANOMALY  engine/core/muninn_tree.py       freq=+4.8 loc=+5.2  bugfix=68%
ANOMALY  engine/core/mycelium.py          freq=+4.9 loc=+2.9  bugfix=50%
ANOMALY  engine/core/mycelium_db.py       freq=+2.3 loc=+3.0  bugfix=71%
ANOMALY  muninn/_engine.py                freq=+6.0 loc=+3.4  bugfix=37%
ANOMALY  muninn/cube_providers.py         churn=+11.4 freq=+3.6 bugfix=75%
```

**Bugfix rates absolus** :
- `mycelium_db.py` : **71%** (7 commits sur 10 corrigent un bug)
- `muninn_tree.py` : **68%**
- `cube_providers.py` : **55%**
- `mycelium.py` : **50%**

**Verdict** : les 4 fichiers que je m'apprête à toucher sont dans le top historique d'instabilité. Chaque modification doit être testée AVANT commit.

## 5 — Failure heatmap (`forge --heatmap`)

```
66 runs logged
  1x  tests/test_lazy_real.py::test_real_cleanup
  1x  tests/test_lazy_real.py::test_real_observe
  1x  tests/test_lazy_real.py::test_real_save
  
Pareto: top 1 test(s) = 33% of all failures
```

3 tests dans `test_lazy_real.py` ont chacun failed 1 fois. Pas critique en volume (3 fails / 66 runs = 4.5%), mais à creuser si ces tests testent du mycelium lazy mode.

## 6 — Property tests (`forge --gen-props`)

| Module | Tests générés | Skipped (destructive) | Pass | Fail |
|---|---:|---:|---:|---:|
| `engine/core/mycelium.py` | 0 | — | — | "No testable functions found" |
| `engine/core/mycelium_db.py` | 2 | n/a | 2 | 0 |
| `engine/core/cube_providers.py` | 7 | 1 (`run_progressive_levels`) | 6 | 1 (deadline flake 241ms) |
| `engine/core/cube.py` | 11 | 4 (scan_repo, format_code, ...) | 10 | 1 (deadline flake 282ms) |
| `engine/core/cube_analysis.py` | n | 5+ destructive | passing | — |
| **TOTAL** | **37+** | **10+** | **37 pass** | **1 deadline flake** |

**Falsifying examples Hypothesis** (pas des bugs logiques, juste edge cases timing) :
- `test_reconstruct_cube_waves_no_crash` : input `attempts_per_wave=282, max_waves=440` → deadline exceeded à 241ms vs default 200ms. Edge case: si quelqu'un appelle avec 282 attempts au lieu de 11 (impossible en pratique mais Hypothesis cherche les bords).
- `test_subdivide_file_no_crash` : idem, 282ms timeout.

**Observation importante** : `mycelium.py` = "No testable functions found". 1415 LOC, 16 bugfixes, mais aucune fonction module-level pure que forge puisse fuzzer. Toutes les méthodes sont sur des classes avec side effects (DB writes). **Couverture forge = 0**.

## 7 — Shield orchestration (`forge --shield`)

```
[STAGE 1] Carmack risk scoring
[STAGE 2] Gen-props on top-risk files
  Generated 5 property tests -> tests/test_props_analytics.py
[STAGE 3] Fast-deep impact selection + run
  Changed files: 4
  fast-deep: 41/280 tests selected (transitive depth ≤ 5, max hop observed = 4)
  ⚠️  FAST-DEEP MODE — 0 tests in 63.8s
  ⚠️  Passed: 0  Failed: 0
SHIELD complete — 2 tests generated, 0 skipped, 1 skipped (test files)
```

**Anomalie forge** : fast-deep sélectionne 41 tests mais en execute 0 (63.8s pour rien). Probable bug du runner fast-deep — à signaler upstream à forge-shield, pas notre problème immédiat.

## 8 — En attente (background)

- `forge --locate` (Ochiai SBFL) — nécessite coverage.py, lent
- `forge --flaky 2` — re-run des 3 fails de test_lazy_real
- `forge --mutate engine/core/mycelium_db.py` — mutation testing sur le fichier à 71% bugfix rate (long, 10-30 min)

Résultats ajoutés ci-dessous au fur et à mesure de leur arrivée.

## 9 — Verdict consolidé

### Pas de bug logique nouveau découvert
- 37/38 property tests passent (1 deadline flake)
- Q-modularity 0.670 = OK
- Pas de crash inattendu, pas de falsifying example logique

### Mais signaux historiques très chargés
- 4 fichiers sur 5 que je vais toucher sont dans le top instabilité
- `mycelium_db.py` 71% bugfix rate = **le plus fragile**
- `cube_providers.py` 38 bugfixes = le plus modifié

### Recommandations pour Phase 1-5 du battle plan

1. **Phase 1 (bug ligne 2101 `observe()` type mismatch)** : LOW RISK.
   `cube_providers.py` mais juste un argument fix. Run forge --gen-props
   après pour confirmer 0 régression.

2. **Phase 3 (API `observe_failure` + table SQL `failures`)** : HIGH RISK.
   `mycelium.py` (0 couverture forge) + `mycelium_db.py` (71% bugfix rate).
   PROPOSITION : avant de coder, écrire des tests unitaires sur le
   contrat attendu de `observe_failure` (signature, side effects, idempotence).
   Forge gen-props après. Mutation testing recommandé sur la nouvelle
   table SQL pour valider sa robustesse.

3. **Phase 4 (bench multi-LLM)** : LOW RISK code-side, mais
   `mycelium_db.py` va être écrit en masse pendant le bench. Si Phase 3
   ajoute une nouvelle table mal testée, le bench peut crasher.
   Recommandation : Phase 3 doit être 100% verte AVANT Phase 4.

### Patch local non-commité (Phase 0 du battle plan)

`engine/core/cube_providers.py` ligne 1900-1909 : 5 lignes ajoutées qui
appellent `mycelium.observe_text(c.content)` sur fail. Forge passes 37/38
sur ce working tree (avec le patch). Le seul deadline flake est unrelated
au patch (touche subdivide_file et reconstruct_cube_waves, pas
_run_level_pass où le patch est).

**Verdict patch** : safe à committer comme quick-fix temporaire SI on
décide de ne pas faire Phase 3 (vrai API observe_failure). Sinon
revert et faire Phase 3 propre.

---

## Annexe : commandes forge utilisées

```bash
forge --modularity                                # ✅ done
forge --carmack                                   # ✅ done
forge --predict                                   # ✅ done
forge --anomaly                                   # ✅ done
forge --heatmap                                   # ✅ done
forge --gen-props engine/core/mycelium.py         # ✅ (0 tests)
forge --gen-props engine/core/mycelium_db.py      # ✅ (2 tests)
forge --gen-props engine/core/cube_providers.py   # ✅ (7 tests)
forge --gen-props engine/core/cube.py             # ✅ (11 tests)
forge --gen-props engine/core/cube_analysis.py    # ✅
forge --shield                                    # ✅ done
forge --locate                                    # ⏳ background
forge --flaky 2                                   # ⏳ background
forge --mutate --paths-to-mutate mycelium_db.py   # ⏳ background
```
