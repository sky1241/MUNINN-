# Battle Plan FINAL — Light Up Everything (2026-05-13)

> **Verdict des 4e deep audit (12 mai soir)** : tout est trouvé, listé, chiffré.
> Sky ne doit plus oublier aucune feature.
>
> **Total dormant identifié et confirmé** : ~17 800 LOC code shipped + 3 hooks Claude Code + 1 env var + 1 flag + 2 TODO stubs vides.
>
> **Effort total pour TOUT brancher + garde-fou anti-régression** : **5h30**.

---

## Triage des 4 deep audits (faux positifs filtrés)

### ✅ CONFIRMÉ DORMANT (vrai code orphelin)

| # | Item | Où | LOC | Source audit |
|---|---|---|---|---|
| 1 | **Cube CLI** (cli_scan/run/status/god) | engine/core/cube_analysis.py | 5597 | Audit 1+2+4 |
| 2 | **muninn/ui/ entier** | muninn/ui/*.py (23 fichiers) | 11 712 | Audit 1+2+4 |
| 3 | **mycelium_dream.dream()** | engine/core/mycelium_dream.py | 561 | Audit 1+4 |
| 4 | **forge_metrics module** | engine/core/forge_metrics.py | 344 | Audit 1 |
| 5 | **sync_tls.py serve mode** | engine/core/sync_tls.py | 643 | Audit 1 |
| 6 | **watchdog.py** | engine/core/watchdog.py | 66 | Audit 1 |
| 7 | **3 hooks Claude Code** (post_tool_use_edit_log, pre_tool_use_*, config_change, notification_audit) | .claude/hooks/*.py | ~750 | Audit 3 |
| 8 | **--include-dreams flag** absent | engine/core/muninn.py argparse | — | Audit 1+4 |
| 9 | **--output flag** défini jamais lu | engine/core/muninn.py:942 | — | Audit 3 |
| 10 | **MUNINN_GL_SOFTWARE env var** documenté jamais lu | CLAUDE.md:195 | — | Audit 3 |
| 11 | **2 TODO stubs vides** | engine/core/muninn.py:682 + muninn/_engine.py:764 | — | Audit 4 |
| 12 | **89 fonctions zombies** non-MCP (dont 16 vraies dans cube_providers + ui) | divers | ~3000 | Audit 2 |
| 13 | **7 classes orphan** (AboutDialog, TreeHandler, ConceptTranslator, CubeScheduler, ForestToggle, SearchBar, PlaceholderPanel) | muninn/ui/ + engine/core/ | ~500 | Audit 2 |
| 14 | **102 méthodes publiques inutilisées** dans MyceliumDB (81% !), Cube (67%), Mycelium (50%) | classes vivantes | API bloat | Audit 2 |
| 15 | **3 fichiers .muninn/ dormants** (edits_log.jsonl write-only, session_index.json mystery, ...) | .muninn/*.json | — | Audit 3 |

### ❌ FAUX POSITIFS d'agents (filtrés)

| Item flaggé | Pourquoi c'est faux positif |
|---|---|
| `mycelium_recall` dans muninn/mcp/server.py | **WIRED via MCP stdio** — appelé live aujourd'hui par Claude Code. Pas un import Python. |
| `runbook_get`, `bugs_list`, `tree_get_root`, etc. (MCP tools) | Idem — registered via `@app.tool()` decorator, appelés stdio |
| 4 mixins mycelium | Wired via héritage class (`class Mycelium(MyceliumMetaMixin, MyceliumZonesMixin, MyceliumActivationMixin, MyceliumDreamMixin)`) |
| `forge --predict / --diff / --anomaly` | C'est forge-shield (binary externe PyPI), pas notre code. Pas notre problème |
| `MCP server 10 tools` flaggé "pas codé" | **WIRED depuis Phase B** — preuve live aujourd'hui : recall_local/meta/dual fonctionnent end-to-end |

---

## Le plan béton armé

### Méthodologie OBLIGATOIRE (post Phase E learnings)

Pour CHAQUE chunk H.X :
1. **Problème** — 1 phrase
2. **Code existant** — file:line + ce qui marche déjà
3. **Manque** — ce qui empêche d'être user-facing
4. **Implem** — diff minimal (no scope creep)
5. **Test pin WIRING-CHECK** — pas isolation, prouve appel en prod
6. **forge --gen-props** si engine/core/ touché (RULE 5)
7. **Output verbatim AVANT/APRÈS**
8. **Commit + push + watch CI green**

---

## Chunks ordonnés (5h30 total)

### 🛡️ Chunk H.0 — Garde-fou anti-orphan AVANT TOUT (30min)

**OBJECTIF** : Établir le **système immunitaire** AVANT de brancher quoi que ce soit. Si demain on rebranche tout, le test doit aujourd'hui être ROUGE. Demain après wiring, VERT. Et pour TOUJOURS, tout nouveau module orphan = CI rouge.

**Test pin** : `tests/test_wiring_no_orphan.py`
- `test_no_orphan_engine_module` : pour CHAQUE `engine/core/*.py`, assert qu'il a au moins 1 caller depuis le code SHIPPED (pas tests/). Whitelist : `__init__.py`, `watchdog.py` (standalone CLI documenté).
- `test_no_orphan_ui_module` : pour CHAQUE `muninn/ui/*.py`, assert qu'il est référencé soit par main_window.py soit par un autre module ui/.
- `test_all_documented_env_vars_read` : parse CLAUDE.md env vars table, assert chaque `MUNINN_*` listée a au moins 1 `os.environ.get` ou `os.getenv` dans engine/ ou muninn/.
- `test_all_argparse_flags_consumed` : pour chaque `parser.add_argument`, assert que `args.X` est utilisé quelque part dans main().
- `test_all_cli_commands_have_handler` : pour chaque choice dans argparse, assert un `if args.command == "X":` handler existe.
- `test_all_hooks_on_disk_registered` : list `.claude/hooks/*.py`, assert chacun est référencé dans `.claude/settings.local.json` OU explicitement dans une whitelist "intentional dormant".

**État attendu AUJOURD'HUI** : ROUGE (15 items orphan listés).
**État attendu APRÈS Phase H** : VERT.
**État futur** : si nouveau module ajouté sans wire, CI rouge immédiat.

**Effort** : 30min.

---

### 🔥 Chunk H.1 — Wire `muninn-mem cube` CLI (45min) — **5597 LOC débloquées**

**Problème** : Sky a codé 5597 LOC + 39 bricks Cube. **Aucun moyen de l'appeler**.

**Code existant** :
- `engine/core/cube_analysis.py:cli_scan(repo_path)` — init store
- `engine/core/cube_analysis.py:cli_run(repo_path, cycles=N, level=N)` — run reconstruction
- `engine/core/cube_analysis.py:cli_status()` — état du store
- `engine/core/cube_analysis.py:cli_god()` — god's number
- Anchors LLM boost via `_build_full_anchor_map`, `_learn_anchors_from_reconstruction` (cube_providers.py)

**Implem** :
1. Add `"cube"` dans argparse choices (engine/core/muninn.py + muninn/_engine.py mirror)
2. Add flags : `--cube-action {scan,run,status,god}` (default status) + `--cycles N` (default 1) + `--level N` (default 0)
3. Handler dans muninn.py qui call `cli_scan/run/status/god` selon action

**Test pin** : `tests/test_h1_cube_cli_wiring.py`
- `test_h1_cube_status_no_init` : sur dir vierge, `muninn-mem cube --cube-action status` → "no store yet" message friendly
- `test_h1_cube_scan_creates_store` : run scan sur tmp repo, assert store fichier créé
- `test_h1_cube_run_processes_cycles` : after scan, run avec --cycles 1, assert cycle count incrementé
- `test_h1_cube_god_returns_dict` : assert god() retourne dict avec keys attendues
- `test_h1_cube_in_argparse_choices` : assert "cube" in choices list

**forge** : forge --gen-props engine/core/muninn.py.

---

### 🖼️ Chunk H.2 — Wire `muninn-ui` console script (30min) — **11 712 LOC débloquées**

**Problème** : 23 fichiers PyQt6 totalisant 11 712 LOC. **Aucun entry point user**.

**Code existant** :
- `muninn/ui/main_window.py:MainWindow` class avec layout 4-panneaux
- 22 autres modules : neuron_map, cube_live, terminal, ai_router, theme, system_tray, command_palette, context_menu, forest, tree_view, detail_panel, etc.
- 15 tests `test_ui_*.py` passent avec `QT_QPA_PLATFORM=offscreen`

**Implem** :
1. Vérifier que `main_window.py` a une fonction `main()` (créer si absent : `def main(): app = QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec())`)
2. Add `muninn/ui/__main__.py` : `from .main_window import main; main()`
3. Add à pyproject.toml `[project.scripts]` :
   ```toml
   muninn-ui = "muninn.ui.main_window:main"
   ```
4. Add `[project.optional-dependencies]` :
   ```toml
   ui = ["PyQt6>=6.10"]
   ```
5. Update `all` extra pour include `ui`

**Test pin** : `tests/test_h2_ui_wiring.py`
- `test_h2_ui_console_script_in_pyproject` : assert "muninn-ui" in [project.scripts]
- `test_h2_ui_main_callable` : importlib resolve `muninn.ui.main_window:main`, assert callable
- `test_h2_ui_pyqt_extra_declared` : assert "ui" in optional-dependencies
- `test_h2_ui_offscreen_launches` : subprocess.run `QT_QPA_PLATFORM=offscreen muninn-ui` avec timeout 3s, kill, assert process started OK (pas crash import)

**Activer CI UI tests** (bonus) :
- Update ci.yml step pytest : retirer `--ignore-glob='tests/test_ui_*.py'`
- Add `env: QT_QPA_PLATFORM=offscreen`
- Add apt install : `libegl1 libgl1 libxkbcommon0`

---

### 💤 Chunk H.3 — Add `--include-dreams` flag (15min) — **561 LOC débloquées**

**Problème** : `mycelium_dream.py:dream()` (sleep consolidation Wilson & McNaughton 1994, 561 LOC) wired conditionnellement dans `prune(include_dreams=True)` mais **le flag CLI n'existe pas**.

**Implem** :
1. `parser.add_argument("--include-dreams", action="store_true", help="Activate sleep consolidation during prune (writes insights.json)")`
2. Dans handler prune : `m.prune(force=args.force, include_dreams=args.include_dreams)`
3. Mirror dans muninn/_engine.py

**Test pin** : `tests/test_h3_dream_flag.py`
- `test_h3_flag_in_help` : `muninn-mem prune --help` output contient `--include-dreams`
- `test_h3_flag_triggers_dream` : monkeypatch `Mycelium.dream`, run `muninn-mem prune --force --include-dreams`, assert dream() called
- `test_h3_flag_off_skips_dream` : sans flag, assert dream() not called
- `test_h3_insights_json_written` : after flag run, assert `.muninn/insights.json` exists

---

### 📊 Chunk H.4 — Wire `muninn-mem forge` (or `metrics`) CLI (30min)

**Problème** : `engine/core/forge_metrics.py` (344 LOC) calcule Carmack ratio + Newman-Girvan Q. Pas accessible CLI.

**Décision Sky avant kick-off** : nom = `forge` (risque confusion forge-shield PyPI) OU `metrics` (clair, no clash) ?

**Implem** :
1. Add `"metrics"` ou `"forge"` dans argparse choices
2. Handler appelle `forge_metrics.compute_metrics(repo)` + pretty-print
3. Optional `--output forge.json` (réutilise le flag `--output` mort de H.5)

**Test pin** : `tests/test_h4_metrics_cli.py`
- `test_h4_metrics_command_exists` : `muninn-mem metrics --help` exit 0
- `test_h4_metrics_returns_q` : assert "Q =" dans stdout
- `test_h4_metrics_output_json` : avec --output, assert fichier JSON créé

---

### ⚰️ Chunk H.5 — Cleanup "silent dead config" (15min)

**Problème** : 3 items documentés mais jamais lus/utilisés (Audit 3) :
1. `MUNINN_GL_SOFTWARE` env var dans CLAUDE.md:195, **0 occurrences en code**
2. `--output` argparse flag (line 942), **jamais consulté post-parse**
3. 2 TODO stubs vides : engine/core/muninn.py:682 + muninn/_engine.py:764 ("## TODO\n- [ ] Verifier que le bootstrap a capture les bons concepts")

**Décision Sky** :
- `MUNINN_GL_SOFTWARE` : **wire-or-drop**. Si Qt/Vulkan workaround nécessaire pour UI (H.2), wire dans main_window.py. Sinon retirer de CLAUDE.md.
- `--output` : **wire-or-drop**. H.4 le réutilise probablement. Sinon retirer.
- TODO stubs : soit clarifier (ajouter description), soit supprimer.

**Test pin** : (couvert par H.0 test_all_documented_env_vars_read + test_all_argparse_flags_consumed)

---

### 🪝 Chunk H.6 — Wire 5 hooks Claude Code orphans (30min)

**Problème** : Audit 3 confirme **3 hook files sur disque PAS dans settings.local.json** :
- `post_tool_use_edit_log.py` (écrit `.muninn/edits_log.jsonl` write-only)
- `pre_tool_use_bash_destructive.py`
- `pre_tool_use_bash_secrets.py`
- `pre_tool_use_edit_hardcode.py`
- `config_change_hook.py`
- `notification_audit_hook.py`

CLAUDE.md ligne 224 affiche "10 scripts wirés" → **MENSONGE** : seuls 7 vraiment registered.

**Décision Sky** : Activer les 3 hooks défensifs ? (PreToolUseBash destructive/secrets, PreToolUseEdit hardcode protègent RULE 1/2/3 en pratique). OU les laisser dormant explicitement avec doc.

**Implem si activer** :
- Add les 5 hooks dans `.claude/settings.local.json` `hooks` section
- Mettre à jour `install_hooks()` dans muninn_install.py pour register ces hooks au prochain `muninn-mem init`

**Test pin** : `tests/test_h6_all_hooks_registered.py`
- Pour CHAQUE `.claude/hooks/*.py`, assert sa référence existe dans settings.local.json OU dans une whitelist documentée "intentionnel dormant".

---

### 🧹 Chunk H.7 — Décisions finales sync_tls + watchdog + classes orphan (15min)

**Items à décider** :
1. **sync_tls.py** (643 LOC) — TLS sync distant. Sky pas de serveur. Options : drop OU `[experimental]` extra OU doc opt-in via env var
2. **watchdog.py** (66 LOC) — Windows Task Scheduler standalone. Sky sur Linux. Options : drop OU doc "Windows-only"
3. **7 classes orphan** (AboutDialog, TreeHandler, ConceptTranslator, CubeScheduler, ForestToggle, SearchBar, PlaceholderPanel) :
   - Si elles sont dans muninn/ui/ et qu'on wire l'UI en H.2, peut-être qu'elles s'activeront naturellement
   - Sinon drop

**Décisions par défaut (Sky override possible)** :
- sync_tls : déplacer dans `engine/core/experimental/sync_tls.py` + doc
- watchdog : drop (Linux-only Sky)
- Classes UI orphan : sera couvert par H.2 wiring naturel, sinon drop dans cycle suivant

---

### 🧪 Chunk H.8 — 102 méthodes publiques inutilisées : décision (30min)

**Problème** : Audit 2 trouve **API bloat massif** :
- MyceliumDB : **57/70 méthodes publiques jamais appelées** (81% API mort)
- Cube : 32/48 jamais appelées (67%)
- Mycelium : 13/26 (50%)

**Décision Sky** : Refactor MyceliumDB en priorité (le pire) ? Ou laisser car ça marche ?

**Recommandation** : Pas dans Phase H actuelle (trop gros). Note pour **Phase I** : "MyceliumDB interface narrowing" — réduire l'API publique de 70 → ~15 méthodes utilisées, marquer le reste `_private` ou supprimer.

Pour H.8 actuel : juste documenter la dette + créer un test garde-fou anti-régression : `test_no_new_public_method_added_to_core_classes_without_caller`.

**Effort** : 30min pour le garde-fou. Le refactor lui-même = Phase I (futur).

---

### 📄 Chunk H.9 — Docs + CHANGELOG + WINTER_TREE (15min)

- Update CHANGELOG avec Phase H delivered (avec NOMS DES FEATURES nouvellement accessibles)
- WINTER_TREE snapshot final post-H
- README : section "Quick reference 35 CLI commands" (toutes documentées)
- QUICKSTART : ajouter exemples concrets pour `cube`, `ui`, `--include-dreams`
- CLAUDE.md : retirer `MUNINN_GL_SOFTWARE` ou wire ; corriger "10 hooks" → vrai count
- Suppression du faux `## TODO` stubs

---

### 🎯 Chunk H.10 — Bump 1.0.3 → 1.1.0 + release (15min)

**Pourquoi 1.1.0 (minor) et pas 1.0.4 (patch)** : Ajout features publiques majeures (`cube` CLI, `muninn-ui` console script, `--include-dreams` flag) = backward-compatible mais SIGNIFICATIF.

**Étapes** :
1. Bump 1.0.3 → 1.1.0 (4 mirrors)
2. `rm -rf dist && python3 -m build`
3. `twine check dist/*`
4. Run full test_protocol mais updated pour 1.1.0
5. Upload TestPyPI 1.1.0 via terminal interactif
6. Validate venv vierge
7. Décision Sky : upload PyPI prod 1.1.0 OU TestPyPI seulement

---

## Récap effort total

| Chunk | Effort | LOC débloquées |
|---|---|---|
| H.0 garde-fou anti-orphan | 30min | (système immunitaire) |
| H.1 Cube CLI | 45min | 5 597 |
| H.2 muninn-ui | 30min | 11 712 |
| H.3 --include-dreams | 15min | 561 |
| H.4 metrics CLI | 30min | 344 |
| H.5 dead config cleanup | 15min | (3 items) |
| H.6 hooks orphans | 30min | ~750 |
| H.7 sync_tls + watchdog | 15min | 709 (drop ou doc) |
| H.8 API bloat MyceliumDB | 30min | (garde-fou, refactor Phase I) |
| H.9 docs | 15min | — |
| H.10 release 1.1.0 | 15min | — |
| **TOTAL** | **5h30** | **~19 600 LOC** dormantes activées ou explicitement classifiées |

---

## 5 décisions Sky avant kick-off demain matin

1. **Phase H complète 5h30** ou réduite à H.0+H.1+H.2+H.3 (2h critiques) ?
2. **UI command name** : `muninn-ui` séparé OU `muninn-mem ui` sub-command ?
3. **Forge command name** : `muninn-mem forge` (clash forge-shield ?) OU `muninn-mem metrics` ?
4. **Hooks orphans (H.6)** : activer les 5 hooks défensifs/audit OU laisser dormants documentés ?
5. **sync_tls + watchdog (H.7)** : drop / experimental folder / opt-in ?

---

## Garantie post-Phase H

**Plus jamais une feature codée mais pas en prod sans que la CI le détecte.**

Le test `test_wiring_no_orphan_engine_module` + ses 5 cousins font le travail automatiquement à chaque push.

Si Sky code une feature géniale dans `engine/core/awesome_new_thing.py` mais oublie de la wire au CLI, la CI sera rouge.

Si quelqu'un ajoute `--cool-flag` dans argparse mais n'utilise pas `args.cool_flag`, CI rouge.

Si CLAUDE.md mentionne `MUNINN_AWESOME_VAR` mais 0 `os.environ.get("MUNINN_AWESOME_VAR")` dans le code, CI rouge.

**Système immunitaire actif. Sky peut coder sans peur d'oublier.**
