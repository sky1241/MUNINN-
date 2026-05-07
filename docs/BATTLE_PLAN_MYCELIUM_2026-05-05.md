# PLAN DE BATAILLE — MYCÉLIUM MUNINN

**Date** : 2026-05-05
**Auteur** : Sky + Claude (audit 4+4+3 agents, 3 passes, validation live finale)
**Statut** : 🟢 PRODUCTION FONCTIONNELLE — bugs mineurs identifiés, pas urgent

> ⚠️ **NOTE D'HONNÊTETÉ** : Les versions précédentes de ce document affirmaient
> que le mycélium était "🔴 PRODUCTION DÉGRADÉE" avec 3 root causes critiques.
> **C'était faux.** La validation live (§2) a invalidé 2 des 3 bugs revendiqués.
> Le mycélium fonctionne. Les agents ont sur-interprété des artefacts de tests.
> Voir §1 Mea culpa pour la chronologie complète.

---

## 0. RÉSUMÉ EXÉCUTIF (60 secondes)

Le mycélium projet de Muninn **fonctionne**. La DB SQLite reçoit des writes
en continu, les hooks Claude Code sont câblés et actifs, la sync vers le
méta tourne. Le rythme variable d'écriture (964 edges le 23 avr → 17 aujourd'hui)
reflète l'activité réelle de Sky, pas un bug.

Les bugs identifiés sont **réels mais non-critiques** : 4 swallow-exceptions
qui masquent les crashes (visibilité), 1 guard inversé sur `check_disk_space`,
des tables annexes vides (tombstones, edge_zones, sync_log côté projet) et
54% des tests qui sont des stubs `assert isinstance`.

**Budget total recommandé** : 4h pour améliorer la visibilité et l'audit trail,
pas urgent.

---

## 1. MEA CULPA — chronologie des audits et invalidations

### Tour 1 — Audit "ultra-profond" (4 agents)
**Conclusion erronée** : "Le mycélium projet est en mort silencieuse depuis le commit `2afebaa` 'yikes' du 2026-04-24. observe()/save()/sync_to_meta() ne persistent rien."

**Erreurs commises** :
- Agent a affirmé "DELTA edges: 0 après save()" sans vérifier que sa query SQL
  utilisait les bonnes colonnes (`a_id` au lieu de `a`).
- Agent a vu `sync_to_meta()` retourner 34118 mais méta inchangée → conclu
  "ment". En réalité : `ON CONFLICT DO UPDATE` standard, comportement attendu
  de la déduplication.
- Agent a interprété la chute de 964→12 edges/jour comme un bug, sans corréler
  avec l'activité Claude Code de Sky (transcripts par jour).

### Tour 2 — Investigation 3 agents
**Conclusion erronée** : "3 root causes en cascade : settings.json invalide,
sqlite3 isolation_level autocommit, hook stdin tty exit 1."

**Erreurs commises** :
- Agent 1 a vu `[{"hooks": [...]}]` dans settings.json et conclu "structure
  imbriquée invalide". **C'est en réalité le format CORRECT** documenté de
  Claude Code (le wrapper `{"hooks": [...]}` permet les matchers).
- Agent 2 a affirmé "isolation_level='' → transactions désactivées → 0 edges
  écrites". **Test live invalide** : `m.observe()+m.save()` écrit bien des
  edges. La query SQL de validation utilisait des colonnes inexistantes.
- Agent 3 a affirmé "hook exit 1 sur stdin tty". **Code de sortie réel** : 0,
  pas 1. Mais l'effet pratique (no-op silencieux) est correct.

### Tour 3 — Validation live (commandes réelles, sorties verbatim)
```
m.observe(['live_test_2026_05_05_alpha', 'beta', 'gamma']); m.save()
BEFORE: n_edges=20390, max_last_seen=2316
AFTER:  n_edges=20393, max_last_seen=2316
DELTA edges: +3 ✅
live_test concepts created: 3 ✅
live_test edges in DB: 3 ✅
```

**Verdict final** : observe() écrit, save() persiste, sync_to_meta() sync.
Le mycélium fonctionne.

