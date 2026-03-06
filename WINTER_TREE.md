# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: CROISSANCE — le tronc est trouve, on fait pousser
Etat: 6 briques vivantes, 5 supprimees (nettoyage P3)

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
| B2 | muninn.py v0.5 | OK | Moteur principal, bootstrap, compress, tree, boot, feed |
| B4 | tree.json | OK | Enrichir: hash, temperature |
| B5 | *.mn files | OK | Memoire vivante |
| NEW | mycelium.py | OK | Tracker co-occurrences, fusion, decay |
| B9 | docs/ | OK | LITERATURE.md enrichi (15+ papiers) |
| B10 | ci.yml | OK | Tests: tree, engine, mycelium, feed |
| NEW | .claude/settings.local.json | OK | Hooks PreCompact + SessionEnd -> feed |
| ~~B1~~ | ~~CODEBOOK.json~~ | SUPPRIME | Remplace par UNIVERSAL_RULES + mycelium |
| ~~B3~~ | ~~muninn_codec.py~~ | SUPPRIME | Code sinogramme mort |
| ~~B8~~ | ~~CODEBOOK_TREE.md~~ | SUPPRIME | Index sinogrammes mort |

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

### P1 — La plomberie (le tuyau qui manque) [FAIT]
- [x] Cold start: `muninn.py bootstrap <repo>` — scanne et nourrit le mycelium
- [x] Hook PreCompact: parse transcript JSONL, nourrit le mycelium avant compaction
- [x] Hook SessionEnd: meme chose, filet de securite en fin de session
- [x] `muninn.py feed <transcript.jsonl>` — nourrit depuis un fichier specifique
- [x] `muninn.py feed --history` — rattrapage: digere tous les transcripts passes
- [x] Idempotent: tracked via .muninn/fed_transcripts.json
- [x] Integre dans .claude/settings.local.json (hooks natifs Claude Code)
- Note: hooks receoivent transcript_path via stdin JSON (decouverte mars 2026)

### P2 — Compresseur v2 (mycelium-aware)
- [x] Codebook loader v2: UNIVERSAL_RULES + mycelium (zero sinogrammes)
- [x] Compresseur utilise fusions mycelium pour strip redondance
- [ ] Mesurer gain tokens REEL (avant/apres sur root.mn)
- [ ] Tester sur 2e repo (infernal-wheel)
- Note: compression x1.1-1.2 sur texte deja compact. Gains reels = texte verbeux

### P3 — Nettoyage [FAIT]
- [x] Supprimer muninn_codec.py (code sinogramme mort)
- [x] Supprimer CODEBOOK.json (remplace par UNIVERSAL_RULES + mycelium)
- [x] Supprimer CODEBOOK_TREE.md (index sinogrammes mort)
- [x] Nettoyer muninn.py: virer sym_to_concept, concept_to_sym, CODEBOOK_PATH
- [x] Reecrire CI: tester tree, engine commands, mycelium (zero sinogramme)
- [x] Fix sys.stdout wrapper (condition encoding != utf-8)

### P4 — Enrichir l'arbre [FAIT]
- [x] tree.json: hash SHA-256 (8 chars) par noeud — detecte changements
- [x] tree.json: score temperature auto-calcule (access + recency + fill)
- [x] Ratios biologiques: budget dynamique par temperature (COCOM 2025)
- [x] Prune utilise temperature au lieu de access_count brut
- [x] Boot utilise temperature pour ranking des branches
- [x] Status affiche barre de temperature visuelle

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
