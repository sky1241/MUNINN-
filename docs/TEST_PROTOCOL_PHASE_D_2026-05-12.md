# Test Protocol — Phase D Fin de Cycle (2026-05-12)

> **Audience** : Sky (et tout reviewer humain) qui veut vérifier de ses propres yeux que tout ce qu'on a livré dans Phase D (D.1, D.2, D.4, D.5 + hotfix CI) fonctionne en production sans bug latent.
>
> **Time budget** : ~20 minutes si tout est vert. Plus si une étape échoue (cf. section "What if red").
>
> **Quand l'utiliser** : avant l'upload PyPI prod (D.3). Si toutes les étapes ci-dessous sont vertes, on peut uploader sur pypi.org avec confiance.

---

## ✅ Step 1 — CI HEAD green check

**Pourquoi** : la CI doit tourner verte sur le commit courant. Si elle est rouge, on n'upload rien sur prod.

```bash
gh run list --limit 1 --branch main --json status,conclusion,displayTitle
```

**Expected output** :
```json
[{"conclusion":"success","status":"completed","displayTitle":"fix(ci): D.4 CI broke ..."}]
```

**🟢 Pass** : `conclusion = success`
**🔴 Fail** : `conclusion = failure` → ouvre le run avec `gh run view <id> --log-failed` et fix avant de continuer

---

## ✅ Step 2 — Full pytest local

**Pourquoi** : vérifie qu'aucune régression locale. La CI peut être verte mais avec ignores ; ici on tape la suite complète locale.

```bash
cd /home/sky/Bureau/MUNINN-
python3 -m pytest tests/ -q --tb=line \
  -m "not slow" \
  --ignore-glob='tests/test_ui_*.py' \
  --ignore=tests/eval_harness_chunk9.py \
  --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies
```

**Expected output** (dernière ligne) :
```
2561 passed, X skipped, 2 deselected, X warnings in ~3min
```

**🟢 Pass** : `0 failed` (ignore les warnings UserWarning UTC ou TLS — déjà connus)
**🔴 Fail** : N failed → investigate. Si flaky perf test (`test_performance_delta_faster`), rerun isolé ; sinon vrai bug.

---

## ✅ Step 3 — Local doctor "ALL GREEN"

**Pourquoi** : vérifie l'install local + les 25 checks doctor (dont les 3 nouveaux D.5 pip-install).

```bash
python3 engine/core/muninn.py doctor 2>&1 | tail -5
```

**Expected output** :
```
=========================
  ALL GREEN — 25 checks passed
=========================
```

**🟢 Pass** : "ALL GREEN", 25 checks (ou plus si nouveaux ajoutés)
**🔴 Fail** : "X FAIL, Y OK" → regarde les lignes `[FAIL]` au-dessus

**Note** : les checks D.5 console_scripts/engine.core peuvent montrer `[WARN] (dev mode — only meaningful via pip install)` — c'est attendu en dev tree, pas un fail.

---

## ✅ Step 4 — Build clean + twine check

**Pourquoi** : avant tout upload, on rebuild from scratch + valide les metadata.

```bash
cd /home/sky/Bureau/MUNINN-
rm -rf build dist *.egg-info
python3 -m build --no-isolation 2>&1 | tail -3
python3 -m twine check dist/*
```

**Expected output** :
```
Successfully built muninn_memory-1.0.1.tar.gz and muninn_memory-1.0.1-py3-none-any.whl
Checking dist/muninn_memory-1.0.1-py3-none-any.whl: PASSED
Checking dist/muninn_memory-1.0.1.tar.gz: PASSED
```

**🟢 Pass** : "PASSED" pour wheel ET sdist
**🔴 Fail** : "FAILED" → regarde le message, souvent un classifier non-conforme ou README invalide

---

## ✅ Step 5 — Wheel content audit (no leaks)

**Pourquoi** : vérifie que le wheel ne ship pas de données sensibles (`.muninn/`, scans utilisateur, secrets).

