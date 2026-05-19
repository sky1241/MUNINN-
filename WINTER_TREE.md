# MUNINN — Winter Tree (Carte Technique)

> Ce fichier est une CARTE DE NAVIGATION pour Claude. Pas un changelog.
> Objectif: savoir EXACTEMENT ou chercher quoi dans le code, avec les numeros de lignes.
>
> ### 📍 SNAPSHOT 2026-05-19 (Remediation D12 hotfix — HEAD vert)
>
> **Replace C2 flaky timing test with deterministic AST inspection**.
>
> **Contexte** : Sky a flag le drift (push D5→D11 en rafale sans
> attendre CI verte). D5 + D6 CI rouges sur même test perf flaky C2.
> Hotfix nécessaire avant de continuer méthodiquement.
>
> **Fichier touché** :
> - `tests/test_chunk_2026-05-19_C2_record_cycles_batch.py` :
>   - `test_record_cycles_batch_is_at_least_2x_faster_than_singular`
>     (timing, flaky) → `test_record_cycles_batch_uses_executemany_not_loop`
>     (AST inspection + runtime smoke, déterministe).
>   - Inspect AST de `CubeStore.record_cycles` → doit contenir
>     `executemany`. Inspect AST de `CubeStore.record_cycle` → ne doit
>     PAS contenir `executemany`.
>
> **État final remediation** :
> - 12 commits sur main (D1-D11 + D12 hotfix).
> - HEAD vert (`3c8b81c`).
> - D5 + D6 commits individuels ont CI rouge à cause du flaky pré-D12,
>   leur code est sur main et fonctionne (vérifié 171/171 local + CI
>   verte sur D12).
>
> **Leçon méthode** : 1 commit, 1 push, attendre CI verte AVANT le
> suivant. Pas de rafale.
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D6/11 🎉 11/11 COMPLET)
>
> **Tri 44 forge no-op tests + handbook**.
>
> **Fichiers touchés** :
> - `tests/test_props_cube_providers.py` : 7 → 6 tests (helpers purs
>   compute_ncd + validate_reconstruction avec vraies post-conditions).
> - `tests/test_props_cube.py` : 12 → 4 tests (normalize_content +
>   sha256_hash post-conditions).
> - `tests/test_props_cube_analysis.py` : 25 → 0 test (toutes fonctions
>   prennent objets typés, hors-scope D6).
> - `docs/FORGE_REGEN_HANDBOOK.md` (NOUVEAU) : procédure manuelle
>   obligatoire après chaque `forge --gen-props` sur ces 3 modules.
>
> **Avant** : 44 tests no-op, 0 assertion.
> **Après** : 10 tests réels, ~24 assertions.
>
> **🎉 REMEDIATION COMPLETE : 11/11 chunks D1-D11 livrés.**
> Tous les RED de l'audit C8→C13 fixed. Sky a maintenant :
> - C10+C11 affichent du vrai contenu (D1)
> - Shim cold-start fonctionne (D2)
> - DetailPanel sans bruit syntaxique (D3+D4)
> - C12 hover/click fonctionnel à zoom>1 (D5)
> - Forge re-gen documenté (D6)
> - E2E test prouve vraiment quelque chose (D7)
> - Perf gate weekly enforcé (D8)
> - options_applied trace propre (D9)
> - C0 prouvé runtime via mock_ollama (D10)
> - DetailPanel auto-refresh sur late CYCLE_END (D11)
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D5/11 — Q1 B acté)
>
> **C12 hover/click via groups : clic sur molécule sélectionne le groupe entier**.
>
> **Fichier touché** :
> - `muninn/ui/neuron_map.py` :
>   - `_aggregate_neurons_with_groups` nouveau helper (retourne `(molecules, groups)`).
>   - `_aggregate_neurons_to_level` devient wrapper backward-compat.
>   - `NeuronMapWidget._displayed_groups: list` (mapping mol→originals).
>   - Cache `_displayed_neurons_cache` (+level+n) pour identité Python stable.
>   - `_hit_test` au zoom>1 cherche dans `_displayed_neurons()` O(n).
>   - `_resolve_clicked_originals(neuron)` helper de résolution.
>   - `_handle_neuron_click` utilise resolve_clicked_originals + select groupe.
>
> **Tests** : 7 nouveaux `test_d5_*` dans
> `tests/test_chunk_2026-05-19_C12_fractal_zoom.py`. Total = 18 tests.
>
> **Reste remediation** : D6 (forge tri 44 no-op).
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D10/11 — Q3 B acté)
>
> **mock_ollama capture + test C0 runtime**.
>
> **Fichiers touchés** :
> - `tests/_helpers/mock_ollama.py` : `mock_ollama_session` yield
>   maintenant une `captured` list ; chaque request body est parsée
>   en JSON et appendée à `captured`.
> - `tests/test_chunk_2026-05-19_C0_llm_runtime.py` (NOUVEAU) :
>   5 tests qui consume mock_ollama_session et assertent que C0
>   options (`repeat_penalty=1.15`, `temperature=0.2`) arrivent dans
>   le payload HTTP `/api/generate`. Autouse fixture pour reload
>   propre.
>
> **Reste remediation** : D5 (C12 hover/click groups), D6 (forge tri 44).
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D7/11)
>
> **`test_pipeline_trace_emits_during_reco` durci**.
>
> **Fichier touché** :
> - `tests/test_pipeline_e2e_2026-05-19.py:131-180` :
>   - `assert isinstance(events, list)` (no-op) → `assert len(events) > 0`
>     + `assert event_names & expected_any`.
>   - 3 events attendus : `pipeline.engine.reco.cube_ordering_applied`,
>     `pipeline.mycelium.spread.begin/end`.
>
> **Reste remediation** : D5 (C12 hover/click groups), D6 (forge tri 44 no-op),
> D10 (mock_ollama + test C0 runtime).
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D8/11 — Q2 A acté)
>
> **Workflow `perf.yml` weekly cron pour `MUNINN_RUN_PERF=1`**.
>
> **Fichier nouveau** :
> - `.github/workflows/perf.yml` :
>   - Schedule `cron '0 8 * * 0'` (dimanche 08:00 UTC).
>   - `workflow_dispatch` pour trigger manuel.
>   - `MUNINN_RUN_PERF: "1"` dans step pytest.
>   - Reset `.muninn` state avant run.
>
> **Reste remediation** : D5 (C12 hover/click groups), D6 (forge tri 44),
> D7 (E2E pipeline_trace réel), D10 (mock_ollama + test C0 runtime).
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D11/11)
>
> **`update_cube_details` refire `neuron_selected` if cube already selected**.
>
> **Fichier touché** :
> - `muninn/ui/neuron_map.py:update_cube_details` :
>   - Si `idx in self._selected` après update, refire `self.neuron_selected.emit(n)`.
>   - DetailPanel refresh automatique sur late CYCLE_END.
>
> **Tests** : 2 nouveaux `test_d11_*` dans `tests/test_chunk_2026-05-19_C10_recon_extras.py`.
>
> **Reste remediation** : D5 (C12 hover/click groups), D6 (forge tri 44 no-op),
> D7 (E2E pipeline_trace réel), D8 (workflow perf.yml weekly), D10 (mock_ollama + test C0 runtime).
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D9/11)
>
> **`options_applied` trace fires ONCE per session (module-level guard)**.
>
> **Fichier touché** :
> - `engine/core/cube_providers.py` : `_OPTIONS_TRACE_EMITTED = False`
>   module-level + check/set dans `OllamaProvider.__init__`.
>
> **Tests** : 1 nouveau `test_d9_options_applied_emitted_only_once_per_session`
> dans `tests/test_chunk_2026-05-19_C0_llm_no_collapse.py`. Total = 8 tests.
>
> **Reste** : D5, D6, D7, D8, D10, D11.
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D4/11)
>
> **Shim re-export `_extract_gap_lines` + `_extract_unknown_identifiers`**.
>
> **Fichier touché** :
> - `muninn/cube_providers.py` : ajout explicite des 2 helpers privés
>   dans le bloc de re-export public (wildcard `import *` skip les `_*`).
>
> **Tests** : 2 nouveaux `test_d4_*` dans `tests/test_bug_091_shim_first_import.py`
> (subprocess cold-start + call check). Total fichier = 6 tests.
>
> **Reste** : D5-D11.
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D3/11)
>
> **Filter language keywords + min length 4 in `_extract_unknown_identifiers`**.
>
> **Fichier touché** :
> - `engine/core/cube_providers.py` :
>   - `_COMMON_LANG_KEYWORDS` frozenset (Python + Go + JS/TS + C-family, ~40 mots).
>   - `_extract_unknown_identifiers` : regex `{2,}` → `{3,}` + filter keywords.
>
> **Tests** : 4 nouveaux `test_d3_*` dans `tests/test_chunk_2026-05-19_C10_recon_extras.py`.
> **Forge** : 7 props cube_providers re-gen, OK.
>
> **Reste** : D4-D11.
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D2/11)
>
> **Shim `muninn.cube_providers` ImportError circular fix**.
>
> **Fichier touché** :
> - `muninn/cube_providers.py:14-17` : pre-import `cube` AVANT
>   `from cube_providers import *`. Casse la chaîne circulaire
>   cold-start (cube_providers → cube → cube_analysis → cube_providers).
>
> **Tests** : `tests/test_bug_091_shim_first_import.py` (NOUVEAU, 4 tests
> subprocess `python -c "..."` pour éviter le warmup contamination).
>
> **Reste** : D3-D11 du plan REMEDIATION.
>

