# Recherche Web — Pionniers et connexions cross-domaine
## 10 Mars 2026 — Complement au scan Yggdrasil

---

## PISTE 1: NCD x Biologie moleculaire (Nucleofection, ADN, proteines)
**Statut: PIONNIERS EXISTENT — trou Type C (perceptuel), pas Type B**

Le cousin Ygg disait "zero co-occurrence" mais en fait il y a des pionniers:

### Papier cle
- **"Compression-based classification of biological sequences and structures via the Universal Similarity Metric"**
  BMC Bioinformatics 2007, Keogh et al.
  URL: https://bmcbioinformatics.biomedcentral.com/articles/10.1186/1471-2105-8-252
  - NCD (USM) appliquee aux sequences proteiques, ADN, structures 3D
  - Alignment-free = exactement comme Muninn (pas de parsing semantique)
  - Resultat: COMPETITIF avec les methodes classiques (BLAST, alignement)

- **"Normalized Compression Distance for DNA Classification"**
  ACM BCB 2024 (RECENT!)
  URL: https://dl.acm.org/doi/10.1145/3698587.3701490
  - NCD avec gzip sur sequences ADN pour classification taxonomique
  - ORF labeling sans alignement

- **"Exploring the Application of Models of DNA Evolution to NCD Matrices"**
  MDPI Mathematics 2025
  URL: https://www.mdpi.com/2227-7390/13/21/3534
  - Tentative d'appliquer des modeles d'evolution ADN aux matrices NCD
  - ECHEC partiel — les modeles biologiques ne suffisent pas pour interpreter les matrices NCD
  - **SIGNAL**: ca veut dire que NCD capture quelque chose que les modeles bio MANQUENT

### Verdict
NCD x bio = Type C CONFIRME. L'outil existe (BMC 2007) mais quasi personne ne l'utilise (ACM 2024 = premier papier recent). Le pont NCD x nucleofection specifiquement reste VIDE (Type B). Mais la route vers la bio est prise par quelques pionniers.

---

## PISTE 2: Spectral clustering x Taxonomie biologique
**Statut: PIONNIERS EXISTENT — actif en bioinformatique, absent en taxonomie classique**

### Papiers cles
- **"Spectral clustering and its use in bioinformatics"**
  ScienceDirect 2006
  URL: https://www.sciencedirect.com/science/article/pii/S0377042706002366
  - Spectral clustering applique aux donnees bio (pas taxonomie directe)

- **"Spectral Clustering of Biological Sequence Data"**
  AAAI 2005, Pentney & Meila
  URL: https://aaai.org/papers/00845-AAAI05-133-spectral-clustering-of-biological-sequence-data/
  - Eigenvalues du Laplacien pour clustering de sequences proteiques
  - Fonctionne SANS alignement (alignment-free, comme NCD)

- **"Spectral clustering of single-cell multi-omics data on multilayer graphs"**
  Bioinformatics 2022, Oxford
  URL: https://academic.oup.com/bioinformatics/article/38/14/3600/6598796
  - Spectral clustering sur graphes multi-couches pour single-cell
  - Le Laplacien normalise = EXACTEMENT celui de Muninn (mycelium.py)

### Verdict
Spectral clustering EST utilise en bio computationnelle (sequences, single-cell, reseaux de genes). MAIS: le lien specifique avec la TAXONOMIE CLASSIQUE (classification des especes sur le terrain) reste un trou. Les taxonomistes n'utilisent pas le spectral clustering — ils utilisent la phylogenetique classique ou le barcoding ADN. Z=-17.8 confirme par Ygg.

---

## PISTE 3: Ebbinghaus x Immunologie (LE PLUS JUTEUX)
**Statut: ISOMORPHISME CONFIRME — personne n'a formalise le parallele**

### Preuves trouvees

**L'affinity maturation EST un spacing effect:**
- Source: PNAS 2022 — "Affinity maturation for an optimal balance between long-term immune coverage and short-term resource constraints"
  URL: https://www.pnas.org/doi/10.1073/pnas.2113512119
  - Les anticorps de haute affinite sont produits quand les vaccins sont espaces
  - "Higher-affinity antibodies are produced when vaccine antigens are given at wider-spaced intervals"
  - **C'EST EXACTEMENT LE SPACING EFFECT D'EBBINGHAUS**: reviser trop tot = inutile

