# BATTLE PLAN — 2026-05-10 (CLOTURÉ matin — voir AFTERNOON pour la suite)

Audit final 4 agents mode seigneur dev (2026-05-09 soir).
**P1 + P2 EXÉCUTÉS ce matin** (`024da87` → `ecf1184`, 4 commits, 0 régression).
**P3 split muninn_tree.py 3929L → 2179L (-45%) LIVRÉ** (`96729ad` pré-split + `f17d34c` doctor + `2170a33` prune + `4d738c6` boot + `23a7974` cleanup, 5 commits, 0 régression).
**CI freezegun fix** (`abf4887`) — main HEAD vert.

→ Suite après-midi : `docs/BATTLE_PLAN_AFTERNOON_2026-05-10.md` (F1-F10).

---

## ✅ VRAIMENT FAIT, EN PRODUCTION (vérifié par 4 agents)

### Code shippé en 24h (45 commits sur main, dernier `f15459c`)

| Phase | Commits | Status | Preuve runtime |
|---|---|---|---|
| P0bis sécurité | 3 (607f1a7, 21b4cb3, 008f9c7) | ✅ EN PROD | `secure_perms()` ~50 sites, vault.py 15 sites |
| Migration forge | 4 (0d88508, d85d12c, 2770aa0, 8a9b7be) | ✅ EN PROD | PyPI binary 1.1.0, CI smoke 11 modules |
| Refactors F1-F6 | 8 commits | ✅ EN PROD | -130L muninn.main, +forge_metrics module |
| **H1** forge migration | `d6a5fc3` | ✅ EN PROD | -8156L (3 forge.py supprimés) |
| **H4.1** C12 wired | `a19081a` | ✅ EN PROD | permissions/slow/real-API gate |
| **H3.1** growth_stats | `a143830` | ✅ EN PROD | `muninn status` affiche "Growth: Concepts: 4777, Connections: 247860" |
| **H3.2+H3.3** zones CLI | `21606d8` | ✅ EN PROD | `muninn zones` affiche "12 detected" + 10 zones listées |
| **H4.2** forge_smoke CI | `f4304c2` | ✅ EN PROD | matrix 11 modules, 101 props PASS |
| **H5.1** retrieval xfail | `11b4bba` | ✅ EN PROD | `xfail` absent du fichier |
| **H2** forge_metrics → cube_live | `78ce4dd` | ⚪ EN PROD partiel | Helpers callables (test 17/17), émission Qt non vérifiable sans UI |
| **H5.2** sync_tls TLS-RST | `591fbe1` | ✅ EN PROD | `conn.unwrap()` présent, test_t1_9 PASS sans xfail |
| **H6.1-4** mycelium split | 5977772, df11508, 81eb654, 59bed03 | ✅ EN PROD | mycelium.py 3163→1415L, MRO 5 mixins clean |
| v3 audit easy wins | `c36ba40` | ✅ EN PROD | 12 docs archivés, scanner model fixé, deps bumped |
| v4 audit deep | `a7394e6` | ✅ EN PROD | Plan v4 documenté |
| **B1 BUG-091** fix complet | 83adeac, 2bb1ea5, 22baf4a, 7de6dee, a8d809c | ✅ EN PROD | muninn/* 7700→2982L (-4718L), 19 shims propres |
| Cleanup-1 archi | `74a9991` | ✅ EN PROD | Drift docs forge.py + provider fallback cube_live |
| v5 wrap | `f15459c` | ✅ EN PROD | Plan final v5 |
| **P3 split muninn_tree.py** | `96729ad` `f17d34c` `2170a33` `4d738c6` `23a7974` | ✅ EN PROD | 3929L → 2179L, +3 sous-modules doctor/prune/boot, 2332 PASS conservés |
| CI freezegun fix | `abf4887` | ✅ EN PROD | constraints.txt + ci.yml — débloqué les 4 CI rouges du matin |

### Métriques objectives mesurées (forge live + pytest)

| Indicateur | Valeur | Statut |
|---|---|---|
| Tests pytest run normal | **2332 PASS, 47 skipped, 0 fail, 0 xfail** | ✅ |
| Q-modularity | **0.662** (good ≥ 0.30) | ✅ |
| forge.py interne | **0** (PyPI single source) | ✅ |
| Fichiers byte-identiques engine/core ↔ muninn | **0** | ✅ B1 finished |
| Shims muninn/ propres | **19** | ✅ |
| BUG-091 status | **FIXED** post-B1 | ✅ |
| CI runs success consécutifs | 12+ | ✅ |
| Hooks installés | **9** (manifest sha256 9/9 OK) | ✅ |

---

## 🚨 DÉCOUVERTES CRITIQUES (2026-05-09 soir → ✅ TOUTES FIXÉES 2026-05-10 matin)

### ✅ CRIT-1 FIXED (`024da87`) — 10 commandes CLI débloquées

bootstrap/feed --history/ingest/bridge/trip + sync/sync status/doctor/init/push
marchent maintenant via `python -m muninn`. Fix : `sys.modules.pop` + force
`sys.path.remove/insert(0)` dans les 2 shims `muninn/mycelium.py` + `sync_backend.py`.

### ✅ CRIT-2 FIXED (`b1fc72f`) — 2 tests flaky temporels stabilisés

`test_tier1_a2.py` + `test_tier3_c1.py` désormais wrap par `freezegun` (déjà
installé v1.5.5). Plus de fail 50% en CI après minuit.

### ✅ CRIT-3 FIXED (`3b8c151`) — 3 mensonges doc résolus

CHANGELOG mycelium.py 3163 → 1415 (post-H6 split, 4 mixins listés).
BUGS.md contradiction interne BUG-091 résolue (0 "Status: OPEN" restant).
"_engine 4415L" clarifié = diff count, pas size.

### ✅ P2 FIXED (`ecf1184`) — 19 skips morts → asserts

test_chunk_a2/a3/a4/a8 cleanup. 23/23 PASS sur les fichiers concernés.

---

## 📜 HISTORIQUE DÉCOUVERTES (référence)

### CRIT-1 : 10 commandes CLI cassées en cold-start `python -m muninn`

**🚨 PRÉ-EXISTANT à B1** — vérifié par checkout sur tag `a7394e6` (pré-B1) : crash identique.

**Symptôme** : ImportError circular sur les shims `muninn/mycelium.py` et `muninn/sync_backend.py`. Le shim fait `from <name> import *` mais Python trouve déjà `<name>` dans `sys.modules` (le shim partially initialized) au lieu de `engine/core/<name>.py`.

**Commandes cassées** :
- Mycelium circular : `bootstrap`, `feed --history`, `ingest`, `bridge`, `trip` + warnings sur `boot`, `recall`
- Sync_backend circular : `sync`, `sync status`, `sync doctor`, `sync init`, `sync push`

**Pourquoi tests pytest passent** : `tests/conftest.py` preload les modules dans le bon ordre AVANT que le cycle puisse se déclencher. CLI cold-start n'a pas ce filet.

**Fix proposé** (30-45 min, à valider) :
Modifier `muninn/mycelium.py` (et `muninn/sync_backend.py`) pour pop self de sys.modules avant le `from import *` :
```python
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

# Critical: pop our partially-initialized self so 'from mycelium import *'
# resolves to engine/core/mycelium.py (not back to us, infinite cycle).
sys.modules.pop('mycelium', None)

from mycelium import *
from mycelium import (...)  # explicit privates
```

**Protocole de test reproductible** :
```bash
cd /tmp && rm -rf test_b && mkdir test_b
python -m muninn bootstrap /tmp/test_b 2>&1 | head -5
# AVANT fix : ImportError circular
# APRÈS fix : "=== MUNINN BOOTSTRAP: test_b ===" + processing
```

### CRIT-2 : 2 tests flaky temporels — fail après minuit

**Découvert pendant l'audit** (la date est passée à 2026-05-10 mid-session) :
- `tests/test_tier1_a2.py::test_a2_1_arithmetic` (line 34-45)
- `tests/test_tier3_c1.py::test_c1_3_below_threshold_untouched` (line 65-75)

**Symptôme** : utilisent `datetime.now()` au runtime + arithmetic sur `_days_ago(1)`. Quand le test tombe juste après minuit, delta = 2 jours au lieu de 1.

**Impact** : CI fail 50% du temps si run après 00h00.

**Fix proposé** (30 min) : utiliser `time-machine` ou monkeypatch `datetime.now` pour freezer à un epoch fixe.

**Protocole de test reproductible** :
```bash
pytest tests/test_tier1_a2.py::test_a2_1_arithmetic tests/test_tier3_c1.py::test_c1_3_below_threshold_untouched -v
# Run actuel après minuit : FAIL (B=0.6381 expected=0.5653, small=15.0 expected ~7)
# Run avant minuit : PASS
```

### CRIT-3 : 3 mensonges doc à corriger

| Doc | Ligne | Claim | Réel |
|---|---|---|---|
| CHANGELOG.md | 3 | `mycelium.py 3163` | **1415** (post-H6.4 split) |
| BUGS.md | 16 vs L448-491 | header dit "BUG-091 FIXED" | body dit "OPEN" en 2 endroits |
| BUGS.md | 16 | "_engine.py drift 4415L" | confond taille (2225L) vs diff count (4414) |

**Fix** (10 min sed + edits manuels) :
- CHANGELOG L3 : remplacer `mycelium.py 3163` par `mycelium.py 1415`
- BUGS.md : éditer L448-491 pour dire "[SUPERSEDED — see header L16, FIXED 2026-05-09]"
- BUGS.md L16 : reformuler "4415L diff < cap 5000" (pas la taille du fichier)

---

## 🟡 SKIPS MORTS À NETTOYER (cosmétique, 0 risque)

19 `pytest.skip("not yet implemented")` dans 4 fichiers — modules cités existent maintenant :
- `test_chunk_a2_mn_corruption.py` (2 skips)
- `test_chunk_a3_db_integrity.py` (5 skips)
- `test_chunk_a4_transcript_path.py` (7 skips)
- `test_chunk_a8_hook_logger.py` (5 skips)

Vérifié : tous les helpers (`_safe_read_mn`, `check_integrity`, `_validate_transcript_path`, `log_hook_event`) existent. **Run isolé : 23/23 passent en 0.71s, 0 skip déclenché**.

→ Code défensif mort, à supprimer (sed simple).

---

## ⚪ NON VÉRIFIABLE SANS LANCER L'UI Qt

- H2 émission `[forge] risk=...` dans terminal cube_live (Qt signal) — code path présent, helpers OK, mais `self.status.emit(...)` non testé auto

**Test manuel demain** :
```bash
python -m muninn ui  # ou équivalent qui lance Qt
# Dans le terminal cube_live, taper /reconstruct engine/core/cube_providers.py 112 0
# Attendu : voir "[forge] risk=0.464 (MOD) for engine/core/cube_providers.py" en orange
```

---

## 🐛 BUG OPEN — non bloquant prod (déjà documenté)

- **BUG-104** L12 BudgetMem chunk granularity. OFF par défaut → 0 impact prod. Fix = 4h.

---

## 🎯 ORDRE D'ATTAQUE — STATE 2026-05-10

### ✅ Priorité 1 + Priorité 2 — DONE (4 commits ce matin)
- `024da87` CRIT-1 circular imports → 10 cmd CLI débloquées
- `b1fc72f` CRIT-2 freezegun → 2 tests temporels stables
- `3b8c151` CRIT-3 doc sync → 0 mensonge restant
- `ecf1184` P2 → 19 skips morts → 19 asserts

**État** : 2332 PASS, 0 fail, 0 xfail, CLI 100% fonctionnelle.

---

## 🎯 P3 — Split `muninn_tree.py` 3929L (en cours)

**Inspection 2 agents 2026-05-10 matin** : GO confirmé. Pattern `cube.py`-style
(sub-modules + `from sub import *` à la fin), pas mixin. ~4h25 Sky-réel.

### 5 ACTIONS PRÉ-SPLIT (préparer le terrain, ~20 min)

Toutes ces actions sont SAFE, à faire dans l'ordre AVANT P3.1 :

1. **Tag rollback** : `git tag pre-P3-split-muninn_tree-2026-05-10`
2. **Pré-ajouter `muninn_tree_boot/prune/doctor` à `engine_only`** dans
   `tests/test_chunk_d11_shim_drift.py` (avec justification — calque
   pattern mycelium_meta/zones/activation/dream)
3. **Ajouter protection `sys.modules.setdefault('muninn_tree', sys.modules[__name__])`**
   à la fin de `engine/core/muninn_tree.py` (sans `from sub import *` encore,
   commit séparé low-risk)
4. **Update shim `muninn/muninn_tree.py`** avec protection CRIT-1 (sys.modules.pop
   + sys.path.remove/insert) — calque ce qui a été fait sur mycelium.py
5. **Run full pytest** — confirmer 2332 PASS avant de toucher quoi que ce soit

### CHUNK P3.1 — `doctor()` (lignes 3267-3548, 283L) — 30-40 min

**Risque : faible** (self-contained, 0 helpers à co-extraire).

**Plan d'extraction** :
1. Créer `engine/core/muninn_tree_doctor.py` :
   ```python
   from muninn_tree import _m, cleanup_tmp_files
   # + redéfinir _m localement si besoin (ModRef class, 5 lignes)

   def doctor(): ...   # déplacé depuis muninn_tree.py:3267-3548
   ```
2. Dans `muninn_tree.py` : ajouter `from muninn_tree_doctor import doctor` à la TOUTE FIN
3. Mirror `muninn/muninn_tree.py` shim : ajouter `from muninn_tree_doctor import doctor`
4. Retirer `("muninn_tree.py", "doctor")` de `DOCUMENTED_OVERSIZED_FUNCTIONS`
   dans `tests/test_brick20_architecture.py`
5. `forge --gen-props engine/core/muninn_tree_doctor.py` (BUG-102 destructive
   detector skip OK car `doctor` a print/side-effects)
6. Test : `pytest tests/test_doctor.py tests/test_chunk_b11_doctor_extensions.py tests/test_chunk_e2_helpers_wired.py -v`

**Tests touchés** (3) : test_doctor + test_chunk_b11 + test_chunk_e2.
Tous appellent `muninn.doctor()` ou `muninn_tree.doctor()` → re-export OK.

**Commit** : `refactor(P3.1): extract doctor() to muninn_tree_doctor.py (-283L)`

### CHUNK P3.2 — `prune()` + 3 helpers (lignes 2473-3211, ~580L) — 1h-1h15

**Risque : moyen** (couplage avec muninn_feed via `_m._sleep_consolidate` /
`_m._light_prune`).

**Co-extraire dans `muninn_tree_prune.py`** :
- `_sleep_consolidate` (L2473-2629, 161L) — appelé par prune() + muninn_feed.py:1318
- `_auto_backup_tree` (L2773-2794) — exclusif prune
- `_light_prune` (L2729-2770) — appelé par muninn_feed.py:1267 via `_m`
- `prune` (L2797-3211, 419L)

**Plan** :
1. Créer `engine/core/muninn_tree_prune.py` avec les 4 fonctions + imports
   (`from muninn_tree import _m, load_tree, save_tree, refresh_tree_metadata,
   _ebbinghaus_recall, _days_since, _atomic_text_write, _safe_read_mn, compute_hash`)
2. Dans `muninn_tree.py` : `from muninn_tree_prune import prune, _sleep_consolidate, _auto_backup_tree, _light_prune` à la fin
3. Mirror shim
4. **CRITICAL — étendre concat list** dans :
   - `tests/test_huginn_h1.py:166`
   - `tests/test_huginn_h2.py:143`
   - `tests/test_decay_in_prune.py:158`
   Ces tests font `chr(10).join(read_text(...))` sur les 4 fichiers historiques
   et grep `m_decay.decay()` / `dream(` / `trip(`. Ajouter `muninn_tree_prune.py`
   à la liste pour que le grep retrouve.
5. Forge --gen-props sur le nouveau module
6. Test : `pytest tests/test_biovectors_v9b.py tests/test_chunk_a2_mn_corruption.py tests/test_huginn_h1.py tests/test_huginn_h2.py tests/test_decay_in_prune.py tests/test_chunk_ex5_sleep_consolidate_wired.py tests/test_phase6_scale.py tests/test_phase7_intelligence.py -v`

**Tests touchés** (8 fichiers) — voir ci-dessus.

**Commit** : `refactor(P3.2): extract prune + _sleep_consolidate + _auto_backup_tree + _light_prune (-580L)`

### CHUNK P3.3 — `boot()` + 4 helpers (lignes 1089-3927, ~857L) — 2h-2h30

**Risque : élevé** (le monstre 656L + 4 helpers + cycles imports + 144 occurrences `_m.X`).

**Co-extraire dans `muninn_tree_boot.py`** :
- `_load_virtual_branches` (L1089-1202, 115L)
- `_load_relevant_sessions` (L3655-3706, 52L)
- `_surface_insights_for_boot` (L2716-2727, 10L)
- `_surface_known_errors` (L3813-3837, 24L)
- `boot` (L1204-1857, 656L)

**LAISSER dans muninn_tree.py core** :
- `_extract_error_fixes` (L3768) — appelé par muninn_feed.py via `_m`
- `_append_session_log` (L3708) — idem

**Plan** :
1. Créer `engine/core/muninn_tree_boot.py` :
   ```python
   from muninn_tree import (
       _m, BUDGET, load_tree, save_tree, read_node,
       _ebbinghaus_recall, _actr_activation, _tfidf_relevance,
       adaptive_boot_budget, _atomic_json_write,
       detect_session_mode, classify_session, predict_next,
       _extract_error_fixes, _append_session_log,
   )
   # 5 fonctions co-extraites + boot
   ```
2. Dans `muninn_tree.py` : `from muninn_tree_boot import boot, _load_virtual_branches, _surface_insights_for_boot, _surface_known_errors, _load_relevant_sessions` à la TOUTE FIN
3. Mirror shim
4. **CRITICAL — étendre concat list** dans `tests/test_huginn_h3.py:175,185`
   pour inclure `muninn_tree_boot.py`
5. **Vérifier qu'aucun test n'importe directement** `_load_virtual_branches`
   ou `_load_relevant_sessions` :
   `grep -rn "_load_virtual_branches\|_load_relevant_sessions" tests/`
6. **Confirmer ordre d'imports** : `from muninn_tree_boot import boot` DOIT
   être en TOUTE FIN de muninn_tree.py (après toutes les défs)
7. Forge --gen-props sur le nouveau module
8. Test : `pytest tests/test_biovectors_v11b.py tests/test_biovectors_v5a.py tests/test_biovectors_v8b.py tests/test_huginn_h3.py tests/test_chunk_e6_boot_integrity.py tests/test_ablation_vectors.py -v`

**Cycle Python** : pas de nouveau setdefault nécessaire si action #3 pré-split
faite (sys.modules.setdefault dans muninn_tree.py). Le proxy `_m` existe déjà
et résout via `sys.modules['muninn']`.

**Commit** : `refactor(P3.3): extract boot + _load_virtual_branches + _surface_* (-857L)`

### CHUNK P3.4 — Cleanup test_brick20 + props régénération (~30 min)

1. Retirer `"muninn_tree.py"` de `DOCUMENTED_OVERSIZED_MODULES` dans
   `test_brick20_architecture.py` (passé sous le seuil 2500L post-split)
2. Régénérer `tests/test_props_muninn_tree.py` complet via
   `forge --gen-props engine/core/muninn_tree.py` (le fichier core, pas les
   sous-modules — le props existe déjà avec 14 tests, à mettre à jour)
3. Run full pytest : `rm -rf .muninn && pytest tests/ -q ...` → cible 2332+ PASS
4. Run forge baseline : `forge --modularity` (cible Q ≥ 0.65)
5. Update CHANGELOG.md ligne 3 avec les nouvelles tailles fichiers

**Commit** : `refactor(P3.4): cleanup oversized refs + regen props post-split`

---

### POINTS DE GARDE communs aux 3 chunks

- [ ] Mirror dans `muninn/muninn_tree.py` shim après chaque chunk
- [ ] `__all__` de muninn_tree.py : **NE PAS retirer boot/prune/doctor**
      (sinon shim casse)
- [ ] Forge --gen-props sur chaque nouveau module
- [ ] Update `tests/test_brick20_architecture.py::DOCUMENTED_OVERSIZED_FUNCTIONS`
- [ ] Run `pytest tests/ -q` complet après chaque extraction (~120s, 2332 tests)
- [ ] `_m` proxy doit être importable depuis chaque sous-module
      (option 1: `from muninn_tree import _m`, option 2: redéfinir `_ModRef` localement)

### ESTIMATION TOTALE P3 (mode Sky-réel cohérent H6 hier)

| Chunk | Effort | Risque |
|---|---|---|
| Pré-split (5 actions) | 20 min | bas |
| P3.1 doctor | 30-40 min | bas |
| P3.2 prune + 3 helpers | 1h-1h15 | moyen |
| P3.3 boot + 4 helpers | 2h-2h30 | élevé |
| P3.4 cleanup + props | 30 min | bas |
| Buffer surprises | 30 min | — |
| **TOTAL** | **~4h25** | une après-midi |

À l'allure H6 d'hier (4 chunks × 30min = 2h), Sky peut atteindre 3h en flow.

---

### Priorité 4 — Reportée (gros chantiers + B2B prep)

- **Split cube_providers.py 2124L** par provider (Ollama/Claude/OpenAI/Mock). **3-4h focused**.
- **Wire `_hook_logger` dans 8 hooks** (compliance audit_log/edits_log/config_changes .jsonl). **2h**.
- **L9 prompt caching** (cache_control sur system prompt) → -50% coût Anthropic API. **1 jour**.

---

## 🔧 PROTOCOLE DE TEST QUOTIDIEN (à utiliser demain et après)

```bash
# Reset clean state
cd /home/sky/Bureau/MUNINN- && rm -rf .muninn

# Full pytest suite (mêmes flags que CI)
MUNINN_RUN_REAL_API_TESTS=0 MUNINN_RUN_REAL_LLM_TESTS=0 \
pytest tests/ -m "not slow" --tb=short -q \
  --ignore-glob='tests/test_ui_*.py' \
  --ignore=tests/eval_harness_chunk9.py \
  --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies

# Attendu : 2330-2335 passed, 44-47 skipped, 1 deselected, 0 fail
# Si > 3 écart sur passed → investiguer (peut être les 2 flaky temporels)

# Forge full cycle
forge --modularity        # Q ≥ 0.65 attendu
forge --carmack --weeks 4 | head -10  # top 5 risque
forge --locate            # "No failing tests" si suite verte

# CLI commandes essentielles
python -m muninn doctor   # ALL GREEN attendu
python -m muninn status memory/tree.json
python -m muninn zones    # 12 zones detected (si mycelium populé)
python -m muninn tree
```

---

## 🚦 STATUS GLOBAL

**Ce qui marche en prod** : 19/29 commandes CLI, tous les hooks, CI vert, mycelium split clean, forge chain, sécurité P0bis.

**Ce qui ne marche pas en cold-start CLI** : 10 commandes (mycelium write-path + sync entier) — fix 45 min.

**Doc honnête** : 3 mensonges identifiés, 15 min sed pour corriger.

**Verdict** : **66% CLI EN PROD réellement, 34% cassé en cold-start mais pas régression d'aujourd'hui**. Tu peux lever et fixer les P1 en 1.5h pour atteindre 100% CLI fonctionnelle.

Bonne nuit.