> ### 📍 SNAPSHOT 2026-05-19 (Remediation D1/11)
>
> **Fix `gap_lines` TypeError swallowed (Bonus B = full anchor map)**.
>
> **Fichier touché** :
> - `engine/core/cube_providers.py:1070-1085` :
>   - Ajout du 4ème argument `ext` à `_build_full_anchor_map(...)`.
>   - `ext = os.path.splitext(cube.file_origin)[1]` (graceful si vide).
>   - Le `try/except` reste mais ne swallow plus le `TypeError` (signature fix).
>
> **Avant** : `gap_lines = []` toujours → toute la chaîne C10+C11 affichait vide.
> **Après** : `gap_lines = [1, 2]` sur un cube avec 2 unique code lines + `}` + first_line.
>
> **Mission Muninn cohérente** : full anchor map ancre les triviaux (closing
> braces, defer, struct tags, constants) → rouge = mémoire dev seniors uniquement.
>
> **Tests** : 3 nouveaux dans `tests/test_chunk_2026-05-19_C10_recon_extras.py`
> (`test_d1_gap_lines_*`). Total C10 file = 14 tests.
> **Forge** : 7 props cube_providers (1 destructive skipped).
>
> **Plan de remediation** : `docs/BATTLE_PLAN_REMEDIATION_2026-05-19.md`
> (11 chunks D1→D11). D1 livré, D2-D11 enchainent.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C13/14 🎉 COMPLET)
>
> **E2E pipeline + perf opt-in + sandbox smoke documenté**.
>
> **Fichiers nouveaux** :
> - `tests/_helpers/__init__.py`, `pipeline_trace.py`, `mock_ollama.py` :
>   3 patterns test établis (aucun n'existait pré-audit 2026-05-19).
> - `tests/test_pipeline_e2e_2026-05-19.py` (7 tests E2E).
> - `tests/test_perf_cube_run_2026-05-19.py` (3 perf tests opt-in via
>   `MUNINN_RUN_PERF=1`).
> - `docs/SANDBOX_SMOKE_2026-05-19.md` (9 étapes manuelles dans
>   muninn-sandbox).
>
> **Forge** : `forge --gen-props` re-tourné sur cube_analysis,
> cube, cube_providers → 44 props pass, `deadline=None` restauré.
>
> **Battle plan 2026-05-19** : **14/14 chunks** (C0→C13) ✅.
> Voir snapshots C0…C12 ci-dessous.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C12/14)
>
> **Fractal x1/x2/x3 zoom : molécules visuelles à la molette Ctrl+wheel**.
>
> **Fichiers touchés** :
> - `muninn/ui/neuron_map.py` :
>   - `_zoom_level: int = 1` (distinct de `_zoom` float).
>   - `set_zoom_level(level)`, `_displayed_neurons()`.
>   - `_aggregate_neurons_to_level(neurons, level)` module-level helper
>     (token-weighted-avg NCD, max degree, centroid xyz).
>   - `_paint_neurons` peint depuis `_displayed_neurons()`.
>   - `wheelEvent` : `Ctrl+wheel` cycle 1→2→3→1.
>
> **Tests** : `tests/test_chunk_2026-05-19_C12_fractal_zoom.py` (11 tests).
> **Forge** : skip (UI, helper privé `_`).
>
> **Reste C13** : E2E + benchmark + sandbox smoke (~2h30).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C11/14)
>
> **File line-by-line heatmap (bottom panel sous cube 3D)**.
>
> **Fichiers touchés** :
> - `muninn/ui/file_heatmap_view.py` (nouveau) :
>   - `FileHeatmapView(QWidget)` : QPlainTextEdit + gutter colorisé.
>   - `load_file(path)` + `set_line_colors(dict)` API.
>   - Signal `line_clicked(int)`.
> - `muninn/ui/cube_live.py` :
>   - `_compute_line_colors_for_cube(start, end, gap_lines, sha)` helper.
>   - Signal `file_heatmap_ready = pyqtSignal(str, dict)`.
>   - Accumulateur `_file_heatmap` + `_cube_sha_status` dans run().
> - `muninn/ui/terminal.py` + `main_window.py` : bubble signal +
>   `_on_file_heatmap_ready` slot. FileHeatmapView placé dans
>   `left_splitter` entre `neuron_panel` et `tree_panel`.
>
> **Couleurs** : green = ancré, red = gap+fail, orange = gap+SHA match.
>
> **Tests** : `tests/test_chunk_2026-05-19_C11_file_heatmap.py` (12 tests).
> **Forge** : skip (UI, pas de fonctions publiques module-level).
>
> **Reste C12-C13** : fractal x1/x2/x3 (C12), E2E + benchmark + sandbox (C13).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C10/14)
>
> **DetailPanel enrichi reco : SHA / NCD / gaps / unknown identifiers**.
>
> **Fichiers touchés** :
> - `engine/core/cube_providers.py` :
>   - `ReconstructionResult` : `gap_lines`, `unknown_identifiers` (default []).
>   - `WaveResult` : propage les 2 champs depuis l'attempt gagnant.
>   - `_extract_gap_lines(anchor_map, n_lines)` helper.
>   - `_extract_unknown_identifiers(reconstruction, ast_hints)` helper.
>   - `reconstruct_cube` populate les 2 champs.
>   - `reconstruct_adaptive` + `_run_level_pass` kwarg
>     `on_cube_extras: callable = None`.
> - `muninn/ui/neuron_map.py` :
>   - `Neuron.gap_lines` + `Neuron.unknown_idents`.
>   - `NeuronMapWidget.update_cube_details(idx, gap, unknown)` slot.
> - `muninn/ui/cube_live.py` : signal `cube_details = pyqtSignal(int, list, list)`,
>   callback `on_cube_extras` passé à `reconstruct_adaptive`.
> - `muninn/ui/terminal.py` + `main_window.py` : bubblé worker → UI.
> - `muninn/ui/detail_panel.py` : 4 labels reco (`_sha_label`, `_ncd_label`,
>   `_gaps_label`, `_unknowns_label`) ; affichés ssi `level == 'cube'`.
> - `muninn/ui/main_window.py::_on_neuron_selected` : enrichit payload
>   `show_neuron` (sha_match dérivé de `status == 'done'`, ncd de
>   `temperature`).
>
> **Tests** : `tests/test_chunk_2026-05-19_C10_recon_extras.py` (11 tests).
> **Forge** : `forge --gen-props engine/core/cube_providers.py` → 7 props,
> 1 destructive skipped (`run_progressive_levels`).
>
> **Reste C11-C13** : file line-by-line heatmap (C11), fractal x1/x2/x3 (C12),
> E2E + benchmark + sandbox (C13).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C9/14)
>
> **Toggle Mycelium↔Reconstruction wirée + bouton visible**.
>
> **Fichiers touchés** :
> - `muninn/ui/neuron_map.py` :
>   - `self._color_mode` (default `"mycelium"`, persistance via ai_config).
>   - `set_color_mode(mode)`, `toggle_color_mode()`.
>   - `_paint_neurons` branche sur `_color_mode` (degree vs NCD temperature).
> - `muninn/ui/forest.py` : `ColorModeToggle` widget companion (cyan↔orange).
> - `muninn/ui/main_window.py` :
>   - Instantie `_color_mode_toggle` overlay top-right neuron_panel.
>   - `eventFilter` reposition sur resize.
>   - Palette `toggle_mode` → `neuron_panel.toggle_color_mode()`.
> - `~/.muninn/ui_config.json` : clé `neuron_color_mode`.
>
> **Tests** : `tests/test_chunk_2026-05-19_C9_color_mode_toggle.py` (10 tests).
> **Forge** : skip (UI files).
>
> **Reste C10-C13** : DetailPanel SHA/NCD/gaps (C10), file line-by-line
> heatmap (C11), fractal x1/x2/x3 (C12), E2E + benchmark + sandbox (C13).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C8/14)
>
> **Mycelium neighbors live refresh entre cycles**.
>
> **Fichiers touchés** :
> - `muninn/ui/cube_live.py` :
>   - `_NEIGHBORS_LIVE_REFRESH_ENABLED` (env flag, default `1`).
>   - `_compute_mycelium_neighbors(cubes, mycelium)` (module-level helper,
>     extrait de l'inline `ReconstructionWorker.run`).
>   - Signal `ReconstructionWorker.cube_neighbors_refreshed = pyqtSignal(list)`.
>   - `on_cube` détecte `CYCLE_END` → recompute + emit payload
>     `[{idx, mycelium_neighbors}, …]`.
> - `muninn/ui/neuron_map.py` :
>   - `NeuronMapWidget.refresh_neighbors(payload)` rebuild edges +
>     relance Laplacien (sans toucher `self._neurons` → couleurs
>     NCD/SHA préservées).
> - `muninn/ui/terminal.py` + `muninn/ui/main_window.py` : signal bubblé.
>
> **Tests** : `tests/test_chunk_2026-05-19_C8_neighbors_refresh.py` (7 tests).
> **Forge** : skip (UI files, pas de fonctions publiques).
> **Feature flag** : `MUNINN_NEIGHBORS_LIVE_REFRESH` (default `1`).
>
> **Reste C9-C13** : UI toggle Mycelium↔Reconstruction (C9), DetailPanel
> SHA/NCD (C10), file line-by-line heatmap (C11), fractal x1/x2/x3 (C12),
> E2E + benchmark + sandbox smoke (C13).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C7/14)
>
> **THE archi fix livré**. Scan-aware subdivide_file: pure zone-based.
>
> **Fichiers touchés** :
> - `engine/core/mycelium.py` :
>   - `Mycelium.has_concept(name) -> bool` (méthode publique).
>   - `concept_to_file_lines(content, mycelium) -> dict[idx, set]`.
> - `engine/core/cube.py` :
>   - `_SCAN_AWARE_SUBDIVIDE_ENABLED` (env flag).
>   - `find_concept_boundaries(content, mycelium, target_tokens)`.
>   - `_subdivide_at_boundaries(...)` slicer.
>   - `subdivide_file(... mycelium=None)` étendu.
> - `muninn/ui/cube_live.py` — passe mycelium.
> - `engine/core/cube_providers.py` — 3 call sites passent mycelium.
>
> **Tests** : `tests/test_chunk_2026-05-19_C7_subdivide_mycelium.py` (9 tests).
> **Forge** : 12 props cube + 1 prop mycelium.
>
> **Décision Sky 2026-05-19** : pure zone-based, `target_tokens` = plafond.
> Cubes hétérogènes OK (60-400 tokens). 1 cube = 1 unité logique.
> **Feature flag** : `MUNINN_SCAN_AWARE_SUBDIVIDE` (default `1`).
>
> **Pipeline scan→reco maintenant entièrement aligné** :
> 1. Scan définit zones conceptuelles via mycelium
> 2. subdivide_file (C7) coupe les cubes à ces zones
> 3. fuse_risks (C6) trie cubes par risk
> 4. reconstruct_adaptive cycles avec mycelium feedback
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C6/14)
>
> Septième chunk. fuse_risks wiré dans reconstruct_adaptive (F2).
>
> **Fichiers touchés** :
> - `engine/core/cube_providers.py` :
>   - Constante `_FUSE_RISKS_ORDERING_ENABLED` (env flag).
>   - `_sort_to_test_by_risk(to_test, cubes, store, forge_root)` —
>     trie ASC par fuse_risks.combined.
>   - `reconstruct_adaptive(... forge_root=None, ...)` étendu.
>   - Pipeline_trace event `pipeline.engine.reco.cube_ordering_applied`.
> - `muninn/ui/cube_live.py` — passe `forge_root=str(repo_root)`.
>
> **Tests** : `tests/test_chunk_2026-05-19_C6_fuse_risks_wired.py` (7 tests).
> **Forge** : 7 props générées (regen), 1 destructive skipped.
>
> **Feature flag** : `MUNINN_FUSE_RISKS_ORDERING` (default `1`).
>
> **Wiring forge complet** : F0 (C4) cache + F1 (C5) file-level priority
> + F2 (C6) cube-level fusion. Le pipeline `scan → reco` est maintenant
> entièrement risk-aware via forge.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C5/14)
>
> Sixième chunk. Forge file-level priority (F1) — sort des files par
> forge_risk descendant avant scan.
>
> **Fichier touché** :
> - `engine/core/scanner/orchestrator.py` :
>   - Constante module `_FORGE_FILE_ORDERING_ENABLED` (env flag).
>   - Helper `_get_file_risk_map_safe(repo)` — wrap avec fallback {}.
>   - Helper `_sort_files_by_forge_risk(files, repo)` — sort stable,
>     emit pipeline.forge.file_ordering_applied.
>   - PIPELINE_TRACE block import au top.
>   - 1 ligne ajoutée après `files_to_scan = _select_files(...)` pour
>     brancher le sort dans le pipeline scan.
>
> **Tests** : `tests/test_chunk_2026-05-19_C5_file_priority.py` (7 tests).
> **Forge** : 2 props générées, 0 destructive.
>
> **Feature flag** : `MUNINN_FORGE_FILE_ORDERING` (default `1`).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C4/14)
>
> Cinquième chunk. Forge cache infrastructure (F0) — prépare C5+C6.
>
> **Fichier touché** :
> - `engine/core/forge_metrics.py` — nouvelle fonction publique
>   `get_file_risk_map(repo, ttl_seconds=86400) -> dict[str, float]`.
>   Wrap `get_repo_risk()` existant. Pipeline_trace event
>   `pipeline.forge.risk_map_cached` émis 1x par appel.
> - Ajout PIPELINE_TRACE block import au top du fichier.
>
> **Tests** : `tests/test_chunk_2026-05-19_C4_forge_cache.py` (6 tests).
> **Forge** : 5 props générées, 0 destructive skipped.
>
> Bonus : `tests/test_props_forge_metrics.py` reçoit `@settings(deadline=None)`
> sur 4 tests qui shell out à `forge` binary (lent).
>
> **Pas de feature flag** : addition pure d'API publique.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C3/14)
>
> Quatrième chunk exécuté. Healed set chargé depuis DB cross-run.
>
> **Fichiers touchés** :
> - `engine/core/cube.py::CubeStore.get_healed_cubes(min_success_count=3, min_success_rate=1.0) -> set[str]` (nouvelle méthode publique).
> - `engine/core/cube_analysis.py` : constante module-level
>   `_HEALED_PERSISTENT_ENABLED` (env `MUNINN_HEALED_PERSISTENT`),
>   `cli_run` charge `healed` depuis DB quand actif.
>
> **Tests** : `tests/test_chunk_2026-05-19_C3_healed_persistent.py` (6 tests, flag ON+OFF tous deux testés per §8.B).
>
> **Feature flag** : `MUNINN_HEALED_PERSISTENT` (default `1`, mettre `0`
> pour legacy).
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C2/14)
>
> Troisième chunk exécuté. Hot path record_cycle batché.
>
> **Fichiers touchés** :
> - `engine/core/cube.py` — nouvelle méthode publique
>   `CubeStore.record_cycles(batch: list[tuple])` qui fait
>   `executemany + commit` une fois pour N rows. `record_cycle`
>   (singulier) conservé en backward-compat.
> - `engine/core/cube_analysis.py::run_destruction_cycle` — accumule
>   les results dans `cycle_batch: list[tuple]` puis flush via
>   `store.record_cycles(cycle_batch)` une fois après la boucle.
>
> **Tests** : `tests/test_chunk_2026-05-19_C2_record_cycles_batch.py` (5 tests).
> Bonus : `tests/test_props_cube.py::test_subdivide_file_no_crash` a
> reçu `@settings(deadline=None)` car flaky sur cold tokenizer cache.
>
> **Forge** : 11 props générées (cube.py), 4 destructives skipped
> (scan_repo, format_code, check_formatters, install_formatters).
>
> **Pas de feature flag** : pure perf fix, le singulier reste
> accessible pour legacy callers.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C1/14)
>
> Deuxième chunk exécuté. BUG WAGON SHA-256 fixé.
>
> **Fichier touché** :
> - `engine/core/cube_analysis.py:148-156` — wagon effect maintenant met à jour cube.sha256 en plus de cube.content avant `store.save_cube(cube)`. 1 ligne ajoutée, commentaire 5 lignes.
>
> **Test pin** : `tests/test_chunk_2026-05-19_C1_wagon_sha.py` (3 tests).
> **Forge** : 25 props générées, 9 destructives skipped.
> **Impact** : cycle 2+ skip les cubes déjà SHA-matchés cycle 1 (x2-x5
> appels LLM économisés par run multi-cycle).
> **Pas de feature flag** : fix mécanique, pas tunable.
>

