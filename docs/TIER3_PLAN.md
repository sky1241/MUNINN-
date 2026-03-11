# TIER 3 — Plan de bataille

## Status: EN ATTENTE (Sky choisit les priorites)

## Briques disponibles

| # | Brique | Difficulte | Description |
|---|--------|-----------|-------------|
| C1 | Saturation beta | Facile | Activer A4 beta>0 (fusible Lotka-Volterra, actuellement 0.0) |
| C2 | Boot feedback log | Facile | B3 blind spots: logger quels trous ont ete couverts |
| C3 | Auto-preload predictions | Moyen | B4: charger les branches predites avant la query |
| C4 | k adaptatif temps reel | Moyen | B5: ajuster k pendant la session, pas juste au boot |
| C5 | Bootstrap cree branches | Moyen | P40: bootstrap scan -> branches (pas juste root+mycelium) |
| C6 | CLI diagnose | Facile | `muninn.py diagnose` — sante complete en une commande |
| C7 | Contradiction resolution | Dur | Detecter/resoudre contradictions dans B1 reconsolidation |
| D1 | Paper | Hors-code | "Universal Memory Dynamics" — writeup academique |

## Idee P41 — Mycelium auto-referentiel (Sky, 10 mars 2026 21h30)

Nourrir le mycelium avec sa propre sortie compactee (fusions) comme substrat.
- Co-occurrences DE co-occurrences = structure de second ordre
- Ratio propose: 2/3 brut + 1/3 compacte (evite convergence point fixe)
- Le meta-mycelium existe deja, format compatible
- Cout: ~10 lignes dans mycelium.py
- Pas critique, quasi gratuit, gain mesurable apres quelques sessions
- Contexte: session P!=NP + chiffrement cognitif

## Deja fait
- TIER 1: 6 upgrades, 36 bornes (A1-A5, B1)
- TIER 2: 5 upgrades + 4 wiring, 74 bornes (B2-B7)
- Total: 110 bornes, 0 FAIL
