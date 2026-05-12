# Phase H — "Light Up Everything" (2026-05-13)

> **Sky est énervé** : "j en ait marre des truc coder mais pas en production sa me fait chier".
>
> **Verdict des 4 deep audits** : ~20 000 LOC codées + testées qui MARCHENT mais n'ont **pas de chemin d'entrée user** (CLI manquant, console script manquant, ou flag absent).
>
> **Objectif Phase H** : brancher TOUT, avec des tests "wiring-check" qui PROUVENT que c'est vraiment en prod (pas juste qu'isolément le code marche).
>
> **Effort total estimé** : ~4h30.

---

## Méthodologie obligatoire (post Phase E learnings)

Pour CHAQUE chunk :
1. **Problème** — 1 phrase
2. **Code existant** — où il vit, qui le wire actuellement
3. **Ce qui manque pour user-facing** — CLI / console script / flag / hook / cron
4. **Implémentation** — diff minimal, pas de scope creep
5. **Test pin WIRING-CHECK** — pas juste "ça marche en isolation", mais "ça EST appelé en prod quand l'user fait l'action attendue"
6. **forge --gen-props** si engine/core/ touché
7. **Output verbatim AVANT/APRÈS**
8. **Commit + push + watch CI green**

---

## H.1 — Wire `muninn-mem cube` sub-command (45min) — **CRITIQUE**

**Problème** : Le système Cube (5597 LOC, 39 bricks B1-B39, anti-code-loss + reconstruction) est complètement codé et testé. Mais Sky n'a JAMAIS pu l'utiliser parce qu'**il n'existe pas de commande CLI**.

**Code existant** :
- `engine/core/cube_analysis.py:cli_scan(repo_path)` — initialise le store
- `engine/core/cube_analysis.py:cli_run(repo_path, cycles=N)` — exécute reconstruction cycles
- `engine/core/cube_analysis.py:cli_status()` — état du cube store
- `engine/core/cube_analysis.py:cli_god()` — god's number (reconstruction optimale)
- Anchors LLM boost (`_build_full_anchor_map`, `_learn_anchors_from_reconstruction`) déjà dans `cube_providers.py`

**Manque pour user-facing** :
- Pas dans `argparse choices` (line 927 de muninn.py)
- Pas de handler `if args.command == "cube":`

**Implémentation** :
1. Add `"cube"` à argparse choices
2. Add sub-flags : `--cube-action scan|run|status|god` + `--cycles N` (default 1) + `--level N` (default 0)
3. Handler dans muninn.py + mirror muninn/_engine.py :
   ```python
   if args.command == "cube":
       from cube_analysis import cli_scan, cli_run, cli_status, cli_god
       repo = Path(args.repo or ".").resolve()
       action = getattr(args, "cube_action", "status")
       if action == "scan": cli_scan(str(repo))
       elif action == "run": cli_run(str(repo), cycles=args.cycles, level=args.level)
       elif action == "status": cli_status()
       elif action == "god": cli_god()
       return
   ```

**Test pin WIRING-CHECK** : `tests/test_h1_cube_cli_wiring.py`
- `test_h1_cube_scan_creates_store` : run `muninn-mem cube --cube-action scan` sur tmp_path, assert `.muninn/cube/` ou store file créé
- `test_h1_cube_run_processes_cycles` : after scan, run `--cube-action run --cycles 1`, assert au moins 1 cube reconstruit (verifiable via stdout count)
- `test_h1_cube_god_returns_dict` : assert god() retourne dict avec keys attendues

**Forge** : muninn.py + muninn/_engine.py touchés → `forge --gen-props engine/core/muninn.py`.

**Valeur livrée** : 5597 LOC + 39 bricks deviennent enfin user-accessible. Sky peut faire `muninn-mem cube --cube-action scan` puis `--cube-action run --cycles 10` pour tester l'anti-code-loss sur un repo.

---

## H.2 — Add `--include-dreams` flag à `prune` (15min)

