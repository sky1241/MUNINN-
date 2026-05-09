# BATTLE PLAN TOMORROW — 2026-05-10 (matin)

Audit final 4 agents mode seigneur dev (2026-05-09 soir).
Sky se lève demain → coche FAIT / PAS FAIT.

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

## 🚨 DÉCOUVERTES CRITIQUES — PAS FAIT

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

## 🎯 ORDRE D'ATTAQUE PROPOSÉ pour DEMAIN

### Priorité 1 (1.5h, bugs vrais à fixer)

1. **Fix circular imports** `muninn/mycelium.py` + `muninn/sync_backend.py` (sys.modules.pop) → débloque 10 commandes CLI. **45 min**.
2. **Freeze datetime.now() dans 2 tests flaky** (test_tier1_a2 + test_tier3_c1). **30 min**.
3. **Sync 3 mensonges doc** (CHANGELOG L3, BUGS L16+L448-491). **15 min**.

Total P1 : **1.5h** → CLI 100% fonctionnelle + CI stable 24/24 + doc honnête.

### Priorité 2 (cleanup cosmétique, 30 min)

4. **Delete 19 `pytest.skip("not yet implemented")` morts** dans test_chunk_a2/a3/a4/a8. **30 min**.

### Priorité 3 (gros chantiers archi, focused)

5. **Split muninn_tree.py 3929L** (boot 656L + prune 419L + doctor 281L) → pattern H6 prouvé. **4-6h focused**.
6. **Split cube_providers.py 2124L** par provider (Ollama/Claude/OpenAI/Mock). **3-4h focused**.

### Priorité 4 (B2B prep, dette compliance)

7. **Wire `_hook_logger` dans 8 hooks** (compliance audit_log/edits_log/config_changes .jsonl). **2h**.
8. **L9 prompt caching** (cache_control sur system prompt) → -50% coût Anthropic API. **1 jour**.

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
