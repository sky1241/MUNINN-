# Muninn — Shopping List (techniques a implementer)

> Trouvees le 8 mars 2026. 10 implementees (+ L10/L11 + Spreading Activation + Sleep Consolidation), 1 impasse confirmee, 11 skip.

## Tier 1 — Zero dependance, gain prouve

| # | Technique | Source | Gain | Status |
|---|-----------|--------|------|--------|
| 1 | Meta-Tokens (LZ77 pour prompts) | ACL 2025 | 15-27% lossless | **IMPASSE** — 0% sur texte deja compresse, BPE overhead |
| 2 | Merge semantique de lignes | SimpleMem 2026 | 10-20% | MAYBE — NCD couvre deja |
| 3 | Contradiction resolution (numeric mismatch) | Stanford NLP 2008 | Correctesse | **FAIT** — skeleton last-writer-wins |
| 4 | Semantic RLE (collapse boucles debug/retry) | Concept classique | 10-30% sessions | **FAIT** — 13msg->5 sur boucles debug |
| 5 | Optimal Forgetting (temperature -> compression) | Neurosciences 2020 | Densite long-terme | **FAIT** — re-compress cold via L9 in prune |
| 6 | NCD dedup (zlib similarity) | Cilibrasi 2005 | 5-8% boot | **FAIT** — remplace word-overlap P19 |

## Tier 2 — pip install, gros gain

| # | Technique | Source | Gain | Status |
|---|-----------|--------|------|--------|
| 7 | Word Graph Sentence Fusion | Filippova 2010 | Merge N phrases | SKIP — texte pre-compresse |
| 8 | SemHash dedup semantique | MinishLab 2025 | 10-30% | SKIP — NCD fait le job sans dep |
| 9 | token-reducer (entity abstraction) | PyPI 2025 | 5-15% | SKIP — redondant L3+L5+L6 |
| 10 | Selective-Context (self-info pruning) | EMNLP 2023 | 30-50% | SKIP — GPT-2 500MB, L2+L9 couvrent |
| 11 | Sequitur (grammar-based compression) | Nevill-Manning 1997 | patterns O(n) | MAYBE — overlap Meta-Tokens |
| 12 | Zstd dictionnaire entraine | Facebook 2016 | x10 binaire | SKIP — mauvais niveau (bytes pas texte) |

## Tier 3 — Plus lourd, gain qualitatif

| # | Technique | Source | Gain | Status |
|---|-----------|--------|------|--------|
| 13 | KIComp density scoring au boot | Expert Systems 2025 | 20-30% boot overflow | **FAIT** — drop low-density on overflow |
| 14 | EAT reasoning truncation | NeurIPS 2025 | 10-15% | MAYBE — overlap Semantic RLE |
| 15 | R1-Compress chunking pour L9 | NeurIPS 2025 Workshop | Qualite L9 | **FAIT** — section-aware API calls >8K |
| 16 | A-MEM Zettelkasten linking | NeurIPS 2025 | Meilleur retrieval | SKIP — =mycelium+tree |
| 17 | ACON self-improving L9 prompt | 2025 | +8% fact retention | LATER — needs eval infra |
| 18 | Context-Aware Hierarchical Merging | ACL 2025 | Anti-hallucination | **FAIT** — contradiction+dedup on merge |
| 19 | TextRank importance scoring | Mihalcea 2004 | Importance scoring | MAYBE — P25 tags suffisent |
| 20 | Bloom Filter concept tracking | Classique | 10-15% boot | **FAIT** — skip <10% novelty branches |

## Impasses confirmees (ne PAS implementer)

| Idee | Pourquoi ca marche pas |
|------|----------------------|
| Enlever les voyelles | BPE eclate en caracteres = +110% tokens |
| Synonymes plus courts | BPE gere deja les mots longs en 1 token |
| Sinogrammes/symboles | 2-3 tokens par sinogramme vs 1 pour l'anglais |
| Format TOON/CSV pour .mn | Pipes, virgules, tabs = meme cout que espaces |
| Meta-Tokens (LZ77) | 0% gain — texte deja compresse par L1-L7, n-grams trop courts pour BPE |

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
- Virer la CONNAISSANCE GENERIQUE que le LLM sait deja (L10 Cue Distillation)
- Factoriser les PATTERNS REPETITIFS en regles (L11 Rule Extraction)

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

### L10/L11 — Carmack moves (session 2026-03-08)
- L10 Cue Distillation: Method of Loci (500 BC) + Schema Theory (Bartlett 1932) + Predictive Coding (Rao & Ballard 1999)
- L11 Rule Extraction: Kolmogorov Complexity (1965) + KoLMogorov Test (ICLR 2025)
- Selective-Context: aclanthology.org/2023.emnlp-main.391/ (self-information, syntactic — L10 is semantic)
- LAMA Probes: github.com/facebookresearch/LAMA (Facebook 2019, parametric knowledge probing)
- Prompt Compression Survey: arxiv.org/abs/2410.12388 (NAACL 2025)
- SuRe: Surprise-Driven Replay: arxiv.org/abs/2511.22367 (ICLR 2025)
- KoLMogorov Test: openreview.net/forum?id=C45YqeBDUM (ICLR 2025)
- Gain: WEARABLE.md x19.4 -> x23.1 (+19%), L9 input reduced 38%

### Spreading Activation — Carmack move #4 (session 2026-03-08)
- Collins & Loftus 1975: Spreading activation through semantic networks
- Replaces pure TF-IDF keyword matching with semantic propagation in boot()
- Mycelium IS already a weighted semantic network — just needed the propagation algo
- boot() scoring: 0.15 recency + 0.15 importance + 0.5 tfidf + 0.2 activation
- Gain: retrieval quality (finds branches with zero keyword overlap)

### Sleep Consolidation — Carmack move #3 (session 2026-03-08)
- Wilson & McNaughton 1994: episodic->semantic consolidation during sleep
- _sleep_consolidate() in prune(): NCD groups similar cold branches, merges via pipeline
- Zero API cost (dedup + contradiction + L10 + L11 only)
- Tested: 2 codec branches (NCD=0.57) merged, architecture branch preserved
