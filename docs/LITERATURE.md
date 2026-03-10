# Muninn — Etat de l'art compression memoire LLM

## Constraint
Muninn ne peut PAS fine-tuner le modele. On controle uniquement le texte
qui entre dans la fenetre de contexte. Seules les techniques text-level comptent.

## Papiers analyses

### Directement applicables

| Papier | Idee cle | Ratio | Ce qu'on vole |
|--------|----------|-------|---------------|
| MemGPT (Packer 2023) | LLM comme OS, memoire virtuelle paginee | N/A (paging) | Self-directed paging, tiered memory |
| MemWalker (Chen 2023) | Arbre de resumes, navigation interactive | N/A (tree nav) | Valide notre arbre L-system + pointeurs |
| LLMLingua-2 (Pan 2024) | Filtrage par self-information, compression prompt | 2-5x | Garder high-entropy, virer predictable |
| Selective Context (Li 2023) | Self-information = critere de compression | Variable | Strip boilerplate, keep numbers/noms |

### Inspirations (model-level mais idees volables)

| Papier | Idee cle | Ratio | Technique adaptable |
|--------|----------|-------|---------------------|
| Compressive Transformers (Rae 2020) | Memoire multi-granularite | 2-8x | Recent=detail, ancien=compresse |
| Gisting (Mu 2023) | Prompts comprimes en gist tokens | 26x | Principe du bottleneck |
| AutoCompressors (Chevalier 2023) | Compression recursive segmentee | N/A | Compression context-aware (pas redondant) |
| ICAE (Ge 2024) | Autoencoder in-context | 4x | Valide notre cible 3-4x |
| COCOM (Rau 2025) | Taux variable par importance | 5.69x speedup | Root 1.5x, branch 3x, leaf 6x |

## 5 techniques a integrer dans Muninn

1. **Compression conditionnelle a la query** — quand on charge une branche pour
   "architecture", ultra-compresser les infos "bugs" (LongLLMLingua)

2. **Compression variable par temperature** — root peu compresse (1.5x),
   branches moyennement (3x), feuilles froides fort (6x) (COCOM, Compressive)

3. **Self-information filtering** — garder nombres, dates, noms propres, metriques.
   Virer verbes, articles, connecteurs (Selective Context, LLMLingua)

4. **Compression recursive context-aware** — compresser noeud B en sachant
   ce que noeud A contient deja pour eviter redondance (AutoCompressors)

5. **Log de navigation** — tracker les chemins parcourus dans l'arbre pour
   feeder R4 promotion/elagage (MemWalker)

### Nouveaux papiers 2025-2026 (decouverts session 2026-03-06)

| Papier | Idee cle | Ratio | Pertinence Muninn |
|--------|----------|-------|-------------------|
| MemOS (Li 2025) | Memory OS 3 couches: API/scheduling/storage | N/A | Architecture proche — mais top-down corporate, pas bottom-up boucher |
| MemoryOS (EMNLP 2025 Oral) | OS memoire pour agents personnalises | N/A | Persistent memory + user profiles |
| KVzip (NeurIPS 2025 Oral, top 0.35%) | Compression KV cache 3-4x, query-agnostic | 3-4x | Bas niveau (KV cache), nous = haut niveau (semantique) |
| Mem0 (commercial) | "Memory layer for AI apps" | N/A | Produit commercial, pas open-research |
| Word2Vec (Mikolov 2013) | Co-occurrence = meaning, vectors from context | N/A | FONDATION du mycelium — mots qui co-apparaissent = sens lie |
| GloVe (Pennington 2014) | Global vectors from co-occurrence matrix | N/A | Matrice co-occurrence -> embedding. Notre mycelium = GloVe artisanal |
| LLM-Codebook (2025) | Codebooks appris > codebooks manuels | Extreme | Confirme: codebook statique (CODEBOOK.json) est sous-optimal |
| Huff-LLM (2025) | Huffman sur poids LLM end-to-end | N/A | Modele-level, pas applicable directement |

### Concepts fondamentaux empruntes