**Problème** : `mycelium_dream.py:dream()` (561 LOC, sleep consolidation Wilson & McNaughton 1994) est codé. `muninn_tree_prune.py` accepte un param `include_dreams=True` mais **le flag CLI n'existe pas** — donc impossible de l'activer.

**Manque** : `parser.add_argument("--include-dreams", action="store_true")` + plumbing vers `prune(include_dreams=args.include_dreams)`.

**Implémentation** : 2 lignes ajoutées dans muninn.py + 2 dans muninn/_engine.py + 1 ligne dans `prune()` handler qui passe le flag.

**Test pin** : `tests/test_h2_include_dreams_flag.py`
- `test_h2_flag_in_argparse` : assert `--include-dreams` est listée dans `muninn-mem prune --help`
- `test_h2_flag_triggers_dream_call` : monkeypatch `Mycelium.dream`, run `muninn-mem prune --force --include-dreams`, assert dream() called
- `test_h2_flag_off_skips_dream_call` : sans flag, dream() NOT called

**Valeur** : 561 LOC sleep consolidation activables. Insights générés dans `.muninn/insights.json` (déjà codé).

---

## H.3 — `muninn-ui` console script + entry point (30min) — **CRITIQUE**

**Problème** : 23 fichiers PyQt6 dans `muninn/ui/` totalisant **11 712 LOC** (!) sont 100% DORMANTS parce que **pas de console script** et **pas de `__main__.py`** dans `muninn/ui/`.

**Code existant** :
- `muninn/ui/main_window.py` (626 LOC) — `MainWindow` class avec layout 4-panneaux
- 22 autres modules : cube_live (visualisation live Cube reconstruction), neuron_map, terminal embarqué, ai_router, theme, system_tray, command_palette, context_menu, forest (meta-mycelium viz), tree_view, detail_panel, etc.
- Tests UI : 15 fichiers `test_ui_*.py` — **passent en CI si on set `QT_QPA_PLATFORM=offscreen`**

**Manque user-facing** :
- Console script `muninn-ui` dans pyproject.toml
- Fonction `main()` dans `main_window.py` callable depuis l'entry point
- `__main__.py` dans `muninn/ui/` pour `python -m muninn.ui`
- Optionnel : extras `[ui]` dans pyproject.toml pour `pip install muninn-memory[ui]`

**Implémentation** :
1. Vérifier que `main_window.py` a un `def main():` ou en créer un qui fait `QApplication(sys.argv); win = MainWindow(); win.show(); sys.exit(app.exec())`
2. Add `muninn/ui/__main__.py` : `from .main_window import main; main()`
3. Add à `pyproject.toml` `[project.scripts]` :
   ```toml
   muninn-ui = "muninn.ui.main_window:main"
   ```
4. Add `[project.optional-dependencies]` :
   ```toml
   ui = ["PyQt6>=6.10"]
   ```
5. Update `all` extra pour inclure ui

**Test pin** : `tests/test_h3_ui_wiring.py`
- `test_h3_ui_console_script_declared` : parse pyproject.toml, assert `muninn-ui` dans scripts
- `test_h3_ui_main_callable` : import `muninn.ui.main_window`, assert `hasattr(main_window, "main") and callable(main_window.main)`
- `test_h3_ui_pyqt_extra_declared` : assert `ui` extra dans optional-dependencies

**Activer CI tests UI** (bonus) :
- Update `.github/workflows/ci.yml` step pytest : retirer `--ignore-glob='tests/test_ui_*.py'`
- Add `env: QT_QPA_PLATFORM=offscreen` au pytest step
- Add `apt-get install -y libegl1 libgl1` ou équivalent au CI prep

**Valeur** : Sky lance `muninn-ui` et voit son interface 4-panneaux Muninn EN VRAI. Premier vrai utilisateur de l'UI : lui-même.

---

## H.4 — `muninn-mem forge` command (30min)

**Problème** : `engine/core/forge_metrics.py` (344 LOC) calcule Carmack ratio + modularity Newman-Girvan Q. Existait pour intégration UI mais jamais exposé en CLI.