**Leçon** : RULE 4 ABSOLUTE de CLAUDE.md — pas de claim sans output frais.
J'ai laissé 7 agents successifs construire un narrative cohérent sans valider
chaque étape en live. Erreur classique : preuves circulaires entre agents.

---

## 2. ÉTAT RÉEL VALIDÉ EN LIVE

### 2.1 — DB projet active

```bash
$ sqlite3 .muninn/mycelium.db "SELECT COUNT(*), MAX(last_seen) FROM edges;"
20390|2316  # 20,390 edges, dernier write aujourd'hui (2316 = 2026-05-05)
```

### 2.2 — Distribution récente
```
2311 (30 avr) : 49 edges
2312 (1 mai)  : 42 edges
2315 (4 mai)  : 3 edges
2316 (5 mai)  : 17 edges
```
Variabilité **= activité Claude Code de Sky**, pas un bug.

### 2.3 — Hooks actifs (preuve directe)
Pendant la session de cet audit, les hooks ont produit des outputs visibles :
```
[MUNINN SENTINEL] High-entropy string detected — possible password or key.
[MYCELIUM BRIDGE] opened -> ide_opened_file, battleplan_scanner...
```
→ `UserPromptSubmit` hook fonctionne, donc `bridge_hook.py` est correctement
câblé via le settings.json prétendument "invalide".

### 2.4 — Pipeline feed manuel (T3 — avec stdin JSON)
```
echo '{"transcript_path": "/dev/null", "hook_event_name": "SessionEnd",
       "cwd": "/home/sky/Bureau/MUNINN-"}' | python muninn.py feed --repo .
→ MUNINN SessionEnd: processing null for MUNINN-
→ MUNINN AUTO-PRUNE: 200 branches > 150, running light prune
→ MUNINN FEED: 0 messages -> mycelium (MUNINN-)
→ MUNINN SYNC: 20393 connections -> meta-mycelium
EXIT_CODE=0
```

### 2.5 — Schéma SQLite réel (pour les futurs audits)
```sql
CREATE TABLE edges (
    a INTEGER NOT NULL,           -- ⚠️ pas a_id
    b INTEGER NOT NULL,           -- ⚠️ pas b_id
    count INTEGER NOT NULL DEFAULT 0,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL,
    PRIMARY KEY (a, b)
) WITHOUT ROWID;
```
Toute query qui utilise `a_id`/`b_id` retournera 0 silencieusement.

---

## 3. VRAIS BUGS IDENTIFIÉS (mineurs/moyens, non-bloquants)

### Bug réel #1 — Swallow-exceptions silencieuses (4 emplacements)

