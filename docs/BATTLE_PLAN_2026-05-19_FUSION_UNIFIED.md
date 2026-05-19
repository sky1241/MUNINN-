# Battle Plan — Fusion Unified (2026-05-19)

> **But final** : tout ce qu'on a planifié sur la reconstruction
> est livré, chunk par chunk, testé, forgé, wiré, en production.
> À la fin : `muninn-mem cube run` et `muninn-ui` exécutent un
> pipeline complet scan→subdivide(mycelium)→fuse_risks→reco
> cycles→UI vivant.
>
> **Source** : fusion de
> [`BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE.md`](BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE.md)
> (perf engine) + [`BATTLE_PLAN_2026-05-19_RECO_SCAN_FUSION.md`](BATTLE_PLAN_2026-05-19_RECO_SCAN_FUSION.md)
> (archi + UX).
>
> **Méthode** : 4 agents d'audit fresh, output verbatim,
> dépendances mappées. Aucune paraphrase optimiste.
>
> **Workflow par chunk** :
> READ → TEST PIN → RED → FIX → GREEN → WIRE → END-TO-END → CLEAN → FORGE → COMMIT → PUSH → CI vert
> *(1 chunk = 1 commit = 1 push = 1 CI vert avant le suivant)*

---

## 0. État vérifié 2026-05-19 (audit triple : original + fusion + hallucination-check)

Trois passes d'audit consécutives, dont une dédiée à vérifier que chaque
claim du plan correspond à du code existant (file:line + verbatim).
**Score final** : 20 / 24 claims TRUE, 4 corrections appliquées
(orchestrator insertion point, fuse_risks default weights, ForestToggle
réutilisation, test infra patterns absents). Le plan ci-dessous reflète
l'état corrigé.



### 0.1 Du plan CUBE_TRUE_ONE — 3/4 claims toujours valides

