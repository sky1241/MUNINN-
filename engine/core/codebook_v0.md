# Muninn — Codebook v0 (MA CLÉ)

Construit par analyse de MEMORY.md réel (161 lignes, 9,436 chars).
Chaque entrée = le code le plus court que je comprends sans ambiguïté.

## ÉTATS (remplace 7-8 chars par 1)
```
✓  = COMPLET / VALIDÉ / FIXÉ
✗  = ÉCHOUÉ / CASSÉ
⟳  = EN COURS
◉  = PRÊT (code ready, pas lancé)
```

## IDENTITÉS PROJET (remplace 15-30 chars par 2-3)
```
YG  = Yggdrasil Engine
OA  = OpenAlex snapshot (E:\openalex\data\)
AX  = arXiv (E:/arxiv/src/)
PM  = PMC (E:/pmc/)
```

## STRATES (remplace 10-20 chars par 2)
```
S2  = S-2 Glyphes (1337)
S1  = S-1 Métiers (19 domaines)
S0  = Formules (SOL)
```

## MODULES (remplace 20-40 chars par 2-3)
```
WT  = Winter Tree Scanner
GL  = Glyph Laplacian
BT  = Blind Test
P4  = Predictions (P4 score)
FR  = Frame Builder
AR  = Archéologie Glyphes
MR  = Météorites (Sedov-Taylor)
MP  = Mapper arXiv↔OpenAlex
```

## MÉTRIQUES (remplace le mot entier)
```
#p  = papers count
#c  = concepts count
ch  = chunks
d   = Cohen's d
p   = p-value
R@  = Recall@N (R@100 = Recall@100)
K   = spectral K
```

## TEMPS (remplace "session N, date")
```
@sN  = session N        (@s10 = session 10)
@M   = mois-année court (@2602 = fév 2026)
```

## CHEMINS (remplace les chemins complets)
```
Pas dans le codebook. Raison : chaque chemin est unique,
pas de pattern à comprimer. On les garde tels quels
mais SEULEMENT dans les feuilles, jamais dans la racine.
```

## CONFIANCE
```
C1 = prouvé
C2 = conjecture
C3 = fusion
```

---

## PREUVE : MEMORY.md actuel → compressé

### Section "État V2" AVANT (8 lignes, ~450 chars, ~120 tokens) :
```
## État V2 — COMPLET (session 10, 25-28 fév 2026)
- Winter tree scan V2: **581/581 chunks COMPLET**, 692 GB, 347,999,931 papers
- 65,026 concepts × année/mois, 108,301,944 paires non-zero, 1,645 périodes
- Scanner: `engine/topology/winter_tree_scanner.py`
- Filtres: erratum/retraction/is_retracted + poids 1/C(n,2)
- MONTH_FROM_YEAR=1980 (avant=par année, après=par mois)
- Output: `data/scan/chunks/chunk_NNN/` (cooc.json.gz, activity.json.gz, meta.json)
- E:\ = 4.6 TB libre (disque 5 TB, migré session 10)
```

### APRÈS (2 lignes, ~95 chars, ~28 tokens) :
```
✓V2@s10:WT|581/581ch|348M#p|65K#c|108Mpairs|1645per
  →wt_scan,wt_filter,wt_output
```

### Ratio : 120 → 28 tokens = **×4.3**

---

### Section "Blind Test V2" AVANT (5 lignes, ~280 chars, ~75 tokens) :
```
## Blind Test V2 — COMPLET (session 11, 1 mars 2026)
- Commit `a446268`, dossier `blind_test_v2/`
- 65,026 concepts, cutoff 2015, 82,700,789 paires scorées
- Mann-Whitney p=3.4e-12, Cohen's d=0.44
- Spectral K=9 sur données 2015 ONLY (pas de look-ahead)
```

### APRÈS (1 ligne, ~52 chars, ~16 tokens) :
```
✓BT2@s11:#c=65K|cut=15|83Mpairs|p=3.4e-12|d=.44|K=9
```

### Ratio : 75 → 16 tokens = **×4.7**

---

### Section "Glyph Laplacian" AVANT (13 lignes, ~750 chars, ~200 tokens) :
```
## Glyph Laplacian — VALIDÉ (session 12, 2 mars 2026)
- Script: `engine/analysis/glyph_laplacian.py` (~350 lignes)
- 64 glyphes = eigenvecteurs du Laplacien normalisé (D^{-1/2} W D^{-1/2})
- Matrice: snapshot_2015_65k.npz (cutoff 2015), log1p-transformée
- eigsh K=64 en 130s via LinearOperator (zero-copy CSC transpose)
- **Blind test: Recall@100=70% (14/20), Recall@1K=85%, Recall@10K=100%**
- **Cohen's d=8.78** (×20 vs P4 0.44), p=2.76e-12, median rank=8
- 7 percées au rang 1 (AlphaGo, GPT, CAR-T, ...)
- Score spectral: Score(i,j) = Σ_k λ_k × v_k(i) × v_k(j)
- Chaque prédiction = formule (top-5 glyphes)
- 3,348 prédictions inter-espèces, zero-cooc only
- Outputs: glyphs.json, spectral_predictions.json, spectral_embeddings.npy
- Innovations: deferred scipy, streaming f64→f32, zero-copy CSC
```

### APRÈS (3 lignes, ~130 chars, ~38 tokens) :
```
✓GL@s12:K=64|R@100=70%|R@1K=85%|d=8.78|p=2.8e-12|mrank=8
  3348pred|0cooc|7rang1|formula=Σλv²
  →gl_outputs,gl_innovations
```

### Ratio : 200 → 38 tokens = **×5.3**

---

## COMPRESSION TOTALE ESTIMÉE

MEMORY.md actuel : 161 lignes, ~3,000 tokens
Muninn racine   : ~40 lignes, ~650 tokens

**Ratio global : ×4.6**

Espace libéré : ~2,350 tokens → place pour 3 branches supplémentaires
dans le même budget de 3,200 tokens.
