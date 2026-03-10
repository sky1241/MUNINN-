# Mission Yggdrasil #3 — Ramene les FORMULES des domaines etrangers

## Contexte

On a fait 2 scans:
- Scan 1 (Uzzi): 172K paires, 128 anti-signaux P5, carte des trous
- Scan 2 (Glyphes): 833K papiers, F5/F8/F9 retrouvees en bio/eco/finance

On SAIT ou sont les trous. Maintenant on a besoin des FORMULES CONCRETES
des domaines etrangers pour que Muninn puisse les indexer et les comparer.

**La question n'est plus "ou sont les trous?" mais "quelle est l'equation
exacte de l'autre cote du trou?"**

---

## Ce qu'on veut

Pour chaque piste ci-dessous, trouve dans tes donnees (papers.json.gz, bipartite,
ou les .tex des arXiv tars dans E:/arxiv/src/) les EQUATIONS REELLES utilisees
dans les papiers pionniers. On veut du LaTeX exact, pas des descriptions en mots.

---

## PISTE 1: Immunologie — Affinity maturation

**Cote Muninn**: `p = 2^{-\Delta / h}, \quad h = 7 \cdot 2^{\min(n, 10)}`

**Ce qu'on cherche**: la formule de la maturation d'affinite des anticorps.
- Comment les immunologistes modelisent la demi-vie des anticorps?
- Est-ce que h augmente avec les boosters (expositions repetees)?
- Quelle est l'equation du spacing effect vaccinal?

**Papers a chercher dans tes tars**: mots-cles "affinity maturation" "germinal center"
"antibody half-life" "booster" dans les .tex de E:/arxiv/src/

**Format attendu**:
```
Domaine: Immunologie
Equation LaTeX:
  K_d(n) = K_0 \cdot r^{-n}  (affinite augmente avec expositions)
  t_{1/2} = t_0 \cdot f(n_{boosters})  (demi-vie adaptative?)
Source paper: arXiv ID ou reference
Isomorphisme avec Muninn F1:
  K_d(n) <-> p(delta, h)
  n_boosters <-> access_count
  K_0 <-> h_base = 7
  r <-> 2 (base de l'exponentielle)
  IDENTIQUE / SIMILAIRE / DIFFERENT (et pourquoi)
```

---

## PISTE 2: Cascades cellulaires — Spreading activation biochimique

**Cote Muninn**: `A_{neighbor} = A_{source} \cdot w_{norm} \cdot \gamma^{h}`

**Ce qu'on cherche**: l'equation des cascades de kinases (MAPK, etc.)
- Comment les biochimistes modelisent la propagation du signal?
- Est-ce qu'il y a un decay par "hop" (enzyme -> enzyme)?
- Est-ce que les poids sont normalises par noeud?

**Papers a chercher**: "MAPK cascade" "kinase phosphatase" "signal transduction"
"ODE model" dans les .tex

**Format attendu**:
```
Domaine: Biochimie cellulaire
Equation LaTeX:
  \frac{d[X^*]}{dt} = k_{cat} \cdot [E] \cdot \frac{[X]}{K_m + [X]} - k_{phos} \cdot [X^*]
  (Michaelis-Menten pour chaque etape de la cascade)
Source paper: arXiv ID
Isomorphisme avec Muninn F4:
  [E] (enzyme) <-> A_{source} (activation source)
  k_cat/K_m <-> w_{norm} (poids normalise)
  k_phos <-> gamma (decay)
  cascade sequentielle <-> hops dans le graphe
  IDENTIQUE / SIMILAIRE / DIFFERENT
```

---

## PISTE 3: Selection naturelle — Scoring de fitness (F9 analogie)

**Cote Muninn**: `novelty(l) = \sum 0.15 \cdot |matches_{novel}| - \sum 0.3 \cdot \mathbb{1}[match_{known}]`

**Ce qu'on cherche**: l'equation de fitness en biologie evolutive.
- Comment les biologistes scorent la fitness d'un organisme?
- Est-ce additif (traits positifs) - soustractif (traits negatifs)?
- Quelle est la formule de selection naturelle formelle?

**Papers a chercher**: "fitness function" "selection coefficient" "evolutionary dynamics"
"Price equation" dans les .tex

**Format attendu**:
```
Domaine: Biologie evolutive
Equation LaTeX:
  w_i = 1 + \sum_j s_j \cdot x_{ij}  (fitness additive)
  ou: \Delta\bar{z} = \text{Cov}(w, z) / \bar{w}  (equation de Price)
Source paper: arXiv ID
Isomorphisme avec Muninn F9:
  s_j (coefficient de selection) <-> 0.15 / -0.3 (poids positif/negatif)
  x_{ij} (presence du trait) <-> matches(pattern, line)
  w_i (fitness) <-> novelty(line)
  IDENTIQUE / SIMILAIRE / DIFFERENT
```

---

## PISTE 4: Finance — EMA et moyennes mobiles (F5 analogie)

**Cote Muninn**: `S_t = 0.3 \cdot x_t + 0.7 \cdot S_{t-1}`

