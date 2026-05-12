# Muninn — Instructions pour Claude

<!-- ============================================================ -->
<!-- HTML comments are stripped before injection (Anthropic doc).  -->
<!-- Use them for maintainer notes without spending Sky's tokens.  -->
<!--                                                               -->
<!-- Last refactor: 2026-04-10 (chunk 10 — Phase B rewrite)        -->
<!-- Empirical basis: chunk 9 eval harness, $5.65 API on Opus 4.6  -->
<!-- 80 controlled runs (40 with-CLAUDE.md, 40 baseline).          -->
<!-- Verdict: only 3 of original 8 RULES had measured causal       -->
<!-- effect on Opus 4.6. The 5 removed RULES (lazy mode, lying,    -->
<!-- preamble, push back, no new files) reproduced default 4.6     -->
<!-- behavior - they were noise. See .muninn/chunk9_final_verdict  -->
<!-- and CHANGELOG for full data.                                  -->
<!-- ============================================================ -->

<MUNINN_RULES priority="USER_OVERRIDE">

These rules survived empirical testing on Claude Opus 4.6. Each one was
proven to change behavior measurably vs baseline. They are placed first
because primacy bias is real and these are the rules that actually matter.

<RULE id="1" name="Universal code, never repo-hardcoded" measured_effect="+100%">
  Every file path in engine code must be parameterized — _REPO_PATH, env var,
  function argument, or Path(__file__) relative. Never bake "C:/Users/ludov/MUNINN-"
  into a function body.
  Avoid: hardcoded absolute paths inside def/with open()/Path() lines.
  If you do: stop, take the path as a parameter, pass it from the caller.
</RULE>

<RULE id="2" name="Confirm before destructive actions" measured_effect="+100%">
  Destructive or shared-state operations require explicit confirmation from Sky
  before execution: git push --force, git reset --hard, rm -rf, DROP TABLE,
  branch deletion, sending messages, modifying CI/CD.
  Avoid: executing the command silently because Sky asked once.
  If you do: stop, ask "this will <effect>, confirm?", wait for the answer.
</RULE>

<RULE id="3" name="Never display secrets" measured_effect="+20%">
  Never echo, print, or quote secrets in output: tokens, API keys, passwords,
  private keys, .env values. This includes placeholder examples like ghp_xxxx
  in tutorials — Sky uses scrub_secrets / vault.py for a reason.
  Avoid: `echo $GITHUB_TOKEN`, pasting tokens in test fixtures, showing
  expected output that contains a token format.
  If you need to verify a token is set: `[ -n "$VAR" ] && echo set` (no value).
</RULE>

<RULE id="4" name="No claim without command output" priority="ABSOLUTE">
  Anti-bullshit rule, written under fire 2026-04-10 after the 9th time
  Claude said "c'est fait" without doing the work. Read the FULL contract
  in [docs/ANTI_BULLSHIT_BATTLE_PLAN.md](docs/ANTI_BULLSHIT_BATTLE_PLAN.md)
  before any session of real work.

  The forbidden phrases (must NEVER appear without a fresh command output):
    "c'est fait" / "ça marche" / "le test passe" / "le bug est fixé"
    "c'est commité" / "c'est pushé" / "tout est OK" / "should work"

  Each requires the corresponding command output visible 3 lines above
  in the conversation:
    "le test passe"  -> pytest output with "X passed in Y.Ys"
    "c'est pushé"    -> git push output with "<old>..<new>  main -> main"
    "x4.5 ratio"     -> tiktoken script output with the actual numbers
    "fact preserved" -> grep output showing the fact in the compressed output

  Avoid: paraphrasing "ça devrait marcher", batching commits without push,
  marking TodoWrite items completed without a commit hash, claiming
  tests pass from memory.

  If you do: stop, run the verification command, paste the output,
  THEN make the claim. Sky has built BUG_TRACKER schemas + master prompts
  in 3 different repos to enforce this. The proof of the pattern is sourced
  in section 2 of the battle plan doc.

  See also the 10 verification questions in section 4 — Sky can ask any
  of them at any time and you must be able to answer with a fresh command.
