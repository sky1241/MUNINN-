# Battle Plan — Reco × Scan × Forge fusion (2026-05-19)

> **But** : finir d'implémenter ce qu'on avait planifié sur la
> reconstruction — fusionner scan, forge et mycélium dans un pipeline
> unique, puis brancher les UX manquants. Audit du jour, chunk par
> chunk, push après chaque chunk avec CI verte.
>
> **Source** : audit 4-agents du 2026-05-19 sur subdivide_file,
> fuse_risks, UX components, mycelium feedback loops. État réel relevé
> en lignes de code, pas en docstring.

---

## Sommaire — État réel des features (audit 2026-05-19)

| Feature | Codé | Branché runtime | Prod | Verdict |
|---|---|---|---|---|
| **A. subdivide_file mycelium-aware** | partiel | ❌ | partiel | `subdivide_file` ignore le mycélium. `detect_zones` retourne des concepts, pas des lignes. Helper `concept_to_lines` MISSING. |
| **B. fuse_risks → reco ordering** | ✅ | ❌ | ❌ | Fonction `engine/core/cube_analysis.py:1544` EXISTE et est exportée. **Zero call site runtime** — 3 tests offline seulement. |
| **C. forge_score_for_path display** | ✅ | ✅ | ✅ | `muninn/ui/cube_live.py:182-218` affiche risk=X (HIGH/MOD/LOW/STABLE). Pas d'influence sur le scheduling. |
| **D. observe_text on SHA match** | ✅ | ✅ | ✅ | `engine/core/cube_providers.py:1897` feed mycelium au SHA. Phase 3 du 2026-05-14. |
| **E. observe_failure on NCD fail** | ✅ | ✅ | ✅ | `engine/core/cube_providers.py:1907` → `mycelium.py:653`. Bounded `[-10, 0]`. |
| **F. mycelium_neighbors live refresh** | ❌ | ❌ | ❌ | `cube_live.py:246-276` calcule une fois pré-reco. Static. Pas de refresh entre cycles. |
| **G. Cube cycles x1/x2/x3 engine** | ✅ | ✅ | ✅ | `cube_providers.py:1964-2000`. Plateau detection (cycle_new_sha == 0 → break). |
| **H. UI toggle Mycelium↔Reconstruction** | ❌ | ❌ | ❌ | `set_reconstruction_cubes` existe (hier) mais aucun bouton pour switcher. Pattern ForestToggle dispo (`forest.py:123-171`). |
| **I. DetailPanel SHA/NCD/gaps/unknown** | ❌ | partiel | partiel | Affiche temperature, zone, voisins. PAS SHA/NCD/gaps/unknown idents. |
| **J. File line-by-line heatmap view** | ❌ | ❌ | ❌ | Aucun widget `file_view.py`. Phase 3 du HEATMAP_PLAN intacte. |
| **K. Fractal x1/x2/x3 visual** | ❌ | ❌ | ❌ | Engine cycles OK (G) mais aucun zoom UI x1/x2/x3. |

**Synthèse** : 5 features prod-ready (C/D/E/G + half-A). 3 dormantes critiques (B/F/H). 3 manquantes UX (I/J/K). 1 archi à brancher (A complet).

---

## Ordre d'exécution — chunks 1 à 7

Chaque chunk = 1 commit + 1 push + 1 CI verte. Dépendances déclarées.
Aucune Phase n'est démarrée avant la CI verte du chunk précédent.

### CHUNK 1 — `fuse_risks` → `reconstruct_adaptive` ordering

**But** : sortir `fuse_risks` du mode dormant. Reconstruire les cubes du
moins risqué au plus risqué — les cubes faibles deviennent contexte
stable pour les hauts.

**Fichiers à toucher** :
- `engine/core/cube_providers.py::reconstruct_adaptive` (signature + boucle `for c in cubes`)
- `engine/core/cube_providers.py::_run_level_pass` (sort `to_test` par risk)
- `muninn/ui/cube_live.py` (lookup forge_root, passer à reconstruct_adaptive)
- `engine/core/muninn.py::cli_run` handler `cube run` (idem côté CLI)

**Spec technique** :
- `reconstruct_adaptive(... forge_root: Optional[str]=None, ...)` → si fourni, appelle `fuse_risks` une fois et conserve un dict `{cube_idx: combined_risk}`.
- `_run_level_pass` sort `to_test` par combined_risk croissant avant la boucle d'attempts.
- Pas d'attempt budget par tier en chunk 1 — juste l'ordering (laisser tier budget pour chunk plus tard si besoin).
- Fallback silencieux : si `fuse_risks` retourne vide ou throw, ordre séquentiel naturel.

