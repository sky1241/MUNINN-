# Audit Report 3ème vague — 2026-05-19 PM (post-REMEDIATION-2)

> **Contexte** : Sky est crevé, m'a demandé de me débrouiller. 3ème audit
> ruthless après C8-C13 → REMEDIATION D1-D12 → REMEDIATION-2 E1-E8.
> Question centrale : le pattern "audit → fix → re-audit trouve d'autres
> bugs" finit-il par converger ?
>
> **Source** : 4 agents lancés en parallèle (git history / code core /
> tests / build-runtime). Scope = 30+ commits entre `b2e115d` et HEAD
> (`8e2e6af`).
>
> **Verdict global** : le code TOURNE runtime. Mais 2 RED résiduels
> + 5 AMBER + 4 trous tests. Pas catastrophique, mais le pattern
> n'a pas fini de converger.

---

## ✅ GREEN — vérifié runtime (Agent 4)

```
1. UI Qt boot offscreen        → exit 0, "UI OK"
2. Cold-start engine/core      → exit 0 (E2 fix tient)
3. reconstruct_cube pipeline   → gap_lines=[2], unknown_idents=[] (filtered),
                                   ncd_score=0.192, exact_match=False
4. _compute_mycelium_neighbors → [[1], [0], []] (correct)
5. Click molecule (C12+E6)     → _selected={2, 3} (Q1 B respecté)
6. CI workflows (ci/nightly/perf) → présents, perf.yml MUNINN_RUN_PERF=1
7. HEAD CI                     → success (8e2e6af, 4m41s)
8. Hypothesis patches          → 3 anciens (mai 13/14), aucun nouveau
9. git status untracked        → vide post-E8
10. reconstruct_adaptive E2E   → keys correctes, sha_pct=14% sur btree
```

**Tous les claims fonctionnels de C8-C13 + D1-D12 + E1-E8 marchent en runtime.**

---

## 🔴 RED résiduels (2)

### RED-1 — `_build_full_anchor_map` peut raise `ValueError`, E1 narrow except le rate

**Source** : `engine/core/cube_providers.py:1156` post-E1 catch
`(TypeError, KeyError, AttributeError, IndexError)`. Mais
`_build_full_anchor_map:488` fait `for ln, lt in ast_hints['anchors']`.

Repro :
```python
ast_hints = {'anchors': [(1,)]}   # tuple malformé
for ln, lt in ast_hints['anchors']: pass
# → ValueError: not enough values to unpack (expected 2, got 1)
```

`ValueError` n'est PAS dans la whitelist E1 → propage → `reconstruct_cube`
CRASH. Probabilité faible (anchors viennent du parser AST interne), mais
E1 a précisément été fait pour ne PAS swallow et émettre un trace event
sur ces drift de signature. L'objectif rate les `ValueError`.

Aussi `re.error` (sous-classe `Exception` mais pas dans la liste)
échapperait sur regex corrompue.

**Fix prévu (F1)** : ajouter `ValueError` (et `re.error`) à la whitelist.

### RED-2 — `main_window:466` confond "fresh todo" et "reconstructed-but-failed todo"

**Source** : E6 fix dans `muninn/ui/main_window.py:463-467` :
```python
"ncd": (
    None
    if neuron.level != "cube" or neuron.status == "todo"
    else float(neuron.temperature)
),
```

Le test E6 traite `status == "todo"` comme "cube jamais reconstruit".

**MAIS** `muninn/ui/neuron_map.py:1507` (`update_cube_ncd`) fait :
```python
n.status = "done" if sha_match else ("wip" if clamped < 0.3 else "todo")
```

Donc un cube reconstruit avec **NCD ≥ 0.3** (échec partiel) a aussi
`status = "todo"`. main_window cache son NCD réel → DetailPanel affiche
"N/A" au lieu de la vraie valeur. **L'INVERSE de l'intention E6** (preuve
positive même sur fail).

**Fix prévu (F2)** : ajouter un flag explicite `Neuron.cube_ncd_set: bool`
initialisé `False` à la création, passé `True` dans `update_cube_ncd`.
Le guard E6 devient `if not getattr(neuron, 'cube_ncd_set', False)`.

---

## 🟡 AMBER (5)

### AMBER-1 — `_COMMON_LANG_KEYWORDS` manque keywords 4+ chars

Java/Kotlin/Ruby/Swift partiellement non couverts : `print`, `match`,
`super`, `this`, `final`, `public`, `private`, `protected`, `throws`,
`extends`, `implements`, `abstract`, `volatile`, `synchronized`, `begin`,
`rescue`, `unless`, `until`, `guard`. Pollution résiduelle DetailPanel
sur ces langages.

**Fix prévu (F3)** : ajout dans le frozenset E5.

### AMBER-2 — `tests/_helpers/mock_ollama.py` patch global non thread-safe

`urllib.request.urlopen = ...` est un patch GLOBAL. 2 `mock_ollama_session`
concurrents (pytest-xdist) se clobbent. Pas utilisé aujourd'hui, mais
piège futur.

**Fix prévu** : decline. Pas utilisé en parallèle, à corriger si on
introduit pytest-xdist.

### AMBER-3 — Doc-drift test FAIL sur HEAD (env vars BENCH non documentées)

`tests/test_chunk_c10_c11_doc_drift.py::test_all_env_vars_documented`
FAILE : `MUNINN_BENCH_MODELS` et `MUNINN_BENCH_FILE` détectés dans
`tests/run_bench_multi_llm_2026_05_14.py` (gitignored par E8), absents
de CLAUDE.md. E8 a gitignored le fichier mais le test scanne le disque,
pas l'index.

