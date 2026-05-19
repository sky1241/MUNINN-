# Pattern récidive : nouveau env var doc-only → whitelist h0 obligatoire

> **Objectif** : éviter qu'une future session Claude tombe pour la 4ème
> fois dans le même piège. Le pattern s'est déjà répété 3 fois en
> 2026-05-19 (commits `dbb2708`, parts of E8, `a6f7773`).

## Le pattern

Quand on ajoute une nouvelle variable d'environnement `MUNINN_*` :

1. **Si elle est LUE par du code engine/UI/hooks tracked** :
   - Documenter dans `CLAUDE.md` (table § Configuration)
   - Les 2 tests doc-drift passent automatiquement.

2. **Si elle est LUE par du code dans un fichier `.gitignore`d**
   (script local-only, bench opt-in, eval harness, etc.) :
   - Documenter dans `CLAUDE.md` (table § Configuration)
   - **EN PLUS** : ajouter à `WHITELIST_DOC_ONLY_ENV_VARS` dans
     `tests/test_h0_no_orphan.py`.

   Pourquoi : le test `test_h0_all_env_vars_documented_read` scanne
   `engine/`, `muninn/`, `.claude/hooks/` pour vérifier que toute
   variable documentée dans CLAUDE.md est *aussi* lue quelque part.
   Si le seul lecteur est un fichier gitignored, le test fail en CI
   (l'index doesn't contain it) bien que le code marche localement.

## Historique des récidives

| Date | Var | Caller gitignored | Hotfix commit |
|---|---|---|---|
| 2026-05-19 13:51 | `MUNINN_RUN_PERF` | `tests/test_perf_*.py` (opt-in) | `dbb2708` |
| 2026-05-19 19:28 | `MUNINN_FUSE_RISKS_ORDERING` | — *(pas gitignored, juste un faux flag)* | — |
| 2026-05-19 22:03 | `MUNINN_BENCH_FILE` + `MUNINN_BENCH_MODELS` | `tests/run_bench_multi_llm_2026_05_14.py` | `a6f7773` |

## Checklist anti-récidive

Avant de commit/push une modif qui ajoute un `MUNINN_*` à CLAUDE.md :

```bash
# 1. Trouver tous les callers
grep -rn "MUNINN_FOOBAR" /home/sky/Bureau/MUNINN-/ --include="*.py" --include="*.sh"

# 2. Pour chaque caller :
#    - S'il est tracké : OK, rien de plus à faire
#    - S'il est gitignored : `cat .gitignore | grep <path>` confirme
#      → AJOUTER à WHITELIST_DOC_ONLY_ENV_VARS dans test_h0_no_orphan.py
#      → MÊME COMMIT que la doc CLAUDE.md, pas un commit séparé

# 3. Vérifier local AVANT push
QT_QPA_PLATFORM=offscreen python -m pytest \
  tests/test_h0_no_orphan.py::test_h0_all_env_vars_documented_read \
  tests/test_chunk_c10_c11_doc_drift.py \
  -v --timeout=20
# Les 2 doivent passer.
```

## Pourquoi ne pas changer le test ?

On pourrait modifier `test_h0_all_env_vars_documented_read` pour qu'il
ignore automatiquement les fichiers gitignored. Mais :

1. Lire `.gitignore` correctement (avec patterns globs, `**`, négations
   `!path`) est non-trivial.
2. Le pattern actuel est explicite : si tu ajoutes un env var à CLAUDE.md,
   tu DOIS savoir si son caller est gitignored ou non. La whitelist
   manuelle force ce choix.
3. La whitelist actuelle (10 vars) est petite, facile à reviewer.

Mieux vaut un test strict qui demande de la rigueur qu'un test laxiste
qui rate des drifts.

## Note pour les sessions Claude futures

Si tu vois ce pattern dans le passé git :
```
fix(test): X hotfix — whitelist MUNINN_FOO as doc-only test opt-in
```
... c'est exactement cette récidive. Ne re-cree pas le bug, applique
la checklist ci-dessus AVANT de pousser une modif CLAUDE.md.
