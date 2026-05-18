# MUNINN Sandbox + UX Audit Notes (2026-05-15)

> Consolidation de ce qu'on a monté pendant la session Sky/Claude
> du 2026-05-15. À garder en mémoire pour les sessions futures
> (Claude qui boot ici doit voir ces notes avant de re-proposer un
> setup sandbox/UX).

---

## 1. Sandbox Docker — état actuel

**Localisation**: `/home/sky/Bureau/muninn-sandbox/` (PAS dans le repo MUNINN-)

**Fichiers**:
- `Dockerfile` — base `python:3.13-slim` + `git build-essential less nano sqlite3 tiktoken`
  - User non-root `sandbox`, workdir `/home/sandbox`
  - `pip install --upgrade pip setuptools wheel && pip install --no-cache-dir tiktoken`
- `entrypoint.sh` — au container start:
  1. Clone `/muninn-source` (bind RO) → `/home/sandbox/workspace/muninn`
  2. `pip install --user --no-cache-dir -e ".[mcp]"` (extra `mcp` inclus → mcp lib + deps)
  3. Affiche banner "MUNINN sandbox ready" + drop dans bash
- `build.sh` — `docker build -t muninn-sandbox:latest .`
- `run.sh` — `docker run -it --rm --name muninn-sandbox -v /home/sky/Bureau/MUNINN-:/muninn-source:ro muninn-sandbox:latest "$@"`
- `README.md` — usage

**Image actuelle**: `muninn-sandbox:latest` (déjà build, en cache local)

**Caveat important**: la sandbox a un **mycelium VIERGE** à chaque `docker run --rm`
parce que `.muninn/` est gitignored donc absent du clone. Le mycelium accumule
seulement ce que le bootstrap fait sur ce run unique (~376K connexions sur 30
fichiers). Comparé au **vrai mycelium de Sky**:
- Local repo MUNINN-: **176 MB**, ~13K edges, 1.8K concepts, 329 sessions
- Meta cross-repo `~/.muninn/meta_mycelium.db`: **1.66 GB**, **9.3M edges**, 71K concepts
- Ratio sandbox/prod meta = **~500x moins** d'edges

Toute analyse UX dans la sandbox est donc à interpréter avec cette limite.

---

## 2. Tests UX déjà faits dans la sandbox

Commandes user-facing testées:

| Cmd | Résultat |
|---|---|
| `muninn-mem` (no arg) | Welcome screen propre, 3 cmd essentielles, lien quickstart |
| `muninn-mem --help` | Liste 32 subcommands |
| `muninn-mem status` | Affiche arbre 109 nodes (root + 50+ branches), IDs hash, tags concepts |
| `muninn-mem boot <query>` | Output structuré: `P:` préambule, `E:` entry, `S:` session, `F:` fichiers, `K:` keywords, `R:` recent commits |
| `muninn-mem recall "<query>"` | bag-of-words grep — 1 match seulement sur query test (recall pauvre) |
| `muninn-mem tree` | **CRASH** `ERROR: file argument required` (UX bug) |
| `muninn-mem init` | OK, crée `.muninn/tree/` + 10 hooks + repos.json |
| `muninn-mem doctor` (post-init) | "ALL GREEN — 24 checks passed" après le fix du jour (avant: 22 avec 2 false WARN MCP) |

---

## 3. Drifts UX identifiés (visibles, indépendants du mycelium pauvre)

Ces drifts tiennent quel que soit l'état du mycelium:

1. **`detect_zones requires: pip install numpy scipy scikit-learn`** — warning crypto
   silencieux au boot. Soit auto-install, soit logger en debug, soit virer le warning.

2. **`muninn-mem tree` sans arg crash** — UX bug pur. Soit afficher l'arbre par défaut
   (current behavior de `status`), soit afficher un help spécifique.

3. **Stopwords filter incomplet dans bridge_fast** — top concepts au boot contient
   `the`, `for`, `chunk`, `bug` mélangés avec les vrais concepts domain. Filtre
   ligne `muninn_tree.py:1523-1536` est codé en dur, peut être enrichi.

4. **Le root.mn commence par les badges markdown du README** —
   `Odin License | MIT | License [![Python](...)]` injecté au boot. Gaspillage du
   budget contexte Claude. Soit pré-process `root.mn` pour stripper les badges, soit
   le compress_transcript devrait virer ces patterns.

Drifts UX qui ne tiennent que dans la sandbox (mycelium pauvre):
- Recall sous-généreuse, branches sous-utilisées, vocabulaire pauvre — tous biais
  de la sandbox vierge, pas représentatifs de la prod Sky.

---

## 4. Plan branchement UI desktop dans sandbox (DONE 2026-05-18 — CHUNK 9 pipeline_trace)

Pour piloter `muninn-ui` (PyQt6 desktop) avec moi qui observe + Sky qui interagit:

**Étape 1 — Bump Dockerfile**:
```dockerfile
# Ajouter dans le bloc apt-get install
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential ca-certificates less nano sqlite3 \
        xdotool x11-apps imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Au moment du pip install (dans entrypoint.sh) :
# remplacer pip install -e ".[mcp]" par :
pip install --user --no-cache-dir -e ".[mcp,ui]"
```

