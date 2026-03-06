# Muninn

> *Le corbeau de la memoire — celui qui revient toujours.*

Moteur de compression memoire pour LLM. 9 couches de compression, zero dependance obligatoire.

## Le probleme

Les LLM n'ont pas de memoire persistante. Chaque session repart de zero.
Le hack actuel = fichier MEMORY.md (200 lignes, ~3K tokens). C'est du texte brut
injecte dans le contexte. Gaspillage massif.

## Ce que fait Muninn

Muninn compresse la memoire et les transcripts de session pour que le LLM
garde x2.5 a x12 plus d'information dans le meme budget de tokens.

### 9 couches de compression

```
L1: markdown strip          L5: universal rules (FR->EN compact)
L2: filler word removal     L6: mycelium (abbreviations apprises)
L3: phrase compression      L7: fact extraction
L4: number shortening       L8: LLMLingua-2 (BERT scorer, optionnel)
                            L9: LLM self-compress (Claude API, optionnel)
```

- **L1-L7** : regex pur, zero dependance, instantane
- **L8** : `pip install llmlingua` — modele BERT ~1GB, CPU, x2.1 additionnel
- **L9** : `pip install anthropic` — Claude Haiku resume via API, x5 additionnel

### Le mycelium (codebook vivant)

Reseau de co-occurrences qui pousse a chaque session :
- Concepts frequents ensemble → connexion forte → fusion
- Connexions mortes → decay → disparition
- Plus tu l'utilises, mieux il compresse

### L'arbre (memoire structuree)

Arbre fractal L-system :
- Racine (100 lignes, toujours chargee) → pointeurs vers branches
- Branches (150 lignes, chargees si pertinentes)
- Temperature par noeud : chaud = lu souvent, froid = oublie
- Budget : 30K tokens max = 15% du contexte

## Commandes

```bash
muninn.py status              # Etat de l'arbre + temperatures
muninn.py boot [query]        # Charge root + branches pertinentes + derniere session
muninn.py compress <fichier>  # Compresse un fichier markdown
muninn.py feed <transcript>   # Nourrit le mycelium + compresse en .mn
muninn.py feed --history      # Rattrape tous les transcripts passes
muninn.py bootstrap <repo>    # Cold start sur un nouveau repo
muninn.py prune [--force]     # Elagage (froid -> supprime)
muninn.py verify <fichier>    # Verifie qualite (facts preserves, ratio)
muninn.py scan <repo>         # Genere codebook local
```

## Resultats mesures

| Input | Ratio | Details |
|-------|-------|---------|
| Texte verbeux (MEMORY.md style) | x7.4 | 1091 → 148 tokens, -86% |
| WINTER_TREE.md | x2.9 | 96% facts preserves, EXCELLENT |
| README.md | x1.7 | 75% facts preserves, GOOD |
| Transcript de session | x2.5 | Avec L8 (LLMLingua) |

## Installation

```bash
# Minimum (L1-L7, zero dependance)
git clone https://github.com/sky1241/MUNINN-.git
python engine/core/muninn.py status

# Optionnel: L8 (BERT compression)
pip install llmlingua

# Optionnel: L9 (LLM self-compress)
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
```

## Hooks Claude Code

Ajouter dans `.claude/settings.local.json` :
```json
{
  "hooks": {
    "PreCompact": [{ "type": "command", "command": "python path/to/muninn.py feed --repo ." }],
    "SessionEnd": [{ "type": "command", "command": "python path/to/muninn.py feed --repo ." }]
  }
}
```

## Origine

Cree par Sky (electricien, autodidacte, 11 mois de code).
Ne de l'observation que la memoire LLM n'est pas un probleme de stockage
mais un probleme de compression.

## Licence

MIT
