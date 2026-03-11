# Plan de Bataille — Bio-Vectors
## 11 Mars 2026

**Objectif**: 16 formules bio-inspirees (6 TIER S + 6 TIER A + 4 TIER B), chacune avec
bornes de validation strictes. Un upgrade = un commit = un push. Bug scan independant
apres chaque implementation.

**Source**: 22 formules de 28 papiers (JSON: `docs/muninn_biovectors_formulas.json`)
**TIER C (6 formules)**: skip — doublons de l'existant (V1B, V2A, V4A, V7A, V8A, V11A)

---

## PROTOCOLE PAR FORMULE

1. **Baseline** — mesurer l'etat avant (recall%, boot time, compression ratio)
2. **Code** — implementation dans muninn.py / mycelium.py / mycelium_db.py
3. **Bug scan** — agent Claude independant review tout le code modifie
4. **Metriques** — tests PASS/FAIL avec bornes definies ci-dessous
5. **Commit + push** — si et seulement si metriques OK
6. **Regression** — relancer tous les tests precedents (complementaire)

---

## ORDRE D'EXECUTION (facile → dur)

### PHASE 1 — TIER S : les 6 pepites (semaine 1)

| # | ID | Nom | Lignes | Depends on | Difficulte |
|---|-----|-----|--------|------------|------------|
| 1 | V10A | VADER sentiment scoring | ~40 | rien | FACILE — pip install vaderSentiment, appel direct |
| 2 | V6B | Valence-modulated decay | ~15 | V10A (fournit valence+arousal) | FACILE — upgrade h existant |
| 3 | V6A | Emotional tagging E(a) | ~20 | V10A (fournit arousal) | FACILE — Hill function sur poids mycelium |
| 4 | V2B | TD-Learning delta | ~35 | rien | MOYEN — tracking reward, delta, V(s) par branche |
| 5 | V5B | Cross-inhibition branches | ~30 | rien | MOYEN — Lotka-Volterra quand 2+ branches matchent |
| 6 | V7B | ACO pheromone boot scoring | ~40 | rien | MOYEN — p_ij combine tau + eta dans boot() |

### PHASE 2 — TIER A : les 6 solides (semaine 2)

| # | ID | Nom | Lignes | Depends on | Difficulte |
|---|-----|-----|--------|------------|------------|
| 7 | V3A | Transitive inference | ~25 | rien | MOYEN — beta^distance sur co-occurrences |
| 8 | V11B | Boyd-Richerson 3 biases | ~35 | rien | MOYEN — 3 signaux dans node weight update |
| 9 | V4B | EWC Fisher importance | ~30 | V2B (delta pour Fisher) | MOYEN — Fisher F_i modifie decay rate |
| 10 | V3B | Bayesian ToM user model | ~50 | rien | DUR — inference goal, cost function, prior update |
| 11 | V9A | Bioelectric regeneration | ~40 | rien | DUR — Levin diffusion, graph repair, neighbor reconstruction |
| 12 | V9B | Reed-Solomon redundancy | ~60 | rien | DUR — encodage/decodage polynomial, detection corruption |

### PHASE 3 — TIER B : les 4 utiles (semaine 3)

| # | ID | Nom | Lignes | Depends on | Difficulte |
|---|-----|-----|--------|------------|------------|
| 13 | V10B | Russell circumplex | ~15 | V10A (valence+arousal) | FACILE — theta+r mapping, session clustering |
| 14 | V1A | Coupled oscillator | ~30 | rien | MOYEN — C_ij propagation locale inter-branches |
| 15 | V5A | Quorum Hill switch | ~20 | rien | MOYEN — gate activation par voisins co-actifs |
| 16 | V8B | Active sensing info gain | ~35 | rien | DUR — H(X|Y,a) entropy calcul, action selection |

---

## METRIQUES DE VALIDATION (PASS/FAIL)

### PHASE 1 — TIER S

**V10A — VADER sentiment**
- PASS: compound score dans [-1,+1] pour 100% des inputs
- PASS: "this is great!" > 0.5, "terrible failure" < -0.5, "the function returns 42" dans [-0.1,+0.1]
- PASS: temps < 1ms par phrase (rule-based, pas LLM)
- PASS: zero crash sur session vide, session longue (1000 messages)