**Étape 2 — X11 forward au runtime**. Modifier `run.sh`:
```bash
xhost +local:docker  # une fois, sur l'host
docker run -it --rm \
    --name muninn-sandbox \
    -e DISPLAY=$DISPLAY \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$MUNINN_REPO":/muninn-source:ro \
    --network host \
    muninn-sandbox:latest \
    "$@"
```

**Étape 3 — Lancer l'UX**: Sky dans le container: `muninn-ui` (la fenêtre s'ouvre
sur son écran X11 host, mais le process tourne dans le container).

**Étape 4 — Pilotage depuis ma session** (Claude bash):
- Clic: `docker exec muninn-sandbox xdotool search "Muninn" windowactivate; xdotool key ctrl+r`
- Type: `docker exec muninn-sandbox xdotool type "mycelium decay"`
- Screenshot: `docker exec muninn-sandbox import -window root /tmp/screen.png` puis `docker cp muninn-sandbox:/tmp/screen.png /tmp/`
- Tail logs UI: `docker exec muninn-sandbox tail -f /tmp/muninn-ui.log` (si l'UI écrit un log file)

**Workflow type** (Sky → Claude):
- Sky: "clic sur le bouton recall et tape 'mycelium decay'"
- Claude: exec `xdotool` series, screenshot, dit ce que l'UI affiche
- Sky: "OK et maintenant clic sur scan"
- Claude: idem, raconte le comportement

**Setup estimé**: ~30 min (Dockerfile bump + rebuild image + premier test fenêtre).

---

## 5. Observabilité du pipeline — où on en est

Plan complet (4 étapes):

| Étape | Status | Output |
|---|---|---|
| 1. **Pipeline map** (carto code) | ✅ **DONE** | `docs/PIPELINE_MAP.md` v1 (commit `5f01320`) + v2 révision (commit `e70ee24`). 541 lignes. 4 actions cartographiées, 11 drifts triés en v2 (3 confirmés, 1 doc drift, le reste nuancé/by-design) |
| 2. **Instrumentation** (log_event hot path) | ⏳ **PAS FAIT** | Ajouter `log_event("pipeline.X.start", {...})` aux ~15 entry points vérifiés. Output dans `.muninn/pipeline_trace.jsonl`. ~1-2h de boulot |
| 3. **Observation live** | ⏳ **PAS FAIT** | Sky utilise muninn-ui, Claude tail `.muninn/pipeline_trace.jsonl`, raconte ce qui s'execute. ~0 setup une fois étape 2 faite |
| 4. **Comparaison comportement vs intention** | ⏳ **PAS FAIT** | Pour chaque trace observée: conforme à la doc? Liste `CONFORM / DRIFT / WTF` |

---

## 6. Vrais points actionables à ce stade

(Après la session bâclée du 2026-05-15 sur Phase L — voir le bas de
`PIPELINE_MAP.md` v2 pour les détails sourcés)

1. **Virer `bridge()` orphan total** (P42 phase 1, `muninn_tree.py:1355-1602`).
   Zero callers prod depuis `655c386 (2026-03-14)` quand `bridge_fast` l'a remplacé.

2. **Wirer `adaptive_decay`** en 1 ligne dans `muninn_feed.py:1421`:
   ```python
   dead = m.decay(days=m.adaptive_decay_half_life())
   ```
   Sky's repo très actif passerait de half-life=30 à half-life=15 jours.

3. **Corriger Phase L L0 verdict** dans `docs/BATTLE_PLAN_PHASE_L_2026-05-14.md`:
   B42 = dead end mesuré (le benchmark 11%→88.8% SHA a écarté B42 au profit
   de B40 waves + B43 adaptive + CHUNK 13 learned anchors). Phase L L0 disait
   "B42 = pépite à wirer" — c'est faux, c'est une fonction obsolète d'un
   design précédent. Marker "Verdict révisé: dead end, recommend cleanup".

4. **Corriger doc drift CLAUDE.md** sur SessionStart auto-boot. La doc dit
   "muninn-mem boot [query] auto-invoked par SessionStart hook" mais le hook
   fait file I/O direct (light mode). Soit aligner la doc, soit aligner le hook.

---

## 7. À NE PAS refaire (pièges identifiés ce jour)

1. **Lancer 4 agents Explore en parallèle pour auditer le code** — ils hallucinent
   et concluent en surface. Mieux: lire le code soi-même + grep direct + citer
   file:line. Voir le pushback Sky du 2026-05-15 PM.

2. **Auditer UX dans la sandbox vierge et conclure que "MUNINN n'apprend pas"** —
   biais d'observation. Le mycelium pauvre de la sandbox ne reflète pas la prod.

3. **Proposer "wirer la pépite X"** sans avoir lu les benchmarks qui ont peut-être
   déjà mesuré X comme inférieur. Phase L L0 a fait ça avec B42, mon audit l'a
   répété. Toujours lire `tests/run_*.py`, `tests/test_ablation_*.py`,
   `tests/bench_*.py`, `tests/audit_*.py` ET les CHANGELOG entries de bench
   AVANT de conclure qu'une feature dormante est une "pépite".

4. **Concure que le projet a drift** alors qu'il a MUTÉ pour de bonnes raisons
   mesurées (11%→88.8% SHA match, target_tokens sweep 88→112, A/B yo-yo vs
   restart documenté). L'évolution architecturale a une histoire benchmarkée.
