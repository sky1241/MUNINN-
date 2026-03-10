# SCAN MUNINN x YGGDRASIL — Analogues structurels cross-domaine
## 10 Mars 2026, Versoix

**Methode**: P4 Uzzi z-scores sur matrice 65,026x65,026 concepts (108M paires, snapshot_full.npz)
**Approche**: Extraction CSR two-phase, scoring holes.py

---

## 1. CHIFFRES CLES

| Metrique | Valeur |
|----------|--------|
| Paires totales scorees | 172,762 |
| Cross-species | 102,075 |
| Trous structurels (z < 0) | 88,546 |
| Anti-signaux P5 (z << 0, cooc ~ 0) | 128 |
| Formules actives sur 10 | 5 (F1, F2, F3, F4, F6) |
| Especes etrangeres touchees | 8 sur 9 |

### Distribution types de trous
| Type | Count | % |
|------|-------|---|
| B — Conceptuel | 294 | 59% |
| C — Perceptuel | 137 | 27% |
| A — Technique | 69 | 14% |

### Distribution patterns
| Pattern | Count |
|---------|-------|
| P4 — Open Hole | 363 |
| P5 — Anti-signal | 128 |
| P1 — Bridge | 8 |
| P2 — Dense | 1 |

---

## 2. RESULTATS PAR FORMULE

### F6 — Spectral Clustering / Laplacien (253 matches)
Eigenvalues, Markov chains, Laplacian matrix. Le plus gros morceau.

| # | P | T | Muninn concept | x Domaine etranger | Espece | z | cooc |
|---|---|---|---------------|-------------------|--------|---|------|
| 1 | P4 | A | Eigenvalues | Sample (material) | Geo/Env | -28.6 | 10.8 |
| 2 | P4 | A | Markov chain | Sample (material) | Geo/Env | -26.6 | 27.4 |
| 3 | P5 | A | Eigenvalues | Diafiltration | Physics | -22.6 | 0.015 |
| 4 | P4 | A | Eigenvalues | Power (physics) | Physics | -21.4 | 37.7 |
| 5 | P4 | A | Eigenvalues | Plasma | Physics | -22.0 | 9.6 |
| 6 | P4 | A | Markov chain | Power (physics) | Physics | -20.6 | 27.8 |
| 7 | P5 | A | Markov chain | Plasma | Physics | -21.4 | 0.26 |
| 8 | P5 | A | Eigenvalues | Demotion | Physics | -20.1 | 0.013 |
| 9 | P4 | A | Eigenvalues | Population | Medicine | -19.0 | 22.0 |
| 10 | P4 | A | Eigenvalues | Identification (bio) | Geo/Env | -18.8 | 12.7 |

### F1 — Ebbinghaus Decay 2^(-delta/h) (110 matches)
Touche les 9 especes — la plus universelle.

| # | P | T | Muninn concept | x Domaine etranger | Espece | z | cooc |
|---|---|---|---------------|-------------------|--------|---|------|
| 1 | P4 | A | Exponential function | Sample (material) | Geo/Env | -25.9 | 19.9 |
| 2 | P5 | A | Exponential function | Diafiltration | Physics | -20.8 | 0.018 |
| 3 | P4 | A | Exponential function | Plasma | Physics | -20.2 | 9.6 |
| 4 | P4 | A | Exponential function | Power (physics) | Physics | -19.0 | 44.8 |
| 5 | P5 | A | Exponential function | Triacetin | Physics | -19.5 | 0.018 |
| 6 | P5 | A | Exponential function | Large Helical Device | Physics | -19.0 | 0.008 |
| 7 | P4 | A | Exponential function | Identification (bio) | Geo/Env | -17.4 | 7.5 |
| 8 | P4 | A | Exponential function | Beam (structure) | Physics | -17.2 | 10.4 |
| 9 | P4 | A | Exponential function | Population | Medicine | -15.9 | 47.8 |
| 10 | P4 | A | Exponential function | Context (archaeology) | Humanities | -16.6 | 26.4 |

### F3 — TF-IDF + Cosine (60 matches)

