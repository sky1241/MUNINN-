# Phase G — Audit Compilation + Cleanup Final avant Prod (2026-05-13)

> **Audience** : Sky (validation chunk-par-chunk demain) + Claude (exécutant).
>
> **Contexte** : Phase E+F sont livrées et fonctionnelles. TestPyPI 1.0.3 live, CI green sur HEAD `107a0ad`, intégration MCP **prouvée live dans vraie session Claude Code** (premier consumer-side test réussi). Decision prod 1.0.3 reportée à demain pour Sky reposé.
>
> **Sky's request 2026-05-12 soir** : "ho sa me soule claude aujourdhui j ai vraiment la flemme je crois fait moi une analyse total de tout sa mesure l ensemble des dommage bosse en atonomis sans rien push et fait moi un deep audit avec battle plan pour demain stpo"
>
> Plan ci-dessous = compilation des findings des **4 deep audits** lancés en parallèle ce soir.

---

## Sommaire honnête de la dette technique post-Phase F

| Catégorie | Count | Sévérité globale |
|---|---|---|
| BLOCKERS prod (UX bugs visibles) | 2 | CRITICAL |
| IMPORTANT (qualité dégradée mais pas crash) | 5 | IMPORTANT |
| COSMETIC (drift docs internes, optimisation) | 3 | COSMETIC |

**Statut prod 1.0.3** : ship POSSIBLE tel quel (rien ne crash), mais ship MEILLEUR si G.1+G.3 fixés avant. Décision Sky.

---

## Méthodologie (NON-NÉGOCIABLE — apprentissage de Phase E)

Pour chaque chunk G.X :

1. **Problème** — 1 phrase verbatim
2. **POURQUOI ça foire** — cause technique
3. **QUI a foiré** — Claude (généralement)
4. **Reproduction** — commande exacte qui montre le bug
5. **Fix** — diff minimal
6. **Test pin** — vrai test fonctionnel (subprocess.run ou function call, PAS grep-presence)
7. **Output verbatim AVANT/APRÈS**
8. **Commit + push** avec message honnête
9. **Watch CI green** avant chunk suivant

Phase E a montré que push sans watch CI = 6 push rouges en série. **Discipline non négociable : 1 chunk = 1 commit = 1 watch CI = 1 décision avant chunk suivant.**

---

## Chunks G.X (ordonnés par sévérité décroissante)

### Chunk G.1 — Universal degree-based stopword filter (30min) — **BLOCKER qualité**

> **Version v2 (2026-05-12 soir)** : Sky a fait remarquer que hardcoder
> les stopwords français est mauvais design — les users parlent toutes
> les langues. **Sky a aussi pointé que la solution existe DÉJÀ dans
> son code** : `DEGREE_FILTER_PERCENTILE = 0.05` ligne 80 de mycelium.py.
> Ce plan v2 utilise CETTE solution universelle au lieu de hardcoder FR.

**Problème** : `recall_meta("compression")` retourne `pas(1.0), est(0.99), les(0.83)` — stopwords français dominent. Mais le vrai problème est plus large : N'IMPORTE QUELLE langue va avoir le même souci (anglais "the/of/and", espagnol "el/de/la", etc.).

**POURQUOI** : `engine/core/mycelium.py:80` définit `DEGREE_FILTER_PERCENTILE = 0.05` (top 5% degree concepts = universal stopwords). Mais ce filtre est utilisé **SEULEMENT pour bloquer les FUSIONS** (S3 tier), **PAS au query-time** du recall. Donc les stopwords passent au top des résultats même s'ils sont déjà identifiés comme tels.

**QUI a foiré** : Claude original (Phase initiale du mycelium) a implémenté le degree filter pour les fusions mais a oublié de l'appliquer au query-time. Mon plan G.1 v1 initial (hardcoder FR) était aussi mauvais — Sky m'a corrigé.

