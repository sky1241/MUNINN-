# BATTLE PLAN AUDIT 3 — Mode No-Bullshit

**Date** : 2026-05-08 (post-Phase A+B+C+D)
**Source** : 4 agents senior parallèles (honesty / deep code / test quality / CI runtime)
**Statut** : 🔴 Audit honnête après les 41 commits du jour. Pas de complaisance.

---

## §0 Verdict global no-bullshit

**Note honnête** : ~7/10 (pas 9/10 comme j'avais claim avant l'audit).

**Réalité brute mesurée** :
- pytest tests/ : **6 failed**, 2349 passed, 16 skipped
- **4 failed sur 6 = MA FAUTE** (régressions introduites par mes commits aujourd'hui)
- 5 chunks pure theater (effet 0 en prod)
- 4 helpers DEAD shippés aujourd'hui (jamais callés en prod)
- 30 tests skip via BUG-091 collisions (couverture order-dependent)
- CI GitHub n'exécute **PAS** pytest sur les 38 test_chunk_*.py — 0 visibilité
- A8 hook logger centralised : helpers shippés mais **PAS migrés** dans bridge_hook + muninn_feed

**Score réel par axe** :
- Solides (vraiment changent quelque chose) : 28/41 (68%)
- OK mais pas wired (effet 0 si caller absent) : 6/41 (15%)
- Theater pur (dead code + propositions yaml) : 5/41 (12%)
- Fragiles (test order-dependent, skip-heavy) : 2/41 (5%)

**4 régressions introduites aujourd'hui** :
1-3. `test_tier3_c3.py` × 3 — mon docstring `(CHUNK C3:` pollue le pattern `'C3:'`
4. `test_brick19_dead_code_audit` — `health()` (D12) + `purge_old_anomalies()` (D7) flagged dead

---

## §1 Convergence des 4 agents — top findings

### 5 chunks PURE THEATER (effet 0 en prod)

| Chunk | Issue | Source agent |
|---|---|---|
| **D12** `health()` | Définie, public, **0 caller en prod**. Test seul prouve son existence. | A1, A2 |
| **D7** `purge_old_anomalies()` | Idem — fonction shippée, jamais appelée. | A1, A2 |
| **D9** `swallow()` + `log_engine_event()` | Helpers shippés. **0 migration** des callers existants (bridge_hook + muninn_feed). Docstring example uniquement. | A1, A2 |
| **C12** CI pytest yaml | Proposition seulement. **5/7 tests skip** "until merge". 0 effet sur CI réel. | A1, A4 |
| **D8** CI forge yaml | Idem. Proposition seulement. | A1, A4 |

### Helpers définis aujourd'hui mais NON-WIRED en production

| Helper | File | Real callers (excl. tests) |
|---|---|---|
| `health()` | `engine/core/muninn_layers.py:43` | **0** |
| `purge_old_anomalies()` | `engine/core/cube_analysis.py:1726` | **0** |
| `log_engine_event()` | `engine/core/_hook_logger.py:122` | **0** |
| `swallow()` | `engine/core/_hook_logger.py:146` | **0** |
| `check_integrity()` (A3) | `engine/core/mycelium_db.py` | **1** (doctor() seulement, pas auto-boot) |
| `backup_mycelium()` (C7) | `scripts/backup_mycelium.py` | **0** crons (CLI manuelle uniquement) |

### CI GitHub — la grosse découverte de l'audit

**Le `.github/workflows/ci.yml` actuel fait 5 steps sans pytest** :
- validate tree.json
- smoke tests engine/core via subprocess
- mycelium simulate
- benchmark
- feed parsing

**0 ligne `pytest tests/`**. Mes 197 test_chunk_*.py qui passent localement = **invisibles au CI**. Une régression destructive sur main passe silencieusement.

C12 et D8 yaml propositions dans `docs/CI_PROPOSED_*.md` — non appliqués (token agent sans `workflow` scope).

### Tests cosmétiques — 50/197 sont theater (25%)

**Top 10 selon agent 3** :
1. **test_chunk_c5** — 6 tests, **0 assert comportemental**. Juste `try/except: pytest.fail(...)` sans valider le retour.
2. **test_chunk_d9::swallow_clean_block_no_log** — assert OR-faible (`not log.exists() or log.read_text() == ""`)
3. **test_chunk_b4** — 29% comportemental, juste `exists()` / `not exists()` sans causalité
4. **test_chunk_c12** — 5/7 skip (`pytest.skip("workflow change not merged yet")`)
5. **test_chunk_a4** — skip si helper absent (esquive le test critique)
6. **test_chunk_d2::speedup_on_repeat** — skip silencieusement si timing pas favorable
7. **test_chunk_c8::no_hardcoded_version_string** — source grep, pas runtime
8. **test_chunk_d6** — 5 tests source-scan sur fichier texte
9. **test_chunk_b8::no_double_union_all** — source scan, pas exécution SQL
10. **test_chunk_c12::proposed_doc_exists** — vérifie un fichier .md existe

### BUG-091 résiduel — 30 tests skip via shim collision

Les shims `muninn/X.py` re-exportent `from X import *` (bare). Quand un test charge `muninn_tree` via path engine/core puis un autre fait `import muninn.X`, circular import.

**30 tests skip** avec motif "BUG-091 shim collision". Pas un bug du shim — fragilité du setup d'import.

### Code mort confirmé

- `engine/core/watchdog.py` (66 lignes) + `muninn/watchdog.py` (57 lignes) : **0 imports** du repo. Mort complet.
- `compress_file` post-C3 : cap 50 MB OK mais lit toujours en RAM. Streaming refactor (Phase D parking lot) pas implémenté.

---

## §2 Plan de bataille — 4 phases

### Phase E — RÉPARATIONS URGENTES (mes régressions + helpers à wirer)

| # | Action | Effort | Pourquoi maintenant |
|---|---|---|---|
| **E1** | Renommer "CHUNK C3:" dans docstring `compress_file` (collisione avec test_tier3_c3 pattern) | 5min | 3 tests rouges, ma faute |
| **E2** | Wire `health()` + `purge_old_anomalies()` dans `doctor()` ou ajouter à `DOCUMENTED_IN_TREE_DEAD_CANDIDATES` | 20min | 1 test rouge (brick19), 2 helpers dormants |
| **E3** | Réparer `hooks.sha256sum` paths (chemins relatifs vs cwd) | 10min | check d'intégrité actuellement broken |
| **E4** | Wire `health()` dans `doctor()` (en plus de E2 — pour vrai usage) | 10min | D12 effet 0 sans ça |
| **E5** | Wire `purge_old_anomalies()` dans `doctor()` ou auto-boot | 15min | D7 effet 0 sans ça |
| **E6** | Wire `check_integrity()` au boot CLI (pas juste doctor) | 20min | A3 effet 0 si Sky n'appelle pas doctor |
| **E7** | Migrer `bridge_hook._log_hook_error` + `muninn_feed._log_sync_error` vers `swallow()`/`log_engine_event()` | 30min | A8 + D9 effet 0 sans migration |
| **E8** | `git rm memory/b*.mn memory/tree.json memory/root.mn` (fichiers fantômes en `D` depuis BUG-091) | 5min | bruit constant en `git status` |

**Total Phase E : ~2h**. Tout ça transforme du theater en valeur réelle.

### Phase F — CI / DÉPLOIEMENT (le vrai trou noir)

| # | Action | Qui | Effort |
|---|---|---|---|
| **F1** | Merger `docs/CI_PROPOSED_C12.md` dans `.github/workflows/ci.yml` | **SKY** (token avec workflow scope) | 5min |
| **F2** | Merger `docs/CI_PROPOSED_D8.md` (forge_smoke job) | **SKY** | 5min |
| **F3** | `crontab -e` → `0 2 * * * python scripts/backup_mycelium.py --keep 14` | **SKY** | 5min |
| **F4** | BUG-091 architectural fix : 30 tests skip via shim circular | reste à designer | 2-4h |

**Sans F1+F2, mes 197 test_chunk_*.py sont morts dans le CI.** C'est l'action n°1 prioritaire.

### Phase G — NETTOYAGE / DÉCISIONS SKY-PENDING

| # | Action | Effort | Status |
|---|---|---|---|
| **G1** | `watchdog.py` mort complet — supprimer ou wire | 30min | DEMANDER SKY |
| **G2** | `forge.gen_props` refactor <200 lignes | 1h | DEMANDER SKY (forge standalone debug en cours) |
| **G3** | `muninn/_engine.py` (2100 LOC) reduce to shim | 3-5h | Plan dans `docs/D10_DRIFT_AUDIT.md` |

### Phase H — TESTS QUI MENTENT À DURCIR

| # | Action | Effort |
|---|---|---|
| **H1** | `test_chunk_c5` — ajouter `assert wd.main() ...` ou capture return value (0 asserts actuellement) | 30min |
| **H2** | `test_chunk_d9::swallow_clean_block_no_log` — remplacer OR-faible par strict | 10min |
| **H3** | `test_chunk_b4` — ajouter assertions de causalité (pourquoi supprimé, pas juste "exists") | 20min |
| **H4** | Décider sort des 5 doc-only tests (C13, D6, C10/C11) — durcir ou accepter comme drift detectors | 30min |

### Phase I — DETTE PRÉ-AUDIT (déjà documentée)

| # | Action | Effort | Note |
|---|---|---|---|
| **I1** | BUG-104 L12 BudgetMem chunk granularity | 3-4h | OPEN dans BUGS.md |
| **I2** | B6 `_REPO_PATH` context manager | 1h | Skipped en Phase B |
| **I3** | D5 naming standardisation `repo_path/_REPO_PATH/MUNINN_REPO` | 30min | Dépend de I2 |

---

## §3 Priorités absolues (ordre d'attaque)

1. **E1** — fix régression docstring C3 (5min, 3 tests rouges)
2. **E2** — fix régression dead code D7+D12 (20min, 1 test rouge)
3. **F1** — Sky merge yaml C12 (5min, 197 tests passent enfin en CI)
4. **F2** — Sky merge yaml D8 (5min, forge gating en CI)
5. **E3** — hooks.sha256sum paths (10min, A7 vraiment fonctionnel)
6. **E6** — check_integrity au boot (20min, A3 vraiment protège)
7. **E7** — migrate hooks vers _hook_logger (30min, A8+D9 vraiment effets)
8. **E4+E5** — wire health()/purge() dans doctor (25min, D7+D12 vraiment utiles)
9. **F3** — cron backup_mycelium (5min, C7 vraiment protège)
10. **E8** — cleanup memory/ ghost files (5min)

**Total Phase E + F (1-3 + 5-10) : ~2h30 de Claude + ~15min de Sky.**

Après ça : **~50% du theater devient réel**. Note attendue : 7/10 → 8.5/10.

---

## §4 Ce que je promets de faire vs Sky

- Je peux faire E1 → E8, H1 → H4 maintenant (TDD chunk par chunk).
- F1, F2, F3 nécessitent SKY (token workflow scope OU crontab utilisateur).
- G1, G2 demandent confirmation SKY.
- I1 est un gros refactor (3-4h) — décider si on l'attaque ou pas.

**Honesty rule** : avant de claim qu'un chunk est "fait", je dois montrer un test qui :
1. Failed pré-fix (preuve du bug)
2. Passe post-fix avec output verbatim
3. Vérifie le COMPORTEMENT (pas juste l'existence d'un attribut)

C'est ce qui m'a manqué sur D7, D9, D12 aujourd'hui — j'avais des tests "existence" qui passaient mais 0 caller en prod = 0 valeur.

---

## §5 Sources verbatim

Output complet des 4 agents dans le transcript de session 2026-05-08 (jsonl). Chaque ligne du tableau §1 est traçable à un `file:line` cité par un agent.

Agents :
- A1 honesty audit (136s, ~5K tokens)
- A2 deep code (164s, ~5K tokens)
- A3 test quality (92s, ~6K tokens)
- A4 CI runtime (205s, ~4K tokens)
