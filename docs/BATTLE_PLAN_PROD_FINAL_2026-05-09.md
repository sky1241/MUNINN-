# Battle plan PROD FINAL v2 — soir 2026-05-09

**Décision Sky** : on garde TOUT (le code écrit était senser être en production, juste oublié). Pas de delete, on **wire correctement** chaque truc.

**Pattern par chunk** (debug + 6 tests forge complet) :
```
1. git tag pre-H<N>-2026-05-09         # rollback safety
2. forge --modularity                   # baseline Q (≥ 0.30)
3. forge --carmack | head -5            # baseline top risque
4. <edit code>
5. pytest tests/ -q                     # local vert
6. forge --modularity                   # Q reste ≥ baseline
7. forge --carmack | head -5            # top risque ne monte pas
8. forge --locate                       # 0 nouveau Ochiai high
9. forge --predict | head -5            # churn rank stable
10. forge --anomaly | head -10          # 0 nouveau outlier
11. git commit + push                   # déclenche CI
12. CI vert = en production             # chunk suivant
```

Si CI fail → `git revert <commit>` immédiat, pas de fix-forward.

---

## 📋 Inventaire factuel — ce qui n'est PAS en production

### A. Forge interne — 3 fichiers parallèles au PyPI

| Fichier | Taille | Diagnostic |
|---------|--------|------------|
| `/forge.py` | 109K | Legacy CLI, 28 fonctions toutes équivalentes au PyPI |
| `/engine/core/forge.py` | 86K | 27 fonctions, 2 renommées dans PyPI (`detect_anomalies`→`anomaly_detect`, `measure_robustness`→`measure_modularity`) |
| `/muninn/forge.py` | 86K | Mirror identique à engine/core |

**Audit conclu** : suppression = **zéro perte fonctionnelle**, juste renommage d'imports.

### B. forge_metrics (F6) — module créé, 0 import UI

- `engine/core/forge_metrics.py` = 304L, 11 tests verts
- Pas consommé par `muninn/ui/cube_view.py` ni `cube_live.py`

### C. Méthodes mycelium orphelines — code écrit, jamais wiré

| Méthode | LOC | Sites prod | Plan |
|---------|-----|------------|------|
| `detect_zones` | 152 | 0 | → nouvelle CLI `muninn zones` |
| `auto_label_zones` | 46 | 0 | → idem (interne à `muninn zones`) |
| `get_zones` | 12 | 0 | → idem (interne à `muninn zones`) |
| `growth_stats` | 17 | 0 | → wire dans `muninn status` |
| `detect_blind_spots` | 133 | **2** ✅ | déjà en prod |

→ **227L de code à wire en production** (pas delete).

### D. Tests "workflow not merged"

- `tests/test_chunk_c12_ci_workflow.py` (8 skips) — workflow pytest CI **DÉJÀ MERGÉ le 8 mai** → tests obsolètes, retirer skip
- `tests/test_chunk_d8_ci_forge.py` (3 skips) — workflow forge_smoke **JAMAIS MERGÉ** → merger le workflow

### E. xfails — bugs acknowledged jamais fixés

- `test_retrieval_benchmark.py:407` — GROUND_TRUTH dérive (refresh dict)
- `test_sync_tls.py:235` — SyncServer rate-limit retourne `pong` au lieu d'erreur (vrai fix)

---

## 🎯 Phases d'attaque (révisées — wire au lieu de delete)

### **Phase H1 — Forge migration totale** (~45min) — 🔴 PROD-BLOCKING

**Steps** :
1. Tag git `pre-H1-forge-migration-2026-05-09`
2. **Renommer les imports** :
   - `engine/core/cube_analysis.py:1593` → `from forge import predict_defects`
   - `tests/test_props_forge.py:9` → `from forge import *`
   - `tests/test_forge_carmack.py:23` → `from forge import (predict_carmack, anomaly_detect, flaky_dtw)` (les noms PyPI)
3. `git rm forge.py engine/core/forge.py muninn/forge.py`
4. Update `tests/test_chunk_d11_shim_drift.py` — retirer `"forge"` de `engine_only`
5. Update `tests/test_brick19_dead_code_audit.py` — retirer references mortes au forge interne
6. **6 tests forge baseline** + pytest + commit + push + CI vert

**Critère done** : `find . -name 'forge.py' -not -path '*/site-packages/*' -not -path '*/.git/*'` = 0.

---

### **Phase H2 — forge_metrics → cube heatmap UX** (~1h-1h30) — 🟡 FEATURE

**Objectif** : `forge_metrics` consommé par UI cube_view, heatmap colorée par fragility.

**Steps** :
1. Identifier widget cube heatmap dans `muninn/ui/`
2. Ajouter helper async qui appelle `get_repo_risk()` au load + cache TTL 24h (déjà géré dans forge_metrics)
3. Mapping couleur via `color_for_score()`
4. Async fetch via QThread (pas freezer UI)
5. Fallback "no forge" → temperature mycelium seul
6. Tests UI + commit + push + CI vert

---

### **Phase H3 — Wire 4 méthodes mycelium en production** (~45min)

**Sub-step H3.1 — `growth_stats` dans `muninn status`** (~10min)
- Lire `engine/core/muninn.py::show_status()` — ajouter `m.growth_stats()` output
- Test : `muninn status` affiche un nouveau bloc "Growth"
- **Tests forge baseline avant** + commit + push + CI