| # | P | T | x Domaine etranger | Espece | z | cooc |
|---|---|---|--------------------|--------|---|------|
| 1 | P4 | A | Sample (material) | Geo/Env | -20.5 | 12.0 |
| 2 | P5 | A | Gestational period | Physics | -16.7 | 0.021 |
| 3 | P5 | A | Diafiltration | Physics | -16.5 | 0.066 |
| 4 | P4 | A | Power (physics) | Physics | -15.3 | 23.2 |
| 5 | P5 | B | Fusible alloy | Physics | -14.6 | 0.059 |
| 6 | P5 | B | Demotion (linguistics) | Physics | -14.6 | 0.024 |
| 7 | P4 | B | Population | Medicine | -13.2 | 20.8 |
| 8 | P4 | B | Context (archaeology) | Humanities | -13.0 | 18.2 |

### F2 — NCD / Compression Distance (48 matches)

| # | P | T | x Domaine etranger | Espece | z | cooc |
|---|---|---|--------------------|--------|---|------|
| 1 | P4 | A | Sample (material) | Geo/Env | -19.3 | 5.0 |
| 2 | P5 | A | Nucleofection | Physics | -15.9 | 0.27 |
| 3 | P5 | A | Plasma | Physics | -15.1 | 0.21 |
| 4 | P4 | B | Power (physics) | Physics | -14.7 | 12.5 |
| 5 | P5 | B | Population | Medicine | -13.5 | 0.86 |

### F4 — Spreading Activation (29 matches)

| # | P | T | Paire | Espece | z | cooc |
|---|---|---|-------|--------|---|------|
| 1 | P4 | B | Random walk x Sample (material) | Geo/Env | -13.3 | 9.4 |
| 2 | P5 | B | Graph theory x Sample (material) | Geo/Env | -13.2 | 2.0 |
| 3 | P4 | B | Random walk x Plasma | Physics | -10.7 | 0.76 |
| 4 | P5 | B | Graph theory x Gestational period | Physics | -10.6 | 0.007 |
| 5 | P4 | B | Random walk x Population | Medicine | -8.3 | 12.6 |

### F5, F8, F9 — PAS ASSEZ D'ACTIVITE
EMA (idx 5237), Co-occurrence (idx 8467), Predictive coding (idx 28203), Novelty detection (idx 32258) trop petits dans OpenAlex pour generer des z-scores. Sous le radar = potentiellement le plus interessant mais invisible au scan Uzzi.

---

## 3. CARTE DES ESPECES

| Espece | Matches | P5 | Type A | Type B | Type C |
|--------|---------|-----|--------|--------|--------|
| Physics/Optics | 235 | 68 | 31 | 158 | 46 |
| Geo/Environmental | 74 | 25 | 23 | 45 | 6 |
| Psychology/Business | 59 | 6 | 3 | 38 | 18 |
| Medicine | 37 | 9 | 5 | 14 | 18 |
| Humanities/PoliSci | 37 | 13 | 6 | 25 | 6 |
| MatSci/Chemistry | 26 | 3 | 0 | 8 | 18 |
| **Cell Biology** | **23** | **1** | **0** | **1** | **22** |
| Biology/Botany | 8 | 3 | 1 | 4 | 3 |

**SIGNAL**: Cell Biology = 22/23 Type C (perceptuel). Plus gros blind spot.

---

## 4. LES 25 ANTI-SIGNAUX P5

| # | F | Muninn concept | x Concept etranger | z | cooc | Espece |
|---|---|---------------|-------------------|---|------|--------|
| 1 | F6 | Eigenvalues | Diafiltration | -22.6 | 0.015 | Physics |
| 2 | F6 | Markov chain | Plasma | -21.4 | 0.256 | Physics |
| 3 | F1 | Exponential fn | Diafiltration | -20.8 | 0.018 | Physics |
| 4 | F6 | Eigenvalues | Demotion | -20.1 | 0.013 | Physics |
| 5 | F1 | Exponential fn | Triacetin | -19.5 | 0.018 | Physics |
| 6 | F6 | Markov chain | Demotion | -19.1 | 0.040 | Physics |
| 7 | F1 | Exponential fn | Large Helical Device | -19.0 | 0.008 | Physics |
| 8 | F6 | Eigenvalues | Taxonomy (biology) | -17.8 | 0.104 | Geo/Env |
| 9 | F6 | Markov chain | Taxonomy (biology) | -16.9 | 0.630 | Geo/Env |
| 10 | F6 | Eigenvalues | Government | -17.4 | 0.282 | Humanities |
| 11 | F3 | Logarithm | Gestational period | -16.7 | 0.021 | Physics |
| 12 | F6 | Eigenvalues | Taxon | -16.8 | 0.094 | Geo/Env |
| 13 | F1 | Exponential fn | Taxonomy (biology) | -16.4 | 0.013 | Geo/Env |
| 14 | F6 | Eigenvalues | Annotation | -16.3 | 1.177 | Geo/Env |
| 15 | F6 | Eigenvalues | Similitude | -16.1 | 0.237 | Geo/Env |
| 16 | F6 | Markov chain | Government | -16.4 | 2.662 | Humanities |
| 17 | F1 | Exponential fn | Government | -16.0 | 0.389 | Humanities |
| 18 | F6 | Markov chain | Taxon | -16.0 | 0.505 | Geo/Env |
| 19 | F2 | Data compression | Nucleofection | -15.9 | 0.267 | Physics |
| 20 | F1 | Exponential fn | Taxon | -15.5 | 0.189 | Geo/Env |
| 21 | F2 | Data compression | Plasma | -15.1 | 0.214 | Physics |
| 22 | F6 | Markov chain | Annotation | -15.4 | 3.667 | Geo/Env |
| 23 | F3 | Logarithm | Fusible alloy | -14.6 | 0.059 | Physics |
| 24 | F3 | Logarithm | Demotion | -14.6 | 0.024 | Physics |
| 25 | F2 | Data compression | Population | -13.5 | 0.86 | Medicine |

