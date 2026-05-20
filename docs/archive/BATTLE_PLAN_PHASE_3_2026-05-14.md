# Battle Plan Phase 3 — Mycelium learns from fails (2026-05-14)

Validé par Sky 2026-05-14. Implémentation autonome jusqu'au commit final.

## Trois ajouts demandés par Sky

1. **Auto-calibration du weight** (env var `MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE=1`)
2. **Bug #2101 corrigé dans cette même phase** (pas séparé)
3. **MCP : Claude tranche** → flag `apply_failure_penalty=True` par défaut (rétrocompat sécurisée)

## Steps (séquentiel, ~6h)

| Step | Description | Durée |
|---|---|---:|
| 0 | Revert patch local `cube_providers.py` ligne 1900-1909 | 1 min |
| A | Schéma SQL : `CREATE TABLE failures` dans `_setup_tables()` + migration v3→v4 + SCHEMA_VERSION=4 | 30 min |
| B | DB methods : `upsert_failure`, `get_failure_weight`, `get_failure_weights_batch` (perf critical) | 45 min |
| C | API `observe_failure(text, weight=-0.5)` + helper `_record_failure` + env var override | 45 min |
| C-bis | Auto-calibration optionnelle (sigmoid centré 0.5, persistance JSON, recompute toutes 50 obs) | 1h |
| D | `spread_activation` injecte penalty via batch query, flag `apply_failure_penalty=True` default | 30 min |
| E | Wire pipeline `reconstruct_adaptive` + fix bug #2101 (observe → observe_text, drop zone=) | 30 min |
| F | 13 tests dans `tests/test_phase3_observe_failure.py` | 1h30 |
| G | forge --gen-props + pytest full suite (no regression) | 30 min |
| H | CLAUDE.md env vars + CHANGELOG + 1 commit verbatim outputs | 30 min |

## Invariants RULE 4 / RULE 5

- **No claim without command output** : chaque step affiche pytest output verbatim avant validation
- **Forge after each engine touch** : `forge --gen-props` sur les fichiers modifiés avant commit
- **No push without Sky's GO** : commit local final, attendre OK pour push

## Critères de succès

1. `pytest tests/test_phase3_observe_failure.py -v` → 13/13 pass
2. `pytest tests/ -q` → 2849+ tests, 0 régression
3. `forge --gen-props engine/core/mycelium.py` → tests générés (vs 0 avant)
4. Bug #2101 réparé (observe sans zone=)
5. CLAUDE.md à jour avec 2 nouvelles env vars
6. 1 commit unique avec message détaillé