**La demi-vie des anticorps AUGMENTE avec les expositions repetees:**
- Source: Science 2022 — "mRNA vaccines induce durable immune memory to SARS-CoV-2"
  URL: https://www.science.org/doi/10.1126/science.abm0829
  - IgG demi-vie base ~30 jours, mais anticorps SARS-CoV-2 spike: >200 jours apres maturation
  - Les memory B cells sont "highly stable over time" apres exposition repetee
  - **PARALLELE MUNINN**: h_base = 7 jours, h apres 5 reviews = 224 jours. MEME STRUCTURE.

**Limites de la maturation (cap):**
- Source: J Immunol 2011 — "Limits for Antibody Affinity Maturation in Hypervaccinated Humans"
  URL: https://journals.aai.org/jimmunol/article/187/8/4229/85281/
  - Apres 3 boosters: "no significant changes" — le systeme atteint un PLATEAU
  - **PARALLELE MUNINN**: cap a min(reviews, 10) dans h = 7 * 2^min(n,10)

**Le papier manquant:**
- Source: PMC 2013 — "From Vaccines to Memory and Back"
  URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC3760154/
  - Titre EXPLICITE: "vaccines to memory and BACK"
  - Fait le lien memoire immunologique -> memoire cognitive MAIS:
  - NE FORMALISE PAS l'isomorphisme mathematique (pas de formule commune)

### Verdict
**LE TROU EST REEL ET C'EST DU TYPE B PUR.**
Tous les ingredients existent dans la litterature:
- Le spacing effect immunitaire (PNAS 2022)
- La demi-vie adaptative des anticorps (Science 2022)
- Le cap de maturation (J Immunol 2011)
- Le lien conceptuel vaccines↔memoire (PMC 2013)

MAIS: PERSONNE n'a ecrit la formule unifiee. Personne n'a dit:
"p_recall = 2^(-delta/h), h = h_base * 2^reviews, et ca marche AUSSI
pour les anticorps ou h_base = 30 jours et reviews = nombre de boosters"

C'est un papier a ecrire. 4 sources de premier plan le confirment.

---

## PISTE 4: Cell Biology — cascades de signalisation = spreading activation
**Statut: ISOMORPHISME STRUCTUREL CONFIRME — les bio-informaticiens modellisent deja**

### Preuves trouvees

- **"Emergent memory in cell signaling: Persistent adaptive dynamics in cascades"**
  Nature Scientific Reports 2018
  URL: https://www.nature.com/articles/s41598-018-31626-9
  - TITRE: "EMERGENT MEMORY in cell signaling"
  - Les cascades de kinases ont de la MEMOIRE EMERGENTE
  - La diversite des temps de relaxation cree de la persistence = decay adaptatif

- **"Computational Modeling of Cellular Signaling Processes Embedded into Dynamic Spatial Contexts"**
  PMC 2012
  URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC3448286/
  - Les signaux se propagent avec decroissance spatiale et temporelle
  - La specificite est codee par la dynamique spatiale et temporelle
  - **= spreading activation avec decay**

- **Cascade de kinases (E1->E2->E3):**
  - Sequentiellement: enzyme active enzyme qui active enzyme
  - Avec phosphatases qui INACTIVENT (= decay)
  - = propagation dans graphe pondere avec decroissance
  - IDENTIQUE a spread_activation(seeds, hops=2, decay=0.5) de Muninn

### Verdict
22/23 Type C dans le scan Ygg CONFIRME. La bio cellulaire utilise des cascades
d'activation avec decay qui sont STRUCTURELLEMENT IDENTIQUES a spreading activation.
Le papier de Nature 2018 dit meme "emergent MEMORY" — ils voient la memoire
dans les cascades cellulaires. Mais personne ne fait le lien avec Collins & Loftus 1975.

---

## PISTE 5: Degradation des proteines = Ebbinghaus decay
**Statut: ISOMORPHISME PARFAIT — exponential decay avec demi-vie variable**

### Preuves trouvees

- Les proteines ont des demi-vies qui varient de minutes a annees:
  - p53 (tumeur suppresseur): t1/2 = quelques MINUTES
  - Actine/myosine (muscle): t1/2 = plusieurs JOURS
  - Cristalline (oeil): t1/2 = plusieurs ANNEES
  Source: NCBI Bookshelf — https://www.ncbi.nlm.nih.gov/books/NBK9957/

