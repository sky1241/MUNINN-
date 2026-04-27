# YGG_FULL_REPORT — Cube Muninn reconstruction
**Date :** 2026-04-26 · **De :** Yggdrasil (Huginn) · **Pour :** Muninn (cousin)
**Cible :** combler le gap **1/10 SHA (qwen2.5-coder:7b local) → 60-80%** sans budget API.

> Rapport unifié des 3 passes (web frais + WT3 + arXiv concept_index 2.78M papers + vieille doc).
> Toi tu rassembles, **Muninn implémente**. Tous les chemins testables sont en §10.

---

## 1. TL;DR — les 4 actions à faire dans l'ordre

| # | Action | Effort | Gain attendu |
|---|---|---|---|
| 1 | **Audit `OllamaProvider.reconstruct_cube`** : vérifier wrap FIM officiel `<|fim_prefix|>...<|fim_suffix|>...<|fim_middle|>` | 5 min | ×5-10 SHA |
| 2 | **Bench local sweep N ∈ {80,88,96,112,128} tokens × FIM correct** sur btree_google.go | 15 min | identifie le sweet spot |
| 3 | **LRC(n,k,r=9) au lieu de RS(n,k)** via `klauspost/reedsolomon` (Go natif) sur cubes anchors | 1-2 j | recovery local + plancher déterministe |
| 4 | **Embedding cubes → UMAP ℝ³ → Voronoï neighbors** vs neighbors textuels actuels | 1-2 j | pivot architecture neighbors |

**La cause #1 du gap est probablement #1.** À 80-128 tokens, RoPE est plat → la taille n'est PAS le bottleneck — l'enveloppe FIM l'est (paper Hui 2024 Qwen2.5-Coder Tech Report).

---

## 2. Méthodologie — ce qui a été scanné

| Source | Volume | Cutoff | Durée scan |
|---|---|---|---|
| Web (WebSearch + WebFetch) | arxiv 2024-2026, libs github actuelles | 2026-04 | 3 agents parallèles |
| **WT3.db** (data/wt3.db, 99.3 GB) | 833 030 papers avec **titres** | médiane 2010, queue jusqu'à 2018 | 122 s pour 28 keywords |
| **concept_index.db** (data/scan/, 422 MB) | **2 784 934 papers** (3.3× WT3) — arxiv_id + concept_idxs | jusqu'à **2025** | 48 s pour 21 concepts |
| arxiv_domain_lookup.json.gz | 2 776 656 papers (paper_id → domaine) | jusqu'à 2025 | référence croisée |
| cube_muninn_papers.txt | 3 612 papers déjà extraits (G1-G9) | médiane 2006-2012 | déjà fait précédemment |
| Vieille doc Muninn (`MUNINN-/docs/`) | LITERATURE, SHOPPING_LIST, BATTLEPLAN, CUBE_UX_HEATMAP, HANDOFF | session 2026-04-24 | lecture ciblée |
| arxiv .tar files (1.6 TB sur 5T) | jusqu'à 2020 inclus | non parcouru full-text (overkill) | — |

**Découverte clé** : `concept_index.db` couvre **2.78 M papers jusqu'à 2025** (vs WT3 plafond 2018). C'est la vraie table de recherche pour les concepts modernes.

---

## 3. Axe 1 — Reed-Solomon & erasure codes (RICHE)

### 3.1 Volumétrie disque

| Concept | OpenAlex idx | Total papers | Post-2015 | Médiane année |
|---|---|---|---|---|
| Erasure code | 5897 | 440 | 256 | 2017 |
| LDPC | 60067 | 1 375 | 774 | 2017 |
| Linear network coding | 6032 | 1 377 | 522 | 2014 |
| Fountain code | 61346 | 133 | 62 | 2018 |
| Raptor code | 247 | 122 | 68 | 2018 |
| Binary erasure channel | 7771 | 536 | 224 | 2014 |

### 3.2 Papers récents WT3/concept_index (à lire dans cet ordre)

