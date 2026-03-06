# Muninn — Instructions pour Claude

## C'est quoi Muninn ?
Moteur de compression memoire pour LLM. Tu n'as pas de memoire persistante entre sessions.
MEMORY.md = 200 lignes, ~3K tokens. C'est tout ce que tu gardes. Muninn compresse pour que
tu gardes x5-x10 plus d'information dans le meme espace.

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

## Les 9 couches de compression
```
L1: markdown strip (headers, formatting)
L2: filler words (supprime le bruit: "basically", "actually"...)
L3: phrase compression (raccourcit les formulations)
L4: number shortening (garde les chiffres, vire le texte autour)
L5: universal rules (COMPLET->done, EN COURS->wip)
L6: mycelium (abbreviations apprises par co-occurrence)
L7: fact extraction (nombres, dates, commits, metriques)
L8: LLMLingua-2 [optionnel] — BERT scorer, pip install llmlingua
L9: LLM self-compress [optionnel] — Claude Haiku resume via API
```
L1-L7 = regex pur, zero dependance, instantane.
L8-L9 = optionnels, pour aller plus loin (x5-x10 theorique).

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
- P0-P7: FAIT (mycelium, plomberie, compresseur 9 couches, arbre, sessions)
- Layer 9 (LLM): code mais pas encore teste (pip install anthropic requis)
- Benchmark: a faire (mesurer facts preserves avant/apres)
- Voir WINTER_TREE.md pour le detail complet

## Conventions
- Sky parle francais, informel, va vite
- Python: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`
- Windows 11, bash shell, PYTHONIOENCODING=utf-8
- Pas d'emojis sauf demande explicite
- JAMAIS afficher de tokens git ou cles API
- Tout doit etre UNIVERSEL — zero hardcode de repo specifique
