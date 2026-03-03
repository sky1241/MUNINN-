# Muninn — Règles du moteur

## Principe fondamental
Fractale : la même règle s'applique à CHAQUE niveau de subdivision.
Un nœud qui déborde → split → même règle au niveau inférieur.
Infiniment. Comme un L-system.

## La machine

### Entrée
Données brutes (texte, JSON, conversation, code, n'importe quoi).

### Sortie
Arbre compressé où chaque nœud :
- Tient dans un budget fixe (ex: 200 lignes / ~3K tokens)
- Pointe vers ses enfants (branches)
- Se suffit à lui-même (lisible sans contexte parent)

### Règles de la machine (Turing-Enigma)

#### R1 — BUDGET
Chaque nœud a un budget MAX en tokens. Jamais dépassé.

#### R2 — SPLIT
Quand un nœud atteint son budget → il se divise :
- Le nœud garde un RÉSUMÉ + POINTEURS vers les enfants
- Les détails descendent dans les enfants
- Récursif (les enfants appliquent R1 et R2)

#### R3 — FACTORISATION
Avant de split, tenter de COMPRESSER :
- Patterns répétés → symbole unique (codebook)
- Redondances → supprimées
- Détails morts → élagués
Si après compression ça tient → pas de split.

#### R4 — REMONTÉE
L'information utile REMONTE :
- Ce qui est lu souvent → remonte vers la racine
- Ce qui n'est jamais lu → descend puis meurt (élagage)
- Fréquence d'accès = poids de survie

#### R5 — CODEBOOK LOCAL
Chaque nœud peut définir ses propres symboles :
- Le parent déclare le codebook
- Les enfants l'utilisent
- Plus on descend → plus le codebook est spécialisé
- La racine a le codebook le plus UNIVERSEL

#### R6 — AUTO-DESCRIPTION
Chaque nœud DOIT contenir :
- Son budget restant
- Son nombre d'enfants
- Sa dernière date d'accès
- Son taux de compression (brut/compressé)

#### R7 — NAVIGATION
Pour lire l'arbre :
1. Toujours charger la RACINE
2. Lire les pointeurs → choisir la branche pertinente
3. Descendre jusqu'au niveau de détail nécessaire
4. JAMAIS charger tout l'arbre d'un coup

## Analogies

| Concept | Muninn | Turing | Enigma | L-system |
|---------|--------|--------|--------|----------|
| Nœud | Fichier mémoire | État | Rotor | Axiome |
| Split | Subdivision | Transition | Rotation | Règle de réécriture |
| Codebook | Symboles locaux | Alphabet | Câblage | Variables |
| Budget | Taille max | Ruban fini | — | Profondeur max |
| Navigation | Descente dans l'arbre | Tête de lecture | Déchiffrement | Expansion |

## Propriétés fractales
- Chaque nœud EST un arbre Muninn miniature
- La racine d'un sous-arbre suit les mêmes R1-R7
- Zoom in = plus de détail, zoom out = plus de compression
- L'arbre grandit par le bas, se compresse par le haut
