# BATTLE PLAN MASTER — MCP Integration & Auto-Setup

> **Document de référence unique** pour la roadmap "rendre Muninn automatique de bout en bout".
>
> Issu de la session 2026-05-11 (Sky) — après livraison de :
> 23 commits le 2026-05-10 (P3 split, BUG-104 fix, forge v1.2.2 bump),
> deep audit 3 agents sur MCP + Muninn current state + Claude Code hooks.
>
> Anciens battle plans archivés dans `docs/archive/`. Ce doc est **le seul**
> battle plan vivant — référencé depuis CLAUDE.md, BUGS.md, ROADMAP.
>
> Ne pas créer de nouveau `BATTLE_PLAN_*.md` daté — append des sections
> "État au YYYY-MM-DD" dans CE document à chaque session.

---

## 0. POURQUOI CE PLAN — ÉTAT MESURÉ 2026-05-11

### Ce qui marche déjà en prod (vérifié)

- 9 hooks Claude Code installés (UserPromptSubmit, PreCompact, SessionEnd, Stop, PostToolUseFailure, SubagentStart, ConfigChange, PreToolUseBash{Destructive,Secrets})
- `muninn init` / `bootstrap` / `install_hooks` fonctionnels
- Bridge hook injecte concepts mycelium à chaque prompt
- PreCompact compresse session × x132 mesuré
- 230 036 connexions mycelium local + 7.5M edges meta-mycelium
- 2339 tests pytest PASS + 103 property tests
- forge-shield v1.2.2 consommé en CI (forge_smoke matrix 17 modules)
- 22+ papers cités + 10 papers cross-validés (`sky1241/tree/CROSSVAL_REPORT.md`)

### Ce qui manque (gap MESURÉ pour "fully automatic")

| # | Gap | Impact | Effort |
|---|---|---|---|
| G1 | Pas de `SessionStart` hook — boot manuel | Claude amnésique au début de chaque session | 4h |
| G2 | Pas de `SessionEnd` auto-sync meta | Risque drift entre repo et meta-mycelium | 3h |
| G3 | Pas de cron auto-prune | Mycelium grossit sans nettoyage scheduled | 4h |
| G4 | Pas de test E2E "pip install + init from scratch" | Régression non-détectable sur first-user | 4h |
| G5 | **Pas de MCP server** — Claude ne peut pas query le mycelium pendant qu'il génère | Mycelium reste passif (juste contexte pré-loadé), pas actif | **40h** |
| G6 | Pas sur PyPI public | Sky doit faire support manuel sur chaque install | 17h (en fin) |

**Total effort : ~92h core + 25h buffer = ~117h** (cible Sky : ~120h, ✓).

---

## 1. FAITS DE RÉFÉRENCE (issus deep audit 3 agents 2026-05-11)

### 1.1 MCP Protocol

- Package : `pip install mcp` (Anthropic officiel, **v1.7.1 mai 2026**, stable)
- FastMCP haut-niveau inclus (mai 2026, `from mcp.server.fastmcp import FastMCP`)
- Transport : `stdio` (parfait local, zéro latence)
- 3 primitives : **tools** (functions executables), **resources** (data read-only), **prompts** (templates)
- Config Claude Code : `~/.claude.json` (user scope) OU `.mcp.json` (project scope, git-shared)
- Stabilité : MCP 1.x stable, **aucun breaking change prévu**
- Template officiel à fork : `github.com/modelcontextprotocol/servers`

**Exemple ultra-minimal (14 lignes)** :
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Muninn Server")

@mcp.tool()
def mycelium_recall(query: str) -> str:
    """Search Sky's mycelium for related concepts."""
    from mycelium import Mycelium
    m = Mycelium(repo_path)
    return format_for_claude(m.spread_activation(query.split(), hops=2))

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 1.2 Claude Code Hooks

31 hook events disponibles. Les pertinents pour Muninn :