**Code existant** : `forge_metrics.py:compute_metrics(repo_path)` + helpers.

**Manque user-facing** : pas dans argparse choices, pas de handler.

**Implémentation** :
1. Add `"forge"` à argparse choices
2. Handler appelle `forge_metrics.compute_metrics(repo)` + pretty-print
3. Optionnel : `muninn-mem forge --output forge.json` pour export

**Test pin** : `tests/test_h4_forge_cli_wiring.py`
- `test_h4_forge_command_exists` : `muninn-mem forge --help` exit 0
- `test_h4_forge_returns_modularity` : run sur tmp_path repo + assert "Q =" ou "modularity" dans stdout

**Note** : Il y a déjà `forge-shield` PyPI v1.3.0 (binary distinct). Notre `muninn-mem forge` serait une mince couche qui appelle nos métriques internes (pas le binary externe). Risque de confusion → maybe renommer en `muninn-mem metrics` ou `--carmack-modularity`. À décider avec Sky.

**Valeur** : 344 LOC accessibles. Sky peut voir Q en direct sans recompiler.

---

## H.5 — Exposer les 4 mycelium mixins via CLI (45min)

**Problème** : 4 mixins (1917 LOC total) PARTIAL — fonctions wired via héritage Mycelium class mais aucun CLI direct pour les invoquer individuellement.

| Mixin | LOC | Fonctions clés | CLI proposé |
|---|---|---|---|
| `mycelium_activation.py` | 545 | spread_activation, ACT-R retrieval threshold | `muninn-mem mycelium activate <seed>` |
| `mycelium_dream.py` | 561 | dream(), trip() | déjà via `muninn-mem trip` ✓ + H.2 flag |
| `mycelium_meta.py` | 428 | meta_db_path, sync helpers | `muninn-mem mycelium meta` (stats meta DB) |
| `mycelium_zones.py` | 383 | detect_zones, auto_label_zones, Laplacian | déjà via `muninn-mem zones` ✓ |

**Manque** : Ajouter sub-commands `muninn-mem mycelium activate|meta` (et confirmer `trip`/`zones` doc explicite).

**Implémentation** : un sub-dispatch dans muninn.py + 2 nouveaux handlers (activate, meta).

**Test pin** : `tests/test_h5_mycelium_mixins_cli.py`
- 4 tests subprocess assert chaque mixin invocable via CLI

**Valeur** : Surface API mycelium accessible directement par script/cron, pas seulement via le flow feed.

---

## H.6 — Wiring-check tests pour TOUS les features dormants/critiques (1h30) — **LE PLUS IMPORTANT**

**Problème** : Aujourd'hui on a des tests qui prouvent "feature X marche en isolation" (test_vault, test_cube_b1_b6, etc.) mais **rien ne prouve que feature X est appelée en prod**. C'est exactement ce qui a permis à 20K LOC de glisser en dormance.

**Solution** : Une suite `tests/wiring/` qui pour CHAQUE feature mainstream prouve que son code path est traversé par un flow user normal :