**Tests à ajouter** (`tests/test_chunk1_2026-05-19_fuse_risks_ordering.py`) :
- `test_fuse_risks_used_when_forge_root_provided` (mock provider, assert call order)
- `test_fallback_to_sequential_when_forge_unavailable`
- `test_low_risk_cubes_processed_first`

**Forge (RULE 5)** : `forge --gen-props engine/core/cube_providers.py`, vérifier que les props ne touchent pas la nouvelle branche.

**Coût** : ~60 LOC + 3 tests + forge. **Estimation 2h.**

**Critère de done** : `fuse_risks` apparaît dans le call stack d'un run UI (vérifié via pipeline_trace event `pipeline.engine.reco.fuse_risks_used`).

---

### CHUNK 2 — `subdivide_file` mycelium-aware (Phase 2 globale)

**But** : le découpage en cubes suit les frontières conceptuelles du
scan, pas un grid token-uniforme aveugle.

**Fichiers à toucher** :
- `engine/core/mycelium.py` ou `engine/core/mycelium_zones.py` : **nouveau helper** `concept_to_file_lines(content: str, mycelium: Mycelium) -> dict[int, set[str]]` qui retourne pour chaque ligne du fichier les concepts mycélium présents (intersection words ∩ codebook avec regex `r"[A-Za-zÀ-ÿ_]{3,}"` — réutilise constante de `cube_live.py:_MYCELIUM_CONCEPT_REGEX`).
- `engine/core/cube.py` : **nouveau helper** `find_concept_boundaries(content, mycelium, target_tokens)` qui appelle `detect_zones` puis `concept_to_file_lines`, calcule dominant zone par ligne, retourne les line numbers où la zone dominante change.
- `engine/core/cube.py::subdivide_file` : signature `(...mycelium: Optional[Mycelium]=None)`. Si fourni : boundaries préférées = retour de `find_concept_boundaries`. Sinon : fallback comportement actuel (token-uniform).
- `muninn/ui/cube_live.py` : passer `mycelium=mycelium` au `subdivide_file(...)` l.143-146.
- `engine/core/cube_providers.py` : 3 call sites (1970, 2005, 2062) passent mycelium quand dispo.

**Spec technique** :
- Découpage final = max(token-target, frontière conceptuelle la plus proche dans une window ±20% target_tokens). Préserve la propriété "cube ≈ 112 tokens" tout en alignant sur zones.
- Si `detect_zones()` retourne <2 zones → fallback token-uniform (signal trop pauvre).
- BUG-091 mirror = pas applicable, `muninn/cube.py` est un shim.

**Tests à ajouter** (`tests/test_chunk2_2026-05-19_subdivide_mycelium.py`) :
- `test_subdivide_falls_back_when_no_mycelium`
- `test_subdivide_respects_zone_boundaries_when_mycelium_provided`
- `test_concept_to_file_lines_returns_per_line_set`
- `test_find_concept_boundaries_empty_when_under_2_zones`

**Forge** : `forge --gen-props engine/core/cube.py` après modifs.

**Coût** : ~80 LOC (helper + plumbing) + 4 tests + forge. **Estimation 3h.**

**Critère de done** : sur `tests/cube_corpus/btree_google.go` avec mycelium populé, `subdivide_file(..., mycelium=m)` retourne un nombre de cubes différent du token-uniform et leurs `line_start` matchent des frontières de fonctions/types (vérifiable visuellement).

**Dépendances** : aucune sur CHUNK 1, mais CHUNK 1 vient avant car plus simple et profite déjà du découpage actuel.

---

### CHUNK 3 — Live refresh `mycelium_neighbors` entre cycles

**But** : aujourd'hui `cube_live.py:246-276` calcule `mycelium_neighbors`
une fois pré-reco. Pendant les cycles x1→x2→x3 le mycélium grossit
(observe_text + observe_failure), mais le graphe d'edges UI reste figé.
Le user voit les premiers cubes verts mais le clustering ne se met pas
à jour.

**Fichiers à toucher** :
- `muninn/ui/cube_live.py` : extraire le calcul `mycelium_neighbors` en méthode `_compute_neighbors()`. L'appeler entre chaque cycle (callback `on_cube(status="CYCLE_END")`).
- `muninn/ui/cube_live.py::cubes_payload` : ajouter signal `neighbors_refreshed(list[list[int]])` ou réémettre `cubes_ready` modifié.
- `muninn/ui/neuron_map.py::set_reconstruction_cubes` ou nouveau slot : accepter un payload d'edges refresh-only sans rebâtir les neurons.