| Hook | Timing | Peut modifier contexte ? | Status Muninn |
|---|---|---|---|
| `SessionStart` | Avant 1er prompt user | **Oui** (via `additionalContext` JSON) | ❌ pas wiré |
| `UserPromptSubmit` | À chaque prompt | Oui | ✅ wiré (bridge_hook) |
| `PreCompact` | Avant compaction context | Oui | ✅ wiré |
| `PostCompact` | Après compaction | Non | ❌ pas wiré |
| `SessionEnd` | Fin de session | **Non** (no-op only) | ✅ wiré partiellement |
| `Stop` | Claude finit une réponse | Non | ✅ wiré |
| `PostToolUseFailure` | Tool fail | Non | ✅ wiré |

### 1.3 Muninn current state

- **24 sub-commands** disponibles (`muninn init/bootstrap/boot/prune/feed/...`)
- `install_hooks` patche `.claude/settings.json` (pas `settings.local.json`)
- `bootstrap` crée `.muninn/` + `tree.json` + mycelium.db
- **PyPI** : `muninn-memory` v0.9.2 mais NON publié public (juste editable install)
- 0 cron / systemd timer / daemon
- README quick-start : 3 commandes manuelles (git clone + pip install -e . + bootstrap)

---

## 2. ROADMAP — 4 PHASES, ~117H

### Vue d'ensemble

```
Phase A — Auto session lifecycle (15h)
├── A.1 SessionStart hook + auto-boot                4h
├── A.2 SessionEnd hook + auto-sync meta             3h
├── A.3 Cron/systemd timer auto-prune               4h
└── A.4 Test E2E "from scratch"                     4h

Phase B — MCP server core (40h) ← LE KILLER FEATURE
├── B.1 Scaffold projet muninn_mcp/                 3h
├── B.2 Server minimal stdio + .mcp.json setup      4h
├── B.3 Tool mycelium_recall(query)                 6h
├── B.4 Tool tree_search(query)                     5h
├── B.5 Tool bug_lookup(query)                      4h
├── B.6 Tool meta_pull(concepts)                    5h
├── B.7 Tool runbook_step(action)                   5h
├── B.8 Tests E2E avec Claude Code + Desktop        4h
└── B.9 Latency tuning < 200ms par tool             4h

Phase C — Polish + benchmark (20h)
├── C.1 Property tests sur chaque tool MCP          5h
├── C.2 Documentation user (README + docs/)         4h
├── C.3 Examples gallery (calque forge/examples/)   4h
├── C.4 Benchmark fact-recall avant/après MCP       4h
└── C.5 CHANGELOG + version bump                    3h

Phase D — PyPI release (17h, à la FIN comme demandé Sky)
├── D.1 pyproject.toml finalisation                 3h
├── D.2 Test PyPI server                            3h
├── D.3 PyPI upload + verification                  2h
├── D.4 `muninn init` post-install detection        4h
└── D.5 First-user UX + examples polish             5h

Buffer R&D / bugs imprévus                          25h
─────────────────────────────────────────────────────
TOTAL                                               117h
```

### Phase A — Auto session lifecycle (15h)

**Objectif** : transformer "user doit lancer muninn boot manuellement" en "Claude boot automatiquement au début de chaque session".

#### Chunk A.1 — SessionStart hook + auto-boot (4h)

**Spec** :
- Créer `.claude/hooks/session_start_hook.py`
- Read stdin JSON (`session_id`, `transcript_path`, `cwd`, `source`)
- Si `source == "startup"` ou `"resume"` :
  - Lancer `muninn boot` avec query vide (loads root + hottest branches)
  - Retourner `{"additionalContext": "<output boot>"}` sur stdout
- Patcher `install_hooks()` dans `engine/core/muninn.py` pour ajouter ce hook au `.claude/settings.json`

**Test pin** : `tests/test_chunk_mcp_a1_session_start.py`
- Mock stdin avec payload SessionStart
- Vérifier que le script exit 0
- Vérifier que `additionalContext` contient "root.mn"

**Commit** : `feat(mcp.A1): SessionStart hook auto-boots root + hot branches`

