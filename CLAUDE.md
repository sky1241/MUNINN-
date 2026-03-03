# Muninn — Instructions pour Claude

## C'est quoi Muninn ?
Moteur de compression mémoire pour LLM. Créé par Sky (électricien, autodidacte, pense en fractales).
Le nom vient du corbeau de mémoire d'Odin — celui qui revient toujours.

## Le problème
Claude n'a pas de mémoire persistante. Le hack actuel = fichier MEMORY.md (200 lignes max, ~3K tokens)
chargé à chaque session. C'est du texte brut. Gaspillage massif. On peut faire ×4 mieux.

## La solution — 3 couches

### 1. Arbre L-system
Mémoire structurée en arbre fractal :
- Racine (100 lignes, toujours chargée) → pointeurs vers branches
- Branches (150 lignes, chargées si pertinentes) → pointeurs vers feuilles
- Feuilles (200 lignes, chargées si nécessaires)
- Même règles à chaque niveau (fractal)
- Budget total : 30K tokens max chargés = 15% du contexte

### 2. Codebook sub-token
Alphabet de compression sémantique — pas du texte humain, un langage machine-natif :
- `BT2:✓|65K|c15|d0.44` au lieu de "Blind test V2 complet, 65K concepts, cutoff 2015, Cohen's d=0.44"
- Compression ×3-4 sur les données factuelles
- Codebook universel (racine) + codebooks locaux (branches)
- Pointeurs : `→arch` `→bugs` `→sky` (2 tokens chacun)

### 3. Auto-optimisation
- Ce qui est lu souvent remonte vers la racine
- Ce qui est jamais lu descend puis meurt (élagage)
- Le LLM évalue sa propre compression
- Boucle de feedback

## Les 7 règles (engine/core/rules.md)
R1=Budget fixe, R2=Split si déborde, R3=Compresser avant split,
R4=Utile remonte/mort descend, R5=Codebook local par nœud,
R6=Auto-description, R7=Navigation par descente

## Budget réel (engine/core/budget.md)
- Racine : 600 tokens compressé (1,600 brut)
- Branche : 800 tokens compressé (2,400 brut)
- Feuille : 1,000 tokens compressé (3,200 brut)
- Capacité max : 90K tokens d'info dans 30K de budget

## Repo parent
Yggdrasil Engine (`c:\Users\ludov\Desktop\ygg\yggdrasil-engine`) — moteur de science des sciences.
Muninn est né de l'observation que la mémoire d'Yggdrasil (MEMORY.md) était sous-factorisée.
Briques existantes dans Yggdrasil : winter tree scanner, L-system mémoire, strates S-2→S6.

## Conventions
- Sky parle français, informel, va vite
- Python : `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`
- Windows 11, bash shell, PYTHONIOENCODING=utf-8
- Pas d'emojis sauf demande explicite
- JAMAIS afficher de tokens git

## État actuel
- README.md : 4 points cardinaux posés
- engine/core/rules.md : 7 règles du moteur
- engine/core/budget.md : valeurs concrètes mesurées
- Prochaine étape : implémenter le codebook + premier arbre prototype