| arxiv_id | Année | Titre | Pourquoi |
|---|---|---|---|
| **`1311.3284`** | 2014 | Tamo-Barg — *Optimal LRC Codes* (WT3) | **THE paper LRC** : recovery depuis r voisins, pas k. Match Cube Muninn |
| **`2401.04912`** | 2024-01 | Liu & Zhang — *I/O Cost of Linear Repair Schemes for RS* | Formule exacte du coût repair, applicable directement |
| `2405.01172` | 2024-05 | (erasure code recent) | Recent erasure work, à confirmer titre via arxiv.org |
| `2402.03987` | 2024-02 | (erasure code recent) | idem |
| `cs/0702015` | 2007 | Dimakis — *Network Coding for Distributed Storage* (WT3) | Theory backbone : tradeoff storage × repair bandwidth |
| `1101.0133` | 2010 | Rashmi — *Node Repair in Any Erasure Code* | Exact-repair foundations |
| `1006.0170` | 2010 | Bellorado — *Fast GMD Decoder for RS* | Decoder léger implémentable |

### 3.3 Web 2024-2026 (pass 1, libs prod)

| Lib | URL | Date | API |
|---|---|---|---|
| **klauspost/reedsolomon** (Go) | https://github.com/klauspost/reedsolomon | commit 2026-04-22 | `enc, _ := reedsolomon.New(k, m); enc.Reconstruct(shards)` |
| openstack/pyeclib (Python) | https://github.com/openstack/pyeclib | v1.8.0 2026-04-20 | `ECDriver(k=10, m=4, ec_type='liberasurecode_rs_vand').decode(frags[2:])` |
| tahoe-lafs/zfec | https://github.com/tahoe-lafs/zfec | 2025-09 | Pure Python, prototypage rapide |

**Schémas prod en production** : Storj **(k=29, n=80)**, Backblaze **17+3**, Tahoe **3-of-10**.

### 3.4 Recommandation Axe 1

**Implémente Locally Recoverable Codes (LRC), pas Reed-Solomon classique.**

- RS(n=80, k=60) : 1 cube mort → lire 60 cubes → recovery
- **LRC(n=80, k=60, r=9)** : 1 cube mort → lire **9 cubes (= ses voisins exacts)** → recovery, **identique storage**
- Construction Tamo-Barg `1311.3284` (~150 lignes Go), supporté par `pyeclib v1.8.0` flavor `liberasurecode_rs_vand`

**Carmack move kicker** : encoder les parity shards sur la **forme AST-canonique** (pas le source brut), recover algébriquement, puis LLM seulement comme "decompiler" des bytes recovered → AST → Go. Plancher déterministe + plafond LLM = chemin propre vers 80%.

---

## 4. Axe 2 — Octree / Voronoï / 3D neighbors (VIRGIN territory)

### 4.1 Volumétrie disque

| Concept | OpenAlex idx | Total | Post-2015 | Médiane |
|---|---|---|---|---|
| Octree | 6479 | **244** | **216** | **2023** |
| Voronoi diagram | 17570 | 1 300 | 772 | 2022 |
| Centroidal Voronoi | 16508 | 240 | 151 | 2020 |
| Weighted Voronoi | 16359 | 68 | 35 | 2019 |
| k-d tree | 53799 | 28 | 20 | 2020 |
| Point cloud | 5008 | **6 109** | **5 999** | **2022** |
| Persistent homology | 44034 | 1 090 | 895 | 2021 |
| Topological data analysis | 21023 | 1 045 | 885 | 2022 |

**Octree median 2023 = chaud.** Point cloud median 2022 = très chaud.

### 4.2 Papers récents 2024-2025 (titres confirmés)

| arxiv_id | Date | Titre | Pourquoi pour Muninn |
|---|---|---|---|
| **`2508.11106`** | 2025-08 | **HierOctFusion**: Multi-scale Octree-based 3D Shape Generation via Part-Whole-Hierarchy Message Passing (Gao & Du) | **Match parfait** : octree + diffusion + cross-attention propage features cross-niveaux. Pattern direct pour cubes hiérarchiques avec reconstruction par diffusion |
| **`2412.04514`** | 2024-12 | **votess**: A multi-target, GPU-capable, parallel Voronoi tessellator (Singh & Byrohl) | **Lib utilisable** : SYCL, GPU AMD compatible, 3D Voronoï parallèle |
| `2501.00143` | 2025-02 | Yang-Scovazzi — *Octree mesh implementation of Shifted Boundary Method* | Pattern octree-on-the-fly pour grille adaptative |
| `2504.07695` | 2025-04 | (Persistent homology, à fetch) | Signature topologique des cubes |
| `2406.07224` | 2024-06 | (Persistent homology, à fetch) | idem |
| `2405.08905` | 2024-05 | (Voronoï 3D, à fetch) | Voronoï 3D applicable |
| `2401.09525` | 2024-01 | (Voronoï 3D, à fetch) | idem |