#### Chunk A.2 — SessionEnd hook + auto-sync meta (3h)

**Spec** :
- Créer `.claude/hooks/session_end_hook.py`
- Read stdin JSON
- Lancer `mycelium.push_to_meta()` pour sync edges locales → meta-mycelium
- Logger via `log_hook_event` (déjà wiré F5)
- Exit 0 (SessionEnd ne peut pas bloquer)

**Test pin** : `tests/test_chunk_mcp_a2_session_end.py`

**Commit** : `feat(mcp.A2): SessionEnd hook auto-syncs to meta-mycelium`

#### Chunk A.3 — Cron/systemd timer auto-prune (4h)

**Spec** :
- Ajouter sub-command `muninn install-cron` qui :
  - Detect OS (Linux systemd vs cron vs macOS LaunchAgent)
  - Sur Linux systemd : crée `~/.config/systemd/user/muninn-prune.{service,timer}`
  - Sur Linux cron : ajoute ligne à `crontab -l`
  - Timer hebdomadaire (Sundays 4am)
- `muninn install-cron --uninstall` pour retirer
- Documenter dans README

**Test pin** : `tests/test_chunk_mcp_a3_cron_install.py` — vérifier que le timer file est créé + bien formé

**Commit** : `feat(mcp.A3): muninn install-cron sets up weekly prune timer`

#### Chunk A.4 — Test E2E "from scratch" (4h)

**Spec** :
- `tests/test_e2e_pip_install_from_scratch.py`
- Dans un `tmp_path` venv :
  - `pip install -e /home/sky/Bureau/MUNINN-` (path source actuel)
  - `cd tmp_repo && muninn init`
  - Vérifier `.muninn/`, hooks, settings.json
  - Vérifier `python -m muninn doctor` returns ALL GREEN

**Test pin** : passe en CI

**Commit** : `test(mcp.A4): E2E from scratch install + init`

---

### Phase B — MCP server core (40h) — **LE KILLER FEATURE**

**Objectif** : Claude peut activement query le mycelium / tree / BUGS / runbook pendant qu'il génère, via MCP tools.

#### Chunk B.1 — Scaffold projet muninn_mcp/ (3h)

**Spec** :
- Créer `muninn_mcp/` dans le repo MUNINN- (ou repo séparé `sky1241/muninn-mcp` — décision à prendre)
- Ajouter `mcp>=1.7.1` à `pyproject.toml` extras `[mcp]`
- Structure :
  ```
  muninn_mcp/
    __init__.py
    server.py        # FastMCP server
    tools/
      __init__.py
      recall.py
      tree.py
      bugs.py
      meta.py
      runbook.py
    config.py        # repo path, defaults
  ```
- README "How to install and run"

**Test pin** : `import muninn_mcp ; muninn_mcp.server.create_server()` ne crash pas

**Commit** : `feat(mcp.B1): scaffold muninn_mcp/ package`

#### Chunk B.2 — Server minimal stdio + .mcp.json setup (4h)

**Spec** :
- `muninn_mcp/server.py` minimal qui run via `python -m muninn_mcp`
- Sub-command `muninn install-mcp` qui :
  - Patche `~/.claude.json` ou `.mcp.json` avec :
    ```json
    {"mcpServers": {"muninn": {
       "type": "stdio",
       "command": "python",
       "args": ["-m", "muninn_mcp"],
       "env": {"MUNINN_REPO": "${CLAUDE_PROJECT_DIR}"}
    }}}
    ```
- Test : `claude mcp list` doit voir "muninn"

**Test pin** : `test_chunk_mcp_b2_server_starts.py`

**Commit** : `feat(mcp.B2): minimal MCP server + install-mcp sub-command`

#### Chunk B.3 — Tool mycelium_recall(query) (6h)

