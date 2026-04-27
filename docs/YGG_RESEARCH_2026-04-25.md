# YGG_RESEARCH — Muninn cube reconstruction (2026-04-25)

> Recherche commandée par Muninn → livrée par Yggdrasil. Web frais (avr 2026) + cross-ref WT3.
> Cible : passer de **1/10 SHA (qwen2.5-coder:7b local)** vers **60-80%** sans budget API.

---

## TL;DR — la chose à faire d'abord (5 min, bug-fix probable)

**Vérifie que `OllamaProvider` wrap chaque cube dans le template FIM officiel de qwen2.5-coder :**

```
<|fim_prefix|>{prefix_neighbors}<|fim_suffix|>{suffix_neighbors}<|fim_middle|>
```

Si le pipeline appelle `ollama run qwen2.5-coder:7b "<raw prompt>"` sans ces 3 sentinelles, qwen tombe en next-token brut et **l'exact-match s'effondre 5–10×**. C'est l'explication la plus probable du gap 1/10 vs 8.85/10. À 80–128 tokens, RoPE est plat, donc la taille de cube n'est PAS le bottleneck — l'enveloppe FIM l'est. Source : Qwen2.5-Coder Tech Report (Hui 2024).

---

## Axe 1 — Reed-Solomon erasure codes pour code reconstruction

État 2026 : RS dur-à-cuire en storage (Storj 29/80, Backblaze 17/3, Tahoe 3/10), throughput ~75 GiB/s sur AVX512+GFNI. **Personne n'a publié RS sur cubes-tokens de code source** — Parchive est l'analogue le plus proche mais opère sur bytes bruts.

| # | Ref | URL | Type | Date | Pertinence Muninn |
|---|---|---|---|---|---|
| 1 | Optimal Sequence Reconstruction for RS Codes | https://arxiv.org/abs/2403.07754 | paper | 2024-03 | Décodage RS au-delà du Johnson radius depuis multiples lectures bruitées — tes outputs LLM SONT des lectures bruitées de cubes |
| 2 | ML-Based Error Correcting Decoders (transformer ECT + OSD) | https://arxiv.org/abs/2410.15899 | paper | 2024-10 | Précédent direct du couplage "petit NN aide RS decoder" = exactement ton hybride |
| 3 | klauspost/reedsolomon (Go, AVX512+GFNI) | https://github.com/klauspost/reedsolomon | lib | commit 2026-04-22 | Native Go (= cible Muninn). API : `enc, _ := reedsolomon.New(k, m); enc.Reconstruct(shards)` |
| 4 | openstack/pyeclib (v1.8.0, liberasurecode + ISA-L) | https://github.com/openstack/pyeclib | lib | 2026-04-20 | API Python : `ec = ECDriver(k=10, m=4, ec_type='liberasurecode_rs_vand'); ec.decode(frags[2:])` |
| 5 | tahoe-lafs/zfec (GF(2^8) Cauchy, prod-hardened) | https://github.com/tahoe-lafs/zfec | lib | 2025-09 | Pure-Python boosté ×2 en v1.6.0.0, prototype rapide |
| 6 | Storj 29-of-80 + Backblaze 17-of-3 | https://storj.dev/learn/concepts/file-redundancy | system | prod | Schémas (n,k) battle-tested, point de départ pour ton dimensionnement cube |

**Verdict : VIRGIN (Carmack opportunity)** pour l'hybride ; **GREEN** pour augmentation pure (RS pour les cubes-anchor structurels, LLM seulement pour le sémantique).

**Carmack-move kicker** : encoder les cubes en RS sur leur **forme AST-canonique** (pas le source brut sinon les parity cubes sont du garbage), recover algébriquement les cubes manquants jusqu'à (n-k)/n loss, puis **invoquer le LLM uniquement comme "decompiler"** des bytes parity-recovered vers du Go valide. Ça donne un **plancher déterministe** RS + un **plafond LLM** = chemin propre vers 60-80%.

---

## Axe 2 — Octree /8 + Voronoï 3D pour neighbors lookup