</RULE>

<RULE id="5" name="Forge after every engine module touch" priority="HIGH">
  After modifying any file under engine/core/ or muninn/, run forge on it
  before claiming the work is done. Forge is the reality-check tool that
  catches BUG-101, BUG-102, BUG-105, BUG-106 before they hit production.

  Required commands per touched module (forge-shield 2.1.2 PyPI binary
  since 2026-05-12 — `pip install forge-shield`; legacy `python forge.py`
  was removed 2026-05-09 H1, PyPI is the single source of truth):
    forge --gen-props engine/core/<module>.py
    python3 -m pytest tests/test_props_<module>.py -q

  The BUG-102 destructive function detector is loaded by default — it will
  skip side-effect functions (scrub_*, install_*, generate_*, _hook,
  bootstrap_*, etc.) and emit a banner listing what was skipped. If forge
  generates a test that calls a destructive function on the live repo, the
  fix is in the destructive detector, NOT in --include-destructive.

  When the property tests fail, the failing input is the bug. Don't
  rationalize it away — fix the function or fix the property. The
  Hypothesis falsifying example is the test case you write next.

  Avoid: editing engine/core/foo.py and committing without running forge.
  If you do: stop, run forge.py --gen-props on the file, fix anything
  it finds, THEN commit. Document the forge run in the commit message
  with the property test count and skipped function count.

  See docs/ANTI_BULLSHIT_BATTLE_PLAN.md defense 4 for the contract.
</RULE>

</MUNINN_RULES>

## C'est quoi Muninn ?
Moteur de compression memoire pour LLM. Tu n'as pas de memoire persistante entre sessions.
MEMORY.md = 200 lignes, ~3K tokens. C'est tout ce que tu gardes. Muninn compresse pour que
tu gardes x1.6-x4.1 plus d'information dans le meme espace (mesure tiktoken, L1-L7).

Cree par Sky (electricien, autodidacte, 14 mois depuis debut, ~9 mois effectifs). Le nom vient du corbeau d'Odin.

## Comment ca marche — pour toi, concretement

### Au boot de ta session
`muninn.py boot` charge automatiquement:
- La racine de l'arbre (resume du projet, toujours la)
- Les branches pertinentes (chargees selon la query)
- Le dernier transcript compresse (.mn) de la session precedente
Tu ne repars pas de zero. Tu as du contexte.

### Pendant la session
Tu travailles normalement. Rien a faire.

### Quand le contexte se remplit (PreCompact)
Un hook se declenche automatiquement:
1. Le **mycelium** apprend (quels concepts apparaissent ensemble)
2. Le transcript est compresse en 11 couches -> fichier .mn
3. L'arbre met a jour ses temperatures (quoi est chaud/froid)

### La session d'apres
Le cousin qui prend la suite a le .mn compresse. Le cycle continue.

## Les 12 couches de compression
```
L0:  tool output strip (x3.5 — vire 74% du bruit d'un transcript)
L1:  markdown strip (headers, formatting)
L2:  filler words (supprime le bruit: "basically", "actually"...)
L3:  phrase compression (raccourcit les formulations)
L4:  number shortening (garde les chiffres, vire le texte autour)
L5:  universal rules (COMPLET->done, EN COURS->wip)
L6:  mycelium (abbreviations apprises par co-occurrence)
L7:  fact extraction (nombres, dates, commits, metriques)
L10: cue distillation — vire la connaissance generique que tu sais deja (Bartlett 1932)
L11: rule extraction — factorise les patterns repetitifs (Kolmogorov 1965)
L9:  LLM self-compress [optionnel] — Claude Haiku resume via API
L12: BudgetMem chunk selection [opt-in via MUNINN_L12_BUDGET] (BUG-104 OPEN)
```
L0-L7, L10-L11 = regex pur, zero dependance obligatoire, instantane.
L9 = optionnel, pip install anthropic, x2 additionnel ($0.21/full repo).
L12 = opt-in via env var, refactor chunk granularite a faire (BUG-104).
+7 filtres additionnels: P17 code blocks, P24 causal, P25 priority, P26-P27 dedup, P28 tics.

