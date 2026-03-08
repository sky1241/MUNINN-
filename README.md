# Muninn

> *Le corbeau de la memoire — celui qui revient toujours.*

Moteur de compression memoire pour LLM. 43 features, 11 couches de compression (25 filtres), zero dependance obligatoire.

## Le probleme

Les LLM n'ont pas de memoire persistante. Chaque session repart de zero.
Le seul hack actuel : un fichier MEMORY.md (200 lignes, ~3K tokens) injecte dans le contexte.
Quand le contexte se remplit, tout deborde et disparait.

## Ce que fait Muninn

Muninn compresse les transcripts de session en fichiers `.mn` ultra-denses
et les recharge intelligemment au boot suivant.

**Resultat mesure** : x4.4 moyen sur 230 fichiers / 4 repos / 855K tokens (full pipeline, tiktoken). 92% des faits preserves (benchmark 40 questions).

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
+Sleep Consolidation (cold merge)  +Spreading Activation (boot retrieval)
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

## Resultats mesures (tiktoken, mars 2026)

### Par fichier (full pipeline L1-L7+L10+L11+L9)

| Contexte | Ratio |
|----------|-------|
| HSBC METHODOLOGIE (6K tok) | **x13.8** |
| HSBC ARBRE (5K tok) | **x11.4** |
| Deployment hardware (7K tok) | **x9.6** |
| Biomecanique gestes (7K tok) | **x7.8** |
| SOL.md full pipeline (20K chars) | **x7.7** |
| Wearable UX research (8K tok) | **x7.4** |

### Cross-repo (230 fichiers, 4 repos, 8 mars 2026)

| Repo | Fichiers | Input | Output | Ratio |
|------|----------|-------|--------|-------|
| infernal-wheel | 58 | 535K tok | 87K tok | **x6.2** |
| HSBC-algo-genetic | 115 | 194K tok | 64K tok | **x3.0** |
| shazam-piano | 45 | 107K tok | 37K tok | **x2.9** |
| MUNINN- | 12 | 19K tok | 8K tok | **x2.3** |
| **TOTAL** | **230** | **855K tok** | **196K tok** | **x4.4** |

Cout API (Haiku) : **$0.21** pour 230 fichiers.

### Benchmark factuel

- 40 questions sur texte compresse -> **37/40 correct (92%)**
- Methode : text search pur, zero API, reproductible par quiconque

## 4 Carmack moves (fondations theoriques)

| Move | Technique | Reference | Gain |
|------|-----------|-----------|------|
| #1 | Cue Distillation (L10) | Bartlett 1932 + Predictive Coding 1999 | Vire ce que le LLM sait deja |
| #2 | Rule Extraction (L11) | Kolmogorov 1965 | Factorise les patterns en regles |
| #3 | Sleep Consolidation | Wilson & McNaughton 1994 | Fusionne les branches froides |
| #4 | Spreading Activation | Collins & Loftus 1975 | Retrieval semantique via reseau |

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
  muninn.py        # Moteur principal (3775 lignes, 60 fonctions)
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

## References

- Bartlett, F.C. (1932). *Remembering*. Cambridge University Press.
- Collins, A.M. & Loftus, E.F. (1975). A spreading-activation theory of semantic processing. *Psychological Review*, 82(6).
- Kolmogorov, A.N. (1965). Three approaches to the quantitative definition of information. *Problems of Information Transmission*, 1(1).
- Wilson, M.A. & McNaughton, B.L. (1994). Reactivation of hippocampal ensemble memories during sleep. *Science*, 265(5172).
- Park, J.S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *UIST '23*.
- Jiang, H. et al. (2023). LLMLingua: Compressing Prompts for Accelerated Inference. *EMNLP 2023*.

## Licence

MIT
