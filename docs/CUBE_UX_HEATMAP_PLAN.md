# Plan UX — Carte de chaleur de reconstruction

## Contexte

Le NeuronMapWidget (cube 3D) affiche actuellement les concepts du scan
mycelium colores par **degree** (nombre de connexions). C'est utile mais
ca montre la structure du reseau, pas la resilience du code.

Le Cube Muninn reconstruit du code et produit un **NCD** (0.0 = parfait,
1.0 = echec total) par cube. Cette information est exactement ce qu'il
faut pour une carte de chaleur : les zones rouges = code critique non
reconstructible (logique unique, vocabulaire invente), zones vertes =
code standard reconstructible a 100%.

## Ce qui existe deja

| Brique | Fichier | Ce que ca fait |
|--------|---------|----------------|
| NeuronMapWidget | muninn/ui/neuron_map.py | Cube 3D rotatif, heatmap vert→rouge, zoom/pan |
| DEGREE_GRADIENT | neuron_map.py:80-91 | 10 niveaux de couleur (vert→jaune→rouge) |
| Neuron.temperature | neuron_map.py:55 | Champ float stocke mais colore par degree, pas temperature |
| DetailPanel | muninn/ui/detail_panel.py | Affiche temperature en texte, zone, voisins |
| TreeViewWidget | muninn/ui/tree_view.py | Arbre botanique avec status done/wip/todo |
| Bidirectionnel | main_window.py:130-132 | Clic neuron ↔ highlight tree (B-UI-11) |
| CubeStore | engine/core/cube.py:839 | SQLite avec SHA, NCD, temperature par cube |
| compute_hotness | cube_providers.py:1073 | Calcule temperature d'un cube |
| _build_full_anchor_map | cube_providers.py:357 | 21 regles d'ancrage, retourne gaps |

## Ce qu'il faut faire

### Phase 1 — Brancher NCD sur la carte (le pont)

Le scanner actuel produit des `Neuron` avec `temperature` base sur la
frequence de scan. Faut ajouter un **mode reconstruction** ou :

1. **Chaque cube = un neuron** sur la carte 3D
   - Position : basee sur la position dans le fichier (x = ligne, y = profondeur d'indentation, z = fichier)
   - Couleur : NCD → DEGREE_GRADIENT (0.0 = vert, 1.0 = rouge)
   - Taille : nombre de gap lines (plus de gaps = plus gros = plus visible)

2. **Toggle de mode** dans la toolbar
   - Mode "Mycelium" (actuel) : couleur par degree
   - Mode "Reconstruction" (nouveau) : couleur par NCD
   - Meme widget, meme gradient, juste la source de donnees qui change

3. **Les cubes qui fail** (NCD > 0) montrent au hover :
   - Les gap lines exactes (ce que le modele n'a pas su reconstruire)
   - Les identifiers inconnus (le vocabulaire invente)
   - Le NCD et le nombre de tentatives

### Phase 2 — Le detail panel enrichi

Le DetailPanel affiche deja temperature/zone. Ajouter :

- **SHA status** : check vert / croix rouge
- **NCD value** : barre de progression coloree
- **Gap lines** : liste des lignes non-ancrees avec leur categorie
  (METHOD_CALL, VAR_DECL, CONTROL_FLOW, etc.)
- **Identifiers inconnus** : les mots que le programme ne connait pas
  → ce sont les points critiques du code

### Phase 3 — La vue fichier

Vue complementaire au cube 3D : le fichier source affiche ligne par ligne
avec un bandeau de couleur a gauche (comme un code coverage).

- Ligne ancree (SHA garanti) → bandeau vert
- Ligne gap (modele doit deviner) → bandeau rouge
- Ligne gap mais SHA match quand meme → bandeau orange (risque)

Ca c'est la vue que le banquier comprend : "ligne 47 est rouge, c'est
la qu'il faut regarder".

### Phase 4 — Integration avec les niveaux x1/x2/x3

La carte montre les cubes x1 (atomes). Quand on zoom out, les cubes x2
(molecules) apparaissent — fusion visuelle de 2 cubes x1 adjacents.

- x1 : granularite fine, chaque cube 112 tokens
- x2 : 2 cubes fusionnes, couleur = moyenne des NCD
- x3 : 4 cubes, vue d'ensemble

Le zoom physique du widget controle le niveau de detail. C'est fractal
— comme l'arbre Muninn lui-meme.

## Architecture technique

```
CubeStore (SQLite)          NeuronMapWidget (PyQt6)
  cubes: id, sha, ncd   →    Neuron: id, temperature=ncd, zone=file
  neighbors: links       →    Neuron.depends: edges
  gaps: per-cube         →    Neuron.degree: gap_count

_build_full_anchor_map   →    color mapping: 0 gaps = green, N gaps = red
```

Le bridge c'est une fonction `load_reconstruction_map(cube_store_path)`
dans le NeuronMapWidget qui :
1. Ouvre le CubeStore
2. Pour chaque cube, cree un Neuron avec temperature=NCD
3. Les voisins du cube deviennent les edges du neuron
4. Appelle load_neurons() (methode existante)

C'est ~50 lignes de code.

## Le flux mycelium multi-pass

Le plan de Sky pour les cubes qui fail :

```
x1 pass 1 → 87% SHA, mycelium apprend 53 cubes
x1 pass 2 → 88.5% SHA, mycelium a le vocabulaire
x2 pass 1 → plus de contexte, les molecules couvrent les atomes fails
x2 pass 2 → mycelium a aussi les molecules
x3 pass 1 → cellules, vision d'ensemble
```

Chaque niveau nourrit le mycelium. Le vocabulaire custom du projet
(`mutableFor`, `copyOnWriteContext`) est appris progressivement.
Les cubes qui failent au x1 reussissent au x2 parce que le modele
voit le pattern complet (atome + son voisin).

A terme : le mycelium connait TOUT le vocabulaire → les cubes x1
qui failaient passent au re-run suivant. Le programme apprend le
projet et s'ameliore a chaque pass. C'est pas du ML — c'est de
l'accumulation de vocabulaire. Comme un humain qui lit du code.

## Priorite

1. Le pont NCD → carte (Phase 1) — 50 lignes, impact immediat
2. Le detail panel enrichi (Phase 2) — 30 lignes, info critique
3. La vue fichier (Phase 3) — nouveau widget, ~200 lignes
4. Les niveaux fractals (Phase 4) — design a penser

## Ce qu'on touche PAS

- Le NeuronMapWidget actuel continue de marcher en mode Mycelium
- Le TreeView reste independant
- Zero changement dans le pipeline de reconstruction
- Le toggle mode est juste un bouton qui change la source de donnees