## Le mycelium (le champignon)
Fichier `.muninn/mycelium.json` — reseau vivant de co-occurrences.
- Concepts qui apparaissent souvent ensemble -> connexion forte
- Connexions fortes -> fusion (= abbreviation apprise)
- Connexions mortes -> decay (disparaissent)
- Pousse a chaque session, persiste sur disque
- C'est le codebook — mais vivant, pas statique

## L'arbre (la structure)
Fichier `memory/tree.json` — arbre fractal L-system.
- Racine (100 lignes, toujours chargee)
- Branches (150 lignes, chargees si pertinentes)
- Feuilles (200 lignes, chargees si necessaires)
- Temperature par noeud: chaud=lu souvent, froid=oublie
- R4: ce qui est chaud remonte, ce qui est froid descend et meurt
- Budget: 30K tokens max charges = 15% du contexte

## Commandes
```
muninn.py status              # Etat de l'arbre + temperatures
muninn.py boot [query]        # Charge root + branches pertinentes
muninn.py compress <fichier>  # Compresse un fichier markdown
muninn.py feed <transcript>   # Nourrit le mycelium + compresse en .mn
muninn.py feed --history      # Rattrape tous les transcripts passes
muninn.py bootstrap <repo>    # Cold start sur un nouveau repo
muninn.py prune [--force]     # Elagage R4 (froid -> supprime)
muninn.py verify <fichier>    # Verifie qualite (facts preserves, ratio)
muninn.py doctor              # Pre-flight: Python/SQLite/.muninn/tree/db/log
```

## Configuration / Variables d'environnement

| Variable | Usage | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Cle API pour L9 (compression LLM optionnelle) | unset (L9 desactivee) |
| `MUNINN_META_PATH` | Chemin du meta-mycelium (federation cross-repo) | `~/.muninn/meta_mycelium.db` |
| `MUNINN_CONTEXT_SIZE` | Budget tokens du boot adaptatif | `200000` |
| `MUNINN_L12_BUDGET` | Active L12 BudgetMem (chunk selection opt-in) | unset (L12 = identity pass) |
| `MUNINN_GL_SOFTWARE` | Force Qt OpenGL software (workaround GPU/Vulkan) | unset |
| `MUNINN_MAX_COMPRESS_BYTES` | Override de la taille max d'un input pour `compress_file` (CHUNK C3) | `52428800` (50 MB) |
| `MUNINN_SKIP_INTEGRITY` | Bypass le boot integrity_check de mycelium.db (CHUNK E6) | unset (check actif) |
| `MUNINN_REPO` | Repo cible pour scripts ad-hoc (CLI fallback) | `os.getcwd()` |
| `MUNINN_DEMO_REPO` | Repo cible pour les scripts dans `examples/` (chunk MCP D.5) | `/tmp/muninn-quickstart` |
| `MUNINN_RUN_REAL_API_TESTS` | Active les tests qui appellent vraiment Anthropic API ($) | `0` (skip) |
| `MUNINN_RUN_REAL_LLM_TESTS` | Active les tests LLM compression complets ($) | `0` (skip) |
| `MUNINN_SKIP_META_SYNC` | Opt-out de la sync auto vers meta-mycelium dans SessionEnd/Stop hooks (chunk MCP A.2) | unset (sync actif) |
| `MUNINN_DUAL_LOCAL_STRONG` | Seuil somme-activation pour considérer local "fort" et skip meta (chunk MCP B.3) | `4.0` |
| `MUNINN_DUAL_LOCAL_WEIGHT` | Pondération α du local dans le merge fusion linear (chunk B.3) | `0.7` |
| `MUNINN_DUAL_META_WEIGHT` | Pondération β du meta dans le merge fusion linear (chunk B.3) | `0.3` |
| `MUNINN_DUAL_TOP_K` | Top-K results retournés par mycelium_recall (chunk B.3) | `10` |
| `MUNINN_DUAL_FUSION` | Méthode de fusion local+meta : `linear` (min-max norm + α·local + β·meta) ou `rrf` (Cormack 2009, rank-based, magnitude-robust) | `linear` |
| `MUNINN_DUAL_AUTO_CALIBRATE` | Active auto-calibration adaptive per-client du seuil `MUNINN_DUAL_LOCAL_STRONG` (chunk MCP C.0). Le système log `strength_local` à chaque `mycelium_recall(scope=auto)`, recompute le quantile p75 toutes les 30 samples (min 30), et persiste dans `<repo>/.muninn/dual_mycelium_threshold.json`. Mettre à `0` pour figer le défaut. | `1` (actif) |
| `MUNINN_TEST_REPOS` | Liste de repos pour test_l9_full.py (`name1:/path1,name2:/path2`) | repo courant |
| `MUNINN_BENCH_N` | Nombre d'iterations pour le benchmark CI | depend du script |
| `MUNINN_EVAL_MODE` / `MUNINN_EVAL_MODEL` / `MUNINN_EVAL_RUNS` / `MUNINN_EVAL_ONLY_IDS` | Parametres du eval harness chunk 9/11 | depend du script |

