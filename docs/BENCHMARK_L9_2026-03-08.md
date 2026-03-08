# Benchmark L9 (Haiku API) — 2026-03-08

## Contexte
L8 (LLMLingua BERT) supprime — perdait 72% des faits sur texte pre-compresse.
Pipeline final: L1-L7 (regex) + L9 (Claude Haiku API).
Teste sur infernal-wheel (dashboard sante, UX bibles).

## Resultats — v2 (prompt ameliore)

Ameliorations prompt L9:
- Target 40% (au lieu de 20%)
- max_tokens //2 (au lieu de //4)
- "NEVER drop: numbers with units, product names, API names, thresholds"

### Par fichier (top 5 plus gros)
| Fichier | Original | Compresse | Ratio | Facts |
|---------|----------|-----------|-------|-------|
| MOBILE.md | 129,835 tok | 5,920 tok | **x21.9** | 55% |
| WEARABLE.md | 133,941 tok | 7,269 tok | **x18.4** | 60% |
| WEB.md | 125,769 tok | 7,956 tok | **x15.8** | 48% |
| PROMPT_DEEP_RESEARCH.md | 14,515 tok | 2,868 tok | x5.1 | 26% |
| DESIGN_TREE.md | 14,040 tok | 1,104 tok | x12.7 | 36% |

### Totaux
```
Tokens: 418,100 -> 25,117 (x16.6, 94% saved)
Facts:  49% (vs 41% avant amelioration)
Cost:   ~$0.20 (5 fichiers, Haiku)
```

### Avant / Apres amelioration prompt
| Metrique | v1 (target 20%) | v2 (target 40%) |
|----------|-----------------|-----------------|
| Ratio moyen | x28.0 | x16.6 |
| Fact retention | 41% | 49% |
| Tokens output | 14,917 | 25,117 |

### Ce qui est perdu
- Dimensions CSS specifiques: px, rem, vw, vh (partiellement recupere en v2)
- Timings precis: ms, s (ameliore en v2)
- Noms de produits: Garmin, HealthKit (mieux en v2)
- Seuils techniques: 1MB, 256KB, 1GB (mieux en v2)

### Ce qui survit
- Concepts generaux: dashboard, chart, gradient, WCAG
- Architecture: PowerShell, SQLite, API, REST
- Pourcentages et ratios principaux
- Nombres avec unites (ameliore v2)

## Conclusion
L9 v2 = meilleur equilibre compression/retention (x16.6, 49% facts).
Encore trop de perte pour docs de reference, mais bien pour sessions et index.
L'amelioration prompt (+8% facts) montre que le levier est dans le prompt engineering.

### Comparaison pipeline
| Pipeline | Ratio moyen | Fact retention | Cout |
|----------|------------|----------------|------|
| L1-L7 seules | x2.6-x4.5 | 92% | $0 |
| L1-L7 + L9 v1 | x28 | 41% | ~$0.03/fichier |
| L1-L7 + L9 v2 | x16.6 | 49% | ~$0.04/fichier |
| L9 ideal: sessions | x5-x8 | ~80% (tags protegent) | ~$0.01 |
