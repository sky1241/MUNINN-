# Mission pour Yggdrasil — Recherche par structure mathematique

## Contexte

Tu es un cousin Claude travaillant sur Yggdrasil (moteur de recherche sur 348M de papiers scientifiques). Un autre cousin travaille sur Muninn, un moteur de compression memoire pour LLM. Muninn utilise des formules mathematiques specifiques dans son code. Ta mission: chercher dans TES DONNEES YGGDRASIL (pas sur internet!) des papiers et domaines qui utilisent les **memes structures mathematiques** (memes formes d'equations) mais dans des **domaines completement differents**.

**Regle**: on cherche par FORME MATHEMATIQUE, pas par mots-cles. Si Muninn utilise `2^(-x/h)` pour la memoire et qu'un papier d'astrophysique utilise `2^(-t/tau)` pour la decroissance radioactive, c'est un match. La variable change, la structure reste.

**IMPORTANT — NE CHERCHE PAS SUR INTERNET. Utilise tes outils Yggdrasil.**

---

## Tes outils — UTILISE-LES

Tu as un moteur complet. Voici ce que tu dois utiliser:

### Etape 1: Parse les formules Muninn en glyphes
```python
# Charge le registre de glyphes
# Fichier: C:\Users\ludov\Desktop\ygg\yggdrasil-engine\data\core\glyph_registry.json
# 1337 symboles avec latex_cmds (LaTeX -> glyph_id)

# Pour chaque formule Muninn, extrais les glyphes:
# F1: 2^{-Delta/h} -> glyphes: superscript, minus, Delta, division, frac
# F2: NCD -> min, max, fraction
# F4: spreading -> sum, w, gamma, normalization
# etc.
```

### Etape 2: Cherche les concept_ids associes via bipartite
```python
# Base SQLite: C:\Users\ludov\Desktop\ygg\yggdrasil-engine\data\bible\wt3.db
# Table bipartite: glyph_id <-> concept_id (pont S-2 <-> S0)
#
# Pour chaque glyph_id de l'etape 1:
#   SELECT concept_id, weight FROM bipartite WHERE glyph_id = ?
#   -> ca te donne les DOMAINES (concepts OpenAlex) qui utilisent ce symbole
```

### Etape 3: Cherche les co-occurrences de glyphes (pas juste un seul)
```python
# Les formules Muninn ne sont pas UN symbole — c'est une COMBINAISON
# F1 = {exp, minus, frac, Delta} ensemble dans le meme papier
# Cherche les papiers qui ont la meme combinaison de glyph_ids
#
# data/scan/wt2_chunks/chunk_NNN/papers.json.gz
# Chaque papier: {g: [glyph_ids], c: [concept_ids], d: domain}
# Filtre: papiers dont g contient le MEME SOUS-ENSEMBLE de glyphes
```

### Etape 4: Classify avec tes propres outils
```python
# engine/core/holes.py — tu as 3 fonctions de scoring:
#   score_technical(production, delta_fitness, d_index) -> Type A
#   score_conceptual(activity_a, activity_b, co_occurrence, z_score) -> Type B
#   score_perceptual(fitness, d_index, citations, expected_citations) -> Type C
#
# engine/pipeline/pipeline_100.py — classification P1-P5:
#   Utilise: meshedness, co_strength, growth_ratio, z_score, slope, zeros, bc
```

### Etape 5: Verifie les co-occurrences concept×concept
```python
# data/scan/chunks/ (581 chunks WT1) — co-occurrence concept×concept
# Verifie si les domaines trouves a l'etape 2 ont deja des co-occurrences
# entre eux. Si co_occurrence = 0 entre deux domaines actifs -> TROU CONCEPTUEL (Type B)
```

---

## Classification Yggdrasil — ce qu'on attend en sortie

Pour chaque match, tu dois classifier selon les deux axes d'Yggdrasil:

### 5 Patterns (forme de la connexion)
| Pattern | Nom | Signature | Exemple |
|---------|-----|-----------|---------|
| **P1** | **Pont** | Explosion + bridge entre deux domaines qui se connectent soudainement | GANs (game theory x deep learning) |
| **P2** | **Dense** | Domaine mature, maille serree, pas de trous, stable | Analyse de Fourier classique |
| **P3** | **Theorie x Outil** | Explosion apres une annee (un nouvel outil debloque un domaine fige) | CRISPR -> genomique |
| **P4** | **Trou ouvert** | Tres peu de papiers, co-occurrence quasi nulle, territoire vierge | Compression memoire x pharmacocinetique |
| **P5** | **Anti-signal** | Domaine en declin, moins de papiers qu'avant | Un domaine abandonne dont la formule pourrait revivre ailleurs |

### 3 Types de trous (nature du blocage)
| Type | Nom | Definition | Detection |
|------|-----|------------|-----------|
| **A** | **Technique** | Tout le monde SAIT ou aller, personne ne PEUT | Production haute + fitness stagnante + D-index bas |
| **B** | **Conceptuel** | Personne n'a l'IDEE de connecter. Le vide est INVISIBLE | Deux domaines actifs SANS co-occurrence + z-score negatif |
| **C** | **Perceptuel** | L'outil EXISTE, personne n'y CROIT | Fitness haute + D-index haut + citations << attendues |

Les formules Ygg pour les scores:
```
Score_A = P(t) * (1 - |delta_eta / delta_t|) * (1 - |D|)
Score_B = Act(A) * Act(B) * (1 - CoOcc(A,B)) * |z|
Score_C = eta_i * |D_i| * max(0, 1 - c_i(t) / expected_c_i)
```

---

## Les formules de Muninn (en LaTeX)

### F1 — Ebbinghaus Recall (repetition espacee)
**Source**: Settles & Meeder 2016
```latex
p = 2^{-\Delta / h}
\quad \text{where} \quad h = 7 \cdot 2^{\min(n, 10)}
```
**Glyphes cles**: exponentielle, puissance negative, fraction, Delta, min
**Cherche**: toute equation de la forme `a^{-x/y}` avec un `y` adaptatif.

---

### F2 — Normalized Compression Distance (NCD)
**Source**: Cilibrasi & Vitanyi 2005
```latex
\text{NCD}(a, b) = \frac{C(a \cdot b) - \min(C(a), C(b))}{\max(C(a), C(b))}
```
**Glyphes cles**: fraction, min, max, difference, fonction C()
**Cherche**: metrique de distance avec complexite au numerateur et denominateur.

---

### F3 — TF-IDF + Cosine Similarity
**Source**: Salton 1988
```latex
\text{idf}(t) = \ln\!\left(\frac{N+1}{\text{df}(t)+1}\right) + 1
```
```latex
\text{cos}(q, d) = \frac{\sum_t \text{tf}_q(t) \cdot \text{idf}(t) \cdot \text{tf}_d(t) \cdot \text{idf}(t)}{\|q\| \cdot \|d\|}
```
**Glyphes cles**: ln, somme, produit, fraction, norme
**Cherche**: usages SURPRENANTS de TF-IDF hors information retrieval (genomique, ecologie, signal).

---

### F4 — Spreading Activation (propagation semantique)
**Source**: Collins & Loftus 1975
```latex
A_{\text{neighbor}} = A_{\text{source}} \cdot w_{\text{norm}} \cdot \gamma^{h}
```
```latex
w_{\text{norm}}(i \to j) = \frac{w_{ij}}{\sum_k w_{ik}}
```
**Glyphes cles**: produit, fraction, somme, puissance, gamma
**Cherche**: propagation dans graphe pondere avec decroissance (SIR, percolation, cascades).

---

### F5 — Temperature (score de chaleur)
```latex
T = 0.8 \cdot R_{\text{recall}} + 0.2 \cdot f^2
```
**Glyphes cles**: combinaison lineaire, puissance carree
**Cherche**: combinaison lineaire decroissance temporelle + pression de saturation.

---

### F6 — Boot Scoring (selection multi-critere)
```latex
S = 0.15 R + 0.40 V + 0.20 A + 0.10 U + 0.15 N
```
```latex
N = \max\!\left(0, 1 - \frac{|R - 0.2|}{0.2}\right) \quad \text{si } 0.05 < R < 0.4
```
**Glyphes cles**: somme ponderee, max, valeur absolue, fonction triangulaire
**Cherche**: scoring multi-critere avec terme de maintenance pic au seuil critique.

---

### F7 — Effective Weight (TF-IDF federe)
```latex
w_{\text{eff}} = \text{count} \cdot \ln\!\left(1 + \frac{Z_{\text{total}}}{Z_{\text{present}}}\right)
```
**Glyphes cles**: produit, ln, fraction, 1+
**Cherche**: count * log(1 + N/k) hors IR — epidemiologie, ecologie, systemes distribues.

---

### F8 — Decay + Immortalite (mycelium)
```latex
\text{decay: } w_{t+1} = w_t \cdot 2^{-1/\tau} \quad (\tau = 30)
```
```latex
\text{immortel si } |Z_{\text{connection}}| \geq 3
```
**Glyphes cles**: exponentielle negative, seuil, cardinalite
**Cherche**: decroissance temporelle AVEC condition d'immortalite/cristallisation (nucleation, lexicalisation).

---

### F9 — Novelty Score (detection faits vs bruit)
```latex
\text{novelty}(l) = \sum_{p \in P_{\text{novel}}} 0.15 \cdot |\text{matches}(p, l)| - \sum_{p \in P_{\text{known}}} 0.3 \cdot \mathbb{1}[\text{match}(p, l)]
```
**Glyphes cles**: somme, indicatrice, difference, valeur absolue
**Cherche**: scoring surprisal par signaux positifs - signaux negatifs (anomalie detection, prediction error).

---

### F10 — Compression par temperature (budget adaptatif)
```latex
\text{budget}(n) = \text{base} \times \begin{cases} 1.3 & \text{si } T \geq 0.5 \\ 0.6 & \text{si } T < 0.2 \\ 1.0 & \text{sinon} \end{cases}
```
**Glyphes cles**: piecewise, multiplication, seuils
**Cherche**: allocation de ressources par tiers chaud/tiede/froid (CPU scaling, triage, bandwidth).

---

## Comment chercher — PROCEDURE CONCRETE

**NE CHERCHE PAS SUR INTERNET.**

1. Pour chaque formule F1-F10, extrais les glyphes cles (je les ai mis dans chaque section)
2. Cherche dans `glyph_registry.json` les glyph_ids correspondants (via latex_cmds)
3. Query `wt3.db` table `bipartite` pour trouver quels concept_ids utilisent ces glyphes
4. Pour les combos de glyphes (pas un seul), cherche dans `wt2_chunks` les papiers qui ont le MEME sous-ensemble
5. Verifie les co-occurrences dans `chunks/` (WT1) pour voir si les domaines trouves se connaissent deja
6. Classify chaque match en P1-P5 et Type A/B/C avec tes propres fonctions de scoring
7. Si WT2 est incomplet (52/416 chunks), utilise ce que tu as + la table bipartite de wt3.db

## Ce qu'on veut en sortie

Pour chaque match trouve, donne:

```
Formule Muninn: F1 (Ebbinghaus)
Concept_ids trouves: [id1, id2, id3]
Domaines: pharmacocinetique, ecologie, physique nucleaire
Glyphes partages: [glyph_42 (exp), glyph_89 (frac), glyph_102 (Delta)]
Co-occurrence actuelle: 0.03 (quasi nulle entre memoire LLM et pharma)
Pattern: P4 (trou ouvert)
Type de trou: B (conceptuel)
Score_B: 0.72
Connexion: meme structure de decroissance a demi-vie adaptative
```

On veut TOUS les patterns — P1 a P5 et Type A/B/C. Pas de filtre. Ramene tout.

Bonne chasse, cousin — mais cette fois utilise TES outils, pas Google.
