# PROMPT MASTER — EXEC TOTAL (Phase G + H + zéro-dormant)

> **Tu es** : Claude Opus 4.7 sur la machine de Sky. HEAD `385b922`, 8 commits ahead origin/main.
>
> **Sky veut** : UN SEUL fichier exécutable qui fait TOUT — fix les bugs Phase G + wire les features dormantes Phase H + élimine le code dormant restant (L12, vault semantics, tests UI en CI, fonctions zombies, etc.) → 1 SEUL gros commit final + 1 push GitHub.
>
> **Pas de question. Tu suis. Tu exécutes.**

---

## 🚫 RÈGLES NON NÉGOCIABLES

1. **Anti-drift** : ordre obligatoire `G.* → H.* → I.*`. Si tu vois autre chose, NOTE dans `/tmp/findings.md` mais NE FIX PAS hors séquence.
2. **Anti-bullshit RULE 4** : chaque "ça marche" = output verbatim 3 lignes au-dessus. Pas de "ça devrait".
3. **PAS de commit/push intermédiaire** entre chunks (CI mycelium = 41min × 26 chunks = stupide). `git add` après chaque chunk green, UN seul commit + push à la fin.
4. **Forge RULE 5** après chaque touche `engine/core/*.py` ou `muninn/*.py` : `forge --gen-props <fichier>` + verify props pass.
5. **Si chunk fail** (rouge irréparable en 30min) : STOP, `git stash`, écris `/tmp/blocker.md`, demande Sky.
6. **Décisions par défaut si Sky absent** (listées dans chaque chunk).

---

## 📋 WORKFLOW PAR CHUNK (10 étapes obligatoires)

```
1. READ      Lire le code existant (Read tool, pas cat)
2. TEST PIN  Écrire le test AVANT le code
3. RED       pytest → ROUGE attendu
4. FIX       Implémenter minimal
5. GREEN     pytest → VERT (output verbatim)
6. WIRE      CLI / hook / settings
7. END-TO-END Commande user réelle, capture output
8. CLEAN     pytest tests/ -m "not slow" → 0 fail nouveau
9. FORGE     Si engine/core/ touché
10. STAGE    git add ; PAS de commit
```

---

## 🩺 GATE INITIAL (5 min avant kick-off)

```bash
cd /home/sky/Bureau/MUNINN-
git status -sb
# Attendu : ## main...origin/main [devant 8], aucun M non-staged

forge --version
# Attendu : 2.1.2

python3 -m pytest tests/ -q --tb=no -m "not slow" \
  --ignore-glob='tests/test_ui_*.py' \
  --ignore=tests/eval_harness_chunk9.py --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies \
  2>&1 | tail -3
# Attendu : 2546 passed, 42 skipped, 0 failed (BASELINE)

forge --modularity 2>&1 | head -3
# Attendu : Q = 0.671 (ou meilleur)
```

Si une vérif échoue → STOP.

---

# 🟦 PHASE G — Bug fixes (~3h, 10 chunks)

## G.1 — Universal degree-based stopword filter (30 min)

**Problème** : `recall_meta("compression")` retourne `pas/est/les` (stopwords FR). `mycelium.py:1252` `_STOPWORDS` set incomplet. Sky a découvert que `DEGREE_FILTER_PERCENTILE = 0.05` ligne 80 existe déjà mais n'est utilisé QUE pour bloquer fusions (S3 tier), PAS au query-time.

**READ** : `engine/core/mycelium.py:80` + `:1252` + `muninn/mcp/server.py:_recall_local_impl/_recall_meta_impl/_recall_dual_impl`.

**TEST PIN** `tests/test_g1_universal_stopword_filter.py` :
```python
def test_g1_recall_filters_top_degree_concepts():
    # seed mycelium with 1 dominant concept "xxx" co-occurring with everything
    # query → assert "xxx" NOT in top-k results
def test_g1_recall_meta_no_french_stopwords():
    # real meta query "compression" → assert "pas", "est", "les" absent
def test_g1_env_var_percentile_tunable():
    # MUNINN_RECALL_STOPWORD_PERCENTILE=0 → no filter
    # =0.10 → plus strict
```

