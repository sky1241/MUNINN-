# BUG: meta_mycelium.db ne se sync plus depuis le 17 mars 2026

## Symptome
- `~/.muninn/meta_mycelium.db` derniere modification: 2026-03-17 01:24
- Aujourd'hui: 2026-03-25. 8 jours sans sync.
- Le mycelium local (`.muninn/mycelium.db`) est a jour (modifie aujourd'hui).
- Le meta n'est PAS a jour.

## Diagnostic

### Ou le sync est appele (2 endroits)

**1. feed_watch() — ligne ~6838-6852 de muninn.py**
```python
if fed_count > 0:    # <-- PROBLEME ICI
    # ... refresh tree ...
    # Sync to meta-mycelium
    m = Mycelium(repo_path)
    pushed = m.sync_to_meta()
```
Le sync est DANS le `if fed_count > 0`. Si aucun transcript n'est feed avec succes, le sync est skip. Or le feed hang depuis le 17 mars sur un gros JSONL.

**2. feed_from_hook() — ligne ~6448-6456 de muninn.py**
```python
# 5. P20b: Sync to meta-mycelium (cross-repo memory)
m = Mycelium(repo_path)
pushed = m.sync_to_meta()
```
Meme probleme: si le feed crash ou hang plus haut dans la fonction, on arrive jamais a cette ligne.

### Preuve dans les logs
- `hook_log.txt`: 0 occurrence de "SYNC" dans tout le fichier.
- Les entries montrent "WATCH feeding" suivi de rien (pas de "WATCH fed ok", pas de "WATCH done").
- Le feed hang sur un transcript JSONL. Timeout. fed_count = 0. Sync skip.

### Chaine de causalite
```
feed_watch toutes les 15 min (OK)
  → feed_from_transcript(gros_fichier.jsonl)
    → HANG (memoire? WAL lock? concept translation?)
  → timeout ou exception
  → fed_count = 0
  → if fed_count > 0: FALSE
  → sync_to_meta() JAMAIS APPELE
  → meta_mycelium.db FIGE
```

## Question pour toi (Muninn)

1. **Pourquoi le sync est-il conditionne a `fed_count > 0`?** Le mycelium local peut avoir ete mis a jour par d'autres chemins (sessions, recalls, boots). Le sync devrait-il etre decouple du feed?

2. **Quel transcript hang?** Regarde dans `.muninn/watch_state.json` et `.muninn/feed_progress.json` quel fichier JSONL bloque. Verifie sa taille. Si c'est un monstre (>50MB), c'est probablement ca le probleme.

3. **Le WAL fait 70MB.** Est-ce que c'est normal? Est-ce que ca bloque le sync? Faut-il forcer un checkpoint (`PRAGMA wal_checkpoint(TRUNCATE)`) avant de sync?

4. **La meta fait 1.3GB.** C'est enorme. Est-ce que le sync essaie de pusher trop de data d'un coup? Faut-il chunker?

## Fix propose (a valider)

**Option A — Decouple le sync du feed:**
Sortir le `sync_to_meta()` du `if fed_count > 0` dans `feed_watch()`. Le sync tourne a chaque cycle, que le feed ait reussi ou pas. Ajouter un timer: sync max 1x par heure (pas toutes les 15 min, trop lourd avec 1.3GB).

**Option B — Fix le hang d'abord:**
Identifier quel JSONL hang, le skipper ou le chunker, et le feed reprendra normalement avec le sync.

**Option C — Les deux:**
Fix le hang (B) ET decouple le sync (A) pour que ca arrive plus jamais.

## Action immediate
Lancer manuellement pour debloquer:
```python
from engine.core.mycelium import Mycelium
m = Mycelium("C:/Users/ludov/MUNINN-")
pushed = m.sync_to_meta()
print(f"Synced: {pushed}")
```
Ou via CLI si disponible. Ca devrait pusher le mycelium local vers le meta immediatement.

## Fichiers concernes
- `engine/core/muninn.py` lignes 6838-6852 (feed_watch sync) et 6448-6456 (feed_from_hook sync)
- `engine/core/mycelium.py` lignes 2069-2199 (sync_to_meta implementation)
- `.muninn/hook_log.txt` (logs)
- `.muninn/watch_state.json` (etat du watch)
- `.muninn/feed_progress.json` (progression des feeds)
- `~/.muninn/meta_mycelium.db` (la base qui sync pas)