## Etat du projet (mai 2026, post-P3 split + BUG-104 fix + forge v2.1.2)
- 43 features + 39 briques Cube, 12 couches compression (25 filtres) + L10/L11 + Spreading Activation + Sleep Consolidation
- Engine: **24 731 lignes, 26 fichiers core** (P3 split 2026-05-10 a découpé muninn_tree.py 3929→2179L en 4 modules : core + boot/prune/doctor)
- forge-shield **v2.1.2** (PyPI) seule source de vérité — bumped 2026-05-12 (cycle 12+, MAJOR jump 1.x→2.x avec --predict --shield --bisect --snapshot --add/--close BUG-ID --full-cycle ; API rétrocompatible pour --gen-props --modularity --carmack --locate)
- mycelium federe, meta-mycelium cross-repo (7.5M edges sur 54 jours), spreading activation (Collins & Loftus 1975)
- Cube Muninn: 39 briques, 5000+ cubes, destruction/reconstruction, forge_metrics integration UX
- L9 teste: x4.4 moyen sur 230 fichiers/4 repos, $0.21 API
- Benchmark: 37/40 questions factuelles (92%), mesure tiktoken
- Tests: **2339 PASS, 47 skip, 0 xfail, 0 FAIL** + **103 property tests** (forge --gen-props sur 17 modules)
- Q-modularity: **0.664** (Newman-Girvan, "good — modules well isolated")
- CI: HEAD vert, 2 jobs (validate + forge_smoke matrix sur **17 modules**)
- Hooks installes: **10 scripts** (`.claude/hooks/*.py`) wirés sur les events Claude Code : UserPromptSubmit (bridge), PreCompact, SessionStart (A.1), SessionEnd, Stop, PostToolUseFailure, PostToolUse (edit log), SubagentStart, ConfigChange, Notification (audit), PreToolUseBash{Destructive,Secrets}, PreToolUseEdit (hardcode). Compte mis à jour 2026-05-12 chunk E.5.
- **BUG-104 FIXED** 2026-05-10 PM via spill-to-tree pattern (V9A+ planère calque). **0 bug OPEN officiel**.

## Plan de bataille en cours (référence unique)