**FIX** : Dans `_recall_local_impl` et `_recall_meta_impl` (et `_recall_dual_impl`), avant return, filter `results = [r for r in results if r['concept'] not in top_degree_set]` où `top_degree_set` = top 5% degree du graphe (réutiliser logique existante mycelium.py).

**WIRE** : add env var `MUNINN_RECALL_STOPWORD_PERCENTILE` (default 0.05). Document dans CLAUDE.md.

**FORGE** : `forge --gen-props engine/core/mycelium.py`.

**STAGE** : `git add tests/test_g1_*.py muninn/mcp/server.py engine/core/mycelium.py CLAUDE.md`.

---

## G.2 — Doc drift résiduel `muninn init` → `muninn-mem init` (15 min)

**Problème** : Sed E.3 a raté les commentaires Python.

**READ** : grep `\bmuninn (init|status|doctor|boot)` dans `muninn/_engine.py`, `engine/core/muninn.py`, `examples/*.py`, `BUG_HOOKS_UNIVERSELS.md` (archivé).

**FIX** : sed précis sur ces 3 fichiers. Add header "RESOLVED en E.3" en haut de `docs/archive/BUG_HOOKS_UNIVERSELS.md`.

**TEST PIN** `tests/test_g2_no_old_cli_in_comments.py` : grep dans engine/core/, muninn/, examples/ doit retourner 0 match.

**STAGE** : 4 fichiers.

---

## G.3 — Error handling friendly (20 min)

**Problème** : `muninn-mem feed /nonexistent.jsonl` → raw Python traceback.

**READ** : `engine/core/muninn.py:main()` flow.

**TEST PIN** `tests/test_g3_friendly_errors.py` :
```python
def test_g3_feed_nonexistent_friendly():
    # subprocess + assert "not found" in stderr + NO "Traceback"
    # exit code 1 (pas 0, mais user-friendly)
def test_g3_compress_invalid_path():
def test_g3_bootstrap_nonexistent_repo():
def test_g3_munnin_debug_env_shows_traceback():
    # MUNINN_DEBUG=1 → traceback visible (escape hatch)
```

**FIX** : Wrapper try/except dans `main()` qui catche `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `KeyError`, friendly message + exit(1). Si `os.environ.get("MUNINN_DEBUG")` → raise normal.

**STAGE** : muninn.py + _engine.py + tests/.

---

## G.4 — F.1 tests @pytest.mark.slow (5 min)

**FIX** : ajouter `pytestmark = pytest.mark.slow` au top de `tests/test_chunk_mcp_f1_uninstall.py`.

**TEST PIN** : `test_g4_f1_marked_slow.py` parse le fichier + assert marker.

**STAGE** : 2 fichiers.

---

## G.5 — `~/.pypirc` security note (10 min)

**FIX** :
1. Add `~/.pypirc` à `~/.gitignore_global` de Sky (créer si absent)
2. `git config --global core.excludesfile ~/.gitignore_global` (idempotent)
3. Add note dans README.md section "Security" : "Never commit ~/.pypirc, chmod 600 + global gitignore"

**TEST PIN** : pas applicable (config global, hors repo).

**STAGE** : README.md.

---

## G.6 — Doctor pre-init clarity (30 min)

**Problème** : `muninn-mem doctor` dans repo sans `.muninn/` affiche 22+ checks mixant global + local manquant.

**READ** : `engine/core/muninn_tree_doctor.py:doctor()`.

**TEST PIN** `tests/test_g6_doctor_pre_init.py` :
```python
def test_g6_doctor_pre_init_simplified(tmp_path):
    # subprocess muninn-mem doctor dans tmp_path vierge
    # assert "Run `muninn-mem init` first" in stdout
    # assert moins de 12 checks dans output (vs 25 post-init)