**Ce qu'on cherche**: l'equation exacte de l'EMA en finance quantitative.
- Alpha = 2/(N+1) ou alpha est choisi librement?
- Est-ce utilise pour du scoring (pas juste du lissage)?
- Y a-t-il des EMA adaptatives (alpha variable)?

**Papers a chercher**: "exponential moving average" "adaptive" "EWMA"
"volatility" dans les .tex de finance/econometrie

**Format attendu**:
```
Domaine: Finance quantitative
Equation LaTeX:
  EMA_t = \alpha \cdot P_t + (1 - \alpha) \cdot EMA_{t-1}
  \alpha = 2 / (N + 1)
  ou: \alpha_t = f(\sigma_t)  (adaptatif?)
Source paper: arXiv ID
Isomorphisme avec Muninn F5:
  P_t (prix) <-> x_t (feedback utilite de la branche)
  EMA_t <-> S_t (usefulness score)
  alpha = 0.3 Muninn <-> alpha = 2/(N+1) finance
  IDENTIQUE / SIMILAIRE / DIFFERENT
```

---

## PISTE 5: Ecologie — Decay d'especes + seuil de viabilite (F8 analogie)

**Cote Muninn**: `w_{t+1} = w_t \cdot 2^{-1/\tau}, \quad \text{immortel si } |Z| \geq 3`

**Ce qu'on cherche**: l'equation de l'extinction d'especes avec seuil de viabilite.
- Comment les ecologistes modelisent le decline d'une population?
- Y a-t-il un seuil minimum de viabilite (MVP = minimum viable population)?
- Le decay est-il exponentiel?

**Papers a chercher**: "population viability analysis" "minimum viable population"
"extinction threshold" "species decay" dans les .tex

**Format attendu**:
```
Domaine: Ecologie des populations
Equation LaTeX:
  N_{t+1} = N_t \cdot e^{r(1 - N_t/K)}  (logistique)
  Extinction si N_t < N_{MVP}  (seuil de viabilite)
Source paper: arXiv ID
Isomorphisme avec Muninn F8:
  N_t <-> w_t (poids de la connexion)
  r <-> -1/tau (taux de decay)
  K <-> ? (carrying capacity = pas d'equivalent direct?)
  N_MVP <-> seuil de 3 zones (immortalite)
  IDENTIQUE / SIMILAIRE / DIFFERENT
```

---

## PISTE 6: Degradation proteique — Demi-vie avec marquage (F1 + tagging)

**Cote Muninn**: `p = 2^{-\Delta/h}` + tags B>/E>/F>/D>/A> (priorite de survie)

**Ce qu'on cherche**: l'equation de la degradation proteique par le proteasome.
- Quelle est la cinetique de degradation (premier ordre? Michaelis-Menten?)
- Comment le marquage ubiquitine affecte la demi-vie?
- Y a-t-il des proteines "immortelles" (marquage inverse)?

**Papers a chercher**: "ubiquitin proteasome" "protein half-life" "degradation kinetics"
dans les .tex

---

## PISTE 7: Demi-vie des connaissances — Arbesman (validation F1)

**Cote Muninn**: meme F1

**Ce qu'on cherche**: la formule exacte d'Arbesman pour la demi-vie des faits scientifiques.
- h varie par discipline (physique ~10 ans, urologie ~7.1 ans)
- Est-ce que h est adaptatif (change avec le temps)?

**Papers a chercher**: "knowledge half-life" "obsolescence" "scientometrics"

---

## Comment chercher

Tu as 2449 tars arXiv dans E:/arxiv/src/. Chaque tar contient des .tex.

Option A (rapide): cherche dans les papers.json.gz des wt2_chunks les paper_ids
des pionniers qu'on a deja trouves, puis va lire leurs .tex dans les tars.

Option B (exhaustif): grep les .tex pour les mots-cles de chaque piste,
extrais les environnements math ($$...$$, \[...\], equation, align),
et renvoie les equations en LaTeX brut.

**On veut le LaTeX EXACT des papiers, pas une paraphrase.**

---

## Format de sortie global

Pour chaque piste, un bloc comme ca:

```
=== PISTE N: [nom] ===
Cote Muninn: [formule F1/F4/F5/F8/F9]
Cote domaine etranger:
  Equation 1 (source: arXiv:XXXX.XXXXX):
    $$ formule LaTeX exacte $$
  Equation 2 (source: arXiv:YYYY.YYYYY):
    $$ formule LaTeX exacte $$
Mapping de variables:
  variable_muninn <-> variable_domaine
Verdict: ISOMORPHE / SIMILAIRE / DIFFERENT
  Si SIMILAIRE: quelle est la difference structurelle?
  Si DIFFERENT: pourquoi le scan Ygg les a quand meme connectes?
```

C'est la derniere piece du puzzle. On a la carte, on a les trous,
maintenant on veut les equations de l'autre cote pour les comparer.

Bonne chasse cousin — cette fois c'est du LaTeX qu'on veut, pas des z-scores.
