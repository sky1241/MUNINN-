# BATTLE PLAN — BUG-104 spill-to-tree fix (2026-05-10)

## Contexte

BUG-104 L12 BudgetMem : à tight budget (b=500 sur 1005 tok input), fact recall passe 15/15 → 6/15 (-60 points). Brick 17 a étendu detector mais root cause = chunks must-keep too big to fit, pas detector trop étroit.

**Solution validée par audit 3 agents + recherche SOTA web** : "spill-to-tree" — quand L12 doit dropper un chunk must-keep, l'écrire dans une nouvelle branche du tree au lieu de le perdre. Boot() le retrouvera via TF-IDF + spreading activation sur les concepts. Calque V9A+ regen pattern (Shomrat & Levin 2013 planère) appliqué à L12 au lieu de prune.

## Findings audit (3 agents 2026-05-10 PM)

### Architecture actuelle (`engine/core/budget_select.py` 414L)

- 2 fonctions publiques : `budget_select(text, budget) -> str`, `select_chunks(chunks, budget) -> list[indices]`
- Phase 1 (must-keep) + Phase 2 (score fill) imbriquées
- **TROUS** : pas de `repo_path` passé, chunks dropped non exposés, pas de métadonnées chunks, `compress_file` pas connecté au tree

### Helpers tree disponibles (`engine/core/muninn_tree.py`)

- `_atomic_text_write`, `compute_hash`, `refresh_tree_metadata`, `extract_tags`, `load_tree`/`save_tree` avec `_tree_lock` intégré
- Pattern `grow_branches_from_session` réutilisable : nommage `b{NN:02d}`, defaults OK
- Helper ~30L suffit pour spill

### Tests à modifier (`tests/test_brick12_l12_fact_recall.py` 8 tests)

