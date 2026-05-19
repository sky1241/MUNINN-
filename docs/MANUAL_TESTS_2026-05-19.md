# Tests manuels à refaire à la main — Sky's checklist

> Liste des actions manuelles que Sky peut refaire pour valider chaque
> chunk poussé. S'enrichit chunk par chunk. Le but : qu'à la fin du plan
> unifié 2026-05-19, Sky puisse re-tester end-to-end sans dépendre de
> moi.
>
> **Convention** : `[ ]` = à valider, `[x]` = validé par Sky.
>
> **Reset env recommandé avant chaque test** :
> ```bash
> unset MUNINN_LLM_REPEAT_PENALTY MUNINN_LLM_TEMPERATURE \
>       MUNINN_HEALED_PERSISTENT MUNINN_FORGE_FILE_ORDERING \
>       MUNINN_FUSE_RISKS_ORDERING MUNINN_SCAN_AWARE_SUBDIVIDE \
>       MUNINN_NEIGHBORS_LIVE_REFRESH MUNINN_UI_NEURON_MODE
> ```

---

## CHUNK C0 — LLM mode collapse fix (repeat_penalty + temperature)

### Test 1 — Defaults sans env var
```bash
cd /home/sky/Bureau/MUNINN-
python3 -c "
import os
os.environ.pop('MUNINN_LLM_REPEAT_PENALTY', None)
os.environ.pop('MUNINN_LLM_TEMPERATURE', None)
import sys
sys.path.insert(0, 'engine/core')
from cube_providers import _OLLAMA_REPEAT_PENALTY, _OLLAMA_TEMPERATURE
print(f'repeat_penalty={_OLLAMA_REPEAT_PENALTY}, temperature={_OLLAMA_TEMPERATURE}')
"
```
**Attendu** : `repeat_penalty=1.15, temperature=0.2`
- [ ]

### Test 2 — Override env vars
```bash
MUNINN_LLM_REPEAT_PENALTY=1.30 MUNINN_LLM_TEMPERATURE=0.5 python3 -c "
import sys
sys.path.insert(0, 'engine/core')
from cube_providers import _OLLAMA_REPEAT_PENALTY, _OLLAMA_TEMPERATURE
print(f'repeat_penalty={_OLLAMA_REPEAT_PENALTY}, temperature={_OLLAMA_TEMPERATURE}')
"
```
**Attendu** : `repeat_penalty=1.3, temperature=0.5`
- [ ]

### Test 3 — Sandbox UI reco end-to-end (visuel)
```bash
cd /home/sky/Bureau/muninn-sandbox && ./run-ui.sh muninn-ui
# Dans l'UI : /scan /tmp/btree-only puis /reconstruct /tmp/btree-only/btree_google.go
```
**Attendu** : dans le terminal, plus de boucle `returning, returning, returning…` sur les outputs LLM. Les attempts peuvent toujours échouer (modèle trop petit) mais elles produisent du code varié, pas une seule chaîne répétée.
- [ ]

### Test 4 — Legacy mode (revert au comportement pré-fix)
```bash
MUNINN_LLM_REPEAT_PENALTY=1.0 MUNINN_LLM_TEMPERATURE=0.0 ./run-ui.sh muninn-ui
# /scan + /reconstruct
```
**Attendu** : retour au mode déterministe legacy. Si le modèle bouclait avant, il rebouclerait ici (preuve que la bascule legacy fonctionne).
- [ ]

### Test 5 — Pipeline trace event
```bash
# Après n'importe quelle reco lancée, lire le trace :
tail -5 /home/sandbox/.muninn/pipeline_trace.jsonl  # dans le container
# OU
tail -5 $(find / -name "pipeline_trace.jsonl" 2>/dev/null | head -1)
```
**Attendu** : au moins 1 ligne `"event": "pipeline.engine.llm.options_applied"` avec `repeat_penalty: 1.15, temperature: 0.2`.
- [ ]

---

## CHUNK C1 — BUG WAGON SHA-256 fix (cycle 2+ optimization)

### Test 1 — Cycle 2+ exact_match passe pour cubes healed (visuel sandbox)
```bash
cd /home/sky/Bureau/muninn-sandbox && ./run-ui.sh muninn-ui
# Dans l'UI : /scan /tmp/btree-only puis /reconstruct /tmp/btree-only/btree_google.go
# Observer le terminal :
#   cycle 1 : N cubes SHA, M cubes NCD partial
#   cycle 2 : les N cubes SHA cycle 1 doivent rester SHA cycle 2 (skipped via exact_match)
#            au lieu d'être re-traités à zéro
```
**Attendu pré-fix** : cycle 2 réitère sur tous les cubes (slow). **Post-fix** : cycle 2 skip les SHA matchés cycle 1 (fast — preuve du fix).
- [ ]

### Test 2 — DB cube.sha256 cohérent avec content
```bash
# Après reco, ouvrir le store SQLite :
python3 -c "
import sqlite3, hashlib
conn = sqlite3.connect('/tmp/btree-only/.muninn/cube.db')
for cube_id, sha, content in conn.execute('SELECT id, sha256, content FROM cubes LIMIT 5'):
    actual = hashlib.sha256(content.encode()).hexdigest()
    print(f'{cube_id}: stored={sha[:12]}... actual={actual[:12]}... match={sha==actual}')
"
```
**Attendu** : tous match=True (cohérence SHA ↔ content garantie post-fix).
- [ ]