| Concept | Source | Application Muninn |
|---------|--------|-------------------|
| Co-occurrence = sens | Word2Vec, GloVe | Le mycelium tracke les co-occurrences pour fusionner les concepts |
| Gulf of execution/evaluation | Norman (1988) | Les chirurgiens construisent pour des chirurgiens, pas pour des bouchers |
| Layered memory hierarchy | MemOS | Root (working) / branches (long-term) / leaves (cold archive) |
| Query-agnostic compression | KVzip | Le mycelium compresse AVANT de savoir la query (offline) |
| Living codebook | LLM-Codebook | Codebooks appris > statiques. Notre mycelium APPREND par co-occurrence |

### Outils open-source concurrents (decouverts session 2026-03-06 #2)

| Outil | Ce qu'il fait | Ratio | Utilisable ? |
|-------|-------------|-------|-------------|
| Claude-Mem (21K stars) | Capture tool calls, compresse via Claude API, SQLite + FTS | x10 | OUI — pip install, hooks Claude Code |
| Letta Code (ex-MemGPT) | Memory-first agent, git-backed markdown, subagents | N/A | OUI — agent complet (pas une brique) |
| PCToolkit (IJCAI 2025) | API unifiee: 5 compresseurs, 10 datasets, benchmark | N/A | OUI — pip install, benchmark |
| ACON (Oct 2025) | Compression guidelines optimisees, gradient-free | -26-54% | OUI — zero GPU, closed-source compatible |

Refs additionnelles:
- Claude-Mem: github.com/thedotmack/claude-mem
- Letta Code: github.com/letta-ai/letta-code
- Letta Context Repos: letta.com/blog/context-repositories
- PCToolkit: github.com/3DAgentWorld/Toolkit-for-Prompt-Compression (IJCAI 2025)
- ACON: arxiv.org/abs/2510.00615

### Carmack Move #5: Spaced Repetition (Ebbinghaus 1885 / Settles 2016)

| Papier | Idee cle | Application Muninn |
|--------|----------|--------------------|
| Ebbinghaus (1885) | Forgetting curve: memory decays over time unless rehearsed | Branch memory lifecycle — stability grows with each boot load |
| Murdock (1960) | Exponential approximation: R = e^(-t/S) | Simpler model for branch recall probability |
| Pimsleur (1967) | Graduated-interval recall schedule | Rehearsal slots at boot for branches near forgetting threshold |
| Leitner (1972) | Box system: correct=advance, wrong=return | Loaded branches gain stability, unused branches decay |
| Settles & Meeder (2016) | Half-life regression: p = 2^(-delta/h), trained on 13M Duolingo traces | Our formula — h doubles with each review, branch-level tracking |

Key: `p = 2^(-delta / h)` where delta = days since last access, h = half-life (doubles with each load at boot). Branch dies when p < 0.05.

### Recherche militaire/defense — cognition et memoire (decouverts session 2026-03-10)