| Claim | Status | File:Line preuve |
|---|---|---|
| BUG WAGON SHA-256 jamais updaté après reco | ✅ STILL VALID | [cube_analysis.py:145-149](../engine/core/cube_analysis.py#L145-L149) — pas de `cube.sha256 = ...` après `cube.content = result.reconstruction` |
| `record_cycle` non-batch (INSERT+commit par row) | ✅ STILL VALID | [cube.py:1078-1088](../engine/core/cube.py#L1078-L1088) — pas de `record_cycles()` plural |
| `compute_delta()` jamais appelée | ❌ **FIXED** depuis le plan original | [scanner/orchestrator.py:347](../engine/core/scanner/orchestrator.py#L347) — `delta = compute_delta(hashes, cache_path)` ACTIF |
| `healed = set()` recréé vierge à chaque run | ✅ STILL VALID | [cube_analysis.py:1116](../engine/core/cube_analysis.py#L1116) — pas de persistance DB |

### 0.2 Du plan RECO_SCAN_FUSION — toutes features missing

| Feature | Codé | Branché | Prod | Note |
|---|---|---|---|---|
| `fuse_risks` runtime call | ✅ | ❌ | ❌ | Définie [cube_analysis.py:1544](../engine/core/cube_analysis.py#L1544), zéro call site |
| `subdivide_file(mycelium=)` | ❌ | — | — | Signature actuelle: `(file_path, content, target_tokens, level)` |
| `mycelium_neighbors` live refresh | partiel | partiel | partiel | [cube_live.py:246-276](../muninn/ui/cube_live.py#L246) calc pre-reco only |
| UI toggle Mycelium↔Reconstruction | partiel | partiel | stub | [shortcuts.py:56-58](../muninn/ui/shortcuts.py#L56-L58) Space bound, [main_window.py:252](../muninn/ui/main_window.py#L252) lambda no-op |
| DetailPanel SHA/NCD/gaps/unknown | ❌ | — | — | `show_neuron` n'accepte pas ces clés |
| File line-by-line heatmap view | ❌ | — | — | Aucun `file_heatmap_view.py` |
| Fractal x1/x2/x3 zoom | ❌ | — | — | Pas de `_zoom_level`, `aggregate_to_level` |

### 0.3 Forge — split en 3 chunks atomiques

L'audit a montré que le wire forge n'est pas UN chunk mais **3 chunks
orthogonaux** :

- **F0** : infra cache (réuser `get_repo_risk()` partout, 1 endroit)
- **F1** : file-level priority (sort des fichiers par risque)
- **F2** : cube-level fusion (sort des cubes par `fuse_risks` dans un fichier)

---

## 1. Plan unifié — 14 chunks ordonnés (C0 → C13)

### Conventions communes

- **Workflow** : READ→TEST PIN→RED→FIX→GREEN→WIRE→END-TO-END→CLEAN→FORGE→COMMIT→PUSH→CI vert.
- **Forge** : `forge --gen-props <file>` sur chaque fichier `engine/core/` touché. Skip propre sur les fichiers UI (`muninn/ui/*` n'ont pas de public functions module-level).
- **No-touch zones** ([CUBE_TRUE_ONE §3](BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE.md#3-no-touch-zones-ce-qui-doit-rester-intact)) : 15 tests critiques + contrats publics `cli_run` / `CubeStore` / clés JSON output.
- **No mirror BUG-091** : depuis 2026-05-19 (commit `4ff59c7`), tous les modules `muninn/*.py` sont shims. Seul `engine/core/*.py` modifié.
- **Trace event** : chaque chunk ajoute au moins 1 `pipeline.<layer>.<action>` pour l'observabilité.
- **CHANGELOG + WINTER_TREE** mis à jour à chaque chunk poussé.
- **Pas de hardcode** (RULE 1) : tout chiffre tunable = constante module ou env var.

---

### CHUNK 0 — Fix LLM mode collapse (repetition_penalty + temperature)

**Sévérité** 🔴 Haute (prérequis qualité — sans ça les autres chunks
livrent vert mais le user voit toujours du babillage) • **LOC** ~5 •
**Risque** Bas • **Estimation 20 min**

#### Problème
qwen2.5-coder:1.5b et même :7b sur sandbox local boucle sur certains
tokens (`returning, returning, returning…`). Cause classique : pas de
repetition_penalty + temperature=0 (déterministe → boucle). Documenté
dans `docs/STATUS_2026-05-18_RECO_GEOMETRY.md`.

#### Spec
- [engine/core/cube_providers.py::OllamaProvider](../engine/core/cube_providers.py) `generate` et `fim_generate` : ajouter `'repeat_penalty': 1.15` et `'temperature': 0.2` aux `options` Ollama (3 sites).
- Constantes module :
  ```python
  _OLLAMA_REPEAT_PENALTY = float(os.environ.get("MUNINN_LLM_REPEAT_PENALTY", "1.15"))
  _OLLAMA_TEMPERATURE = float(os.environ.get("MUNINN_LLM_TEMPERATURE", "0.2"))
  ```
- Pipeline_trace event `pipeline.engine.llm.options_applied` 1 fois au boot du provider.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C0_llm_no_collapse.py` :
- `test_ollama_provider_sends_repeat_penalty_option` — mock requests.post, assert payload contains `repeat_penalty=1.15`.
- `test_temperature_overridable_via_env` — env `MUNINN_LLM_TEMPERATURE=0.5`, assert payload temperature=0.5.
- `test_default_values_when_no_env` — sans env, assert 1.15 / 0.2.

#### Forge
- `forge --gen-props engine/core/cube_providers.py`.

#### Critère done
- Sandbox run sur btree_google.go avec qwen2.5-coder:1.5b → terminal n'affiche plus de bouclage type "returning, returning…".

---

### CHUNK 1 — Fix BUG WAGON SHA-256 (foundation, x2-x5 gain)

**Sévérité** 🔴 Haute • **LOC** 1 • **Risque** Bas • **Estimation 20 min**

#### Spec
- [cube_analysis.py:148](../engine/core/cube_analysis.py#L148) après `cube.content = result.reconstruction` :
  ```python
  cube.sha256 = sha256_hash(result.reconstruction)
  ```
- `sha256_hash` est déjà importé depuis `cube.py`.

#### Tests à ajouter (nouveau fichier)
`tests/test_chunk_2026-05-19_C1_wagon_sha.py` :
- `test_cube_sha256_updated_after_reconstruction` — crée cube `sha=ABC`, mock LLM retourne `NEW`, assert `cube.sha256 == sha256_hash(NEW)` après save_cube.
- `test_wagon_sha_match_cycle2` — 2 cycles consécutifs, cycle 2 `exact_match=True` puisque sha cohérent.

#### Forge
- `forge --gen-props engine/core/cube_analysis.py` + `pytest tests/test_props_cube_analysis.py -q`.

#### Critère done
- Tests RED→GREEN, baseline test_cube_b16/b19/wiring tous PASS, CI vert.

---

### CHUNK 2 — Batch `record_cycles` via executemany (perf x250)

**Sévérité** 🟠 Moyenne • **LOC** ~15 • **Risque** Moyen • **Estimation 1h**

#### Spec
- [cube.py:1078](../engine/core/cube.py#L1078) : ajouter méthode publique
  ```python
  def record_cycles(self, batch: list[tuple[str, int, bool, str, float]]) -> None:
      with self._lock:
          self.conn.executemany(
              "INSERT INTO cycles (cube_id, cycle_num, success, reconstruction, perplexity, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
              [(*row, _time.time()) for row in batch],
          )
          self.conn.commit()
  ```
- [cube_analysis.py:130-160](../engine/core/cube_analysis.py#L130-L160) : accumuler `cycle_batch.append((...))` dans la boucle, appeler `store.record_cycles(cycle_batch)` une fois après.
- `record_cycle` (singulier) conservé pour backward-compat des tests.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C2_record_cycles_batch.py` :
- `test_record_cycles_uses_executemany` — patch `conn.executemany`, assert call_count == 1 même si 100 records.
- `test_record_cycles_persists_all_rows` — insère 50 records via batch, SELECT COUNT(*) == 50.
- `test_record_cycle_singular_still_works` — backward-compat.

#### Forge
- `forge --gen-props engine/core/cube.py engine/core/cube_analysis.py`.

#### Critère done
- 24s gagnés sur run 1000 cubes mesurable via `time muninn-mem cube run`.

---

### CHUNK 3 — `healed` set persistant cross-run (perf x3-x5)

**Sévérité** 🟠 Moyenne • **LOC** ~20 • **Risque** Bas • **Estimation 1h**

#### Spec
- [cube.py](../engine/core/cube.py) : ajouter
  ```python
  def get_healed_cubes(self, min_success_count: int = 3,
                      min_success_rate: float = 1.0) -> set[str]:
      """Cubes with N+ cycles, all successful — skip in future runs."""
      with self._lock:
          rows = self.conn.execute("""
              SELECT cube_id FROM cycles
              GROUP BY cube_id
              HAVING COUNT(*) >= ? AND MIN(success)=1 AND MAX(success)=1
          """, (min_success_count,)).fetchall()
      return {r[0] for r in rows}
  ```
- [cube_analysis.py:1116](../engine/core/cube_analysis.py#L1116) : `healed = store.get_healed_cubes()` (était `set()`).
- Constantes module pour les seuils.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C3_healed_persistent.py` :
- `test_healed_loaded_from_db_when_min_success_satisfied`
- `test_healed_excludes_cubes_with_failure_history`
- `test_healed_empty_when_first_run`

#### Forge
- `forge --gen-props engine/core/cube.py`.

#### Critère done
- Run 2 d'un fichier déjà 100% SHA → 0 LLM calls, tous cubes skipped.
- Dépendance : CHUNK 1 (sha cohérent) sinon healed jamais peuplé correctement.

---

### CHUNK 4 — Forge cache infrastructure (F0)

**Sévérité** 🟡 Moyenne • **LOC** ~15 • **Risque** Bas • **Estimation 30 min**

#### Spec
- [engine/core/forge_metrics.py](../engine/core/forge_metrics.py) : exposer
  ```python
  _RISK_MAP_CACHE: dict[Path, tuple[float, dict[str, float]]] = {}

  def get_file_risk_map(repo: Path, ttl: float = 86400.0) -> dict[str, float]:
      """Repo-level risk map (file→score), cached TTL 24h.
      Wraps get_repo_risk() to expose a flat dict reusable by F1 (file
      ordering) and F2 (cube fusion).
      """
  ```
- Pipeline_trace event `pipeline.forge.risk_map_cached` avec `repo, n_files, age_s`.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C4_forge_cache.py` :
- `test_get_file_risk_map_cached_within_ttl`
- `test_get_file_risk_map_refresh_after_ttl_expires`
- `test_fallback_empty_dict_when_forge_unavailable`

#### Forge
- `forge --gen-props engine/core/forge_metrics.py`.

#### Critère done
- 2 appels successifs dans une même session : 1 vrai forge run, 1 cache hit.

---

### CHUNK 5 — Forge file-level priority (F1, ex-A:7)

**Sévérité** 🟠 Moyenne • **LOC** ~10 • **Risque** Bas • **Estimation 1h**

#### Spec (audit 2026-05-19 : insertion points corrigés)
- [engine/core/scanner/orchestrator.py:577](../engine/core/scanner/orchestrator.py#L577) (regex scan path) ET [orchestrator.py:594](../engine/core/scanner/orchestrator.py#L594) (LLM scan path) — c'est là que `files_to_scan` et `llm_files` sont itérés. **Avant ces boucles**, sort la liste par `get_file_risk_map(repo).get(str(f), 0.0)` décroissant.
- Si `MUNINN_FORGE_FILE_ORDERING=0`, skip le sort (legacy disk order).
- Pipeline_trace event `pipeline.forge.file_ordering_applied` avec top-3 hot files.

**Note** : `orchestrator.py:347` (mentionné dans une version précédente de ce plan) est juste un return statement de helper `compute_delta`, PAS le point d'itération. Audit corrigé.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C5_file_priority.py` :
- `test_files_sorted_by_forge_risk_descending`
- `test_fallback_unsorted_when_forge_unavailable`

#### Forge
- `forge --gen-props engine/core/muninn.py`.

#### Critère done
- Le run scan affiche les fichiers à risque en premier dans la trace.

---

### CHUNK 6 — Forge cube-level fusion in `reconstruct_adaptive` (F2, ex-B:1)

**Sévérité** 🔴 Haute • **LOC** ~60 • **Risque** Moyen • **Estimation 2h**

#### Spec
- [cube_providers.py::reconstruct_adaptive](../engine/core/cube_providers.py) signature étendue (la signature actuelle accepte déjà `mycelium=None` — audit l.1913-1919 confirmé) :
  ```python
  def reconstruct_adaptive(file_path, content, provider, base_tokens=112,
                           max_cycles=3, attempts_per_cube=11,
                           mycelium=None, forge_root=None,
                           on_cube=None) -> dict:
  ```
- Si `forge_root` fourni + `CubeStore` accessible : appeler `fuse_risks(store, forge_root)` une fois pour obtenir le dict `{cube_idx: combined_risk}`.
- **Poids par défaut** : la signature actuelle de `fuse_risks` utilise `forge_weight=0.4, cube_weight=0.6` (audit confirmé l.1544-1546). Le plan respecte ces defaults. Tunables via env `MUNINN_FUSE_FORGE_WEIGHT` et `MUNINN_FUSE_CUBE_WEIGHT` si besoin.
- `_run_level_pass` trie `to_test` par `combined_risk` croissant (low first → contexte stable).
- Fallback silencieux : ordre séquentiel naturel si forge indispo.
- [cube_live.py](../muninn/ui/cube_live.py) `ReconstructionWorker` calcule `forge_root = repo_root` et passe à `reconstruct_adaptive`.
- Pipeline_trace events `pipeline.engine.reco.cube_ordering_applied` + `pipeline.forge.fuse_risks_used`.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C6_fuse_risks_wired.py` :
- `test_reconstruct_adaptive_sorts_cubes_by_risk_when_forge_root_given`
- `test_fallback_sequential_order_when_forge_root_none`
- `test_low_risk_cubes_processed_first_in_level_pass`
- `test_pipeline_trace_event_fuse_risks_used`

#### Forge
- `forge --gen-props engine/core/cube_providers.py`.

#### Critère done
- Sandbox run : ordre des cubes traités visible dans pipeline_trace correspond au combined_risk croissant.

---

### CHUNK 7 — `subdivide_file` mycelium-aware

**Sévérité** 🔴 Haute (THE archi fix) • **LOC** ~80 • **Risque** Moyen • **Estimation 3h**

#### Spec
- [engine/core/mycelium.py](../engine/core/mycelium.py) : nouveau helper
  ```python
  def concept_to_file_lines(content: str, mycelium_db, regex: str = r"[A-Za-zÀ-ÿ_]{3,}") -> dict[int, set[str]]:
      """For each line in content, set of concepts that line touches (∩ codebook mycelium)."""
  ```
  Constante `_CONCEPT_REGEX` partagée (déjà dans `muninn/ui/cube_live.py:_MYCELIUM_CONCEPT_REGEX`).

- [engine/core/cube.py](../engine/core/cube.py) : nouveau helper
  ```python
  def find_concept_boundaries(content: str, mycelium, target_tokens: int = 112) -> list[int]:
      """Line numbers where dominant zone changes. Uses mycelium.detect_zones()
      + concept_to_file_lines. Returns [] if <2 zones (fallback to uniform)."""
  ```

- [engine/core/cube.py::subdivide_file](../engine/core/cube.py#L772) signature :
  ```python
  def subdivide_file(file_path, content, target_tokens=TARGET_TOKENS,
                     level=0, mycelium=None) -> list[Cube]:
  ```
  **Si mycelium fourni : pure zone-based découpage** (révision Sky 2026-05-19) :
  - boundaries = `find_concept_boundaries(content, mycelium, target_tokens)` — line numbers où la zone dominante change.
  - Cubes = ranges entre 2 boundaries consécutives, **peu importe le token count**.
  - `target_tokens` devient un **plafond** : si une zone > 2 × target_tokens, split intra-zone par minima locaux de densité conceptuelle (points dans la zone où le moins de concepts mycelium sont actifs — probable transition logique mineure).
  - Zones petites (< target_tokens / 2) → fusion avec la zone voisine **la plus cohérente sémantiquement** (Jaccard concepts > 0.3).
  - Cubes peuvent être hétérogènes (60 tokens / 200 tokens / 400 tokens) — c'est OK, c'est cohérent sémantiquement.

  Sinon (mycelium=None) fallback comportement actuel token-uniform.

  **Justification du pure zone-based** : 1 cube = 1 unité logique du code (fonction, méthode, bloc cohérent). Le LLM reconstruit mieux une fonction entière qu'un fragment de 112 tokens coupé en plein milieu d'une boucle. SHA match ne dépend pas de la taille du cube. C'est l'idée originale du pipeline Muninn — scan définit la structure, reco s'aligne dessus.

- 4 call sites mis à jour pour passer `mycelium=mycelium` quand dispo :
  - cube_live.py:143
  - cube_providers.py:1970, 2005, 2062
  - cube_analysis.py:1050 reste sans mycelium (path CLI batch — optionnel plus tard).

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C7_subdivide_mycelium.py` :
- `test_subdivide_falls_back_when_no_mycelium`
- `test_subdivide_respects_zone_boundaries`
- `test_concept_to_file_lines_returns_per_line_set`
- `test_find_concept_boundaries_empty_when_under_2_zones`
- `test_btree_google_cube_count_matches_function_boundaries` (intégration sur `tests/cube_corpus/btree_google.go`)
- `test_combined_with_fuse_risks_produces_consistent_ordering` (C6 × C7 interaction : assert que cube_order après `fuse_risks(store, forge)` est stable peu importe le découpage)

#### Tests existants à mettre à jour
- `tests/test_cube_b1_b6.py::test_small_file_single_cube` — assertion `len(cubes) == 1` peut casser si mycelium passé. Décorer `@pytest.mark.parametrize("mycelium", [None])` pour lock le comportement uniform-token quand pas de mycelium, et ajouter un nouveau test parametré qui exerce avec mycelium.
- `tests/test_cube_b1_b6.py::test_large_file_multiple_cubes` — vérifier que la nouvelle signature ne casse pas (la fonction accepte un 5e param optionnel rétro-compat).

#### Forge
- `forge --gen-props engine/core/cube.py engine/core/mycelium.py`.

#### Critère done
- Sur btree_google.go avec mycélium populé, les `cube.line_start` matchent des frontières de fonctions/types Go (visuel + assertion).

---

### CHUNK 8 — `mycelium_neighbors` live refresh entre cycles ✅ LIVRÉ 2026-05-19

**Sévérité** 🟡 Moyenne (UX vivante) • **LOC** ~40 • **Risque** Bas • **Estimation 1h30**

> ✅ Livré : helper `_compute_mycelium_neighbors`, signal
> `cube_neighbors_refreshed`, slot `NeuronMapWidget.refresh_neighbors`,
> wiring terminal→main_window. Flag `MUNINN_NEIGHBORS_LIVE_REFRESH`.
> 7/7 tests `test_chunk_2026-05-19_C8_neighbors_refresh.py`.

#### Spec
- [cube_live.py:246](../muninn/ui/cube_live.py#L246) : extraire calc en méthode `_compute_neighbors(cubes_payload)`.
- Hook : appeler depuis le callback `on_cube` quand `status == "CYCLE_END"`.
- Nouveau signal `cube_neighbors_refreshed(list[list[int]])` ou réémission de `cubes_ready` modifié.
- [neuron_map.py::set_reconstruction_cubes](../muninn/ui/neuron_map.py) : nouvelle méthode `refresh_edges(new_neighbors)` qui ne rebuilds pas les neurons, juste les edges + Laplacian.
- Pipeline_trace event `pipeline.ui.cube_live.neighbors_refreshed` avec `cycle, n_edges_old, n_edges_new`.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C8_neighbors_refresh.py` :
- `test_neighbors_refresh_emits_signal_per_cycle`
- `test_neighbor_count_grows_when_mycelium_grows_between_cycles`
- `test_refresh_edges_keeps_existing_neurons`

#### Forge
- N/A (UI files, no public funcs).

#### Critère done
- Screenshot temporel sandbox : clusters qui se réorganisent entre les cycles.

---

### CHUNK 9 — UI toggle Mycelium↔Reconstruction (vrai bouton) ✅ LIVRÉ 2026-05-19

**Sévérité** 🟡 Moyenne • **LOC** ~50 • **Risque** Bas • **Estimation 1h**

> ✅ Livré : `NeuronMapWidget._color_mode` + `set_color_mode` +
> `toggle_color_mode` ; widget `ColorModeToggle` companion overlay
> top-right neuron panel ; palette `toggle_mode` action wirée.
> Persistance via `~/.muninn/ui_config.json` (`neuron_color_mode`).
> 10/10 tests `test_chunk_2026-05-19_C9_color_mode_toggle.py`.

#### Spec (audit 2026-05-19 : clarification — `ForestToggle` solo/forest existe DÉJÀ, on l'étend)
- [muninn/ui/forest.py:123-171](../muninn/ui/forest.py#L123-L171) `ForestToggle` existe déjà avec signal `mode_changed(str)` ("solo"/"forest"). Le Space shortcut ([shortcuts.py:26-29](../muninn/ui/shortcuts.py#L26-L29) → `_toggle_mode` l.56-58) appelle déjà `_forest_toggle.toggle()`.
- **Ce chunk étend ce mécanisme** en ajoutant une 2e dimension de mode : neuron_map color source.
- [neuron_map.py](../muninn/ui/neuron_map.py) :
  - Field `self._color_mode = "mycelium"` à l'init (distinct du solo/forest).
  - Méthode `set_color_mode(mode: str)` qui repaint sans rebuild.
  - Dans `_paint_neurons` (~l.592), conditionner la source de couleur sur `_color_mode`.
- Étendre `ForestToggle` ou créer `ColorModeToggle` companion. Placement : 2 toggles côte-à-côte top-right neuron panel.
- [main_window.py:252](../muninn/ui/main_window.py#L252) `toggle_mode` action du command palette : remplacer le lambda no-op par `self.neuron_panel.toggle_color_mode()`.
- Persistance dans `~/.muninn/ui_config.json` (clé `neuron_color_mode`).

**Note** : le Space shortcut existant fonctionne déjà pour solo/forest. Ce chunk N'enleve PAS ce comportement, il ajoute le toggle color en parallèle.

#### Tests à ajouter
`tests/test_ui_neuron_map.py` (extension) :
- `test_mode_toggle_changes_paint_source`
- `test_set_mode_invalid_ignored`
- `test_mode_persists_via_ui_config`

#### Forge
- N/A (UI).

#### Critère done
- Clic sur le bouton → couleurs basculent immédiatement entre degree (mycelium) et NCD (reco).

---

### CHUNK 10 — DetailPanel enrichi (SHA / NCD / gaps / unknown identifiers)

**Sévérité** 🟠 Moyenne (info critique) • **LOC** ~180 (engine + UI) • **Risque** Moyen • **Estimation 3h**

#### Spec engine
- [cube_providers.py::ReconstructionResult](../engine/core/cube_providers.py) : ajouter
  ```python
  gap_lines: list[int] = field(default_factory=list)
  unknown_identifiers: list[str] = field(default_factory=list)
  ```
- [cube_providers.py::reconstruct_cube](../engine/core/cube_providers.py) après reco, calculer :
  - `gap_lines = [i for i in range(n_lines) if i not in anchor_map]` (inverse de `_build_full_anchor_map`)
  - `unknown_identifiers = re.findall(regex, reconstruction) - ast_hints["identifiers"]`
- [cube_providers.py::WaveResult](../engine/core/cube_providers.py) : propage les 2 champs.
- [cube_live.py::on_cube](../muninn/ui/cube_live.py) : payload `cube_done` enrichi.

#### Spec UI
- [neuron_map.py::Neuron](../muninn/ui/neuron_map.py) : ajouter champs `gap_lines: list[int]`, `unknown_idents: list[str]`.
- [detail_panel.py](../muninn/ui/detail_panel.py) :
  - `_sha_label` (QLabel icône ✓/✗).
  - `_ncd_bar` (QProgressBar coloré SUCCESS/WARNING/ERROR).
  - `_gaps_section` (QListWidget, clic → emit `gap_clicked(line_no)`).
  - `_unknowns_section` (idem).
  - Cachés en mode Mycelium pur.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C10_recon_result_extras.py` + extension `tests/test_ui_detail_panel.py` :
- `test_reconstruction_result_carries_gap_lines`
- `test_unknown_identifiers_diff_against_ast_hints`
- `test_detail_panel_shows_sha_when_sha_match`
- `test_detail_panel_hides_reco_fields_in_mycelium_mode`

#### Forge
- `forge --gen-props engine/core/cube_providers.py`.

#### Critère done
- Clic sur un cube rouge dans le sandbox → panel affiche "NCD=0.67, gaps=12 lignes, unknowns=[xyz, foo]".

---

### CHUNK 11 — File line-by-line heatmap view

**Sévérité** 🟡 Moyenne (banquier UX) • **LOC** ~200 • **Risque** Moyen • **Estimation 4h**

#### Spec
- Nouveau widget `muninn/ui/file_heatmap_view.py` :
  - QPlainTextEdit read-only avec syntax highlighting (réuse theme).
  - Marge gauche custom paintEvent → bandeau couleur par ligne :
    - Vert : ligne ancrée (présente dans anchor_map d'un cube).
    - Rouge : gap (NON dans anchor_map).
    - Orange : gap mais SHA match quand même (faux positif chanceux).
  - Click sur ligne → emit `line_clicked(int)`.
- [main_window.py](../muninn/ui/main_window.py) : ajouter widget en **bottom panel** (split horizontal sous le cube 3D, tranché 2026-05-19). Sync visuelle cube ↔ fichier en parallèle.
- [cube_live.py](../muninn/ui/cube_live.py) : nouveau signal `file_heatmap_ready(path, dict[int, str])`.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C11_file_heatmap.py` :
- `test_line_colors_derived_from_anchor_map`
- `test_orange_for_gap_with_sha`
- `test_click_emits_line_signal`

#### Forge
- N/A (UI).

#### Critère done
- Ouverture du fichier `btree_google.go` post-reco affiche les 25% lignes ancrées en vert et le reste en rouge/orange.

#### Dépendance
- CHUNK 10 (ReconstructionResult.gap_lines disponible).

---

### CHUNK 12 — Fractal x1/x2/x3 zoom visual

**Sévérité** 🟢 Basse (polish) • **LOC** ~130 • **Risque** Bas • **Estimation 2h30**

#### Spec
- [neuron_map.py](../muninn/ui/neuron_map.py) :
  - Field `self._zoom_level: int = 1` (1, 2, 3).
  - Méthode `_aggregate_to_level(cubes, level)` qui réduit N cubes à ceil(N/level) molécules (moyenne pondérée NCD par token_count).
  - Hook wheel event ou bouton zoom → change `_zoom_level` et repaint.
- [cube_live.py](../muninn/ui/cube_live.py) : émettre les payloads pour les 3 niveaux (engine itère déjà `level in [1, num_levels]`).
- Edges x2/x3 : union des `mycelium_neighbors` des cubes constituants.

#### Tests à ajouter
`tests/test_chunk_2026-05-19_C12_fractal_zoom.py` :
- `test_aggregate_x2_halves_count`
- `test_aggregate_x3_averages_ncd_weighted_by_tokens`
- `test_zoom_level_changes_paint`

#### Forge
- N/A (UI).

#### Critère done
- Molette de souris → transitions visuelles entre 3 niveaux de granularité.

#### Dépendances
- CHUNK 10 (NCD propagé jusqu'aux neurons).
- CHUNK 9 (mode reconstruction actif pour que le zoom ait du sens).

---

### CHUNK 13 — E2E pipeline + benchmark + sandbox smoke test

**Sévérité** 🔴 Haute (preuve globale — sans ça on commit sur foi) •
**LOC** ~150 + helpers • **Risque** Bas • **Estimation 2h30**

#### Pré-établir 3 patterns test (audit 2026-05-19 : aucun n'existe aujourd'hui)
1. **HTTP mocking Ollama** : pas de pattern actuel (pas de `responses` lib, pas de monkeypatch urllib). Établir un helper `tests/_helpers/mock_ollama.py` qui patch `urllib.request.urlopen` pour retourner un payload Ollama JSON simulé. Utilisable depuis C0 (xfail jusqu'à C13 si pas dispo).
2. **Pipeline_trace assertions** : pas de fixture actuelle. Créer `tests/_helpers/pipeline_trace.py::read_trace_events(repo)` qui lit `.muninn/pipeline_trace.jsonl` et retourne `list[dict]`. Utilisable par tous les tests qui asservent un event.
3. **Benchmark harness** : pas de `pytest-benchmark` (`@pytest.mark.benchmark` absent). Établir une convention `def test_perf_*` qui utilise `time.perf_counter()` brut + skipif `os.environ.get("MUNINN_RUN_PERF", "0") != "1"` (perf tests opt-in, pas dans le run CI normal).

#### Spec
**Test E2E global** : `tests/test_pipeline_e2e_2026-05-19.py`
- `test_full_pipeline_scan_to_reco_on_btree_google_go` :
  1. Scan `tests/cube_corpus/btree_google.go` → vérifie mycelium.db créé, codebook populé.
  2. `cube run` sur le scan target avec `forge_root` + `mycelium` + 2 cycles, MockLLMProvider.
  3. Assertions :
     - `cubes_active` décroit cycle après cycle (preuve healed + skip).
     - `fuse_risks` apparaît dans pipeline_trace events (preuve C6 wiré).
     - `subdivide_file` produit cubes avec line_start aligné sur fonctions Go (preuve C7 wiré).
     - `healed` set restauré au run 2 (preuve C3 wiré).
- `test_pipeline_metrics_match_promised_speedups` :
  - Run baseline (env `MUNINN_FUSE_RISKS_ORDERING=0 MUNINN_SCAN_AWARE_SUBDIVIDE=0`) sur 100 cubes mocks.
  - Run optimized (defaults) sur le même corpus.
  - Assert que optimized fait au moins 2x moins d'appels LLM (preuve C1+C2+C3+C6 wired ensemble).

**Benchmark** : `tests/test_perf_cube_run_2026-05-19.py`
- `test_perf_record_cycles_batch_under_5s_for_1000` : mesure le temps de `store.record_cycles(batch_of_1000)`. Doit être < 5s.
- `test_perf_subdivide_file_under_200ms_for_btree` : `subdivide_file(btree_google_go, mycelium=m)` doit retourner en < 200ms (cache hit mycélium concepts).
- `test_perf_fuse_risks_under_500ms_for_100_cubes` : `fuse_risks(store, forge_root)` sur 100 cubes < 500ms.
- Skipper si `time` env non dispo (CI ne mesure pas perf en strict).

**Sandbox smoke (manuel, documenté)** :
- Document `docs/SANDBOX_SMOKE_2026-05-19.md` qui liste les 5 actions manuelles à faire après chaque chunk UX :
  1. `./run-ui.sh` dans muninn-sandbox
  2. `/scan /tmp/btree-only`
  3. Vérifier cube 3D affiche clusters organiques (C9 mode reco)
  4. Clic sur un neuron → DetailPanel affiche NCD/gaps (C10)
  5. Toggle Space → bascule mycelium↔reco (C9)
  6. Molette → zoom x1↔x2↔x3 (C12)
  7. Screenshot final inclus dans le PR commit body.

#### Forge
- `forge --gen-props engine/core/cube_analysis.py engine/core/cube.py engine/core/cube_providers.py` (full reforge pour confirmer que les props tests générés depuis le début passent toujours).

#### Critère done
- Test E2E vert sur la chaîne complète.
- Benchmark dans les seuils.
- Smoke sandbox documenté avec screenshot.

#### Dépendances
- TOUS les chunks précédents (C0-C12).

---

## 2. Dépendances + chemin critique

```
C0 LLM repeat_penalty (prérequis qualité)
 │
 ▼
C1 BUG WAGON SHA  ──┐
C2 record_cycles ───┼──> C3 healed persistent (a besoin de sha cohérent)
                    │
C4 forge cache ─────┴──> C5 file-level priority
                         │
                         └──> C6 fuse_risks cube ordering
                                │
C7 subdivide(mycelium) ─────────┤  (orthogonal mais bénéficie de C6)
                                │
C8 neighbors live refresh ──────┤  (orthogonal)
                                │
C9 UI toggle mode ──────────────┼──> C10 DetailPanel enrichi
                                │     │
                                │     ├──> C11 file heatmap (needs gap_lines)
                                │     │
                                │     └──> C12 fractal zoom (needs NCD)
                                │
                                └──> (C9 prerequisite pour le mode visuel)
 │
 ▼
C13 E2E + benchmark + sandbox smoke (preuve globale)
```

**Chemin critique** :
`C0 → C1 → C2 → C3 → C4 → C5 → C6 → C7 → C8 → C9 → C10 → C11 → C12 → C13`

**Parallélisations possibles** (si plusieurs sessions) :
- C0 indépendant (1 ligne config Ollama), peut tourner même sans le reste
- C7 peut se faire en parallèle de C4-C6 (zone engine vs scan-aware)
- C8 peut se faire en parallèle de C9-C10 (UX live vs UX statique)
- C13 = bouchon final, doit attendre tout le reste

---

## 3. Estimation totale

| Phase | Chunks | Coding | Tests + Forge | Push + CI | Total |
|---|---|---|---|---|---|
| **PRE** LLM mode collapse fix | C0 | 0h05 | 0h10 | 0h05 | **20 min** |
| **A** Engine bugs/perf | C1-C3 | 0h40 | 0h50 | 0h30 | **2h** |
| **B** Forge wiring | C4-C6 | 1h30 | 1h | 0h30 | **3h** |
| **C** Scan-aware archi | C7 | 1h30 | 1h | 0h30 | **3h** |
| **D** UX live | C8-C9 | 1h | 0h45 | 0h15 | **2h** |
| **E** UX enrichi | C10-C12 | 5h | 2h | 0h30 | **7h30** |
| **POST** E2E + benchmark + smoke | C13 | 1h | 0h45 | 0h15 | **2h** |
| **Total** | 14 | | | | **~20h** |

Sky lance 1-3 chunks par session. Pas de marathon.

---

## 4. Garde-fous transversaux

À CHAQUE chunk :

1. **Forge (RULE 5)** : `forge --gen-props <file>` sur tout `engine/core/*.py` touché. Document run count dans le commit message.

2. **Tests locaux** : `pytest tests/ -q --tb=no` doit passer (11 fails connus pré-existants, voir CHANGELOG.md 2026-05-19).

3. **Pipeline_trace event** : au moins 1 `pipeline.<layer>.<action>` ajouté pour observabilité sandbox.

4. **CHANGELOG.md entry** + **WINTER_TREE.md snapshot** mis à jour.

5. **Pas de hardcode** (RULE 1) : tout chiffre/chemin tunable.

6. **Pas de mirror BUG-091** : modifier uniquement `engine/core/*.py`. Les shims `muninn/*.py` re-importent automatiquement.

7. **CI verte** avant chunk suivant. Push intermédiaire OK (revert facile chunk par chunk en cas de drift).

---

## 4bis. Feature flags (rollback chirurgical sans revert)

Chaque comportement nouveau introduit dans C0–C12 est gated par une env
var. Default = activé (nouveau comportement). Bascule à 0 = ancien
comportement, sans revert git. À documenter dans CLAUDE.md à chaque
chunk poussé.

| Env var | Default | Chunk | Bascule désactive |
|---|---|---|---|
| `MUNINN_LLM_REPEAT_PENALTY` | `1.15` | C0 | repeat_penalty (mettre `1.0` = comportement legacy) |
| `MUNINN_LLM_TEMPERATURE` | `0.2` | C0 | temperature (mettre `0.0` = déterministe legacy) |
| `MUNINN_HEALED_PERSISTENT` | `1` | C3 | charger healed depuis DB (0 = recréer set() chaque run) |
| `MUNINN_FORGE_FILE_ORDERING` | `1` | C5 | tri files par forge risk (0 = ordre disque) |
| `MUNINN_FUSE_RISKS_ORDERING` | `1` | C6 | tri cubes par fuse_risks (0 = séquentiel naturel) |
| `MUNINN_SCAN_AWARE_SUBDIVIDE` | `1` | C7 | subdivide mycelium-aware (0 = token-uniform) |
| `MUNINN_NEIGHBORS_LIVE_REFRESH` | `1` | C8 | refresh mycelium_neighbors entre cycles (0 = static pre-reco) |
| `MUNINN_UI_NEURON_MODE` | `"mycelium"` | C9 | mode initial UI (`"reconstruction"` au lieu de `"mycelium"`) |

**Règle** : aucun comportement nouveau n'est imposé. Si un user veut
revenir au legacy pour debug, il bascule la variable et relance. Pas
besoin de fork/branch.

---

## 5. Critère global de "Done"

Quand les 12 chunks sont mergés sur main avec CI verte, la promesse
originale est livrée **end-to-end** :

1. **`/scan <repo>`** → mycélium (concepts + edges) + neuron map JSON.
2. **`subdivide_file(content, mycelium=m)`** → cubes alignés sur les
   frontières conceptuelles, pas un grid uniforme.
3. **`fuse_risks(store, forge_root)`** → ordre des cubes : low risk → high
   risk. Stables comme contexte des fragiles.
4. **`reconstruct_adaptive` cycles x1→x2→x3** avec mycelium qui apprend
   en boucle (`observe_text` sur SHA, `observe_failure` sur fail).
5. **UI vivant** :
   - Toggle Mycelium↔Reconstruction (vrai bouton).
   - Cube géométrie organique (Laplacien + mycelium edges — déjà livré).
   - DetailPanel SHA/NCD/gaps/unknown identifiers au clic.
   - File line-by-line view en parallèle pour diagnostic.
   - Zoom x1/x2/x3 pour passer du détail à l'overview.
   - Neighbors refresh entre cycles (clusters qui bougent en live).
6. **Performance** : `cube run` rapide grâce aux fixes engine (WAGON
   SHA, batch cycles, healed persistent).
7. **Pipeline_trace** observable : chaque action génère un événement
   suivable depuis le sandbox.

**Le scan définit la structure → la reco la suit → forge classe le risque
→ mycélium apprend en boucle → l'UI rend tout ça vivant.** C'est le
concept de départ de Muninn, livré au complet.

---

## 6. Sources

- [docs/BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE.md](BATTLE_PLAN_CUBE_TRUE_ONE_PIPELINE.md) — claims 4 chunks engine perf (rédigé 2026-05-14/15)
- [docs/BATTLE_PLAN_2026-05-19_RECO_SCAN_FUSION.md](BATTLE_PLAN_2026-05-19_RECO_SCAN_FUSION.md) — 7 chunks reco+scan+UX (rédigé 2026-05-19 matin)
- [docs/CUBE_UX_HEATMAP_PLAN.md](CUBE_UX_HEATMAP_PLAN.md) — vision UX 4 phases (rédigé 2026-04)
- [docs/STATUS_2026-05-18_RECO_GEOMETRY.md](STATUS_2026-05-18_RECO_GEOMETRY.md) — état post-CHUNK 10 sandbox
- [docs/ANTI_BULLSHIT_BATTLE_PLAN.md](ANTI_BULLSHIT_BATTLE_PLAN.md) — discipline preuve (RULE 4)
- [CLAUDE.md](../CLAUDE.md) — RULES 1-5, état 2880 PASS / 11 fail (pré-existants)

---

## 8. Règles anti-drift seigneur-dev — contrat qualité par chunk

À cocher mécaniquement avant CHAQUE commit. Si un point n'est pas
respecté, le chunk n'est PAS prêt à push, peu importe la pression.

### A. Definition of Done — checklist mécanique
- [ ] Test RED→GREEN documenté avec output verbatim (pas paraphrase)
- [ ] `pytest tests/ -q --tb=no` baseline maintenue : **2880 passed, 11 failed (pré-existants)**. Si un test pré-existant nouveau apparaît dans les failed → STOP avant push, investiguer.
- [ ] `forge --gen-props <file>` exécuté, output count sauvé (props générées + destructive skipped) dans le commit message
- [ ] Property tests existants (`tests/test_props_*.py`) toujours verts
- [ ] Pipeline_trace event ajouté + LU par un test (pas juste écrit, vérifier qu'on peut le retrouver)
- [ ] Feature flag ON et OFF tous deux testés (cf. règle B ci-dessous)
- [ ] CHANGELOG.md entry + WINTER_TREE.md snapshot mis à jour
- [ ] CLAUDE.md mis à jour si nouvelle env var ajoutée (table § variables d'environnement)
- [ ] CI verte avant chunk suivant
- [ ] Pas de `print()` débug oublié, pas d'import inutile, pas de TODO non documenté

### B. Feature flag dual-testing obligatoire
Pour chaque `MUNINN_*` env var listée en §4bis, le chunk DOIT ajouter
**2 tests** :
- `test_<feature>_when_flag_enabled` : nouveau comportement, flag=1
- `test_<feature>_when_flag_disabled_preserves_legacy` : ancien comportement, flag=0

Sinon le rollback chirurgical est non testé = drift garanti dès qu'un
user bascule la variable en prod.

### C. RULE 4 anti-bullshit dans le commit message
Le **corps du commit** DOIT contenir l'output verbatim de 3 commandes :
```
pytest tests/test_chunk_X.py -q   → "N passed in T.Ts"
forge --gen-props ENGINE/X.py     → "Generated N props, M destructive skipped"
pytest tests/ -q --tb=no          → "X passed, Y failed (pre-existing)"
```
Pas de "tests verts" en paraphrase. Référence stricte :
[docs/ANTI_BULLSHIT_BATTLE_PLAN.md](ANTI_BULLSHIT_BATTLE_PLAN.md).

### D. Forge property fail = bug réel, pas test à désactiver
Si `forge --gen-props` génère une property qui échoue, le Hypothesis
falsifying example **EST** le test case à fixer dans le code.

**Tentation interdite** : commenter le test pour passer la CI. Le bon
move = lire le falsifying example, comprendre l'invariant violé, fixer
la fonction (ou réviser la property si elle est trop large). Cf.
CLAUDE.md RULE 5.

### E. No backwards-incompatible signature dans 1 chunk
Si un chunk change la signature d'une fonction publique, **TOUS** les
callers doivent migrer dans le même commit OU le default doit préserver
le legacy.

Exemple C7 : `subdivide_file(file_path, content, target_tokens=112, level=0, mycelium=None)` — le param `mycelium=None` préserve le legacy car None → fallback uniforme. Pas de "TODO migrate later" sinon drift garanti à la prochaine session.

### F. Pipeline_trace event naming convention formelle
```
event   = "pipeline.<layer>.<action_verb>"
layer   ∈ {cli, engine, ui, mcp, hook, forge, mycelium}
action_verb = snake_case présent (begin / end / applied / cached / refreshed / used)
data    = dict[str, JSON-primitive]  (pas d'objets, pas de Path, pas de datetime)
```
Exemples valides :
- `pipeline.engine.reco.fuse_risks_used` ✓
- `pipeline.forge.file_ordering_applied` ✓
- `pipeline.ui.cube_live.neighbors_refreshed` ✓

Exemples invalides :
- `pipeline.fuseRisks` (camelCase + pas de layer) ✗
- `pipeline.engine.reco.go` (verb manquant) ✗

### G. Thread safety pour pyqtSignal cross-thread (C8-C12)
Tout `signal.emit()` depuis un QThread worker doit être testé avec un
mini fixture qui :
1. Lance un worker dans un QThread
2. Le worker emit le signal
3. Le main thread reçoit le signal via un slot
4. Asserte que le slot a été appelé avec les bons args

Référence : le bug X11 (CHUNK 10 du 2026-05-18) où `QTimer.singleShot`
ne suffisait pas — il a fallu remplacer par `pyqtSignal` avec
`Qt.QueuedConnection` pour cross-thread. Cf.
`tests/test_ui_terminal.py::test_subprocess_output_signal_main_thread`.

### H. Tests d'isolation ET en suite full
Chaque nouveau `tests/test_chunk_X.py` doit passer dans 2 configurations :
- **Isolation** : `pytest tests/test_chunk_X.py -q` (vert)
- **Suite full** : `pytest tests/ -q` (vert, sans interaction avec autres tests)

Audit d'hier 2026-05-19 a montré `test_a2_1_arithmetic` qui pass isolé
mais fail en full (pollution freezegun via path d'import). Règle
explicite pour éviter ce pattern : si un test fail UNIQUEMENT en suite,
c'est un bug d'isolation, pas une raison de skip — chercher la pollution.

### I. Sandbox smoke screenshot before/after dans le commit (C8-C12)
Pour les chunks UX (C8, C9, C10, C11, C12), le commit body DOIT
contenir :
1. Screenshot AVANT le changement (état actuel UI)
2. Screenshot APRÈS le changement (état post-merge)
3. Lien vers les 2 fichiers dans `/tmp/` (gardés locaux, pas commités)

Sans ça, "ça marche visuellement" reste affirmation non vérifiée. Cf.
sandbox session 2026-05-18.

### J. No-clever-code rule
Si une fonction nécessite plus de **5 lignes de commentaire** pour
expliquer le WHY, c'est probablement trop clever. **Refactor** :
- Extract méthode helper avec un nom explicite qui remplace le commentaire
- Ou simplifier l'algorithme

Code lisible > code optimisé. Sauf hot path mesuré (profiling chiffré),
auquel cas docstring explicite le pourquoi de la complexité.

### K. Forge skipped functions tracking
Quand `forge --gen-props` skip une destructive function, lister
**laquelle** dans le commit message :
```
Forge: Generated 3 props, skipped 2 destructive functions:
  - scan_repo (calls .mkdir())
  - bootstrap_mycelium (calls .read_text())
```
Sinon on perd visibilité sur ce qui n'est PAS testé en property-based.
Le BUG-102 destructive detector déjà loadé par forge-shield 2.1.2 fait
le travail technique — il suffit de pasted son output.

---

## 7. Décisions Sky requises avant attaque

1. **Validation de l'ordre** : OK pour les 14 chunks (C0→C13) dans cet ordre ? Réordonner ?
2. **Granularité commit** : 1 commit par chunk (recommandé), ou regrouper certains (ex: C4+C5+C6 forge bundle) ?
3. **Push intermédiaire** : OK après chaque chunk vert (recommandé), ou push final unique ?
4. **C0 LLM repeat_penalty default** : `1.15` est conservatif. Tu veux plus agressif `1.3` ou plus doux `1.05` ? (1.15 = standard recommandation Ollama)
5. ~~**C7 granularité subdivide**~~ — **TRANCHÉ 2026-05-19** : pure zone-based, `target_tokens` comme plafond, zones petites fusionnées, zones grosses splittées par minima de densité conceptuelle. Cubes hétérogènes acceptés.
6. ~~**C11 file view UX**~~ — **TRANCHÉ 2026-05-19** : bottom panel (split horizontal sous le cube 3D). Sync visuelle cube ↔ fichier en parallèle, pas de fenêtre flottante à gérer.
7. **C13 sandbox smoke** : tu accepte de relancer le container et faire les 5 actions manuelles après chaque chunk UX (C9-C12), ou tu préfères que je fasse les screenshots via xdotool moi-même ?

Co-Authored-By: Claude Opus 4.7