1. `test_wiring_cube_called_by_cli_cube` (post H.1)
2. `test_wiring_dream_called_when_include_dreams_flag` (post H.2)
3. `test_wiring_ui_console_script_resolves` (post H.3)
4. `test_wiring_forge_metrics_invoked_by_cli` (post H.4)
5. `test_wiring_mycelium_activation_invoked_by_cli` (post H.5)
6. `test_wiring_mycelium_zones_invoked_by_cli` (existing zones command)
7. `test_wiring_vault_lock_unlock_full_flow` (vault.py)
8. `test_wiring_l12_budgetmem_when_env_var_set` (L12 chunk selection)
9. `test_wiring_l9_llm_compression_when_api_key_set` (mock anthropic)
10. `test_wiring_no_orphan_engine_modules` : pour chaque engine/core/*.py, assert au moins 1 caller dans le code shipped (pas dans tests/)

Le dernier test (`test_wiring_no_orphan_engine_modules`) est le **garde-fou anti-régression** : si un futur module est ajouté mais jamais wired, le test échoue.

**Implémentation** : 1h30 pour les 10 tests. Utiliser `subprocess.run`, `monkeypatch`, ou `unittest.mock.patch` pour intercepter et vérifier les calls.

**Valeur** : **Système immunitaire contre le code dormant**. Si un futur chunk ajoute un module qui n'est pas branché, CI rouge.

---

## H.7 — Décision finale sur sync_tls + watchdog (15min)

**`sync_tls.py` (643 LOC)** :
- TLS sync distant pour multi-machine federated mycelium
- Sky n'a pas de serveur distant aujourd'hui
- Options :
  - (A) Wire en mode "opt-in via `MUNINN_SYNC_TLS_HOST=...`" + doc README
  - (B) Marquer `[experimental]` extras dans pyproject.toml
  - (C) Déplacer dans `engine/core/experimental/` sub-folder

**`watchdog.py` (66 LOC)** :
- Standalone Windows Task Scheduler script
- Sky est sur Linux → probablement inutile pour lui
- Options :
  - (A) Drop le fichier
  - (B) Garder mais doc "Windows-only, run manually"

Décision à prendre demain avec Sky.

---

## H.8 — Doc + CHANGELOG + WINTER_TREE snapshot (15min)

- Update CHANGELOG avec Phase H delivered
- WINTER_TREE snapshot final
- README : ajouter section "Quick reference" qui liste les ~35 CLI commands user-facing
- QUICKSTART : ajouter exemples pour cube, ui, --include-dreams

---

## Ordre d'exécution recommandé

| # | Chunk | Effort | Cumulatif | Pourquoi cet ordre |
|---|---|---|---|---|
| 1 | H.6 partiel (test_wiring_no_orphan_engine_modules) | 30min | 30min | Établir le garde-fou AVANT de wire pour qu'il échoue, puis voir vert après wiring |
| 2 | H.1 Cube CLI | 45min | 1h15 | Plus gros gain LOC user-visible (5597) |
| 3 | H.3 muninn-ui | 30min | 1h45 | Second plus gros gain LOC (11 712 !) |
| 4 | H.2 --include-dreams | 15min | 2h00 | Quick win 561 LOC |
| 5 | H.4 forge CLI | 30min | 2h30 | 344 LOC |
| 6 | H.5 mixins CLI | 45min | 3h15 | 1917 LOC |
| 7 | H.6 reste (wiring-checks par feature) | 45min | 4h00 | Cimente le tout |
| 8 | H.7 décision sync_tls + watchdog | 15min | 4h15 | Cleanup |
| 9 | H.8 docs | 15min | 4h30 | Wrap-up |

**Total** : **~4h30 pour brancher 20 000+ LOC dormantes en prod avec wiring-check tests qui empêchent toute régression future.**

---

## Sortie de Phase H

Si tous les chunks verts + CI 3/3 green :
- Bump version 1.0.3 → **1.1.0** (minor bump car ajout features publiques majeures)
- Build wheel + upload TestPyPI 1.1.0
- Run TEST_PROTOCOL_PHASE_D adapté
- Décision Sky prod 1.1.0

**Le résultat** : muninn-memory ne ship plus de code mort. Tout ce qui est dans le wheel est ACCESSIBLE à l'user via une commande CLI documentée. Et un test automatique empêche tout futur ajout dormant.

---

## Décision à prendre AVANT de commencer

Sky doit valider :

1. **OK pour Phase H complète 4h30** ou réduire à H.1+H.3+H.6 (les 3 plus critiques, 2h) ?
2. **Console script UI nom** : `muninn-ui` ou `muninn-mem ui` (subcommand) ?
3. **Forge command** : `muninn-mem forge` (risque confusion avec forge-shield PyPI) ou `muninn-mem metrics` ?
4. **sync_tls + watchdog** : drop, opt-in, ou experimental folder ?

À discuter demain matin tête fraîche.
