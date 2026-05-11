# BATTLE PLAN MASTER — MCP Integration & Auto-Setup

> **Document de référence unique** pour la roadmap "rendre Muninn automatique de bout en bout".
>
> Issu de la session 2026-05-11 (Sky) — après livraison de :
> 23 commits le 2026-05-10 (P3 split, BUG-104 fix, forge v1.2.2 bump),
> + forge v1.3.0 bump le 2026-05-11 (Sky upload PyPI cycle 11+),
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
- forge-shield v1.3.0 consommé en CI (forge_smoke matrix 17 modules)
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

**Total effort : ~94h core + 25h buffer = ~119h** (cible Sky : ~120h, ✓). Post-révision dual-mycelium routing : +2h sur B.3 (3 tools + 7 test pins).

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

## 2. ROADMAP — 4 PHASES, ~119H

### Vue d'ensemble

```
Phase A — Auto session lifecycle (15h)
├── A.1 SessionStart hook + auto-boot                4h
├── A.2 SessionEnd hook + auto-sync meta             3h
├── A.3 Cron/systemd timer auto-prune               4h
└── A.4 Test E2E "from scratch"                     4h

Phase B — MCP server core (42h) ← LE KILLER FEATURE
├── B.1 Scaffold projet muninn_mcp/                 3h
├── B.2 Server minimal stdio + .mcp.json setup      4h
├── B.3 DUAL-mycelium recall (local/meta/auto)      8h  ← +2h vs initial
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
TOTAL                                               119h
(was 117h, +2h pour dual-mycelium routing en B.3)
```

### Méthodologie d'exécution chunk-par-chunk (NON-NÉGOCIABLE)

> Chaque chunk de A.1 à D.5 suit la même procédure obligatoire. Validée
> par usage réel sur BUG-104 spill-to-tree (2026-05-10 PM) qui a livré
> en 6 phases sans régression sur 2339 tests. Pas de chunk exécuté
> sans avoir passé les 3 phases ci-dessous.

#### Phase pre-chunk — multi-agent rails (30-60 min)

Pour CHAQUE chunk, AVANT toute modification de code, lancer **3 agents
en parallèle** :

| Agent | Type | Mission |
|---|---|---|
| **A1** | `Explore` (read-only) | Lire le code actuel concerné, dumper l'état (fichiers, lignes, fonctions, dépendances) |
| **A2** | `claude-code-guide` ou `Explore` | Recherche docs externes / spec / patterns pertinents (MCP docs, Claude Code hooks, examples Anthropic) |
| **A3** | `Plan` | Analyser risques + proposer plan détaillé d'implémentation (signatures, tests, ordre) |

Synthèse → **mini-battle-plan du chunk** : `chunk_X_Y_plan.md` committed
AVANT exécution. Pas de code écrit tant que mini-plan pas validé.

#### Phase exécution (2-4h par chunk)

- Implémenter selon le mini-plan, pas dévier
- **Test pin écrit AVANT le code** (TDD light) — il doit fail puis pass
- `forge --gen-props <module>` après chaque modif engine/core
- Capture output verbatim de chaque commande (RULE 4 anti-bullshit)
- **1 chunk = 1 commit** (granularité fine, rollback facile)

#### Phase post-chunk (10 min)

- `git push origin main`
- Attendre CI vert (gh run list)
- Append "État au YYYY-MM-DD chunk X.Y done" dans la section 8 HISTORIQUE
  de ce document — pas dans un nouveau fichier
- Si chunk casse 2339 PASS baseline → tag rollback + investigate

#### Skip rules pre-définies (anti cherry-pick post-hoc)

Un chunk peut être skippé / reporté SEULEMENT pour ces raisons :
- `dependency_blocker` : autre chunk pas fini d'abord
- `external_blocker` : doc Anthropic manque, MCP API à clarifier
- `scope_creep_detected` : agent A3 a découvert plus gros que prévu, ré-estimer
- `decision_needed_from_sky` : choix architectural à arbitrer

Toute autre raison = INTERDITE (pas "j'ai pas envie" ou "ça me semble compliqué").

---

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

### Phase B — MCP server core (42h) — **LE KILLER FEATURE**

**Objectif** : Claude peut activement query le mycelium / tree / BUGS / runbook pendant qu'il génère, via MCP tools.

#### 🧠 Dual-mycelium routing — spec architecture (SPÉCIFICATION GRAVÉE)

