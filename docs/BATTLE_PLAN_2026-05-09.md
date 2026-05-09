# BATTLE PLAN — 2026-05-09

**Auteur** : Claude (sky-master) après deep audit 5 agents + cross-vérification 3 agents indépendants
**Contexte** : prod-grade requis (Sky vend Muninn à des boîtes tech).
**Statut commit en tête** : `3b70836 fix(P0): chmod 0o600 on every Muninn-managed sensitive file` — incomplet.

---

## ⚡ Verdict de l'audit du jour

Le P0 d'hier (chmod 0o600 sur les fichiers `~/.muninn/*`) a **oublié 3 fichiers critiques** :

| Fichier | Sites manqués | Type fichier non-protégé |
|---------|--------------|--------------------------|
| `engine/core/vault.py` | **15** sites | salt, ciphertext, plaintext, verify hash |
| `muninn/_engine.py` | **7** sites | `.mn`, root.mn, hooks générés, settings patch |
| `engine/core/muninn.py` | **6** sites | idem (BUG-091 dual tree) |

Total : **28 sites de création** où un user externe sur la même machine peut lire des secrets.

Cross-vérifié indépendamment par 3 agents qui n'ont pas vu mon analyse → tous CONFIRMENT VRAI.

---

## 📋 Phase 0 — Production-blockers (~1h)

### P0bis-1 : `vault.py` secure_perms (CRITICAL, 30min)

**Sites à patcher** (engine/core/vault.py) : 181, 185, 192, 278, 315, 337, 349, 391, 424, 433 + 5 sites secondaires
**Pattern** : ajouter `secure_perms(<path>)` immédiatement après chaque `write_bytes/write_text`.
**Pourquoi CRITICAL** : le salt + verify hash exposent la dérivation de clé. Brute-force PBKDF2 offline possible si user lit ces fichiers.
**Test** : `tests/test_chunk_p0bis_vault_perms.py` — 3 tests behavioural (salt, verify, ciphertext en 0o600 après init/lock/rekey).

### P0bis-2 : `_engine.py` (muninn + engine/core) secure_perms (HIGH, 30min)

**Sites à patcher** :
- `muninn/_engine.py` : 508, 637, 714, 915, 1052, 1226, 1520
- `engine/core/muninn.py` : 437, 649, 850, 987, 1161, 1486

**BUG-091 dual tree** : mirror exact entre les deux fichiers.
**Pattern** : `secure_perms(path)` après chaque `write_text`.
**Pourquoi HIGH** : root.mn = transcript compressé du projet (= contexte work confidentiel). Hooks générés contiennent les sentinelles secrets installées chez Sky.
**Test** : `tests/test_chunk_p0bis_engine_perms.py` — 3 tests behavioural (root.mn, bridge_hook.py, .mn temp).

---

## 📋 Phase 1 — Logging rotation (~30min)

### P0bis-3 : `RotatingFileHandler` rotation perms (P1)

**Site** : `engine/core/_hook_logger.py:50`
**Bug** : le `secure_perms(log_path)` du commit P0 ne couvre QUE le fichier initial. Quand `RotatingFileHandler.doRollover()` rename `hook_errors.log` → `hook_errors.log.1` et crée un nouveau fichier, ce dernier hérite du umask 022 → 0o644.
**Fix** : subclasse `RotatingFileHandler` avec un override `doRollover` qui chmod 0o600 sur tous les `.1/.2/.3`.
**Test** : forcer 2 rotations + vérifier perms.

---

## 📋 Phase 2 — Dette identifiée (~2h)

| # | Item | Effort | File:Line |
|---|------|--------|-----------|
| **P2** | BUG-104 b255 truncate à 150 lignes | 30min | tree.json node b255 |
| **P4** | `forge.gen_props` split <200L | 1h | engine/core/forge.py:gen_props |
| **D1** | `cube.db` chemin relatif → `Path().resolve()` | 10min | cube_analysis.py:932 |
| **D2** | SECRET_PATTERNS dupe (BUG-091) | 20min | muninn/_engine.py:83 |

---

## 📋 Phase 3 — Quality / robustness (~3h, optionnel)

| # | Item | Effort | Severity |
|---|------|--------|----------|
| Q1 | `_LOGGERS` LRU eviction (cache unbounded) | 30min | P3 |
| Q2 | `_concept_cache` invalidation (mycelium_db) | 30min | P2 |
| Q3 | `@pytest.mark.slow` annotation tests >5s | 1h | qualité CI |
| Q4 | Tests directs `vault.py` + `sync_tls.py` (0 actuel) | 3h | coverage crypto |
| Q5 | `_LOGGERS` cleanup à shutdown | 20min | P3 |