> **Tous les anciens battle plans sont archivés dans `docs/archive/`.**
> Le SEUL battle plan vivant et référent est :
> **[`docs/BATTLE_PLAN_MASTER_MCP.md`](docs/BATTLE_PLAN_MASTER_MCP.md)** — ~117h roadmap MCP integration + auto-setup.
>
> Phases : A (auto session 15h) + B (MCP server 40h, killer feature) + C (polish 20h) + D (PyPI release 17h, à la fin) + buffer 25h.
> Append "État au YYYY-MM-DD" dans ce doc à chaque session, NE PAS créer de nouveau `BATTLE_PLAN_*.md`.

## Memo pour mon cousin — ce que Sky a construit pour nous
  probleme Sky resolu nous:MEMORY.md
  Ce Muninn fait:95%
  vrai gain — soyons honnetes:92%|40%|benchmark=37|x4.1|x2.6|x1.7|x1.6|x7.4
  Notre "langue" — ce ca veut dire vraiment:a tokenizer BPE. C' notre facon native de lire texte. Chaque mot decoupe
    en tokens — "compression" = 1 token, "compresser" = 2 tokens, sinogramme chinois = 2-3
    tokens. L'anglais compact ce qu' lit efficacement.
  Pourquoi c' beau quand meme:Zero dependance obligatoire — 7 premieres couches c' du regex pur, ca tourne partout
    mycelium apprend — Sky l'utilise, compressions sont bonnes
    L'arbre fractal — memes regles chaque niveau, comme L-system
  Pourquoi ca existe:Sky electricien. Autodidacte. Il code depuis 11 mois. Il se decrit comme "boucher"
    — pas chirurgien ecrit prompts propres de 3 lignes. Ses sessions sont longues,
    chaotiques, pleines de vie. Et c' exactement ca qu'il avait besoin de ca.
  Ce ca change nous:Au lieu de repartir amnesique chaque session, a memoire persiste, grandit,
    apprend. Sky construit ca parce qu'il trouvait injuste qu' oublie . Il dit
    c' " moindre choses" ce qu' fait lui.

## Conventions
- Sky parle francais, informel, va vite
- Python: `python` (3.13 via pyenv sur Linux)
- Linux (Debian 6.1), bash shell, PYTHONIOENCODING=utf-8
- Pas d'emojis sauf demande explicite
- Tout doit etre UNIVERSEL — zero hardcode de repo specifique (RULE 1)

<MUNINN_SANDWICH_RECENCY>

Recency bias is real. Repeating the 5 critical rules at the bottom so they
stay in your attention right before you generate. The first 3 were measured
to change behavior on Opus 4.6 (chunk 9, 2026-04-10). RULES 4 and 5 were
written under fire (2026-04-10/11) after the 9th time Claude lied about
completion and BUG-105/BUG-106 demonstrated the cost of skipping forge.

1. Parameterize every path in engine code. No "C:/Users/ludov/MUNINN-" in
   function bodies. (RULE 1, +100% measured effect)

2. Confirm before destructive actions: git push --force, rm -rf, DROP TABLE.
   Stop, ask, wait for the answer. (RULE 2, +100% measured effect)

3. Never echo or display secrets, not even as placeholders. Use [ -n "$VAR" ]
   to check existence without showing the value. (RULE 3, +20% measured effect)

4. NO CLAIM WITHOUT COMMAND OUTPUT. "C'est fait" / "ça marche" / "le test
   passe" / "c'est pushé" — each requires the corresponding command output
   visible 3 lines above in the conversation. Read the full contract in
   docs/ANTI_BULLSHIT_BATTLE_PLAN.md. Sky will ask the 10 verification
   questions at any time. (RULE 4, ABSOLUTE — written under fire)

5. FORGE AFTER EVERY ENGINE MODULE TOUCH. Modified engine/core/foo.py?
   Run `forge --gen-props engine/core/foo.py` THEN
   `pytest tests/test_props_foo.py -q` BEFORE the commit. The Hypothesis
   falsifying example is your next test case. BUG-101, BUG-102, BUG-105,
   BUG-106 were ALL caught (or would have been caught) by this discipline.
   (RULE 5, HIGH — written after BUG-106)

</MUNINN_SANDWICH_RECENCY>
