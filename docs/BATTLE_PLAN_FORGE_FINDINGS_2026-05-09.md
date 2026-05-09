# Battle plan — Forge findings (2026-05-09)

**Source** : runs forge-shield 1.1.0 full-capacity sur `/home/sky/Bureau/MUNINN-` (résultats archivés dans `/tmp/forge_run_2026-05-09/`).
**Statut** : 📋 PLAN — non exécuté.
**Pré-requis** : Phase 4 forge branchement complet (commits `0d88508` → `dc7ca12`).

---

## 🎯 Objectif

Traiter les findings réels que forge a remontés. Différencier ce qui est :
- **Critique** : doit être actionné rapidement
- **Refactor** : utile pour la maintenabilité long-terme
- **Statistical noise** : à ignorer (anomalies normales pour des hubs)

---

## 📊 Synthèse des runs forge

| Run | Verdict global | Action requise ? |
|-----|----------------|------------------|
| `forge --modularity` | 🟢 Q = 0.677 (good ≥ 0.30) | **Aucune** — c'est un score sain |
| `forge --carmack` | 🟠 Top risque `engine/core/muninn.py` 0.558 | Refactor planifié |
| `forge --predict` | 🟠 Idem (churn 13.7, 46% bugfix rate) | Confirme carmack |
| `forge --anomaly` | 🟠 5 hubs flaggés en z-score | Examen, pas refactor en bloc |
| `forge --locate` | 🟢 1 fail = `test_tfidf_relevance_meaningful` | Dette P5 connue, deselect CI |
| `forge --fast-deep` | 🟢 RAS (working tree clean) | — |
| `forge --heatmap` | 🟡 66 runs loggés (peu d'historique) | Laisser s'accumuler 2-3 semaines |

---

## 🥇 Findings prioritaires (consensus carmack + predict + anomaly)

Ces 4 fichiers apparaissent **dans les 3 méthodes** comme à risque :

| # | Fichier | LOC | Bugfix rate | Coupling | Carmack | Predict |
|---|---------|-----|-------------|----------|---------|---------|
| 1 | `engine/core/muninn.py` | 2104 | **46%** (101/221) | **1.00** | 0.558 | 0.68 |
| 2 | `engine/core/mycelium.py` | 3163 | **56%** (47/84) | 0.05 | 0.293 | 0.41 |
| 3 | `engine/core/cube_providers.py` | 2135 | **52%** (34/65) | 0.15 | 0.284 | 0.37 |
| 4 | `engine/core/mycelium_db.py` | 1401 | **74%** (25/34) | 0.05 | 0.222 | 0.26 |

> Note : "bugfix rate" = ratio bugfix-commits / total-commits sur 12 semaines glissantes. Un taux > 30% indique un fichier "qui plante souvent".

---

## ⚠️ Avertissement — anti-overreaction

Avant d'attaquer :

1. **Ces fichiers sont les hubs core**. Ils ont un haut bugfix rate parce qu'**ils contiennent la logique principale**. Un refactor mal pensé peut **casser plus qu'il ne corrige**.
2. **Q-modularity = 0.677 = good**. L'architecture globale est saine. Les hubs ne doivent pas être éclatés en 100 micro-modules — ça réduirait Q.
3. **Pas de refactor sans test gold standard**. Chaque refactor doit être précédé d'un cliché du comportement (snapshot tests + mutation testing baseline).

---

## 📋 Phase F1 — Examen ciblé `muninn.py` (top risque, ~3h)

`engine/core/muninn.py` (2104L, 27 subcommands, coupling=1.0) est le **CLI orchestrator**. Coupling 1.0 = il importe absolument tout — c'est par design (entry point), pas un bug.

**Mais** 101 bugfixes sur 221 commits = 46% bugfix rate = signal réel. À actionner :

### F1.1 — Audit des 27 subcommands (~1h)
- Run `forge --gen-props engine/core/muninn.py` → tests Hypothesis sur les CLI helpers
- Identifier les 5 commandes les plus modifiées historiquement (via `forge --predict` filtré par fichier)
- Pour chacune : vérifier qu'elle a un test behavioural (pas juste un test source-greppy)

### F1.2 — Extraire les sub-routines longues (~1h)
- Identifier les fonctions `> 80 lignes` dans `muninn.py`
- Pour les 3 plus longues, vérifier :
  - Est-ce qu'elles ont un seul `if/else` profond qui peut être splitté ?
  - Est-ce qu'elles font du I/O + logique mélangés (= séparable) ?
- Splitter en `_helper()` modules locaux **sans changer la signature publique**

### F1.3 — Mutation testing ciblé (~1h)
```bash
forge --paths-to-mutate engine/core/muninn.py
```
- Mute uniquement ce fichier
- Mutants survivants = trous de coverage
- Pour chaque survivant : ajouter un test qui le tue

**Critère done** : carmack score `engine/core/muninn.py` < 0.50 (vs 0.558 actuel) au prochain run forge.

---

## 📋 Phase F2 — `mycelium.py` (3163L, 56% bugfix, ~3h)

`engine/core/mycelium.py` est le **gros morceau** : co-occurrence network + spreading activation + fusion + decay. 47 bugfixes sur 84 commits = 56% bugfix rate (le pire des 4).

### F2.1 — Sortir les sous-systèmes (~2h)
3 sous-systèmes identifiables qui pourraient devenir des modules dédiés :
- **Spreading activation** (Collins & Loftus 1975) → `engine/core/mycelium_activation.py`
- **Fusion / decay** (lifecycle des connexions) → `engine/core/mycelium_lifecycle.py`
- **Federation meta-mycelium** (cross-repo) → `engine/core/mycelium_federation.py`

Le `mycelium.py` resterait l'orchestrator + l'API publique. Les 3 sous-modules importés via re-exports.

⚠️ **Risque** : casser l'import shim `muninn/mycelium.py` (BUG-091). Faut adapter en parallèle.

### F2.2 — Property tests sur invariants (~30min)
- "Si concept A et B sont fusionnés, A.weight + B.weight doit être conservé" (mass conservation)
- "Decay sur connexion non-utilisée pendant N jours doit aboutir à removal" (lifecycle)
- "Spreading activation depuis seed inexistant doit retourner empty dict" (déjà testé brick15 — vérifier ailleurs)

### F2.3 — Bench avant/après refactor (~30min)
```bash
python3 -m timeit -n 100 'from mycelium import Mycelium; m = Mycelium("."); m.spread_activation(["test"], hops=2)'
```
Snapshot la latence pré-refactor. Le post-refactor ne doit pas régresser de plus de 10%.

**Critère done** : `mycelium.py` < 2000L. Carmack score < 0.20.

---

## 📋 Phase F3 — `cube_providers.py` (2135L, 52% bugfix, ~2h)

`engine/core/cube_providers.py` gère les providers (Ollama, mock, anthropic) pour la reconstruction cube.

### F3.1 — Architecture provider plugin (~1h30)
Actuellement les providers sont probablement codés en dur. Migration vers un **registry pattern** :
```python
@register_provider("ollama")
class OllamaProvider: ...

@register_provider("anthropic")
class AnthropicProvider: ...
```
→ Ajouter un nouveau provider = nouveau fichier dans `engine/core/cube_providers/`, pas de modif au core.

### F3.2 — Tests par provider (~30min)
Un test mock par provider (déjà partiellement fait via `test_props_cube_providers.py`).

**Critère done** : `cube_providers.py` < 1500L (orchestrator), `cube_providers/<provider>.py` chacun < 500L.

---

## 📋 Phase F4 — `mycelium_db.py` (1401L, 74% bugfix, ~2h)

**74% bugfix rate** = le plus alarmant en taux. Mais 25 bugfixes en 34 commits = chaque commit corrige presque un bug. Souvent c'est le signe d'un **module historiquement instable** mais maintenant stabilisé.

### F4.1 — Vérifier la stabilité actuelle (~30min)
Run `forge --carmack --weeks 4` (4 dernières semaines uniquement) :
- Si `mycelium_db.py` n'est plus dans le top 10 → fichier stabilisé, pas d'action
- Si toujours dans le top 5 → vraiment instable, refactor nécessaire

### F4.2 — Extract migration logic (~1h)
Le module contient probablement la migration JSON → SQLite + ConceptTranslator + WAL setup mélangés. Splitter :
- `mycelium_db.py` → connexion + transactions
- `mycelium_migration.py` → migration legacy
- `concept_translator.py` → ConceptTranslator (utility)

### F4.3 — Property tests SQL (~30min)
- "Insert + select retourne la même row" (round-trip)
- "FK cascade delete propre"
- "PRAGMA journal_mode = WAL persistant après reconnect"

**Critère done** : `mycelium_db.py` < 800L, plus de migration code mélangé.

---

## 📋 Phase F5 — Statistical noise (RAS, mais documenter)

`forge --anomaly` flag 5 fichiers mais ce sont **les hubs**. C'est attendu — un hub a forcément freq + loc anormalement élevés vs la médiane.

**Action recommandée** : **aucune**. Documenter dans `BUGS.md` que ces 5 anomalies sont **statistical noise inhérent à une topologie hub-and-spoke**, pas des bugs.

---

## 📋 Phase F6 — Heatmap UX cube (Phase 4.6 déjà planifiée, ~1h+)

Le branchement forge avait prévu une Phase 4.6 (heatmap UX cube). Avec les findings consolidés ci-dessus, on peut maintenant l'implémenter intelligemment :

```
muninn/ui/cube_view.py
  ├─ Mycelium temperature (hot/cold usage runtime) — déjà présent
  ├─ Forge --carmack score (fragility)            — NEW
  └─ Forge --modularity Q-contribution            — NEW
       ↓
  fusion : 0.5 × temperature + 0.3 × carmack + 0.2 × q_contrib
       ↓
  mapping couleur :
    rouge ≥ 0.7 (chaud + fragile + couplé)
    orange ≥ 0.4
    jaune ≥ 0.2
    vert sinon
```

**Pré-requis** :
- Cache des scores forge dans `.muninn/forge_cache.json` (TTL 24h)
- Async fetch (QThread) pour ne pas freeze l'UI
- Fallback "no forge installed" → afficher uniquement temperature

---

## 🎯 Ordre d'exécution recommandé

```
Étape 0 (CE WEEK-END, optionnel)  Phase F4.1 quick-check
                                    Run forge --carmack --weeks 4
                                    Si mycelium_db.py sort du top 5 → skip F4
                                    [30 min, low risk]

Étape 1 (PRIORITÉ HAUTE)          Phase F1 — muninn.py
                                    Le top risque, l'orchestrator
                                    Effort : 3h
                                    Risk : moyen (CLI public)

Étape 2 (PRIORITÉ MOYENNE)        Phase F2 — mycelium.py
                                    Le plus gros refactor mais le plus rentable
                                    (-1100 lignes potentiel)
                                    Effort : 3h
                                    Risk : ÉLEVÉ (BUG-091 dual tree)

Étape 3 (LATER)                    Phase F3 — cube_providers.py
                                    Architecture plugin = chunk dédié
                                    Effort : 2h
                                    Risk : faible

Étape 4 (CONDITIONNEL)             Phase F4 — mycelium_db.py
                                    Seulement si F4.1 confirme l'instabilité
                                    Effort : 2h
                                    Risk : ÉLEVÉ (data migration)

Étape 5 (FEATURE)                  Phase F6 — heatmap UX cube
                                    Pas un refactor, une nouvelle feature
                                    Effort : 1h+
                                    Risk : faible (UI-only)
```

**Total essential** (Étape 0 + 1) : ~3h30
**Total avec mycelium refactor** (+ Étape 2) : ~6h30
**Total ambitieux** (toutes étapes) : ~12h

---

## 🚦 Critères de done par phase

Pour chaque phase F1–F4 :
1. **Avant refactor** : forge --carmack baseline noté dans le commit
2. **Refactor** : commits séparés par sous-étape
3. **Tests** : `pytest tests/ -q` toujours vert + `forge --paths-to-mutate <file>` lance et tue les survivants
4. **CI vert** : push → run CI → vert avant phase suivante
5. **Après refactor** : forge --carmack re-run, score doit baisser de >= 10%

Pour F5 : juste un commit `docs(BUGS): document hub topology anomaly noise`.
Pour F6 : test fonctionnel UI (mock subprocess + assert color mapping correct) + screenshot dans le commit.

---

## ⚠️ Anti-bullshit (RULE 4)

Aucune phase n'est marquée DONE sans :
- Output verbatim de `forge --carmack` avant + après (preuve de baisse)
- Output verbatim de `pytest tests/ -q` (X passed in Y.Ys)
- Hash du commit publié + URL CI run vert

Pas de "ça marche" sans la commande qui le prouve.

---

## 📝 Note honnête

**Ce plan est ambitieux**. Sky a déjà poussé 12+ commits aujourd'hui. Réaliste :
- F4.1 quick-check (30min) faisable demain matin
- F1 muninn.py — chunk dédié, 1 demi-journée
- Le reste — étalé sur la semaine

Pas obligatoire de tout faire d'un coup. Le repo tourne en prod, les tests sont verts, **rien n'est cassé**. C'est un plan d'**amélioration**, pas un plan de fix.

Si le calendrier commercial presse, on peut s'arrêter à F1 (top risque) + F5 (doc anomaly noise) et garder F2-F4 pour plus tard.