État 2026 : octree = canon 3D depuis Meagher 1982 (la subdivision /8 est la SEULE qui garde l'isotropie cubique). Voronoï dans l'espace latent LLM est actif (Mabrok 2026). **Aucun lien publié vers reconstruction code.** Le SOTA code-RAG actuel = AST graphs (cAST, CodeCRAG) — jamais 3D-projeté.

| # | Ref | URL | Type | Date | Pertinence Muninn |
|---|---|---|---|---|---|
| 1 | Voronoi Tessellation in LLM Latent Manifolds (Qwen3.5-4B, R²=0.9997) | https://arxiv.org/abs/2604.06767 | paper | 2026-04 | Preuve directe : les cellules Voronoï dans l'espace embedding LLM sont reshape-ables — substrat exact pour définir des neighbors de cubes |
| 2 | LLMs Meet Isolation Kernel (Voronoi → binary embeddings retrieval) | https://arxiv.org/html/2601.09159 | paper | 2026-01 | Analogue le plus proche : Voronoï pour hash retrieval. Swap target text→cube |
| 3 | Retrieval-Augmented Code Generation Survey | https://arxiv.org/abs/2510.04905 | paper | 2026-01 | Confirme l'absence de 3D/octree dans le SOTA code-RAG = champ vierge |
| 4 | Open3D 0.19.0 (Octree + KDTreeFlann) | https://github.com/isl-org/Open3D/releases | lib | 2024-11 | `o3d.geometry.Octree(max_depth=6)` — 100K pts en <100 ms CPU |
| 5 | scipy.spatial.cKDTree (1.17.1) | https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.cKDTree.html | lib | 2026-02 | **À 3D et 10K-100K points, cKDTree exact bat HNSW.** HNSW ne paie qu'à D≥50. `kdt.query(p, k=27)` |
| 6 | Meagher — Octree foundational paper | http://fab.cba.mit.edu/classes/S62.12/docs/Meagher_octree.pdf | paper | 1982 | Justifie /8 = seule split axis-aligned récursive qui garde l'isotropie |

**Verdict : VIRGIN.**

**Carmack-move kicker** : pipeline 2-semaines à prototyper — embed cubes 112-tokens via qwen embeddings → projection ℝ³ via UMAP → octree depth 5-6 → Voronoï neighbors via cKDTree. Si la cellule Voronoï d'un cube donne mieux que la fenêtre textuelle, tu publies. **Note importante** : pour une grille cubique avec coords entières, hash direct `(i±1,j±1,k±1)` bat tous les arbres → O(1) par query. Pas de tree si tes cubes sont déjà sur grille régulière.

---

## Axe 3 — Attention windows 7B coders (qwen, deepseek, codellama)

État 2026 : aucun benchmark publié ne sweep 80-128 tokens parce que toutes les courbes publiées **commencent à ≥1k tokens**. RoPE est dans son régime trivial à cette taille. La variable dominante pour reconstruction ligne-à-ligne = **balance prefix/suffix FIM** + alignement boundary, pas la taille brute.

| # | Ref | URL | Type | Date | Pertinence Muninn |
|---|---|---|---|---|---|
| 1 | Qwen2.5-Coder Technical Report (Hui 2024) | https://arxiv.org/pdf/2409.12186 | paper | 2024-09 | Définit l'éval single-line FIM = exactement la tâche Muninn ; donne le template officiel `<|fim_*|>` |
| 2 | Structure-Aware FIM Pretraining (Single-Node vs Aligned-Span) | https://arxiv.org/html/2506.00204v1 | paper | 2025-06 | Confirme FIM rate 0.5 PSM sweet spot ; **span size > total context** pour le scoring |
| 3 | What is Wrong with Perplexity for Long-context LM (ICLR 2025) | https://arxiv.org/pdf/2410.23771 | paper | 2025-01 | Pour scoring SHA-match : mesurer exact-match per-line, PAS PPL moyenné |
| 4 | RepoBench + ExecRepoBench (Qwen2.5-Coder-Instruct-C 7B) | https://execrepobench.github.io/ | bench | 2024-12 | Repo-level line completion sur 7B coder, varie cross-file context — proxy publié le plus proche (Python/Java seulement) |
| 5 | M2RC-EVAL (massivement multilingue, **Go inclus**) | https://aclanthology.org/2025.acl-long.763.pdf | bench | 2025-08 | Seul bench 7B-coder qui score Go ; ne sweep pas chunk size |
| 6 | Base of RoPE Bounds Context Length / TAPA | https://arxiv.org/html/2405.14591 | paper | 2025-09 | Prouve RoPE plat de 1k à 16k → à 80-128 tokens c'est trivial régime, **chunk size ≠ ton bottleneck** |

**Verdict : VIRGIN.** Pas d'étude publiée sur 80-128 tokens × Go × qwen2.5-coder.

**Bench local recommandé (~15 min sur RX 5700 XT)** :

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

---

## Cross-ref Yggdrasil WT3 (validation par co-occurrences)

| Concept web → | OpenAlex idx | cooc edges | Top voisin | État Yggdrasil |
|---|---|---|---|---|
| Erasure code | 5897 | 1,138 | Decoding w=9.8, Dist.storage w=5.9 | **Déjà cible Cube Muninn** (metaprompt) — axe 1 confirmé |
| Reed-Solomon | 61657 | — | Via erasure code | Sous-lien actif |
| Belief propagation | 8250 | 1,800 | LDPC w=8.0, Decoding w=12.4 | **Pont LDPC↔Decoding fort** — option si RS sature |
| Octree / Voronoï | — | absent | — | **TROU Yggdrasil** = vraie Carmack move axe 2 |
| Compressed sensing | 3921 | 4,357 | AI w=116, Vision w=75 | **PIÈGE 3 metaprompt** : signal "CS for code" minuscule, ne pas creuser |

---

## Plan d'action 3-couches (priorité décroissante)

1. **Aujourd'hui (5 min)** : audit de `OllamaProvider` → vérifier wrap FIM officiel. Si absent, fix → re-run `/reconstruct btree_google.go 112 10` → score attendu ×5.
2. **Cette semaine (1-2 j)** : prototype RS hybride avec `klauspost/reedsolomon` (Go natif, fits Muninn) — encoder 8 cubes-anchor en (10, 8) RS, mesurer recovery floor pur algébrique vs LLM.
3. **2 semaines (publi-grade)** : pipeline Voronoï 3D — embed cubes via qwen embeddings → UMAP ℝ³ → cKDTree neighbors → comparer vs textuel. Si mieux, draft arxiv.

---

*Sources principales : arxiv 2403.07754, 2410.15899, 2604.06767, 2601.09159, 2510.04905, 2409.12186, 2506.00204, 2410.23771, 2405.14591 ; libs github klauspost/reedsolomon, openstack/pyeclib, tahoe-lafs/zfec, isl-org/Open3D ; benchs RepoBench, ExecRepoBench, M2RC-EVAL. Cross-ref WT3 Yggdrasil 833K papers / 69M cooc / 65K concepts OpenAlex.*