**Spec** :
- `@mcp.tool() def mycelium_recall(query: str, top_n: int = 10) -> str`
- Wraps `mycelium.spread_activation(query.split(), hops=2) + transitive_inference()`
- Format output :
  ```
  Top related concepts for "<query>":
  - concept_a (strength=0.85, hops=1)
  - concept_b (strength=0.62, hops=2)
  ...

  Related branches in tree:
  - b03 (tags: bureau, channel, claude)
  ...
  ```
- Latency budget : < 200ms (mesurer)

**Test pin** : `tests/test_chunk_mcp_b3_recall.py` — 5 tests :
1. Tool registered
2. Returns non-empty for known concept
3. Returns gracefully for unknown
4. Latency < 200ms
5. Handles empty query

**Commit** : `feat(mcp.B3): mycelium_recall tool wired to spread_activation`

#### Chunks B.4-B.7 — 4 autres tools (19h total)

Même pattern que B.3 pour :
- B.4 `tree_search(query)` — TF-IDF sur branches
- B.5 `bug_lookup(query)` — grep BUGS.md
- B.6 `meta_pull(concepts)` — cross-repo facts
- B.7 `runbook_step(action)` — search RUNBOOK_PROD_FINAL

#### Chunk B.8 — Tests E2E avec Claude Code + Desktop (4h)

**Spec** :
- Tester manuellement avec Claude Code CLI :
  ```
  $ claude
  > Use the muninn tools to find what BUG-104 is about
  ```
- Vérifier que Claude appelle `mcp_muninn_bug_lookup("BUG-104")` et utilise le résultat
- Documenter le test dans `docs/MCP_E2E_TEST.md` avec screenshots

**Test pin** : pas de pytest (E2E manuel), mais checklist documentée

**Commit** : `docs(mcp.B8): E2E test results + manual verification protocol`

#### Chunk B.9 — Latency tuning < 200ms par tool (4h)

**Spec** :
- Profiler chaque tool avec `cProfile` ou `time.perf_counter()`
- Optimisations probables :
  - Cache mycelium connection (pool)
  - Index TF-IDF en mémoire au boot serveur (pas par query)
  - Limit results top_n = 10 par défaut
- Documenter latencies finales dans `docs/MCP_LATENCY.md`

**Cible** : p50 < 100ms, p95 < 200ms par tool

**Commit** : `perf(mcp.B9): latency tuning < 200ms p95 across 5 tools`

---

### Phase C — Polish + benchmark (20h)

#### Chunk C.1 — Property tests sur chaque tool (5h)

**Spec** : `forge --gen-props muninn_mcp/tools/recall.py` puis pareil pour les autres. Vérifier que les tools ne crash pas sur input random (BUG-102 destructive detector skip OK).

**Commit** : `test(mcp.C1): 5 property test files for MCP tools`

#### Chunk C.2 — Documentation user (4h)

**Spec** :
- Update README.md MUNINN- section "Claude integration"
- Section "How Claude actively recalls from your mycelium" avec exemples
- Diagram ASCII du flow user → Claude → MCP → mycelium

**Commit** : `docs(mcp.C2): user-facing MCP integration guide`

#### Chunk C.3 — Examples gallery (4h)

**Spec** : `examples/mcp_demo/` avec un mini-projet où user clone, lance Claude, et voit Muninn en action en 30s. Calque sur `forge/examples/calculator`.

**Commit** : `examples(mcp.C3): muninn-in-action demo project`

#### Chunk C.4 — Benchmark fact-recall avant/après MCP (4h)

**Spec** : 
- Reprendre les 40 questions du benchmark factuel existant
- Mesurer le score sans MCP (just bridge hook + CLAUDE.md) : baseline
- Mesurer le score avec MCP (Claude can call mycelium_recall) : post-fix
- Comparer. **Cible : +10 points minimum** sur 40 questions.

**Test pin** : `tests/test_mcp_benchmark_fact_recall.py`

**Commit** : `test(mcp.C4): fact-recall benchmark before/after MCP`

#### Chunk C.5 — CHANGELOG + version bump (3h)

**Spec** : section [0.10.0] dans CHANGELOG.md, bump version partout, prepare release notes.