**Sub-step H3.2 — Nouvelle CLI `muninn zones`** (~30min)
- Dans `engine/core/muninn.py` :
  - Ajouter `"zones"` à la liste des subcommands argparse
  - Créer `_handle_zones_command(args)` qui fait :
    - `m = Mycelium(repo)` 
    - `zones = m.detect_zones()`
    - `labels = m.auto_label_zones(zones)`
    - Print formatted output (top N zones par taille, label, top concepts)
- Mirror dans `muninn/_engine.py`
- Test : `muninn zones` retourne au moins 1 zone sur le repo MUNINN-
- **Tests forge baseline avant** + commit + push + CI

**Sub-step H3.3 — Update README** (~5min)
- Ajouter `muninn zones` à la table des 27 commandes (qui devient 28)
- Mentionner `growth_stats` dans la section Commands

---

### **Phase H4 — Tests workflow obsolètes** (~30min)

**H4.1 — C12 (8 skips obsolètes)** (~10min)
- Workflow pytest CI déjà mergé (commit `bf3858a`) — retirer les `pytest.skip("workflow not merged")` 
- Vérifier les asserts : ils doivent passer maintenant que ci.yml a `pytest`
- Si ils échouent : c'est que les asserts attendaient un autre format → adjust

**H4.2 — D8 forge_smoke matrix wire** (~20min)
- Lire `docs/CI_PROPOSED_D8.md`
- Merger le job `forge_smoke` dans `.github/workflows/ci.yml` (matrix par module)
- Retirer les `pytest.skip` dans `test_chunk_d8_ci_forge.py`
- Push avec workflow scope (déjà acquis au G1.2)
- CI run #N+1 vert avec le nouveau job

---

### **Phase H5 — xfails fix** (~1h-2h)

**H5.1 — `test_retrieval_benchmark` GROUND_TRUTH refresh** (~30min)
- Lire actuel `GROUND_TRUTH` dict
- Cross-check avec `memory/tree.json` actuel — quelles branches existent vraiment, quels tags
- Update dict pour refléter l'état actuel
- Retirer `@pytest.mark.xfail`
- Test passe : commit + push + CI

**H5.2 — `test_t1_9_rate_limit_server` fix protocole** (~1h)
- Lire `engine/core/sync_tls.py::SyncServer` rate-limit logic
- Le bug : retourne `{status: pong}` au lieu de `{error: rate_limited}`
- Fix : ajouter early return avec `{error: "rate_limited"}` quand quota dépassé
- Test passe : retirer `@pytest.mark.xfail`, commit + push + CI

---

### **Phase H6 — F2 mycelium split** (~1h40) — 🟢 OPTIONNEL ce soir

Refactor cosmétique du fichier 3163L → 3 sous-modules. Plan déjà rédigé. Aucun changement sémantique.

---

## 🚦 Ordre d'exécution

```
1. H1   forge migration totale         [45min]   🔴 PROD-BLOCKING
2. H4.1 C12 retirer skip obsolètes     [10min]   cleanup
3. H3.1 growth_stats → muninn status   [10min]   wire
4. H3.2 muninn zones nouvelle CLI      [30min]   wire ★
5. H3.3 README update zones+growth     [ 5min]   doc
6. H4.2 D8 forge_smoke workflow merge  [20min]   wire CI
7. H5.1 retrieval_benchmark refresh    [30min]   xfail fix
8. H2   forge_metrics → UI cube        [1h-1h30] FEATURE ★
9. H5.2 sync_tls rate-limit fix        [1h]      xfail fix
10. H6  F2 mycelium split              [1h40]    optionnel demain
```

**Total essential (H1-H5)** : ~4h-5h
**Avec H6** : ~6h-7h

---

## 🛡️ Garde-fous globaux — pattern uniforme par chunk

```bash
# AVANT
git tag pre-H<N>.<M>-2026-05-09
forge --modularity                    # Q baseline (≥ 0.30 attendu)
forge --carmack | head -10            # top risque baseline
pytest tests/ -q [excludes]           # 2398+ pass baseline

# EDIT le code

# APRÈS
forge --modularity                    # Q ≥ baseline (pas de régression archi)
forge --carmack | head -10            # top risque ne monte pas
forge --locate 2>&1 | head -5         # 0 nouveau Ochiai high
pytest tests/ -q [excludes]           # 2398+ pass (zéro régression)

# COMMIT + PUSH
git commit -m "<message verbose>"
git push
gh run watch <id>                     # poll CI

# CI vert = en production = chunk suivant
# CI fail = git revert immédiat
```

---

## ✅ Critère de done global pour la journée

À la fin de H1-H5 :
- [x] 0 forge.py interne (PyPI = unique source production)
- [x] forge_metrics consommé par UI cube
- [x] mycelium 4 méthodes orphelines wirées (`growth_stats` + `muninn zones` CLI)
- [x] 0 test "workflow not merged" (C12 retiré, D8 mergé)
- [x] 0 xfail (les 2 fixés)
- [x] CI vert sur main
- [x] forge --modularity Q ≥ 0.677 (pas de régression archi)
- [x] README à jour avec nouvelles CLI commands

---

## 📊 État cible final journée

```
Avant aujourd'hui :
  - forge interne 3 copies (280K)
  - 4 méthodes mycelium dead
  - 11 tests workflow obsolètes
  - 2 xfails
  - forge_metrics non consommé

Après H1-H5 :
  - 1 seul forge (PyPI 1.1.0)
  - 100% mycelium API en production
  - 0 test obsolète
  - 0 xfail
  - heatmap UX cube colorée par forge metrics
  - 27 commandes CLI → 28 (muninn zones)
  - Q-modularity ≥ 0.677
  - CI vert
```
