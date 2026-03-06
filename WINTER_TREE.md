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

### P0 — Le pivot fondamental
- [ ] Definir le nouveau format de compression (anglais compact, zero codebook)
- [ ] Repondre a la question: comment je compresse l'input de Sky dans MON format et comment ca roundtrip?
- [ ] Valider que le format compressed coute moins de tokens que le texte brut (mesurer avec tiktoken)
- [ ] Ecrire FORMAT_RULES.json (regles, pas traduction)

### P1 — Reconstruire le compresseur
- [ ] Reecrire compress dans muninn.py pour appliquer les nouvelles regles
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

## Refs
- Lindenmayer (1968) — L-Systems
- Prusinkiewicz (1990) — Algorithmic Beauty of Plants
- LLM-Codebook (2025) — codebooks appris > codebooks manuels
- Huff-LLM (2025) — Huffman sur poids LLM
- GQ-VAE (2025) — tokenization variable-length
- LLMLingua (2024) — compression de prompts par self-information
