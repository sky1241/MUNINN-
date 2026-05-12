# Phase E — Hardening 1.0.2 (2026-05-12)

> **Audience** : Sky (validation chunk-par-chunk) + Claude (exécutant).
>
> **Contexte** : Phase D livré (4/5) avec 1.0.1 sur TestPyPI. Deep audit 4-agents a révélé 4 blockers + 6 issues importantes + 36 tests faibles. Sky valide le plan chunk-par-chunk avec **explication détaillée à chaque étape** (pourquoi ça foire / qui a foiré / fix / test / preuve).
>
> **Goal** : muninn-memory 1.0.2 prod-ready, tous blockers fix, principaux tests faibles renforcés, prêt pour PyPI prod upload.
>
> **Stratégie** : 1 chunk = 1 commit + forge --gen-props si engine/core/* touché (RULE 5).

---

## Méthodologie par chunk (NON-NÉGOCIABLE)

Pour chaque E.X, dans cet ordre :

1. **Problème** — 1 phrase
2. **POURQUOI ça foire** — cause technique
3. **QUI a foiré** — Claude (généralement) avec leçon
4. **Reproduction** — commande qui reproduit le bug + output verbatim
5. **Fix** — diff minimal, justifié
6. **Test pin** — vrai test fonctionnel (pas grep-presence)
7. **forge --gen-props** si engine/core/* touché
8. **Verification verbatim** — commande qui prouve le fix
9. **Commit + push** avec message honnête
10. **Watch CI** → green avant chunk suivant

---

## Chunk E.1 — Re-vérif empty-repo guard en pip-install (30 min)

**Problème** : Agent audit dit que `muninn status` auto-init dans le wheel pip-installé, contredisant mon test live D.4.

**Question à trancher** : D.4 fix est bien dans 1.0.1 sur TestPyPI ou j'ai un faux positif d'agent ?

**Reproduction** :
```bash
rm -rf /tmp/e1_venv /tmp/e1_empty
python3 -m venv /tmp/e1_venv
/tmp/e1_venv/bin/pip install --quiet --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ 'muninn-memory==1.0.1'
mkdir -p /tmp/e1_empty
cd /tmp/e1_empty
/tmp/e1_venv/bin/muninn status
# Capture output verbatim
find /tmp/e1_venv -name "tree.json" 2>/dev/null
find /tmp/e1_empty -name ".muninn" 2>/dev/null
```

**Critère pass** : output contient "No .muninn/ found" + `find` retourne vide.

**Si pass** : E.1 marqué resolved, agent était faux positif (a probablement run `init` avant test 2).
**Si fail** : on a un bug D.4 latent en pip-install. Fix obligatoire avant prod.

---

## Chunk E.2 — Fix `examples/mcp_recall_demo.py` + test runtime (45 min)

**Problème** : Le script claim appeler `mcp_server.tree_get_root()` mais ces fonctions n'existent pas au scope module.

**POURQUOI ça foire** : les tools MCP sont définis dans la fonction `create_server()` du module `muninn/mcp/server.py` via `@app.tool()` decorator. Elles existent comme méthodes liées à l'instance `app`, pas comme fonctions module-level. Le script les appelle comme si c'était `module.fonction()` → AttributeError.

**QUI a foiré** : Claude. J'ai écrit le script en D.5 sans le run end-to-end. Mon test fait `ast.parse()` qui valide syntaxe Python mais pas le runtime. Leçon : tout exemple livré doit avoir un test `subprocess.run([python3, script])`.

**Fix possible** :
- Option A : Refactor le script pour utiliser `create_server()` + récupérer les tools de l'app instance
- Option B : Importer directement les helpers internes (genre `_recall_local_impl`, `_load_tree_for_repo`) qui sont au scope module
- Option C : Supprimer le script (acceptable car `mcp_recall_demo` complexe pour un exemple)

**Recommandé** : Option B (utiliser les `_impl` functions au scope module qui font le travail réel sans passer par FastMCP).

**Test pin nouveau** : `tests/test_chunk_e_examples_run.py` qui fait `subprocess.run([sys.executable, script])` sur CHAQUE example, asserte exit code 0 (ou skip gracieux si `[mcp]` absent).

---

## Chunk E.3 — Name collision PyPI : décision + fix (60 min)

**Problème** : `muninn` (7.2.1, S&T data catalog) et `mycelium` (0.4.9, greenbyte/luigi) existent déjà sur pypi.org. Notre console scripts vont clobber leurs binaires si user a les 2 installés.

**POURQUOI ça foire** : pyproject.toml `[project.scripts]` enregistre `muninn = "muninn._engine:main"`. Quand pip install, ça crée `$VENV/bin/muninn`. Si user avait déjà le `muninn` 7.2.1 installé, **son binaire est écrasé**. Pip ne warne pas.

**QUI a foiré** : Claude. En D.1 j'ai pas vérifié l'existence des noms sur PyPI prod avant validation.

**Décision Sky requise** : 3 options.

| Option | Cost | Impact users |
|---|---|---|
| A. Renommer `muninn`→`muninn-mem`, `mycelium`→`muninn-mycelium` | 30min code + tous docs à mettre à jour | API change UX (les utilisateurs Claude Code voient `muninn-mem` au lieu de `muninn`) |
| B. Garder + documenter incompatibilité dans README | 5min docs | Risk clobber pour ~20 users existants (estimé) |
| C. Hybrid : garder `muninn` (priorité), renommer `mycelium`→`muninn-mycelium` car package abandonné en 2019 (faible risque) | 15min | Compromis raisonnable |

**Recommandé** : Option C (compromis).

---

## Chunk E.4 — Fix `muninn-mcp --help` argument parsing (30 min)

**Problème** : `muninn-mcp --help` lance le serveur stdio infiniment au lieu d'afficher l'aide.

**POURQUOI ça foire** : `muninn/mcp/server.py:main()` call directement `app.run()` (FastMCP stdio loop) sans parser argv. `--help` lui est passé en argv mais ignoré ; le serveur attend stdin JSON-RPC indéfiniment. User voit un terminal qui pend.

**QUI a foiré** : Claude. En B.1 quand j'ai créé `muninn-mcp` script, pas mis d'argparse. Convention CLI : tout binaire doit répondre `--help` + `--version`.

**Fix** : ajouter argparse minimal dans `main()` qui intercepte `--help`, `--version`, `--list-tools` avant d'entrer la boucle stdio.

**Test pin** : `subprocess.run([muninn-mcp, '--help'], timeout=5)` doit retourner exit 0 + output contenir "Usage:".

---

## Chunk E.5 — Doc cleanup (45 min)

**Problèmes** :
1. README mentionne 5× "2356 tests" — actual 2561
2. README link dead vers `docs/BATTLE_PLAN_2026-05-09.md` (doesn't exist, vrai = `MASTER_MCP.md`)
3. QUICKSTART line 73 dit "muninn 0.9.x" — actual 1.0.1
4. CLAUDE.md "9 hooks installés" — actual 10 fichiers `.claude/hooks/*.py`

**POURQUOI ça foire** : pas de test de doc drift automatique (sauf chunk C8 version sync). Les docs évoluent moins vite que le code.

**QUI a foiré** : Claude. À chaque chunk j'aurais dû vérifier que les docs amont sont à jour.

**Fix** : 4 edits ciblés + 1 test pin de drift étendu (compte tests dynamique, link checker, version coherence).

---

## Chunk E.6 — Renforcer 5 tests WEAK les + dangereux (90 min)

**Cible** : transformer 5 tests grep-presence en tests fonctionnels qui catchent vraiment les régressions.

| Test à renforcer | Pourquoi dangereux | Renforcement |
|---|---|---|
| `test_d5_examples_scripts_parseable` | A laissé passer le bug `mcp_recall_demo` | → `subprocess.run([sys.executable, script], timeout=30)` sur CHAQUE example |
| `test_d1_manifest_prunes_internal_data` | Grep MANIFEST.in, jamais build sdist | → build sdist + `tarfile.open()` + assert `muninn/.muninn/` ABSENT |
| `test_a3_service_calls_muninn_prune` | Grep keywords, systemd jamais validé | → parse ExecStart, vérifier que la commande s'exécute (dry-run) |
| `test_d5_doctor_checks_console_scripts` | Grep dans doctor.py source | → call `doctor()` réellement + capture stdout + assert présence des 3 checks |
| `test_c0_env_var_top_k_default` | Reload module, jamais call réel | → seed mycelium + call `_recall_dual_impl()` + asserte limite respectée |

**POURQUOI tests faibles existent** : speed-of-delivery. Grep-presence est plus rapide à écrire que test fonctionnel. Le coût se paie quand un bug passe au travers (cf. E.2).

**Note** : on ne renforce pas TOUS les 36 weak tests (effort 2.5h supplémentaires). Juste les 5 plus risqués. Les autres restent dans la dette technique documentée.

---

## Chunk E.7 — Re-build 1.0.2 + re-upload TestPyPI + decision prod (30 min)

**Étapes** :
1. Bump `1.0.1` → `1.0.2` dans les 4 mirrors
2. `rm -rf build dist *.egg-info && python3 -m build --no-isolation`
3. `twine check dist/*`
4. Re-run TEST_PROTOCOL_PHASE_D_2026-05-12.md de bout en bout
5. Upload TestPyPI 1.0.2 via le terminal interactif (token TWINE_PASSWORD)
6. Install fresh venv from TestPyPI 1.0.2 + verify tous les blockers E.1-E.4 fix
7. Decision Sky : go prod 1.0.2 ou pas

---

## Stats prévus fin de Phase E

- Engine : ~26 500-26 700 LOC (E.4 ajoute argparse ~20L)
- Tests : ~2570 actifs (+10 tests E.x)
- Q-modularity : devrait rester ≥ 0.67
- Bugs OPEN : 0
- PyPI : muninn-memory 1.0.2 sur TestPyPI + (selon décision) prod

---

## Sortie de Phase E

Quand tous les chunks E.1-E.7 verts + Sky valide → on peut :
- Soit uploader sur PyPI prod (`twine upload --repository pypi dist/*`)
- Soit pause et reprendre plus tard

Pas de Phase F prévue. Phase E = fin du cycle MCP+PyPI.
