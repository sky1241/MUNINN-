# Branchement forge-shield v1.1.1 dans MUNINN-

**Date** : 2026-05-09
**Statut** : 📋 PLAN — pas encore exécuté
**Source** : audit 2 agents indépendants + diff v1.0.3 → v1.1.1 (cycles 5/6/7/8)
**Pré-requis** : forge-shield v1.1.1 release sur PyPI (sky1241/forge tag v1.1.1 ✅)

---

## 🎯 Bonne surprise

Le branchement est **plus léger** qu'estimé hier (4-6h) :

| Catégorie | Sites | Action |
|-----------|-------|--------|
| Subprocess `python forge.py` | **0** | RAS (c'était de la doc) |
| Imports Python `from forge import` | **2** | 1 critique + 1 test généré |
| Tests `test_props_*.py` | **17** | régéner auto |
| Doc CLAUDE.md RULE 5 | **1** | update commande |
| CI `forge_smoke` job | optionnel | proposition D8 |

**Estimation révisée : 2-3h.**

---

## 📦 Ce qu'on branche

`forge-shield v1.1.1` (single-file 4097L stdlib-only, mypy --strict, CI 9 jobs cross-platform 3 OS × 3 Python 3.11/3.12/3.13).

### Sub-commandes consommables par MUNINN-

| Subcommand | Usage MUNINN- |
|------------|---------------|
| `forge --carmack` | composite Kalman+Wavelet+KM+Newman → **score risque par fichier** pour heatmap cube UX |
| `forge --locate` | Ochiai SBFL → **score "die and retry"** par fichier pour heatmap |
| `forge --modularity` | Newman Q + Louvain clustering → **couplage architectural** |
| `forge --predict` | churn-based defect prediction → reprend `predict_defects()` actuel |
| `forge --anomaly` | z-score outlier detection (cycle 7) |
| `forge --fast-deep` | transitive impact tests (cycle 7 P2) — replace `--fast` simple |
| `forge --incremental-mutate` | libcst AST-diff mutation (cycle 6 — innovation Sky) |
| `forge --gen-props` | régénère les 17 `test_props_*.py` |

### Outputs forge consommables (artefacts JSON)

```
.forge/config.json         # 21 knobs tunable
.forge/baseline.json       # snapshot suite (passed/failed/errors + lists)
.forge/last_report.json    # dernier run
.forge/flaky.json          # {test_name: [pass_count, fail_count]}
.forge/forge_log.txt       # historique
BUGS.md                    # tracker (existe déjà MUNINN-)
tests/test_props_*.py      # générés auto
```

---

## 📋 Phase 4 — Plan d'exécution

### Phase 4.1 — Installation (~10 min)

**Objectif** : `pip install forge-shield` + déclaration dans `pyproject.toml` MUNINN-.

```bash
# Vérifier Python ≥ 3.11 (forge-shield requirement)
python3 --version  # déjà 3.13 chez Sky ✓

# Installer
pip install -c constraints.txt 'forge-shield[all]'

# Vérifier
forge --version    # → "forge-shield 1.1.1"
which forge        # → ~/.local/bin/forge ou venv

# Pin dans constraints.txt
echo "forge-shield==1.1.1" >> constraints.txt
echo "libcst>=1.0" >> constraints.txt  # pour --mutate / --incremental-mutate
echo "coverage>=7.0" >> constraints.txt # pour --locate
```

**Pyproject** : ajouter à la section `[project.optional-dependencies]` :
```toml
[project.optional-dependencies]
quality = [
    "forge-shield>=1.1.1",
    "libcst>=1.0",
    "coverage>=7.0",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",
]
```

### Phase 4.2 — Remap de l'import critique (~15 min)

**Site** : `engine/core/cube_analysis.py:1593`

Avant :
```python
from engine.core.forge import predict_defects
```

Après :
```python
# forge-shield v1.1.1+ : pip install forge-shield
try:
    from forge import predict_defects  # entry: forge.py module-level
except ImportError:
    # Fallback: forge-shield not installed → noop or use local
    def predict_defects(root):
        print("[forge-shield not installed; pip install forge-shield]")
        return None
```

Mais regarde d'abord si `predict_defects` est exposé directement dans le package public — c'est probable (vu qu'il a `[project.scripts] forge = "forge:main"` et le module est `forge.py` single-file).

### Phase 4.3 — Régénération des `test_props_*.py` (~30 min)

```bash
# Backup current
mkdir -p tests/_props_backup_2026-05-09
cp tests/test_props_*.py tests/_props_backup_2026-05-09/

# Modules à régénérer (17)
for module in tokenizer _secrets _hook_logger lexicons lang_lexicons \
              sentiment dedup budget_select mycelium_db mycelium \
              cube cube_analysis cube_providers muninn_layers \
              muninn_feed muninn_tree sync_backend; do
    forge --gen-props "engine/core/${module}.py"
done

# Diff vs backup pour voir ce qui change
diff -r tests/_props_backup_2026-05-09/ tests/test_props_*.py
```

### Phase 4.4 — Update CLAUDE.md RULE 5 (~5 min)

`CLAUDE.md:78-103` actuel :
```
python forge.py --gen-props engine/core/<module>.py
python -m pytest tests/test_props_<module>.py -q
```

Nouveau :
```
forge --gen-props engine/core/<module>.py
python3 -m pytest tests/test_props_<module>.py -q
```

(plus court, et c'est l'entry point pip-installé).

### Phase 4.5 — CI forge_smoke job (optionnel, ~30 min)

Reprendre `docs/CI_PROPOSED_D8.md` (proposition existante non mergée) et l'intégrer à `.github/workflows/ci.yml` :

```yaml
  forge_smoke:
    runs-on: ubuntu-latest
    needs: validate
    strategy:
      matrix:
        module: [cube, mycelium_db, muninn_tree, muninn_feed, _secrets,
                 cube_analysis, cube_providers, mycelium, muninn_layers,
                 _hook_logger, vault]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install forge-shield hypothesis
      - run: forge --gen-props engine/core/${{ matrix.module }}.py
      - run: pytest tests/test_props_${{ matrix.module }}.py -q
```

### Phase 4.6 — 🌟 Wiring heatmap UX cube (~1h)

**C'est ce que Sky avait évoqué** : utiliser les scores forge pour colorer la heatmap cube UX.

**Site** : `muninn/ui/cube_view.py` (ou `cube_live.py` selon le widget actif).

**Pipeline proposé** :
```python
# Au load du panneau cube UX
import json
import subprocess
from pathlib import Path

def _fetch_forge_scores(repo_path: Path) -> dict[str, float]:
    """Score 0-1 par fichier basé sur forge --carmack + --locate."""
    # 1. Run forge --carmack avec --json output (à confirmer si supporté)
    result = subprocess.run(
        ["forge", "--carmack", "--weeks", "12"],
        cwd=repo_path, capture_output=True, text=True, timeout=60
    )
    # parse stdout → dict {file_path: composite_risk}

    # 2. Combiner avec --locate (Ochiai "die and retry" signal)
    locate = subprocess.run(
        ["forge", "--locate"],
        cwd=repo_path, capture_output=True, text=True, timeout=30
    )
    # parse → dict {file_path: ochiai_score}

    # Fusion : carmack 0.6 + locate 0.4
    return _fuse_scores(carmack_scores, locate_scores)

def _color_for_score(score: float) -> str:
    """Mapping score → couleur heatmap."""
    if score >= 0.7:   return "#d62728"  # rouge — die-and-retry intense
    if score >= 0.4:   return "#ff7f0e"  # orange — risque modéré
    if score >= 0.2:   return "#bcbd22"  # jaune — moyen
    return "#2ca02c"                      # vert — stable
```

**3 sources fusionnées dans la heatmap** :
1. **Mycelium temperature** (chaud/froid d'usage runtime) — déjà présent
2. **Forge `--carmack` + `--locate`** (fragilité historique + signal "die and retry") — nouveau
3. **Forge `--modularity` Q-contribution** (couplage local) — nouveau

→ La heatmap devient un signal multi-axes : "ce fichier est utilisé souvent ET pète tout le temps ET il est couplé partout" = rouge vif.

**Questions à trancher avec Sky avant** :
- Cache des scores (lourd à recalculer en live) → `.muninn/forge_cache.json` avec TTL ?
- Async fetch (subprocess sur le main UI thread = freeze) → QThread worker ?
- Affichage des 3 axes (overlay multi-couleurs) ou juste un score fusionné ?

---

## 🚦 Ordre d'exécution recommandé

```
Phase 4.1  pip install + pyproject extras       [10min]
Phase 4.2  remap predict_defects import         [15min] ← CRITICAL
Phase 4.3  régénérer 17 test_props_*.py         [30min]
Phase 4.4  CLAUDE.md RULE 5 update              [5min]
─── push CI vert ici ───
Phase 4.5  forge_smoke job CI [optionnel]       [30min]
Phase 4.6  wiring heatmap UX cube [feature]     [1h+]
```

**Total essential : 1h** (4.1 → 4.4) + push CI vert.
**Total avec polish : 2-3h** (+ 4.5 + 4.6).

---

## ⚠️ Risques identifiés

| Risque | Mitigation |
|--------|------------|
| Conflit deps (libcst / coverage / hypothesis pin) | constraints.txt + tester en venv isolé |
| `predict_defects` API différente entre interne et public | tester localement avant commit ; fallback noop |
| Tests `test_props_*` régénérés avec stratégies différentes | diff vs backup ; si divergence → debug avant commit |
| `forge` non dans PATH après `pip install --user` | doc + ajouter `~/.local/bin` au PATH |
| CI Python 3.11 vs forge-shield py3.11+ | déjà aligné (CI bumped à 3.13) |

---

## ✅ Critères de done

- [ ] `forge --version` retourne `forge-shield 1.1.1` localement et en CI
- [ ] `engine/core/cube_analysis.py:1593` import remappé et test passe
- [ ] 17 `test_props_*.py` régénérés, suite verte (`pytest tests/test_props_*.py -q`)
- [ ] CLAUDE.md RULE 5 updated
- [ ] [optional] CI `forge_smoke` job vert
- [ ] [optional] heatmap UX cube affiche scores forge (Phase 4.6 = chunk dédié)

---

## 📝 Note sur les 3 forge.py internes

Décision recommandée :
- **Garder** `forge.py` (root, 2745L) — entry point CLI legacy
- **Garder** `engine/core/forge.py` (2196L, juste split P4) — fallback module
- **Garder** `muninn/forge.py` — fallback pour pip install local

→ Ne pas supprimer aujourd'hui. Marquer `# DEPRECATED — use pip install forge-shield` en tête.
→ Suppression dans une release MUNINN- v2.x dédiée (rupture API).
