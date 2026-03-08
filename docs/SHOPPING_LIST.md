# Muninn — Shopping List (techniques a implementer)

> Trouvees le 8 mars 2026. A implementer apres 2-3 semaines de test en prod.

## Tier 1 — Zero dependance, gain prouve

| # | Technique | Source | Gain | Lignes | Status |
|---|-----------|--------|------|--------|--------|
| 1 | Meta-Tokens (LZ77 pour prompts) | ACL 2025 | 15-27% lossless | ~100 | TODO |
| 2 | Merge semantique de lignes | SimpleMem 2026 | 10-20% | ~60 | TODO |
| 3 | Contradiction resolution (numeric mismatch) | Stanford NLP 2008 + Mem0 | Correctesse long-terme | ~60 | TODO |
| 4 | Semantic RLE (collapse boucles debug/retry) | Concept classique | 10-30% sur sessions chaotiques | ~100 | TODO |
| 5 | Optimal Forgetting (temperature -> compression depth) | Neurosciences 2020 | Densite long-terme | ~50 | TODO |
| 6 | NCD dedup (zlib similarity) | Cilibrasi 2005 | Catch doublons semantiques en 20 lignes | ~20 | TODO |

## Tier 2 — pip install, gros gain

| # | Technique | Source | Gain | Dep | Status |
|---|-----------|--------|------|-----|--------|
| 7 | Word Graph Sentence Fusion | Filippova 2010 | Merge N phrases -> 1 phrase optimale | pip takahe | TODO |
| 8 | SemHash dedup semantique | MinishLab 2025 | 10-30% | pip semhash | TODO |
| 9 | token-reducer (entity abstraction) | PyPI 2025 | 5-15% | pip token-reducer | TODO |
| 10 | Selective-Context (self-info pruning) | EMNLP 2023 | 30-50% | pip selective-context + GPT-2 | TODO |
| 11 | Sequitur (grammar-based compression) | Nevill-Manning 1997 | Decouvre patterns repetes en O(n) | ~150 ou pip | TODO |
| 12 | Zstd dictionnaire entraine | Facebook 2016 | Compression binaire x10 sur .mn | pip zstandard | TODO |

## Tier 3 — Plus lourd, gain qualitatif

| # | Technique | Source | Gain | Status |
|---|-----------|--------|------|--------|
| 13 | KIComp density scoring au boot | Expert Systems 2025 | 20-40% au boot | TODO |
| 14 | EAT reasoning truncation | NeurIPS 2025 | 10-15% | TODO |
| 15 | R1-Compress chunking pour L9 | NeurIPS 2025 Workshop | Meilleure qualite L9 | TODO |
| 16 | A-MEM Zettelkasten linking | NeurIPS 2025 | Meilleur retrieval | TODO |
| 17 | ACON self-improving L9 prompt | 2025 | +8% fact retention | TODO |
| 18 | Context-Aware Hierarchical Merging | ACL 2025 | Anti-hallucination au merge | TODO |
| 19 | TextRank importance scoring | Mihalcea 2004 | Compression depth par importance | TODO |
| 20 | Bloom Filter concept tracking | Classique | Skip faits deja charges au boot | TODO |

## Impasses confirmees (ne PAS implementer)

| Idee | Pourquoi ca marche pas |
|------|----------------------|
| Enlever les voyelles | BPE eclate en caracteres = +110% tokens |
| Synonymes plus courts | BPE gere deja les mots longs en 1 token |
| Sinogrammes/symboles | 2-3 tokens par sinogramme vs 1 pour l'anglais |
| Format TOON/CSV pour .mn | Pipes, virgules, tabs = meme cout que espaces |

## Insight cle: pourquoi l'optimisation mot-a-mot est morte

Le tokenizer BPE (cl100k_base) est entraine sur des milliards de mots anglais.
"compression", "documentation", "implementation" = tous 1 seul token.
On ne peut PAS battre le tokenizer au niveau du mot individuel.

Les gains restants sont STRUCTURELS:
- Eliminer les REPETITIONS de groupes de mots (Meta-Tokens, Sequitur)
- Fusionner les PHRASES SIMILAIRES (Word Graph, merge semantique)
- Supprimer les CONTRADICTIONS (numeric mismatch, last writer wins)
- Compresser les VIEUX SOUVENIRS plus fort (Optimal Forgetting)
- Collapser les BOUCLES DEBUG (Semantic RLE)

## Refs

### Modernes (2023-2026)
- Meta-Tokens: arxiv.org/abs/2506.00307
- SimpleMem: arxiv.org/abs/2601.02553
- SemHash: github.com/MinishLab/semhash
- token-reducer: pypi.org/project/token-reducer/
- selective-context: pypi.org/project/selective-context/
- KIComp: sciencedirect.com/science/article/abs/pii/S0957417425013600
- R1-Compress: arxiv.org/abs/2505.16838
- A-MEM: arxiv.org/abs/2502.12110
- ACON: arxiv.org/abs/2510.00615
- Context-Aware Hierarchical Merging: arxiv.org/abs/2502.00977

### Classiques (1997-2020)
- Sequitur: sequitur.info/jair (Nevill-Manning 1997)
- Word Graph Sentence Fusion: github.com/boudinfl/takahe (Filippova 2010)
- NCD: en.wikipedia.org/wiki/Normalized_compression_distance (Cilibrasi 2005)
- Finding Contradictions in Text: nlp.stanford.edu/pubs/contradiction-acl08.pdf (2008)
- Optimal Forgetting: journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008367 (2020)
- Sleep Replay: pmc.ncbi.nlm.nih.gov/articles/PMC7898724/ (2021)
- TextRank: Mihalcea & Tarau 2004
- Zstandard: facebook.github.io/zstd/
- Bloom Filter: en.wikipedia.org/wiki/Bloom_filter
- Information Bottleneck: arxiv.org/abs/physics/0004057 (Tishby 1999)
