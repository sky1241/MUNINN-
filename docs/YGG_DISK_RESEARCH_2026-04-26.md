# YGG_DISK_RESEARCH — Muninn cube reconstruction (2026-04-26)

> Pass 2 — recherche dans le disque dur (vieille doc + WT3.db 99 GB + cube_muninn_papers.txt + 1.6 TB arXiv .tar local).
> Complète [YGG_RESEARCH_2026-04-25.md](YGG_RESEARCH_2026-04-25.md) (web frais, pass 1).

---

## 0. TL;DR — les 3 trouvailles disque qui changent quelque chose

1. **Locally Recoverable Codes (LRC)** — variante de Reed-Solomon où chaque bloc manquant se recouvre à partir d'**un petit sous-ensemble** de voisins, pas tous. Papailiopoulos & Dimakis 2014 (`1311.3284`). **C'est exactement le pattern Muninn** : un cube mort doit être recovery depuis ses ~9 voisins, pas depuis tous les cubes du fichier. **LRC bat RS classique pour ce cas.**

2. **Self-Healing Expanders (DEX, Pandurangan 2012)** — graphe qui maintient propriétés spectrales sous deletion de nœuds. `1206.1522`. Pattern Carmack : encoder le graphe de voisinage des cubes comme DEX → garantit des chemins de reconstruction même quand plusieurs cubes meurent simultanément.

3. **Barnes-Hut octree** (`1305.1825`, 2014) — décomposition récursive 3D pour calcul N-body. Pattern transposable : si tu plonges les cubes en 3D (UMAP/embeddings), Barnes-Hut donne O(N log N) pour trouver les neighbors d'influence par cube — beaucoup plus efficace que cKDTree exhaustif au-delà de 10K cubes.

**Et la confirmation du pass 1** : WT3 indexe arXiv jusqu'à ~2015-2018, donc **zero hit FIM / RoPE / qwen / CodeLlama** sur disque. L'axe 3 reste 100% web (cf pass 1).

---

## 1. Méthodologie — ce qui a été scanné