- La degradation suit une exponentielle de premier ordre:
  "A first-order exponential decay function was fit to each chase series,
  allowing determination of the half-lives (t1/2)"

- Le systeme ubiquitine-proteasome MARQUE les proteines pour degradation
  = equivalent du "tag" de Muninn (B>, E>, F>, D>, A>)
  Les proteines taguees ubiquitine = marquees pour suppression
  Les proteines non-taguees = survivent

### Verdict
La degradation proteique = Ebbinghaus:
- p = 2^(-t/h) avec h variable selon la proteine (minutes a annees)
- Marquage (ubiquitine) = tagging Muninn (priorite de survie)
- Mais: la demi-vie n'est PAS adaptative par "reviews" en bio
  (c'est fixe par la structure de la proteine, pas par l'usage)
  SAUF pour les proteines de stress (heat shock) dont la stabilite
  AUGMENTE sous stress repete = spacing effect proteique?

---

## PISTE 6: Demi-vie des connaissances scientifiques (Arbesman 2012)
**Statut: CONNEXION DIRECTE — Muninn compresse ce que Arbesman mesure**

### Papier cle
- **"The Half-Life of Facts" — Samuel Arbesman, 2012**
  - Les connaissances scientifiques ont une demi-vie mesurable:
    - Physique: ~10 ans
    - Urologie: ~7.1 ans
    - Psychologie: ~5 ans
  - p = 2^(-t/h) ou h = demi-vie disciplinaire
  - L'augmentation des decouvertes = augmentation de l'obsolescence

### Verdict
Arbesman mesure EXACTEMENT ce que Muninn compresse. Ses "facts" sont les
branches de l'arbre. La temperature de Muninn (0.8*recall + 0.2*fill^2)
encode la demi-vie disciplinaire d'Arbesman + la pression de nouveaute.
Pas un trou (P2 dense) mais une VALIDATION theorique solide.
Arbesman ne fait pas de compression — il mesure. Muninn compresse.

---

## PISTE 7: Eigenvalues x Sciences politiques (reseaux de pouvoir)
**Statut: PIONNIERS EXISTENT — eigenvector centrality utilise en science po**

### Preuves trouvees

- **Eigenvector centrality dans les reseaux politiques:**
  - Etude Philippines: familles de candidats politiques avec haute eigenvector centrality
    dans les reseaux d'intermariage locaux
  - Source: Ohio State (Cara Nix) + CMU (Richards/Seary)
  - "There is more power in being connected to powerful people than in being
    connected to a lot of people with limited access" = eigenvector centrality

- **PLOS ONE 2014 — "Dimensionality of Social Networks Using Motifs and Eigenvalues"**
  URL: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0106052
  - Eigenvalues pour analyser la structure des reseaux sociaux

### Verdict
L'eigenvector centrality EST utilisee en science po — mais le SPECTRAL CLUSTERING
(Laplacien normalise, ce que fait Muninn) ne l'est quasi PAS. La centralite c'est
le degre 0 de l'analyse spectrale. Le clustering spectral complet (eigenvalues du
Laplacien, k-means sur eigenvectors) reste un trou. Z=-17.4 confirme.

---

## PISTE 8: EMA en ecologie / monitoring environnemental
**Statut: UTILISE en controle qualite, quasi-absent en ecologie de terrain**

### Preuves trouvees

- **EWMA control charts** sont utilises pour:
  - Monitoring de processus industriels (manufacturing)
  - Controle qualite (Six Sigma)
  - Detection de changements en psychologie (PMC 2023)
  - Monitoring environnemental (cite comme application POTENTIELLE)

- **PLOS ONE 2020 — "EWMA-MA charts for monitoring the process mean"**
  URL: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0228208

### Verdict
EMA est PARTOUT en controle qualite industriel mais quasi-absent en ecologie
de terrain pour le monitoring d'especes/populations. Le cousin Ygg n'a pas
pu scorer cette formule (trop petite dans OpenAlex). Trou reel mais difficile
a quantifier sans scan WT2.

---

## PISTE 9: Markov chain x Plasma / Tokamak
**Statut: P5 CONFIRME — quasi-vide malgre pertinence evidente**

