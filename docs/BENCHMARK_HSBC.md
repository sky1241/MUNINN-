# Muninn Bootstrap — HSBC-algo-genetic

Date: 2026-03-07
Engine: muninn.py v0.9+, L1-L7 + L9 (Haiku API)

## Scan
- Files scanned: 1955
- Mycelium connections: 500
- Fusions learned: 392
- Top concepts: fourier, outputs, phase, regime, btc_usd, segments

## Compression Results (L1-L7 + L9)

| File | Original | Compressed | Ratio |
|------|----------|------------|-------|
| README.md | 2,035 | 1,520 | x1.3 |
| LOGIQUE_PROGRAMME.md | 12,353 | 1,288 | x9.6 |
| METHODOLOGIE_COMPLETE.md | 13,594 | 982 | x13.8 |
| HMM_SPECTRAL_ALGO_FR.md | 4,865 | 3,423 | x1.4 |
| ARBRE_PROJET.md | 12,113 | 1,066 | x11.4 |
| **TOTAL** | **44,960** | **8,279** | **x5.4** |

## Comparison with Yggdrasil Bootstrap

| Metric | Yggdrasil | HSBC-algo |
|--------|-----------|-----------|
| Files scanned | 104 | 1,955 |
| Connections | 500 | 500 |
| Fusions | 145 | 392 |
| Avg compression | x2.6-x4.1 | x1.3-x13.8 |
| Weighted avg | ~x3.0 | x5.4 |

## Notes
- Verbose docs (LOGIQUE, METHODOLOGIE, ARBRE) compress 10-14x — heavy filler, structured content
- Compact docs (README, HMM_SPECTRAL) compress 1.3-1.4x — already dense
- HSBC repo has richer vocabulary (trading domain) = more fusions (392 vs 145)
- Engine is universal: same code, different domain, works out of the box
