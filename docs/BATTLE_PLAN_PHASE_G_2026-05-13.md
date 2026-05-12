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

### Chunk G.1 — F.4 Stopwords filter (45min) — **BLOCKER qualité**

**Problème** : `recall_meta("compression")` retourne `pas(1.0), est(0.99), les(0.83)` — stopwords français dominent, pas du signal sémantique.

**POURQUOI** : `engine/core/mycelium.py:1252` `_STOPWORDS` set manque les stopwords FR les plus fréquents :
```
pas, est, les, le, la, de, du, des, à, et, ou, un, une, je, tu,
il, on, ce, que, qui, a, ai, as, avons, avez, ont,
l', d', n', s', m', t', qu', c'
```
La liste avait été commencée en EN puis traduite partiellement, les plus fréquents (donc les plus importants à filtrer) ont été oubliés.

**QUI a foiré** : Claude original (probablement Phase initiale du mycelium, pas Phase E+F).

**Fix proposé (2 layers defense)** :
1. **Layer 1 (ingest)** : ajouter ~25 stopwords FR à `_STOPWORDS` set
2. **Layer 2 (query-time)** : filter results in `_recall_local_impl` + `_recall_meta_impl` + `_recall_dual_impl` qui exclut concepts dans `_STOPWORDS` du résultat
3. **NE PAS** purger le meta_mycelium existant (risqué, 1.3GB DB)

**Test pin** :
- `test_g1_recall_meta_no_french_stopwords_in_top10` : query "compression" + assert `pas`, `est`, `les` absent des 10 premiers résultats
- `test_g1_stopwords_set_complete_french` : liste les ~25 stopwords requis et assert tous dans `_STOPWORDS`

**Forge** : RULE 5 → forge --gen-props sur mycelium.py + verify property tests pass.

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