| Fichier:ligne | Effet |
|---|---|
| [.claude/hooks/bridge_hook.py:74](.claude/hooks/bridge_hook.py#L74) | JSON parse error → exit 0 silencieux |
| [.claude/hooks/bridge_hook.py:110](.claude/hooks/bridge_hook.py#L110) | `clamp_chained_commands()` crash → output unclamped silencieux |
| [.claude/hooks/bridge_hook.py:113-114](.claude/hooks/bridge_hook.py#L113) | Crash bridge_fast → exit 0 sans output |
| [engine/core/muninn_feed.py:1204](engine/core/muninn_feed.py#L1204) | sync_to_meta crash dans `finally` → swallowed |

**Impact** : un crash silencieux ne se voit pas. Pas critique mais opaque.

### Bug réel #2 — Guard inversé `check_disk_space`

[engine/core/sync_backend.py:33](engine/core/sync_backend.py#L33)
```python
except (OSError, AttributeError):
    return True  # ← bug : assume OK sur erreur
```

**Impact** : si `shutil.disk_usage()` plante (NAS offline, perm denied), le
sync procède quand même. Risque faible de corruption méta DB.

### Bug réel #3 — Tables annexes vides côté projet

| Table | Projet | Méta | Cause |
|---|---|---|---|
| `tombstones` | 0 | 0 | `decay()` ne crée pas de tombstones (record_tombstone existe mais jamais appelé) |
| `edge_zones` | 0 | 7,239,665 | `federated=False` par défaut → tagging zones jamais déclenché côté projet |
| `sync_log` | 0 | 53 | `log_sync()` appelé côté méta seulement (best-effort `try/except: pass`) |

**Impact** : pas d'audit trail local. Pas de soft-delete. Asymétrie projet/méta.
Cosmétique pour les ops actuels.

### Bug réel #4 — Tests stubs `assert isinstance` (54%)

[tests/test_bugfix_mycelium.py](tests/test_bugfix_mycelium.py) — 14 tests sur 26 sont :
```python
def test_dream_returns_list():
    assert isinstance(m.dream(), list)  # stub
```

[tests/test_props_mycelium_db.py](tests/test_props_mycelium_db.py) — try/except qui swallow :
```python
try:
    date_to_days(arbitrary_text)
except (ValueError, TypeError, ...):
    pass  # any error is "OK" — anti-pattern
```

**Impact** : fausse impression de couverture. `_prune_weakest()` n'a aucun
test dédié.

---

## 4. PLAN DE BATAILLE (court, réaliste)

### P1 — Logger les 4 swallow-exceptions (30 min)
**Pattern à appliquer** : remplacer `except Exception: pass` par log dans
`~/.muninn/hook_errors.log` avec timestamp + traceback. Préserver `exit 0`
pour ne pas casser les hooks Claude Code.

**Fichiers** :
- `.claude/hooks/bridge_hook.py:74,110,113-114`
- `engine/core/muninn_feed.py:1204`

**Critère de victoire** :
```bash
# Forcer un crash, vérifier le log
echo 'BAD JSON' | python .claude/hooks/bridge_hook.py
tail -3 ~/.muninn/hook_errors.log
# Doit montrer: timestamp + JSONDecodeError + traceback
```

### P2 — Inverser le guard `check_disk_space` (5 min)
**Fichier** : [engine/core/sync_backend.py:33](engine/core/sync_backend.py#L33)
```python
except (OSError, AttributeError):
    return False  # AVANT: True
```

**Critère** : forge sur sync_backend passe sans falsifying example.

### P3 — Brancher `tombstones` dans `decay()` (1h)
**Fichier** : [engine/core/mycelium.py](engine/core/mycelium.py) `def decay()`

Pour chaque edge supprimée par decay, appeler
`self._db.record_tombstone(a, b, reason="decay")` AVANT le delete.

**Critère** :
```python
m._db.upsert_connection(a="old_a", b="old_b", count=1, last_seen=0)
n = m.decay(half_life_days=30)
assert len(m._db.get_tombstones()) >= n
```

### P4 — Renforcer 14 tests stubs (2h)
**Cible** : remplacer `assert isinstance(x, dict)` par assertions sur valeurs.

Exemples de transformations :
```python
# AVANT
def test_decay_returns_int():
    assert isinstance(m.decay(), int)

# APRÈS
def test_decay_removes_old_edges():
    m._db.upsert_connection("old_a", "old_b", count=1, last_seen=0)
    n = m.decay(half_life_days=30)
    assert n >= 1
    assert not m._db.has_connection("old_a", "old_b")
```

Ajouter test dédié `_prune_weakest()`.

### P5 (optionnel) — `federated=True` auto si meta_db existe (30 min)

[engine/core/mycelium.py](engine/core/mycelium.py) `__init__` :
```python
def __init__(self, repo_root, federated=None):
    if federated is None:
        meta_db = Path.home() / ".muninn" / "meta_mycelium.db"
        federated = meta_db.exists()
```

**Critère** : `SELECT COUNT(*) FROM edge_zones` > 0 côté projet après une
session.

---

## 5. CRITÈRES DE VICTOIRE

Le mycélium est "amélioré" (pas "réparé" — il marche déjà) quand :

1. ✅ Aucun `except Exception: pass` dans bridge_hook.py / muninn_feed.py /
   sync_backend.py (sans replacement par log)
2. ✅ `~/.muninn/hook_errors.log` existe et collecte les crashes
3. ✅ `SELECT COUNT(*) FROM tombstones` > 0 après un `decay()` manuel
4. ✅ Aucun test `assert isinstance(x, T)` sans assertion sémantique en plus
5. ✅ Forge property tests sur mycelium.py / mycelium_db.py / sync_backend.py
   passent
6. ✅ (P5 opt) `SELECT COUNT(*) FROM edge_zones` > 0 côté projet

---

## 6. RISQUES

- **Risque P1** : un log trop verbeux peut grossir `hook_errors.log` rapidement.
  **Mitigation** : rotation au-delà de 10 MB, ou format minimal (1 ligne par
  erreur, pas de traceback complet).
- **Risque P3** : les tombstones grossissent indéfiniment si `cleanup_old_tombstones()`
  n'est pas appelé périodiquement. **Mitigation** : appeler dans le hook
  SessionEnd, age > 60j.
- **Risque P5** : `federated=True` double l'écriture (zones par edge) → +200MB
  DB projet sur le long terme. **Mitigation** : guard sur `count > 1M edges`.

---

## 7. NOTES POUR LE PROCHAIN CLAUDE QUI REPREND

Si tu lis ce document après une nouvelle session :

### 7.1 Avant de claim quoi que ce soit, valider en live
**Commande de vérification rapide** :
```bash
cd /home/sky/Bureau/MUNINN-

# Snapshot DB
sqlite3 .muninn/mycelium.db "SELECT COUNT(*), MAX(last_seen) FROM edges;"

# Test write
python -c "
from engine.core.mycelium import Mycelium
m = Mycelium('.')
m.observe(['probe_$(date +%s)_a', 'probe_$(date +%s)_b'])
m.save()
"

# Snapshot DB après
sqlite3 .muninn/mycelium.db "SELECT COUNT(*), MAX(last_seen) FROM edges;"
```
Si `COUNT(*)` augmente, le mycélium est vivant.

### 7.2 Schéma SQLite — colonnes correctes
```sql
edges:    (a, b, count, first_seen, last_seen)  -- pas a_id/b_id
concepts: (id, name)
fusions:  (a, b, ...)
edge_zones: (a, b, zone)
tombstones: (a, b, deleted_at, reason)
sync_log: (id, direction, started_at, finished_at, status, ...)
```
Toute query SQL avec `a_id`/`b_id` est cassée silencieusement.

### 7.3 NE PAS faire
- Ne pas amender les commits passés (RULE 4 ABSOLUTE)
- Ne pas faire `git push --force` sans confirmation Sky (RULE 2)
- Ne pas afficher de tokens même placeholders (RULE 3)
- Ne pas hardcode de paths absolus dans le code engine (RULE 1)
- Ne pas claim "le bug est fixé" sans output sqlite3 prouvant le fix (RULE 4)

### 7.4 DOIT faire
- Forge après modif de mycelium.py / mycelium_db.py / muninn_feed.py (RULE 5)
- Backup `.muninn/mycelium.db` avant toute manip
- Tester en live AVANT de croire un agent qui claim un bug
- Si plusieurs agents convergent sur un narrative, **valider chaque étape
  individuellement** — les preuves circulaires sont le piège classique

### 7.5 Repos.json pollution (à nettoyer un jour)
`/home/sky/.muninn/repos.json` contient des entrées de tests pytest
(`fake_repo`, `test_repo`) qui ont fui dans la fédération. Pas critique mais
sale.

### 7.6 COUSIN_PROMPT_2026-05-01.md contient un nombre fabriqué
"5 925 766 edges" mentionné dans le doc → faux. Vrais chiffres :
- Projet : 20,393 edges (2026-05-05)
- Méta : 7,239,665 edges (2026-05-05)
À corriger lors de la prochaine touche du COUSIN_PROMPT.

---

**FIN DU PLAN DE BATAILLE**

Sky, le mycélium marche. Ce qu'il faut c'est de la visibilité (P1), de la
robustesse (P2-P3) et des vrais tests (P4). Pas une réparation d'urgence.