**Commit** : `release(mcp.C5): v0.10.0 — MCP integration complete`

---

### Phase D — PyPI release (17h) — À LA FIN comme demandé Sky

(détails identiques au plan précédent — voir section 2 du roadmap)

---

## 3. RÈGLES À TOUJOURS RESPECTER

Cf. [`docs/ANTI_BULLSHIT_BATTLE_PLAN.md`](ANTI_BULLSHIT_BATTLE_PLAN.md) — non-négociable.

1. **No claim without command output** — chaque commit doit avoir un test pin + run capture verbatim
2. **Forge after every engine module touch** — `forge --gen-props engine/core/X.py` + `pytest tests/test_props_X.py` AVANT commit
3. **No paths hardcoded** — toujours `Path(__file__)` / env var / function arg
4. **Confirm before destructive** — `git push --force`, `rm -rf`, etc. = stop + ask
5. **Never echo secrets** — pas de tokens dans output

---

## 4. ORDRE D'EXÉCUTION RECOMMANDÉ

| Phase | Effort | Risque | Priorité |
|---|---|---|---|
| **A — Auto session lifecycle** | 15h | bas | 🥇 commencer ici, win rapide |
| **B — MCP server core** | 40h | moyen | 🥈 le killer feature |
| **C — Polish + benchmark** | 20h | bas | 🥉 quand B est vert |
| **D — PyPI release** | 17h | bas | 🏁 à la fin |
| Buffer | 25h | — | à dispatcher |

**Mon conseil pratique** :
- Phases A.1+A.2 (~7h) cette semaine — déjà transforme l'UX
- Phase B en 2 semaines (sprint dédié)
- Phase C en parallèle de l'usage réel (1 semaine)
- Phase D quand tout le reste est stable

---

## 5. CHECKLIST FIN DE CHAQUE CHUNK

À copier-coller en fin de chaque session de travail :

```
- [ ] Test pin écrit ET pass (output verbatim)
- [ ] forge --gen-props sur les modules touchés si applicable
- [ ] Commit avec message descriptif (1 chunk = 1 commit)
- [ ] git push origin main
- [ ] CI HEAD vert (gh run list) — ou explication
- [ ] CHANGELOG.md entry ajouté
- [ ] BUGS.md mis à jour si bug nouveau

PAS FAIT (à reprendre) :
- ...
```

---

## 6. RÉFÉRENCES (à jour 2026-05-11)

- **Charte anti-bullshit** : `docs/ANTI_BULLSHIT_BATTLE_PLAN.md`
- **Carte pipeline & papers** : `docs/PIPELINE_FORMULAS_MAP.md`
- **Roadmap général** : `docs/ROADMAP_2026-05-10.md`
- **CHANGELOG** : `CHANGELOG.md`
- **Bugs status** : `BUGS.md`
- **Anciens battle plans** : `docs/archive/`
- **Forge consommé en CI** : v1.2.2 (PyPI)
- **Forge case studies** : `https://github.com/sky1241/forge-case-studies` (0/3 OUI verdict honest)

## 7. SOURCES EXTERNES VALIDÉES (deep audit 2026-05-11)

- MCP package : `pip install mcp` v1.7.1
- MCP GitHub officiel : https://github.com/modelcontextprotocol/python-sdk
- Servers templates : https://github.com/modelcontextprotocol/servers
- Claude Code hooks docs : https://code.claude.com/docs/en/hooks.md
- Claude Code MCP docs : https://code.claude.com/docs/en/mcp
- Claude Code settings : https://code.claude.com/docs/en/settings.md

---

## 8. HISTORIQUE (append seulement, ne pas écraser)

### État au 2026-05-11 (matin)

- Document créé suite à audit 3 agents + décision Sky d'unifier les battle plans
- 8 anciens battle plans archivés dans `docs/archive/`
- Phase A.1 → début prévu cette semaine
- Note : ne PAS publier sur HN/blog avant Phase C terminée (forge-case-studies a montré qu'il faut des benchmarks avant la promo)
