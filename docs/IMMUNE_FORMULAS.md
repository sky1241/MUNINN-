# Immune System Formulas — TIER 4

3 formules du systeme immunitaire injectees dans Muninn.
~45 lignes de code total. Pas un sous-systeme — des formules dans des fonctions existantes.

## I1: Danger Theory — DCA (Greensmith 2008)

**Principe**: Une session chaotique (erreurs, boucles debug, changements de sujet)
produit des branches plus resistantes a l'oubli.

**Formule originale** (Dendritic Cell Algorithm):
```
danger_score = w1 * PAMP + w2 * danger + w3 * safe
```

**Formule Muninn** — calculee par session dans `_update_session_index()`:
```
session_danger = 0.4 * error_rate + 0.3 * retry_loops + 0.2 * topic_switches + 0.1 * (1 - compression_ratio)
```
- `error_rate` = lignes E> / lignes totales du transcript compresse
- `retry_loops` = nombre de boucles debug (patterns retry/debug/fix dans le transcript)
- `topic_switches` = changements de sujet (concepts disjoints entre blocs consecutifs)
- `compression_ratio` = ratio Semantic RLE (session chaotique = ratio bas = danger)

**Effet sur la branche** dans `_ebbinghaus_recall()`:
```
h_boost = h * (1 + gamma * session_danger)
```
- `gamma` = sensibilite (defaut 1.0)
- Session dangereuse -> demi-vie multipliee -> branche survit plus longtemps
- Session tranquille -> pas de boost (danger=0 -> h inchange)

**Injection**: `_ebbinghaus_recall()` lit `node.get("danger_score", 0.0)`

---

## I2: Suppression Competitive — Perelson 1989

**Principe**: Branches quasi-identiques se suppriment mutuellement.
La plus faible perd du recall, meurt plus vite. Auto-dedup continu.

**Formule originale** (reseau immunitaire):
```
dx_i/dt = c * (sum(m_ij * x_j) - sum(s_ik * x_k)) - k * x_i
```

**Formule Muninn** dans `prune()`:
```
suppression_i = alpha * sum(NCD_sim(i,j) * recall_j)   pour tout j != i ou NCD(i,j) < 0.4
recall_effectif_i = recall_i - suppression_i
```
- `NCD_sim(i,j)` = 1 - NCD(i,j) = similarite (0=different, 1=identique)
- `alpha` = force de suppression (defaut 0.1)
- Seuil NCD < 0.4 = branches tres similaires seulement
- La plus faible perd du recall -> meurt plus vite

**Injection**: `prune()` juste avant la classification hot/cold/dead.

---

## I3: Negative Selection — Forrest 1994

**Principe**: Detecter les branches anormales (trop longues, zero faits, densite bizarre).
Flag pour inspection.

**Formule**:
```
anomaly(branch) = 1  si  distance(branch, self_profile) > threshold
                  0  sinon
```

**Self-profile** = medianes des branches saines:
```
self_profile = {
    token_density:  median(tokens/ligne),
    fact_ratio:     median(lignes_taguees / lignes_totales),
    line_count:     median(nombre de lignes)
}

distance(b, self) = sum(|b.metric - self.metric| / max(self.metric, 0.01))
```

**Seuil**: distance > 2.0 = anomalie (3x la mediane sur un axe = flag)

**Injection**: `prune()` — branches flaggees sont loggees `[ANOMALY]` et demotees vers cold.

---

## Recap

| Modele | Formule cle | Ou dans Muninn | ~Lignes |
|--------|------------|----------------|---------|
| I1 Danger Theory | `h *= (1 + gamma * danger)` | `_ebbinghaus_recall()` + `_update_session_index()` | ~15 |
| I2 Suppression | `recall -= alpha * sum(sim * recall_j)` | `prune()` classification | ~20 |
| I3 Negative Selection | `flag si distance > 2.0` | `prune()` health check | ~15 |

**Total**: ~50 lignes. Backward compatible (defauts = 0 = pas d'effet).
