# Muninn — Etat de l'art compression memoire LLM

## Constraint
Muninn ne peut PAS fine-tuner le modele. On controle uniquement le texte
qui entre dans la fenetre de contexte. Seules les techniques text-level comptent.

## Papiers analyses

### Directement applicables

| Papier | Idee cle | Ratio | Ce qu'on vole |
|--------|----------|-------|---------------|
| MemGPT (Packer 2023) | LLM comme OS, memoire virtuelle paginee | N/A (paging) | Self-directed paging, tiered memory |
| MemWalker (Chen 2023) | Arbre de resumes, navigation interactive | N/A (tree nav) | Valide notre arbre L-system + pointeurs |
| LLMLingua-2 (Pan 2024) | Filtrage par self-information, compression prompt | 2-5x | Garder high-entropy, virer predictable |
| Selective Context (Li 2023) | Self-information = critere de compression | Variable | Strip boilerplate, keep numbers/noms |

### Inspirations (model-level mais idees volables)

| Papier | Idee cle | Ratio | Technique adaptable |
|--------|----------|-------|---------------------|
| Compressive Transformers (Rae 2020) | Memoire multi-granularite | 2-8x | Recent=detail, ancien=compresse |
| Gisting (Mu 2023) | Prompts comprimes en gist tokens | 26x | Principe du bottleneck |
| AutoCompressors (Chevalier 2023) | Compression recursive segmentee | N/A | Compression context-aware (pas redondant) |
| ICAE (Ge 2024) | Autoencoder in-context | 4x | Valide notre cible 3-4x |
| COCOM (Rau 2025) | Taux variable par importance | 5.69x speedup | Root 1.5x, branch 3x, leaf 6x |

## 5 techniques a integrer dans Muninn

1. **Compression conditionnelle a la query** — quand on charge une branche pour
   "architecture", ultra-compresser les infos "bugs" (LongLLMLingua)

2. **Compression variable par temperature** — root peu compresse (1.5x),
   branches moyennement (3x), feuilles froides fort (6x) (COCOM, Compressive)

3. **Self-information filtering** — garder nombres, dates, noms propres, metriques.
   Virer verbes, articles, connecteurs (Selective Context, LLMLingua)

4. **Compression recursive context-aware** — compresser noeud B en sachant
   ce que noeud A contient deja pour eviter redondance (AutoCompressors)

5. **Log de navigation** — tracker les chemins parcourus dans l'arbre pour
   feeder R4 promotion/elagage (MemWalker)

## Ce qui est unique a Muninn (pas dans la litterature)

- **L-system fractal** — memes regles a chaque niveau d'arbre. Novel.
- **Codebook texte Huffman semantique** — les autres = embeddings model-level.
  Nous = alphabet texte. Novel.
- **Zero acces modele** — pur fichier texte a 3-4x compression. Sous-explore.

## Refs
- MemGPT: arxiv.org/abs/2310.08560
- MemWalker: arxiv.org/abs/2310.05029
- LLMLingua-2: arxiv.org/abs/2403.12968
- Selective Context: arxiv.org/abs/2304.12102
- Compressive Transformers: arxiv.org/abs/1911.05507
- Gisting: arxiv.org/abs/2304.08467
- AutoCompressors: arxiv.org/abs/2305.14788
- ICAE: arxiv.org/abs/2307.06945
- COCOM: arxiv.org/abs/2407.09252