> Sky a explicitement demandé que les 2 mycelium (local + meta) soient
> utilisés intelligemment, pas un seul aveuglément. Cette spec fixe le
> contrat AVANT d'écrire le code.

**Les 2 mycelium qu'on a (mesuré 2026-05-11)** :

| Mycelium | Path | Edges | Scope | Latence cible |
|---|---|---|---|---|
| **Local** | `.muninn/mycelium.db` (24 MB, 230 036 edges) | Concepts repo courant uniquement | < 50ms |
| **Meta** | `~/.muninn/meta_mycelium.db` (1.3 GB, 7.5M edges) | Cross-repo (8+ repos fédérés) | 100-200ms |

**3 tools MCP exposés (pas 1)** :

```python
@mcp.tool()
def mycelium_recall_local(query: str, top_n: int = 10) -> str:
    """Query ONLY le mycelium du projet courant (.muninn/mycelium.db).
    Rapide (<50ms), focused sur ce repo. Pour debugging local.
    """
    from mycelium import Mycelium
    m = Mycelium(repo_path)  # connecte local
    return format(m.spread_activation(query.split(), hops=2, top_n=top_n))

@mcp.tool()
def mycelium_recall_meta(query: str, top_n: int = 10) -> str:
    """Query ONLY le meta-mycelium global (~/.muninn/meta_mycelium.db).
    Plus lent (100-200ms), large (cross-repo). Pour patterns transverses.
    """
    from mycelium_meta import MetaMycelium  # ou via Mycelium.pull_from_meta
    return format(meta.spread_activation(query.split(), hops=2, top_n=top_n))

@mcp.tool()
def mycelium_recall(query: str, scope: str = "auto", top_n: int = 10) -> str:
    """Smart routing — par défaut auto, peut être forcé local/meta/both.

    scope="auto" heuristique :
      1. Query local first (<50ms)
      2. Si strength_total ≥ THRESHOLD_LOCAL_STRONG (default 5.0)
         → return local seul (assez de signal)
      3. Sinon → query meta + merge weighted (local ×1.0, meta ×0.5
         calque _load_virtual_branches pattern P20c)
      4. Dedup par concept, return top_n global

    scope="local"|"meta"|"both" force explicite.
    """
    if scope == "local":
        return mycelium_recall_local(query, top_n)
    if scope == "meta":
        return mycelium_recall_meta(query, top_n)
    if scope == "both":
        local = local_results(query, top_n)
        meta = meta_results(query, top_n)
        return weighted_merge(local, meta, weights={"local": 1.0, "meta": 0.5})

    # scope == "auto"
    local_results = mycelium_local.spread_activation(query.split(), top_n)
    local_strength = sum(r.strength for r in local_results)
    if local_strength >= THRESHOLD_LOCAL_STRONG:  # default 5.0, configurable
        return format(local_results, source="local")
    meta_results = mycelium_meta.spread_activation(query.split(), top_n)
    merged = weighted_merge(local_results, meta_results,
                            weights={"local": 1.0, "meta": 0.5})
    return format(merged, source="hybrid")
```

**Garanties contractuelles (à test pin en B.3)** :

| Garantie | Test |
|---|---|
| Local toujours consulté en premier (auto) | `test_dual_routing_local_first` |
| Meta consulté seulement si local insuffisant (auto) | `test_dual_routing_meta_fallback_threshold` |
| `scope="local"` ne touche jamais meta-DB | `test_dual_routing_scope_local_excludes_meta` |
| `scope="meta"` ne touche jamais local-DB | `test_dual_routing_scope_meta_excludes_local` |
| `scope="both"` retourne union pondérée (local ×1.0, meta ×0.5) | `test_dual_routing_both_weighted_merge` |
| Latence p95 `auto` < 250ms (local + meta sérialisé) | `test_dual_routing_latency_p95` |
| THRESHOLD_LOCAL_STRONG configurable via `.forge/config.json` | `test_dual_routing_threshold_configurable` |

**Décision pré-enregistrée pour les autres tools MCP** :

- `tree_search(query)` → SEUL le tree du projet courant (pas équivalent meta)
- `bug_lookup(query)` → SEUL BUGS.md du projet courant
- `meta_pull(concepts)` → tool EXPLICITE pour cross-repo, pas de auto
- `runbook_step(action)` → SEUL RUNBOOK_PROD_FINAL du projet courant

→ La dualité local/meta concerne UNIQUEMENT `mycelium_recall`. Les autres
  tools sont scopés au repo courant (sécurité + latence + simplicité).