| Papier | Financeur | Idee cle | Application Muninn |
|--------|-----------|----------|-------------------|
| ACT-R (Anderson 1993) | ONR + AFOSR | Activation memoire = recence + frequence + spreading. Equation base-level: B = ln(sum(t_j^(-d))) | Remplace Ebbinghaus simple — prend en compte TOUT l'historique d'acces, pas juste le dernier |
| Endsley SA (1995) | USAF (Chief Scientist) | 3 niveaux: Perception -> Comprehension -> Projection | boot()=L1, mycelium=L2, MANQUE L3: prediction de ce qui va etre necessaire |
| Klein RPD (1986) | Army Research Institute | Experts reconnaissent patterns (80%+), ne comparent pas options | Mycelium fusions = prototypes compiles. Manque: reconnaissance de session-type |
| Boyd OODA (1976) | USAF Colonel | Orient = phase critique, ou modeles mentaux + experience se synthetisent | Compression = accelerer l'Orient du prochain cousin |
| Soar chunking (Laird 1987) | DARPA + ONR + AFOSR | Tout apprentissage = compilation de sous-buts en regles directes | Fusions mycelium = chunking conceptuel. Manque: chunking procedural |
| CLS (McClelland 1995) | Non confirme militaire | Deux systemes: hippocampe (rapide, episodes) + neocortex (lent, patterns) | sessions.mn=hippocampe, branches=neocortex, sleep=transfert. Manque: neocortex influence l'encodage |
| Reconsolidation (Nader 2000) | NIMH + HFSP | Souvenir rappele = instable, doit etre re-stocke, peut etre modifie | Chaque boot() devrait re-evaluer/re-compresser la branche chargee |
| DARPA RAM Replay (2013) | DARPA | Consolidation memoire pendant sommeil via stimulation | Valide notre _sleep_consolidate() |
| DARPA AugCog (2001) | DARPA | Filtrage adaptatif selon charge cognitive du combattant | Valide notre pipeline L0-L10 = gestion charge cognitive |
| DARPA L2M (2017) | DARPA | Apprentissage continu sans oubli catastrophique | Valide architecture CLS: capture rapide + consolidation lente |
| DARPA KAIROS (2019) | DARPA | Schemas = templates compresses d'evenements recurrents | Nos L11 rules + fusions = schemas compiles |

### Pistes non-implementees identifiees

1. **Endsley Level 3 — Projection** : predire ce qui va etre necessaire AVANT la query
2. **Klein RPD — Reconnaissance de session-type** : "cette session ressemble a la session X"
3. **CLS — Compression context-aware** : compresser en sachant ce que l'arbre contient deja
4. **Reconsolidation — Branches mutables** : re-compresser une branche a chaque acces
5. **ACT-R base-level** : historique d'acces complet (pas juste last_access + count)
6. **Soar chunking procedural** : compiler des PROCEDURES (pas juste des concepts)
7. **Mycelium comme moteur d'inference** : generer des insights pendant le sommeil (reve)

### Pistes architecturales (brainstorm session 2026-03-10)

