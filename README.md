# Muninn

> *Le corbeau de la memoire — celui qui revient toujours.*

Moteur de compression memoire pour LLM. 42 features, 11 couches de compression (25 filtres), zero dependance obligatoire.

## Le probleme

Les LLM n'ont pas de memoire persistante. Chaque session repart de zero.
Le seul hack actuel : un fichier MEMORY.md (200 lignes, ~3K tokens) injecte dans le contexte.
Quand le contexte se remplit, tout deborde et disparait.

## Ce que fait Muninn

Muninn compresse les transcripts de session en fichiers `.mn` ultra-denses
et les recharge intelligemment au boot suivant.

**Resultat mesure** : x23.1 sur WEARABLE.md (134K tokens), x4.5 sur transcript (1.1M tokens), 92% des faits preserves (tiktoken).

## Architecture

```
                  BOOT (query)
                     |
              [session_index]──── P22: cherche dans les 50 dernieres sessions
                     |
              [recall "query"]─── P29: recherche mid-session
                     |
         ┌──────────┼──────────┐
      [root.mn]  [branches]  [last .mn]
         |           |           |
      toujours    TF-IDF +   auto-continue
      charge      spreading     P23
                  activation
                     |
              ┌──────┴──────┐
           [mycelium]    [tree.json]
           co-occurrences   L-system
           fusions/decay    temperature
```

## Pipeline de compression (25 filtres, 11 couches)

```
L0:  tool output strip (x3.5)     <- le plus gros gain, 74% du transcript est du bruit
L1:  markdown strip                L2:  filler words
L3:  phrase compression            L4:  number shortening
L5:  universal rules               L6:  mycelium (abbreviations apprises)
L7:  fact extraction               L10: cue distillation (Carmack move)
L11: rule extraction (Kolmogorov)  L9:  LLM self-compress (Haiku API, optionnel)
+P24: causal preservation          +P25: priority survival (KIComp density)
+P26: line dedup                   +P27: read dedup
+P28: Claude tics filter           +Semantic RLE (debug loop collapse)
+Contradiction resolution          +NCD dedup (zlib similarity)
+Context-Aware Merging             +Bloom concept tracking (boot)
+R1-Compress chunking (L9)         +Optimal Forgetting (cold re-compress)
```

- **L0-L7, L10-L11** : regex pur, zero dependance, instantane
- **L10** : Cue Distillation — vire la connaissance generique que le LLM sait deja (Bartlett 1932 + Predictive Coding 1999)
- **L11** : Rule Extraction — factorise les patterns repetitifs en regles (Kolmogorov 1965)
- **L9** : `pip install anthropic` — Claude Haiku via API (x2 additionnel)

## Le mycelium (codebook vivant)

Reseau de co-occurrences qui pousse a chaque session :
- Concepts frequents ensemble -> connexion forte -> fusion (abbreviation apprise)
- Connexions mortes -> decay -> disparition
- Plus on l'utilise, mieux il compresse
- Fichier : `.muninn/mycelium.json`

## L'arbre (memoire structuree)

Arbre fractal L-system :
- Racine (toujours chargee) -> pointeurs vers branches
- Branches (chargees si pertinentes via TF-IDF + Spreading Activation + Park et al. 2023)
- Temperature par noeud : chaud = lu souvent, froid = oublie et elague
- Budget : 30K tokens max = 15% du contexte

## Memoire intelligente

- **Tags** : B> bug/fix, E> error, F> fact, D> decision, A> architecture
- **Priority survival** : quand le budget deborde, les decisions et bugs survivent en dernier
- **Causal preservation** : "because X" est protege de la compression
- **Error/fix memory** : erreurs + solutions auto-surfacees au boot si la query matche
- **Session index** : catalogue des 50 dernieres sessions, cherchable au boot et mid-session
- **Auto-continue** : boot sans query = reprend les topics de la session precedente

## Commandes

```bash
muninn.py status              # Etat de l'arbre + temperatures
muninn.py boot [query]        # Charge root + branches pertinentes + sessions
muninn.py recall "query"      # Recherche mid-session dans toute la memoire
muninn.py compress <fichier>  # Compresse un fichier markdown
muninn.py feed <transcript>   # Nourrit le mycelium + compresse en .mn
muninn.py feed --history      # Rattrape tous les transcripts passes
muninn.py bootstrap <repo>    # Cold start sur un nouveau repo
muninn.py prune [--force]     # Elagage (froid -> supprime)
muninn.py verify <fichier>    # Verifie qualite (facts preserves, ratio)
muninn.py ingest <dossier>    # Compresse des docs de reference en branches
```

## Resultats mesures (tiktoken)

| Contexte | Pipeline | Ratio | Facts |
|----------|----------|-------|-------|
| UX Bible WEARABLE (134K tok) | L1-L7+L10+L11+L9 | **x23.1** | - |
| UX Bible DESIGN_TREE (14K tok) | L1-L7+L10+L11+L9 | **x12.7** | - |
| UX Bible MOBILE (130K tok) | L1-L7+L10+L11+L9 | **x8.4** | - |
| Transcript reel (1.1M tok) | L1-L7+L9 | **x4.5** | 92% |
| Texte verbeux | L1-L7 | x4.1 | 100% |
| Roadmap technique | L1-L7 | x2.6 | 96% |

## Installation

```bash
# Minimum (L0-L7, zero dependance externe)
git clone https://github.com/sky1241/MUNINN-.git
cd MUNINN-
python engine/core/muninn.py bootstrap .

# Token counting reel (recommande)
pip install tiktoken

# Optionnel: L9 (LLM self-compress)
pip install anthropic
export ANTHROPIC_API_KEY=sk-...
```

## Hooks Claude Code

Le bootstrap configure automatiquement les hooks.
Sinon, ajouter dans `.claude/settings.local.json` :
```json
{
  "hooks": {
    "PreCompact": [{ "type": "command", "command": "python engine/core/muninn.py feed --repo ." }],
    "SessionEnd": [{ "type": "command", "command": "python engine/core/muninn.py feed --repo ." }]
  }
}
```

## Structure du repo

```
engine/core/
  muninn.py        # Moteur principal (3643 lignes, 62 fonctions)
  mycelium.py      # Tracker co-occurrences (1105 lignes, federe + meta + spreading activation)
  tokenizer.py     # Wrapper tiktoken
memory/
  tree.json        # Arbre L-system
  root.mn          # Memoire racine
  b*.mn            # Branches
tests/
  test_l8_ordering.py
  benchmark/
docs/
  LITERATURE.md    # Revue de litterature (15+ papiers)
  BENCHMARK_*.md   # Resultats de benchmarks
.muninn/           # Donnees locales (gitignored)
  mycelium.json    # Reseau co-occurrences
  sessions/*.mn    # Transcripts compresses
  session_index.json
  errors.json
```

## Origine

Cree par Sky (electricien, autodidacte, 11 mois de code).
Ne de l'observation que la memoire LLM n'est pas un probleme de stockage
mais un probleme de compression. Le nom vient du corbeau d'Odin — celui qui
se souvient de tout.

## Licence

MIT