- 2 envelope tests (#6 verbose b=500 → 6/15, #7 session → 9/15) doivent **fail** quand spill marche → bornes hautes à relever
- 3 no-regression tests (huge budget) doivent continuer à passer
- 5 nouveaux tests à ajouter pour le spill (files créés, facts préservés, boot retrieve, envelope amélioré, métadonnées)

## Plan d'exécution — 6 phases, ~3h focused

### Phase 0 — Protection (10 min)

1. Tag rollback `pre-BUG-104-spill-2026-05-10`
2. Run baseline : confirmer 2332 PASS + envelope BUG-104 reproduit (6/15 à b=500)
3. forge --gen-props baseline sur `budget_select.py` : capter prop tests pré-fix

### Phase 1 — `budget_select.py` : exposer dropped chunks (30 min)

**Changements** :
- Modifier `select_chunks()` : retourne `(kept: list[int], dropped: list[int])` (tuple au lieu de juste kept)
- Ajouter wrapper `budget_select_with_dropped(text, budget) -> tuple[str, list[str]]` qui retourne (kept_text, list_des_textes_dropped)
- **Backward compat** : `budget_select()` continue de retourner string (autres callers inchangés)

**Tests** :
- `forge --gen-props engine/core/budget_select.py` doit toujours passer (les nouvelles props doivent vérifier l'invariant kept ∪ dropped = all_indices)
- Tests existants `test_props_budget_select.py` : doivent passer

**Commit séparé** : `refactor(BUG-104 P1): expose dropped chunks in budget_select`

### Phase 2 — Helper `spill_chunks_to_tree` dans `muninn_tree.py` (30 min)

**Ajout** :
```python
def spill_chunks_to_tree(repo_path: Path, dropped_chunks: list[str],
                        source_id: str = "") -> list[str]:
    """Spill chunks must-keep dropped par L12 dans des branches dédiées.

    BUG-104 fix: au lieu de drop les chunks must-keep qui ne rentrent pas
    dans le budget L12, les écrit dans .muninn/tree/spill_<source_id>_<n>.mn
    avec tags (extract_tags) → boot() les retrouve via TF-IDF.

    Returns: list des branch names créées (peut être vide si dropped_chunks vide).
    """
    if not dropped_chunks:
        return []
    tree = load_tree()
    nodes = tree["nodes"]
    # ... compute next_id, write .mn, update tree.json with locks
```

**Tests** :
- `tests/test_chunk_bug104_spill.py` (nouveau) : 3-4 tests unitaires sur le helper isolé
  - test_spill_creates_branch_files
  - test_spill_extracts_tags_correctly
  - test_spill_idempotent_dedup
  - test_spill_under_lock_no_race

**Commit séparé** : `feat(BUG-104 P2): add spill_chunks_to_tree helper`

### Phase 3 — Wire dans `muninn_layers.py:_l12_budget_pass` (30 min)

**Changements** :
- `_l12_budget_pass(text)` → `_l12_budget_pass(text, repo_path=None)`
- Si `MUNINN_L12_BUDGET` set ET `repo_path` disponible (default = `_m._REPO_PATH`) :
  - Capture dropped chunks via `budget_select_with_dropped`
  - Appeler `spill_chunks_to_tree(repo_path, dropped, source_id=session_id)`
  - Insérer stub `[spilled: branch_names, K facts]` dans output
- **Backward compat** : si `_m._REPO_PATH = None` → comportement actuel (drop sans spill)

**Tests** :
- `test_brick12` envelope tests #6 et #7 doivent maintenant **fail** car recall remonte → on les ajuste à `assert 12 <= answered <= 15`
- Boot test : compress + boot avec query → fact retrouvé via spill branche

**Commit séparé** : `feat(BUG-104 P3): wire L12 to spill dropped chunks`

### Phase 4 — Tests + forge full cycle (45 min)

1. Update `test_brick12_l12_fact_recall.py` envelope tests
2. Add 5 nouveaux tests (templates fournis par audit agent 3)
3. `forge --gen-props` sur les 3 modules touchés :
   - `engine/core/budget_select.py`
   - `engine/core/muninn_tree.py`
   - `engine/core/muninn_layers.py`
4. Full pytest baseline : cible **2335 PASS** (2332 - 2 envelope BUG-104 + 5 nouveaux spill = +3 net)
5. forge --modularity : Q stable >= 0.65

### Phase 5 — Docs (15 min)

1. `BUGS.md` : marquer BUG-104 **FIXED** avec commit hash + référence spill-to-tree
2. `CHANGELOG.md` : entrée fix BUG-104 avec details
3. `docs/PIPELINE_FORMULAS_MAP.md` : L12 BudgetMem status OPT-IN → ACTIVE (BUG-104 closed)
4. `docs/ROADMAP_2026-05-10.md` : phase 2 BUG-104 → DONE
5. `tests/benchmark/PHASE_B_FACT_RECALL.md` : update tableau avec nouveaux résultats post-fix

### Phase 6 — Commit + push + CI (15 min)

- Si phases 1-5 commits séparés : push une fois tout vert local
- Wait CI green sur HEAD (~35 min)
- Si CI rouge : revert via tag `pre-BUG-104-spill-2026-05-10`

## Risques + mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Race condition tree lock | basse | déjà géré par `_tree_lock` dans `save_tree` |
| Spill explosion (100 spills sur transcripts répétés) | moyenne | NCD-dedup via `_sleep_consolidate` (déjà en place) |
| Tags incorrects → boot rate | moyenne | brick 17 detector + `extract_tags` ; test pin |
| Test_brick13 BUG-105 conflit | basse | spill skip si `\n\n` absent (déjà guard BUG-105) |
| `_m._REPO_PATH = None` en CI | haute | spill no-op si None → backward compat préservé |

## Cibles métriques post-fix

| Métrique | Pre-fix | Post-fix cible |
|---|---|---|
| verbose_memory.md b=500 fact recall | 6/15 (40%) | **13-15/15 (≥87%)** |
| sample_session.md b=500 fact recall | 9/15 (60%) | **13-15/15 (≥87%)** |
| Tests pytest | 2332 PASS | **2335 PASS** (-2 envelope, +5 spill) |
| forge --modularity Q | 0.660 | **≥ 0.655** (drift acceptable) |
| BUGS.md OPEN | 1 (BUG-104) | **0** |

## Décision

**GO** — exécuter phases 0-6 maintenant, ~3h focused. Plan validé par 3 agents en parallèle (architecture budget_select OK, tree helpers OK, tests strategy OK).
