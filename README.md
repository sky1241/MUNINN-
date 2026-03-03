# Muninn

> *Le corbeau de la mémoire — celui qui revient toujours.*

Moteur de compression sémantique sub-token pour mémoire persistante LLM.

## Les 4 points cardinaux

### NORD — Le problème
Les LLM n'ont pas de mémoire persistante. Chaque session repart de zéro.
Les hacks actuels (fichiers markdown, RAG, vector stores) sont du texte brut
injecté dans le contexte — gaspillage massif de tokens.
200 lignes × 16 tokens/ligne = 3,200 tokens pour stocker ce qu'un codebook
compressé dirait en 800.

### EST — L'idée
Compression sémantique **sous le niveau du token**.
Un alphabet de classement conçu pour les LLM — pas du texte humain,
un langage machine-natif qui maximise le sens par token.

Inspiré de :
- **L-systems** (Lindenmayer) — croissance fractale depuis un axiome
- **Machines de Turing** — codebook = table de transition
- **Enigma** — le codebook est la clé, le LLM sait décoder

### SUD — L'architecture
Des moteurs modulaires câblables en boucle :

```
[Moteur Mémoire v10] ←→ [Moteur Principal v12] ←→ [Moteur Auto-Optim]
        ↑                                                    ↓
        └────────────── boucle de rétroaction ───────────────┘
```

Chaque moteur = un module autonome (un repo).
Une phrase en entrée → la chaîne fait le reste.

### OUEST — Les briques existantes
- **Yggdrasil Engine** — compression de 348M papers en strates (S-2→S6)
- **Winter Tree Scanner** — scan incrémental par chunks avec arbre d'état
- **L-system mémoire** — arbre MEMORY.md → branches → feuilles (prototype dans Claude Code)
- **Codebook proto** — format compact `BT2✓11|65K|c15|d0.44` (à formaliser)
- **Règles UX** — (à extraire des autres repos)

## Feuille de route

### Phase 0 — Spécification (maintenant)
- [ ] Définir le format du codebook (alphabet, séparateurs, règles d'encodage)
- [ ] Spécifier l'arbre L-system (profondeur max, règles de réécriture)
- [ ] Lister les briques existantes à importer
- [ ] Benchmark : texte brut vs codebook compressé (ratio tokens/information)

### Phase 1 — Codebook v0.1
- [ ] Table de symboles : concepts fréquents → codes compacts
- [ ] Encoder/décoder une session Yggdrasil en format Muninn
- [ ] Mesurer la compression réelle

### Phase 2 — Arbre L-system
- [ ] Structure racine → branches → feuilles avec pointeurs
- [ ] Règles de réécriture (quand un nœud déborde → split)
- [ ] Navigation intelligente (quel chemin descendre selon le contexte)

### Phase 3 — Boucle auto-optimisation
- [ ] Le LLM évalue sa propre compression
- [ ] Feedback loop : ce qui a été utile remonte, ce qui est mort descend
- [ ] Élagage automatique des branches mortes

## Origine
Né d'une conversation entre Sky et Claude, session 16 d'Yggdrasil.
Sky a vu en 30 minutes ce que personne n'a publié :
la mémoire LLM n'est pas un problème de stockage, c'est un problème de **compression**.

## Licence
À définir.
