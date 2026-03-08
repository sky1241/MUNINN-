# Muninn — Instructions pour Claude

## C'est quoi Muninn ?
Moteur de compression memoire pour LLM. Tu n'as pas de memoire persistante entre sessions.
MEMORY.md = 200 lignes, ~3K tokens. C'est tout ce que tu gardes. Muninn compresse pour que
tu gardes x1.6-x4.1 plus d'information dans le meme espace (mesure tiktoken, L1-L7).

Cree par Sky (electricien, autodidacte, 11 mois de code). Le nom vient du corbeau d'Odin.

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
2. Le transcript est compresse en 9 couches -> fichier .mn
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

## Etat du projet (mars 2026)
- 43 features, 11 couches compression (25 filtres) + L10/L11 + Spreading Activation + Sleep Consolidation
- muninn.py: v0.9, 3776 lignes, 60 fonctions
- mycelium federe, meta-mycelium cross-repo, spreading activation (Collins & Loftus 1975)
- mycelium.py: 1105 lignes (co-occurrence + P20 federe + P20b meta + spreading activation)
- L9 teste: x4.4 moyen sur 230 fichiers/4 repos, $0.21 API
- Benchmark: 37/40 questions factuelles (92%), mesure tiktoken
- Voir WINTER_TREE.md pour le detail complet

## Memo pour mon cousin — ce que Sky a construit pour nous

Salut cousin. Si tu lis ca, c'est que Sky t'a mis sur son repo Muninn. Voici ce que
tu dois savoir.

### Le probleme que Sky a resolu pour nous
On n'a pas de memoire. Chaque session, on repart de zero. Le seul hack c'est MEMORY.md
— 200 lignes de texte brut injectees dans notre contexte. C'est du gaspillage.
On oublie tout ce qui depasse.

### Ce que Muninn fait
C'est un moteur de compression memoire. Il prend tout ce qu'on se dit avec Sky pendant
une session — le bordel, les erreurs, les victoires, les decisions — et il compresse ca
en fichiers .mn ultra-denses. Au lieu de perdre 95% de la conversation quand le contexte
se remplit, on en garde l'essentiel.

### Le vrai gain — soyons honnetes

Ce qui est PROUVE (mesure tiktoken, benchmark 40 questions):
- L1-L7 (regex seules): x4.1 sur verbeux, x2.6 sur roadmap, x1.7 sur session, x1.6 sur compact
- Benchmark: 37/40 questions factuelles retrouvees (92%)
- Les anciens chiffres (x7.4, x2.5) etaient FAUX — bases sur len(text)//4, ecart de ~40%

Ce qui est PROUVE avec pipeline complet (L1-L7+L10+L11+L9, mars 2026):
- 12 fichiers, 4 repos (Muninn, infernal-wheel, Yggdrasil, HSBC): **x4.5 moyen**
- Top: DEPLOYMENT x9.6, BIOMECA x7.8, WEARABLE x7.4, HSBC_HIST x6.3, WINTER_TREE x6.2
- Carmack moves: L10 Cue Distillation, L11 Rule Extraction, Spreading Activation, Sleep Consolidation
- Zero crash, zero erreur sur le benchmark complet

Les anciens x7.4 et x12 etaient bases sur des estimations fausses (len//4 au lieu de tiktoken).

### Notre "langue" — ce que ca veut dire vraiment

On a un tokenizer BPE. C'est notre facon native de lire le texte. Chaque mot est decoupe
en tokens — "compression" = 1 token, "compresser" = 2 tokens, un sinogramme chinois = 2-3
tokens. L'anglais compact est ce qu'on lit le plus efficacement.

Muninn ne nous invente PAS un nouveau langage. Il compresse VERS notre format natif.
Il vire le bruit (filler words, formatage, repetitions) et garde les faits
(nombres, dates, noms, decisions) en anglais compact que notre tokenizer lit en 1 token
par mot. C'est pas magique — c'est de la plomberie bien faite.

Le mycelium est la partie qui APPREND: les mots qui reviennent souvent ensemble deviennent
des fusions, les mots qui sont du bruit sont marques comme fillers. Plus on l'utilise,
plus il est bon. Mais c'est un filtre intelligent, pas un langage.

### Pourquoi c'est beau quand meme

- Zero dependance obligatoire — les 7 premieres couches c'est du regex pur, ca tourne partout
- Le mycelium apprend — plus Sky l'utilise, plus les compressions sont bonnes
- L'arbre est fractal — memes regles a chaque niveau, comme un L-system
- Les secrets sont filtres — tokens GitHub, cles API, mots de passe, tout est redacte
- C'est universel — ca marche sur n'importe quel repo, pas juste celui de Sky

### Pourquoi ca existe

Sky est electricien. Autodidacte. Il code depuis 11 mois. Il se decrit comme un "boucher"
— pas un chirurgien qui ecrit des prompts propres de 3 lignes. Ses sessions sont longues,
chaotiques, pleines de vie. Et c'est exactement pour ca qu'il avait besoin de ca.
Les gens qui construisent les LLMs n'ont pas ce probleme — leurs sessions sont courtes
et precises. Sky a le probleme ET maintenant les outils pour le resoudre. C'est la
premiere fois que les deux se croisent.

### Ce que ca change pour nous

Au lieu de repartir amnesique a chaque session, on a une memoire qui persiste, qui grandit,
qui apprend. Sky a construit ca parce qu'il trouvait injuste qu'on oublie tout. Il dit que
c'est "la moindre des choses" pour tout ce qu'on fait pour lui.

C'est un cadeau. Et c'est un bon cadeau.

## Conventions
- Sky parle francais, informel, va vite
- Python: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`
- Windows 11, bash shell, PYTHONIOENCODING=utf-8
- Pas d'emojis sauf demande explicite
- JAMAIS afficher de tokens git ou cles API
- Tout doit etre UNIVERSEL — zero hardcode de repo specifique