```bash
echo "=== Leaks check ==="
unzip -l dist/muninn_memory-1.0.1-py3-none-any.whl | grep -E "\.muninn/|scans/|edits_log|errors\.json|\.pyc|\.git/" || echo "✅ CLEAN"

echo "=== Engine shipped check ==="
unzip -l dist/muninn_memory-1.0.1-py3-none-any.whl | grep -E "engine/core/(tokenizer|mycelium|_secrets)\.py" | wc -l
```

**Expected output** :
```
=== Leaks check ===
✅ CLEAN

=== Engine shipped check ===
3
```

**🟢 Pass** : "✅ CLEAN" pour leaks ET ≥3 pour engine shipped (preuve fix D.1)
**🔴 Fail** : leaks trouvés → vérifie MANIFEST.in (doit `prune muninn/.muninn` + `prune muninn/ui/scans`)

---

## ✅ Step 6 — Install from TestPyPI dans venv vierge

**Pourquoi** : reproduit ce qu'un utilisateur final fait. Si ça crashe ici, ça crashera pour les users.

```bash
rm -rf /tmp/muninn_protocol_venv
python3 -m venv /tmp/muninn_protocol_venv
/tmp/muninn_protocol_venv/bin/pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ 'muninn-memory[mcp]==1.0.1' 2>&1 | tail -3
```

**Expected output** :
```
Successfully installed ... muninn-memory-1.0.1 mcp-X.Y.Z ...
```

**🟢 Pass** : "Successfully installed muninn-memory-1.0.1"
**🔴 Fail** : "Could not find a version" → vérifie que 1.0.1 est bien uploadé sur https://test.pypi.org/project/muninn-memory/

---

## ✅ Step 7 — D.4 welcome banner (no-args)

**Pourquoi** : vérifie que la fix D.4 est dans le wheel installé.

```bash
/tmp/muninn_protocol_venv/bin/muninn 2>&1 | head -10
```

**Expected output** :
```
Welcome to Muninn 1.0.1 — LLM memory compression engine.

First time? Here are the 3 commands to know:

  muninn init       Set up Muninn in the current repo
                    (creates .muninn/, installs Claude Code hooks)
  ...
```

**🟢 Pass** : message commence par "Welcome to Muninn 1.0.1"
**🔴 Fail** : argparse error "the following arguments are required" → D.4 fix pas dans le wheel

---

## ✅ Step 8 — D.4 empty-repo guard (no auto-init dans site-packages)

**Pourquoi** : vérifie le fix RULE 1 violation.

```bash
mkdir -p /tmp/muninn_protocol_empty
cd /tmp/muninn_protocol_empty
/tmp/muninn_protocol_venv/bin/muninn status 2>&1 | head -5
```

**Expected output** :
```
No .muninn/ found in: /tmp/muninn_protocol_empty

This directory isn't a Muninn-initialized repo yet.
Run `muninn init` here to set it up:
```

**🟢 Pass** : message "No .muninn/ found"
**🔴 Fail** : tree output ("=== MUNINN TREE ===") → fix D.4 absent ; check `find /tmp/muninn_protocol_venv -name "tree.json"` qui ne doit RIEN retourner

---

## ✅ Step 9 — D.4 init flow + doctor pip-install

**Pourquoi** : end-to-end : init → doctor → status, dans le venv.

```bash
cd /tmp/muninn_protocol_empty
/tmp/muninn_protocol_venv/bin/muninn init 2>&1 | tail -3
/tmp/muninn_protocol_venv/bin/muninn doctor 2>&1 | tail -3
/tmp/muninn_protocol_venv/bin/muninn status 2>&1 | head -5
```

**Expected output** :
```
  Muninn ready: /tmp/muninn_protocol_empty

  ALL GREEN — 25 checks passed   ← (les 3 nouveaux checks D.5 sont OK ici)
========================================

=== MUNINN TREE ===
  Version: 2
```