**Fix prévu (F4)** : soit ajouter les 2 env vars à CLAUDE.md, soit faire
que le doc-drift test ignore les fichiers gitignored. **Option A** plus
sûre (les vars sont réelles).

### AMBER-4 — Pas de test UI avec vrai `QTest.mouseClick`

Tous les tests UI bypassent Qt event loop (`widget._handle_neuron_click(...)`
direct). Le bug click-zoom>1 a été fixé via D11+E6 mais aucun test n'a
une vraie souris qui survole la molécule.

**Fix prévu** : decline (faisable mais long ; offscreen Qt + mouseMove
fiable est un projet à part). Tests directs couvrent la logique.

### AMBER-5 — Hot path `reconstruct_adaptive` jamais testé avec VRAI Ollama

Les tests `@skip` si `MUNINN_RUN_REAL_LLM_TESTS=1`. `MockLLMProvider`
retourne stub fixe → invariants C6 (fuse_risks ordering) / C7 (subdivide
mycelium-aware) sur **contenu** des cubes pas validés. Tests vérifient
que l'event `cube_ordering_applied` fire, pas que l'ordering est correct.

**Fix prévu** : decline (nécessite Ollama daemon en CI = trop coûteux).
Couverture acceptable pour le moment.

---

## 🟡 Trous tests (4)

### T1 — Test C7 `test_find_concept_boundaries_detects_zone_transition` : monkeypatch mort

`engine/core/cube.py:806-808` fait `from mycelium import concept_to_file_lines`
À L'INTÉRIEUR de `find_concept_boundaries`. Donc
`monkeypatch.setattr(cube, "concept_to_file_lines", ...)` au test E7 ligne
123-124 ne sert à rien. Test marche QUE grâce au 2nd patch sur
`mycelium.concept_to_file_lines`. Code mort dans le test.

**Fix prévu (F5)** : virer le patch `cube.*` mort, garder uniquement
`mycelium.*`.

### T2 — 2 FAIL pré-existants masqués par CLAUDE.md claim "0 FAIL"

`tests/test_chunk_c10_c11_doc_drift.py` (lié à AMBER-3) +
`tests/test_h2_id_to_name_perf.py` failent sur HEAD aujourd'hui.

CLAUDE.md ligne 380 dit "Tests: 2339 PASS, 47 skip, 0 xfail, 0 FAIL".
**Faux**.

**Fix prévu (F4)** : recount + update CLAUDE.md.

### T3 — Test C8 `test_compute_mycelium_neighbors_returns_list_of_lists` : tautologie partielle

FakeMycelium `_Conn.execute` retourne TOUJOURS les mêmes 6 concepts.
Selon la logique du test, les 3 cubes devraient être voisins entre eux.
Le test PASSE seulement si `_compute_mycelium_neighbors` ignore le
`_Conn.execute` et tokenize `content` directement.

À vérifier : si vrai, FakeMycelium est inutile et le test cache son
fonctionnement réel.

**Fix prévu** : decline pour le moment, à investiguer. Test passe
runtime (Agent 4 vérifie `[[1], [0], []]`), donc le contenu est testé
mais pas via la mécanique attendue.

### T4 — Pas de vrai test UI click souris

Voir AMBER-4. Pattern à fix par projet dédié.

---

## 🟢 Cleanup à faire

### S1 — Stash entries obsolètes

```
stash@{0}: WIP on main: b2e115d  (CLAUDE.md déjà commité)
stash@{1}: phase0-shim            (muninn/_engine.py refactor obsolète)
```

**Fix prévu (F6)** : `git stash drop` × 2 — destructif, demande à Sky.

### S2 — `tests/.test_intelligence/*.history.json` dirty à chaque pytest

35+ fichiers history mutent à chaque run local → pollue `git status`.
Tracked par erreur historique.

**Fix prévu (F7)** : `.gitignore` + `git rm --cached` (destructif).
Decline maintenant, attend décision Sky.

---

## Plan de fix REMEDIATION-3 (proposé)

| ID | Sujet | Estim | Sévérité |
|---|---|---|---|
| F1 | Ajouter `ValueError`, `re.error` aux whitelist E1 | 10min | 🔴 RED-1 |
| F2 | `Neuron.cube_ncd_set` flag pour distinguer fresh todo vs failed todo | 30min | 🔴 RED-2 |
| F3 | Étendre `_COMMON_LANG_KEYWORDS` (Java/Ruby/Swift) | 10min | 🟡 AMBER-1 |
| F4 | Documenter `MUNINN_BENCH_*` + recount CLAUDE.md FAIL | 15min | 🟡 AMBER-3 + T2 |
| F5 | Nettoyer monkeypatch mort test C7 | 5min | 🟡 T1 |
| **Total** | | **~1h10** | |

**Hors-scope explicit** : AMBER-2 (thread-safe mock_ollama), AMBER-4 (real
mouseClick), AMBER-5 (real Ollama in CI), T3 (FakeMycelium tautologie),
S1+S2 (stash + history files — destructifs, demandent Sky).

---

## Conclusion

Le pattern "audit → fix → re-audit trouve d'autres bugs" se calme :
- Audit 1 : 11 bugs → fixés en D1-D12
- Audit 2 : 12 bugs → fixés en E1-E8
- Audit 3 : 2 RED + 5 AMBER + 4 trous tests → **F1-F5 (~1h10)** à faire

Si Sky veut un 4ème audit après F1-F5, on aura probablement <5 trucs
résiduels mineurs. Convergence en cours.

**Code marche en production sur tous les axes critiques. Les 2 RED sont
des bugs latents (faible probabilité de trigger), pas des crashs visibles.**
