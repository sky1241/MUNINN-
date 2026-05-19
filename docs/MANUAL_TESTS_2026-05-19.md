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

*(Plus de chunks à ajouter ici au fur et à mesure C1 → C13.)*