---

## 5. CONCEPTS MUNINN UTILISES (21 indices)

```
Exponential decay (12550), Half-life (54681), Information theory (57221),
Data compression (61733), Kolmogorov complexity (34208), Exponential smoothing (5237),
Moving average (11819), Laplacian matrix (2429), Eigenvalues/eigenvectors (9157),
Spectral clustering (934), Semantic network (62789), Co-occurrence (8467),
Cosine similarity (40678), Predictive coding (28203), Novelty detection (32258),
Forgetting (60649), Exponential function (8014), Logarithm (54757),
Graph theory (63207), Random walk (3378), Markov chain (64837)
```

---

## 6. PISTES PRIORITAIRES

### Tier 1 — Papiers a ecrire (P5 Type B, zero co-occurrence)
1. **NCD x Nucleofection** (z=-15.9) — compression appliquee a l'optimisation de sequences ADN
2. **Eigenvalues x Taxonomy** (z=-17.8) — spectral clustering pour classification biologique
3. **Exponential decay x Immunologie** — demi-vie adaptative par exposition (spacing effect immunitaire)

### Tier 2 — Blind spots perceptuels (Type C dominant)
4. **Cell Biology** (22/23 Type C) — cascades signalisation = spreading activation, degradation proteique = Ebbinghaus
5. **MatSci/Chemistry** (18/26 Type C) — cinetique reaction = decay, orbitales moleculaires = eigenvalues

### Tier 3 — Lianes secretes (P5, concepts exotiques)
6. **Eigenvalues x Diafiltration** (z=-22.6) — decomposition spectrale pour filtration membranaire
7. **Markov chain x Plasma** (z=-21.4) — transitions d'etats plasma
8. **Exponential x Large Helical Device** (z=-19.0) — decay dans confinement fusion nucleaire
9. **Logarithm x Gestational period** (z=-16.7) — courbes croissance foetale log-normales
10. **Eigenvalues x Government** (z=-17.4) — analyse spectrale reseaux de pouvoir

### Formules sous le radar (F5/F8/F9)
Scanner par glyphes (WT2) au lieu de concepts (WT1) pour trouver EMA, co-occurrence decay, novelty detection dans la litterature. Invisible au scan Uzzi faute d'activite suffisante.

---

---

## 7. SCAN GLYPHES V2 — Formules invisibles (F5/F8/F9)

**Methode**: Combinaisons de glyphes dans 833K papiers (416 chunks WT2, 17s)
**Objectif**: Trouver les formules trop petites dans OpenAlex pour le z-score Uzzi

### Chiffres

| Formule | Signature | Total | Hors CS/Math | Hors Physics |
|---------|-----------|-------|-------------|-------------|
| F5 EMA | alpha+cdot+sum | 87,464 | 8,289 | ~8K |
| F8 Decay | tau+geq | 73,812 | 6,820 | ~7K |
| F9 Novelty (membership) | sum+in+pipe | 62,260 | 7,106 | ~7K |
| F9 Novelty (indicator) | sum+double-struck-1 | **1** | 0 | 0 |

### Signal: F9 indicator (double-struck 1) = LIANE MORTE
1 seul papier sur 833K utilise le symbole Unicode double-struck-1 en LaTeX.
Le glyphe existe dans le registre mais personne ne l'ecrit sous cette forme.
Les auteurs ecrivent `\mathbf{1}` ou `\mathds{1}` ou `1_{A}` — pas le caractere Unicode.