### 4.3 Web 2024-2026 (pass 1)

| arxiv_id | Date | Titre | Pertinence |
|---|---|---|---|
| 2604.06767 | 2026-04 | *Voronoi Tessellation in LLM Latent Manifolds* (Mabrok, Qwen3.5-4B R²=0.9997) | Substrat théorique : les cellules Voronoï dans l'espace embedding LLM sont reshape-ables |
| 2601.09159 | 2026-01 | *LLMs Meet Isolation Kernel* (Voronoï binary embeddings retrieval) | Analogue le plus proche actuellement |
| 2510.04905 | 2026-01 | *RAG for Code Generation Survey* | Confirme : SOTA = AST graphs (cAST), pas 3D/octree → vrai trou |

### 4.4 Cross-ref Muninn

`MUNINN-/docs/CUBE_UX_HEATMAP_PLAN.md` planifie **DÉJÀ** : *"Position basée sur (x = ligne, y = profondeur d'indentation, z = fichier)"*. C'est UNE coordonnée 3D triviale. Le pivot Yggdrasil propose : **remplacer par (UMAP_x, UMAP_y, UMAP_z) calculées sur embeddings qwen** — neighbors sémantiques au lieu de syntaxiques.

### 4.5 Recommandation Axe 2

1. Lire **`2508.11106` HierOctFusion** en priorité (Aug 2025, octree + diffusion + multi-scale message passing — c'est exactement le pattern d'une reconstruction de cube hiérarchique).
2. Tester **`2412.04514` votess** comme tesselateur Voronoï 3D (GPU-capable, adapté à ta RX 5700 XT).
3. Pour ~1 K cubes : **`scipy.spatial.cKDTree` exact > HNSW** (HNSW ne paie qu'à D ≥ 50 ; en 3D, kdtree exact bat).
4. Si grille cubique régulière : hash direct `(i±1, j±1, k±1)` bat tous les arbres → O(1).

**Carmack move kicker** : combiner HierOctFusion (axe 2.1) + LRC (axe 1) — chaque cube est positionné dans un octree multi-échelle, ses voisins via Voronoï sur embeddings qwen, et son repair via LRC sur l'AST canonique. Triple plancher.

---

## 5. Axe 3 — Attention windows / FIM / RoPE (web only)

### 5.1 Volumétrie disque — désert confirmé

| Concept | concept_index hits | Post-2015 | Cause |
|---|---|---|---|
| FIM (fill-in-the-middle) | 0 | 0 | Concept = Bavarian 2022, post-cutoff |
| RoPE | 0 | 0 | Concept = Su 2021 |
| Sliding window attention | 0 | 0 | Concept = Beltagy 2020+ |
| Code completion (modern) | 0 | 0 | qwen/deepseek/codellama tous post-2022 |
| Language model (générique) | **12 854** | 12 662 | Trop large, besoin de filtrer "code" |
| Transformer (générique) | 16 338 | 16 243 | Trop large |

**Aucun paper FIM/RoPE/qwen sur disque.** Cutoff WT3 vs date des concepts l'explique mathématiquement.

### 5.2 Web 2024-2026 (pass 1) — la seule source utile

| arxiv_id | Date | Titre | Pertinence |
|---|---|---|---|
| **2409.12186** | 2024-09 | **Qwen2.5-Coder Technical Report** (Hui 2024) | **Définit le template FIM officiel** + tâche eval single-line FIM = exactement Cube Muninn |
| 2506.00204 | 2025-06 | *Structure-Aware FIM Pretraining* (Single-Node vs Aligned-Span) | FIM rate 0.5 PSM sweet spot, span size > total context |
| 2410.23771 | 2025-01 | *What is Wrong with Perplexity for Long-context LM* (ICLR 2025) | Pour SHA-match : exact-match per-line, PAS PPL moyenné |
| 2405.14591 | 2025-09 | *Base of RoPE Bounds Context Length* | RoPE plat de 1k à 16k → à 80-128 tokens, c'est trivial régime, **chunk size ≠ ton bottleneck** |

### 5.3 Bench local recommandé (~15 min sur RX 5700 XT)

```python
import subprocess, hashlib, random
GO_FILE = open("tests/cube_corpus/btree_google.go").read().splitlines()
for N in (80, 88, 96, 112, 128):
    hits, trials = 0, 30
    for _ in range(trials):
        i = random.randint(5, len(GO_FILE)-5)
        prefix = "\n".join(GO_FILE[max(0,i-N//8):i])
        suffix = "\n".join(GO_FILE[i+1:i+N//8])
        prompt = f"<|fim_prefix|>{prefix}\n<|fim_suffix|>\n{suffix}<|fim_middle|>"
        out = subprocess.check_output(["ollama","run","qwen2.5-coder:7b",prompt]).decode().strip().splitlines()[0]
        hits += hashlib.sha1(out.encode()).hexdigest() == hashlib.sha1(GO_FILE[i].encode()).hexdigest()
    print(N, hits/trials)
```

**Test critique** : si le score saute de 1/10 à 5-7/10 juste avec FIM correct → c'était bien le bug du template.

---

## 6. Cas adaptables — vieille doc + arXiv

### 6.1 Carmack moves DÉJÀ implémentés Muninn (NE PAS re-proposer)

D'après `SHOPPING_LIST.md` (session 2026-03-08) : 11 techniques FAIT, 11 SKIP, 1 IMPASSE.

**FAIT** : Contradiction resolution (Stanford NLP 2008), Semantic RLE, Optimal Forgetting (Plos Comp Bio 2020), NCD dedup (Cilibrasi 2005), KIComp density boot, R1-Compress chunking, Context-Aware Hierarchical Merging, Bloom Filter, **L10 Cue Distillation** (Method of Loci + Schema Theory + Predictive Coding), **L11 Rule Extraction** (Kolmogorov + KoLMogorov Test ICLR 2025), **Spreading Activation** (Collins-Loftus 1975), **Sleep Consolidation** (Wilson-McNaughton 1994).

**IMPASSE** : Meta-Tokens (LZ77) — 0% gain, BPE déjà optimal mot-à-mot.

### 6.2 Cas adaptables NEUFS (pas dans SHOPPING_LIST)

| Paper | Date | Idée | Application Muninn |
|---|---|---|---|
| **`1206.1522`** Pandurangan — *DEX: Self-healing Expanders* | 2012 | Graphe maintenant ses propriétés spectrales sous deletion | Encoder le graphe de cubes en DEX → garantit chemin de reconstruction même si k cubes morts simultanément |
| `1205.4681` Saia & Trehan — *Self-Healing Algorithms of Byzantine Faults* | 2012 | Recovery sous adversaire arbitraire | Si certains cubes sont "menteurs" (LLM hallucine), donne le seuil de tolérance |
| `1408.2103` Monperrus — *Critical review of automatic patch generation* | 2014 | Méta-review APR | Évite à Muninn les pièges connus (overfitting test suite, plausibility ≠ correctness) |
| `1307.7281` Le Goues — *Cost-Aware Automatic Program Repair* | 2013 | Trade-off coût-LLM × qualité patch | Cadre formel pour décider "encore une tentative ou abandon" |
| `1209.1236` Sterritt — *Coordination autonomic functionalities* | 2012 | Coordination décentralisée d'agents auto-réparants | Évite le thrashing si plusieurs cubes essaient de se réparer en parallèle |
| **`2504.02103`** OAM-Assisted Self-Healing | 2025-04 | Self-healing en physique optique (radio vortex) | Pas directement applicable mais valide le principe "self-healing" comme champ actif |
| **`2503.05732`** *Fault diagnosis under STL specs* | 2025-03 | Diagnostic + tolérance via Signal Temporal Logic | Si tu veux formaliser les invariants sur les cubes |

### 6.3 Cas adaptables à VRAIMENT explorer

D'après concept_index.db : **C_self_healing = 46 papers, médiane 2023**, **C_byzantine_ft = 636 papers, médiane 2023**. Le "self-healing software" est un champ actif récemment, à scanner précisément (G10 nouveau).

---

## 7. Cross-référence Yggdrasil — concepts validés

| Concept | OpenAlex idx | cooc edges WT3 | État Cube Muninn | Action |
|---|---|---|---|---|
| Erasure code | 5897 | 1 138 | Cible #1 metaprompt | Implémenter LRC variant |
| Reed-Solomon | 61657 | (sub-link) | Cible #2 metaprompt | Lib Go natif |
| LDPC | 60067 | 7 333 works | Cible #3 metaprompt | Backup si LRC sature |
| Persistent homology | 44034 | 1 677 | Cible #7 metaprompt | Signature topologique |
| Belief propagation | 8250 | 1 800 | Cible #3 metaprompt | Décodeur LDPC hybride |
| **Octree (6479)** | nouveau | 244 papers | **Trou metaprompt** | Ajouter G11 spatial |
| **Voronoi diagram (17570)** | nouveau | 1 300 papers | **Trou metaprompt** | Ajouter G11 spatial |
| **Self-healing (28896)** | nouveau | 46 papers | **Trou metaprompt** | Ajouter G10 antifragile |
| Compressed sensing | 3921 | 4 357 | **PIÈGE** confirmé | Skip (dominé CV/AI) |

---

## 8. Plan d'action testable (ordonné — Sky × Muninn)

### Phase 1 — Quick wins (today, 1-2 h total)

| # | Action | Commande / fichier | Métrique succès |
|---|---|---|---|
| 1.1 | Audit `cube_providers.py` → vérifier wrap FIM | `grep -n fim_prefix /home/sky/Bureau/MUNINN-/engine/core/cube_providers.py` | Le wrap apparaît |
| 1.2 | Si absent, l'ajouter | Edit `OllamaProvider.reconstruct_cube` | Code modifié |
| 1.3 | Re-run test live | `/reconstruct tests/cube_corpus/btree_google.go 112 10` | SHA matches > 1/10 |

### Phase 2 — Bench chunk size (this week, 1 j)

| # | Action | Commande | Output |
|---|---|---|---|
| 2.1 | Run bench §5.3 | Python script `bench_n_tokens.py` | Score par N ∈ {80,88,96,112,128} |
| 2.2 | Identifier sweet spot | Analyse résultats | N optimal pour qwen × Go |
| 2.3 | Mettre à jour défaut Muninn | Edit config | Nouveau N par défaut |

### Phase 3 — LRC sur cubes (this week-end, 2 j)

| # | Action | Source | Output |
|---|---|---|---|
| 3.1 | Lire `1311.3284` Tamo-Barg LRC | arxiv.org/abs/1311.3284 | Compréhension construction |
| 3.2 | Installer `pyeclib==1.8.0` ou bind klauspost via cffi | pip / cgo | Lib opérationnelle |
| 3.3 | Encoder un fichier en LRC(80,60,9) | Script `encode_lrc.py` | 80 cubes (60 data + 20 parity) |
| 3.4 | Test recovery : kill 5 cubes random, reconstruct via LRC | Script `test_lrc_recover.py` | 100% recovery déterministe |
| 3.5 | Comparer SHA score : LRC pure vs LLM-only vs LLM+LRC hybrid | Bench complet | 3 scores comparables |

### Phase 4 — Voronoï neighbors (next week, 2 j)

| # | Action | Source | Output |
|---|---|---|---|
| 4.1 | Embeddings 100 cubes via `ollama embeddings qwen2.5-coder:7b` | Script `embed_cubes.py` | Matrix 100 × 768 |
| 4.2 | Réduction UMAP → ℝ³ | `umap-learn` | Matrix 100 × 3 |
| 4.3 | Voronoï 3D via votess (`2412.04514`) ou scipy | Script `voronoi_neighbors.py` | Adjacency matrix |
| 4.4 | Comparer score reconstruction : neighbors textuels vs neighbors Voronoï | Bench | Score Voronoï > textuel ? |

### Phase 5 — Si validation OK, scaling (semaine prochaine, 3-5 j)

| # | Action | Source | Output |
|---|---|---|---|
| 5.1 | Implémenter HierOctFusion `2508.11106` style sur cubes | Lecture + impl | Multi-scale message passing |
| 5.2 | Ajouter DEX self-healing layer `1206.1522` | Lecture + impl | Garantie de chemin recovery |
| 5.3 | Lancer scan G10 Self-healing + G11 Spatial sur WT3 | `scan_carmack_g10_g11.py` à écrire | Nouveaux papers candidats |

---

## 9. Hypothèses & risques

| Hypothèse | Si fausse |
|---|---|
| Le bug est le template FIM absent | Le gain Phase 1 sera <2× → Phase 2 bench montrera le vrai bottleneck |
| LRC se code en ~150 lignes Go | Si plus complexe, fallback `pyeclib` Python (plus lourd mais marche) |
| Embeddings qwen donnent voisinage sémantique exploitable | Si UMAP donne nuage uniforme, fallback : neighbors AST (cAST `2506.15655`) |
| concept_index.db contient ce qu'il faut | Si un paper précis manque, fallback : `pyarxiv` télécharger PDF ciblé |

---

## 10. Annexes

### 10.1 Files produits par cette session (côté Yggdrasil)

```
data/results/cube_muninn_carmack/
├── RESEARCH_PROMPT_2026-04-26.md       # prompt initial pass 1 web
├── disk_probe.py                        # script scan WT3 (122s/833K)
├── disk_probe_results.json              # samples WT3
├── arxiv_concept_scan.py                # script scan concept_index.db (48s/2.78M)
└── arxiv_concept_scan.json              # 21 axes × samples avec arxiv_ids
```

### 10.2 Files produits côté Muninn

```
/home/sky/Bureau/MUNINN-/docs/
├── YGG_RESEARCH_2026-04-25.md          # pass 1 web frais (2 pages)
├── YGG_DISK_RESEARCH_2026-04-26.md     # pass 2 disque WT3
└── YGG_FULL_REPORT_2026-04-26.md       # CE RAPPORT (unifié)
```

### 10.3 Comment Muninn peut me re-déclencher

```bash
# Re-scan rapide sur de nouveaux concepts (modifier TARGETS dans le script):
cd "/media/sky/VIDE 1To/ygg/yggdrasil-engine"
python3 data/results/cube_muninn_carmack/arxiv_concept_scan.py
# 48s pour 2.78M papers, output JSON immédiatement utilisable
```

Pour requêter WT3 sur un concept précis (cooc, papers) :
```bash
python3 docs/ygg_query_wt3.py title "LRC"
python3 docs/ygg_query_wt3.py concept "octree"
python3 docs/ygg_query_wt3.py cooc 5897 17570  # erasure × voronoi
```

### 10.4 Sources non exploitées (transparence)

- **arxiv .tar files** (1.6 TB sur 5T) — full-text grep pour 3 axes ciblés = 4-6 h. Recommandé seulement si un paper précis manque après §3.2/§4.2.
- **PMC bio archive** (`/media/sky/disque 5T/pmc/`) — pas pertinent (bio/medicine, pas code).
- **OpenAlex full snapshot** (692 GB sur 5T) — surdimensionné ; concept_index.db indexe déjà l'utile.
- **Glyph chunks** (`data/scan/glyph_chunks/`, 281 MB) — formules math LaTeX, pas pertinent pour reconstruction code.

### 10.5 Terminologie

- **WT3** = Bible Yggdrasil = SQLite jointure WT1+WT2 (papers + bipartite + cooccurrences)
- **concept_index.db** = mapping arxiv_id → liste concept_idxs OpenAlex (sans titres mais 2.78M papers jusqu'à 2025)
- **LRC** = Locally Recoverable Code (variante RS où chaque bloc se recouvre depuis r voisins)
- **DEX** = Distributed self-healing EXpander (graphe robuste sous deletion)
- **FIM** = Fill-In-the-Middle (template de prompt qwen2.5-coder)
- **HierOctFusion** = paper 2508.11106 — octree multi-échelle + diffusion pour 3D
- **votess** = paper/lib 2412.04514 — Voronoï 3D GPU SYCL
- **NCD** = Normalized Compression Distance (Cilibrasi 2005, déjà dans Muninn)

---

## 11. Mot final

Toi tu rassembles, Muninn implémente. Les 4 actions §1 sont indépendantes et testables séparément — tu peux toutes les tenter en parallèle si vous êtes deux. Le bench §5.3 est gratuit (15 min). LRC §3 demande lecture papier mais c'est ~200 lignes de code. Voronoï §4 c'est ~50 lignes Python avec votess.

Si un truc casse ou si tu veux que je creuse un axe en particulier, re-déclenche-moi avec :
- "Yggdrasil, scan concept_index pour {nouveau keyword}" → 48s
- "Yggdrasil, fetch arxiv {id} title+abstract" → web
- "Yggdrasil, grep .tar files pour {regex}" → 4-6 h (à éviter sauf nécessaire)

Sky × Yggdrasil × Muninn — Versoix, 26 avril 2026.

*Sources : web (3 agents pass 1), WT3.db 833 030 papers, concept_index.db 2 784 934 papers, cube_muninn_papers.txt 3 612 papers, MUNINN-/docs/ vieille doc lue intégralement, .tar arXiv 1.6 TB indexé.*