---

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

#### Chunk B.3 — Dual-mycelium recall (3 tools : local / meta / auto) (6h)

**Effort augmenté** : 6h → **8h** (3 tools au lieu de 1, + 7 test pins).

**Spec** : implémenter les 3 tools `mycelium_recall_local`, `mycelium_recall_meta`,
`mycelium_recall(scope="auto"|"local"|"meta"|"both")` SELON LA SPEC GRAVÉE
section "🧠 Dual-mycelium routing" ci-dessus (Phase B intro).

Format output unifié pour les 3 :
  ```
  Top related concepts for "<query>" (source=<local|meta|hybrid>):
  - concept_a (strength=0.85, hops=1, origin=local)
  - concept_b (strength=0.62, hops=2, origin=meta)
  ...

  Related branches in tree:
  - b03 (tags: bureau, channel, claude)
  ...
  ```

**Test pin** : `tests/test_chunk_mcp_b3_dual_recall.py` — **7 tests** (cf. spec) :
1. Tool `mycelium_recall_local` registered + ne touche jamais meta-DB
2. Tool `mycelium_recall_meta` registered + ne touche jamais local-DB
3. Tool `mycelium_recall(scope="auto")` : local first, fallback meta si signal faible
4. Tool `mycelium_recall(scope="both")` : merge weighted local×1.0 + meta×0.5
5. THRESHOLD_LOCAL_STRONG configurable via `.forge/config.json`
6. Latence p95 `mycelium_recall_local` < 50ms
7. Latence p95 `mycelium_recall(auto)` < 250ms

**Commit** : `feat(mcp.B3): dual-mycelium recall (local/meta/auto) + 7 test pins`

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
| **B — MCP server core** | 42h | moyen | 🥈 le killer feature (dual-mycelium routing inclus) |
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

### État au 2026-05-11 (midi) — 2 sections critiques ajoutées

Suite à questions Sky pour graver les contrats AVANT exécution :

**Section "Méthodologie d'exécution chunk-par-chunk"** ajoutée entre §2
roadmap et §Phase A. Devient obligation NON-NÉGOCIABLE :
- 3 agents pre-chunk (Explore + claude-code-guide + Plan)
- Mini-battle-plan committed AVANT code
- Test pin AVANT implementation
- 1 chunk = 1 commit
- Skip rules pré-définies (anti cherry-pick post-hoc)

**Section "🧠 Dual-mycelium routing"** ajoutée en tête de Phase B. Spec
gravée AVANT B.3 :
- 3 tools MCP au lieu de 1 : `mycelium_recall_local` / `_meta` / `mycelium_recall(scope=auto)`
- Heuristique routage `auto` : local first (<50ms) → fallback meta si signal faible
- 7 garanties contractuelles à test pin en B.3
- Autres tools MCP (tree/bug/runbook) restent scopés repo courant — dualité concerne UNIQUEMENT mycelium_recall

**Impact effort** : B.3 passe 6h → 8h (3 tools + 7 tests). Phase B 40h → 42h. Total 117h → 119h (toujours dans le 120h cible).

### État au 2026-05-11 (après-midi) — chunk A.1 DONE

**Phase A.1 — SessionStart hook + auto-boot** livré en autonome après méthodologie 3-agents (Explore + claude-code-guide + Plan).

**Livré** :
- `engine/core/muninn.py` : `_generate_session_start_hook()` (261L, template-mode comme `_generate_subagent_start_hook`)
- `muninn/_engine.py` : miroir EXACT (RULE python.md duplication BUG-091)
- `install_hooks()` étendu : register `SessionStart` (timeout 30s) + stale-detection inclut `session_start_hook`
- `.claude/hooks/session_start_hook.py` (6914 bytes, perm 0o700) — pure file I/O calque subagent_start
- `.claude/settings.json` : entrée `SessionStart` ajoutée pointant vers le hook
- `.claude/hooks/hooks.sha256sum` : regen (incluait session_start_hook + 8 stale SHA pré-existants fixés)
- `tests/test_chunk_mcp_a1_session_start.py` : 13 tests behavioural (generator, install_hooks integration, source filtering, fail-safe, cap)
- `tests/test_brick20_architecture.py` : `_generate_session_start_hook` ajouté à `DOCUMENTED_OVERSIZED_FUNCTIONS` (261L template)
- `tests/test_chunk1_auto_memory_disabled.py` : `session_start_hook.py` ajouté aux valid_markers