### Test 3 — Bascule legacy (re-introduire le bug pour test)
Pas applicable directement — le fix est mécanique (1 ligne, pas d'env var pour C1). Pour tester legacy, revert le commit C1 et observer cycle 2 (cubes re-traités).

---

## CHUNK C2 — Batch `record_cycles` via executemany (~x250 gain)

### Test 1 — API existe
```bash
python3 -c "
import sys; sys.path.insert(0, 'engine/core')
from cube import CubeStore
import inspect
assert hasattr(CubeStore, 'record_cycles'), 'method missing'
assert hasattr(CubeStore, 'record_cycle'), 'singular still exists'
print('OK : record_cycles (plural) + record_cycle (singular legacy) tous deux présents')
"
```
- [ ]

### Test 2 — Speedup mesuré
```bash
python3 -c "
import sys, time
sys.path.insert(0, 'engine/core')
from cube import CubeStore
import tempfile, pathlib

# Singular path
db_a = pathlib.Path(tempfile.mkdtemp()) / 'a.db'
store_a = CubeStore(str(db_a))
t0 = time.perf_counter()
for i in range(200):
    store_a.record_cycle(f'c{i}', 1, True, '', 0.0)
t_sing = time.perf_counter() - t0

# Batch path
db_b = pathlib.Path(tempfile.mkdtemp()) / 'b.db'
store_b = CubeStore(str(db_b))
batch = [(f'c{i}', 1, True, '', 0.0) for i in range(200)]
t0 = time.perf_counter()
store_b.record_cycles(batch)
t_batch = time.perf_counter() - t0

speedup = t_sing / t_batch
print(f'singular: {t_sing*1000:.1f}ms, batch: {t_batch*1000:.1f}ms, speedup: {speedup:.1f}x')
assert speedup >= 2, 'expected >=2x speedup'
"
```
**Attendu** : speedup >= 2x (en pratique 10-50x).
- [ ]

### Test 3 — `muninn-mem cube run` end-to-end
```bash
cd /home/sky/Bureau/muninn-sandbox && ./run-ui.sh muninn-ui
# /scan /tmp/btree-only puis /reconstruct
# Mesurer le temps total avec `time` côté host (run-ui.sh)
```
**Attendu** : run notablement plus rapide qu'avant C2 (~25s économisés sur 1000-cube run, moins mesurable sur petit btree mais quand même).
- [ ]

---

## CHUNK C3 — Healed set persistent cross-run (x3-x5 gain)

### Test 1 — get_healed_cubes() retourne 100% successful
```bash
python3 -c "
import sys, tempfile, pathlib
sys.path.insert(0, 'engine/core')
from cube import CubeStore
db = pathlib.Path(tempfile.mkdtemp()) / 'cube.db'
store = CubeStore(str(db))
for cycle in (1,2,3):
    store.record_cycle('cubeA', cycle, True, '', 0.0)
store.record_cycle('cubeB', 1, True, '', 0.0)
store.record_cycle('cubeB', 2, False, '', 0.0)
store.record_cycle('cubeB', 3, True, '', 0.0)
healed = store.get_healed_cubes(min_success_count=3)
print(f'healed={healed}')
assert healed == {'cubeA'}, 'cubeB excluded (1 failure history)'
print('OK')
"
```
- [ ]

### Test 2 — Bascule legacy MUNINN_HEALED_PERSISTENT=0
```bash
MUNINN_HEALED_PERSISTENT=0 python3 -c "
import sys; sys.path.insert(0, 'engine/core')
import cube_analysis
assert cube_analysis._HEALED_PERSISTENT_ENABLED is False
print('OK : legacy mode activated')
"
```
- [ ]

### Test 3 — `cube run` incremental (visuel sandbox)
```bash
cd /home/sky/Bureau/muninn-sandbox && ./run-ui.sh muninn-ui
# Run 1: /scan /tmp/btree-only puis /reconstruct → mesure le temps total
# Run 2 (sans tout fermer): /reconstruct à nouveau → mesure le temps total
```
**Attendu** : Run 2 notablement plus rapide que Run 1 (les cubes SHA-matchés au run 1 sont skippés au run 2). Si MUNINN_HEALED_PERSISTENT=0, run 2 = run 1 (preuve bascule).
- [ ]

---

## CHUNK C4 — Forge cache infrastructure (F0)

### Test 1 — API existe
```bash
python3 -c "
import sys; sys.path.insert(0, 'engine/core')
import forge_metrics
assert callable(forge_metrics.get_file_risk_map)
print('OK : get_file_risk_map exposé')
"
```
- [ ]

### Test 2 — Retourne dict[str, float]
```bash
python3 -c "
import sys, pathlib
sys.path.insert(0, 'engine/core')
import forge_metrics
risk_map = forge_metrics.get_file_risk_map(pathlib.Path('.'))
print(f'type={type(risk_map).__name__}, len={len(risk_map)}')
if risk_map:
    sample = list(risk_map.items())[:3]
    print(f'sample: {sample}')
"
```
**Attendu** : dict (peut être vide si forge unavailable, sinon ~30 entries pour MUNINN-).
- [ ]

### Test 3 — Pipeline trace event
Après n'importe quel appel à `get_file_risk_map`, l'event suivant apparaît dans `pipeline_trace.jsonl`:
```bash
grep "pipeline.forge.risk_map_cached" /home/sandbox/.muninn/pipeline_trace.jsonl 2>/dev/null | tail -2
```
**Attendu** : `{"event": "pipeline.forge.risk_map_cached", "data": {"repo": "...", "n_files": N, "available": true|false}}`.
- [ ]

---

*(Plus de chunks à ajouter ici au fur et à mesure C5 → C13.)*
