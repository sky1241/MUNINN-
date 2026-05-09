# Handoff — Session 2026-04-24 : tests live Cube dans l'UX

> Document à donner en contexte à la prochaine session Claude (ou à tout
> nouvel agent qui reprend les tests de reconstruction Cube depuis l'UX).
> Écrit à chaud après la première reco bout-en-bout réussie dans l'UX.

---

## 1. État du repo (fresh)

- Remote : `github.com/sky1241/MUNINN-`
- Branche : `main`
- Dernier commit pertinent : `40a0581` (feat UI: cube_live uses real Muninn pipeline)
- OS : Debian 12, kernel 6.1, pyenv 3.13.13
- GPU : AMD RX 5700 XT via Vulkan (ROCm désactivé, cf `b85b222`)
- Ollama : service actif, backend Vulkan, modèles pullés :
  `qwen2.5-coder:7b`, `deepseek-coder:6.7b`, `llama3.2:1b`

## 2. Ce qui marche (validé en live)

Dans l'UX PyQt6 (`python -m muninn.ui.main_window`), la commande :

    /reconstruct tests/cube_corpus/btree_google.go 112 10

déclenche `engine.core.cube_providers.reconstruct_adaptive` sur les 10
premiers cubes du fichier via `OllamaProvider(qwen2.5-coder:7b)` et :
- émet une heatmap de cubes (carrés) dans le `NeuronMapWidget`,
- met à jour la couleur de chaque cube en live (vert = SHA match),
- affiche dans le terminal intégré les logs par cube (`c1 x1 cube N: ...`).

## 3. Résultat du test live (RULE 4 — output réel, pas paraphrasé)

```
/reconstruct tests/cube_corpus/btree_google.go 112 10
[reco] btree_google.go — model=qwen2.5-coder:7b, lines/cube=112, max=10
[reco] file has 61 cubes, capping to first 10 for the heatmap
[reco] btree_google.go — 10 cubes @ 112 tokens, model=qwen2.5-coder:7b,
       max_cycles=3, attempts/cube=3
   c1 x1 cube  0: SHA (attempt 1)
   c1 x1 cube  1: NCD=0.758 (3a)
   c1 x1 cube  2: NCD=0.928 (3a)
   c1 x1 cube  3: NCD=0.879 (3a)
   c1 x1 cube  4: NCD=0.775 (3a)
   c1 x1 cube  5: NCD=0.833 (3a)
   c1 x1 cube  6: NCD=0.691 (3a)
   c1 x1 cube  7: NCD=0.826 (3a)
   c1 x1 cube  8: NCD=0.851 (3a)
   c1 x1 cube  9: NCD=0.829 (3a)
```

Bilan : **1 SHA match / 10 cubes** (cube 0, au premier attempt).
Plateau detection de `reconstruct_adaptive` a coupé après cycle 1 (0
nouveau SHA prévisible en cycle 2/3 avec ces réglages).

## 4. Pourquoi seulement 1/10 (honnête)

Les vrais résultats Muninn publiés dans le CHANGELOG sont :
- **80/80 SHA** sur `server.go` (Claude Sonnet, 3 passes, mycelium alimenté)
- **54/61 SHA (88.5%)** sur `btree_google.go` (même config)

On est **loin** de ces chiffres parce que ce run a été lancé avec :
- `provider = OllamaProvider(qwen2.5-coder:7b)` (Qwen 7B local, pas Sonnet)
- `mycelium = None` (aucun apprentissage préalable, mycelium vide)
- `attempts_per_cube = 3` (au lieu de 11 par défaut du pipeline)
- `max_cycles = 3` mais plateau après cycle 1
- Aucune session Muninn préalable n'a nourri les learned anchors

**Le pipeline marche**. Le tuning est ce qui est à améliorer pour
s'approcher des scores de référence.

## 5. Setup pour reprendre (commandes exactes)

    cd /home/sky/Bureau/MUNINN-
    git pull origin main
    # Vérifier Ollama + GPU Vulkan
    systemctl status ollama --no-pager | head -6
    ollama ps        # vide si aucun modèle chargé
    ollama list      # doit lister qwen2.5-coder:7b
    # Lancer l'UX
    PYTHONPATH=$(pwd) python -m muninn.ui.main_window

## 6. Sessions de test suggérées (ordre d'impact)

### 6.1 — Rejouer le baseline Qwen (ce qui a été testé)
    /reconstruct tests/cube_corpus/btree_google.go 112 10
Cible : reproduire ~1/10 SHA. Si < 1/10 → régression à investiguer.

### 6.2 — Monter `attempts_per_cube` à 11 (défaut engine)
Modifier `muninn/ui/cube_live.py` ReconstructionWorker default
`attempts_per_cube=3` -> `11`. Relancer (temps x3-4, NCD attendu baisse).

### 6.3 — Alimenter le mycelium avant test
Avant `/reconstruct`, faire `muninn feed` sur quelques transcripts
préalables pour que `reconstruct_adaptive(..., mycelium=M)` ait du
vocabulaire. Actuellement `cube_live.py` passe `mycelium=None` —
c'est à changer pour accepter un mycelium depuis l'UX.

### 6.4 — Swap provider : Claude Sonnet
Dans l'UX : dropdown AI → Claude, fournir clé API, retester.
Attendu : scores proches du benchmark publié (80+%). `cube_live.py`
doit lire `get_active_provider()` et instancier `ClaudeProvider`
au lieu de hardcoder `OllamaProvider`.

### 6.5 — Autres fichiers de test
- `tests/cube_corpus/analytics.py` (Python court)
- `tests/cube_corpus/allocator.c` (C court)
- `tests/cube_corpus/cache.rs` (Rust)
Plus petits que `btree_google.go`, bons pour itérer vite.

## 7. Fichiers-clés touchés cette session

| Fichier | Rôle |
|---|---|
| `muninn/ui/cube_live.py` | `ReconstructionWorker` QThread, appelle `reconstruct_adaptive` |
| `muninn/ui/neuron_map.py` | mode reconstruction + Laplacien chain edges + rotation fixée + carrés |
| `muninn/ui/terminal.py` | commandes `/reconstruct` et `/stop` |
| `muninn/ui/main_window.py` | signal wiring terminal ↔ heatmap + Navi hide |

Commits de la session : `b85b222`, `306dc44`, `932426b`, `40a0581`.
Optionnel : encore en working tree si non-commité au moment du handoff :
le fix Navi hide (2 petits hunks terminal.py + main_window.py).

## 8. Bugs connus / trous à boucher

- **BUG-NAVI** (ouvert) : `muninn/ui/navi.py:_paint_orb` tourne ~30fps
  même pendant une reco, monopolise le main thread (~150% CPU un cœur)
  et fait laguer la heatmap. Fix partiel : hide Navi pendant `/reconstruct`
  via signaux `reconstruction_started` / `reconstruction_ended` (implémenté,
  à tester au prochain restart UX).
- **`memory/tree.json` régression** (working tree, non-commité) :
  b0002.lines 29 → 3, re-casserait CI. `git checkout -- memory/tree.json`
  pour reset. C'est un hook Muninn auto qui l'a mis dirty.
- **`test_brick19_dead_code_audit`** fail pré-existant sur
  `reconstruct_adaptive` / `reconstruct_line_by_line` — pas une régression
  de cette session, `DOCUMENTED_IN_TREE_DEAD_CANDIDATES` à compléter.

## 9. Règles que la prochaine session DOIT respecter

Lues et appliquées cette session (voir `CLAUDE.md` + `docs/ANTI_BULLSHIT_BATTLE_PLAN.md`) :

1. Paths universels, jamais hardcoded (RULE 1).
2. Confirmer avant destructif (RULE 2).
3. Jamais afficher de secrets (RULE 3).
4. **NO CLAIM WITHOUT COMMAND OUTPUT** (RULE 4, ABSOLUTE).
5. Forge après chaque module engine touché (RULE 5). Cette session n'a
   touché **que muninn/ui/**, pas engine/, donc pas de run forge
   requis. Mais **si la prochaine session modifie `reconstruct_adaptive`
   ou `OllamaProvider`**, forge est obligatoire.

Checklist de fin de session en dernier message (défense 10 du battle plan).

---

## Prompt de démarrage suggéré pour la prochaine session

> Tu reprends une session sur le repo MUNINN- à
> `/home/sky/Bureau/MUNINN-` (Sky/sky1241 sur GitHub). Lis d'abord
> `CLAUDE.md` puis `docs/HANDOFF_CUBE_LIVE_TESTS.md`. Les commits de la
> dernière session sont `b85b222`, `306dc44`, `932426b`, `40a0581`.
> Le dernier test live a produit 1/10 SHA match sur btree_google.go avec
> Qwen 2.5 Coder 7B. Sky veut continuer les tests. Ne dis rien sans
> output — applique les 10 défenses du battle plan, termine par une
> checklist. Ne lance pas `/reconstruct` sans lui demander d'abord
> quels paramètres il veut (fichier, base_tokens, max_cubes).
