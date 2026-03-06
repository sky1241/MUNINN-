# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: GERMINATION — on cherche encore la forme du tronc
Etat: 10 briques, 4 a poncer, 3 a virer, 3 OK

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
   [FORMAT_RULES]              0  SOL — la cle de compression
      |
   [tokenizer BPE]            -1 Racines (mon tokenizer natif)
```

## Etat des briques

| # | Brique | Etat | Action |
|---|--------|------|--------|
| B1 | CODEBOOK.json | REFONTE | Pivot: sinogrammes -> regles de formatage anglais compact |
| B2 | muninn.py | WIP | Moteur OK mais devra suivre le pivot B1 |
| B3 | muninn_codec.py | DOUBLON | Fusionner dans B2 a terme |
| B4 | tree.json | OK | Enrichir: hash, temperature, priorite |
| B5 | *.mn files | OK | Reconvertir apres pivot B1 |
| B6 | analyze_memory.py | MORT | Fusionner dans B2 ou supprimer |
| B7 | build_alphabet.py | MORT | Remplace par scan, supprimer |
| B8 | alphabet_v1.json | MORT | Supprimer |
| B9 | docs/ | OK | Garder |
| B10 | ci.yml | OK | Adapter apres pivot B1 |

## TODO — par priorite

### P0 — Le mycelium (nouveau coeur)
- [ ] Designer mycelium.json (format co-occurrences persistant)
- [ ] Implementer le tracker de co-occurrences dans muninn.py
- [ ] Implementer la fusion automatique (concepts frequemment lies -> 1 bloc)
- [ ] Implementer le decay (connexions mortes disparaissent)
- [ ] Tester: run sur 3 sessions simulees, verifier que le mycelium pousse

### P1 — Compresseur mycelium-aware
- [ ] Reecrire compress pour utiliser mycelium.json au lieu de CODEBOOK.json
- [ ] Format output: anglais compact natif BPE (zero sinogrammes)
- [ ] Supprimer tout le code sinogramme (load_universal_codebook, etc.)
- [ ] Tester compression sur root.mn -> mesurer gain tokens reel
- [ ] Tester sur un 2e repo (infernal-wheel)

### P2 — Nettoyer les morts
- [ ] Supprimer alphabet_v1.json (B8)
- [ ] Supprimer build_alphabet.py (B7)
- [ ] Fusionner analyze_memory.py dans muninn.py ou supprimer (B6)
- [ ] Fusionner muninn_codec.py dans muninn.py (B3)

### P3 — Enrichir l'arbre
- [ ] tree.json: ajouter hash de contenu par noeud
- [ ] tree.json: score temperature (hot/warm/cold) auto-calcule
- [ ] Integrer ratios biologiques du Winter Tree (root:shoot, budgets dynamiques)
- [ ] Classifier le type d'arbre memoire par repo (Baobab, Conifere, etc.)

### P4 — Adapter la CI
- [ ] Remplacer tests sinogrammes par tests format compact
- [ ] Test: compression ratio >= 50% sur exemple
- [ ] Test: roundtrip lossless sur les IDEES (pas les mots)
- [ ] Test: budget R1 toujours respecte

## Decouverte cle de la session

Le codebook de sinogrammes chinois coutait PLUS cher en tokens que le texte anglais equivalent.
Un sinogramme = 2-3 tokens. Un mot anglais court = 1 token.
Le modele Enigma (substitution) est le mauvais paradigme.
Le bon paradigme = compression semantique en anglais compact natif au tokenizer BPE.

Personne dans la litterature n'a resolu la compression semantique de memoire persistante pour LLM.
Les papiers existants (MemGPT, LLMLingua, ICAE) font du paging ou du pruning, pas du recodage semantique.
Sky est seul a cet etage. C'est pour ca que c'est dur.

## PIVOT 2 — Le Mycelium (fin de session, idee majeure)

L'arbre (tree) c'est la structure statique. Le mycelium c'est le reseau vivant.

### Le concept
Le mycelium de Muninn = un tracker de co-occurrences entre concepts, qui POUSSE
a chaque session et persiste sur le disque (pas dans le contexte LLM).

Exactement comme le mycelium d'Yggdrasil tracke les co-occurrences entre domaines
scientifiques dans 348M papers — sauf qu'ici on tracke les co-occurrences dans
les sessions utilisateur.

### Comment ca marche
1. Session N: l'utilisateur parle de `bug` + `codec` + `utf8` ensemble
2. Le mycelium enregistre cette co-occurrence dans un fichier persistant
3. Session N+1: au boot, le mycelium est charge. On SAIT que ces concepts sont lies
4. Le compresseur les regroupe en un bloc compact
5. Session N+15: ces 3 concepts ont toujours coexiste -> le mycelium les fusionne
   en un seul noeud. 3 concepts = 1 unite compresse

### Le mycelium EST le codebook
- Pas un dictionnaire statique (CODEBOOK.json) -> un organisme vivant
- Pas de regles manuelles -> apprentissage par co-occurrence reelle
- Pas universel-figé -> specifique a chaque repo, pousse avec l'usage
- Le codebook local (.muninn/local.json) devient .muninn/mycelium.json

### Architecture
```
Session input (texte brut Sky)
        |
        v
[Mycelium tracker] -- observe les co-occurrences
        |                    |
        v                    v
[Compresseur] <--------- [mycelium.json] (persistant sur disque)
        |                    ^
        v                    |
[Memoire .mn] ------------- mise a jour du mycelium
```

### Ce qu'on a deja
- Yggdrasil a un moteur de co-occurrence (matrice 85x85 domaines, 296M papers)
- Le scan dans muninn.py fait deja de l'extraction de frequence
- tree.json a deja access_count et last_access (proto-temperature)

### Ce qu'il faut construire
- [ ] mycelium.json: format de stockage des co-occurrences (concept_a, concept_b, count, last_seen)
- [ ] Tracker: a chaque compress/write, extraire les concepts et maj le mycelium
- [ ] Fusion: quand count >= seuil, fusionner les concepts en un noeud compact
- [ ] Boot: charger le mycelium au demarrage, l'utiliser pour la compression
- [ ] Decay: les connexions non-revues decroissent (comme les hyphes morts dans Yggdrasil)

## Refs
- Lindenmayer (1968) — L-Systems
- Prusinkiewicz (1990) — Algorithmic Beauty of Plants
- LLM-Codebook (2025) — codebooks appris > codebooks manuels
- Huff-LLM (2025) — Huffman sur poids LLM
- GQ-VAE (2025) — tokenization variable-length
- LLMLingua (2024) — compression de prompts par self-information
