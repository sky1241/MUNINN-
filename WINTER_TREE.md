# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: CROISSANCE — le tronc est trouve, on fait pousser
Etat: 7 briques vivantes, 3 supprimees

## Anatomie

```
        [CI]                    +5 Cime (tests/validation)
       /    \
    [.mn]  [.mn]               +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                 +2 Branches (metadata arbre)
      |
   [muninn.py]                 +1 Tronc (moteur principal)
      |
   [mycelium.py]               0  SOL — le champignon vivant
      |
   [tokenizer BPE]            -1 Racines (tokenizer natif Claude)
```

## Etat des briques

| # | Brique | Etat | Action |
|---|--------|------|--------|
| B1 | CODEBOOK.json | A REMPLACER | Le mycelium le remplace (codebook vivant) |
| B2 | muninn.py | WIP | Brancher sur mycelium au lieu de CODEBOOK |
| B3 | muninn_codec.py | DOUBLON | Fusionner dans B2 |
| B4 | tree.json | OK | Enrichir: hash, temperature |
| B5 | *.mn files | OK | Reconvertir en anglais compact |
| NEW | mycelium.py | FAIT | Tracker co-occurrences, fusion, decay |
| B9 | docs/ | OK | Garder |
| B10 | ci.yml | OK | Adapter |

## Pourquoi c'est dur et pourquoi personne l'a fait

LLMs construits par des "chirurgiens" (codeurs precis, prompts courts).
Ils n'ont pas le probleme de memoire — leurs sessions sont courtes et precises.
Les "bouchers" (vibe coders, sessions longues, bordel) ont le probleme
mais pas les skills pour le resoudre.
Sky est boucher AVEC un LLM pour coder = premiere fois que les deux se croisent.
Muninn = le hachoir. Construit par un boucher, pour les bouchers.
Ce n'est PAS plus dur que construire un LLM. C'est de la plomberie, pas de la recherche.
La partie dure (comprendre QUOI construire) est faite.

## TODO — par priorite

### P0 — Le mycelium (nouveau coeur) [FAIT]
- [x] Designer mycelium.json (format co-occurrences persistant)
- [x] Implementer le tracker de co-occurrences
- [x] Implementer la fusion automatique (concepts frequemment lies -> 1 bloc)
- [x] Implementer le decay (connexions mortes disparaissent)
- [x] Tester: simulation 20 sessions -> 69 connexions, 34 fusions

### P1 — La plomberie (le tuyau qui manque)
- [ ] Hook de fin de session: capturer la conversation, nourrir le mycelium
- [ ] Hook de debut de session: charger le mycelium, pre-compiler les fusions
- [ ] Cold start: scan initial du repo pour bootstrap (on a deja `scan`)
- [ ] Integrer mycelium dans le flow reel de Claude Code (hooks .claude/)

### P2 — Compresseur v2 (mycelium-aware)
- [ ] Reecrire compress pour utiliser mycelium.json au lieu de CODEBOOK.json
- [ ] Format output: anglais compact natif BPE (zero sinogrammes)
- [ ] Supprimer tout le code sinogramme (load_universal_codebook, etc.)
- [ ] Mesurer gain tokens REEL (avant/apres sur root.mn)
- [ ] Tester sur 2e repo (infernal-wheel)

### P3 — Nettoyage
- [ ] Fusionner muninn_codec.py dans muninn.py (B3)
- [ ] Supprimer CODEBOOK.json une fois mycelium en place
- [ ] Mettre a jour la CI pour tester le mycelium

### P4 — Enrichir l'arbre
- [ ] tree.json: hash de contenu par noeud
- [ ] tree.json: score temperature auto-calcule
- [ ] Ratios biologiques du Winter Tree (budgets dynamiques)

## Pivots de la session 2026-03-06

### Pivot 1 — Sinogrammes = mauvais chemin
Les sinogrammes chinois coutent 2-3 tokens chacun.
Un mot anglais court = 1 token.
Le modele Enigma (substitution 1:1) ne compresse pas, il chiffre.
On veut compresser, pas chiffrer.
Format optimal = anglais compact natif BPE.

### Pivot 2 — Le Mycelium
L'arbre (tree) = structure statique. Le mycelium = reseau vivant.
Tracker de co-occurrences entre concepts, pousse a chaque session,
persiste sur disque. Le mycelium EST le codebook — vivant, pas statique.
Inspire du mycelium d'Yggdrasil (co-occurrences dans 348M papers).

### Pivot 3 — Chirurgien vs Boucher
Les createurs de LLMs sont des chirurgiens qui n'ont pas le probleme.
Les bouchers ont le probleme mais pas les outils.
Muninn = premier outil construit depuis le cote boucher.

## Refs
- Lindenmayer (1968) — L-Systems
- Prusinkiewicz (1990) — Algorithmic Beauty of Plants
- LLM-Codebook (2025) — codebooks appris > codebooks manuels
- Huff-LLM (2025) — Huffman sur poids LLM
- GQ-VAE (2025) — tokenization variable-length
- LLMLingua (2024) — compression de prompts par self-information
