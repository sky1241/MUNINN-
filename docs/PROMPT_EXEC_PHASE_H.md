# PROMPT MASTER — Phase H Light Up Everything (Sky's exec prompt)

> **Tu es** : Claude Opus 4.7 sur la machine de Sky. Tu hérites du repo MUNINN- à HEAD `956c750` (commit local, 7 commits ahead origin/main).
>
> **Sky est fatigué** des deep audits. Il veut **un cousin Claude qui exécute Phase H d'A à Z sans poser de questions**, avec verif à chaque étape.
>
> **Objectif unique** : wire ~17 800 LOC dormantes (Cube + UI + dream + forge_metrics + hooks orphans) + installer un garde-fou anti-orphan permanent, **avec 1 SEUL commit + 1 push à la fin**.
>
> **Source de vérité** : ce fichier. Les autres battle plans (PHASE_G, PHASE_H, FINAL) sont des références mais CE prompt est l'ordre d'exécution.

---

## 🚫 RÈGLES NON NÉGOCIABLES (lis 2 fois avant de commencer)

1. **Anti-drift** : exécute les chunks dans l'ordre `H.0 → H.1 → H.2 → ... → H.10`. JAMAIS de scope creep. Si tu vois un autre bug pendant un chunk, NOTE-LE dans `/tmp/phase_h_findings.md` mais NE LE FIX PAS.

2. **Anti-bullshit RULE 4** : chaque "ça marche" doit avoir l'output de commande visible 3 lignes au-dessus dans la conversation. Pas "ça devrait marcher", pas "le test passe" sans `pytest ... PASSED` literal.

3. **Pas de CI mycelium polluante** : ne PUSH PAS entre chunks. Le step "Test Mycelium" du CI prend 41min — multiplié par 11 chunks = 7h de CI inutile. **Stage les fichiers (`git add`) après chaque chunk green, commit + push UNIQUEMENT à la fin**.

4. **1 SEUL commit final** avec tous les fichiers modifiés. Message commit = changelog complet de Phase H (template plus bas).

5. **Si un chunk FAIL** (test rouge irréparable en 30min) : STOP. Stash tes changements (`git stash push -m "phase-h-partial"`), écris l'état dans `/tmp/phase_h_blocker.md`, demande à Sky.

6. **Forge RULE 5** : après chaque touch de `engine/core/*.py` ou `muninn/*.py`, run `forge --gen-props <fichier>` + `pytest tests/test_props_<fichier>.py -q`. Si fail → fix avant chunk suivant.