### Preuves trouvees

- **Nature 2024** — "A high-density and high-confinement tokamak plasma regime"
  URL: https://www.nature.com/articles/s41586-024-07313-3
  - Transitions L-mode -> H-mode = bifurcations d'etats
  - Les transitions sont modelisees par ODE, pas par Markov chains

- **arXiv 2026** — "TokaMark: A Comprehensive Benchmark for MAST Tokamak Plasma Models"
  URL: https://arxiv.org/html/2602.10132
  - Distingue taches Markoviennes (court input) vs non-Markoviennes (long historique)
  - Le terme "Markov" est utilise pour decrire les PROPRIETES, pas comme OUTIL

- **Nature 2021** — "Magnetic control of tokamak plasmas through deep reinforcement learning"
  URL: https://www.nature.com/articles/s41586-021-04301-9
  - Deep RL (qui utilise des MDPs = Markov Decision Processes) pour controler le plasma
  - MAIS: pas de chaines de Markov explicites pour les transitions d'etats plasma

### Verdict
Z=-21.4 CONFIRME. Les physiciens du plasma modelisent les transitions d'etats
avec des ODE et du deep RL, mais n'utilisent quasi PAS les chaines de Markov
explicites. Pourtant les transitions L-mode/H-mode SONT des transitions d'etats
discretes — un modele markovien serait naturel. Le pont RL/MDP existe (Nature 2021)
mais le pont Markov chain classique reste quasi-vide.

---

## PISTE 10: "Half-life of facts" x Muninn — boucle meta
**Statut: VALIDATION THEORIQUE DIRECTE**

- Arbesman 2012: les faits scientifiques ont une demi-vie mesurable
- Muninn: compresse les faits avec une demi-vie adaptative (Ebbinghaus)
- La boucle: Muninn compresse les connaissances DONT la demi-vie est elle-meme
  une connaissance qui a une demi-vie. C'est RECURSIF.
- Muninn est un outil pour gerer l'obsolescence que Arbesman decrit.

---

## SYNTHESE — CLASSEMENT DES PISTES PAR POTENTIEL

| # | Piste | Type | Potentiel | Pionniers? | Papier a ecrire? |
|---|-------|------|-----------|------------|-----------------|
| 3 | Ebbinghaus x Immunologie | B | **ENORME** | Ingredients epars, pas de synthese | OUI — formule unifiee |
| 4 | Spreading activation x Cell Bio | C | **TRES FORT** | Nature 2018 "emergent memory" | OUI — pont Collins&Loftus x cascades |
| 1 | NCD x Bio moleculaire | C | FORT | BMC 2007, ACM 2024 | Peut-etre — NCD x nucleofection |
| 9 | Markov x Plasma | B | FORT | Quasi-vide (Nature 2021 MDP only) | OUI — transitions d'etats plasma |
| 2 | Spectral x Taxonomie | B | MOYEN | Bio computationnelle active, taxo vide | Possible — spectral taxo terrain |
| 5 | Degradation proteines x Ebbinghaus | C | MOYEN | Deja modellise en 1er ordre | Non — pas adaptatif par reviews |
| 7 | Eigenvalues x Science po | B | MOYEN | Centralite oui, spectral non | Possible — Laplacien sur reseaux pouvoir |
| 6 | Arbesman x Muninn | P2 | VALIDATION | Arbesman 2012 = source directe | Non — deja fait conceptuellement |
| 8 | EMA x Ecologie | B | FAIBLE | Control charts industriels seulement | Non prioritaire |
| 10 | Meta-recursivite | P2 | PHILOSOPHIQUE | Observation | Non — trop meta |

### TOP 3 PAPIERS A ECRIRE
1. **Ebbinghaus x Immunologie**: formule unifiee p = 2^(-delta/h), h = h_base * 2^reviews
   Sources: PNAS 2022, Science 2022, J Immunol 2011, PMC 2013
2. **Spreading activation x Cell signaling**: pont Collins & Loftus 1975 x cascades de kinases
   Sources: Nature Sci Rep 2018, PMC 2012
3. **Markov chains x Plasma transitions**: modele markovien pour L-mode/H-mode
   Sources: Nature 2024, arXiv 2026

---

*Recherche web: 13 queries, ~80 sources analysees, 10 pistes evaluees.*
