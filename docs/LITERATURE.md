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

### Bio-Vectors — 22 formules, 28 papiers primaires (session 2026-03-11)

Sources pour les 11 vecteurs bio-cognitifs. On cite, on ne vole jamais.

| Vecteur | Papier | Idee cle | Application Muninn |
|---------|--------|----------|--------------------|
| V1 Pieuvre | Yekutieli et al. (2005) J Neurophysiol 94:1443 | Coupled oscillator arm control: tau_i = J*theta_ddot + C_ij coupling | Propagation locale sans coordinateur central |
| V1 Pieuvre | Olfati-Saber & Murray (2004) IEEE TAC 49:1520 | Consensus protocol: dx/dt = -L*x, rate=1/lambda_2 | Variante: Laplacien dynamique pour stabilisation recall |
| V2 Primate | Herculano-Houzel (2009) Front Hum Neurosci 3:31 | Cortical scaling: N=a*M^alpha (primates alpha~1.0) | Metrique: branches/memoire suit alpha~1.0 = efficient |
| V2 Primate | Schultz, Dayan, Montague (1997) Science 275:1593 | **TD-Learning: delta=r+gamma*V(s')-V(s)**. Dopamine = reward prediction error | **delta module poids mycelium. Recall reussi = renforce, inutile = accelere decay** |
| V3 Corbeau | Wynne (1995) J Exp Psych Anim Behav 21:166 | Transitive inference: V(A) = r(A) + beta*sum(V(j)*P(A>j)) | Fermeture transitive sur mycelium avec decay beta^distance |
| V3 Corbeau | Paz-y-Mino et al. (2004) Nature 430:778 | Transitive inference in pinyon jays social dominance | Confirms: ordered chains in birds, not just association |
| V3 Corbeau | Baker, Saxe, Tenenbaum (2009) Cognition 113:329 | **Bayesian ToM: P(g|a,s) propto P(a|g,s)*P(g), cost-based** | **Profil utilisateur: infere goal depuis queries** |
| V4 Dauphin | Rattenborg, Amlaner, Lima (2000) Neurosci Biobehav Rev 24:817 | Unihemispheric sleep: two-process switch at theta_h/theta_l | Variante Wilson & McNaughton: deux sous-systemes alternent |
| V4 Dauphin | Borbely (1982) Human Neurobiology 1:195 | Two-process model of sleep regulation (S+C) | Fondement theorique du flip-flop sleep/wake |
| V4 Dauphin | Kirkpatrick et al. (2017) PNAS 114:3521 | **EWC: L(theta)=L_B+lambda/2*sum(F_i*(theta-theta*_A)^2)** | **Fisher importance sur decay: h *= (1+F_i). Noeuds critiques protege** |
| V5 Abeille | Dockery & Keener (2001) Bull Math Biol 63:95 | Quorum sensing Hill switch: dA/dt = k_s*N*A^n/(K^n+A^n) - k_d*A | Gate: branche active seulement si assez de voisins co-actives |
| V5 Abeille | Seeley et al. (2012) Science 335:108 | **Cross-inhibition: dN_A/dt = r_A*(1-N_A/K)*N_A - beta*N_B*N_A** | **Upgrade Lotka-Volterra: deux branches en compet, meilleure gagne** |
| V6 Elephant | Richter-Levin & Akirav (2003) Brain Res Rev 43:247 | **Emotional tagging: w_new = w_old + eta*delta*E(a), E(a)=Hill function** | **Arousal multiplie poids initial encodage mycelium** |
| V6 Elephant | Frey & Morris (1997) Nature 385:533 | Synaptic tagging and capture (STC) — LTP requires protein synthesis | Fondement biologique du tagging emotionnel |
| V6 Elephant | Talmi (2013) Curr Dir Psych Sci 22:430 | **Valence-modulated decay: h(v,a) = h_0*(1+alpha_v*|v|+alpha_a*a)** | **Upgrade Ebbinghaus: h dynamique par valence et arousal** |
| V6 Elephant | McGaugh (2004) Trends Neurosci 27:456 | Emotional arousal modulates declarative memory via amygdala-hippocampus | Pipeline: arousal → amygdala → consolidation renforcee |
| V7 Fourmi | Theraulaz, Bonabeau, Deneubourg (1998) Proc R Soc B 265:327 | Response threshold: P(task)=s^n/(s^n+theta^n), emergent specialization | Branches specialisent sans allocation centrale (= sigmoid existant) |
| V7 Fourmi | Dorigo, Maniezzo, Colorni (1996) IEEE Trans SMC-B 26:29 | **ACO: tau=(1-rho)*tau+deposit; p_ij=tau^a*eta^b/sum** | **Combine historique (tau=decay) + pertinence locale (eta=TF-IDF)** |
| V8 Chauve-souris | Simmons (1989) Cognition 33:155 | Echolocation matched filter: C(tau)=integral(s*r), R=c*dt/2 | Probing actif: cross-correlation contexte vs branches |
| V8 Chauve-souris | Moss & Surlykke (2010) Front Behav Neurosci 4:33 | Natural scene probing, pulse rate adaptation | Frequence de scan augmente quand contexte change vite |
| V8 Chauve-souris | Yang, Wolpert, Lengyel (2016) Curr Opin Behav Sci 11:100 | Active sensing: a*=argmax I(X;Y|a), max info gain | Choisir la meilleure question, pas une question random |
| V9 Planaire | Shomrat & Levin (2013) J Exp Biol 216:3799 | **Bioelectric gap junction: dV/dt=-g_leak*(V-E)+g_gap*sum(V_j-V_i)+I_ion** | **Regeneration: noeuds voisins reconstruisent un noeud detruit par diffusion. 80% retention post-decapitation** |
| V9 Planaire | Levin (2012) BioEssays 34:205 | Molecular bioelectricity in developmental biology | Fondement theorique: information stockee dans patterns bioelectriques, pas juste ADN |
| V9 Planaire | Reed & Solomon (1960) JSIAM 8:300 | **Error correction: p(x)=sum(m_i*x^i), corrects (n-k)/2 errors** | **Redondance: k concepts encodes dans n noeuds, survit a la perte de (n-k)/2** |
| V10 Chien | Hutto & Gilbert (2014) ICWSM-14 | **VADER: compound=raw/sqrt(raw^2+15), rule-based sentiment** | **Capteur sentiment zero-LLM: tag [-1,+1] par interaction. Nourrit V6** |
| V10 Chien | Russell (1980) J Pers Soc Psych 39:1161 | Circumplex: E=(v,a), theta=atan2(a,v), r=sqrt(v^2+a^2) | Chaque session = point (v,a). Clustering emotionnel |
| V11 Baleine | Garland et al. (2011) Current Biology 21:687 | Song revolution SI-model: dN/dt=beta*N*(N_tot-N)/N_tot-mu*N | Variante BARE Wave: remplacement epidemique de patterns memoire |
| V11 Baleine | Boyd & Richerson (1985) Culture & Evolutionary Process, U Chicago Press | **3 biases: conformist dp=beta*p*(1-p)*(2p-1), prestige p'=sum(w_i*p_i), guided p'=p+mu*(p_opt-p)** | **Auto-organisation: conformiste + prestige + correction LLM** |

Echecs connus (13 papiers negatifs — temps economise):
- Hanassy et al. (2015) J Exp Biol — V1A 2D only, fails 3D
- LeBlanc et al. (2013) IEEE TAC — V1B Byzantine faults
- Mortensen et al. (2014) Frontiers — V2A fails cetaceans
- Howe et al. (2013) Nature — V2B dopamine ramp
- Vasconcelos (2008) Animal Behaviour — V3A simple association?
- Huszar (2018) arXiv:1801.01423 — V4B EWC >10 tasks
- Pais et al. (2013) J R Soc Interface — V5B deadlock >5 options
- Bergado et al. (2011) — V6A Yerkes-Dodson inverted-U
- Walker & Skowronski (2009) Mem & Cogn — V6B fading affect bias
- Charbonneau et al. (2013) Behav Ecol — V7A lazy ants = reserve
- Stutzle & Hoos (2000) FGCS — V7B ACO premature convergence
- Gendron et al. (2014) Psych Sci — V10B circumplex culturally biased
- Mascetti (2016) Sleep Med Rev — V4A unihemispheric coupling unknown

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

### Formules du vrai champignon — BARE Wave Model (Nature 2025, session 2026-03-11)

Le vrai mycelium pousse selon ces equations differentielles (Nature 2025, travelling-wave strategy):

```
dn/dt = alpha*n - beta*n*rho + div(J(n))     # tips: naissent, fusionnent, bougent
drho/dt = v*n                                  # filaments: les tips laissent une trace
```

Variables:
- n = densite de tips (pointes exploratrices, mm^-2)
- rho = densite d'hyphes (reseau etabli, um/mm^2)
- alpha = taux de branchement (~0.04/h = 4%/h) — EXPLORATION
- beta = taux d'anastomose/fusion (~23 um/h) — EXPLOITATION
- v = vitesse des tips (~200 um/h)
- rho_sat ~ 1000 um/mm^2 (auto-regulation: branching = anastomose)

Auto-regulation: quand rho monte (reseau dense), beta*n*rho tue les tips → exploitation.
Quand rho bas (territoire vierge), tips proliferent → exploration pure.
La psilocybine = baisser beta temporairement → tips explorent sans fusionner.

Entropie (Carhart-Harris 2014): H = -sum(p * log(p)) sur motifs de connectivite.
Psychedelique = haute entropie = plus de motifs uniques = dissolution du Default Mode Network.

Traduction Muninn:
| Biologie          | Muninn                                          |
|-------------------|-------------------------------------------------|
| tips (n)          | connexions exploratoires nouvelles               |
| hyphes (rho)      | connexions etablies (count eleve)                |
| alpha (branching)  | taux creation liens cross-cluster                |
| beta (anastomose) | taux fusion quand rejoint cluster existant        |
| rho_sat           | MAX_CONNECTIONS / densite locale                 |
| psilocybine       | baisser beta → tips explorent sans fusionner     |
| entropie H        | diversite des motifs de connectivite             |

Sources:
- Nature 2025: "A travelling-wave strategy for plant-fungal trade" (PMC11882455)
- Carhart-Harris 2014: "The entropic brain" (PMC3909994)
- Microbiology Spectrum 2017: "The Mycelium as a Network" (PMC11687498)
- IMA Fungus 2011: "Mathematical modelling of fungal growth" (PMC3317364)
- ISME 2021: "Network traits predict ecological strategies in fungi"

### Plan HUGINN — Muninn stocke, Huginn pense (session 2026-03-11)

3 briques, meme code genetique que le vrai champignon:

H1: Mode trip (psilocybine) — trip() dans mycelium.py
    Trouve clusters distants, cree connexions exploratoires faibles entre eux.
    Modele BARE Wave: alpha*n cree, beta*n*rho fusionne, auto-regulation.
    Connexions marquees "dream" (type special, decay rapide si pas renforcees).
    Se declenche dans prune() / sleep consolidation.

H2: Synthese/reve — dream() genere des insights pendant sleep
    Analyse patterns temporels cross-sessions.
    Detecte correlations ("chaque fois X puis Y"), anomalies, contradictions.
    Ecrit dans .muninn/insights.json, surface au boot comme P18.

H3: Huginn CLI — muninn.py think
    Formule les insights en langage naturel.
    "Tu parles de X depuis 5 sessions mais jamais connecte a Y"
    "Chaque fois que debug, ensuite refactor"
    "Connexion improbable trouvee: A-B-C (score 0.7)"

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
- Bowman et al.: "An Introduction to Markov State Models" (2014), Advances in Experimental Medicine and Biology 797, 7-22 (>1000 cit., Stanford)
- Hormoz et al.: "Inferring Cell-Fate Bifurcations from Transcriptomic Data" (2016), Cell Systems 3(2), 187-197 (cellules souches = non-Markov)
- Amanna, Carlson & Slifka: "Duration of Humoral Immunity to Common Viral and Vaccine Antigens" (2007), PLOS Biology 5(7), e156 (~400 cit., antibody half-lives)
- Antia et al.: "Heterogeneity and longevity of antibody memory" (2018), PLOS Biology 16(8), e2006601
- Garrido et al.: "A unifying Gamma-Mittag-Leffler kernel for decay processes" (2024), PNAS 121(37)
- Faber et al.: "First-principles GW calculations for DNA and RNA nucleobases" (2011), arXiv:1101.3738
- Simserides: "Electron or hole transfer along DNA dimers, trimers and polymers" (2014), arXiv:1402.0654

Bio-Vectors refs (session 2026-03-11):
- Yekutieli et al.: "Dynamic model of the octopus arm" (2005), J Neurophysiol 94:1443, doi:10.1152/jn.00684.2004
- Olfati-Saber & Murray: "Consensus problems in networks of agents" (2004), IEEE TAC 49:1520, doi:10.1109/TAC.2004.834113
- Herculano-Houzel: "The human brain in numbers" (2009), Front Hum Neurosci 3:31, doi:10.3389/neuro.09.031.2009
- Schultz, Dayan, Montague: "A neural substrate of prediction and reward" (1997), Science 275:1593, doi:10.1126/science.275.5306.1593
- Wynne: "Transitive inference in pigeons" (1995), J Exp Psych Anim 21:166, doi:10.1037/0097-7403.21.2.166
- Paz-y-Mino et al.: "Transitive inference in pinyon jays" (2004), Nature 430:778, doi:10.1038/nature02723
- Baker, Saxe, Tenenbaum: "Action understanding as inverse planning" (2009), Cognition 113:329, doi:10.1016/j.cognition.2009.07.005
- Rattenborg, Amlaner, Lima: "Unihemispheric sleep" (2000), Neurosci Biobehav Rev 24:817, doi:10.1016/S0149-7634(00)00039-7
- Borbely: "A two process model of sleep regulation" (1982), Human Neurobiology 1:195
- Kirkpatrick et al.: "Overcoming catastrophic forgetting" (2017), PNAS 114:3521, doi:10.1073/pnas.1611835114
- Dockery & Keener: "Mathematical model for quorum sensing" (2001), Bull Math Biol 63:95, doi:10.1006/bulm.2001.0205
- Seeley et al.: "Stop signals provide cross inhibition" (2012), Science 335:108, doi:10.1126/science.1210361
- Richter-Levin & Akirav: "Emotional tagging of memory formation" (2003), Brain Res Rev 43:247, doi:10.1016/S0165-0173(03)00174-X
- Frey & Morris: "Synaptic tagging and long-term potentiation" (1997), Nature 385:533, doi:10.1038/385533a0
- Talmi: "Enhanced emotional memory" (2013), Curr Dir Psych Sci 22:430, doi:10.1177/0963721413498893
- McGaugh: "Emotional arousal and lasting declarative memory" (2004), Trends Neurosci 27:456, doi:10.1016/j.tins.2004.04.004
- Theraulaz, Bonabeau, Deneubourg: "Response threshold reinforcement" (1998), Proc R Soc B 265:327, doi:10.1098/rspb.1998.0299
- Dorigo, Maniezzo, Colorni: "Ant system: optimization by cooperating agents" (1996), IEEE Trans SMC-B 26:29, doi:10.1109/3477.484436
- Simmons: "A view of the world through the bat's ear" (1989), Cognition 33:155, doi:10.1016/0010-0277(89)90023-X
- Moss & Surlykke: "Probing the natural scene by echolocation" (2010), Front Behav Neurosci 4:33, doi:10.3389/fnbeh.2010.00033
- Yang, Wolpert, Lengyel: "Theoretical perspectives on active sensing" (2016), Curr Opin Behav Sci 11:100, doi:10.1016/j.cobeha.2016.06.009
- Shomrat & Levin: "Long-term memory in planarians" (2013), J Exp Biol 216:3799, doi:10.1242/jeb.087809
- Levin: "Molecular bioelectricity in developmental biology" (2012), BioEssays 34:205, doi:10.1002/bies.201100136
- Reed & Solomon: "Polynomial codes over certain finite fields" (1960), JSIAM 8:300, doi:10.1137/0108018
- Hutto & Gilbert: "VADER: A parsimonious rule-based model for sentiment analysis" (2014), ICWSM-14
- Russell: "A circumplex model of affect" (1980), J Pers Soc Psych 39:1161, doi:10.1037/h0077714
- Garland et al.: "Dynamic horizontal cultural transmission of humpback whale song" (2011), Curr Biol 21:687, doi:10.1016/j.cub.2011.03.019
- Boyd & Richerson: "Culture and the Evolutionary Process" (1985), University of Chicago Press, ISBN 978-0226069333