8. **Live memory injection** : hook Stop cherche dans la memoire a chaque reponse, injecte du contexte mid-conversation (pas juste au boot)
9. **Query-conditional compression at read time** : recompresser les branches selon la query au boot (LLMLingua, note #1 dans LITERATURE.md, jamais implemente)
10. **Synthese / reve** : pendant sleep consolidation, generer de nouvelles connexions entre concepts distants (pas juste merger des branches)
11. **Temporal patterns** : tracker les co-occurrences ACROSS sessions (pas juste within), detecter "chaque fois que X, puis Y"
12. **Metacognition** : le LLM sait ce qu'il sait et ce qu'il ne sait pas, peut demander a sa memoire

### Pistes graphe — le mycelium comme vrai reseau (session 2026-03-10)

13. **Chemins** : plus court chemin entre concepts jamais vus ensemble — decouverte de liens implicites
14. **Clusters** : iles isolees dans le graphe = silos de connaissance, zones aveugles
15. **Trous structurels** : ponts manquants entre clusters (= structural holes Yggdrasil, echelle utilisateur)
16. **Anomalies** : connexions anormalement fortes/faibles par rapport au voisinage
17. **Dynamique temporelle** : comment le graphe evolue — clusters qui grandissent vs meurent
18. **Angles morts** : "tu n'as jamais connecte X et Y, mais relies par Z"

### Pistes non explorées — a creuser

19. **Biologie de l'evolution** : selection naturelle sur branches/fusions? mutation? crossover? fitness?
20. **Direction WTF** : chercher dans domaines inattendus (physique, mycologie reelle, immunologie, thermodynamique?)
21. **Le graphe qui PENSE** : combiner Klein RPD + Endsley L3 + trous structurels = le mycelium detecte, predit, et revele les angles morts

### Huginn — le corbeau manquant (session 2026-03-10)

22. **Huginn = pensee** : Muninn stocke, Huginn pense. Le mycelium observe mais ne reflechit jamais.
    Manque: synthese, generation d'insights, "tiens c'est bizarre que..."
23. **Compression dans la mauvaise direction?** : on transforme histoires->data, mais le LLM lit des histoires.
    Les decisions en narratif ("on est passe a PostgreSQL parce qu'ACID") > en data ("D>MongoDB->PostgreSQL|ACID")
24. **Modele utilisateur** : on se souvient du projet, pas du codeur. Zero profil Sky.
    Patterns de communication, preferences, facon de penser, signaux ("sa me gratte" = breakthrough)

### Mode trip — psilocybine du mycelium (session 2026-03-10)

25. **Carhart-Harris 2012-2014** (Imperial College) : psilocybine dissout le Default Mode Network,
    augmente entropie neurale, cree connexions entre zones normalement isolees.
    Le mycelium est trop convergent (renforce le fort, tue le faible).
    Manque: mode divergent — laisser le reseau explorer connexions improbables entre clusters distants.
    La psilocybine pousse SUR du mycelium. C'etait dans le nom depuis le debut.

### LA BRIQUE — Liane Muninn x Yggdrasil (session 2026-03-10)

26. **Mycelium = ce que TU penses** (tes concepts, connexions, angles morts)
    **Yggdrasil = ce que LE MONDE sait** (348M papiers, 65K concepts, trous structurels)
    Branche les deux: le mycelium revele les trous dans TA tete, Yggdrasil trouve
    ce qui REMPLIT ces trous dans la litterature mondiale. Pas un bibliothecaire — un trip guide.

27. **Formules LaTeX → glyphes Yggdrasil** : les equations de Muninn (p=2^(-delta/h),
    NCD, TF-IDF, spreading activation) injectees dans Yggdrasil comme glyphes.
    Yggdrasil trouve des papiers avec les MEMES structures mathematiques dans des
    domaines completement differents. Recherche par FORME, pas par mot.
    L'espace de recherche n'est pas "papers about memory" — c'est "papers with same math."
    Deux domaines sans rapport qui utilisent la meme equation = connexion WTF invisible aux mots-cles.

### Scan cross-domaine — 7 isomorphismes confirmes (session 2026-03-10)

Scan Yggdrasil (172K paires Uzzi, 833K papers glyphes) + web (80 sources):
les formules de Muninn existent IDENTIQUES dans des domaines etrangers.
Detail: docs/FORMULES_ETRANGERES.md (30 eq LaTeX, 60+ vars mappees).

| Muninn | Domaine etranger | Score | Source | Actionable? |
|--------|-----------------|-------|--------|-------------|
| F3 TF-IDF | Replicateur-mutateur (bio evo) | 19/20 | cond-mat/0004072 | Validation theorique |
| F8 Decay+cooc | Lotka-Volterra (ecologie) | 19/20 | nlin/0009025 | Code: ajouter saturation beta*N^2 |
| F3 TF-IDF | Entropie AA (biochimie) | 19/20 | physics/0012003 | Validation theorique |
| F4+F8 | Quasispecies sigmoid (evolution) | ISOMORPHE | cond-mat/0202047 | Code: sigmoid sur spreading |
| F1 Ebbinghaus | Affinity maturation (immunologie) | 18/20 | PNAS+Science 2022 | PAPIER a ecrire |
| F5 EMA | EWMA finance | 18/20 | standard | Code: alpha adaptatif GARCH |
| F1 Ebbinghaus | Arbesman demi-vie faits | 17/20 | Arbesman 2012 | Validation theorique |

3 ameliorations code inspirees des isomorphismes:
1. **GARCH sur F5**: alpha adaptatif selon volatilite des feedbacks (Bollerslev 1986)
2. **Sigmoid sur F4**: seuil non-lineaire dans spreading activation (cond-mat/0202047)
3. **Saturation sur F8**: terme beta*N^2 (carrying capacity) dans decay mycelium (nlin/0009025)

128 anti-signaux P5 = ponts que personne n'a pris entre Muninn et 8 domaines scientifiques.
22/23 Type C en Cell Biology = plus gros blind spot.

## Ce qui est unique a Muninn (pas dans la litterature)

- **Mycelium vivant** — codebook qui POUSSE par co-occurrence, decay biologique.
  Inspire de Word2Vec/GloVe mais a l'echelle d'un utilisateur, pas d'un corpus.
- **L-system fractal** — memes regles a chaque niveau d'arbre. Novel.
- **Approche boucher** — construit depuis le cote utilisateur non-expert,
  pas depuis le cote chercheur. Le probleme est invisible aux chirurgiens.
- **Zero acces modele** — pur fichier texte, pas de fine-tuning, pas de KV cache.
  Fonctionne sur n'importe quel LLM, n'importe quel provider.
- **BPE-native output** — compresse en anglais compact que le tokenizer lit nativement.
  Pas de codebook lookup, pas de sinogrammes, zero overhead de traduction.

## Refs
- MemGPT: arxiv.org/abs/2310.08560
- MemWalker: arxiv.org/abs/2310.05029
- LLMLingua-2: arxiv.org/abs/2403.12968
- Selective Context: arxiv.org/abs/2304.12102
- Compressive Transformers: arxiv.org/abs/1911.05507
- Gisting: arxiv.org/abs/2304.08467
- AutoCompressors: arxiv.org/abs/2305.14788
- ICAE: arxiv.org/abs/2307.06945
- COCOM: arxiv.org/abs/2407.09252
- MemOS: arxiv.org/abs/2507.03724
- MemoryOS: github.com/BAI-LAB/MemoryOS
- KVzip: arxiv.org/abs/2511.01815
- Mem0: mem0.ai
- Word2Vec: arxiv.org/abs/1301.3781
- GloVe: nlp.stanford.edu/projects/glove/
- Norman: "The Design of Everyday Things" (1988)
- Ebbinghaus: "Uber das Gedachtnis" (1885), Leipzig: Duncker & Humblot
- Murdock: "The distinctiveness of stimuli" (1960), Psychological Review 67(1)
- Pimsleur: "A memory schedule" (1967), Modern Language Journal 51(2), 73-75
- Leitner: "So lernt man lernen" (1972), Verlag Herder
- Settles & Meeder: "A Trainable Spaced Repetition Model for Language Learning" (2016), ACL 2016, 1848-1858
- Anderson: "Rules of the Mind" (1993), Erlbaum; also "An Integrated Theory of the Mind" (2004), Psychological Review 111(4)
- Endsley: "Toward a Theory of Situation Awareness in Dynamic Systems" (1995), Human Factors 37(1), 32-64
- Klein, Calderwood & Clinton-Cirocco: "Rapid Decision Making on the Fire Ground" (1986), Human Factors Society 30th; reprint JCEDM 4(3), 2010
- Boyd: "Destruction and Creation" (1976), unpublished essay; "A Discourse on Winning and Losing" (1987), posthumous
- Laird, Newell & Rosenbloom: "SOAR: An Architecture for General Intelligence" (1987), Artificial Intelligence 33(1), 1-64
- McClelland, McNaughton & O'Reilly: "Why There Are Complementary Learning Systems" (1995), Psychological Review 102(3), 419-457
- Nader, Schafe & LeDoux: "Fear Memories Require Protein Synthesis for Reconsolidation" (2000), Nature 406, 722-726
- Uzzi et al.: "Atypical Combinations and Scientific Impact" (2013), Science 342(6157), 468-472
- Price: "Selection and Covariance" (1970), Nature 227, 520-521
- Huang & Ferrell: "Ultrasensitivity in the Mitogen-Activated Protein Kinase Cascade" (1996), PNAS 93, 10078-10083
- Bollerslev: "Generalized Autoregressive Conditional Heteroskedasticity" (1986), J Econometrics 31, 307-327
- Shaffer: "Minimum Population Sizes for Species Conservation" (1981), BioScience 31(2), 131-134
- Arbesman: "The Half-Life of Facts" (2012), Current, New York
- Carhart-Harris et al.: "Neural correlates of the psychedelic state" (2012), PNAS 109(6), 2138-2143