```

**FIX** : Au début de `doctor()`, check `if not (repo / ".muninn").exists():` → simplified output (only deps + Python + SQLite + global meta DB).

**FORGE** : `forge --gen-props engine/core/muninn_tree_doctor.py`.

**STAGE** : muninn_tree_doctor.py + tests/.

---

## G.7 — (vide, fusionné dans H.7)

## G.8 — Python 3.10-3.12 compat test (15 min)

**DÉCISION DEFAULT** : downgrade claim à `>=3.13` (honest) puisque pyenv 3.10-3.12 pas testés.

**FIX** : pyproject.toml `requires-python = ">=3.10"` → `">=3.13"`. Update classifiers : retirer `Python :: 3.10`, `:: 3.11`, `:: 3.12`. Note dans CHANGELOG.

**TEST PIN** `tests/test_g8_python_version_honest.py` : assert `requires-python` ne ment pas (testé dans CI).

**STAGE** : pyproject.toml + tests/ + CHANGELOG.md.

---

## G.9 — Wheel size optimization (45 min) — **REPORTÉ Phase I**

**SKIP** dans Phase G/H. Document dans WINTER_TREE comme "Phase I optionnel".

---

## G.10 — Audit honest tests recount (10 min)

**FIX** : update CHANGELOG section Phase E avec count corrigé (16 REAL + 6 MEDIUM + 3 WEAK au lieu de 10/12/3 overclaim).

**STAGE** : CHANGELOG.md.

---

# 🟩 PHASE H — Wire features dormantes (~5h30, 11 chunks)

## H.0 — Garde-fou anti-orphan (30 min) — **LE PLUS IMPORTANT**

**OBJECTIF** : système immunitaire CI. ROUGE aujourd'hui (orphans détectés), VERT après H.1-H.7.

**TEST PIN** `tests/test_h0_no_orphan.py` :
```python
WHITELIST_DORMANT_MODULES = {"watchdog.py"}  # standalone scripts intended
WHITELIST_DORMANT_HOOKS = {"config_change_hook.py", "notification_audit_hook.py"}  # audit reserve

def test_h0_no_orphan_engine_module():
    # pour chaque engine/core/*.py NOT in whitelist
    # assert au moins 1 caller depuis code shipped (muninn/, engine/, .claude/hooks/)
    # NOT counting tests/

def test_h0_no_orphan_ui_module():
    # pour chaque muninn/ui/*.py NOT in whitelist
    # assert référencé par main_window.py OR autre ui/ module

def test_h0_all_env_vars_documented_read():
    # parse CLAUDE.md env vars table
    # pour chaque MUNINN_X, assert os.environ.get("MUNINN_X") OR os.getenv("MUNINN_X")
    # quelque part dans engine/ ou muninn/

def test_h0_all_argparse_flags_consumed():
    # parse muninn.py argparse, pour chaque add_argument
    # assert args.X utilisé post-parse

def test_h0_all_cli_commands_have_handler():
    # pour chaque choice dans argparse, assert "if args.command == 'X':" handler

def test_h0_all_hooks_on_disk_registered():
    # list .claude/hooks/*.py NOT in WHITELIST_DORMANT_HOOKS
    # assert chacun référencé dans .claude/settings.local.json
```

**RED EXPECTED maintenant**. Green après H.1-H.7. NE PAS @pytest.mark.skip — laisser rouge volontairement.

**STAGE** : `git add tests/test_h0_no_orphan.py`.

---

## H.1 — Wire `muninn-mem cube` CLI (45 min) — 5597 LOC

**READ** : `engine/core/cube_analysis.py:cli_scan/run/status/god` + `muninn.py:927` argparse.

**TEST PIN** `tests/test_h1_cube_cli.py` (6 tests) : in_choices, status_no_init, scan_creates_store, run_processes_cycles, god_returns_dict, handler_calls_cli_scan (monkeypatch).

**FIX** :
1. Add `"cube"` argparse choices (muninn.py + _engine.py mirror)
2. `--cube-action {scan,run,status,god}` (default status) + `--cycles N` (default 1) + `--level N`
3. Handler :
```python
if args.command == "cube":
    from cube_analysis import cli_scan, cli_run, cli_status, cli_god
    repo = Path(args.repo or args.file or ".").resolve()
    action = getattr(args, "cube_action", "status")
    if action == "scan": cli_scan(str(repo))
    elif action == "run": cli_run(str(repo), cycles=args.cycles, level=args.level)
    elif action == "status": cli_status()
    elif action == "god": cli_god()
    return
