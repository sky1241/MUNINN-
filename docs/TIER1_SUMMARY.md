# TIER 1 — Resume des gains (10 mars 2026)

## Origine
22 blind spots Type C en biologie cellulaire (scan Yggdrasil) convergent avec
formules finance/psychologie cognitive. Quand 2 domaines independants pointent
vers le meme fix, le fix est valide.

## 6 upgrades implementes

| # | Upgrade | Formule | Gain mesurable |
|---|---------|---------|----------------|
| A1 | h adaptatif | h *= usefulness^0.5 | Recall separation 4.3x (0.27 vs 0.06) |
| A2 | ACT-R activation | B = ln(sum(t_j^(-d))) | Detecte cramming vs spaced (1.10 vs 0.27) |
| A3 | Sigmoid spreading | sigma(x) = 1/(1+e^(-k*(x-x0))) | Bruit <0.1, signal >0.9 |
| A4 | Saturation decay | -beta*w^2 (Lotka-Volterra) | Fusible installe, beta=0.0 (inactif) |
| A5 | Spectral gap | lambda_2/lambda_1 | Diagnostic: gap=1.0 (bien connecte) |
| B1 | Reconsolidation | L10+L11 sur branche froide | -43% taille branches froides |

## Chiffres avant/apres

### Recall (A1)
- AVANT: usefulness=0.3 et usefulness=0.9 donnent le meme recall (0.29)
- APRES: usefulness=0.3 -> recall=0.06, usefulness=0.9 -> recall=0.27
- Le systeme oublie les branches inutiles 4.3x plus vite

### ACT-R (A2)
- AVANT: zero information sur le pattern d'acces
- APRES: clustered=1.10, spread=0.27 — detecte le cramming
- Blend 70% Ebbinghaus + 30% ACT-R dans le scoring boot

### Boot (global)
- 26 branches chargees avant et apres
- 23 communes (88% overlap) — stabilite confirmee
- 3 branches differentes = mieux choisies grace au nouveau scoring

### Reconsolidation (B1)
- Texte 423 chars -> 240 chars (57% de l'original)
- Idempotent: 2eme passe = 0% delta
- Conditions: recall < 0.3 ET > 7 jours ET > 3 lignes ET pas root

## Validation
- 36 bornes strictes (test_tier1_full.py)
- 36 PASS, 0 FAIL, 0 SKIP
- 6 fichiers de tests individuels (test_tier1_a1..b1.py)
- Backward compatible: tous les defauts reproduisent le comportement pre-TIER1

## Sources scientifiques (convergence multi-domaines)

| Upgrade | Source 1 | Source 2 |
|---------|----------|----------|
| A1 | GARCH (Bollerslev 1986, finance) | PLOS Bio 2018 (antibody half-lives) |
| A2 | ACT-R (Anderson 1993, psycho cognitive) | Cell Systems 2017 (non-Markov) |
| A3 | cond-mat/0202047 (quasispecies) | Goldbeter-Koshland (MAPK) |
| A4 | nlin/0009025 (Lotka-Volterra) | Ecologie MVP (carrying capacity) |
| A5 | Bowman Stanford (1000+ citations) | detect_zones() eigenvalues |
| B1 | Nader 2000 (Nature 406) | DARPA RAM Replay 2013 |

## Commits
```
7487e94 A1: h adaptatif
11ea3cf A2: access_history + ACT-R
bf36fa0 A3: Sigmoid spreading
5d4c0f9 A4: Saturation decay
26ff860 A5: Spectral gap
059499c B1: Reconsolidation
2325e05 Full battery test (36 PASS)
```
