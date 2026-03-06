# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: CROISSANCE — le tronc est trouve, on fait pousser
Etat: 8 briques vivantes, 3 supprimees (nettoyage P3)

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
| B2 | muninn.py v0.8 | OK | Moteur: 9 couches compression, bootstrap, tree, boot, feed, verify |
| B4 | tree.json | OK | Enrichir: hash, temperature |
| B5 | *.mn files | OK | Memoire vivante |
| NEW | mycelium.py | OK | Tracker co-occurrences, fusion, decay |
| B9 | docs/ | OK | LITERATURE.md enrichi (15+ papiers) |
| B10 | ci.yml | OK | Tests: tree, engine, mycelium, feed |
| NEW | .claude/settings.local.json | OK | Hooks PreCompact + SessionEnd -> feed + compress |
| NEW | .muninn/sessions/*.mn | OK | Transcripts compresses (auto-prune 10 derniers) |
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

### P2 — Compresseur v2 (mycelium-aware) [FAIT]
- [x] Codebook loader v2: UNIVERSAL_RULES + mycelium (zero sinogrammes)
- [x] Compresseur utilise fusions mycelium pour strip redondance
- [x] 7 couches de compression: markdown, filler, phrases, nombres, rules, mycelium, facts
- [x] Extraction de faits: nombres+unites, %, key=value, commits, Cohen's d
- [x] Mesure gain tokens REEL:
  - Texte verbeux (MEMORY-style): x7.4 (1091->148 tokens, -86%)
  - Texte semi-compact (WINTER_TREE): x1.9 (1343->713 tokens, -47%)
  - Texte deja compact (README): x1.7 (714->409 tokens, -43%)
  - infernal-wheel SYSTEM_SUMMARY: x1.7 (3472->2033 tokens, -41%)
- [x] Teste sur 2e repo (infernal-wheel): OK, compression universelle

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

### P5 — Auto-evolution (compresseur qui apprend) [FAIT]
- [x] Mycelium: get_learned_fillers() — mots noise (10+ connexions, zero fusion)
- [x] Mycelium: get_learned_abbreviations() — fusions fortes -> abreviations
- [x] L2b: fillers dynamiques injectes dans le compresseur depuis mycelium
- [x] L3b: abbreviations dynamiques injectees depuis mycelium
- [x] `muninn.py verify` — mesure qualite compression (facts preserved, ratio, score)
- [x] Boucle complete: feed -> mycelium apprend -> compresseur s'ameliore
- Note: abbreviations emergent quand fusion strength >= 8 (apres ~10+ sessions)

### P6 — Session compression (memoire post-compaction) [FAIT]
- [x] compress_transcript(): transcript JSONL -> .mn compresse dans .muninn/sessions/
- [x] Secret filtering: ghp_ tokens, sk_ API keys, passwords redacted avant compression
- [x] Hook PreCompact: feed mycelium + compress transcript (2 actions en 1)
- [x] Hook feed direct: meme chose en mode CLI
- [x] Boot charge le dernier .mn de session (tail-first si trop gros pour budget)
- [x] Auto-prune: garde les 10 derniers .mn, supprime les anciens
- Mesure: session 2730 JSONL -> 50K tokens brut -> 41K compresse (x1.2)
- Note: ratio modeste car transcript deja semi-compact (dialogue technique)
- Note: sur texte verbeux le compresseur fait x7.4 (cf P2)

### P7 — Compression pro (9 couches) [FAIT]

#### Brique 1 : Benchmark [TODO]
- [ ] Prendre 5 transcripts reels, mesurer facts preserves avant/apres

#### Brique 2 : LLMLingua-2 comme Layer 8 [FAIT]
- [x] pip install llmlingua (BERT ~1 GB, CPU, zero API)
- [x] Integre comme couche 8, singleton cache, skip si <2K chars
- [x] Rate=0.5 optimal (garde tous les faits, x2.1 additionnel)

#### Brique 3 : Resume LLM comme Layer 9 [FAIT]
- [x] Claude Haiku resume via API Anthropic (pip install anthropic)
- [x] Prompt optimise: garde 100% facts, cible 20% longueur
- [x] Fallback gracieux si pas de cle API ou pas de SDK
- [x] Seuil: seulement si >4K chars (cout API justifie)
- Ratio attendu: x5-10 additionnel avec ~100% facts
- Cout: ~2K tokens input + ~500 output pour economiser ~10K+

Pipeline complet (9 couches):
  L1: markdown strip | L2: filler words | L3: phrase compression
  L4: number shortening | L5: universal rules | L6: mycelium
  L7: fact extraction | L8: LLMLingua-2 (BERT) | L9: LLM self-compress

Concurrence connue:
- Claude-Mem (21K stars): SQLite + Claude API, x10, pas d'arbre ni mycelium
- Letta Code (ex-MemGPT): git-backed markdown, agent complet
- LLMLingua-2 (Microsoft): BERT scorer, x3-20, pas de persistance
- ACON: gradient-free compression guidelines, -26-54% tokens

Ce que Muninn a que les autres n'ont pas:
- 9 couches empilees (regex + BERT + LLM), pas juste 1 technique
- Mycelium vivant (codebook qui apprend par co-occurrence)
- L-system fractal (memes regles a chaque niveau)
- Secret filtering
- Fonctionne sans dependances (L1-L7 regex only), GPU et API optionnels

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