**Spec technique** :
- 1 refresh entre chaque cycle (pas dans la boucle attempts → trop verbeux).
- Le Laplacien spectral est relancé sur le nouveau graphe → positions se réajustent en arrière-plan QThread.
- Trace event : `pipeline.ui.cube_live.neighbors_refreshed` avec `cycle, n_edges`.

**Tests à ajouter** (`tests/test_chunk3_2026-05-19_neighbors_refresh.py`) :
- `test_neighbors_refresh_emits_signal_per_cycle`
- `test_neighbor_count_grows_between_cycles_when_mycelium_grows`

**Coût** : ~40 LOC + 2 tests. **Estimation 1h30.**

**Critère de done** : screenshot temporel pendant un run réel — clusters
qui se réorganisent visiblement entre les cycles.

**Dépendances** : pas de blocking, mais bénéficie de CHUNK 1 (les cubes
re-feedés plus tôt si low-risk reconstruits d'abord).

---

### CHUNK 4 — UI toggle Mycelium ↔ Reconstruction

**But** : un bouton dans l'UI pour basculer la couleur entre :
- **Mycelium mode** : neurons = concepts, couleur = degree (graphe de scan)
- **Reconstruction mode** : neurons = cubes, couleur = NCD (carte de reco)

**Fichiers à toucher** :
- `muninn/ui/neuron_map.py` :
  - Ajouter `self._current_mode = "mycelium"` à l'init (~l.195).
  - Ajouter `set_mode(mode: str)` qui repaint.
  - Dans `_paint_neurons` (~l.592), conditionner la source de couleur sur `_current_mode`.
- `muninn/ui/main_window.py` ou nouveau widget `mode_toggle.py` : créer un `ModeToggle(QWidget)` à la `ForestToggle` (`muninn/ui/forest.py:123-171`).
- `muninn/ui/main_window.py` : positionner le toggle en overlay top-right du neuron panel ou dans une mini-toolbar.

**Spec technique** :
- Toggle preserve l'état des neurons (pas de rebuild). Juste change la source de couleur du paint.
- Si `_neurons` est vide ou contient des cubes de reco, "Mycelium mode" affiche l'état empty avec un message "Charge un scan d'abord" (pas crash).
- Persistance : sauver `current_mode` dans `~/.muninn/ui_config.json`.

**Tests à ajouter** (`tests/test_ui_neuron_map.py` — fichier existant) :
- `test_mode_toggle_changes_paint_source`
- `test_set_mode_invalid_raises_or_ignored`
- `test_mode_persists_via_ui_config`

**Coût** : ~50 LOC widget + 5 LOC neuron_map + 3 tests. **Estimation 1h.**

**Critère de done** : clic sur le bouton "Mode: Mycelium" → couleurs
changent immédiatement vers "Mode: Reconstruction" et inverse.

**Dépendances** : aucune. Peut se faire après n'importe quel chunk.

---

### CHUNK 5 — DetailPanel SHA/NCD/gaps/unknown identifiers

**But** : quand on clique sur un cube reconstruit, le DetailPanel
affiche les vraies infos de reco (pas juste temperature et voisins).

**Fichiers à toucher** :
- `engine/core/cube_providers.py::ReconstructionResult` (~l.926) : **ajouter** champs `gap_lines: list[int]` et `unknown_identifiers: list[str]`. Default `[]`.
- `engine/core/cube_providers.py::reconstruct_cube` : après reco, calculer :
  - `gap_lines` = `[i for i in range(n_lines) if i not in anchor_map]` (inverse de `_build_full_anchor_map`).
  - `unknown_identifiers` = diff entre `extract_ast_hints(original)['identifiers']` et identifiers extraits ligne par ligne de `reconstruction`.
- `engine/core/cube_providers.py::WaveResult` (~l.1246) : propager `gap_lines`, `unknowns`.
- `muninn/ui/cube_live.py::on_cube` callback : enrichir le payload `cube_done` avec ces champs.
- `muninn/ui/neuron_map.py::Neuron` : ajouter `gap_lines`, `unknown_idents` fields.
- `muninn/ui/detail_panel.py` :
  - Ajouter widget `_sha_label` (QLabel avec icône ✓/✗).
  - Ajouter widget `_ncd_bar` (QProgressBar colorée par theme.SUCCESS/WARNING/ERROR).
  - Ajouter widget `_gaps_section` (QListWidget scrollable, cliquable → emit signal `gap_clicked(line_no)`).
  - Ajouter widget `_unknowns_section` (idem).
  - Étendre `show_neuron(neuron_data)` pour lire les nouveaux champs.

**Spec technique** :
- Si neuron n'a pas de NCD (mode Mycelium pur) → cacher les 4 nouveaux widgets.
- `_build_full_anchor_map` retourne `dict[int, str]` aujourd'hui — l'inverser ne coûte rien (set diff).
- Pour `unknown_identifiers`, regex de tokenisation alignée sur `mycelium.observe_text` (déjà constante dans cube_live).

**Tests à ajouter** :
- `tests/test_chunk5_2026-05-19_recon_result_extras.py` : 4 tests (gap_lines correct, unknowns diff correct, backward-compat default [], propagation jusqu'au callback)
- `tests/test_ui_detail_panel.py` (à étendre) : tests widgets show/hide selon données

**Coût** : ~100 LOC engine + ~80 LOC UI + ~8 tests. **Estimation 3h.**

**Critère de done** : run reco, clic sur un cube rouge, le panel affiche
"NCD=0.67, gaps=12 lignes, unknown identifiers=[xyz, foo]".

**Dépendances** : pas de blocking, mais bénéficie de CHUNK 4 pour l'UX
cohérente (toggle qui montre/cache automatiquement).

---

### CHUNK 6 — File line-by-line heatmap view (HEATMAP Phase 3)

**But** : vue alternative au cube 3D — le fichier source affiché ligne
par ligne avec un bandeau coloré à gauche (style code coverage).

**Fichiers à toucher** :
- `muninn/ui/file_heatmap_view.py` (**nouveau widget**, ~200 LOC) :
  - QPlainTextEdit en read-only avec syntax highlighting (réutiliser theme).
  - Marge gauche custom paintEvent → bandeau vert/orange/rouge par ligne.
  - Click sur ligne → emit `line_clicked(int)`.
- `muninn/ui/main_window.py` : ajouter le widget dans un nouveau tab du right_splitter ou en bottom panel.
- `muninn/ui/cube_live.py` : nouveau signal `file_heatmap_ready(str path, dict[int, str] line_colors)`.

**Spec technique** :
- Couleur ligne :
  - Vert : ligne ancrée (présente dans anchor_map de _build_full_anchor_map du cube contenant cette ligne).
  - Rouge : ligne gap (modèle doit deviner, NON dans anchor_map).
  - Orange : gap mais SHA match quand même (risque caché — le modèle a deviné juste mais par chance).
- Map cube → lignes via `cube.line_start, line_end` (déjà présent dans `Cube` dataclass).

**Tests à ajouter** (`tests/test_chunk6_2026-05-19_file_heatmap.py`) :
- `test_line_colors_derived_from_anchor_map`
- `test_orange_for_gap_with_sha`
- `test_click_emits_line_signal`

**Coût** : ~200 LOC widget + 3 tests. **Estimation 4h.**

**Critère de done** : ouvrir le fichier `btree_google.go` dans la vue,
voir les ~25 % de lignes ancrées en vert et le reste en rouge/orange.

**Dépendances** : CHUNK 5 (ReconstructionResult enrichi avec gap_lines).

---

### CHUNK 7 — Fractal x1/x2/x3 visual (HEATMAP Phase 4)

**But** : aujourd'hui le `NeuronMapWidget` affiche les cubes x1 (atomes
de 112 tokens). En mode "Reconstruction", zoom out doit faire apparaître
les niveaux x2 (molecules de 2 cubes) puis x3 (cellules de 4 cubes), avec
couleur = moyenne des NCD.

**Fichiers à toucher** :
- `engine/core/cube.py::subdivide_recursive` (existe déjà) ou nouvelle `aggregate_cubes(cubes, level)`.
- `muninn/ui/neuron_map.py` :
  - State `_zoom_level: int` (1, 2 ou 3).
  - `_aggregate_to_level()` : reduce les cubes affichés selon le niveau.
  - Hook sur wheel event ou bouton zoom : change `_zoom_level` et repaint.
- `muninn/ui/cube_live.py` : émettre les `cubes_payload` pour les 3 niveaux (déjà calculés par `reconstruct_adaptive` qui itère `level in [1, num_levels]`).

**Spec technique** :
- x1 : N cubes (le scan donne N).
- x2 : ceil(N/2) molécules. NCD = moyenne pondérée par token_count.
- x3 : ceil(N/4) cellules. Idem.
- Edges x2/x3 : agrégation des `mycelium_neighbors` des cubes constituants (union).

**Tests à ajouter** (`tests/test_chunk7_2026-05-19_fractal_zoom.py`) :
- `test_aggregate_x2_halves_count`
- `test_aggregate_x3_averages_ncd`
- `test_zoom_level_changes_paint`

**Coût** : ~80 LOC engine + ~50 LOC UI + 3 tests. **Estimation 2h30.**

**Critère de done** : molette de souris → zoom in/out, transition
visuelle entre 3 niveaux de granularité.

**Dépendances** : CHUNK 5 (NCD propagé jusqu'aux neurons), CHUNK 4
(mode reconstruction actif).

---

## Récap dépendances + estimation totale

```
CHUNK 1 (fuse_risks ordering)       — 2h   — indépendant
CHUNK 2 (subdivide mycelium-aware)  — 3h   — indépendant
CHUNK 3 (neighbors live refresh)    — 1h30 — bénéficie de C1
CHUNK 4 (toggle UI mode)            — 1h   — indépendant
CHUNK 5 (DetailPanel enrichi)       — 3h   — bénéficie de C4
CHUNK 6 (file heatmap view)         — 4h   — dépend C5
CHUNK 7 (fractal zoom)              — 2h30 — dépend C5 + C4
                                    ───
                                    17h total
```

**Ordre suggéré (DAG topologique)** :
C1 → C2 → C3 → C4 → C5 → C6 → C7.
Possible parallélisation C2//C4 si on est deux mais on est seul ici.

---

## Garde-fous transversaux

À CHAQUE chunk :

1. **Forge (RULE 5)** : `forge --gen-props <file>` sur tout fichier touché
   dans `engine/core/`. Les fichiers `muninn/ui/*` n'ont pas de fonctions
   publiques module-level (déjà vérifié) → forge skip propre.

2. **Tests verts locaux** : `pytest tests/ -q --tb=no` doit passer avant
   push. 11 fails connus pré-existants à filtrer (test_a2_1_arithmetic
   xfail, test_retrieval_benchmark, test_wire_auto_label_zones,
   test_tier3_p41, etc. — tous documentés dans CHANGELOG.md 2026-05-19).

3. **Pipeline_trace event** : chaque chunk ajoute au moins 1 event
   `pipeline.<layer>.<action>` pour rendre observable depuis le sandbox
   monitoring.

4. **CHANGELOG entry** + **WINTER_TREE snapshot** à chaque chunk poussé.

5. **Pas de hardcode** (RULE 1) : tout chemin/chiffre tunable via env
   ou constante module-level.

6. **Pas de mirror BUG-091** : depuis hier `muninn/_engine.py` est un
   shim, et tous les autres modules dans `muninn/*.py` aussi. On modifie
   uniquement `engine/core/*.py` et les shims importent automatiquement.

---

## Ce qui est volontairement HORS scope de ce plan

- Migration COBOL/Java AST réel (les heuristiques actuelles + scan
  universel UTF-8 couvrent 99 % des cas observés ; AST natif = projet
  séparé).
- Multi-modèle simultané (qwen-7b + deepseek + llama) — la session du
  2026-05-18/19 a montré que qwen2.5-coder:7b sur sandbox single-host
  fait déjà tourner la reco. Multi-modèle = optimisation, pas
  blocker.
- Auto-réparation des cubes red après cycle 3 (Phase 3 du HEATMAP_PLAN
  parle de "auto_repair" — la fonction existe `engine/core/cube_analysis.py`
  mais c'est un autre chantier).

---

## Critère global de "Done"

Quand tous les 7 chunks sont mergés sur main avec CI verte, le pipeline
Sky décrivait depuis le début est implémenté **end-to-end** :

1. `/scan` produit le mycélium + neuron map.
2. `subdivide_file(mycelium=m)` découpe les cubes alignés sur les zones
   conceptuelles.
3. `fuse_risks` ordonne la reco du moins risqué au plus risqué.
4. `reconstruct_adaptive` cycles x1/x2/x3, feedback continu au mycélium
   (observe_text + observe_failure).
5. Le user voit en live :
   - Toggle Mycelium/Reconstruction sur le cube 3D.
   - Cube reco avec géométrie organique (Laplacien + edges mycélium —
     déjà fait hier).
   - DetailPanel avec SHA/NCD/gaps/unknown idents au clic.
   - Vue fichier line-by-line à côté pour le diagnostic banquier-style.
   - Zoom x1/x2/x3 pour passer du détail à l'overview.

Le scan définit la structure → la reco la suit → forge classe le risque
→ mycélium apprend en boucle. C'est le concept de départ, livré au
complet.