**Note** : Q4 (tests crypto) recommande pytest-cov pour mesurer. C'est un chunk dédié pour plus tard, **pas dans cette journée**.

---

## 📋 Phase 4 — Forge v1.1.0 branchement (CHUNK séparé, gros)

**Statut** : cousin pc1 en train de release v1.1.0 (3 features : `--paths-to-mutate`, `--fast-deep`, `--modularity`).
**À faire APRÈS Phase 0-3** :
- Pull v1.1.0 depuis sky1241/forge
- Décider stratégie : `pip install forge-shield` vs copier `forge.py` dans `engine/core/`
- Migrer les invocations `python forge.py` → `forge` dans hooks/CI/tests MUNINN-
- Porter les flags MUNINN-spécifiques restants (`--fast-deep` déjà porté côté public, `--robustness` renommé `--modularity` côté public)
- Créer `.forge/config.json` MUNINN-spécifique avec les knobs voulus

**Effort estimé** : 4-6h, dépend de combien de sites invoquent forge dans MUNINN-. Faut d'abord audit dédié branchement.

---

## 🎯 Ordre d'exécution recommandé

```
Aujourd'hui (≈3h30 essential) :
  ├─ Phase 0 P0bis-1 vault         [30min] — CRITICAL
  ├─ Phase 0 P0bis-2 _engine.py    [30min] — HIGH
  ├─ Phase 1 P0bis-3 rotation      [30min] — P1
  ├─ Phase 2 P2 b255 truncate      [30min] — dette
  ├─ Phase 2 P4 forge.gen_props    [60min] — dette
  └─ Push CI run vert              [10min]

Demain ou plus tard :
  ├─ Phase 3 Q1-Q5                  [3h]   — quality polish
  └─ Phase 4 Forge v1.1.0 branche   [4-6h] — quand cousin a fini
```

---

## 🔬 Cross-vérification — anti-hallucination

Les 5 agents de la 1re passe ont identifié 25+ findings. La 2e passe (3 agents indépendants) a vérifié les 3 plus critiques :

| Finding | Agent 1 | Agent 2 | Agent 3 | Verdict cross-checké |
|---------|---------|---------|---------|---------------------|
| vault.py 0 secure_perms (15 sites) | VRAI CRITICAL | — | — | ✅ |
| _engine.py 0 secure_perms (13 sites mirror) | — | VRAI HIGH | — | ✅ |
| RotatingFileHandler rotation 0o644 | — | — | VRAI P1 | ✅ |
| _LOGGERS unbounded | — | — | VRAI P3 | ✅ |
| tree_lock soft warning | — | — | VRAI mais INTENTIONNEL B1 | nuance ✅ |

**Verdict sur le faux positif identifié dans la 1re passe** :
- ❌ "_sleep_consolidate _ncd NameError" (agent 2 1re passe) — faux positif. `_m._ncd` existe via `import muninn_tree as _m`. Confirmé par grep direct.

---

## ⚠️ Règles d'hygiène pour aujourd'hui (CLAUDE.md MUNINN_RULES)

1. **RULE 4 anti-bullshit** : aucune claim "c'est fait" / "test passe" sans output verbatim 3 lignes au-dessus.
2. **RULE 1 paths universels** : pas de hardcode `/home/sky/Bureau/MUNINN-`. Pattern A (Path(__file__)) ou Pattern B (arg).
3. **RULE 5 forge** : après chaque modif `engine/core/X.py`, lancer forge. (Note : forge interne MUNINN- en partie cassé, attendre v1.1.0 pour ré-utiliser.)
4. **BUG-091** : toute modif dans `engine/core/X.py` mirroré dans `muninn/X.py` immédiatement.
5. **CI vert avant chunk suivant** : push après chaque phase, watch CI, fail = stop et fix.

---

## 🚦 Critère de done pour la journée

- [x] Phase 0 P0bis-1 vault — 15 sites + 3 tests + CI vert
- [x] Phase 0 P0bis-2 _engine — 13 sites mirror + 3 tests + CI vert
- [x] Phase 1 P0bis-3 rotation — subclass + 1 test + CI vert
- [x] Phase 2 P2 b255 — truncate + bench L12 stable + CI vert
- [x] Phase 2 P4 forge.gen_props — split + brick20 test vert + CI vert
- [ ] Phase 3 — selon temps restant
- [ ] Phase 4 — chunk séparé après forge v1.1.0
