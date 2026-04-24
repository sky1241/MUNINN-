# Benchmark Mycelium Scaling — 2026-03-08

## Contexte
Le mycelium (reseau co-occurrences) crashait avec MemoryError sur les gros fichiers.
Cause: observe_text() traitait le fichier entier comme un seul contexte -> O(n²) paires.
Fix: chunking par paragraphe + limite infinie (MAX_CONNECTIONS=0).

## Resultats

### Infernal-Wheel (130 fichiers, dashboard sante + ML + UX bibles)
```
Fichiers scannes:    130
Connexions:          722,611
Fusions:             6,225
Sessions:            3
Crash:               0
Temps:               < 30s
```

### Top fusions (semantiquement correctes)
```
anxi+sommeil:        81x  (axes dashboard sante)
sommeil+energie:     81x  (axes dashboard sante)
anxi+energie:        81x  (axes dashboard sante)
lite+tflite:         63x  (modeles ML)
apple+watch:         52x  (integration Apple)
forest+random:       52x  (Random Forest ML)
core+coreml:         46x  (CoreML Apple)
health+healthkit:    42x  (HealthKit Apple)
cigarette+eating:    39x  (tracking habitudes)
alcool+cigarette:    36x  (tracking habitudes)
```

### Tests unitaires (7/7 PASS)
```
Test 1 - Small text:        OK (single observation)
Test 2 - 100 paragraphs:    OK (chunked, 0.00s)
Test 3 - 19,500 connections: OK (unlimited growth)
Test 4 - Decay:             OK (old connections removed)
Test 5 - Fusions:           OK (threshold detection)
Test 6 - get_related:       OK (semantic neighbors)
Test 7 - Save/load:         OK (persistence)
```

## Avant/Apres

| Metrique | Avant (MAX=500) | Apres (illimite) |
|----------|-----------------|-------------------|
| MAX_CONNECTIONS | 500 (fixe) | 0 (adaptatif RAM) |
| WEB.md 487K | MemoryError crash | OK |
| Infernal-wheel 130 fichiers | jamais teste | 722K connexions, 0 crash |
| Semantique | global (tout lie a tout) | local (paragraphe = contexte) |
| Pruning | seuil fixe | pression RAM > 200MB |

## Conclusion
Le chunking par paragraphe est a la fois plus correct semantiquement (concepts proches = lies)
et plus performant (pas d'explosion O(n²) sur le fichier entier).
Le mycelium peut maintenant scaler a n'importe quel repo.