7. **Pas de console output via emoji** sauf demande explicite (Sky's preference).

---

## 📋 WORKFLOW PAR CHUNK (10 étapes strictes, suivre dans l'ordre)

Pour CHAQUE chunk H.X :

```
1. READ      : Lire le code existant qui va changer (Read tool, pas Bash cat)
2. TEST PIN  : Écrire le test AVANT le code (Pin TDD). Save fichier.
3. RED       : pytest -k test_h<X>_<name> → doit être ROUGE (proves test mord)
4. FIX       : Implémenter le code minimal pour passer le test
5. GREEN     : pytest -k test_h<X>_<name> → doit être VERT (output verbatim)
6. WIRE      : Brancher dans CLI / hook / settings selon le chunk
7. END-TO-END: Lancer la commande user réelle (muninn-mem <cmd>), capture output
8. CLEAN     : pytest tests/ -k "not slow" --ignore-glob='tests/test_ui_*.py'
              → assert 0 fail nouveau (par rapport à baseline H.0)
9. FORGE     : Si engine/core/ ou muninn/ touchés → forge --gen-props
10. STAGE    : git add <fichiers modifiés du chunk>. NE PAS COMMIT.
```

Après les 10 étapes : **passer au chunk suivant**. PAS de commit intermédiaire.

---

## 🩺 ÉTAT INITIAL — checklist 5 min avant kick-off

Exécute ces commandes et vérifie les résultats :

```bash
# 1. État git correct
cd /home/sky/Bureau/MUNINN-
git status -sb
# Attendu : ## main...origin/main [devant 7] + zéro fichier modified non-staged

# 2. Forge 2.1.2 installé
forge --version
# Attendu : 2.1.2 (ou >=2.1.0)

# 3. pytest baseline marche
python3 -m pytest tests/ -q --tb=no \
  -m "not slow" \
  --ignore-glob='tests/test_ui_*.py' \
  --ignore=tests/eval_harness_chunk9.py \
  --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies \
  2>&1 | tail -3
# Attendu : 2546 passed, 42 skipped, 0 failed (baseline pré-Phase H)
# Note ce chiffre = BASELINE. À chaque chunk après FIX, le total doit augmenter
# (jamais diminuer).

# 4. Forge marche localement
forge --modularity 2>&1 | head -3
# Attendu : Q = 0.671 (good — modules well isolated)
```

**Si une de ces 4 vérifs échoue → STOP, ne lance pas Phase H.**

---

## 🏗️ LES 11 CHUNKS (ordre obligatoire)

### Chunk H.0 — Garde-fou anti-orphan (30 min) — **LE PLUS IMPORTANT**

> **Pourquoi en premier** : si on installe le garde-fou AVANT de wire les features, le test est ROUGE aujourd'hui. Après les chunks H.1-H.9, il devient VERT. Et pour TOUJOURS, tout nouveau module orphan = CI rouge.

**Sous-section 0.1 — READ** :
- Lire `engine/core/muninn_install.py` lignes 880-980 (install_hooks) pour comprendre quelles hooks sont registered
- Lire `.claude/settings.local.json` pour voir hooks actuels (7 wired)
- Lire `engine/core/muninn.py` ligne 920-940 (argparse choices) — liste des 30 commands
- Lire CLAUDE.md table env vars (lignes 189-211) — 21 vars documentées

**Sous-section 0.2 — TEST PIN** :
Créer `tests/test_h0_no_orphan.py` avec 6 tests :
- `test_h0_no_orphan_engine_module` : pour chaque `engine/core/*.py`, assert au moins 1 caller depuis code shipped (pas tests/). Whitelist : `__init__.py`, `watchdog.py`.
- `test_h0_no_orphan_ui_module` : pour chaque `muninn/ui/*.py`, assert référencé par main_window.py OR autre module ui/.
- `test_h0_all_env_vars_documented_read` : pour chaque `MUNINN_*` dans CLAUDE.md, assert au moins 1 `os.environ.get` ou `os.getenv` dans engine/ ou muninn/.
- `test_h0_all_argparse_flags_consumed` : pour chaque `parser.add_argument`, assert `args.X` est utilisé quelque part dans main().
- `test_h0_all_cli_commands_have_handler` : pour chaque choice dans argparse, assert `if args.command == "X":` handler existe.
- `test_h0_all_hooks_on_disk_registered` : list `.claude/hooks/*.py`, assert chacun référencé dans settings.local.json OU dans whitelist documentée `_INTENTIONALLY_DORMANT_HOOKS = {...}`.

**Sous-section 0.3 — RED** :
```bash
python3 -m pytest tests/test_h0_no_orphan.py -v
# Attendu : 4-6 tests FAIL (système immunitaire détecte orphans actuels)
# Note les noms des fails exacts dans /tmp/phase_h_h0_red.txt
```

**Sous-section 0.4 — FIX** :
**NE PAS FIX H.0 maintenant.** Les fails sont SYMPTÔMES des chunks H.1-H.9 qui vont les résoudre. Le garde-fou EST le test — il restera rouge tant que les autres chunks n'auront pas wired les orphans.

**Sous-section 0.5 — GREEN différé** :
Le green vient à la fin, après H.9. **Mark H.0 comme "RED-EXPECTED-for-now" dans pytest output**, NE PAS le marquer @pytest.mark.skip.

**Sous-section 0.6 — STAGE** :
```bash
git add tests/test_h0_no_orphan.py
```

---

### Chunk H.1 — Wire `muninn-mem cube` CLI (45 min) — **5597 LOC débloquées**

**Sous-section 1.1 — READ** :
- `engine/core/cube_analysis.py:cli_scan()`, `cli_run()`, `cli_status()`, `cli_god()` — signatures
- `engine/core/muninn.py:920-940` — argparse choices list
- `engine/core/muninn.py` cherche `if args.command == "init":` pour pattern de handler

**Sous-section 1.2 — TEST PIN** :
Créer `tests/test_h1_cube_cli.py` :
```python
def test_h1_cube_in_argparse_choices():
    # parse muninn.py, assert "cube" in choices

def test_h1_cube_status_no_init(tmp_path):
    # subprocess.run muninn cube --cube-action status sur tmp_path
    # assert exit 0 + message friendly "no store yet"

def test_h1_cube_scan_creates_store(tmp_path):
    # subprocess.run muninn cube --cube-action scan
    # assert .forge/cube/ ou store created

def test_h1_cube_god_returns_dict():
    # call cube_analysis.cli_god() directly, assert dict

def test_h1_cube_handler_calls_cli_scan(monkeypatch):
    # monkeypatch cube_analysis.cli_scan, run main with args.command="cube"
    # assert called once
```

**Sous-section 1.3 — RED** :
```bash
python3 -m pytest tests/test_h1_cube_cli.py -v
# Attendu : 5/5 FAIL
```

**Sous-section 1.4 — FIX** :
1. Add `"cube"` dans argparse choices de `engine/core/muninn.py:927`
2. Add flags : `parser.add_argument("--cube-action", choices=["scan", "run", "status", "god"], default="status")` + `--cycles N` (default 1) + `--level N` (default 0)
3. Handler dans muninn.py après le handler `init` :
```python
if args.command == "cube":
    from cube_analysis import cli_scan, cli_run, cli_status, cli_god
    repo = Path(args.repo or args.file or ".").resolve()
    action = getattr(args, "cube_action", "status")
    cycles = getattr(args, "cycles", 1)
    level = getattr(args, "level", 0)
    if action == "scan": cli_scan(str(repo))
    elif action == "run": cli_run(str(repo), cycles=cycles, level=level)
    elif action == "status": cli_status()
    elif action == "god": cli_god()
    return
```
4. **Mirror dans muninn/_engine.py** (BUG-091).

**Sous-section 1.5 — GREEN** :
```bash
python3 -m pytest tests/test_h1_cube_cli.py -v
# Attendu : 5/5 PASS
```

**Sous-section 1.6 — WIRE** : déjà fait dans 1.4 (handler ajouté).

**Sous-section 1.7 — END-TO-END** :
```bash
cd /tmp && mkdir -p h1_test && cd h1_test
python3 /home/sky/Bureau/MUNINN-/engine/core/muninn.py cube --cube-action status
# Attendu : message status (no store yet OU stats)
python3 /home/sky/Bureau/MUNINN-/engine/core/muninn.py cube --cube-action scan
# Attendu : scan OK
```

**Sous-section 1.8 — CLEAN + FORGE + STAGE** :
```bash
cd /home/sky/Bureau/MUNINN-
forge --gen-props engine/core/muninn.py 2>&1 | tail -3
python3 -m pytest tests/test_props_muninn.py -q 2>&1 | tail -3
python3 -m pytest tests/ -q --tb=no -m "not slow" 2>&1 | tail -3
# Attendu : 2546+5 passed (au moins, +5 nouveaux tests H.1)

git add tests/test_h1_cube_cli.py engine/core/muninn.py muninn/_engine.py
```

---

### Chunk H.2 — `muninn-ui` console script (30 min) — **11 712 LOC débloquées**

**Sous-section 2.1 — READ** :
- `muninn/ui/main_window.py` — chercher si `def main()` existe et `QApplication` setup
- `pyproject.toml:[project.scripts]` — voir entry points actuels

**Sous-section 2.2 — TEST PIN** :
`tests/test_h2_ui_wiring.py` :
```python
def test_h2_ui_console_script_in_pyproject():
    # parse pyproject.toml, assert "muninn-ui" in [project.scripts]

def test_h2_ui_main_callable():
    # importlib resolve "muninn.ui.main_window:main"
    # assert callable

def test_h2_ui_pyqt_extra_declared():
    # assert "ui" in [project.optional-dependencies]

def test_h2_ui_offscreen_launches():
    # subprocess.run "QT_QPA_PLATFORM=offscreen muninn-ui" timeout 3s, kill
    # assert no ImportError, no AttributeError dans stderr
```

**Sous-section 2.3 — RED** : 4/4 FAIL attendu.

**Sous-section 2.4 — FIX** :
1. Vérifier `muninn/ui/main_window.py` a un `def main()` ; sinon ajouter :
```python
def main():
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```
2. Create `muninn/ui/__main__.py` :
```python
from .main_window import main
main()
```
3. Add à `pyproject.toml` `[project.scripts]` :
```toml
muninn-ui = "muninn.ui.main_window:main"
```
4. Add `[project.optional-dependencies]` :
```toml
ui = ["PyQt6>=6.10"]
```
+ update `all` extra pour inclure `ui`.

5. Update muninn/__init__.py + engine/core/muninn.py fallback versions to 1.0.4 (because Phase H = minor bump, see H.10).

**Sous-section 2.5 — GREEN** : 4/4 PASS.

**Sous-section 2.6 — WIRE** : déjà fait (entry point pyproject).

**Sous-section 2.7 — END-TO-END** :
```bash
cd /home/sky/Bureau/MUNINN- && rm -rf build dist *.egg-info
python3 -m pip install --quiet -e ".[ui]" 2>&1 | tail -1
QT_QPA_PLATFORM=offscreen timeout 5 muninn-ui 2>&1 | head -3 || echo "OK (killed by timeout = window started)"
```

**Sous-section 2.8 — STAGE** :
```bash
git add tests/test_h2_ui_wiring.py muninn/ui/main_window.py muninn/ui/__main__.py pyproject.toml
```

---

### Chunk H.3 — `--include-dreams` flag (15 min) — **561 LOC débloquées**

**Sous-section 3.1 — READ** :
- `engine/core/muninn.py:927-945` argparse section
- `engine/core/muninn_tree_prune.py` — chercher `prune(include_dreams=...)`

**Sous-section 3.2 — TEST PIN** :
`tests/test_h3_dream_flag.py` :
```python
def test_h3_flag_in_help():
    # subprocess "muninn-mem prune --help" + assert "--include-dreams" in output

def test_h3_flag_triggers_dream(monkeypatch):
    # monkeypatch Mycelium.dream, run main(["prune", "--force", "--include-dreams"])
    # assert dream() called once

def test_h3_flag_off_skips_dream(monkeypatch):
    # sans flag, assert dream() NOT called
```

**Sous-section 3.3 — RED** : 3/3 FAIL attendu.

**Sous-section 3.4 — FIX** :
1. Add `parser.add_argument("--include-dreams", action="store_true", help="Run sleep consolidation dream() during prune")`
2. Handler `prune` : `prune(repo, force=args.force, include_dreams=args.include_dreams)`
3. Mirror muninn/_engine.py.

**Sous-section 3.5 — GREEN** : 3/3 PASS.

**Sous-section 3.6-3.8 — WIRE/END-TO-END/STAGE** :
```bash
cd /tmp/h1_test
python3 /home/sky/Bureau/MUNINN-/engine/core/muninn.py prune --force --include-dreams 2>&1 | head -5
# Attendu : output prune + mention dream() exécuté

git add tests/test_h3_dream_flag.py engine/core/muninn.py muninn/_engine.py
```

---

### Chunk H.4 — `muninn-mem metrics` CLI (30 min) — **344 LOC débloquées**

> **Décision Sky avant kick-off** : nom = `forge` (risque confusion forge-shield PyPI 2.1.2) OU `metrics` (clair) ? **Default si Sky absent : `metrics`**.

**Sous-section 4.1 — READ** :
- `engine/core/forge_metrics.py:compute_metrics()` ou équivalent
- argparse choices

**Sous-section 4.2 — TEST PIN** :
`tests/test_h4_metrics_cli.py` (4 tests : exists, returns Q, output JSON, in choices).

**Sous-section 4.3-4.8** : Add `"metrics"` à choices, handler appelle `forge_metrics.compute_metrics(repo)`, support `--output X.json` (recycle le flag `--output` mort).

```bash
git add tests/test_h4_metrics_cli.py engine/core/muninn.py muninn/_engine.py
```

---

### Chunk H.5 — Cleanup dead config (15 min)

**Sous-section 5.1 — READ** :
- CLAUDE.md ligne `MUNINN_GL_SOFTWARE` documentée — pas wired
- `engine/core/muninn.py:942` `--output` flag défini mais jamais lu post-parse
- `engine/core/muninn.py:682` + `muninn/_engine.py:764` TODO stubs vides

**Sous-section 5.2 — DÉCISIONS** (default si Sky absent) :
- `MUNINN_GL_SOFTWARE` : **GARDER** (sera utilisé par muninn-ui de H.2 pour Qt workaround). Ajouter `os.environ.get("MUNINN_GL_SOFTWARE")` check dans `muninn/ui/main_window.py:main()` et set Qt env si truthy.
- `--output` flag : **RÉUTILISÉ** par H.4 metrics (output JSON).
- 2 TODO stubs : **SUPPRIMER** les 2 (no description, no value).

**Sous-section 5.3 — IMPL + STAGE** :
1. Add Qt software check dans `muninn/ui/main_window.py:main()` :
```python
import os
if os.environ.get("MUNINN_GL_SOFTWARE"):
    os.environ["QT_OPENGL"] = "software"
```
2. Supprimer les 2 `## TODO` blocks.
3. ```bash
git add muninn/ui/main_window.py engine/core/muninn.py muninn/_engine.py
```

---

### Chunk H.5b — Hygiene (10 min)

**Sous-section 5b.1 — Items à traiter** :
- `.forge/forge_log.txt` silence 5 jours → `forge --baseline` pour reset Kalman (ne pas commit l'output)
- `memory/` legacy folder : **GARDER** comme fallback (référencé dans muninn_tree.py:64,2234), mais **doc explicite** dans CLAUDE.md : "memory/ = legacy fallback if .muninn/tree/ missing, do not modify"
- 16 tags `pre-*` : **GARDER** (safety nets, low overhead)

**Sous-section 5b.2 — STAGE** :
```bash
git add CLAUDE.md
```

---

### Chunk H.6 — Wire 5 hooks Claude Code orphans (30 min)

> **Décision Sky avant kick-off** : activer les 3 hooks défensifs (`pre_tool_use_bash_destructive`, `pre_tool_use_bash_secrets`, `pre_tool_use_edit_hardcode`) qui protègent RULE 1/2/3 ? Default si absent : **ACTIVER les 3 défensifs** (low risk, real value).
> Pour les 2 audit hooks (`config_change`, `notification_audit`, `post_tool_use_edit_log`) : default **GARDER DORMANT** + ajouter whitelist explicite dans test H.0.

**Sous-section 6.1 — TEST PIN** :
`tests/test_h6_hooks_registered.py` : assert les 3 défensifs sont dans settings.local.json.

**Sous-section 6.2 — FIX** :
Edit `.claude/settings.local.json` + update `install_hooks()` dans `engine/core/muninn_install.py` pour register au prochain `muninn-mem init`.

**Sous-section 6.3 — STAGE** :
```bash
git add tests/test_h6_hooks_registered.py .claude/settings.local.json engine/core/muninn_install.py muninn/muninn_install.py
```

---

### Chunk H.7 — Décisions sync_tls + watchdog (15 min)

**Sous-section 7.1 — DÉCISIONS** (default Sky absent) :
- `sync_tls.py` (643 LOC) : **GARDER** + déplacer dans `engine/core/experimental/sync_tls.py` + doc CLAUDE.md "experimental, opt-in via MUNINN_SYNC_TLS_HOST=..."
- `watchdog.py` (66 LOC) : **GARDER** + ajouter docstring "Windows Task Scheduler standalone, Linux: irrelevant" + ajouter à whitelist H.0.

**Sous-section 7.2 — IMPL + STAGE** :
```bash
mkdir -p engine/core/experimental
git mv engine/core/sync_tls.py engine/core/experimental/sync_tls.py
# Update imports dans engine/core/sync_backend.py si besoin
git add engine/core/experimental/sync_tls.py engine/core/sync_backend.py CLAUDE.md
```

---

### Chunk H.8 — Garde-fou API bloat MyceliumDB (30 min)

**Sous-section 8.1 — DÉCISION** : refactor MyceliumDB en Phase H = **NON** (trop gros). Ajouter juste un test garde-fou anti-régression.

**Sous-section 8.2 — TEST** :
`tests/test_h8_api_bloat_baseline.py` :
- Compte le nombre de méthodes publiques de MyceliumDB, Mycelium, Cube
- Assert que ce nombre **ne dépasse pas** le baseline actuel (figer pour Phase I refactor)

**Sous-section 8.3 — STAGE** :
```bash
git add tests/test_h8_api_bloat_baseline.py
```

---

### Chunk H.9 — Docs sync (15 min)

**Sous-section 9.1 — Updates** :
- CHANGELOG : section "Phase H delivered" avec liste des features activées
- WINTER_TREE : snapshot final post-H
- README : ajouter section "Quick reference 35 CLI commands"
- QUICKSTART : exemples concrets `muninn-mem cube`, `muninn-ui`, `--include-dreams`, `muninn-mem metrics`

**Sous-section 9.2 — STAGE** :
```bash
git add CHANGELOG.md WINTER_TREE.md README.md docs/QUICKSTART.md
```

---

### Chunk H.10 — Bump 1.0.3 → 1.1.0 + build (15 min)

> **NE PAS UPLOAD TestPyPI pendant Phase H**. Upload sera fait APRÈS push GitHub (Sky décide).

**Sous-section 10.1 — Bump version** :
- pyproject.toml : version `1.0.3` → `1.1.0`
- muninn/__init__.py (2 spots)
- muninn/_engine.py (2 spots)
- engine/core/muninn.py (2 spots)

**Sous-section 10.2 — Build sanity** :
```bash
rm -rf build dist *.egg-info
python3 -m build --no-isolation 2>&1 | tail -2
python3 -m twine check dist/* 2>&1 | tail -2
# Attendu : Successfully built + PASSED both
```

**Sous-section 10.3 — STAGE** :
```bash
git add pyproject.toml muninn/__init__.py muninn/_engine.py engine/core/muninn.py
# NE PAS stage dist/ (gitignored)
```

---

### Chunk H.FINAL — Vérif H.0 garde-fou GREEN + sanity full

**Sous-section F.1 — Garde-fou maintenant GREEN** :
```bash
python3 -m pytest tests/test_h0_no_orphan.py -v
# Attendu : 6/6 PASS (toutes les orphans ont été wirées par H.1-H.7)
```

Si toujours rouge : DÉBUG quel test fail, identifier quel chunk a manqué le wire, retour à ce chunk.

**Sous-section F.2 — Full pytest** :
```bash
python3 -m pytest tests/ -q --tb=line \
  -m "not slow" \
  --ignore-glob='tests/test_ui_*.py' \
  --ignore=tests/eval_harness_chunk9.py \
  --ignore=tests/eval_harness_chunk11.py \
  --ignore=tests/test_chunk1_auto_memory_disabled.py \
  --ignore=tests/test_chunk_a7_hook_integrity.py \
  --deselect tests/test_retrieval_benchmark.py::test_actr_activation_varies \
  2>&1 | tail -5
# Attendu : ≥ 2546 + 25 nouveaux Phase H tests = 2571+ PASS, 0 fail
```

**Sous-section F.3 — Forge final** :
```bash
forge --gen-props engine/core/muninn.py 2>&1 | tail -3
forge --modularity 2>&1 | head -3
# Attendu : Q ≥ 0.67 (stable ou meilleur)
```

---

## 🎯 LE GROS COMMIT FINAL (UN SEUL)

Quand tous les chunks H.0-H.10 + H.FINAL sont verts, exécute :

```bash
cd /home/sky/Bureau/MUNINN-
git status -sb
# Verify : tous les fichiers en "M " ou "A " (staged), zéro modified non-staged

git commit -m "$(cat <<'EOF'
feat(phase-H): Light Up Everything — wire 17.8K LOC dormantes + garde-fou anti-orphan + bump 1.1.0

Phase H "Light Up Everything" — exécution chunk par chunk per
docs/PROMPT_EXEC_PHASE_H.md (Sky's master prompt).

11 chunks livrés (H.0 → H.10) :

H.0 GARDE-FOU ANTI-ORPHAN (test_h0_no_orphan.py, 6 tests)
  - test_no_orphan_engine_module : pour chaque engine/core/*.py, au moins
    1 caller depuis code shipped (pas tests/)
  - test_no_orphan_ui_module : pour chaque muninn/ui/*.py, référencé
  - test_all_env_vars_documented_read
  - test_all_argparse_flags_consumed
  - test_all_cli_commands_have_handler
  - test_all_hooks_on_disk_registered
  → Système immunitaire CI : tout futur orphan = CI rouge automatique

H.1 muninn-mem cube CLI (5597 LOC débloquées)
  - argparse choices += "cube"
  - --cube-action {scan,run,status,god} + --cycles --level
  - Handler call cli_scan/run/status/god

H.2 muninn-ui console script (11 712 LOC débloquées)
  - pyproject [scripts] += muninn-ui = "muninn.ui.main_window:main"
  - pyproject [optional-dependencies] += ui = ["PyQt6>=6.10"]
  - muninn/ui/__main__.py NEW
  - main() function added to main_window.py

H.3 --include-dreams flag (561 LOC débloquées)
  - argparse flag added + plumbing vers prune(include_dreams=...)

H.4 muninn-mem metrics CLI (344 LOC débloquées)
  - argparse choices += "metrics"
  - Handler call forge_metrics.compute_metrics(repo)
  - Reuse --output flag (was dead)

H.5 Cleanup dead config
  - MUNINN_GL_SOFTWARE wired dans muninn/ui/main_window.py:main()
  - --output flag réutilisé par H.4
  - 2 TODO stubs supprimés (muninn.py:682, muninn/_engine.py:764)

H.5b Hygiene
  - .forge baseline refresh
  - memory/ legacy doc explicite dans CLAUDE.md
  - 16 tags pre-* gardés (safety nets)

H.6 Wire 3 hooks défensifs Claude Code (~750 LOC)
  - pre_tool_use_bash_destructive
  - pre_tool_use_bash_secrets
  - pre_tool_use_edit_hardcode
  - 2 hooks audit gardés dormants intentionnels (whitelist H.0)

H.7 sync_tls + watchdog
  - sync_tls.py → engine/core/experimental/ (opt-in via MUNINN_SYNC_TLS_HOST)
  - watchdog.py kept + docstring "Windows Task Scheduler standalone"

H.8 Garde-fou API bloat (Phase I refactor reporté)
  - test_h8_api_bloat_baseline.py freeze MyceliumDB/Mycelium/Cube API count

H.9 Docs sync
  - CHANGELOG + WINTER_TREE + README Quick Reference + QUICKSTART examples

H.10 Bump 1.0.3 → 1.1.0
  - 4 mirrors version sync
  - python -m build : muninn_memory-1.1.0.whl + .tar.gz CLEAN
  - twine check PASSED

VÉRIFICATIONS (RULE 4) :
- H.0 garde-fou : 6/6 PASS post chunks (ROUGE→VERT, prouve les wires)
- Full pytest : 2571+ PASS, 0 fail
- forge --modularity Q = 0.67X (stable)
- forge --gen-props engine/core/muninn.py : OK
- twine check dist/* : PASSED both

LOC débloquées en prod : ~17 800 (Cube + UI + dream + metrics + hooks)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 🚀 PUSH GITHUB (après commit)

```bash
git push 2>&1 | tail -3
# Attendu : <old>..<new>  main -> main
```

**Note** : la CI mycelium step prend 41min. Tu peux poursuivre vers post-script SANS attendre la verdict CI.

---

## 📝 POST-PUSH — Items à fix au cas par cas (PAS DANS CE PROMPT)

Quand la CI passe (ou rouge), Sky décide pour CHACUN :

1. **CI mycelium step** : si rouge sur Phase H, créer chunks H.x correctifs séparés
2. **TestPyPI 1.1.0 upload** : décision Sky (token déjà dans ~/.pypirc)
3. **PyPI prod 1.1.0** : décision Sky après TestPyPI validé
4. **Phase I refactor MyceliumDB** (81% API mort) : effort 3-4h, plus tard
5. **Decision 16 tags pre-*** : keep / cleanup / archive

Push GitHub trigger CI run (~44min). **Tu peux fermer la session ici**, le cousin Claude qui reprendra demain matin verra le résultat CI et continuera selon décision Sky.

---

## ✅ CONTRAT DE FIN DE PHASE H

Tu as exécuté Phase H correctement SI ET SEULEMENT SI :

- [ ] 11 chunks H.0-H.10 verts (output verbatim après chaque)
- [ ] 1 SEUL commit final (pas de commits intermédiaires entre chunks)
- [ ] 1 push GitHub réussi
- [ ] H.0 garde-fou test 6/6 PASS (prouve système immunitaire actif)
- [ ] Full pytest 2571+ PASS / 0 fail
- [ ] muninn-mem cube, muninn-ui, --include-dreams, muninn-mem metrics tous user-facing accessibles
- [ ] Build wheel 1.1.0 sanity check OK

**Si l'un de ces points fail → STOP et demande à Sky.**