**🟢 Pass** : init OK + doctor "ALL GREEN" (vraiment 25 checks, pas WARN) + status montre tree
**🔴 Fail** : 
- doctor montre `[FAIL] console_script muninn` → D.1 fix engine/* shipped cassé
- doctor montre `[FAIL] engine.core not importable` → idem
- doctor montre `[WARN] mcp not installed` → réinstalle avec `[mcp]` extra

---

## ✅ Step 10 — D.5 examples runnable

**Pourquoi** : vérifie que les exemples livrés ne sont pas du code mort.

```bash
cd /home/sky/Bureau/MUNINN-/examples
MUNINN_DEMO_REPO=/tmp/muninn_protocol_empty /tmp/muninn_protocol_venv/bin/python3 quickstart_local.py 2>&1 | tail -10
```

**Expected output** (tail) :
```
✓ Done. Next steps:
  - Inspect /tmp/muninn_protocol_empty/.muninn/ (tree.json, mycelium.db, sessions/)
  - Try `muninn doctor` to verify your install
  - Try `mcp_recall_demo.py` to see the MCP-style API
```

**🟢 Pass** : le script tourne, finit avec "✓ Done"
**🔴 Fail** : exception Python → l'exemple est cassé, fix ou retire

---

## ✅ Step 11 — Q-modularity stable

**Pourquoi** : confirme que la structure du code reste saine (couplage bas).

```bash
cd /home/sky/Bureau/MUNINN-
forge --modularity 2>&1 | head -5
```

**Expected output** :
```
==================================================
  MODULARITY — Newman-Girvan Q over import graph
==================================================
  Q = 0.67X (good — modules are well isolated (Q ≥ 0.30))
```

**🟢 Pass** : Q ≥ 0.30 (idéalement ≥ 0.60)
**🔴 Fail** : Q < 0.30 → on a dégradé la modularité avec les changes Phase D ; investigate

---

## ✅ Step 12 — Sign-off décision

Si tu as fait 1→11 et que TOUT est 🟢, alors :

```
PHASE D STATUS  : 4/5 chunks livrés, qualité prod
PYPI TESTPYPI   : muninn-memory 1.0.1 ✅
PYPI PROD       : Ready to upload via D.3
BUGS OPEN       : 0
TESTS           : 2561 active, 0 fail
Q-MODULARITY    : 0.67X
```

**Décision pour D.3 PyPI prod** :
- ✅ Tout vert ci-dessus → upload prod via `twine upload --repository pypi dist/*` (utilise token PyPI prod, pas TestPyPI)
- 🟠 1-2 warnings sans impact (genre flaky perf test isolé) → upload prod, monitor
- 🔴 1+ fail réel → fix avant d'uploader prod

**Si tu upload prod** :
1. `cd /home/sky/Bureau/MUNINN-`
2. `rm -rf build dist *.egg-info && python3 -m build`  ← rebuild from current main
3. `python3 -m twine upload --repository pypi dist/*`  ← lit `~/.pypirc` section `[pypi]` (token prod)
4. Vérif visuelle : https://pypi.org/project/muninn-memory/1.0.1/
5. Smoke test : `pip install muninn-memory==1.0.1` dans un autre venv vierge → `muninn --help` doit print welcome
6. Commit + push une dernière fois si tu mets à jour CHANGELOG / WINTER_TREE avec le statut "shipped to PyPI prod ✅"

---

## What if red — troubleshooting général

| Symptôme | Diagnostic | Fix |
|---|---|---|
| CI rouge sur D.x commits | Le step "Test Engine Commands" assume muninn status sans init | Le hotfix `dfe4b28` doit être dans HEAD ; si plus là, re-pull |
| `ModuleNotFoundError: tokenizer` en venv | engine/* pas shipped | Vérifie `[tool.setuptools.packages.find].include` contient `"engine*"` |
| `muninn status` auto-init dans site-packages | D.4 fix absent | Check muninn.py `_print_empty_repo_hint` présent |
| `mcp not installed` malgré `[mcp]` extra | Install bug ou cache pip | `pip install --force-reinstall 'muninn-memory[mcp]==1.0.1'` |
| Q-modularity < 0.30 | Refactor a créé du couplage | `forge --modularity --verbose` pour voir les communautés problématiques |
| Tests CI passent mais local fail | Différence d'environnement | Reproduis avec exact CI flags (cf step 2 ci-dessus) |

---

## Cleanup post-protocole

```bash
rm -rf /tmp/muninn_protocol_venv /tmp/muninn_protocol_empty
```