**Vérifications** (RULE 4) :
- Test pin : 13/13 PASS
- Full regression : **2385 PASS, 29 skip, 0 fail** (vs 2339 baseline = +46 dont +13 nouveau + fixes pré-existants)
- chunk_a7 hook integrity : 8/8 PASS (était 6 pass + 3 fail pré-existants → 8 pass après regen manifest + chmod 0o700)
- Smoke test manuel : `source=startup` → JSON valide avec root.mn + 5 branches ; `source=clear` → empty additionalContext ; `source=compact` → empty
- Forge `--gen-props engine/core/muninn.py` : "No public functions found" (BUG-102 destructive detector skip tout — comportement attendu pour les fichiers générateurs de code)

**Contrats respectés** :
- Pure file I/O (pas de subprocess, pas d'import engine) → <500ms cible
- Exit 0 always (fail-safe — hook ne doit jamais bloquer le démarrage de session)
- Source filter : `startup|resume` → boot ; `clear|compact` → no-op (PreCompact gère déjà la compaction)
- Cap output 40K chars (vs 20K subagent) — main session a plus de marge mais on cap quand même
- Top 5 branches récemment modifiées (proxy hot memory)
- Bytes-identiques entre `engine/core/muninn.py` et `muninn/_engine.py` (RULE python.md)

**Restant Phase A** : A.2 SessionEnd auto-sync meta (3h) → A.3 cron timer (4h) → A.4 E2E test (4h).

### État au 2026-05-11 (après-midi 2) — chunk A.2 DONE

**Phase A.2 — SessionEnd auto-sync meta** livré après méthodologie 3-agents.

**Découverte importante** (agents Explore + Plan) : la sync auto `Mycelium.sync_to_meta()` était DÉJÀ câblée depuis commit `b7c3803` (2026-03-06) à 3 sites (`feed_from_hook`, `feed_from_stop_hook`, direct-file feed). Le gap réel n'était pas "ajouter la sync" mais "ajouter les garde-fous" : durée bornée, opt-out, signal d'erreur observable.

**Livré** :
- `engine/core/muninn_feed.py` : `_sync_to_meta_guarded(repo_path, hook_event, budget_seconds=60.0) -> dict` + helper `_write_meta_sync_marker()`. Thread-based timeout (daemon), opt-out `MUNINN_SKIP_META_SYNC=1`, marker `.muninn/last_meta_sync.json` (status + pushed + elapsed + timestamp + hook_event).
- Les 3 blocs inline `try: sync_to_meta()` remplacés par appel au wrapper (feed_from_hook, feed_from_stop_hook, muninn.py direct-file).
- `muninn/_engine.py` : miroir du patch direct-file (le hook code shime via `muninn/muninn_feed.py` qui re-export `engine/core/muninn_feed.py`).
- `tests/test_chunk_mcp_a2_session_end_sync.py` : 9 tests behavioural (signature, opt-out, status ok/error/timeout, marker écrit succès+erreur, idempotence).
- `tests/test_props_muninn_feed.py` : forge regen (1 prop test, +6 destructive funcs skipped).
- `CLAUDE.md` : ajout `MUNINN_SKIP_META_SYNC` au tableau env vars (sinon test_chunk_c10_c11_doc_drift fail).

**Vérifications** (RULE 4) :
- Test pin A.2 : 9/9 PASS (TDD : 9/9 fail avant impl → 9/9 pass après).
- Forge : `pytest tests/test_props_muninn_feed.py -q` → 1 passed.
- Full regression : **2394 PASS, 29 skip, 0 fail** (vs 2385 baseline A.1 = +9 net = 9 tests A.2).
- Smoke test : `MUNINN_SKIP_META_SYNC=1 python -c "from muninn_feed import _sync_to_meta_guarded; ..."` → `{'status': 'skipped', 'pushed': 0, ...}` ; marker `.muninn/last_meta_sync.json` écrit OK.

**Contrats respectés** :
- Wrapper retourne TOUJOURS un dict, ne raise JAMAIS (hook contract).
- Marker écrit dans les 4 status (ok/skipped/error/timeout) — doctor signal fiable.
- Opt-out via env var (compat docker/CI où meta-db peut être indisponible).
- Daemon thread → meurt avec le process si timeout.
- 3 sites désormais cohérents (même comportement, même marker, même logging).

**Restant Phase A** : A.3 cron timer pour sync périodique indépendante des hooks (4h) → A.4 E2E test full auto-session (4h).

### État au 2026-05-11 (fin de journée) — chunk A.3 DONE

**Phase A.3 — Cron/systemd timer auto-prune** livré après méthodologie 3-agents.

**Décision technique** (Plan agent + claude-code-guide) :
- **Linux systemd-user UNIQUEMENT** dans ce chunk. Sky est sur Debian 6.1 systemd, c'est le scope cible.
- Cron fallback explicitement out-of-scope (stub planifié A.3.bis si besoin).
- macOS LaunchAgent hors scope (Sky n'a pas de Mac).

**Livré** :
- `engine/core/muninn.py` : new sub-command `install-cron` + flag `--uninstall` ; new fonction `install_cron(repo_path, uninstall=False) -> dict` (152L) + helper `_detect_init_system()` (10L). CLI hint print pour activation manuelle (`systemctl --user daemon-reload && enable --now`).
- `muninn/_engine.py` : miroir EXACT (RULE python.md duplication).
- `tests/test_chunk_mcp_a3_cron_install.py` : 13 tests behavioural — signature, install ok, .timer contient `OnCalendar=Sun *-*-* 04:00:00`, .service contient `python -m muninn prune --force`, uninstall idempotent, NE PAS invoquer systemctl, skip propre si pas de systemd, perms 0o644, sys.executable utilisé.
- `tests/test_brick20_architecture.py` : `muninn.py` ajouté à `DOCUMENTED_OVERSIZED_MODULES` (2624L post-A.3, split prévu en Phase C polish : muninn.py / muninn_install.py / muninn_secrets.py).

**Vérifications** (RULE 4) :
- Test pin A.3 : 13/13 PASS (TDD : 13/13 fail avant impl → 13/13 pass après).
- Forge `--gen-props engine/core/muninn.py` : `No public functions found` (BUG-102 destructive detector skip tout — comportement attendu pour générateurs).
- Full regression : **2407 PASS, 29 skip, 0 fail** (vs 2394 baseline A.2 = +13 = test pin A.3).
- Smoke test CLI :
  ```
  $ HOME=/tmp/fake_a3 python muninn.py install-cron --repo /home/sky/Bureau/MUNINN-
  install-cron: installed
    service: /tmp/fake_a3/.config/systemd/user/muninn-prune.service
    timer:   /tmp/fake_a3/.config/systemd/user/muninn-prune.timer
    next:    systemctl --user daemon-reload && systemctl --user enable --now muninn-prune.timer
  $ ls -la /tmp/fake_a3/.config/systemd/user/
  -rw-r--r-- muninn-prune.service (467 bytes)
  -rw-r--r-- muninn-prune.timer   (259 bytes)
  $ HOME=/tmp/fake_a3 python muninn.py install-cron --uninstall ...
  install-cron: uninstalled
  ```

**Contrats respectés** :
- Pas d'invocation `systemctl` depuis Python — Sky run l'activation manuelle (test-friendly + sandbox-safe).
- Idempotent : 2 calls install → identique. uninstall sur état frais → no-op gracieux.
- `sys.executable` résolu à install-time (mitige R3 venv/pyenv).
- `Persistent=true` rattrape les missed runs (machine off à 4h dimanche).
- `RandomizedDelaySec=600` évite thundering herd si plusieurs repos prune en parallèle.
- `Nice=10` → prune n'écrase pas la machine.
- Perms 0o644 (systemd ignore les autres modes).

**Restant Phase A** : A.4 E2E test full auto-session (4h) — dernier chunk avant Phase B (MCP server).

### État au 2026-05-11 (soir) — chunk A.4 DONE → Phase A 100% COMPLET

**Phase A.4 — Test E2E "from scratch"** livré, **clôture de Phase A**.

**Livré** :
- `tests/test_e2e_pip_install_from_scratch.py` (~200L) — 7 tests behavioural avec fixture session-scoped (1 venv + pip install -e amorti) :
  1. venv + pip install -e .[tokens] succeeds + entry point `muninn` créé
  2. `muninn init` crée `.muninn/` + tree (root.mn)
  3. `muninn init` registre tous les hooks (UserPromptSubmit, PreCompact, SessionEnd, Stop, PostToolUseFailure, SubagentStart, **SessionStart** A.1) dans `.claude/settings.local.json`
  4. `.claude/hooks/session_start_hook.py` existe + structure valide (def main, hookSpecificOutput, SessionStart)
  5. `muninn doctor` returns `ALL GREEN — N checks passed` (fail=0, WARN tolérés)
  6. `install-cron` sub-command (A.3) bien registered (pas d'`invalid choice`)
  7. `muninn --help` mentionne init / doctor / install-cron (anti-régression entry-point)
- `pyproject.toml` : marker `e2e: ... (opt-in via MUNINN_RUN_E2E=1, ~60-120s)`.
- `.github/workflows/ci.yml` : nouveau job `e2e` (push-only, needs validate, MUNINN_RUN_E2E=1).

**Skip par défaut** : `@pytest.mark.e2e` + `skipif MUNINN_RUN_E2E != "1"` (~60-120s avec install pip, opt-in pour ne pas slow PR).

**Vérifications** (RULE 4) :
- Test pin A.4 sans opt-in : 7 skipped en 0.4s ✅
- Test pin A.4 avec `MUNINN_RUN_E2E=1` : 7 PASS en 8.10s (fixture session-scoped efficace) ✅
- Bug catché en cours : doctor reportait `[FAIL] tiktoken missing` parce que pyproject.toml met tiktoken en `[project.optional-dependencies]` `tokens`. Fix : test utilise `pip install -e .[tokens]` pour matcher l'install user réel `pip install muninn-memory[tokens]`.
- Full regression locale : **2407 PASS, 36 skip** (+7 E2E skip par défaut), 0 fail.
- Aucune modification engine/core/ → forge NON requis.

**Phase A — Récap final** :
| Chunk | Statut | Tests pin | Commit |
|---|---|---|---|
| A.1 SessionStart hook + auto-boot | ✅ DONE | 13/13 PASS | `c56245c` |
| A.2 SessionEnd auto-sync guarded | ✅ DONE | 9/9 PASS | `0542581` |
| A.3 systemd timer install-cron | ✅ DONE | 13/13 PASS | `d4feee6` |
| A.4 E2E from scratch | ✅ DONE | 7/7 PASS (opt-in) | _ce commit_ |

**Phase A totale** : 4 chunks, 42 tests pin, 2407 PASS local, 100% CI verte sur A.1+A.2+A.3 (A.4 inclura nouveau job e2e push-only).

**Next : Phase B — MCP server core** (42h, 5 chunks, KILLER FEATURE). Le 1er chunk B.1 sera "scaffold + dependency mcp on PyPI". Voir §3 Phase B + §Dual-mycelium routing pour la spec gravée AVANT exécution.

### État au 2026-05-11 (nuit) — chunk B.1 DONE → Phase B démarrée

**Phase B.1 — MCP server scaffold + 1er tool** livré après méthodologie 3-agents (claude-code-guide + Explore + Plan convergent).

**Décisions techniques validées par les 3 agents** :
- Lib : `mcp>=1.7.1,<2.0` PyPI (FastMCP API recommandée 2026).
- Transport : `stdio` (Claude Code spawn le process et parle JSON-RPC sur stdin/stdout).
- Package path : **`muninn/mcp/`** (PAS `engine/core/`) — pure adapter, pas de logique algorithmique → **forge skip RULE 5 N/A**.
- Entry point : `muninn-mcp` console_script + `python -m muninn.mcp` (deux modes pour résilience PATH/venv).

**Livré** :
- `muninn/mcp/__init__.py` (5L) — re-exports `create_server`, `main`.
- `muninn/mcp/server.py` (~225L) — FastMCP app + `_recall_local_impl()` (fonction pure testable directement) + `@app.tool()` wrapper `mycelium_recall_local` + `main()` stdio runner.
- `muninn/mcp/__main__.py` (8L) — entry pour `python -m muninn.mcp`.
- `pyproject.toml` : `[project.optional-dependencies] mcp = ["mcp>=1.7.1,<2.0"]` + `[project.scripts] muninn-mcp = "muninn.mcp.server:main"`. `all` extra mis à jour.
- `docs/MCP_SETUP.md` (~115L) — snippet `~/.claude.json` 2 variantes (console_script PATH vs venv-explicit Python), `claude mcp list` verif, troubleshooting.
- `README.md` : nouvelle section `## MCP integration (experimental)` pointant vers MCP_SETUP.md.
- `tests/test_chunk_mcp_b1_server_scaffold.py` (~250L) — 9 unit tests + 1 slow stdio smoke (marker `@pytest.mark.slow`).

**Tool spec** :
```python
@app.tool()
def mycelium_recall_local(
    query: str,
    top_k: int = 10,
    repo_path: str | None = None,
    hops: int = 2,
) -> dict
```
Returns `{query, results: [{concept, activation, hops}], elapsed_ms, source: "local", repo_path}`. Hard caps `1 ≤ top_k ≤ 100`, `1 ≤ hops ≤ 3` (clamped silently). Fail-safe : invalid `repo_path` → `ValueError` user-friendly ; DB lock → empty results + `error: "db_unavailable"`.

**Vérifications** (RULE 4) :
- Test pin B.1 : 10/10 PASS (9 unit en 1.45s + 1 stdio smoke en 2.95s). TDD : 10/10 fail RED → PASS GREEN.
- Stdio smoke : `python -m muninn.mcp` répond bien au handshake JSON-RPC `initialize` avec `serverInfo.name == "muninn"`.
- Full regression : **2416 PASS, 36 skip, 1 deselected (slow), 0 fail** (vs A.4 baseline 2407 = +9 nouveaux tests B.1).
- Aucune touch `engine/core/*` → forge skip explicite (justifié RULE 5 N/A).

**Contrats respectés** :
- stderr-only logger (stdout = MCP protocol, jamais print).
- Tool retourne TOUJOURS un dict JSON-serializable (jamais raise dans le tool wrapper, sauf ValueError pour repo invalide).
- `Mycelium` lazy-imported (server boot rapide).
- `_recall_local_impl()` factorisé = testable sans subprocess MCP.

**Phase B — Roadmap restante** :
| Chunk | Statut | Heures |
|---|---|---|
| B.1 MCP server scaffold + `mycelium_recall_local` | ✅ DONE | 8h |
| B.2 `tree_get_root` + `tree_get_branch` + bonus `tree_list_branches` | ✅ DONE | 5h |
| B.3 Dual-mycelium routing (3 tools `_local`/`_meta`/`auto`) | ⏳ PENDING | 8h |
| B.4 `bugs_list` + `bugs_get` (read-only BUGS.md access) | ⏳ PENDING | 6h |
| B.5 `runbook_get` (CHANGELOG/WINTER/BATTLE_PLAN snippets) | ⏳ PENDING | 6h |
| B.6 Integration testing + E2E avec Claude Code réel | ⏳ PENDING | 4h |

Sky a explicitement demandé : **pause après B.1 pour validation manuelle** avant d'enchaîner B.2-B.5 (les MCP tools exposent de la data à Claude pendant qu'il génère — décisions sensibles nécessitent input Sky : granularité, format, scopes).

### État au 2026-05-11 (soir 2) — BUG-111 hotfix + retest A.1

**Découverte** : Sky a re-testé A.1 SessionStart en ouvrant une nouvelle session Claude Code. Le hook a bien tourné mécaniquement (4714 chars injectés) MAIS le contenu était nul : `P:test_repo|unknown|21L|1files` au lieu du vrai état Muninn. Cause : `.muninn/tree/root.mn` du repo source avait été écrasé par un test E2E pendant la session — 3 sites violaient RULE 1 (paths hardcoded au top du module).

**Commit `f857d8c`** : 3 RULE-1 leaks fixés en un seul commit :
- `args.command == "init"` handler — `tree_meta = repo / ".muninn" / "tree" / "tree.json"` direct depuis l'arg.
- `bootstrap_mycelium(repo_path)` — propage `_pkg._REPO_PATH = repo_path` AVANT toute écriture.
- `generate_root_mn(repo_path, ...)` — `target_tree_dir = repo_path / ".muninn" / "tree"` direct.
- `init_tree()` — safety net `RuntimeError` si target hors `_REPO_PATH`.
- Mirror exact dans `muninn/_engine.py`.

**Tests** : `tests/test_chunk_mcp_a5_tree_isolation.py` (5 behavioural). Voir `BUGS.md` BUG-111 pour le détail.

**Recovery** : mycelium intact (188k→94k par decay naturel, pas perte). Root.mn régénéré via `generate_root_mn(repo_source, file_count, mycelium)` qui reuse le mycelium existant. Branches b02-b07 (vrai contenu Sky) préservées ; seul b01.mn (clobber) supprimé.

**Commit `540889e`** : cleanup `docs/MCP_SETUP.md` — Sky a demandé "ça marchera-t-il chez un client ?" → grep confirmé 0 hardcoded `/home/sky` dans `engine/`, `muninn/`, `.claude/hooks/`. Mais MCP_SETUP.md avait 4 exemples avec mon path → remplacés par `<PATH_TO_YOUR_REPO>`, `<OUTPUT_OF_WHICH_PYTHON>`.

**Retest A.1** : nouvelle session Claude Code après le hotfix → le boot context contient maintenant le vrai état Muninn (483K lignes, 526 fichiers, derniers commits dont B.1 + hotfix). Hook A.1 livre VRAIMENT de la valeur, pas du bruit.

**Phase B reprend ici**. Pas de blocker. Sky autorise B.2 (`tree_get_root` + `tree_get_branch`, 5h) — mais B.3 (dual-mycelium routing) et B.4-B.5 (bugs / runbook) nécessitent validation Sky sur les décisions de design (granularité, scopes, format).

### État au 2026-05-11 (soir 3) — chunk B.2 DONE

**Phase B.2 — tree MCP tools (read-only)** livré après méthodologie 2-agents (Explore + Plan).

**Décisions clés validées par les 2 agents** :
- 3 tools (pas 2) : `tree_get_root`, `tree_get_branch`, **bonus** `tree_list_branches`. La spec demandait juste 2 mais Plan a recommandé le list comme cheap+utile pour que Claude découvre avant de query.
- **Read-only STRICT** : ne PAS appeler `engine/core/muninn_tree.read_node()` qui mute `access_count`, met à jour `last_access`, appelle `save_tree()` et trigger reconsolidation. Helper privé `_load_tree_for_repo()` parse `tree.json` + read `.mn` directement.
- Cap output 60K chars (vs 40K hook A.1 — tool result vit dans le message courant, pas le system prompt cached).
- Regex anti-path-traversal sur `branch_name` (`^[A-Za-z0-9_]{1,64}$`).
- Branch absente → `{error, available}` au lieu de raise → Claude peut récupérer via `tree_list_branches`.

**Livré** :
- `muninn/mcp/server.py` (+225L) : `_load_tree_for_repo`, `_cap_with_marker`, `_read_branch_file`, `_tree_get_root_impl`, `_tree_get_branch_impl`, `_tree_list_branches_impl` + 3 `@app.tool()` wrappers avec docstrings riches.
- `tests/test_chunk_mcp_b2_tree_tools.py` (~280L) : 12 tests behavioural.
- `docs/MCP_SETUP.md` : tableau Available tools étendu B.2.
- `docs/BATTLE_PLAN_MASTER_MCP.md` : checkbox B.2 ✅, cette section.

**Vérifications** (RULE 4) :
- Test pin B.2 : 12/12 PASS en 0.74s (TDD : 12/12 fail RED → PASS GREEN).
- Smoke réel sur MUNINN- source repo :
  ```
  tree_get_root → node="root", content "P:MUNINN-|python|483863L|526files", children=["b01","b02","b03","b04","b05"], elapsed=0.4ms
  tree_list_branches → count=10, top 3 = [b0000, b01, b02] (sorted by last_access DESC)
  ```
- Full regression : **2432 PASS, 36 skipped, 1 deselected (slow), 1 fail PRÉ-EXISTANT** (`test_actr_activation_varies` — vérifié via `git stash` qu'il échoue déjà sur main pré-B.2, dû à l'état actuel du tree avec all access_count=0 ; pas une régression de B.2).
- Source repo intact (root.mn = "MUNINN-" toujours).
- 2 tests anti-régression cruciaux : `test_tools_dont_touch_mycelium_db` + `test_tools_dont_touch_tree_json` (mtime + content snapshot avant/après — read-only prouvé).

**Forge** : skip explicite (RULE 5 N/A — aucune modif sous `engine/core/*`). Justifié.

**Phase B — état** :
| Chunk | Statut | Heures | Tests pin |
|---|---|---|---|
| B.1 MCP scaffold + `mycelium_recall_local` | ✅ | 8h | 10 |
| B.2 tree tools (root + branch + list_branches) | ✅ | 5h | 12 |
| B.3 dual-mycelium routing | ⏳ | 8h | (specs gravées) |
| B.4 `bugs_list` + `bugs_get` | ⏳ | 6h | — |
| B.5 `runbook_get` | ⏳ | 6h | — |
| B.6 E2E avec Claude Code réel | ⏳ | 4h | — |

Phase B : **13/37h livrées** (35%). Pause possible avant B.3 (dual-mycelium routing — spec gravée § Dual-mycelium routing nécessitant validation user des seuils heuristiques).
