# TIER 2 — Resume des gains (10 mars 2026)

## Origine
Suite du TIER 1 (Cell Bio convergence). Focus sur l'intelligence structurelle:
detecter les anomalies, les trous, predire, s'adapter, injecter en temps reel.

## 5 upgrades implementes + 4 branchements pipeline

| # | Upgrade | Ou | Branche dans |
|---|---------|-----|-------------|
| B2 | Graph anomaly detection | mycelium.py | diagnostic (CLI) |
| B3 | Blind spot detection | mycelium.py | boot() scoring (+0.05) |
| B4 | Endsley L3 Prediction | muninn.py | boot() scoring (+0.03) |
| B5 | Session mode detection | muninn.py | boot() sigmoid k |
| B6 | Klein RPD session-type | muninn.py | boot() scoring weights |
| B7 | Live memory injection | muninn.py | CLI `inject` |

## Chiffres avant/apres

### Anomalies (B2)
- AVANT: zero diagnostic sur le graphe
- APRES: 463 noeuds isoles, 1156 hubs, 0 zones faibles
- Carte de sante du mycelium (2.7M connexions)

### Blind spots (B3)
- AVANT: zero detection de trous structurels
- APRES: 10 trous trouves sur 2.7M connexions
- Branches couvrant ces trous get +0.05 dans le scoring boot

### Prediction (B4)
- AVANT: boot 100% reactif (attend la query)
- APRES: predict_next() predit 5 branches, bonus +0.03 dans scoring
- Cold branches favorisees (fresh penalisees x0.3)

### Session mode (B5)
- AVANT: sigmoid k=10 fixe pour toutes les sessions
- APRES: divergent k=5 (large), convergent k=20 (serre), balanced k=10
- Spread activation s'adapte automatiquement au mode de travail

### Session type (B6)
- AVANT: poids fixes (0.15/0.40/0.20/0.10/0.15)
- APRES: adaptes par type:
  - debug: recall=0.20, usefulness=0.15 (boost erreurs recentes)
  - explore: activation=0.30, relevance=0.30 (spread plus large)
  - review: rehearsal=0.25 (boost branches a re-lire)

### Live injection (B7)
- AVANT: faits mid-session = perdus jusqu'au feed
- APRES: `muninn.py inject "fact"` -> branche live + mycelium nourri
- Tagged D>, retrievable immediatement

### Boot global
- Overlap baseline: 88% -> 85%
- 3 branches differentes = choisies par blind spots + predictions + mode

## Validation
- 32 bornes TIER 2 (test_tier2_b2..b7.py)
- 6 bornes wiring (test_tier2_wiring.py)
- 36 bornes TIER 1 regression (test_tier1_full.py)
- **Total: 74 bornes, 0 FAIL, 0 SKIP**

## Sources scientifiques

| Upgrade | Source |
|---------|--------|
| B2 | LITERATURE #16 (graph anomalies) |
| B3 | Burt 1992 (structural holes), BS-4 Hodge |
| B4 | Endsley 1995 (Situation Awareness L3) |
| B5 | Carhart-Harris 2012 (entropic brain), Guilford 1967 |
| B6 | Klein 1986 (Recognition-Primed Decision) |
| B7 | Park et al. 2023 (live memory) |

## Commits
```
6d1a685 B2: Graph anomaly detection
d734f1f B3: Blind spot detection
6961f78 B7: Live memory injection
a4874c5 B4: Endsley L3 Prediction
7e5e287 B5+B6: Session mode + RPD classification
891a91b WIRING: B3+B4+B5+B6 branches dans boot()
```