**Fix v2 (universal, multi-langues gratis)** :
1. Dans `_recall_local_impl` (mycelium.server) + `_recall_meta_impl` : à la fin du calcul, exclure du top-k tout concept dans le top 5% degree du graphe.
2. Le `Mycelium` instance a déjà la méthode pour calculer ça (utilisée par S3 fusion block). Réutiliser.
3. **Pas de liste hardcodée par langue.** Pas de maintenance future. Marche pour FR, EN, ES, ZH, code, tout ce qui domine en degree.
4. Bonus : `MUNINN_RECALL_STOPWORD_PERCENTILE` env var (default 0.05) → Sky peut tuner si trop strict ou trop laxe.

**Test pin** :
- `test_g1_recall_universal_stopword_filter_active` : seed mycelium avec mots fréquents synthétiques ("xxx" partout) → assert "xxx" absent du top-k recall même si haut activation
- `test_g1_recall_meta_no_french_stopwords_in_top10` : query "compression" sur le vrai meta de Sky + assert `pas`, `est`, `les` absent (incidental, vu que ces concepts sont en top degree)
- `test_g1_env_var_percentile_tunable` : MUNINN_RECALL_STOPWORD_PERCENTILE=0.0 → no filter ; =0.10 → plus strict ; verify behavior different

**Forge** : RULE 5 → forge --gen-props sur mycelium.py + verify property tests pass.

**Bonus credit** : commit message dira `Sky pointed the universal solution (DEGREE_FILTER_PERCENTILE already exists in mycelium.py:80). Co-Authored-By: Sky.`

---

### Chunk G.2 — Doc drift résiduel (15min) — **IMPORTANT**