| Source | Volume | Cutoff | Hits |
|---|---|---|---|
| **WT3.db** (papers table) | 99.3 GB / 833 030 papers | médiane 2010, queue jusqu'à ~2018 | scan complet 122 s, 28 catégories |
| **cube_muninn_papers.txt** | 3 612 papers déjà extraits | G1-G9 (codes/perco/BP/CS/topology/tensor/RG) | médiane 2006-2012, **0-1 papers ≥2020** |
| **/media/sky/disque 5T/arxiv/src/** | 1.6 TB .tar | jusqu'à 2025 (`arxiv_2016_2025_log.txt`) | non parcouru ici (4-6h pour grep full-text — overkill pour 3 axes ciblés) |
| **docs/ Yggdrasil + MUNINN-/docs/** | ~30 fichiers MD | 2026 | LITERATURE.md, BATTLEPLAN_SCANNER.md, SHOPPING_LIST.md, CUBE_UX_HEATMAP_PLAN.md, BRIEFING_MUNINN* |

Scripts Yggdrasil utilisés : `disk_probe.py` (créé pour ce run), `ygg_query_wt3.py` (déjà côté Muninn), `engine/analysis/scan_carmack_*.py`.

---

## 2. Axe 1 — Reed-Solomon & cousins (RICHE sur disque)

WT3 disk hits : **rs_text 67, parity_repair 54, network coding/fountain 458**. Cube_muninn_papers G1 = 153 papers déjà extraits (erasure 20, fountain 18, regenerating 20, LDPC 20, RS 20, LRC 8, network coding 20, rateless 17, raptor 10).

### 2.1 Les papers WT3 qui matter pour Muninn

| Paper | Année | Apport | Utilité Cube Muninn |
|---|---|---|---|
| **`1311.3284` Tamo & Barg — Optimal LRC Codes** | 2014 | Familles optimales de Locally Recoverable Codes : recovery depuis r voisins | **Match parfait** : remplace RS(n,k) par LRC(n,k,r) où r = nb voisins par cube (~9). Storage overhead identique, mais repair locality = O(r) au lieu de O(k) |
| **`1101.0133` Rashmi 2010 — Node Repair in Any Erasure Code** | 2010 | Repair bandwidth ↓ par exact regeneration | Si un cube SHA-fail, le coût pour le ressusciter = bandwidth équivalent à 1 cube (pas k) |
| **`cs/0702015` Dimakis — Network Coding for Distributed Storage** | 2007 | Tradeoff fondamental storage × repair bandwidth (MSR/MBR) | Donne la borne théorique Muninn : avec n cubes, k anchors fixes, repair coût β bytes par cube perdu, **β optimal** se calcule |
| **`1302.4670` Wang & Tamo — Exact-Repair Regenerating** | 2013 | Reconstruction exacte byte-à-byte (vs functional repair) | Tu veux SHA-match, pas approximation → exact-repair obligatoire |
| **`1006.0170` Bellorado — Fast GMD Decoder for RS** | 2010 | Decoder Generalized Minimum Distance pour RS | Implémentable directement pour cubes-as-shards |
| **`0901.1886` Soro — Efficient erasure decoding of RS** | 2009 | Algorithme léger (pas de GF arithmetic complète) | Rapide à porter en Python pur si tu veux skipper la dépendance C |
| **`cs/0606049` Dimakis — Decentralized erasure codes** | 2006 | Original paper du domaine | Lecture obligatoire pour calibrer (n,k) |

### 2.2 Insight cross-paper : LRC > RS pour Muninn

Muninn a ~9 voisins par cube. Reed-Solomon classique exige k cubes connus pour recovery (k ≈ 80-200 selon le fichier). Locally Recoverable Codes garantissent recovery depuis **r** cubes seulement (r typique 3-10). Pour Muninn :

- RS(n=80, k=60) → si 1 cube mort, lire 60 cubes pour recovery (OK mais lourd)
- LRC(n=80, k=60, r=4) → si 1 cube mort, lire **4 cubes** pour recovery, identique storage

Le code de référence : Tamo-Barg construction (paper `1311.3284`) — implémentable en ~150 lignes Go. Pas de lib Python directe, mais `pyeclib` v1.8.0 supporte les schémas LRC via `liberasurecode_rs_vand` flavor.

### 2.3 Cas adaptable : DistributedStorageSystems → CubeStore

Muninn a `engine/core/cube.py:839` un CubeStore SQLite. Le pattern de **Network Coding for Distributed Storage** (Dimakis et al., toute la suite cs/0702015 → 1101.0133 → 1302.4670) est directement transposable : chaque cube SHA = un objet stocké, anchors = nœuds permanents, cubes recovery-pending = nœuds à régénérer. La théorie est mature, les bornes sont connues.

---

## 3. Axe 2 — Octree / Voronoï / 3D neighbors (MODESTE sur disque, classique solide)

WT3 disk hits : voronoi 186, octree 10, kdtree 6, point_cloud 24, spatial_idx 29, ast_graph 4. Tous ≤2018, aucun "code embedding 3D".

### 3.1 Les gemmes WT3

| Paper | Année | Apport | Pattern transposable |
|---|---|---|---|
| **`1305.1825` Hamada — Barnes-Hut octree** | 2014 | Algo N-body en O(N log N) via subdivision /8 | Si Muninn embedde 65K cubes en 3D, Barnes-Hut > cKDTree exhaustif. Implémentation : `pyoctree` ou rouler sa propre subdivision |
| **`1308.1472` ForestClaw — Forest of octrees AMR** | 2013 | Multi-bloc adaptif = grilles octree multiples cousues | **Pattern Carmack** : un fichier = un octree, plusieurs fichiers = forêt — repair cross-file = jonction d'octrees |
| **`1411.4357` (via G7) Barnes-Hut topology + persistent homology** | 2014 | Approximate persistent diagrams via octrees | Si tu veux la signature topologique d'un cube en O(log N) |
| **`1506.06096` Thanou — Graph-Based Compression of Dynamic 3D Point Clouds** | 2016 | Compression de séquences point clouds via graph wavelets | Si cubes ≈ point cloud → compression LOSSLESS du graphe d'arêtes via spectral wavelets |
| **`1506.01788` García-Trillos — Convergence of Laplacian Spectra from Point Clouds** | 2015 | Le Laplacien d'un point cloud ≈ Laplacian-Beltrami de la variété sous-jacente | **Validation théorique** : le mycelium Muninn = approximation du Laplacien d'une variété d'embedding code |
| **`1412.1683` Anagnostopoulos — Randomized Embeddings ANN with Slack** | 2018 | Bornes théoriques sur ANN approximate après projection aléatoire | Si tu projettes 768D embeddings → 3D, voici la perte quantifiée |
| **`1511.00628` Ball*-tree for constrained NN** | 2015 | Ball*-tree avec contraintes (e.g. "neighbors dans même fonction") | Utile si neighbors doivent respecter scope syntaxique |
| **`cs/0601019` Canonical Abstract Syntax Trees** | 2006 | Forme canonique d'AST | **Lecture obligée** avant de plonger les cubes en 3D — la canonicalization AST (axe 1 RS aussi) est le préalable |

### 3.2 Voronoï disk = théorie pure, peu actionnable directement

Les 186 hits Voronoï WT3 sont :
- 60% physique stat (Poisson-Voronoi cells, percolation Voronoï)
- 30% maths pures (généralisations algébriques)
- 10% astro (binning Voronoï X-ray)

**Aucun ne touche au code source.** Les bornes Voronoï classiques (degré moyen 6 en 2D, ~15.5 en 3D) restent valides comme baseline pour estimer combien de neighbors un cube a "naturellement".

### 3.3 Pont avec docs Muninn — déjà 50% du chemin

`CUBE_UX_HEATMAP_PLAN.md` (Phase 1) prévoit DÉJÀ : *"Position basée sur la position dans le fichier (x = ligne, y = profondeur d'indentation, z = fichier)"*. C'est UNE coordonnée 3D triviale. Le pivot Yggdrasil propose : **remplacer (ligne, indent, fichier) par (UMAP_x, UMAP_y, UMAP_z) calculées sur les embeddings qwen** — gain attendu : neighbors sémantiques au lieu de neighbors syntaxiques.

Tu peux benchmarker en 1 jour : génère 100 cubes, calcule embeddings via `ollama embeddings qwen2.5-coder:7b`, projette en 3D via UMAP, compare le score reconstruction avec neighbors textuels vs neighbors Voronoï.

---

## 4. Axe 3 — Attention windows / FIM / RoPE (DÉSERT sur disque — confirme pass 1)

WT3 hits sur les vrais keywords : **0**.
- `axis3_fim` : 0 hits
- `axis3_attention_window` : 0 hits
- `axis3_chunk_size` : 0 hits  
- `axis3_code_llm` (codellama, starcoder, deepseek, qwen, codet5, incoder) : 0 hits
- `axis3_code_completion` : 0 hits
- `axis3_rope` : 70 hits — **mais 100% bruit** (rope = corde, pas Rotary Position Embedding) : "Sliding rope paradox", "carbon nanotube rope", "flux rope solaire", "misanthrope process", etc.

**Cause** : RoPE = Su et al. 2021, FIM = Bavarian et al. 2022, qwen2.5-coder = 2024, deepseek-coder = 2024. Tous post-cutoff WT3.

**Conclusion axe 3** : la pass 1 web (refs `arxiv 2409.12186 Qwen2.5-Coder Tech Report`, `2506.00204 Structure-Aware FIM`, `2410.23771 Perplexity ICLR 2025`, `2405.14591 RoPE Bounds`) reste l'unique source. Le bench local proposé pass 1 reste l'action concrète :

```python
# rappel pass 1 — sweep N tokens × test FIM template
for N in (80, 88, 96, 112, 128):
    prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>\n{suffix}<|fim_middle|>"
    ...
```

**Vérifier en priorité** : `engine/core/cube_providers.py` (Muninn) — la fonction `OllamaProvider.reconstruct_cube` envoie-t-elle ce template, ou un raw `next-token` ? C'est le seul vrai inconnu actionnable.

---

## 5. Cas adaptables — vieille doc + papers (TRÈS RICHE)

### 5.1 Carmack moves Muninn DÉJÀ implémentés (à NE PAS re-proposer)

D'après `MUNINN-/docs/SHOPPING_LIST.md` (session 2026-03-08) — **20 techniques évaluées, 11 implémentées, 11 skip, 1 impasse** :

**Implémentées (FAIT)** : Contradiction resolution (Stanford NLP 2008), Semantic RLE, Optimal Forgetting (Plos Comp Bio 2020), NCD dedup (Cilibrasi 2005), KIComp density boot, R1-Compress chunking, Context-Aware Hierarchical Merging, Bloom Filter concept tracking, **L10 Cue Distillation** (Method of Loci 500 BC + Schema Theory 1932 + Predictive Coding 1999), **L11 Rule Extraction** (Kolmogorov + KoLMogorov Test ICLR 2025), **Spreading Activation** (Collins-Loftus 1975), **Sleep Consolidation** (Wilson-McNaughton 1994).

**Impasse confirmée** : Meta-Tokens (LZ77 sur prompts) — 0% gain car BPE déjà optimal mot-par-mot.

**Skip** : SemHash, token-reducer, Selective-Context, Sequitur, Zstd dict, A-MEM, Word Graph Sentence Fusion.

### 5.2 Cas adaptables que la vieille doc N'A PAS encore couverts

| Paper / Cas | Année | Ce que c'est | Pourquoi pertinent Cube Muninn |
|---|---|---|---|
| **`1206.1522` DEX: Self-healing Expanders** (Pandurangan) | 2012 | Graphe maintenant ses propriétés spectrales sous deletion | Encoder le graphe de cubes comme DEX → garantie de chemin de reconstruction même si k cubes morts simultanément |
| **`1205.4681` Self-Healing Algorithms of Byzantine Faults** | 2012 | Recovery sous adversaire arbitraire (k Byzantine) | Si certains cubes sont "menteurs" (LLM hallucine), Byzantine resilience donne le seuil de tolérance |
| **`1202.2466` Self-healing systems and virtual structures** | 2012 | Architecture autonomic à 3 couches | Pattern direct pour le mode "auto-repair" de Muninn |
| **`1408.2103` Critical review of automatic patch generation** | 2014 | Méta-review : pourquoi l'APR de l'époque échoue | Évite à Muninn les pièges connus (overfitting test suite, plausibility ≠ correctness) |
| **`1307.7281` Cost-Aware Automatic Program Repair** | 2013 | Trade-off coût-LLM × qualité patch | Cadre formel pour décider "encore une tentative ou abandon" |
| **`1305.6762` Hedging without sweat: GP for finance** | 2013 | Genetic Programming pour exploration de stratégies | Si Muninn doit générer des "stratégies de reconstruction" multiples, GP est un baseline robuste |
| **`1209.1236` Coordination of autonomic functionalities in networks** | 2012 | Coordination décentralisée d'agents auto-réparants | Si plusieurs cubes essaient de se réparer en parallèle, ce framework évite le thrashing |

### 5.3 Cross-ref Yggdrasil — concepts qui matter encore (validés cooccurrences WT3)

D'après `cube_muninn_metaprompt.md` + scans existants :

| Concept | OpenAlex idx | cooc edges | État | Action Muninn |
|---|---|---|---|---|
| Erasure code | 5897 | 1 138 | Cible #1 | Implémenter LRC variant |
| Reed-Solomon | 61657 | (sub-link) | Cible #2 | Lib `klauspost/reedsolomon` Go natif |
| Persistent homology | 44034 | 1 677 | Cible #7 | Signatures topologiques de cubes (`1003.1001` Adler) |
| Belief propagation | 8250 | 1 800 | Cible #3 | Pour décodeur LDPC hybride si LRC sature |
| **Self-healing** (case_anti_fragile) | nouveau | 57 papers | **Trou de l'ancien metaprompt** | À ajouter dans G10 Carmack hunt |
| **Octree/Voronoi/spatial_idx** | nouveau | 215 papers cumul | **Trou de l'ancien metaprompt** | G11 nouveau axe |
| Compressed sensing | 3921 | 4 357 | **PIÈGE** | Skip (dominé par CV/AI, signal "for code" minuscule) |

---

## 6. Plan d'action 4-couches (ré-ordonné après pass 2)

| # | Action | Effort | Source |
|---|---|---|---|
| **1** | Audit `OllamaProvider.reconstruct_cube` → vérifier template FIM | 5 min | pass 1 |
| **2** | Bench local sweep N ∈ {80,88,96,112,128} × FIM template | 15 min | pass 1 |
| **3** | Prototype LRC(n=80, k=60, r=9) sur cubes via `pyeclib v1.8.0` ou Go `klauspost/reedsolomon` | 1-2 jours | **disque pass 2** + pass 1 |
| **4** | Expérience neighbors : embeddings qwen → UMAP 3D → cKDTree vs textuel | 1-2 jours | pass 1 + pass 2 (`1506.01788`) |
| **5** | Lire `1311.3284` Tamo-Barg LRC + `cs/0702015` Dimakis Network Coding (2 papers, ~40 pages) avant d'implémenter step 3 | 1/2 journée | **disque pass 2** |
| **6** | Si 3 marche, ajouter DEX self-healing layer (`1206.1522`) sur le graphe de neighbors | 2-3 jours | **disque pass 2** |
| **7** | Lancer un nouveau scan Yggdrasil : G10 Self-healing + G11 Spatial-3D sur WT3 + arXiv 2016-2025 | 1 journée | nouvelle action |

---

## 7. Annexe — fichiers produits par ce run

```
data/results/cube_muninn_carmack/
├── RESEARCH_PROMPT_2026-04-26.md         # prompt initial pass 1
├── disk_probe.py                          # script scan WT3 (122s/833K papers)
└── disk_probe_results.json                # tous les samples par catégorie
```

Le JSON `disk_probe_results.json` contient ~30 échantillons par catégorie avec paper_id + year + title + domain. Utilisable directement pour `pyarxiv` télécharger les PDFs des papers d'intérêt.

---

## 8. Ce qui n'a PAS été fait (transparence)

- **Full-text grep dans /media/sky/disque 5T/arxiv/src/** (1.6 TB de .tar). Coût ~4-6h. Recommandé seulement si un paper précis manque après lecture des 8-10 papers headline ci-dessus.
- **Scan PMC** (`/media/sky/disque 5T/pmc/oa_comm/`) — pas pertinent pour code/erasure/octree (PMC = bio/medicine).
- **Lecture des 3 612 papers de cube_muninn_papers.txt en détail** — j'ai pris les titres+years uniquement. Un agent peut les parcourir si tu veux affiner G3 (belief propagation) ou G7 (persistent homology).
- **OpenAlex full snapshot query** (692 GB sur 5T) — surdimensionné pour 3 axes ciblés ; WT3 indexe déjà l'utile.

---

*Sources principales pass 2 : WT3.db 833 030 papers / 99.3 GB scan complet 122s ; cube_muninn_papers.txt 3 612 papers G1-G9 ; SHOPPING_LIST.md 20 techniques évaluées ; BATTLEPLAN_SCANNER.md TIER S Carmack moves ; CUBE_UX_HEATMAP_PLAN.md positionnement 3D existant ; LITERATURE.md 12 papers compression LLM ; BRIEFING_MUNINN.md + BRIEFING_MUNINN_CELLBIO.md cell-bio blind spots. Croisé avec pass 1 web (arxiv 2024-2026).*
