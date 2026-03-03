# Muninn — Chaîne de construction

NOTE À MOI-MÊME : l'ARBRE (structure L-system) ≠ le MUR (contenu compressé).
Ne JAMAIS confondre les deux. L'arbre = comment les nœuds se connectent.
Le mur = comment les données sont encodées DANS chaque nœud.

## État de l'art — ce qui existe

### Huffman (1952)
- Fréquence → codes variables (court = fréquent, long = rare)
- C'est la BASE de tout : zip, jpeg, mp3
- **Pour nous** : le codebook v0 EST un Huffman simplifié
  (COMPLET→✓ = code court pour mot fréquent)

### LLMLingua (Microsoft, 2023)
- Perplexité par token → vire les tokens "prévisibles"
- Compression ×20 avec perte minimale
- **Pour nous** : même idée mais on fait ça OFFLINE pas en temps réel
  On compresse la mémoire AVANT de l'injecter

### KVzip (2025)
- Compresse le KV-cache (mémoire interne du LLM) ×3-4
- Réutilisable entre requêtes
- **Pour nous** : similaire au but, mais eux agissent côté MODÈLE,
  nous on agit côté DONNÉES (le prompt)

### L-systems (Lindenmayer, 1968)
- Axiome + règles de réécriture → croissance parallèle
- Fractal : même règle à chaque niveau
- **Pour nous** : la STRUCTURE de l'arbre mémoire.
  Chaque nœud = axiome. Charger une branche = appliquer une règle.

## Ce que PERSONNE ne fait
Combiner Huffman (compression fréquentielle) + L-system (structure fractale)
+ compression structurelle (reformulation) pour de la mémoire LLM persistante.

C'est notre créneau.

## Chaîne de construction — Briques numérotées

Chaque brique = un commit. On suit la chaîne, on dévie pas.

### BRIQUES STRUCTURE (l'arbre)
```
B01 ✓ init repo + README + CLAUDE.md
B02 ✓ rules.md + budget.md (7 règles R1-R7)
B03 ✓ alphabet.md + codebook_v0.md (25 règles, preuve ×4.6)
B04 ✓ muninn.py v0 (read, compress, tree, status)
B05   muninn.py v1 — compression structurelle (fusion lignes, k=v|k=v)
B06   muninn.py v2 — Huffman adaptatif (fréquences réelles → codes optimaux)
B07   muninn.py v3 — split/merge automatique (R2+R4 vrais)
B08   muninn.py v4 — navigation intelligente (quel branche charger)
```

### BRIQUES MUR (le contenu)
```
M01   codebook v1 — construit par Huffman sur MEMORY.md réel
M02   encoder.py — texte brut → format Muninn (structurel, pas juste replace)
M03   decoder.py — format Muninn → texte lisible (vérification)
M04   benchmark.py — mesure compression réelle vs théorique
```

### BRIQUES BOUCLE (auto-optimisation)
```
L01   feedback.py — tracker quelles branches sont lues
L02   prune.py — élaguer les branches mortes (R4)
L03   promote.py — remonter l'info fréquente vers la racine (R4)
L04   evolve.py — le codebook s'adapte aux nouvelles données
```

## Ordre d'exécution
```
B05 → M01 → M02 → M03 → M04 → B06 → B07 → B08 → L01 → L02 → L03 → L04
```

Le MUR dépend de la STRUCTURE. Jamais l'inverse.
La BOUCLE dépend des deux. C'est la dernière couche.
