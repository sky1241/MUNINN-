# Benchmark L9 (Haiku API) — 2026-03-08

## Contexte
L8 (LLMLingua BERT) supprime — perdait 72% des faits sur texte pre-compresse.
Pipeline final: L1-L7 (regex) + L9 (Claude Haiku API).
Teste sur infernal-wheel (dashboard sante, UX bibles).

## Resultats

### Par fichier (top 5 plus gros)
| Fichier | Original | Compresse | Ratio | Facts |
|---------|----------|-----------|-------|-------|
| MOBILE.md | 129,835 tok | 4,256 tok | **x30.5** | 47% (33/69) |
| WEARABLE.md | 133,941 tok | 3,722 tok | **x36.0** | 39% (28/71) |
| WEB.md | 125,769 tok | 4,398 tok | **x28.6** | 42% (77/181) |
| PROMPT_DEEP_RESEARCH.md | 14,515 tok | 1,437 tok | x10.1 | 26% (5/19) |
| DESIGN_TREE.md | 14,040 tok | 1,104 tok | x12.7 | 36% (15/41) |

### Totaux
```
Tokens: 418,100 -> 14,917 (x28.0, 96% saved)
Facts:  158/381 (41%)
Cost:   ~$0.15 (5 fichiers, ~74K input + 16K output tokens Haiku)
```

### Ce qui est perdu
- Dimensions CSS specifiques: px, rem, vw, vh
- Timings precis: ms, s (0.25s, 800ms, 40s)
- Noms de produits: Garmin, HealthKit (parfois)
- Seuils techniques: 1MB, 256KB, 1GB

### Ce qui survit
- Concepts generaux: dashboard, chart, gradient, WCAG
- Architecture: PowerShell, SQLite, API, REST
- Pourcentages et ratios principaux

## Conclusion
L9 (Haiku) = compression extreme (x28-x36) mais perte de faits importante (41%).
Adapte pour: index de recherche, overview rapide, sessions de conversation.
PAS adapte pour: docs de reference ou les details CSS/timing comptent.

### Comparaison pipeline
| Pipeline | Ratio moyen | Fact retention | Cout |
|----------|------------|----------------|------|
| L1-L7 seules | x2.6-x4.5 | 92% | $0 |
| L1-L7 + L9 | x10-x36 | 41% | ~$0.03/fichier |
| L9 ideal: sessions | x5-x8 | ~80% (tags protegent) | ~$0.01 |
