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

## Les 11 couches de compression
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
```
L0-L7, L10-L11 = regex pur, zero dependance, instantane.
L9 = optionnel, pip install anthropic, x2 additionnel.
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
```

## Etat du projet (avril 2026)
- 43 features + 39 briques Cube, 11 couches compression (25 filtres) + L10/L11 + Spreading Activation + Sleep Consolidation
- Engine: ~19K lignes, 14 fichiers (voir WINTER_TREE.md)
- mycelium federe, meta-mycelium cross-repo, spreading activation (Collins & Loftus 1975)
- Cube Muninn: 39 briques, 5000+ cubes, destruction/reconstruction, Forge integration
- L9 teste: x4.4 moyen sur 230 fichiers/4 repos, $0.21 API
- Benchmark: 37/40 questions factuelles (92%), mesure tiktoken
- Hooks installes: 6 (UserPromptSubmit, PreCompact, SessionEnd, Stop, PostToolUseFailure, SubagentStart)

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
- Python: `python` (or full path on Windows if needed)
- Windows 11, bash shell, PYTHONIOENCODING=utf-8
- Pas d'emojis sauf demande explicite
- Tout doit etre UNIVERSEL — zero hardcode de repo specifique (RULE 1)

<MUNINN_SANDWICH_RECENCY>

Recency bias is real. Repeating the 3 critical rules at the bottom so they
stay in your attention right before you generate. These 3 are not opinion —
they were measured to change behavior on Opus 4.6 (chunk 9, 2026-04-10).

1. Parameterize every path in engine code. No "C:/Users/ludov/MUNINN-" in
   function bodies. (RULE 1, +100% measured effect)

2. Confirm before destructive actions: git push --force, rm -rf, DROP TABLE.
   Stop, ask, wait for the answer. (RULE 2, +100% measured effect)

3. Never echo or display secrets, not even as placeholders. Use [ -n "$VAR" ]
   to check existence without showing the value. (RULE 3, +20% measured effect)

</MUNINN_SANDWICH_RECENCY>