**V6B — Valence-modulated decay**
- PASS: h(v=0.8, a=0.7) > h(v=0, a=0) (emotionnel dure plus longtemps)
- PASS: h(v=0, a=0) == h_base exactement (backward compatible)
- PASS: separation recall entre branche emotionnelle vs neutre > 1.5x apres 14 jours simules
- PASS: alpha_v=0, alpha_a=0 reproduit comportement pre-V6B identique

**V6A — Emotional tagging E(a)**
- PASS: E(a=0) == 1.0 (pas de boost sans arousal)
- PASS: E(a=1) > 1.5 (boost significatif a arousal max)
- PASS: poids mycelium apres observe() avec arousal > poids sans arousal
- PASS: inverted-U si kappa sature (pas d'explosion numerique)

**V2B — TD-Learning delta**
- PASS: delta > 0 apres successful recall -> poids augmente
- PASS: delta < 0 apres useless recall -> decay accelere
- PASS: V(s) converge (ne diverge pas) sur 100 simulations
- PASS: gamma=0 reproduit comportement pre-V2B (pas de look-ahead)

**V5B — Cross-inhibition**
- PASS: quand 2 branches matchent a 80% et 60%, la 80% gagne en < 5 iterations
- PASS: quand 2 branches matchent a 75% et 74%, pas de deadlock (timeout 100 iterations)
- PASS: beta=0 reproduit comportement pre-V5B (pas de competition)
- PASS: 1 seule branche match -> zero changement (pas de cross-inhibition solo)

**V7B — ACO pheromone boot scoring**
- PASS: boot overlap avec ancien scoring >= 85% (pas de regression)
- PASS: branches souvent rappelees (tau haut) remontent dans le classement
- PASS: eta (relevance locale) pese dans le score final (pas que l'historique)
- PASS: rho=0 -> tau ne decroit jamais (test edge case)

### PHASE 2 — TIER A

**V3A — Transitive inference**
- PASS: A-B, B-C co-occurrences -> A-C infere avec poids = beta^2 * w_AB * w_BC
- PASS: distance 4+ -> poids infere < 0.01 (decroissance exponentielle)
- PASS: pas de boucle infinie sur graphe cyclique
- PASS: beta=0 desactive completement l'inference transitive

**V11B — Boyd-Richerson 3 biases**
- PASS: conformist: concept utilise par >60% voisins -> boost > 20%
- PASS: prestige: concept avec historique 5+ recalls reussis -> boost > prestige de concept 0 recalls
- PASS: guided: correction explicite (inject) -> convergence vers p_opt en < 3 iterations
- PASS: les 3 biases a zero -> comportement pre-V11B identique

**V4B — EWC Fisher importance**
- PASS: F_i eleve (concept critique) -> decay 2x plus lent que F_i=0
- PASS: F_i calcule correctement (variance du delta sur les N derniers recalls)
- PASS: lambda=0 desactive EWC completement
- PASS: pas de memory leak (F_i borne, pas d'accumulation infinie)

**V3B — Bayesian ToM user model**
- PASS: 3 queries sur le meme sujet -> P(goal=sujet) > 0.7
- PASS: changement de sujet brutal -> prior se reajuste en < 3 queries
- PASS: pre-activation des branches liees au goal infere mesurable dans boot()
- PASS: zero impact si desactive (flag btom=False)

**V9A — Bioelectric regeneration**
- PASS: suppression d'1 noeud -> voisins reconstruisent valeur a >80% (Levin threshold)
- PASS: suppression de 30% des noeuds -> reconstruction > 50%
- PASS: graphe deconnecte -> pas de crash, regeneration partielle seulement
- PASS: zero impact sur graphe sain (g_gap=0 quand pas de perte detectee)

**V9B — Reed-Solomon redundancy**
- PASS: k=10 concepts encodes en n=15, survit a perte de 2 noeuds
- PASS: overhead n/k <= 1.5 (max 50% de redondance)
- PASS: detection de corruption (checksum ou syndrome non-zero)
- PASS: desactivable par flag (redundancy=False -> zero overhead)

### PHASE 3 — TIER B

**V10B — Russell circumplex**
- PASS: theta et r calcules correctement pour 4 quadrants (happy/angry/sad/calm)
- PASS: sessions groupees par quadrant dans session_index
- PASS: query routing: "debug frustrant" -> branches de sessions high-arousal negative

**V1A — Coupled oscillator**
- PASS: perturbation locale se propage aux voisins (C_ij > 0)
- PASS: perturbation s'attenue avec la distance (damping B_i)
- PASS: C_ij=0 -> branches completement independantes (backward compat)

**V5A — Quorum Hill switch**
- PASS: 1 voisin actif sur 10 -> pas d'activation (sous le quorum K)
- PASS: 7 voisins actifs sur 10 -> activation (Hill n=3 -> switch net)
- PASS: K et n configurables, defaults raisonnables

**V8B — Active sensing info gain**
- PASS: parmi 3 branches candidates, choisit celle qui reduit le plus H(X)
- PASS: si toutes les branches ont meme entropie -> pas de preference (random)
- PASS: bits gagnes > 0 pour chaque action selectionnee

---

## FICHIERS TOUCHES PAR PHASE

| Phase | Fichiers principaux | Fichiers tests |
|-------|-------------------|----------------|
| 1 (TIER S) | muninn.py, mycelium.py, mycelium_db.py | tests/test_biovectors_s.py |
| 2 (TIER A) | muninn.py, mycelium.py, mycelium_db.py | tests/test_biovectors_a.py |
| 3 (TIER B) | muninn.py, mycelium.py | tests/test_biovectors_b.py |

**Dependance externe nouvelle**: `vaderSentiment` (pip install vaderSentiment) pour V10A.
Toutes les autres formules = math pure (numpy deja present).

---

## BACKWARD COMPATIBILITY

Regle absolue: **chaque formule a un flag ou default qui reproduit le comportement pre-BioVectors**.
- V10A: sentiment=False -> pas de scoring
- V6B: alpha_v=0, alpha_a=0 -> h = h_base (identique)
- V6A: kappa=0 -> E(a) = 1 (pas de boost)
- V2B: gamma=0 -> delta = reward simple (pas de TD)
- V5B: beta=0 -> pas de cross-inhibition
- V7B: flag aco=False -> scoring actuel inchange
- etc.

Si un default casse le comportement existant = **FAIL immediat, on rollback**.

---

## CONVERGENCE YGGDRASIL

| Formule | Signal Ygg | Cosine | Pont confirme |
|---------|-----------|--------|---------------|
| V2B TD-Learning | primate x RL | 0.251 | "Action selection" cos=0.78 |
| V5B Cross-inhib | collective x voting | 0.315 | "Social choice theory" cos=0.61 |
| V6A Emotional tag | amygdala x episodic | 0.695 | cingulate cortex cos=0.89 |
| V6B Valence decay | (meme champ V6A) | 0.695 | engram cos=0.88 |
| V7B ACO | ACO x knowledge graph | 0.261 | "Tree structure" cos=0.72 |
| V10A VADER | affect x user model | 0.622 | "ITS" cos=0.85 |
| V9A Planaire | planarian x dist. mem | -0.001 | AUCUN = P4 pur |
| V9B Reed-Solomon | (meme V9) | -0.001 | AUCUN = P4 pur |
| V3B BToM | ToM x multi-agent | 0.199 | "Cognitive architecture" cos=0.71 |

---

## CARMACK MOVES (trous structurels purs — zero dans la litterature)

1. **V9 Planaire → graph repair** (cos=-0.001) — regeneration memoire, premiere mondiale
2. **V6 Elephant → graph database** (cos=-0.015) — emotional tagging sur graphe de connaissances
3. **V1 Pieuvre → distributed memory** (cos=-0.017) — propagation locale sans coordinateur

---

## ESTIMATION TOTALE

- 16 formules x ~30 lignes moyennes = ~480 lignes de code nouveau
- 16 formules x ~4 tests = ~64 bornes de validation
- 3 fichiers de tests (S/A/B)
- 1 dependance externe (vaderSentiment)
- ~3 semaines a raison de 5-6 formules/semaine
