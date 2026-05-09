# BATTLE PLAN — Audit complet du jour 2026-05-08

**Date** : 2026-05-08 (consolidé après 12 audits agents senior sur la journée)
**Statut** : 🔴 Plan de bataille définitif — consolide les Run 2, Run 3 et Run 4 (12 agents senior parallèles)
**Supersede** : `BATTLE_PLAN_AUDIT2_2026-05-08.md`, `CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md` (intégrés dans ce doc)

---

## §0 Résumé exécutif (2 minutes)

### Ce qui s'est passé aujourd'hui

3 vagues d'audit (4+4+4 agents = 12 agents senior parallèles) ont passé le repo MUNINN- au crible :
- **Run 2** : threading, perf, errors/observability, test quality
- **Run 3** : security, data integrity, codebase rot, CI/supply chain
- **Run 4** : honesty audit des 41 commits, deep code, test quality post-fix, CI runtime

J'ai poussé **41 commits** : Phase A (8/8) + Phase B (9/11) + Phase C (12/13) + Phase D (10/13) + 3 docs.

### La vérité no-bullshit après audit final

| Réalité | Chiffre |
|---|---|
| pytest aujourd'hui (full repo) | **6 failed**, 2349 passed, 16 skipped |
| Failures introduites par MES commits du jour | **4 sur 6** (régressions) |
| Chunks pure theater (effet 0 en prod) | **5/41** (D7, D9, D12, C12, D8) |
| Helpers shippés aujourd'hui sans aucun caller prod | **4** (health, purge_old_anomalies, log_engine_event, swallow) |
| Tests cosmétiques (smoke / source-scan / doc-only) | **50/197** (25%) |
| Tests skip via BUG-091 shim collisions | **30** |
| CI GitHub qui exécute pytest sur mes 197 tests | **0 ligne** — invisible |
| A8 hook logger réellement migré dans bridge_hook/muninn_feed | **0** (helpers shippés mais migration pas faite) |
| Note honnête | **~7/10** (pas 9/10 comme j'avais claim) |

### Le plan en 5 phases

| Phase | Effort | Quoi |
|---|---|---|
| **E** Réparations urgentes | ~2h Claude | 8 fixes : régressions + helpers à wirer |
| **F** CI / déploiement | ~15min Sky + 30min Claude | 4 items dont 2 yaml manual scope `workflow` |
| **G** Décisions Sky-pending | variable | watchdog.py / forge.py / _engine.py shim |
| **H** Durcir tests fragiles | ~1h30 Claude | C5 (0 asserts!), D9, B4, doc-only |
| **I** Dette pré-audit | 4-6h | BUG-104 L12, B6, D5 |

**Total Phase E + F = ~3h** transforme 50% du theater en valeur réelle. Note attendue : 7→8.5/10.

---

## §1 État réel après 41 commits — tableau honnête

Verdicts source : 4 agents Run 4 convergent + vérifications croisées.

### Phase A (8/8) — robuste

| # | Chunk | Hash | Verdict | Justification |
|---|---|---|---|---|
| A1 | L9 redact secrets `_llm_compress_chunk` | `290075d` | ✅ **SOLIDE** | Token `ghp_aB3xY9z...` envoyé verbatim pré-fix. Fix couvre tous callers L9. |
| A2 | UnicodeDecodeError handlers .mn | `eb29eb1` | ✅ **SOLIDE** | UnicodeDecodeError verbatim ligne 812 pré-fix. 4 sites couverts. |
| A3 | PRAGMA `check_integrity()` | `ad152d4` | 🟡 **OK_NOT_WIRED** | Helper marche. Auto-call seulement via `doctor()` (pas au boot CLI). Si Sky n'appelle pas doctor, corruption silencieuse. |
| A4 | transcript_path whitelist | `5858445` | ✅ **SOLIDE** | 7 tests vecteurs réalistes. |
| A5 | Lock SQLite reads (9 sites) | `af60c9d` | ✅ **SOLIDE** | 107 erreurs InterfaceError verbatim pré-fix. |
| A6 | Sentinel calibration | `840b3fb` | 🟡 **HONNÊTE-PARTIEL** | Hardening préventif. Le commit lui-même dit "exact prompts could not be reproduced". Bug live pas fixé avec certitude. |
| A7 | Hook integrity manifest + 0750 | `c4c237e` | 🟡 **TEST_FRAGILE** | Manifest committé. Permissions `chmod 0750` **ne survivent pas un git clone** (git ne tracke pas les perms). Sur fresh checkout, retour 0755. |
| A8 | Hook log rotation centralisé | `767d52c` | ✅ **SOLIDE** | Rotation testée + fallback stderr. 714 lignes archivées. |

### Phase B (9/11) — mixed

| # | Chunk | Hash | Verdict | Justification |
|---|---|---|---|---|
| B1 | save_tree hard-fail | `676a5eb` | ✅ **SOLIDE** | TimeoutError raise vraiment. |
| B2 | bridge_fast granular | `a1bfdac` | 🟡 **TEST_FRAGILE** | Test critique skip en isolation. Order-dependent. |
| B3 | Cache `_id_to_name` 9 sites | `ee9438d` | ✅ **SOLIDE** | Sites remplacés statiquement. |
| B4 | cleanup orphan .lock | `bb550d2` | 🟡 **FAIBLE** | 29% asserts comportementaux. Vérifie `exists()/not exists()` sans causalité. |
| B5 | cube_providers granular | `133bbcb` | 🟡 **SKIP_COMBO** | 4 tests pass isolation, skip combo (BUG-091). |
| B7 | autouse `_repo_path_isolate` | `5279a1d` | ✅ **SOLIDE** | Leak verbatim capturé pré-fix. |
| B8 | UNION ALL → single scan | `f216fc8` | 🟡 **SOURCE_SCAN_ONLY** | Test = `count("UNION ALL") <= 1`. Pas de bench réel. |
| B10 | TLS isinstance shim | `887b082` | ✅ **SOLIDE** | 1 test rouge → vert. 14/14 TLS pass. |
| B11 | doctor() extensions | `4369c66` | 🟡 **TESTS_FRAGILES** | Tests cherchent strings dans output, pas contrat. |
| **B6** | _REPO_PATH context manager | — | ⏸ **PENDING** | Gros refactor, risque > gain |
| **B9** | forge.gen_props refactor | — | ⏸ **PENDING SKY** | Sky débugge forge standalone |

### Phase C (12/13) — solide + 1 régression introduite

| # | Chunk | Hash | Verdict | Justification |
|---|---|---|---|---|
| C1 | constraints.txt pin | `b3e1bbc` | ✅ **SOLIDE** | tiktoken==0.12.0, anthropic==0.96.0. |
| C2 | load_tree schema | `6d618b8` | ✅ **SOLIDE** | 4 fails verbatim pré-fix. |
| **C3** | compress_file size guard 50MB | `abd5344` | 🔴 **REGRESSION_INTRODUCED** | Mon docstring `(CHUNK C3:` collisione avec test_tier3_c3 pattern → **3 tests cassés**. |
| C4 | retire PowerShell fallback | `d0bb210` | ✅ **SOLIDE** | Subprocess powershell verbatim capturé. |
| **C5** | isinstance(dict) | `6178911` | 🟡 **THEATER_LIGHT** | Bug réel mais **0 assert comportemental** dans le test. Juste try/pytest.fail. |
| C6 | .mn magic header CRC | `1dcdc7b` | ✅ **SOLIDE** | Round-trip + CRC + legacy. |
| C7 | scripts/backup_mycelium.py | `f45217f` | 🟡 **OK_NOT_WIRED** | Script marche. **Aucun cron**. Si Sky ne lance pas, backup reste 8j stale. |
| C8 | version single source | `6858f5f` | ✅ **SOLIDE** | importlib.metadata. |
| C9 | (N/A) | — | ⚪ Faux positif agent confirmé. |
| C10+C11 | doc env vars + README drift | `cdc1fee` | 🟡 **DOC_ONLY** | Tests scan strings dans docs. Maintenance-heavy si reformat. |
| **C12** | CI pytest yaml | `99ecc89` | 🔴 **THEATER** | Proposition seulement. 5/7 tests skip "until merge". 0 effet CI tant que Sky ne merge pas. |
| C13 | Dependabot config | `53f2ef5` | 🟡 **NON_VÉRIFIÉ** | Fichier créé. Sera-t-il activé par GitHub ? À voir Monday. |

### Phase D (10/13) — 1 régression + 3 theater

| # | Chunk | Hash | Verdict | Justification |
|---|---|---|---|---|
| D1 | 10 hypothesis property tests | `701a576` | ✅ **SOLIDE** | 95% asserts comportementaux. Premier test faible (`isinstance(out, str)`) mais 9 autres solides. |
| D2 | `_adj_index_json` lazy cache | `1f1255b` | ✅ **SOLIDE** | Cache + invalidation testés. |
| D3 | cube path safety | `6e9d5b3` | 🟡 **TEST_ONLY** | **Pas de fix de code**. Tests qui lockent comportement actuel. |
| D6 | .gitattributes LFS | `4fa2d27` | 🟡 **PRÉEMPTIF** | Routes futurs commits via LFS. **N'affecte PAS les 40MB PNG existants**. |
| **D7** | `purge_old_anomalies()` | `a4b4cc3` | 🔴 **THEATER** | Fonction existe. **0 caller en prod**. Test brick19 la flag dead. |
| **D8** | CI forge yaml | `bd78a22` | 🔴 **THEATER** | Proposition seulement. 3/6 tests skip. 0 effet CI. |
| **D9** | `swallow()` + `log_engine_event()` | `a78e796` | 🔴 **THEATER** | Helpers shippés. **0 caller en prod**. Le commit lui-même dit "Migration deferred". |
| D10 | drift audit `_engine.py` + version sync | `4068f5f` | ✅ **SOLIDE** | Surface parity locked, version synced. |
| D11 | anti-drift shim test 17 modules | `481d0ed` | ✅ **SOLIDE** | 18 tests, 1 skip documenté. |
| **D12** | `muninn_layers.health()` | `09a2fba` | 🔴 **THEATER** | Fonction existe. **0 caller en prod**. Test brick19 la flag dead. |
| **D4** | watchdog.py dead code | — | ⏸ **DEMANDER SKY** | 0 imports repo. Supprimer ou wire. |
| **D5** | naming standardisation | — | ⏸ **DÉPEND DE B6** | |

### Récapitulatif chiffré

| Catégorie | Count | % |
|---|---|---|
| ✅ SOLIDE | 22 | 54% |
| 🟡 OK_NOT_WIRED / FAIBLE / TEST_FRAGILE | 14 | 34% |
| 🔴 THEATER | 5 | 12% |
| 🔴 REGRESSION_INTRODUCED | 1 (C3) | 2% |

---

## §2 Régressions que J'AI introduites aujourd'hui

| # | Test cassé | Cause | Fix |
|---|---|---|---|
| R1 | `tests/test_tier3_c3.py::test_c3_2_code_has_threshold` | Mon `(CHUNK C3:` dans docstring `compress_file` matche le pattern `'C3:'` que ce test scanne | Renommer "CHUNK C3:" en quelque chose qui ne match pas (E1) |
| R2 | `tests/test_tier3_c3.py::test_c3_3_max_preloads` | Idem | E1 |
| R3 | `tests/test_tier3_c3.py::test_c3_5_budget_in_preload` | Idem | E1 |
| R4 | `tests/test_brick19_dead_code_audit.py::test_dead_code_set_matches_documented` | `health()` (D12) + `purge_old_anomalies()` (D7) sont publics et 0 caller → flagged "NEW dead candidates" | Soit wire (E4+E5) soit ajouter à `DOCUMENTED_IN_TREE_DEAD_CANDIDATES` (E2) |

**Pré-existants pas ma faute mais documentés** :
- `test_brick20_architecture::test_no_new_oversized_functions` — `forge.gen_props` >200L (B9 Sky-pending)
- `test_phase4_tls::TestTLSFactory::test_factory_tls_config` — déjà vert maintenant (B10 fix)

---

## §3 Phase E — Réparations urgentes (~2h Claude)

### E1 — Fix régression docstring C3 (5min, 3 tests rouges)

**File** : `engine/core/muninn_layers.py:1372`

**Code actuel** :
```python
"""Top-level compression entry point: read file, run full L0-L11 pipeline.

Pipeline order (Brick 6 wired L12 BudgetMem after secret redaction):
  1. Read file as UTF-8 (CHUNK C3: refuses files above the cap)
                                ^^^^^^^^^
                                pollue le pattern 'C3:' que test_tier3_c3 scanne
```

**Fix** : remplacer `(CHUNK C3:` par `(size cap, audit fix C3)` ou autre formulation qui ne contient pas `C3:`.

**Test** : `pytest tests/test_tier3_c3.py -q` doit passer.

### E2 — Fix régression dead code D7+D12 (20min)

**Choix A** (préféré) : Wire les helpers dans `doctor()` réellement, pas juste les exposer.

**Choix B** : Ajouter à `DOCUMENTED_IN_TREE_DEAD_CANDIDATES` dans `tests/test_brick19_dead_code_audit.py` avec commentaire "public API kept for external doctor extensions".

Fait avec choix A pour avoir la valeur réelle de D7+D12 (sinon ils restent du theater).

### E3 — Réparer hooks.sha256sum paths (10min)

**Problème** : `sha256sum -c .claude/hooks/hooks.sha256sum` échoue car les chemins du manifest sont relatifs (`bridge_hook.py`) mais sha256sum tourne depuis `/home/sky/Bureau/MUNINN-`.

**Fix** : régénérer le manifest depuis le bon cwd OU adapter le check. Préférence : `cd .claude/hooks && sha256sum *.py > hooks.sha256sum` (déjà la commande qui aurait dû être utilisée). Vérifier que les hooks_check_self() dans chaque hook fait bien `cd` avant `sha256sum -c`.

### E4 — Wire `health()` dans doctor() (10min)

**File** : `engine/core/muninn_tree.py::doctor()`

Ajouter check 18 :
```python
# Optional layers status (CHUNK D12)
try:
    from muninn_layers import health as _layers_health
    h = _layers_health()
    for k, v in h.items():
        if v:
            _ok(f"layer.{k} active")
        else:
            _warn(f"layer.{k} unavailable")
except Exception as e:
    _warn("layers.health() skipped", str(e)[:120])
```

### E5 — Wire `purge_old_anomalies()` dans doctor() (15min)

**File** : `engine/core/muninn_tree.py::doctor()`

Ajouter check 19 :
```python
# Anomalies log purge (CHUNK D7)
try:
    from cube_analysis import purge_old_anomalies
    log_path = Path.home() / ".muninn" / "anomalies.jsonl"
    if log_path.exists():
        n_purged = purge_old_anomalies(str(log_path), max_age_days=7)
        if n_purged > 0:
            _ok(f"anomalies purged: {n_purged} stale entries removed")
        else:
            _ok("anomalies.jsonl: no stale entries")
except Exception as e:
    _warn("anomalies purge skipped", str(e)[:120])
```

### E6 — Wire `check_integrity()` au boot (20min)

**File** : `engine/core/muninn.py` (CLI entry point ou `boot()`)

Ajouter au début de chaque commande qui touche le mycelium :
```python
# Boot health check (CHUNK A3+E6)
import os
if os.environ.get("MUNINN_SKIP_INTEGRITY") != "1":
    try:
        from mycelium_db import MyceliumDB
        db = MyceliumDB(_REPO_PATH / ".muninn" / "mycelium.db")
        ok, msg = db.check_integrity()
        if not ok:
            print(f"WARNING: mycelium.db integrity: {msg}", file=sys.stderr)
    except Exception:
        pass
```

OU plus simple : exporter via `muninn doctor --quick` qui ne fait que cette check au boot.

### E7 — Migrer hooks vers `swallow()`/`log_engine_event()` (30min)

**Files** : `.claude/hooks/bridge_hook.py`, `engine/core/muninn_feed.py`

**Sites à migrer** : tous les `try: ... except Exception: pass` dans bridge_hook + muninn_feed que A8 a laissés tels quels malgré la création de `_hook_logger`.

```python
# Avant :
try:
    risky_call()
except Exception:
    pass

# Après :
from _hook_logger import swallow
with swallow("bridge_hook", "context_name"):
    risky_call()
```

Compter les sites : `grep -n "except Exception" .claude/hooks/bridge_hook.py engine/core/muninn_feed.py` puis remplacer un par un.

### E8 — Cleanup memory/ ghost files (5min)

**Problème** : `git status` montre 7 fichiers en `D` (deleted) qui sont sur disque mais marked deleted dans l'index :
```
D memory/b00.mn
D memory/b01.mn
D memory/b03.mn
D memory/b04.mn
D memory/b05.mn
D memory/root.mn
D memory/tree.json
```

**Fix** : décider — soit `git rm` pour confirmer la suppression (ils sont déjà migrés vers `.muninn/tree/`), soit `git checkout HEAD -- memory/` pour les remettre.

Préférence : `git rm` car le TREE_DIR a migré vers `.muninn/tree/` (CHUNK BUG-091/recurrence du 2026-05-08 matin).

---

## §4 Phase F — CI / déploiement (Sky 15min + Claude 30min)

### F1 — MANUAL Sky : merger `docs/CI_PROPOSED_C12.md` (5min)

**Action Sky** : copier le yaml de `docs/CI_PROPOSED_C12.md` dans `.github/workflows/ci.yml`. Token avec scope `workflow` requis (l'agent token ne l'a pas).

**Effet** : les 197 test_chunk_*.py passent enfin en CI. Régression destructive ne passe plus silencieusement.

### F2 — MANUAL Sky : merger `docs/CI_PROPOSED_D8.md` (5min)

**Action Sky** : ajouter le job `forge_smoke` au yaml CI.

**Effet** : RULE 5 (forge après chaque module) enforced en CI au lieu de juste discipline manuelle.

### F3 — Cron `backup_mycelium.py` (5min)

**Action Sky** : `crontab -e` puis ajouter :
```cron
0 2 * * * /home/sky/.pyenv/versions/3.13.13/bin/python /home/sky/Bureau/MUNINN-/scripts/backup_mycelium.py --keep 14
```

**Effet** : C7 vraiment fonctionnel. Backup quotidien rotaté 14j.

### F4 — BUG-091 architectural fix (2-4h, Claude)

**Problème** : 30 tests skip via `BUG-091 shim collision`. Pas un bug du shim — fragilité d'ordre d'import.

**Pistes** :
- Standardiser tous les test_chunk_*.py sur `importlib.util.spec_from_file_location` avec nom unique (déjà utilisé par A3, A5, B3 partiel).
- OU forcer un sys.path setup dans `tests/conftest.py` qui garantit l'ordre.
- OU enfin réduire `muninn/_engine.py` à un vrai shim (D10 follow-up, déplace G3 vers F4).

**Décision** : tester si conftest.py fix règle 80% des skips. Si oui, on garde le shim pattern. Sinon, G3 obligatoire.

---

## §5 Phase G — Décisions Sky-pending

| # | Item | Effort | Décision attendue |
|---|---|---|---|
| **G1** | `watchdog.py` (66L engine + 57L shim) — 0 imports | 30min suppression / 1h wire | Supprimer (mort total) ou wire vers cron Windows ? |
| **G2** | `forge.gen_props()` refactor < 200 lignes | 1h | Toi tu débugges la version standalone — quand on touche la copie engine/core ? |
| **G3** | `muninn/_engine.py` (2100L) reduce to shim | 3-5h | Plan dans `docs/D10_DRIFT_AUDIT.md`. Risque pour 80+ test imports `from muninn._engine import X`. |

---

## §6 Phase H — Durcir les tests cosmétiques (~1h30)

### H1 — `test_chunk_c5` : 0 asserts comportementaux (30min)

**Code actuel** :
```python
def test_watchdog_handles_list_payload(...):
    try:
        wd.main()
    except AttributeError as e:
        pytest.fail(f"watchdog.main() crashed on list payload: {e}")
    # ❌ Pas un seul assert. Si main() ne crash pas mais retourne nimporte quoi, test pass.
```

**Fix** : capturer le return / l'effet de bord et asserter :
```python
def test_watchdog_handles_list_payload(...):
    # Mock subprocess so main() does no real work
    captured = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: captured.append(a))
    wd.main()
    # Behavioral assert: list payload must result in 0 subprocess calls
    assert captured == [], f"List payload triggered {len(captured)} subprocess calls"
```

Idem les 6 tests du fichier.

### H2 — `test_chunk_d9::swallow_clean_block_no_log` strict (10min)

**Code actuel** :
```python
assert not log.exists() or log.read_text() == ""
```

**Fix** : strict — pas de OR-faible :
```python
if log.exists():
    assert log.read_text() == ""
```

### H3 — `test_chunk_b4` causalité (20min)

Ajouter assert que `cleanup_tmp_files` retourne le BON `n` (pas juste >= 0) :
```python
n = mt.cleanup_tmp_files()
assert n == 3, f"expected 3 removed (a.lock, b.lock, c.tmp), got {n}"
# ET vérifier que les 3 fichiers ont disparu
for f in (a_lock, b_lock, c_tmp):
    assert not f.exists()
# ET vérifier qu'un 4e fichier non-aged est encore là (causalité)
assert recent_lock.exists()
```

### H4 — Décider sort des tests doc-only (30min)

`test_chunk_c10_c11_doc_drift`, `test_chunk_c13_dependabot`, `test_chunk_d6_gitattributes` — ces tests scan des fichiers `.md` / `.yml` / `.gitattributes` à la recherche de strings.

**Choix** :
- **A** : durcir (parser le yaml/md vs grep, asserter sur structure pas string)
- **B** : accepter comme drift detectors et documenter la fragilité

Préférence : **B** + ajouter un commentaire de tête expliquant que reformat sémantiquement-équivalent peut casser ces tests. C'est OK si on le sait.

---

## §7 Phase I — Dette pré-audit (4-6h)

| # | Item | Effort | Note |
|---|---|---|---|
| **I1** | BUG-104 L12 BudgetMem chunk granularity | 3-4h | OPEN dans `BUGS.md`. Refactor structural. |
| **I2** | B6 `_REPO_PATH` context manager | 1h | Skipped en Phase B (gros risque). |
| **I3** | D5 naming `repo_path/_REPO_PATH/MUNINN_REPO` | 30min | Dépend de I2. |

---

## §8 Priorités absolues (ordre d'attaque)

1. **E1** — fix régression docstring C3 (5min, 3 tests rouges) ← 1ère action
2. **E2** — fix régression dead code D7+D12 (20min, 1 test rouge)
3. **F1** — Sky merge yaml C12 (5min Sky, 197 tests passent enfin en CI)
4. **F2** — Sky merge yaml D8 (5min Sky, forge gating en CI)
5. **E3** — hooks.sha256sum paths (10min, A7 vraiment fonctionnel)
6. **E6** — check_integrity au boot (20min, A3 vraiment protège)
7. **E7** — migrer hooks vers _hook_logger (30min, A8+D9 vraiment effets)
8. **E4+E5** — wire health()/purge() dans doctor (25min, D7+D12 vraiment utiles)
9. **F3** — cron backup_mycelium (5min Sky, C7 vraiment protège)
10. **E8** — cleanup memory/ ghost files (5min)

**Total Phase E (1-2,5-10) + F1-F3 = ~2h30 Claude + ~15min Sky.**

Après ça : **~50% du theater devient réel**. Note attendue : 7/10 → 8.5/10.

---

## §9 Méthodologie no-bullshit pour la Phase E

Avant de claim qu'un chunk est "fait", je dois montrer :

1. **Test failed pré-fix** (preuve du bug) — output verbatim de pytest
2. **Test pass post-fix** — output verbatim de pytest
3. **Vérification COMPORTEMENTALE**, pas juste `hasattr` ou `isinstance`
4. **Vérification que le caller utilise vraiment le helper** — `grep -rn "<helper>" engine/ muninn/` > 1 résultat hors-test

C'est exactement ce qui m'a manqué sur D7, D9, D12 aujourd'hui. Tests d'existence ≠ valeur prod.

---

## §10 Sources verbatim

| Run | Agents | Total durée | Outputs |
|---|---|---|---|
| **Run 2** | A1 threading, A2 perf, A3 errors/obs, A4 test quality | ~10min | ~18K tokens |
| **Run 3** | A5 security, A6 data integrity, A7 codebase rot, A8 CI/supply | ~12min | ~20K tokens |
| **Run 4** | A9 honesty, A10 deep code, A11 test quality, A12 CI runtime | ~10min | ~22K tokens |

12 agents senior parallèles. Chaque ligne du tableau §1 est traçable à un `file:line` cité par un agent. Outputs complets dans le transcript de session 2026-05-08 (jsonl).

---

## §11 Engagement honnête

Je ne re-claim plus 9/10 ou "Phase X complete" sans :
- 0 régression de tests pré-existants
- 0 helper dormant (chaque chunk shippé a au moins 1 caller en prod)
- pytest --tb=no donne 0 failed (pas juste "ignore les pré-existants")
- CI GitHub voit les tests (pas juste local)

Si je ne peux pas tenir ces 4 conditions sur un chunk, je le marque **OK_NOT_WIRED** ou **THEATER** dans le verdict, pas SOLIDE.
