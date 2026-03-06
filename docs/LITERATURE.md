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

### Nouveaux papiers 2025-2026 (decouverts session 2026-03-06)

| Papier | Idee cle | Ratio | Pertinence Muninn |
|--------|----------|-------|-------------------|
| MemOS (Li 2025) | Memory OS 3 couches: API/scheduling/storage | N/A | Architecture proche — mais top-down corporate, pas bottom-up boucher |
| MemoryOS (EMNLP 2025 Oral) | OS memoire pour agents personnalises | N/A | Persistent memory + user profiles |
| KVzip (NeurIPS 2025 Oral, top 0.35%) | Compression KV cache 3-4x, query-agnostic | 3-4x | Bas niveau (KV cache), nous = haut niveau (semantique) |
| Mem0 (commercial) | "Memory layer for AI apps" | N/A | Produit commercial, pas open-research |
| Word2Vec (Mikolov 2013) | Co-occurrence = meaning, vectors from context | N/A | FONDATION du mycelium — mots qui co-apparaissent = sens lie |
| GloVe (Pennington 2014) | Global vectors from co-occurrence matrix | N/A | Matrice co-occurrence -> embedding. Notre mycelium = GloVe artisanal |
| LLM-Codebook (2025) | Codebooks appris > codebooks manuels | Extreme | Confirme: codebook statique (CODEBOOK.json) est sous-optimal |
| Huff-LLM (2025) | Huffman sur poids LLM end-to-end | N/A | Modele-level, pas applicable directement |

### Concepts fondamentaux empruntes

| Concept | Source | Application Muninn |
|---------|--------|-------------------|
| Co-occurrence = sens | Word2Vec, GloVe | Le mycelium tracke les co-occurrences pour fusionner les concepts |
| Gulf of execution/evaluation | Norman (1988) | Les chirurgiens construisent pour des chirurgiens, pas pour des bouchers |
| Layered memory hierarchy | MemOS | Root (working) / branches (long-term) / leaves (cold archive) |
| Query-agnostic compression | KVzip | Le mycelium compresse AVANT de savoir la query (offline) |
| Living codebook | LLM-Codebook | Codebooks appris > statiques. Notre mycelium APPREND par co-occurrence |

## Ce qui est unique a Muninn (pas dans la litterature)

- **Mycelium vivant** — codebook qui POUSSE par co-occurrence, decay biologique.
  Inspire de Word2Vec/GloVe mais a l'echelle d'un utilisateur, pas d'un corpus.
- **L-system fractal** — memes regles a chaque niveau d'arbre. Novel.
- **Approche boucher** — construit depuis le cote utilisateur non-expert,
  pas depuis le cote chercheur. Le probleme est invisible aux chirurgiens.
- **Zero acces modele** — pur fichier texte, pas de fine-tuning, pas de KV cache.
  Fonctionne sur n'importe quel LLM, n'importe quel provider.
- **BPE-native output** — compresse en anglais compact que le tokenizer lit nativement.
  Pas de codebook lookup, pas de sinogrammes, zero overhead de traduction.

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
- MemOS: arxiv.org/abs/2507.03724
- MemoryOS: github.com/BAI-LAB/MemoryOS
- KVzip: arxiv.org/abs/2511.01815
- Mem0: mem0.ai
- Word2Vec: arxiv.org/abs/1301.3781
- GloVe: nlp.stanford.edu/projects/glove/
- Norman: "The Design of Everyday Things" (1988)