```

**END-TO-END** : `cd /tmp/h1_test && muninn-mem cube --cube-action scan` puis `--cube-action run --cycles 1`.

**FORGE** : muninn.py.

**STAGE** : 3 fichiers.

---

## H.2 — `muninn-ui` console script (30 min) — 11 712 LOC

**READ** : `muninn/ui/main_window.py` — verify `def main()` exists.

**TEST PIN** `tests/test_h2_ui_wiring.py` (4 tests) : console_script_in_pyproject, main_callable, pyqt_extra_declared, offscreen_launches.

**FIX** :
1. Ajouter `def main()` dans main_window.py si absent :
```python
def main():
    import sys, os
    if os.environ.get("MUNINN_GL_SOFTWARE"):
        os.environ["QT_OPENGL"] = "software"
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```
2. NEW `muninn/ui/__main__.py` : `from .main_window import main; main()`
3. pyproject.toml :
```toml
[project.scripts]
muninn-ui = "muninn.ui.main_window:main"

[project.optional-dependencies]
ui = ["PyQt6>=6.10"]
# update `all` to include `ui`
```

**END-TO-END** : `QT_QPA_PLATFORM=offscreen timeout 5 muninn-ui` doit pas crash.

**STAGE** : 4 fichiers.

---

## H.2b — Réactiver tests UI en CI (45 min) — **ZÉRO DORMANT**

**FIX** :
1. `.github/workflows/ci.yml` step pytest : retirer `--ignore-glob='tests/test_ui_*.py'`
2. Add `env: QT_QPA_PLATFORM: offscreen` au step
3. Add CI prep : `apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3`
4. Update `constraints.txt` : `pip install PyQt6==6.10.X` pinned

**TEST PIN** : `test_h2b_ui_tests_run_in_ci.py` assert ci.yml ne contient PAS `--ignore-glob='tests/test_ui_*.py'`.

**STAGE** : ci.yml + constraints.txt + tests/.

---

## H.3 — `--include-dreams` flag (15 min) — 561 LOC

**FIX** : argparse flag + plumbing `prune(include_dreams=args.include_dreams)`. Mirror.

**TEST PIN** (3 tests) : flag_in_help, flag_triggers_dream (monkeypatch), flag_off_skips.

**STAGE** : 3 fichiers.

---

## H.4 — `muninn-mem metrics` CLI (30 min) — 344 LOC

**DÉCISION DEFAULT** : nom = `metrics` (clash forge-shield évité).

**FIX** : argparse `"metrics"` + handler `forge_metrics.compute_metrics(repo)`. Réutilise flag `--output` (était mort).

**TEST PIN** (4 tests) : command_exists, returns_Q, output_json, in_choices.

**STAGE** : 3 fichiers.

---

## H.5 — Cleanup dead config (15 min)

**FIX** :
1. `MUNINN_GL_SOFTWARE` : wired dans muninn/ui/main_window.py:main() (H.2 déjà)
2. `--output` : réutilisé par H.4 metrics
3. 2 TODO stubs vides (`muninn.py:682` + `muninn/_engine.py:764`) : SUPPRIMER

**STAGE** : muninn.py + _engine.py.

---

## H.5b — Hygiene (10 min)

**FIX** :
1. `.forge/forge_log.txt` silence : run `forge --baseline` pour reset Kalman (ne pas commit l'output, juste reset state)
2. `memory/` legacy : add note explicite dans CLAUDE.md : "memory/ = legacy fallback if .muninn/tree/ missing, do not modify"
3. 16 tags `pre-*` : **KEEP** (safety nets)

**STAGE** : CLAUDE.md.

---

## H.6 — Wire 3 hooks défensifs Claude Code (30 min) — **DEFAULT : ACTIVER**

**DÉCISION DEFAULT** : activer pre_tool_use_bash_destructive, pre_tool_use_bash_secrets, pre_tool_use_edit_hardcode (protège RULE 1/2/3). Garder config_change_hook + notification_audit_hook + post_tool_use_edit_log DORMANTS (whitelist H.0).

**FIX** :
1. Edit `.claude/settings.local.json` : ajouter 3 hooks défensifs sous `hooks.PreToolUse`
2. Update `install_hooks()` dans `engine/core/muninn_install.py` pour register au prochain `muninn-mem init`
3. Mirror muninn/muninn_install.py.

**TEST PIN** `tests/test_h6_hooks_registered.py` : assert 3 défensifs dans settings.local.json.

**STAGE** : settings.local.json + muninn_install.py × 2 + tests/.

---

## H.6b — `vault.py` auto-lock semantics (30 min) — **ZÉRO DORMANT**

**Problème** : 551 LOC AES-256 wired CLI mais jamais invoqué (pas de "when to lock" naturel).

**DÉCISION DEFAULT** : Auto-lock `.muninn/mycelium.db` après SessionEnd hook si `MUNINN_VAULT_AUTO_LOCK=1` env var ET `MUNINN_VAULT_PASSWORD` set. Sky opt-in.

**FIX** :
1. Add env var `MUNINN_VAULT_AUTO_LOCK` doc dans CLAUDE.md
2. Dans `muninn_feed.py:feed_from_stop_hook()` : check env vars, si set → call `vault.lock(mycelium_db_path, password)`
3. Le hook reste exit 0 safe (lock fail = warning stderr, pas crash)

**TEST PIN** `tests/test_h6b_vault_auto_lock.py` : monkeypatch env vars, simulate Stop hook, assert vault.lock called.

**FORGE** : muninn_feed.py.

**STAGE** : muninn_feed.py × 2 + CLAUDE.md + tests/.

---

## H.6c — L12 BudgetMem default activation (30 min) — **ZÉRO DORMANT**

**Problème** : L12 chunk selection opt-in via `MUNINN_L12_BUDGET=N`. Sky n'a jamais set.

**DÉCISION DEFAULT** : Activer par défaut avec budget conservatif `MUNINN_L12_BUDGET=16000` (16K tokens) si non set. User peut override ou désactiver via `=0`.

**FIX** : Dans `engine/core/muninn_layers.py` start of L12 pass, `budget = int(os.environ.get("MUNINN_L12_BUDGET", "16000"))`. Si `budget == 0` → skip L12.

**TEST PIN** `tests/test_h6c_l12_default_active.py` :
- Sans env var, assert L12 runs avec budget=16000
- Avec `MUNINN_L12_BUDGET=0`, assert L12 skipped

**FORGE** : muninn_layers.py.

**STAGE** : muninn_layers.py + tests/ + CLAUDE.md (update env var default).

---

## H.7 — sync_tls + watchdog (15 min)

**DÉCISIONS DEFAULT** :
- `sync_tls.py` → `engine/core/experimental/sync_tls.py` (opt-in via `MUNINN_SYNC_TLS_HOST=host:port`)
- `watchdog.py` : keep + docstring "Windows Task Scheduler standalone, Linux: irrelevant"

**FIX** :
```bash
mkdir -p engine/core/experimental
git mv engine/core/sync_tls.py engine/core/experimental/sync_tls.py
# Update imports dans sync_backend.py si nécessaire
```

Add docstring header watchdog.py.

**STAGE** : git mv + sync_backend.py update + watchdog.py.

---

## H.8 — Garde-fou API bloat MyceliumDB (30 min)

**TEST PIN** `tests/test_h8_api_bloat_baseline.py` :
- Compte méthodes publiques (sans `_`) de `MyceliumDB`, `Mycelium`, `Cube`
- Assert que count <= baseline figé (e.g., 70 pour MyceliumDB)
- Si un PR ajoute une méthode publique → CI rouge, oblige justification ou refactor

**STAGE** : tests/.

---

## H.9 — Docs sync (15 min)

**FIX** :
- CHANGELOG : section "Phase G+H delivered"
- WINTER_TREE : snapshot final
- README : section "Quick reference 35 CLI commands"
- QUICKSTART : exemples `muninn-mem cube`, `muninn-ui`, `--include-dreams`, `muninn-mem metrics`

**STAGE** : 4 docs.

---

## H.10 — Bump 1.0.3 → 1.1.0 + build sanity (15 min)

**FIX** : 4 mirrors version sync.

```bash
rm -rf build dist *.egg-info
python3 -m build --no-isolation 2>&1 | tail -2
python3 -m twine check dist/* 2>&1 | tail -2
# Attendu : Successfully built + PASSED both
```

**STAGE** : pyproject + 3 modules version mirrors. Pas dist/ (gitignored).

---

# 🟪 PHASE I — Zéro dormant garantie (~2h30, 5 chunks)

## I.1 — Wiring-check tests par feature dormante (1h)

**TEST PIN** `tests/test_i1_wiring_check.py` (5 tests, un par feature) :
```python
def test_i1_wiring_vault_lock_called_by_stop_hook():
    # monkeypatch vault.lock + env vars + simulate Stop
    # assert vault.lock called

def test_i1_wiring_cube_called_by_cli_cube():
    # subprocess muninn-mem cube --cube-action scan
    # monkeypatch cube_analysis.cli_scan + assert called

def test_i1_wiring_dream_called_by_include_dreams_flag():
    # déjà couvert par H.3 mais en isolation pure
    # ici en CLI end-to-end

def test_i1_wiring_metrics_invoked_by_cli():
    # subprocess muninn-mem metrics + assert forge_metrics.compute_metrics called

def test_i1_wiring_l12_invoked_in_feed_pipeline():
    # simulate feed avec MUNINN_L12_BUDGET=8000
    # assert _l12_budget_pass called
```

**STAGE** : tests/.

---

## I.2 — Garde-fou anti-fonction-zombie (1h)

**TEST PIN** `tests/test_i2_no_zombie_function.py` :
- Parse AST de `engine/core/*.py` + `muninn/*.py`
- Pour chaque `def public_fn():` (no underscore), grep si appelée AILLEURS dans le code shipped
- Whitelist : `main`, `__init__`, helpers used only via decorator (e.g., `@app.tool()`)
- Si fonction publique 0 caller → fail avec liste

Initial run : RED expected (audit a trouvé 89 zombies). FIX : soit supprimer la fonction, soit ajouter au whitelist intentionnel, soit la wire.

**FIX simplification** : Pour le premier run, juste générer la liste dans `/tmp/zombies.txt`, marquer test `@pytest.mark.xfail(strict=False)` avec count. Phase J = refactor systematic.

**STAGE** : tests/.

---

## I.3 — `.muninn/edits_log.jsonl` reader OR drop (30 min)

**DÉCISION DEFAULT** : DROP le hook PostToolUse edit log (utility douteuse, écrit mais aucun lecteur). Ajouter à WHITELIST_DORMANT_HOOKS H.0.

**FIX** : 
1. `.claude/hooks/post_tool_use_edit_log.py` : ajouter docstring "[DORMANT INTENTIONAL] No reader implemented yet. See docs/PROMPT_EXEC_PHASE_H.md I.3"
2. Update H.0 WHITELIST_DORMANT_HOOKS

**STAGE** : test_h0_no_orphan.py + post_tool_use_edit_log.py.

---

## I.4 — `.muninn/session_index.json` investigation (30 min)

**FIX** : grep le code pour trouver écrivain ET lecteur de `session_index.json`. Si zéro lecteur → ajouter docstring "[DORMANT INTENTIONAL]" dans le module qui écrit. Sinon, doc dans CLAUDE.md le rôle.

**STAGE** : selon résultat investigation.

---

## I.5 — Final verify H.0 garde-fou GREEN (30 min)

```bash
python3 -m pytest tests/test_h0_no_orphan.py -v
# Attendu : 6/6 PASS (toutes les orphans wirées par H.1-H.7 ; whitelist couvre les intentionnels)
```

Si toujours rouge sur un test précis → identifier quel chunk a raté le wire, retour à ce chunk.

**STAGE** : (rien si test pin H.0 déjà staged).

---

# 📦 H.FINAL — Sanity full

```bash
# 1. Full pytest
python3 -m pytest tests/ -q --tb=line -m "not slow" \
  --ignore=tests/eval_harness_chunk9.py --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies \
  2>&1 | tail -5
# Attendu : ≥ 2546 + ~40 nouveaux tests = 2586+ PASS, 0 fail

# 2. Forge
forge --gen-props engine/core/muninn.py 2>&1 | tail -3
forge --modularity 2>&1 | head -3
# Attendu : Q ≥ 0.67

# 3. Build sanity
rm -rf build dist *.egg-info
python3 -m build --no-isolation 2>&1 | tail -2
python3 -m twine check dist/* 2>&1 | tail -2
# Attendu : Successfully built 1.1.0 + PASSED both

# 4. UI launches offscreen
QT_QPA_PLATFORM=offscreen timeout 5 muninn-ui 2>&1 | head -3 || echo "OK (killed timeout = window started)"
```

---

# 🎯 LE GROS COMMIT FINAL (UN SEUL)

```bash
cd /home/sky/Bureau/MUNINN-
git status -sb
# Verify : tous fichiers staged (M ou A), zéro modified non-staged

git commit -m "$(cat <<'EOF'
feat(phase-G+H+I): bugfixes + wire 17.8K LOC dormantes + zéro-dormant garantie + bump 1.1.0

EXÉCUTION TOTALE per docs/PROMPT_EXEC_PHASE_H.md (Sky's master prompt) :
- Phase G : 10 chunks bugfixes
- Phase H : 11 chunks wire features dormantes + garde-fou anti-orphan
- Phase I : 5 chunks zéro-dormant garantie

PHASE G — Bug fixes
  G.1 Universal degree-based stopword filter (recall_local/meta/dual)
  G.2 Doc drift résiduel `muninn init` → `muninn-mem init` (3 fichiers)
  G.3 Error handling friendly (FileNotFoundError etc. → exit(1) clean)
  G.4 F.1 tests @pytest.mark.slow marker
  G.5 ~/.pypirc security note (gitignore global + README)
  G.6 Doctor pre-init simplified output
  G.8 Python compat claim downgrade à >=3.13 (honest)
  G.10 Audit honest tests recount (16 REAL + 6 MEDIUM + 3 WEAK)

PHASE H — Wire dormant features
  H.0 GARDE-FOU ANTI-ORPHAN (système immunitaire CI, 6 tests)
  H.1 muninn-mem cube CLI (5597 LOC)
  H.2 muninn-ui console script (11 712 LOC)
  H.2b Tests UI réactivés en CI (offscreen)
  H.3 --include-dreams flag (561 LOC)
  H.4 muninn-mem metrics CLI (344 LOC)
  H.5 Cleanup dead config (MUNINN_GL_SOFTWARE wired, --output réutilisé,
       2 TODO stubs supprimés)
  H.5b Hygiene (.forge baseline reset, memory/ doc, tags pre-* kept)
  H.6 Wire 3 hooks Claude Code défensifs (bash_destructive, bash_secrets,
       edit_hardcode)
  H.6b vault auto-lock après SessionEnd (opt-in MUNINN_VAULT_AUTO_LOCK)
  H.6c L12 BudgetMem default activation (MUNINN_L12_BUDGET=16000 default)
  H.7 sync_tls.py → engine/core/experimental/ + watchdog docstring
  H.8 Garde-fou API bloat baseline (MyceliumDB freeze)
  H.9 Docs sync (CHANGELOG + WINTER_TREE + README + QUICKSTART)
  H.10 Bump 1.0.3 → 1.1.0 (4 mirrors)

PHASE I — Zéro dormant garantie
  I.1 Wiring-check tests par feature (vault, cube, dream, metrics, L12)
  I.2 Garde-fou anti-fonction-zombie (xfail initial avec count, Phase J)
  I.3 `.muninn/edits_log.jsonl` → drop hook PostToolUse edit log
  I.4 `.muninn/session_index.json` investigation + doc rôle
  I.5 Final H.0 garde-fou GREEN verify

VÉRIFICATIONS (RULE 4) :
- H.0 garde-fou : 6/6 PASS (ROUGE→VERT prouve wires)
- Full pytest : 2586+ PASS, 0 fail
- Forge --modularity Q ≥ 0.67
- Build wheel 1.1.0 + twine check : PASSED
- muninn-ui launch offscreen : OK
- 0 code shipped sans caller (verified par H.0 + I.2)

LOC débloquées en prod : ~17 800 (Cube + UI + dream + metrics + hooks
défensifs + vault auto-lock + L12 default).

GARANTIE : à partir de ce commit, tout futur module orphan = CI rouge
automatique. Plus jamais une feature codée mais pas en prod.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"

git push 2>&1 | tail -3
```

---

# 📝 POST-PUSH — Items cas par cas (PAS DANS CE PROMPT)

Après le push trigger une CI run ~44min. Pendant ce temps :

1. **CI step "Test Mycelium" 41min** — Sky a dit "oublie le machin CI qui contrôle le mycelium pour l'instant". Si rouge sur autre chose que mycelium → fix séparé. Si rouge sur mycelium → ignorer (Sky fix au cas par cas plus tard).

2. **TestPyPI 1.1.0 upload** — Sky décide. Token déjà dans `~/.pypirc`.

3. **PyPI prod 1.1.0** — décision Sky après TestPyPI.

4. **Phase J refactor MyceliumDB API bloat (81% méthodes mortes)** — 3-4h, plus tard.

5. **Phase J réviser fonctions zombies** (89 listées par audit) — supprimer ou ajouter au whitelist intentionnel.

---

# ✅ CONTRAT DE FIN

Tu as exécuté correctement SI ET SEULEMENT SI :

- [ ] 26 chunks G.* + H.* + I.* tous verts (output verbatim)
- [ ] 1 SEUL commit final (pas d'intermédiaires)
- [ ] 1 push GitHub réussi
- [ ] H.0 garde-fou 6/6 PASS post-wiring (prouve tout branché)
- [ ] I.2 garde-fou anti-fonction-zombie en place (xfail initial OK)
- [ ] Full pytest 2586+ PASS / 0 fail
- [ ] muninn-mem cube, muninn-ui, --include-dreams, muninn-mem metrics tous accessibles
- [ ] muninn-ui launch offscreen sans crash
- [ ] Build wheel 1.1.0 sanity OK + twine check PASSED
- [ ] 0 features fantôme : vault auto-lock wired, L12 default actif, sync_tls dans experimental, watchdog doc

**Si l'un fail → STOP, stash, écris blocker, demande Sky.**

---

## 🧭 STRUCTURE D'ORIENTATION (pour ne pas te perdre)

```
PHASE G ━━━━━━━━━━━━━━ bugs visibles user (3h)
  G.1-G.10 : qualité output, error handling, doc drift, version honest

PHASE H ━━━━━━━━━━━━━━ wire features dormantes (5h30)
  H.0     : garde-fou anti-orphan (système immunitaire)
  H.1-H.4 : wire 4 CLI commands (cube, ui, --dreams, metrics)
  H.5-H.7 : cleanup config + hooks + sync_tls
  H.6b-c  : vault auto-lock + L12 default (zéro dormant features)
  H.8     : garde-fou API bloat MyceliumDB
  H.9-H.10: docs + bump 1.1.0

PHASE I ━━━━━━━━━━━━━━ zéro dormant garantie (2h30)
  I.1     : wiring-check tests par feature
  I.2     : garde-fou anti-fonction-zombie
  I.3-I.4 : hooks dormants intentionnels documentés
  I.5     : verify H.0 garde-fou GREEN

H.FINAL ━━━━━━━━━━━━━━ sanity full

COMMIT 1× ━━━━━━━━━━━━ message verbose changelog

PUSH 1× ━━━━━━━━━━━━━━ trigger CI 44min (ignore mycelium step)

POST-PUSH ━━━━━━━━━━━ cas par cas (Sky décide TestPyPI/prod/refactor)
```

**Total effort** : ~11h (peut split sur 2 jours si Sky veut).
**Total LOC débloquées en prod** : ~17 800.
**Garantie post-exécution** : 0 feature codée mais pas en prod, garde-fou CI permanent.