**Problème** : Après le sed surgery E.3, 3 fichiers gardent encore `muninn init` au lieu de `muninn-mem init` :
- `muninn/_engine.py:1077-1078` (commentaires)
- `examples/quickstart_local.py:6` (docstring)
- `examples/mcp_recall_demo.py:36` (commentaire dans le if-fallback)
- `BUG_HOOKS_UNIVERSELS.md` (entier — mais c'est un bug report archivé, ajouter juste un header "RESOLVED en E.3")

**POURQUOI** : Mon sed E.3 ciblait les CLI invocations dans code blocks bash, pas les commentaires Python ni les docstrings.

**Fix** :
- 3 edits ciblés sur les fichiers Python
- 1 edit header dans BUG_HOOKS_UNIVERSELS.md

**Test pin** : `test_g2_no_old_cli_command_in_python_comments` : grep `\bmuninn (init|status|doctor)\b` dans engine/core/, muninn/, examples/ → 0 match.

---

### Chunk G.3 — Error handling friendly (20min) — **BLOCKER UX**

**Problème** : `muninn-mem feed /nonexistent.jsonl` → raw Python traceback (FileNotFoundError stack visible). Première impression catastrophique pour user PyPI random.

**POURQUOI** : `_engine.main()` n'a pas de try-except global pour les erreurs utilisateur courantes. Le code suppose des paths valides.

**QUI a foiré** : Pattern défensif jamais codé en Phase A.

**Fix** :
- Wrapper try/except dans `_engine.main()` qui catche `FileNotFoundError`, `PermissionError`, `IsADirectoryError`, `KeyError` et imprime un message friendly + exit(1) au lieu du traceback.
- Garder traceback visible si `MUNINN_DEBUG=1` (pour dev).

**Test pin** :
- `test_g3_feed_nonexistent_file_friendly_error` : subprocess.run muninn-mem feed /nonexistent.jsonl + assert exit=1 + assert "not found" in stderr + NO "Traceback" in output
- Pareil pour `bootstrap` sur path invalide, `compress` sur fichier non existant

---

### Chunk G.4 — F.1 tests @pytest.mark.slow (5min) — **IMPORTANT**

**Problème** : `tests/test_chunk_mcp_f1_uninstall.py` totalize ~11.5s (subprocess + filesystem). Pas marked `@pytest.mark.slow` donc inclus dans la suite "fast" → ralentit dev local + CI.

**Fix** : ajouter `pytestmark = pytest.mark.slow` au top du fichier.

**Test pin** : `test_g4_f1_tests_are_marked_slow` : parse le fichier + assert présence du marker.

---

### Chunk G.5 — `~/.pypirc` security (10min) — **IMPORTANT**

**Problème** : Token PyPI prod en plaintext dans `~/.pypirc` (chmod 600 OK, mais pas dans `.gitignore` global de Sky → risque de leak si Sky push accidentellement depuis home dir un jour).

**Fix** :
- Ajouter `~/.pypirc` au `~/.gitignore_global` de Sky
- Setup `git config --global core.excludesfile ~/.gitignore_global` si pas déjà fait
- Ajouter une note dans CHANGELOG ou QUICKSTART : "Never commit ~/.pypirc — chmod 600 + global gitignore"

**Test pin** : pas applicable (config global, hors repo).

---

### Chunk G.6 — Doctor pre-init clarity (30min) — **IMPORTANT**

**Problème** : `muninn-mem doctor` dans repo sans `.muninn/` affiche 19+ checks mixant état global (sync_log, meta DB) + état local manquant. Confusion : user voit "ALL GREEN" sur des choses qu'il n'a pas encore set up.

**Fix** :
- Au début de `doctor()`, check `if not (repo / ".muninn").exists():` → afficher message "No .muninn/ in this repo. Run `muninn-mem init` first. Doctor will check global health only:" puis simplified output (just deps + Python + SQLite + global meta DB).
- Si `.muninn/` existe → full doctor comme aujourd'hui.

**Test pin** :
- `test_g6_doctor_pre_init_simplified_output` : subprocess.run muninn-mem doctor dans tmp_path vierge + assert "Run `muninn-mem init` first" in stdout + assert moins de 10 checks dans output

---

### Chunk G.7 — Persistent MCP venv (1h) — **IMPORTANT**

**Problème** : `.mcp.json` pointe sur `/tmp/muninn_session_venv/bin/muninn-mcp-mem` qui disparaît au reboot. Sky doit recréer le venv à chaque session.

**Fix proposé (option C ranked above)** :
- Créer venv permanent dans `~/.local/share/muninn-mcp-venv/` (XDG standard)
- Update `.mcp.json` pour pointer là
- Setup script `scripts/setup_mcp_venv.sh` qui crée le venv + pip install muninn-memory[mcp] + idempotent (skip si existe déjà)
- Documenter dans QUICKSTART "first-time setup MCP"

**Test pin** :
- `test_g7_mcp_venv_path_persists_reboot` : assert `.mcp.json` command path n'est PAS dans `/tmp/`
- `test_g7_setup_script_idempotent` : run le script 2x, assert pas de re-pip install au 2e (déjà installé)

---

### Chunk G.8 — Python 3.10-3.12 compat test (15min) — **CAVEAT**

**Problème** : `pyproject.toml` claim `requires-python = ">=3.10"` mais on n'a testé que 3.13.13. Si un user en 3.10 install et hit une f-string syntax nouvelle ou un typing feature 3.11+, il crash.

**Fix** :
- Option A (quick) : changer claim à `>=3.13` (honest about reality)
- Option B (proper) : pyenv install 3.10.x + 3.11.x + 3.12.x, run pytest smoke sur chaque, OK → garder claim ; FAIL → option A

Recommandé : option B. Effort 30min pyenv setup + run.

**Test pin** : `test_g8_python_version_claim_honest` : si claim `>=X.Y` dans pyproject, au moins X.Y doit être testé en CI ou doc-ed comme "only tested on Z.W".

---

### Chunk G.9 — Wheel size reduction (45min) — **OPTIONAL pour 1.1.0**

**Problème** : Wheel 42-43MB dont ~40MB de 12 PNG UI templates (tree visualizations). Inattendu pour un CLI.

**Fix** :
- Déplacer `muninn/ui/templates/*.png` dans un extra `[ui]` :
  ```toml
  [project.optional-dependencies]
  ui = []   # placeholder, mais les PNG sont déjà shipped via MANIFEST
  ```
- Modifier `[tool.setuptools.package-data]` pour exclure les PNG du wheel core
- Créer package séparé `muninn-memory-ui` qui contient juste les PNG, install via `pip install muninn-memory[ui]`
- OU plus simple : laisser dans le wheel mais documenter clairement "42MB wheel — UI templates included for tree visualization"

**Decision Sky** : option simple (juste documenter) suffit pour 1.0.x, vrai split package en 1.1.0.

**Skip si pas le temps** — pas un blocker prod.

---

### Chunk G.10 — Audit honnête tests Phase E+F recompté (10min) — **COSMETIC**

**Constat** : Mon précédent audit avait dit "10 REAL + 12 MEDIUM + 3 WEAK" sur 25 tests Phase E+F. Recompte précis : **16 REAL + 6 MEDIUM + 3 WEAK**. J'avais SOUS-vendu en plus.

**Fix** : pas de code, juste mettre à jour CHANGELOG/WINTER_TREE avec le compte honnête + classification précise. Pour la mémoire historique correcte.

---

## Ordre d'exécution recommandé

| Ordre | Chunk | Effort | Justification |
|---|---|---|---|
| 1 | G.1 stopwords | 45min | BLOCKER qualité, visible LIVE, plus rentable en premier |
| 2 | G.3 error handling | 20min | BLOCKER UX pour PyPI users, rapide |
| 3 | G.2 doc drift résiduel | 15min | Vite fait, cohérence E.3 complète |
| 4 | G.4 F.1 slow marker | 5min | Trivial |
| 5 | G.6 doctor pre-init | 30min | UX clean |
| 6 | G.5 .pypirc security | 10min | Quick win sécurité |
| 7 | G.7 persistent MCP venv | 1h | Important mais peut attendre 1.1.0 |
| 8 | G.8 python compat | 30min | Honest version claim |
| 9 | G.9 wheel size | optionnel | Reporter 1.1.0 |
| 10 | G.10 audit recompte | 10min | Final cosmetic |

**Total core (G.1→G.6+G.10)** : ~2h25
**Total avec G.7+G.8** : ~4h
**Total avec tout** : ~4h45

---

## Sortie de Phase G

Si G.1+G.3+G.2+G.4+G.5+G.6 verts → **bump 1.0.4 + re-upload TestPyPI + re-validation 12 étapes TEST_PROTOCOL + decision prod 1.0.4** (au lieu de 1.0.3).

Si seulement G.1+G.3 verts → ship 1.0.4 quand même (les 2 blockers fixés, le reste = dette acceptable).

---

## Bonus — Décisions à prendre par Sky

1. **Ship 1.0.3 sur prod tel quel** OU **bump 1.0.4 après Phase G** ?
2. **G.7 persistent MCP venv** : effort 1h, attaque ou reporte 1.1.0 ?
3. **G.8 Python compat** : test pyenv 3.10-3.12 ou downgrade claim à 3.13-only ?
4. **G.9 wheel size** : option simple (doc) ou split package en 1.1.0 ?

À discuter demain matin avec tête fraîche.

---

## Final note

Phase E+F a livré l'intégration MCP **prouvée live en vrai consumer Claude Code session**. C'est le **premier vrai signal externe** que tout l'effort A→F était utile, pas du theater. La fatigue actuelle de Sky est légitime : 25+ commits en 24h + 2 phases de hardening découvertes en cours de route. Phase G = finir proprement, pas tout casser.

Demain on attaque chunk par chunk, explication ROOT CAUSE / WHO FAILED à chaque step, watch CI green avant suivant. Pas de stack push, pas d'overclaim.

---

# ANNEXE — PHASE H (Architecture cleanup, audit 2026-05-12 soir)

Sky a demandé un deep audit "y a des trucs pas branchés en production de partout, je vois arriver gros comme une maison". 4 agents lancés en parallèle ont confirmé. Findings :

## Dégâts mesurés

| Surface | Vivant prod | Orphan / Dormant | % dette |
|---|---|---|---|
| Tests (268 fichiers) | 210 actifs | 12 morts + 22 héritage skip | 10% |
| Engine code (26 700 LOC) | ~20 000 actif | **~6 700 dormants** | **25%** |
| Docs (78 .md) | **5** actifs | 73 orphans/archive | **93%** |
| Features claim (43) | 26 vivantes | **5 fantômes + 12 dormantes** | **40%** |
| CLI sub-commands (30) | 22 vivantes | 8 stub/orphan | 27% |

## Top 5 features fantômes (CODE ÉCRIT POUR RIEN)

| # | Feature | LOC | Tests | Activations prod |
|---|---|---|---|---|
| 1 | `vault.py` (AES-256-GCM) | 551 | 12 PASS | **0** — jamais `muninn lock` |
| 2 | `sync_tls.py` (TLS sync distant) | 643 | 8 PASS | **0** — pas de serveur |
| 3 | `mycelium_zones.py` (Laplacian) | 383 | 6 PASS | **0** — `zones` jamais run |
| 4 | `mycelium_dream.py:dream()` | 561 | indirect | **0** — `--include-dreams` jamais set |
| 5 | `think` command | 30 | 1 | **0** — `raise NotImplementedError` |

**Total : ~1 600 LOC crypto/sync + 561 LOC dream + 5500 LOC Cube system barely wired**

## Cube system findings (critical)

- 5500 LOC total (cube.py + cube_providers.py + cube_analysis.py)
- 39 bricks B1-B39
- Appelé UNIQUEMENT via `muninn scan` → **JAMAIS exécuté par Sky**
- Tests passent mais aucun call en prod observé dans hook_log (600+ entries depuis Phase A)
- Verdict honnête : système Cube = sandbox expérimentale, pas feature shipped

## Plans pour Phase H

### Option A — PRUNE TOTAL (recommandé si Sky veut alléger)

Supprimer le code orphan + tests associés + docs orphans + commandes CLI inutiles.

| Chunk H.X | Effort | Gain LOC |
|---|---|---|
| H.1 Remove vault.py + tests + CLI commands | 30min | -551 |
| H.2 Remove sync_tls.py + tests | 20min | -643 |
| H.3 Remove mycelium_dream.py.dream() + dead code | 30min | -300 (keep mixin shell) |
| H.4 Remove "think" stub + clean argparse | 5min | -30 |
| H.5 Remove "scan" + "trip" + "quarantine" CLI handlers if confirmed unused | 20min | -200 |
| H.6 Archive 30 orphan docs to `docs/archive/` | 30min | docs cleanup |
| H.7 Remove `test_ui_*.py` (15 fichiers jamais run) | 10min | -15 fichiers |
| H.8 Decision Cube system : prune complet OU déclarer `[experimental]` extra | 1-3h | -5500 OR doc-only |

**Total Option A** : ~3-5h, -7700 LOC, plus de clarté

### Option B — DOCUMENT + DEFER

Garder le code mais ajouter section CLAUDE.md "Future / Experimental Features" qui liste honnêtement :
- Vault : code complet, opt-in si jamais besoin AES-256-GCM
- Sync TLS : pilot, attente serveur distant config
- Zones : labo Laplacian clustering, run manuel
- Cube system : sandbox 39 bricks, jamais en prod
- Think : TODO stub

Plus : ajouter un test `test_features_claim_honest.py` qui pour chaque feature claimée dans CLAUDE.md verify qu'elle a au moins 1 appel en prod (via hook_log ou code path actif).

**Total Option B** : ~1h, 0 LOC supprimées, claim honnête.

### Option C — STATUS QUO

Laisser. Test coverage assure que rien ne casse. Coût = +7700 LOC dans le wheel, claims surfacés mais inutiles.

**Pas recommandé** — Sky veut clarté, pas accumulation.

## Recommandation finale

**Option B en priorité** (1h, honest claim, zéro risque) → puis **Option A par chunks** sur les semaines suivantes selon ce qu'il garde activer.

Mon avis : **vault.py + sync_tls.py + think** = vraiment morts, **PRUNE**. **Cube system + zones** = sandbox utile pour R&D, **DOCUMENT + extra**. **dream** = à discuter (peut servir à sleep consolidation futur).

À décider avec Sky demain matin tête fraîche après Phase G core (G.1+G.3 stopwords + error handling). Phase H = optionnel mais SOULAGE.