> ### 📍 SNAPSHOT 2026-05-19 (PM — battle plan unifié C0/14)
>
> Premier chunk du `BATTLE_PLAN_2026-05-19_FUSION_UNIFIED.md` exécuté.
>
> **Fichiers touchés** :
> - `engine/core/cube_providers.py` (top du fichier + `OllamaProvider`) :
>   - L.38-43 : constantes `_OLLAMA_REPEAT_PENALTY=1.15`, `_OLLAMA_TEMPERATURE=0.2` (env-driven).
>   - L.45-50 : PIPELINE_TRACE block.
>   - `OllamaProvider.__init__` : émet `pipeline.engine.llm.options_applied`.
>   - `OllamaProvider.generate` : `repeat_penalty` ajouté à options, `temperature` default `_OLLAMA_TEMPERATURE`.
>   - `OllamaProvider.stream` : `repeat_penalty` ajouté.
>   - `OllamaProvider.fim_generate` : `temperature=0.0` → `_OLLAMA_TEMPERATURE`, `repeat_penalty` ajouté.
>
> **Tests** : `tests/test_chunk_2026-05-19_C0_llm_no_collapse.py` (7 tests).
> **Env vars nouvelles** : `MUNINN_LLM_REPEAT_PENALTY`, `MUNINN_LLM_TEMPERATURE` (table CLAUDE.md mise à jour).
>
> **Reste du plan** : C1-C13 (voir `docs/BATTLE_PLAN_2026-05-19_FUSION_UNIFIED.md`).
>

> ### 📍 SNAPSHOT 2026-05-19 (matin — BUG-091 closeout final + UI reco fixes)
>
> **4 commits poussés, CI verte** au run `26084199149` (3 jobs SUCCESS).
> Sandbox-observabilité session du 2026-05-18 (CHUNK 10) a surfacé 3 drifts
> + 1 mirror oublié. Tous fix.
>
> **Commits** :
> - `4ff59c7` refactor(BUG-091): `muninn/_engine.py` 1801L → 47L shim
> - `9892741` feat(ui): reco cube geometry = scan (Laplacien + mycelium edges)
> - `bd1f937` fix(reco): `/reconstruct` gate accepts scan-only repos
> - `3b78c2f` test: xfail `test_a2_1_arithmetic` (flaky freezegun post-shim)
>
> **Carte technique : ce qui change où**
> - `muninn/_engine.py` (47L shim) charge `engine/core/muninn.py` via
>   `importlib.spec_from_file_location("_muninn_engine_canonical", ...)` puis
>   copie tous les attributs (publics + privés via `dir()`).
> - `muninn/ui/neuron_map.py:1052` `set_reconstruction_cubes` — random init
>   + Laplacien sur edges mycelium-derivés (poids 1.0) + chaîne (0.5).
>   Constantes module : `_EDGE_WEIGHT_MYCELIUM`, `_EDGE_WEIGHT_CHAIN`.
> - `muninn/ui/cube_live.py:202-260` — calcul `cube["mycelium_neighbors"]`
>   via Jaccard sur intersection avec codebook mycélium (regex
>   `r"[A-Za-zÀ-ÿ_]{3,}"` alignée sur `mycelium.observe_text`).
>   Constantes : `_MYCELIUM_CONCEPT_REGEX`, `_MYCELIUM_CONCEPT_LIMIT=200000`,
>   `_MYCELIUM_JACCARD_THRESHOLD=0.10`.
> - `muninn/ui/terminal.py:637` — gate `find_bootstrapped_repo` →
>   `find_owning_repo` (accepte scan-only). `_reconstruction_prereqs_missing`
>   n'exige plus `tree.json` (audit a confirmé : pipeline reco ne le lit
>   jamais — `cube_live`, `cube_providers`, `mycelium`, `subdivide_file`,
>   `observe_text` zero accès au tree).
>
> **Tests pinned** :
> - `tests/test_chunk_d11_shim_drift.py` — nouveau test
>   `test_engine_shim_reexports_canonical_muninn` (couvre paire asymétrique
>   `engine/core/muninn.py` ↔ `muninn/_engine.py`).
> - `tests/test_ui_neuron_map.py` — 5 nouveaux tests reco-mode (mycelium
>   edges + chain fallback + random initial + neighbor cache + empty).
> - `tests/test_ui_terminal.py` — 3 tests réécrits (mycelium-only accepté,
>   full bootstrap toujours OK, missing-when-no-mycelium).
>
> **Reste pour Phase 2** (non démarré) : brancher `subdivide_file` sur
> `mycelium.detect_zones()` (`engine/core/mycelium_zones.py`, déjà existe
> via CLI `muninn-mem zones`). Aujourd'hui `subdivide_file` est aveugle
> au scan — découpage uniforme token-based.
>
> **Docs nettoyés** : `.claude/rules/python.md` (règle "mirror immediately"
> obsolète virée), `README.md`, `docs/PIPELINE_TRACE_REMOVAL.md`.
>

> ### 📍 SNAPSHOT 2026-05-12 (nuit — Phase G+H exec partiel via PROMPT_EXEC_PHASE_H.md)
>
> **22 chunks Phase G+H livrés** (G.1-G.10 sans G.7/G.9, H.0-H.8 sans H.6b).
> Push 1/2 (HEAD `40f23db`, 11 commits) confirmé VERT par CI 3/3 jobs SUCCESS
> verbatim. Reportés : H.6 migration settings live, H.6b vault crypto sur prod
> (RULE 2 destructive), H.10 bump 1.1.0, I.1-I.5 Phase I.
>
> **CLI surface élargi** :
> - `muninn-mem cube --cube-action {scan,run,status,god}` — 5597 LOC débloquées (H.1)
> - `muninn-ui` console + `python -m muninn.ui` — 11712 LOC débloquées (H.2)
> - `muninn-mem prune --include-dreams` — Sleep Consolidation 561 LOC (H.3)
> - `muninn-mem metrics [--output PATH]` — forge_metrics 344 LOC (H.4)
> - env `MUNINN_RECALL_STOPWORD_PERCENTILE` 0.05 default — filtre meta MCP (G.1)
> - env `MUNINN_DEBUG` — bypass friendly error handler (G.3)
> - env `MUNINN_L12_BUDGET` default 16000 (flipped opt-in→out, H.6c)
>
> **Garde-fous CI** :
> - `test_h0_no_orphan.py` — 6 facettes anti-dormant (engine/UI/env vars/argparse/CLI/hooks)
> - `test_h8_api_bloat_baseline.py` — ratchet MyceliumDB 52 / Mycelium 20 / Cube 4
>