### Domaines etrangers (hors CS/Math/Physics)

| Domaine | F5 (EMA) | F8 (Decay) | F9 (Novelty) |
|---------|----------|------------|--------------|
| Economics | 853 | 1,030 | 1,317 |
| Biology | 322 | 370 | 532 |
| Psychology | 207 | 195 | 333 |
| Medicine | 90 | 90 | 118 |
| Sociology | 39 | 28 | 57 |
| Engineering | 16 | 22 | 25 |

### Concepts NOUVEAUX (absents du 1er scan Uzzi)
~150 nouveaux concepts cross-species PAR FORMULE. Les plus gros:
- Materials science: 13K papiers F5, 10K F8 (volume massif)
- Economics: 2.6K F5, 2.5K F8, 1.5K F9 (EMA en finance = evident mais absent du scan Uzzi)
- Biology: 562 papiers F9 (scoring de nouveaute en bio)
- Geology: 1.2K chacune (constantes de temps en geosciences)

### Papiers pionniers remarquables

| Paper ID | Domaine | Formule | Concepts |
|----------|---------|---------|----------|
| physics/0012003 | Biology | F5 | Protein folding |
| cond-mat/0001117 | Economics | F5 | Local volatility, Arbitrage, Portfolio |
| nlin/0002032 | Biology | F9 | Predation, Foraging, Coevolution |
| nlin/0009025 | Biology/Env | F8 | Biodiversity, Ecology, Trophic level |
| cond-mat/0204612 | Biology | F8 | Viral quasispecies, Evolutionary biology |
| math/0602337 | Sociology | F8 | Inequality |

### Interpretation

**Biologie evolutive**: les 3 formules F5/F8/F9 sont STRUCTURELLEMENT IDENTIQUES
aux maths de la selection naturelle:
- F5 (EMA) = moyenne ponderee de fitness dans une population
- F8 (decay+seuil) = extinction d'especes + seuil de viabilite
- F9 (scoring novelty) = selection naturelle (traits positifs - traits negatifs)

**Finance**: EMA (F5) est LE pain quotidien de l'analyse technique en bourse
(moyennes mobiles 20/50/200 jours) mais ZERO lien academique avec la memoire computationnelle.
Muninn utilise exactement le meme alpha=0.3 que les traders utilisent pour lisser les cours.

---

## 8. SYNTHESE FINALE — 3 couches de recherche

### Couche 1: Scan Uzzi (concepts, 172K paires)
- 128 anti-signaux P5, 363 trous P4
- Cell Biology: 22/23 Type C (plus gros blind spot)
- F6 Spectral: 253 matches (couteau suisse)
- F1 Ebbinghaus: 110 matches (plus universel)

### Couche 2: Recherche web (10 pistes, 80 sources)
- **Ebbinghaus x Immunologie**: JACKPOT — tous les ingredients existent, pas de synthese formelle
- **Spreading activation x Cell signaling**: Nature 2018 dit "emergent memory"
- **Markov x Plasma**: z=-21.4 confirme, quasi-vide

### Couche 3: Scan glyphes (833K papiers, F5/F8/F9)
- 150+ nouveaux concepts invisibles au scan Uzzi
- Bio evolutive utilise les 3 formules sous d'autres noms
- Finance/EMA: pont evident mais academiquement absent

### TOP 5 TROUS ACTIONABLES

| # | Trou | Type | Evidence | Action |
|---|------|------|----------|--------|
| 1 | Ebbinghaus x Immunologie | B | PNAS+Science+JImmunol, z=-15.9 | Papier: formule unifiee |
| 2 | Spreading activation x Cell Bio | C | Nature 2018, 22/23 Type C Ygg | Papier: pont Collins&Loftus |
| 3 | NCD x Bio moleculaire | C | BMC 2007, ACM 2024, z=-15.9 | Creuser nucleofection |
| 4 | EMA x Memoire computationnelle | B | 853 papers eco, 0 lien memoire | Pont finance x Muninn |
| 5 | Decay+seuil x Ecologie | B | nlin/0009025, z=-17.8 | Pont mycelium x biodiversite |

---

*3 couches. 172K paires + 80 sources web + 833K papiers glyphes.*
*Top signal: Ebbinghaus x Immunologie — le papier que personne n'a ecrit.*
