# TIER 3 — Plan de bataille

## FAIT (commits 87c2a06, db14c37)

| # | Brique | Status |
|---|--------|--------|
| S1 | SQLite backend (mycelium_db.py) | DONE — 946MB JSON -> 657MB SQLite (-30%), WAL, int IDs |
| S2 | Epoch-days dates | DONE — 2 bytes vs 10 bytes par date |
| S3 | Degree filter universel | DONE — top 5% bloques des fusions |
| S4 | ConceptTranslator (BPE + Haiku) | DONE — detection langue + batch API + cache |
| -- | Hardening | DONE — atomic save, migration guard, defensive .get() |
| -- | Tests | 21 bornes (S1:11, S3:5, S4:5), 90/91 PASS |

## RESTE A FAIRE

| # | Brique | Difficulte | Description |
|---|--------|-----------|-------------|
| C1 | Saturation beta | Facile | Activer A4 beta>0 (Lotka-Volterra, actuellement 0.0) |
| C2 | Boot feedback log | Facile | B3 blind spots: logger quels trous couverts |
| C3 | Auto-preload predictions | Moyen | B4: charger branches predites avant query |
| C4 | k adaptatif temps reel | Moyen | B5: ajuster k pendant session, pas juste au boot |
| C5 | Bootstrap cree branches | Moyen | P40: bootstrap -> branches (pas juste root+mycelium) |
| C6 | CLI diagnose | Facile | `muninn.py diagnose` — sante complete en 1 commande |
| C7 | Contradiction resolution | Dur | Detecter/resoudre contradictions dans B1 |
| D1 | Paper | Hors-code | "Universal Memory Dynamics" |
| P41 | Mycelium auto-referentiel | Facile | Nourrir mycelium avec ses fusions (2/3 brut + 1/3 compacte) |

## Bilan global
- TIER 1: 6 upgrades, 36 bornes (A1-A5, B1)
- TIER 2: 5 upgrades + 4 wiring, 74 bornes (B2-B7)
- TIER 3 (fait): 4 upgrades + hardening, 21 bornes (S1-S4)
- Total: 131 bornes, 1 pre-existing date bug