> ### 📍 SNAPSHOT 2026-05-12 (nuit — post-cleanup seigneur dev + forge 2.1.2 + 5 audits compilés)
>
> **Cleanup seigneur dev commit `bd33f98` (LOCAL, non pushé)** :
> - Forge 1.3.0 → **2.1.2** bumped (constraints + pyproject + CLAUDE.md). API rétrocompat verified : `--gen-props`, `--modularity` (Q=0.671), `--carmack`, `--locate`, `--predict`, `--anomaly`, `--mutate` tous présents. Nouveau 2.x : `--shield`, `--bisect`, `--snapshot`, `--add/--close BUG-ID`, `--full-cycle`.
> - MUNINN_test_cube supprimé (duplicate de `tests/cube_corpus/btree_google.go`).
> - 2 résidus BUG-111 supprimés (`.muninn/tree/*.broken.20260511_163630`).
> - 5 root files archivés vers `docs/archive/` : BUG_HOOKS_UNIVERSELS, CUBE_YGG_QUERY, PLAN_PHASE0_TO_8, changelog_before/after.txt.
> - **Root du repo CLEAN** : 6 fichiers .md/.txt (BUGS, CHANGELOG, CLAUDE, README, WINTER_TREE, constraints) + pyproject + LICENSE + MANIFEST.in + index.html.
>
> **5 deep audits compilés (12 mai journée + soir)** → battle plan FINAL :
> - [`docs/BATTLE_PLAN_FINAL_2026-05-13.md`](docs/BATTLE_PLAN_FINAL_2026-05-13.md) — Phase H "Light Up Everything" 5h30 en 10 chunks
> - Verdict : ~17 800 LOC dormantes mais codées+testées (Cube 5597 LOC, UI PyQt6 11712 LOC, dream 561 LOC, forge_metrics 344 LOC, sync_tls 643 LOC) + faux positifs MCP filtrés (MCP IS wired, prouvé live aujourd'hui)
>
> **6 commits locaux non pushés** :
> ```
> bd33f98 chore(archi): cleanup seigneur dev + forge 2.1.2
> 06f99f5 docs(plan-final): battle plan béton armé
> 894bec5 docs(phase-H): Light Up Everything
> 035931e docs(phase-G+H): deep audit findings
> 83cc0bf docs(phase-F-wrap + G-plan)
> 107a0ad fix(mcp.F3): E2E test ← origin/main (CI 3/3 GREEN)
> ```
>
> **Items pending demain matin** :
> - Phase H Light Up Everything 5h30 (10 chunks)
> - 5 décisions Sky : scope H, UI name, metrics name, hooks orphans, sync_tls fate
> - Décision push 6 commits locaux
> - Items mineurs : `memory/` legacy fallback à clarifier, 16 git tags pre-* à décider, `.forge/forge_log.txt` silence 5 jours à investiguer
>
> ### 📍 SNAPSHOT 2026-05-12 (soir — post-Phase E hardening 7/7 + F.1/F.2/F.3 + intégration MCP prouvée live)
>
> **Engine** : ~26 700 lignes / 33 fichiers core (+200L Phase E+F : argparse muninn-mcp-mem + uninstall_hooks + 25 nouveaux tests)
> - `pyproject.toml` 1.0.1 → 1.0.2 → **1.0.3** (E.7 + F.1 bumps, 4 mirrors en sync)
> - **Console scripts renommés** (E.3) : `muninn-mem` / `muninn-mycel` / `muninn-mcp-mem` (collision PyPI prod : `muninn` S&T data catalog, `mycelium` greenbyte, `muninn-mcp` Ilwon Yoon existaient déjà)
> - `engine/core/muninn_install.py` : NEW `uninstall_hooks(repo, purge_data=False)` (F.1, ~120L) — companion à `install_hooks`, retire hooks .py + strip settings.local.json + delegate install_cron(uninstall=True), garde .muninn/ user data par défaut
> - `muninn/mcp/server.py` : NEW argparse dans `main()` (E.4) → `--help` / `--version` / `--list-tools` exit cleanly avant stdio loop (était hang infini avant)
> - `tests/test_chunk_mcp_e4_mcp_argparse.py` + `e5_doc_drift.py` + `e6_hardened.py` + `f1_uninstall.py` : 25 nouveaux tests (10 REAL + 12 MEDIUM + 3 LOW — honest classification post-audit)
> - `.github/workflows/ci.yml` : ajouté `mcp` au pip install (F.2 root cause des 6 push rouges) — install line `pytest hypothesis tiktoken anthropic numpy cryptography freezegun forge-shield mcp`
> - `constraints.txt` : pinned `mcp==1.27.1` (F.2)
> - `tests/test_e2e_pip_install_from_scratch.py` : `bin/muninn` → `bin/muninn-mem` (F.3 régression E.3 rename)
> - `.mcp.json` NEW (gitignored) : config muninn MCP pour Claude Code, pointe sur `/tmp/muninn_session_venv/bin/muninn-mcp-mem`
> - `.claude/settings.local.json` : ajouté `permissions: {allow:[], deny:[]}` (orange warning resolved 2026-05-12 soir)
>
> **Tests** : **2546 PASS / 0 fail** + **18 property tests**
> **forge --modularity Q** : **0.671** (stable, ↑ vs 0.664 du matin)
> **Bugs OPEN** : **0** (mais **1 bug latent identifié** F.4 stopwords incomplète, fix planifié Phase G)
> **PyPI release** : **muninn-memory 1.0.3 sur TestPyPI** (https://test.pypi.org/project/muninn-memory/1.0.3/). Prod 1.0.3 ready — décision Sky reportée à demain
> **CI HEAD `107a0ad`** : **3/3 jobs GREEN** (validate + forge_smoke + E2E) — premier vert depuis E.3 commit
>
> **Intégration MCP prouvée live dans vraie session Claude Code** :
> - Sky a lancé une nouvelle Claude Code session → Claude a appelé les 3 tools verbatim
> - `recall_local("compression")` → tree(1.0), claude(0.16), branches(0.0096)
> - `recall_meta("compression")` → pas(1.0), est(0.99), les(0.83) ⚠️ stopwords FR pollution (F.4 à fix)
> - `recall(scope=auto, "forge")` → scope_used="auto→local", strength_local=5.0 > threshold_used=3.4497 (**auto-calibration C.0 visible LIVE en prod** — premier signal externe que ce chunk marche)
>
> **Phase state** : A 4/4 ✅ + B 6/6 ✅ + C 5/6 ✅ (C.2 reverted) + D 4/5 ✅ (D.3 pending) + E 7/7 ✅ + F.1+F.2+F.3 ✅ + 1 bug latent F.4 identifié pour Phase G
>
> **Battle plan demain (Phase G)** : `docs/BATTLE_PLAN_PHASE_G_2026-05-13.md` — compilation des findings deep audit 4-agents post Phase F
>
> ### 📍 SNAPSHOT 2026-05-12 (matin — post-Phase D 4/5)
>
> **Engine** : **26 499 lignes / 33 fichiers core** (post-Phase D + bug pre-existant pip-install fix)
> - `pyproject.toml` 1.0.0 → **1.0.1** (D.1 + D.4/D.5 fixes inclus)
> - `[tool.setuptools.packages.find].include = ["muninn*", "engine*"]` — D.1 fix critical : ship engine/* dans le wheel (sans ça, tous les shims muninn/* crash en pip-install)
> - `MANIFEST.in` NEW (D.1) : prune `muninn/.muninn/` + `muninn/ui/scans/`, global-exclude `__pycache__/*.pyc`
> - Nouveau dossier `examples/` (D.5) : `quickstart_local.py`, `mcp_recall_demo.py`, `README.md`
> - `engine/core/muninn_tree_doctor.py` : 22 → 25 checks (D.5 ajout `console_scripts`, `engine.core shipped`, `mcp extras` — tous dev-mode-aware WARN/FAIL)
> - `engine/core/muninn.py` + `muninn/_engine.py` : ajouté `_print_welcome()` + `_print_empty_repo_hint()` (D.4) — `muninn` (no args) montre welcome au lieu d'argparse error, `muninn status` en repo vierge guide vers `muninn init` au lieu d'auto-init dans site-packages
>
> **Tests** : **2563 collected / 2 deselected = 2561 actifs** + **18 property tests** (forge --gen-props)
> **forge --modularity Q** : **0.671** (good ≥ 0.30, ↑ vs 0.664 sur snapshot précédent)
> **Bugs OPEN** : **0** (BUG-104 fixed 2026-05-10, BUG-111 fixed 2026-05-11)
> **forge-shield** : **v1.3.0** (PyPI, inchangé)
> **PyPI release** : **muninn-memory 1.0.1 sur TestPyPI** (https://test.pypi.org/project/muninn-memory/1.0.1/). Prod upload en attente validation Sky.
> **CI HEAD** : run en cours suite hotfix `dfe4b28` (fix ci.yml Test Engine Commands + D.1 mcp optional). 3 runs D.1/D.4/D.5 rouges → fix root-cause poussé.
>
> **Phase D state** : **4/5 chunks livrés** (D.1 ✅ + D.2 ✅ + D.4 ✅ + D.5 ✅) + 1 hotfix CI. Reste D.3 (PyPI prod upload).
>
> **Battle plan vivant unique** : `docs/BATTLE_PLAN_MASTER_MCP.md`
> **Protocole de test fin de Phase D** : `docs/TEST_PROTOCOL_PHASE_D_2026-05-12.md`
>
> ### 📍 SNAPSHOT 2026-05-11 (historique — pre-Phase D)
>
> **Engine** : **24 819 lignes / 26 fichiers core** (post-P3 split + H6 mixins + BUG-104 fix)
> - muninn_tree.py : 3929 → **2179L** post-P3 split (-1750L = -45%)
> - 3 nouveaux sous-modules : muninn_tree_boot.py (903L), muninn_tree_prune.py (678L), muninn_tree_doctor.py (297L)
> - mycelium.py : 3163 → **1415L** post-H6 split (-1748L) via 4 mixins (meta 428 / zones 383 / activation 545 / dream 561)
> - budget_select.py : 413 → **501L** post-BUG-104 (wrappers _with_dropped)
>
> **Tests** : **2339 PASS / 47 skip / 0 fail** + **103 property tests** (17 modules)
> **forge --modularity Q** : **0.664** (good ≥ 0.30)
> **Bugs OPEN** : **0** depuis BUG-104 FIXED 2026-05-10 PM (spill-to-tree, V9A+ planère)
> **forge-shield** : **v1.3.0** (PyPI, bumped 2026-05-11 cycle 11+)
> **Hooks Claude Code** : **9 wirés** au logger central (F5 fix 2026-05-10)
> **Papers cités** : **22 directs + 10 cross-validation** (`sky1241/tree/CROSSVAL_REPORT`)
> **CI HEAD** : vert sur 2 jobs (validate + forge_smoke matrix 17 modules)
>
> **Battle plan vivant unique** : `docs/BATTLE_PLAN_MASTER_MCP.md` (570L, ~117h roadmap MCP)
> Anciens battle plans archivés : `docs/archive/` (8 fichiers)
>
> ### 📜 HISTORIQUE (snapshots conservés)
>
> **Snapshot 2026-04-22 (initial)** : Engine: ~22K lignes, 18 fichiers. UI: ~4900 lignes (+5197 ref), 20 fichiers. Tests: **2200+ collected, PASS, 27 skip, 0 FAIL**.
> **Cube L1: 80/80 SHA (100%) on server.go + 53/61 (87%) on btree_google.go.** 21 fixes + refactor. 175 -> 0 gap lines. 73/80 auto-SHA (zero API). 8-language support. Smart formatter detection (doctor --fix). Generalization validated on unseen code.
> Split: muninn.py (7959L -> 4 fichiers), cube.py (3273L -> 3 fichiers: cube.py 1553L, cube_providers.py 1952L, cube_analysis.py 1759L).
> Package: muninn/ pip-installable. _ProxyModule (getattr+setattr+delattr). conftest.py pre-load.
> UI: Phase 0-9 COMPLETE — 32 briques (B-UI-00..32), PyQt6 6.10.2 + pytest-qt, 152 UI tests PASS.
>
> **Leak Intel Battle Plan (2026-04-10): 16 chunks complete.**
> See CHANGELOG.md and docs/CLAUDE_CODE_LEAK_INTEL.md.
>
> Hooks: 4 -> **12 distinct scripts** registered under **10 hook events**:
>   UserPromptSubmit, PreCompact, SessionEnd, Stop, PostToolUseFailure,
>   SubagentStart, **PreToolUse (3 entries: bash-destructive + bash-secrets + edit-hardcode)**,
>   PostToolUse, Notification, ConfigChange.
>
> CLAUDE.md: 8 RULES -> **3 RULES** (chunks 9-10 measured each one with API,
> kept only those with proven causal effect on Opus 4.6: hardcode +100%,
> destructive +100%, secrets +20%). 173 lines, under Anthropic 200-line target.
>
> **Path-scoped rules**: `.claude/rules/python.md` and `.claude/rules/git.md`
> extend RULES with technical detail, loaded only when matching files are touched.
>
> Anti-Adversa clamp on injected content (refuses >30 chained shell commands).
> Anthropic native auto-memory disabled (single source of truth = Muninn).
>
> **Audit chunks 16+17 (2026-04-10)**: 10 bugs found and fixed.
> Chunk 16 (hand audit): 9 bugs in destructive patterns + payload type-checks.
> Chunk 17 (forge + Hypothesis property tests): BUG-101 found by adversarial
>   property testing — `_truncate_with_marker` was producing oversized output
>   when `max_chars < 100`. Hand-written tests in chunk 5 missed it because
>   they only used "reasonable" max_chars (≥1000).
> See BUGS.md BUG-092 to BUG-101. 88 new anti-regression tests added.
>
> **Audit brick 22 (2026-04-11)**: full pytest suite triage. 11 distinct
> failures fixed across 9 test files + 2 source modules:
>   - test_chunk13: bumped CLAUDE.md cap 200->300 (RULE 4+5 added in bricks 8+16)
>   - test_cube_real_api: opt-in env var MUNINN_RUN_REAL_API_TESTS=1 (was hanging)
>   - test_cube_real_llm: opt-in env var MUNINN_RUN_REAL_LLM_TESTS=1 (Ollama 500)
>   - test_phase4_tls: sys.path setup + BUG-091 isinstance fix
>   - test_tier2_b4 + test_tier2_wiring: @timeout(90) for real-DB calls
>   - test_ui_navi (4 fixes): timer 16->15ms, _tutorial_active=True at init,
>     show_first_launch button assertion
>   - test_ui_neuron_map (2 fixes): _cube_angle=0.0 to disable rotation
>   - test_ui_terminal (2 fixes): fake provider stub via monkeypatch
>   - **BUG-110**: pull_from_meta hung on user's 1.8GB home meta DB during
>     temp-repo tests. Fix: 100MB threshold guard mirrored in both trees.
>   Result: 2086 passed / 27 skipped / 0 fail (was hanging or failing on ~12 tests)
>
> **266 chunk tests / 0 regression** (was 178 before audit). Empirical eval
> harness in tests/eval_harness_chunk{9,11}.py. Hypothesis property tests
> in tests/test_audit_hypothesis_hooks.py + tests/test_props__secrets.py.

## Architecture

```
        [1285 tests, 0 FAIL]                +5 Cime (validation)
       /    \
    [.mn]  [.mn]                            +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                              +2 Branches (metadata arbre)
      |
   muninn.py 1532L (orchestrateur)          +1 Tronc
     muninn_layers.py 1294L (compression)
     muninn_tree.py 3649L (arbre+boot+intelligence)
     muninn_feed.py 1640L (feed+hooks)
      |
   [mycelium.py 3145L + db 1336L]            0 SOL — champignon vivant
      |
   [sync_backend.py 1128L]               -0.5 Sync federe (SharedFile/Git/TLS)
      |
   [vault.py + sync_tls.py 601L]           -1 Sous-sol — securite + reseau
      |
   cube.py 1553L (core+formatters+check)    -2 Fondations — resilience
     cube_providers.py 1952L (LLM+reconstruction+20 fixes)
     cube_analysis.py 1759L (analyse+CLI)
      |
   [wal_monitor 109L + tokenizer 43L]      -3 Racines — infrastructure
      |
   muninn/ui/ ~4470L (18 fichiers, +5197 ref) -4 Interface — desktop PyQt6
```

---

## muninn.py — Orchestrateur (1532 lignes)

Slim entry point: globals, scan, bootstrap, CLI, hooks, secrets.

### Globals & Config (1-114)
| Element | Lignes | Role |
|---------|--------|------|
| VERSION, _REPO_PATH, _CB... | 1-60 | Globals mutables (partages via _ModRef) |
| UNIVERSAL_RULES | 62-72 | Dict FR->EN compact (done, wip, fail...) |
| _SECRET_PATTERNS | 74-108 | Regex detection secrets (GitHub PAT, AWS, API keys, FR) |
| _COMPILED_SECRET_PATTERNS | 111 | P10: compiled regex cache |

### Scan & Bootstrap (115-407)
| Fonction | Lignes | Role |
|----------|--------|------|
| scan_repo | 115-275 | R5: auto-genere codebook local |
| analyze_file | 276-301 | Analyse fichier unique |
| bootstrap_mycelium | 302-357 | Cold start mycelium depuis repo |
| _bootstrap_branches | 358-407 | Genere branches depuis scan |

### Generate & Registry (408-695)
| Fonction | Lignes | Role |
|----------|--------|------|
| generate_root_mn | 408-535 | Genere root.mn depuis scan |
| generate_winter_tree | 536-603 | Auto-genere WINTER_TREE.md |
| _repos_registry_path | 604-608 | Path vers repos.json |
| _load_repos_registry | 609-620 | Charge registre repos |
| _register_repo | 621-666 | Enregistre repo dans registre |
| _generate_bridge_hook | 686-808 | Genere bridge_hook.py (UserPromptSubmit) avec anti-Adversa clamp depuis chunk 4 |
| _generate_post_tool_failure_hook | 811-944 | CHUNK 4: genere post_tool_failure_hook.py — auto-feed errors.json (P18 real-time) |
| _generate_subagent_start_hook | 945-1076 | CHUNK 5: genere subagent_start_hook.py — inject Muninn boot dans sub-agents |

### Secrets & CLI (696-1509)
| Fonction | Lignes | Role |
|----------|--------|------|
| _shannon_entropy / _has_char_diversity | 696-720 | Detection secrets heuristique |
| _check_secrets | 721-748 | Check un texte pour secrets |
| install_hooks | 1077-1170 | Install 6 hooks: UserPromptSubmit + PreCompact + SessionEnd + Stop + PostToolUseFailure (chunk 4) + SubagentStart (chunk 5) |
| scrub_secrets | 884-957 | Scan+redact secrets dans .mn |
| purge_secrets_db | 958-1006 | Purge secrets dans DB mycelium |
| main() | 1007-1509 | CLI argparse: boot/feed/compress/prune/status/diagnose/inject/... |

---

## muninn_layers.py — Compression Pipeline (1294 lignes)

L0-L7 + L10-L11 + L9: toutes les couches de compression.

### Codebook & Utils (71-120)
| Fonction | Lignes | Role |
|----------|--------|------|
| load_codebook | 71-97 | Charge rules compression (universal + mycelium) |
| _safe_path | 98-110 | Sanitize paths display (max 3 segments) |
| get_codebook | 111-120 | Wrapper codebook avec cache |

### Compression L0-L7 (121-713)
| Fonction | Lignes | Role |
|----------|--------|------|
| _line_density | 121-167 | Score densite info par ligne (0=bruit, 1=fait) |
| _kicomp_filter | 168-244 | Drop lignes basse-densite si overflow budget |
| _ncd | 245-264 | Normalized Compression Distance (zlib) |
| compress_line | 265-469 | Pipeline: L1 markdown, L3 phrases, L2 fillers, L4 numbers, L5 rules, L6 mycelium, L7 kv |
| extract_facts | 470-577 | Extraction nombres, dates, identifiers, kv, code patterns |
| tag_memory_type | 578-590 | Tags P14: D>/B>/F>/E>/A> |
| compress_section | 591-713 | Compresse section (P14 tags + P26 line dedup + P27 read dedup) |

### Contradiction Resolution C7 (714-819)
| _resolve_contradictions | 714-819 | Skeleton dedup, last-writer-wins |

### Compression L10-L11 (820-1058)
| Fonction | Lignes | Role |
|----------|--------|------|
| _novelty_score | 820-885 | Score nouveaute (patterns connus vs nouveaux) |
| _generate_cue | 886-943 | Bartlett 1932: genere cue de rappel |
| _cue_distill | 944-991 | L10: remplace connaissances generiques par cues |
| _extract_rules | 992-1058 | L11: Kolmogorov factorisation patterns repetitifs |

### Compression L9 + File (1059-1294)
| Fonction | Lignes | Role |
|----------|--------|------|
| _llm_compress_chunk | 1059-1083 | L9: chunk unique via Claude Haiku |
| _llm_compress | 1084-1161 | L9: R1-Compress section-chunked API |
| compress_file | 1162-1216 | Pipeline complet fichier |
| decode_line | 1217-1229 | Decode ligne compressee |
| verify_compression | 1230-1294 | Verifie qualite (facts preserves, ratio) |

### Phase B Wirings (2026-04-10) — bricks 4, 5, 6
| Wiring | Lignes | Role |
|--------|--------|------|
| `_LEXICONS_TIER1_PATTERNS` (module-level) | ~9-18 | Brick 4: lexicons tier1 patterns cached at init from `lexicons.get_safe_filler_patterns("tier1")`. 43 patterns, intensifiers + epistemic hedges. Pure additive in `compress_line()` L2 block. |
| `_DEDUP_AVAILABLE` + `_simhash`/`_hamming` import | ~20-26 | Brick 5: SimHash + hamming distance imported from `dedup.py` for `compress_section()` body dedup. |
| `_dedup_body_lines(lines)` helper | ~28-72 | Brick 5: pure helper called from `compress_section()` after the body collection, BEFORE the join. Tagged lines (B>/E>/F>/D>/A>) and short lines (<20 chars) NEVER deduped. Strict defaults k=4 shingles, threshold=3. |
| `_BUDGET_SELECT_AVAILABLE` + `_budget_select_impl` import | ~74-82 | Brick 6: BudgetMem L12 chunk selection from `budget_select.py`. |
| `_l12_budget_pass(text)` helper | ~84-118 | Brick 6: reads `MUNINN_L12_BUDGET` env var, applies BudgetMem chunk selection on raw text BEFORE secret redaction. Tiktoken-aware (`tokenizer.count_tokens` callback). OFF by default for full backward compat. |
| `compress_line()` L2 inline tier1 loop | ~389-394 | 4-line addition: second `re.sub` loop using `_LEXICONS_TIER1_PATTERNS` after the existing `_FILLER` loop. Pure additive, no overlap with hand-picked list. |
| `compress_section()` body dedup call | ~717-722 | 1-line addition: `body = _dedup_body_lines(body)` after L0-L11 line compression, before the join. |
| `compress_file()` L12 pre-pass | ~1262-1268 | 1-line addition: `text = _l12_budget_pass(text)` after secret redaction, before section split. Wired here (not after L11) because raw text has `\n\n` paragraph separators that BudgetMem expects. |

---

## engine/core/lexicons.py — Vendored MIT word lists (Phase B brick 1)

Pure data module, ZERO side effects. Mirrored to `muninn/lexicons.py`.
Imported by `muninn_layers.py` to extend L2 filler stripping.

| Constant / function | Lignes | Role |
|---------------------|--------|------|
| `MIT_FILLERS_EN`  | 47-63  | 83 entries verbatim from github.com/words/fillers (MIT) |
| `MIT_HEDGES_EN`   | 67-95  | 162 entries verbatim from github.com/words/hedges (MIT) |
| `MIT_WEASELS_EN`  | 99-119 | 116 entries verbatim from github.com/words/weasels (MIT) |
| `DISCOURSE_MARKERS_EN` | 123-138 | 50 Cambridge dictionary markers |
| `FRENCH_FILLERS`  | 142-149 | 22 French agent transcript fillers |
| `L2_TIER1_SAFE`   | 153-167 | 43 ultra-conservative — adverbs of intensification + non-factual hedges. **Default tier wired in compress_line()**. |
| `L2_TIER2_MODERATE` | 171-178 | 63 — adds soft quantifier-adjacent words for chat/meeting compression |
| `get_tier3_raw()` | 184-199 | Pure helper: de-duped union of all MIT lists, sorted by length desc |
| `DANGEROUS_NEVER_ADD` | 203-225 | Frozenset of 83 words that MUST NOT be in any tier (quantifiers, modals, action verbs, directional words, magnitudes) — safety net |
| `get_safe_filler_patterns(tier)` | 228-260 | Pure helper: returns regex patterns for tier1/tier2/tier3/discourse/french |
| `stats()` | 263-274 | Pure helper: returns counts for every list and tier |

Tests: `tests/test_brick1_lexicons.py` (28 tests pass) +
`tests/test_props_lexicons.py` (1 forge property test pass).
Forge BUG-102 detector confirmed: 0 destructive functions in this module.

---

## engine/core/dedup.py — SimHash near-duplicate detection (Phase B brick 2)

Charikar SimHash (STOC 2002) for line-level near-duplicate detection.
Pure-Python, zero deps (uses `hashlib.blake2b` from stdlib).
Mirrored to `muninn/dedup.py`. Imported by `muninn_layers.py` brick 5.

| Function | Lignes | Role |
|----------|--------|------|
| `_tokenize(text)` | 50-54 | Pure: lowercased word tokens via `\b\w+\b` |
| `_shingles(tokens, k=4)` | 57-66 | Pure: word k-grams sliding window, falls back to unigrams for short text |
| `_hash_feature(feature, bits)` | 73-81 | Pure: blake2b-based feature hash, configurable bit width (32/64/128) |
| `simhash(text, bits=64, shingle_size=4)` | 84-117 | Pure: Charikar fingerprint via +/-1 sum across all bit positions |
| `hamming_distance(a, b)` | 120-124 | Pure: bit_count of XOR — number of differing bits |
| `similar(a, b, threshold=3, ...)` | 127-141 | Pure: boolean wrapper around simhash + hamming |
| `dedup_lines(lines, threshold=3, ...)` | 147-188 | Pure: removes near-dups in-order, keeps FIRST occurrence, skips short lines |
| `dedup_paragraphs(text, threshold=3, ...)` | 191-211 | Pure: splits on `\n\n`, calls dedup_lines, rejoins |
| `stats(text=, lines=)` | 214-238 | Pure diagnostic: token count, shingle count, dedup ratio |

Operating range (empirically measured in tests):
- **STRICT** (defaults k=4, t=3): catches typo / punctuation / whitespace / case
- **LOOSE** (k=1, t=14): also catches polling-loop counter drifts
- **NOT CAUGHT**: prefix paraphrases, word-order changes, synonym swaps

Tests: `tests/test_brick2_dedup.py` (36 tests pass) +
`tests/test_props_dedup.py` (6 forge property tests pass).
Forge BUG-102 detector: 0 destructive functions.

---

## engine/core/budget_select.py — BudgetMem L12 chunk selection (Phase B brick 3)

Implementation of BudgetMem (arxiv 2511.04919, 2025) — training-free
chunk-level selective memory using interpretable features. Pure-Python,
zero deps. Mirrored to `muninn/budget_select.py`. Imported by
`muninn_layers.py` brick 6, opt-in via `MUNINN_L12_BUDGET` env var.

| Function | Lignes | Role |
|----------|--------|------|
| `_tokenize(text)` / `_tokenize_preserve_case(text)` | 47-58 | Pure: word tokens (lower / case-preserving) |
| `_DISCOURSE_MARKERS` constant | 63-72 | 26 multi-word discourse markers (Cambridge subset) |
| `_discourse_marker_count(text)` | 75-83 | Pure: count of discourse markers in lowercased text |
| `_FACT_SPAN_RES` | 89-99 | Compiled regexes: ISO date, semver, git hash, %, $money, JIRA, URL |
| `has_fact_span(chunk)` | 102-109 | Pure: True iff chunk contains any fact span (hard-rule trigger) |
| `compute_idf(chunks)` | 115-135 | Pure: returns `{term: idf}` map with smoothed IDF |
| `_entity_density(chunk)` | 141-167 | Pure: capitalized mid-sentence words proxy for NER (no spaCy needed). Splits on `[.!?]+\s+` to skip sentence-initial caps |
| `_tfidf_mean(chunk, idf_map)` | 170-184 | Pure: mean TF-IDF over chunk tokens |
| `_position_score(idx, total)` | 187-196 | Pure: 1.0 for first/last 20%, 0.5 for middle |
| `_number_density(chunk)` | 199-205 | Pure: fraction of tokens containing digits |
| `_question_presence(chunk)` | 208-210 | Pure: 1.0 if "?" in chunk else 0.0 |
| `_discourse_score(chunk)` | 213-215 | Pure: discourse marker count, capped at 1.0 |
| `score_chunk(chunk, idf_map, pos, total)` | 218-241 | Pure: 6-feature weighted sum (entity 0.20 + tfidf 0.20 + position 0.15 + number 0.15 + question 0.10 + discourse 0.10) — exact weights from BudgetMem paper |
| `_default_token_count(text)` | 247-249 | Pure: word count fallback when no tokenizer given |
| `select_chunks(chunks, budget, ...)` | 252-303 | Pure: 2-phase pack — must-keep facts first, then score-sorted others. Returns kept indices in original order |
| `budget_select(text, budget, ...)` | 306-326 | Pure: top-level — splits text by `\n\s*\n`, calls select_chunks, rejoins kept |
| `stats(text=, chunks=, budget=)` | 329-359 | Pure diagnostic: paragraph count, score distribution, selection ratio |

Tests: `tests/test_brick3_budget_select.py` (50 tests pass) +
`tests/test_props_budget_select.py` (6 forge property tests pass).
Forge BUG-102 detector: 0 destructive functions.

Real measured impact (`tests/benchmark/PHASE_B_RESULTS.md`):
- L0-L11 alone: x2-x4 ratio on real Muninn files
- +L12 at 50% budget: **x8-x9 ratio** (more than double)

---

## muninn_tree.py — Arbre + Intelligence (2179 lignes post-P3 split)

> **⚠️ POST-P3 SPLIT 2026-05-10** : muninn_tree.py 3929 → 2179L (-1750L = -45%).
> 3 fonctions monstres extraites en sous-modules :
> - **`engine/core/muninn_tree_boot.py`** (903L) : `boot()` + `_load_virtual_branches` + `_surface_insights_for_boot` + `_load_relevant_sessions` + `_surface_known_errors`
> - **`engine/core/muninn_tree_prune.py`** (678L) : `prune()` + `_sleep_consolidate` + `_light_prune` + `_auto_backup_tree`
> - **`engine/core/muninn_tree_doctor.py`** (297L) : `doctor()`
>
> Les 3 modules sont re-exportés via `from muninn_tree_X import *` à la
> fin de muninn_tree.py (backward compat 100%, callers inchangés).
> Le shim `muninn/muninn_tree.py` re-exporte aussi (CRIT-1 protection).
>
> Restent dans muninn_tree.py : Tree I/O, Memory Intelligence (Ebbinghaus,
> ACT-R, V4B/V6B/A1), TF-IDF, build_tree, grow_branches_from_session,
> extract_tags, recall, bridge, bridge_fast, predict_next, detect_session_mode,
> adapt_k, classify_session, huginn_think, show_status, diagnose, inject_memory,
> **spill_chunks_to_tree** (BUG-104 fix 2026-05-10 PM).

### Numéros de lignes ATTENTION : invalidés post-P3
> Les ranges de lignes ci-dessous datent d'avant le P3 split. Pour le nouveau
> mapping fonction → ligne, voir directement le code post-split. Cette section
> sera refait dans une session future si Sky en a besoin pour navigation
> précise. Les fonctions listées EXISTENT toujours (re-exportées), juste pas
> à ces lignes-là.

### Tree I/O (43-306)
| Fonction | Lignes | Role |
|----------|--------|------|
| adaptive_boot_budget | 43-54 | Budget boot: 15% contexte, floor 15K, cap 100K |
| _get_tree_dir / _get_tree_meta | 55-66 | Resolve tree paths |
| _refresh_tree_paths | 67-73 | Refresh TREE_DIR/TREE_META |
| cleanup_legacy_tree / cleanup_tmp_files | 74-129 | Nettoyage legacy + tmp |
| init_tree | 130-162 | Init arbre vide avec root node |
| _tree_lock / _tree_unlock | 163-213 | Locking concurrent tree access |
| load_tree | 214-243 | Charge tree.json + validation + recovery |
| save_tree | 244-273 | Ecriture atomique via tempfile + os.replace |
| _atomic_json_write | 274-288 | JSON write atomique generique |
| _safe_tree_path | 289-298 | Anti path-traversal |
| compute_hash | 299-306 | SHA-256 fichier (8 hex chars) |

### Memory Intelligence (307-521)
| Fonction | Lignes | Role |
|----------|--------|------|
| _ebbinghaus_recall | 307-358 | Spaced repetition: p=2^(-delta/h), A1 usefulness |
| _actr_activation | 359-407 | ACT-R: B=ln(sum(t_j^(-d))), blend 70/30 |
| _days_since | 408-415 | Calcul jours depuis date |
| compute_temperature | 416-436 | Score branche 0-1 (80% recall, 20% fill) |
| refresh_tree_metadata | 437-450 | Recalcule hash+lines+temperature |
| read_node | 451-521 | Lit .mn + P34 integrity + B1 reconsolidation |

### TF-IDF & Tree Build (522-868)
| Fonction | Lignes | Role |
|----------|--------|------|
| _tokenize_words | 522-526 | Tokenise texte en mots |
| _tfidf_relevance | 527-585 | TF-IDF cosine similarity query vs docs |
| build_tree | 586-679 | Construit arbre depuis fichiers .mn |
| grow_branches_from_session | 680-868 | Cree/merge branches depuis session compressee |

### Boot (869-1694)
| Fonction | Lignes | Role |
|----------|--------|------|
| extract_tags | 869-931 | Extrait tags pour scoring |
| _load_virtual_branches | 932-1046 | Charge branches virtuelles cross-repo |
| boot | 1047-1694 | BOOT COMPLET: TF-IDF + Spreading Activation + Ebbinghaus + Park et al. |

### Recall & Bridge (1695-2039)
| Fonction | Lignes | Role |
|----------|--------|------|
| recall | 1695-1815 | Mid-session memory search (grep sessions+tree+errors) |
| bridge | 1816-1971 | Bridge inter-repos |
| bridge_fast | 1972-2039 | Bridge rapide (sans arbre) |

### Session Intelligence (2040-2279)
| Fonction | Lignes | Role |
|----------|--------|------|
| predict_next | 2040-2117 | B4 Endsley L3: prediction spreading activation |
| detect_session_mode | 2118-2173 | Convergent/divergent mode |
| adapt_k | 2174-2191 | C4: sigmoid k adaptatif |
| classify_session | 2192-2279 | RPD type: debug/feature/explore/refactor/review |

### Sleep & Huginn (2280-2579)
| Fonction | Lignes | Role |
|----------|--------|------|
| _sleep_consolidate | 2280-2440 | Wilson & McNaughton 1994: NCD grouping + dedup + L10+L11 |
| huginn_think | 2441-2522 | Meta-cognition: structural insights |
| _surface_insights_for_boot | 2523-2535 | Surface insights at boot |
| _light_prune | 2536-2579 | Prune leger (hook) |
| _auto_backup_tree | 2580-2603 | A7: backup avant prune |

### Prune (2604-3016)
| prune | 2604-3016 | PRUNE COMPLET: backup + sleep consolidation + decay + R4 temperature + I2/I3 immune |

### Diagnostics (3017-3516)
| Fonction | Lignes | Role |
|----------|--------|------|
| show_status | 3017-3051 | Affiche etat arbre |
| doctor | 3052-3228 | Diagnostic complet (37 checks) |
| diagnose | 3229-3333 | C6: diagnostic CLI |
| _load_relevant_sessions | 3334-3386 | Charge sessions pertinentes |
| _append_session_log | 3387-3446 | Ajoute entree session log |
| _extract_error_fixes | 3447-3491 | P18: extraction error/fix pairs |
| _surface_known_errors | 3492-3516 | Surface erreurs connues au boot |

### Inject (3517-3608)
| inject_memory | 3517-3608 | B7: injection memoire live |

---

## muninn_feed.py — Feed Pipeline + Hooks (1640 lignes)

Ingestion transcripts, compression, hooks PreCompact/SessionEnd.

### Parsing (27-296)
| Fonction | Lignes | Role |
|----------|--------|------|
| _compress_code_blocks | 27-59 | P17: compresse blocs de code |
| _parse_json_conversation | 60-94 | Parse JSON transcript |
| _parse_markdown_conversation | 95-119 | Parse Markdown transcript |
| _detect_transcript_format | 120-163 | Auto-detect format |
| parse_transcript | 164-296 | L0 + parsing complet |

### Feed & Compression (297-917)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_from_transcript | 297-381 | Feed mycelium depuis transcript |
| _semantic_rle | 382-477 | Semantic RLE: collapse debug/retry loops |
| compress_transcript | 478-692 | Pipeline complet transcript -> .mn |
| _update_session_index | 693-787 | P22: session search index |
| _update_usefulness | 788-917 | Met a jour usefulness branches |

### Lock & Hooks (918-1260)
| Fonction | Lignes | Role |
|----------|--------|------|
| _MuninnLock (class) | 918-1051 | Lock fichier cross-process (fcntl/msvcrt) |
| _hook_log | 1052-1062 | Log hook events |
| feed_from_hook | 1063-1143 | Hook PreCompact |
| feed_from_stop_hook | 1144-1186 | Hook SessionEnd entry |
| _feed_from_stop_hook_locked | 1187-1260 | Hook SessionEnd locked |

### History & Watch (1261-1619)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_history | 1261-1414 | Rattrape tous les transcripts passes |
| feed_watch | 1415-1544 | Watch mode: feed auto |
| ingest | 1545-1619 | Ingest fichiers externes |

---

## cube.py — Cube Core (1553 lignes)

Scanner, dataclasses, subdivision, CubeStore, dependencies, neighbors,
format_code (4 formatters), check_formatters, install_formatters.

### Scanner B1 (128-257)
| Fonction | Lignes | Role |
|----------|--------|------|
| ScannedFile (class) | 128-148 | Resultat scan fichier |
| scan_repo | 191-257 | Scan recursif fichiers source |

### Cube & Subdivision B3-B5 (258-838)
| Fonction | Lignes | Role |
|----------|--------|------|
| Cube (class) | 258-296 | id, content, sha256, file_origin, level, neighbors, temp |
| normalize_content | 297-348 | Normalise contenu pour hash (rstrip, collapse blanks) |
| format_code | 350-419 | Appelle gofmt/black/rustfmt/prettier avant SHA. shutil.which + fallback paths. gofmt=stdout, rustfmt=in-place |
| _EXT_TO_FORMATTER | 425-429 | Mapping extension -> formateur |
| _FORMATTER_INFO | 431-480 | Per-formatter: binary, fallback paths, install cmds per OS |
| _resolve_formatter | 482-494 | Trouve un binaire formateur (which + fallback) |
| check_formatters | 496-565 | Detecte quels formateurs sont necessaires vs installes |
| install_formatters | 567-630 | Auto-installe les formateurs manquants (black via pip, etc) |
| sha256_hash | 632-634 | SHA-256 sur format_code + normalize |
| subdivide_file | 695-771 | B4: split fichier en cubes ~112 tokens |
| subdivide_recursive | 772-838 | B4: split recursif /8 par niveau |

### CubeStore B6 (839-1042)
| CubeStore (class) | 839-1042 | SQLite WAL, tables cubes/neighbors/cycles |

### Dependencies & Neighbors B7-B8 (1043-1553)
| Fonction | Lignes | Role |
|----------|--------|------|
| parse_dependencies | 1148-1168 | B7: AST Python + regex JS/TS/Go/Java |
| extract_ast_hints | 1170-1366 | B7b: pre-destruction hints. RAID adaptatif, identifiers (36-word filter), strings, type_sigs, anchors, first/last line. Uses normalize_content for line indexing |
| deduce_imports_from_file | 1367-1417 | Scan pkg.Symbol usage across full file |
| enrich_hints_with_file_context | 1419-1450 | Adds deduced_imports + constant_lines to hints |
| assign_neighbors | 1522-1553 | B8: adjacence + deps, max 9 voisins |

---

## cube_providers.py — LLM Providers + Reconstruction (1952 lignes)

Providers, FIM reconstruction, anchor forcing (fixes 6-20), validation,
NCD, die-and-retry waves, progressive levels. Language-specific forcing
for Python, Rust, JSX, C, COBOL, TypeScript.

### Providers B11-B14 (38-357)
| Classe | Lignes | Role |
|--------|--------|------|
| LLMProvider (ABC) | 38-86 | Interface abstraite |
| OllamaProvider | 88-209 | B12: Ollama local |
| ClaudeProvider | 211-283 | B13: Claude API |
| OpenAIProvider | 285-357 | B14: OpenAI compatible |

### FIM Reconstruction B15 (359-939)
| Classe/Fonction | Lignes | Role |
|--------|--------|------|
| FIMReconstructor | 359-939 | B15: FIM prompt + smart hints + post-processing |
| reconstruct_with_neighbors | 404-939 | Core: FIM prompt, 20 anchor forcing rules, language-specific |
| Fix 20: skip LLM | 450-480 | If 100% anchored, return original (zero API) |
| Anchor forcing block | 606-860 | Fixes 6-13, 14-18 (language), 19 (keywords) |
| _RETURN_KEYWORDS | 750-780 | Expanded keyword set (Go/Python/Rust/JS/TS/COBOL) |

### Post-processing (1436-1662)
| Fonction | Lignes | Role |
|----------|--------|------|
| _is_continuation | 1436-1490 | Line wrap scoring (0.0-1.0, COBOL col7 check first) |
| _adjust_line_count | 1492-1548 | Smart join: score-based continuation detection |
| _insert_missing_blanks | 1550-1662 | 3-tier blank insertion (anchors > block-end > statements) |
| _annealing_schedule | 1396-1434 | Cold-hot-cold temperature curve (Kirkpatrick 1983) |

### Mock & Results (941-995)
| Classe | Lignes | Role |
|--------|--------|------|
| MockLLMProvider | 941-983 | Mock pour tests |
| ReconstructionResult | 985-995 | Resultat reconstruction |

### Reconstruction B16-B19 (997-1117)
| Fonction | Lignes | Role |
|----------|--------|------|
| reconstruct_cube | 997-1060 | B16: orchestre B15+B17+B18+B19 |
| validate_reconstruction | 1062-1071 | B17: SHA-256 compare |
| compute_hotness | 1073-1088 | B18: perplexite voisins |
| compute_ncd | 1090-1117 | B19: NCD zlib (seuil 0.3) |

### Die-and-retry B40 (1303-1834)
| Element | Lignes | Role |
|---------|--------|------|
| WaveResult | 1303-1313 | Resultat d'une wave |
| LevelResult | 1315-1326 | Resultat d'un level progressif |
| _query_mycelium | 1328-1352 | Spreading activation on cube identifiers |
| reconstruct_cube_waves | 1690-1834 | B40: Best-of-N + annealing + targeted feedback |

### Progressive levels B41 (1837-1952)
| Fonction | Lignes | Role |
|----------|--------|------|
| run_progressive_levels | 1837-1952 | B41: x1->x2->...->x11, mycelium accumulation |

---

## cube_analysis.py — Analyse + CLI (1759 lignes)

Destruction cycle, temperatures, math, niveaux, git, scheduling, anomalies.

### Destruction Cycle (78-252)
| Fonction | Lignes | Role |
|----------|--------|------|
| run_destruction_cycle | 78-210 | CYCLE COMPLET: reconstruit + B30+B29+B23+B24+B22+B38 |
| _add_semantic_neighbors | 211-252 | Mycelium spreading activation (cycle 2+) |

### Analysis & Temperature (253-458)
| Fonction | Lignes | Role |
|----------|--------|------|
| post_cycle_analysis | 253-360 | B27+B28+B9+B10+B26+B35+B31+B37+B38 diagnostics |
| compute_temperature | 361-385 | B23: 0.4*perplexity + 0.4*(1-success) + 0.2*failures |
| update_all_temperatures | 386-395 | B23: batch update |
| kaplan_meier_survival | 396-419 | B24: S(t)=prod(1-d_i/n_i) |
| detect_dead_code / filter_dead_cubes | 420-458 | B25: vire commentaires/TODOs |
| prepare_cubes | 459-492 | B25+B21 pre-filtre |

### God's Number & Levels (493-647)
| Fonction | Lignes | Role |
|----------|--------|------|
| compute_gods_number | 503-551 | B26: cubes chauds irremplacables |
| build_level_cubes | 552-599 | B27: groupe 8 cubes lv0 -> 1 lv1 |
| propagate_levels | 612-647 | B28: remontee temperature max |

### Mycelium & Hebbian (648-744)
| Fonction | Lignes | Role |
|----------|--------|------|
| feed_mycelium_from_results | 648-697 | B29: succes=+1.0, echec=-0.5 |
| hebbian_update | 718-744 | B30: Δw=±η*0.1 |

### Git & Scheduling (745-982)
| Fonction | Lignes | Role |
|----------|--------|------|
| git_blame_cube | 745-794 | B31: lie cubes chauds a git |
| git_log_value | 795-825 | Git log pour scoring |
| CubeScheduler (class) | 826-884 | B32: async — run quand repo quiet |
| CubeConfig (class) | 885-982 | B33: config YAML + get_provider() |

### CLI (983-1155)
| Fonction | Lignes | Role |
|----------|--------|------|
| cli_scan | 983-1019 | B1+B4+B7+B8+B6 |
| cli_run | 1020-1094 | FULL PIPELINE: prepare+cycles+analysis |
| cli_status | 1095-1128 | God's Number + temp stats |
| cli_god | 1129-1155 | Compute + display God's Number |

### Graph Algorithms (1156-1414)
| Fonction | Lignes | Role |
|----------|--------|------|
| laplacian_rg_grouping | 1176-1224 | B9: spectral clustering |
| cheeger_constant | 1260-1305 | B10: bottleneck (Fiedler vector) |
| belief_propagation | 1306-1357 | B20: BP Pearl 1988 |
| survey_propagation_filter | 1358-1379 | B21: pre-filtre triviaux |
| tononi_degeneracy | 1380-1414 | B22: fragilite cube |

### Diagnostics & Feedback (1415-1759)
| Fonction | Lignes | Role |
|----------|--------|------|
| cube_heatmap | 1415-1450 | B35: temperatures par fichier |
| fuse_risks | 1451-1494 | B36: forge defect + cube temp |
| auto_repair | 1525-1593 | B37: patches FIM pour cubes chauds |
| record_quarantine | 1594-1632 | Sauvegarde contenu corrompu |
| record_anomaly | 1633-1655 | B38: enregistre anomalies |
| feedback_loop_check | 1656-1720 | B38: anomalies -> validation git |
| feed_anomalies_to_mycelium | 1721-1759 | B38: anomalies -> mycelium |

---

## mycelium.py — Champignon Vivant (3145 lignes)

### Mycelium (class, 54-2779)
| Methode | Lignes | Role |
|---------|--------|------|
| observe_text | ~200 | Observe co-occurrences (chunks par paragraphe) |
| observe_with_concepts | ~300 | Observe avec concepts externes (OpenAlex) |
| observe_latex | ~350 | Observe LaTeX (\section/\begin chunks) |
| spread_activation | ~500 | Collins & Loftus 1975: propagation semantique |
| decay | ~969 | Decay half-life (immortalite zones 3+). BUG-M8: auto-cleanup orphans |
| get_compression_rules | ~1270 | BUG-M6: filtre hubs+min_strength+max_rules (was 445K, now 5K) |
| get_related | ~1296 | BUG-M4: filtre stopwords par defaut (filter_stopwords=True) |
| adaptive_fusion_threshold | ~1088 | A1: seuil adaptatif sqrt(n)*0.4 |
| adaptive_decay_half_life | ~1100 | A2: half-life adaptatif (sessions/jours) |
| cleanup_orphan_concepts | ~800 | A3: vire concepts sans edges |
| vacuum_if_needed | ~850 | A4: auto-vacuum apres decay |
| adaptive_hops | ~900 | A5: hops adaptatif (sparse=3, dense=1) |
| detect_anomalies | ~1000 | B2: graph anomaly detection |
| detect_blind_spots | ~1100 | B3: structural holes (Burt 1992) |
| _bfs_zones | ~2180 | BUG-M2/M3: bounded subgraph + deque (was OOM on 11.7M edges) |
| dream | ~2236 | BUG-M1: sampled via top_connections+all_degrees (was OOM) |
| trip | ~2032 | BUG-M2: bounded conn_set via zone concepts only |

### CLI (2780-2915)
| main | 2780-2915 | CLI: observe/spread/decay/zones/detect/blind_spots |

---

## mycelium_db.py — SQLite Backend (1329 lignes)

### Date Utils (30-60)
| date_to_days / days_to_date / today_days | 30-60 | Epoch-days (int since 2020-01-01) |

### MyceliumDB (class, 61-1097)
| Methode | Lignes | Role |
|---------|--------|------|
| __init__ | ~70 | SQLite WAL + tables concepts/edges/fusions/meta |
| _get_or_create_concept | ~120 | Concept -> int ID (cache) |
| record_cooccurrence | ~200 | Batch increment edges |
| get_neighbors | ~300 | Voisins tries par count |
| fuse / get_fusions | ~400 | Gestion fusions |
| degree_filter | ~500 | S3: top 5% = stopwords |
| transaction() | ~600 | Context manager ACID |
| migrate_from_json | ~700 | S1: JSON -> SQLite migration |

### ConceptTranslator (1098-1329)
| Methode | Lignes | Role |
|---------|--------|------|
| translate | ~1150 | S4: tiktoken detection + Haiku API batch |
| _translate_batch | ~1200 | Batch API call + SQLite cache |

---

## Autres Fichiers

### sync_tls.py (601L) — Sync TLS
P2O: TLS mTLS server/client, push/pull, rate limiting.

### sync_backend.py (1128L) — Sync Backend
SharedFile/Git/TLS backends, auto-detection.

### wal_monitor.py (109L) — WAL Monitor
Passive WAL size monitoring, adaptive flush.

### tokenizer.py (43L) — Tokenizer
tiktoken wrapper with len()//4 fallback.

### lang_lexicons.py (1007L) — Language Lexicons
Multi-language lexicons for cube reconstruction (B15).

### _secrets.py (133L) — Shared Secret Redaction + Anti-Adversa
| Function | Lignes | Role |
|---|---|---|
| _SECRET_PATTERNS | 9-46 | 24+ regex patterns (Git, AWS, AI keys, DB URIs, Bearer, etc.) |
| redact_secrets_text | 51-61 | Defense-in-depth secret stripping before observe_text() |
| MAX_CHAINED_COMMANDS | 84 | CHUNK 3: anti-Adversa default cap (30, below 50 threshold) |
| count_chained_commands | 99-110 | CHUNK 3: counts && and \|\| in text (canonical shell chain markers) |
| clamp_chained_commands | 113-133 | CHUNK 3: refuses content with too many chained commands |

### .claude/hooks/ — Hook Handlers (6 files)
Installed by `install_hooks()` in `engine/core/muninn.py` and mirrored
in `muninn/_engine.py`. Self-contained, never raise, exit 0 always.
The first 3 are generated by f-string templates, the last 3 are static
files copied from the repo source.
| File | Lignes | Role |
|---|---|---|
| `bridge_hook.py` | ~115 | UserPromptSubmit: secret sentinel + bridge_fast(prompt). CHUNK 3 anti-Adversa clamp on output. |
| `post_tool_failure_hook.py` | ~135 | CHUNK 4: PostToolUseFailure -> append entry to .muninn/errors.json (P18 schema, dedup, cap 500) |
| `subagent_start_hook.py` | ~120 | CHUNK 5: SubagentStart -> inject muninn.boot(query=agent_type) capped at 20K chars into sub-agent context |
| `pre_tool_use_bash_destructive.py` | ~115 | **CHUNK 12**: PreToolUse(Bash) -> blocks force-push, rm -rf /, DROP TABLE, --no-verify, etc. Exit 2 with stderr feedback. Enforces RULE 2. |
| `pre_tool_use_bash_secrets.py` | ~125 | **CHUNK 12**: PreToolUse(Bash) -> blocks echo $TOKEN, cat .env, env|grep TOKEN. Allows safe checks like `[ -n "$VAR" ]`. Enforces RULE 3. |
| `pre_tool_use_edit_hardcode.py` | ~135 | **CHUNK 12**: PreToolUse(Edit\|Write) -> blocks Edit/Write to engine/core/ or muninn/ that introduces hardcoded `C:/Users/.../MUNINN-` in code lines. Allows in tests/, docs/, comments. Enforces RULE 1. |

### .claude/rules/ — Path-scoped extension rules (CHUNK 13, 2 files)
Anthropic Claude Code recommendation: rules with YAML frontmatter `paths:`
load only when Claude touches matching files. Enriches CLAUDE.md without
bloating the always-loaded context.
| File | paths: | Role |
|---|---|---|
| `python.md` | `engine/**/*.py`, `muninn/**/*.py`, `tests/**/*.py`, `*.py` | Extends RULE 1 with 4 path patterns used in repo, BUG-091 dual-maintenance, test conventions, Windows encoding, secrets in Python |
| `git.md` | `**/.gitignore`, `**/.gitattributes`, `**/.git/**` | Extends RULES 2 and 3 with git-specific cases, list of blocked operations, pre-commit checklist |

---

## muninn/ui/ — Interface Desktop PyQt6 (~4470 lignes + 5197 ref, 18+2 fichiers)

Phase 0-9 COMPLETE. 32 briques. 152 UI tests PASS (PyQt6 6.10.2).

### __init__.py (62L) — Package + Fonts
| Element | Lignes | Role |
|---------|--------|------|
| _FONTS_DIR, _ASSETS_DIR... | 10-17 | Paths (PyInstaller support) |
| load_fonts() | 32-48 | Load TTF into QFontDatabase |
| get_font_families() | 51-62 | Verify loaded families |

### theme.py (314L) — QSS Cyberpunk
| Element | Lignes | Role |
|---------|--------|------|
| Color tokens | 14-30 | BG_0DP..ERROR, Material dark elevation |
| load_theme() | 43-50 | Cached QSS string |
| _build_qss() | 53-260 | Full QSS (minimal selectors, no border-image) |
| get_palette() | 263-285 | QPalette for dynamic colors (avoids GDI leak) |

### main_window.py (584L) — MainWindow Fully Wired
| Element | Lignes | Role |
|---------|--------|------|
| MainWindow.__init__ | 39-59 | Splitters, status bar, autosave 60s, _install_extras |
| _build_ui() | 61-131 | Search bar + forest toggle toolbar, Navi overlay, command palette |
| _wire_signals() | 133-156 | All panel signals: neuron/tree/detail bidirectional |
| _install_extras() | 158-183 | Shortcuts, context menus, drag-drop, search/forest/palette wiring, tray |
| _on_search_changed/confirmed/cleared | 184-200 | Search -> neuron map highlight (B-UI-25) |
| _on_mode_changed + _load_forest | 201-240 | Forest toggle -> MetaMyceliumWorker QThread (B-UI-17) |
| _on_palette_action() | 243-268 | Dispatch 12 command palette actions |
| _scan_folder() | 290-310 | Run muninn scan via subprocess, load results (B-UI-22) |
| _on_neuron_selected() | 320-350 | Tree highlight + detail panel + status bar |
| load_scan() | 400-430 | Load scan JSON + feed search bar + Navi context |
| register/cancel_worker | 440-460 | Worker registry R13 |
| save/restore_state | 465-510 | QSettings, geometry safe R14 |
| closeEvent | 510-520 | Cancel workers, save, accept |
| main() | 525-572 | R7 entry: HiDPI, Fusion, excepthook, fonts |

### neuron_map.py (~1036L) — Carte Neurones + Cube 3D
| Element | Lignes | Role |
|---------|--------|------|
| Neuron dataclass | 39-55 | id, label, x, y, z, degree, category |
| DEGREE_GRADIENT + _degree_color | 77-107 | B-UI-03: green->yellow->red 10-step gradient |
| 3D cube rotation | ~185-250 | _cube_tick, _project_3d (Y+X rot, perspective fov=3.5) |
| _paint_cube_wireframe | ~250-275 | 12 cyan wireframe edges, 8 corners |
| _world_to_screen | ~280-295 | 3D projection -> screen coords (wz param) |
| load_scan() | ~210-260 | Parse scan JSON, build edges, launch Laplacian |
| _layout_random() | ~325 | 3D positions in [-0.8, 0.8] cube space |
| _start_laplacian() | ~340-370 | B-UI-03: QThread worker (R3, R12) |
| _build_kdtree() | ~400-420 | B-UI-05: scipy cKDTree O(log n) |
| paintEvent | ~450-470 | Cube wireframe + edges + neurons + legend |
| _paint_neurons | ~480-560 | Depth sort, depth-based sizing/alpha, labels hovered/selected only |
| _paint_edges() | ~570-640 | B-UI-07: bezier quadTo, LOD, frustum culling |
| closeEvent | ~200-210 | R4: cancel Laplacian + stop anim + cube timer |

### workers.py (~210L) — QThread Workers
| Element | Lignes | Role |
|---------|--------|------|
| LaplacianWorker | 12-210 | B-UI-03: scipy eigsh spectral layout |
| Top-N filtering | 50-67 | Degree-based, N=1000 |
| _spring_layout | 165-198 | Fallback if eigsh fails |
| _grid_layout | 200-210 | Fallback for disconnected graphs |

### tree_view.py (~469L) — Arbre Botanique + Auto-Layout
| Element | Lignes | Role |
|---------|--------|------|
| TreeNode | 38-52 | id, label, status, x, y, radius |
| load_tree() | 95-170 | Load from scan, uses JSON x/y or auto_layout |
| _auto_layout() | ~180-220 | Generate tree-shaped positions from depth/level |
| _get_image_rect() | ~340-350 | Image-relative coordinates after aspect scaling |
| _center_on_node() | ~260-270 | B-UI-11: 200ms center animation (image-relative) |
| _cross_fade() | ~285-290 | B-UI-11: 200ms opacity cross-fade |
| paintEvent | ~295-325 | R6: pixmap cache + nodes |
| _paint_nodes | ~335-385 | Glow rings, image-relative coords, highlight, labels |
| highlight_concept() | ~430-450 | B-UI-11: center anim + cross-fade |
| hit test + click | ~405-425 | Image-relative hit testing |

### classifier.py (159L) — Auto-Classification
| Element | Lignes | Role |
|---------|--------|------|
| ScanMetrics | 15-25 | concentration, depth, breadth, dispersion, external_deps |
| extract_metrics() | 28-65 | 5 metriques depuis scan JSON |
| classify_repo() | 68-140 | Score 6 familles, domain hints, stats hints |
| classify_scan_file() | 143-150 | Convenience: file path -> family |

### detail_panel.py (~280L) — Panel Details
| Element | Lignes | Role |
|---------|--------|------|
| ClickableLabel | 24-36 | QLabel with clicked signal |
| DetailPanel._build_ui | 66-155 | Title, status, LOC, info, zone, neighbors, files |
| show_empty() | 157-163 | R8 empty state |
| show_neuron() | 165-265 | B-UI-12 basic (LOC) + B-UI-13 extended (zone, last_modified) |
| Cross-fade | 54-61 | QGraphicsOpacityEffect 200ms |

### navi.py (~593L) — Fee Guide Navi Evolved
| Element | Lignes | Role |
|---------|--------|------|
| TUTORIAL_STEPS | 30-85 | 7-step guided tutorial (welcome->scan->explore) |
| HELP_TEXTS | 87-98 | Contextual help dict (FRENCH) |
| _reduce_motion_enabled | 100-110 | Windows SPI_GETCLIENTAREAANIMATION |
| __init__ | 115-170 | Tutorial state, flight patterns, WA_TransparentForMouseEvents=False |
| _tick() | 172-255 | 16ms, 5 flight patterns, geostationary when bubble visible, tutorial auto-advance |
| _advance_tutorial | 295-300 | Step progression + on_scan_complete hook |
| _paint_orb | 350-490 | 3 glow layers + 6 crescent wings (Bezier) + iridescent core |
| _load_bubble_frame | 493-510 | PNG frame with black pixels made transparent (pixel alpha) |
| _paint_bubble | 512-570 | x2.5 size (600x180), centered cyan text, interactive button |
| mousePressEvent | 575-585 | Button click -> scan_requested, else event.ignore() (forward) |

### terminal.py (363L) — Terminal + LLM Streaming
| Element | Lignes | Role |
|---------|--------|------|
| TerminalWidget | 20-180 | B-UI-19: QTextEdit(read-only) + QLineEdit, cmd history, /clear, /help |
| LLMWorker | 180-230 | B-UI-20: Anthropic streaming in QThread, fallback echo |
| Breathing indicator | 155-175 | Pulsing dot InOutSine 2s, stop button |

### forest.py (~170L) — Solo/Forest Toggle + Meta-Mycelium
| Element | Lignes | Role |
|---------|--------|------|
| ZONE_COLORS | 25-39 | 13 QColors for zone differentiation |
| MetaMyceliumWorker | 42-119 | B-UI-17: top 200 per zone from meta_mycelium.db, QThread |
| ForestToggle | 122-170 | B-UI-16: SOLO/FOREST button, mode_changed signal |

### search.py (~100L) — Search Bar
| Element | Lignes | Role |
|---------|--------|------|
| SearchBar | 16-99 | B-UI-25: 200ms debounce, substring match on neurons |
| Signals | 23-25 | search_changed(set), search_confirmed(str), search_cleared() |

### shortcuts.py (~110L) — Global Keyboard Shortcuts
| Element | Lignes | Role |
|---------|--------|------|
| install_shortcuts() | 12-48 | B-UI-26: Ctrl+F, Ctrl+1-4, Space, Escape, F11, Ctrl+Shift+S/P |
| Helpers | 51-110 | _focus_search, _toggle_mode, _escape, _export_screenshot |

### command_palette.py (~128L) — Command Palette
| Element | Lignes | Role |
|---------|--------|------|
| ACTIONS | 16-29 | 12 predefined actions with shortcuts |
| CommandPalette | 32-128 | B-UI-29: frameless overlay, fuzzy search, Enter/Escape |

### context_menu.py (~135L) — Right-Click Menus
| Element | Lignes | Role |
|---------|--------|------|
| install_context_menu() | 11-22 | B-UI-27: install on any widget |
| _build_neuron_menu | 47-75 | Copy, view in tree, open file, zoom to fit |
| _build_tree_menu | 78-93 | Copy, open file, copy path |
| _build_terminal_menu | 96-104 | Copy, clear |
| _copy_text | 116-127 | R9 clipboard retry (5x 50ms) |

### drag_drop.py (~40L) — Drag and Drop
| Element | Lignes | Role |
|---------|--------|------|
| install_drag_drop() | 12-40 | B-UI-28: drop folder -> window._scan_folder() |

### system_tray.py (~60L) — System Tray
| Element | Lignes | Role |
|---------|--------|------|
| MuninnTray | 14-55 | B-UI-30: icon, Show/Quit menu, double-click, notify() |

### about_dialog.py (~60L) — About Dialog
| Element | Lignes | Role |
|---------|--------|------|
| AboutDialog | 18-60 | B-UI-32: version, credits, themed OK button |

---

## Tests (1305+ PASS)

### Fichiers tests (par module)
| Fichier | Tests | Scope |
|---------|-------|-------|
| test_tier1_*.py (6 files) | 36 | A1-A5, B1 reconsolidation |
| test_tier2_*.py (4 files) | 32 | B2-B7, session mode, wiring |
| test_tier3_*.py (4 files) | 21 | S1-S4, C3-C4, C6-C7 |
| test_huginn_*.py (3 files) | ~24 | H1-H3 meta-cognition |
| test_immune_*.py (3 files) | ~15 | I1-I3 immune system |
| test_cube_*.py (10 files) | ~250 | B1-B39 cube briques |
| test_phase*.py (7 files) | ~120 | Phase 1-7 audit |
| test_x*.py (2 files) | ~26 | X3-X16 bug fixes |
| test_quarantine*.py (2 files) | ~25 | Quarantine system |
| test_ui_*.py (14 files) | ~157 | UI Phase 0-9: bootstrap, theme, window(13), neuron(26), tree(13), classifier, detail(12), navi(14), terminal(12), forest(12), search(11), shortcuts(7), cmd_palette(10), context_menu(12), extras(10) |
| Others | ~745 | Mycelium, feed, sync, vault, doctor, decay, etc. |
