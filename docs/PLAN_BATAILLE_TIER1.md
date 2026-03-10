# Plan de Bataille — TIER 1 Upgrades
## 10 Mars 2026

**Objectif**: 5 upgrades formula=data + 1 upgrade fonctionnel, chacun avec bornes
de validation strictes. Un upgrade = un commit = un push. Jamais deux en meme temps.

---

## ORDRE D'EXECUTION

| # | Upgrade | Formule | Lignes | Depends on |
|---|---------|---------|--------|------------|
| A1 | h adaptatif (F1+F5) | `h = h_base * 2^reviews * usefulness^beta` | ~20 | rien |
| A2 | access_history (F1) | `B = ln(sum(t_j^(-d)))` ACT-R | ~30 | A1 (h utilise dans recall) |
| A3 | Sigmoid spreading (F4) | `sigma(x) = 1/(1+e^(-k(x-x0)))` | ~30 | rien |
| A4 | Saturation decay (F8) | `dw = -w/tau - beta*w^2` | ~15 | rien |
| A5 | Spectral gap metric | `gap = lambda_2 / lambda_1` | ~5 | rien |
| B1 | Reconsolidation au boot | L10+L11 sur branche froide | ~40 | A1+A2 (recall calcul) |

A1 en premier car A2 depend du calcul de h, et B1 depend du recall.
A3, A4, A5 sont independants — mais on les fait sequentiellement quand meme (un commit par upgrade).

---

## CONVERGENCE DES SOURCES

Chaque upgrade est justifie par AU MOINS 2 domaines independants:

| Upgrade | Source 1 | Source 2 | Source 3 |
|---------|----------|----------|----------|
| A1 h adaptatif | GARCH (Bollerslev 1986, finance) | PLOS Bio 2018 (antibody half-lives) | BS-6 Cell Bio briefing |
| A2 access_history | ACT-R (Anderson 1993, psycho cognitive) | Cell Systems 2017 (non-Markov cellulaire) | BS-3 Cell Bio briefing |
| A3 Sigmoid | cond-mat/0202047 (quasispecies) | Goldbeter-Koshland (MAPK ultrasensitivity) | — |
| A4 Saturation | nlin/0009025 (Lotka-Volterra) | Ecologie MVP (carrying capacity K) | — |
| A5 Spectral gap | BS-1 (Bowman Stanford, 1000+ cit.) | detect_zones() deja calcule eigenvalues | — |
| B1 Reconsolidation | Nader 2000 (NIMH, Nature 406) | DARPA RAM Replay 2013 | — |

---

## BASELINE A MESURER AVANT TOUT CHANGEMENT

```bash
# Sauver dans docs/BASELINE_TIER1.txt
python muninn.py boot "compression memory"   # branches chargees + scores
python muninn.py boot ""                      # empty query
python muninn.py prune                        # HOT/COLD/DEAD counts
python muninn.py verify memory/root.mn        # facts preserved + ratio
python muninn.py status                       # temperatures
```

NOTE: l'arbre actuel n'a que root (0 branches). Les tests d'integration
(boot avec branches) ne seront possibles qu'apres creation de branches.
Les tests unitaires (formules) marchent sans branches.

---

## BORNES STRICTES PAR UPGRADE

### A1 — h adaptatif

**Fichier**: muninn.py, `_ebbinghaus_recall()` (ligne ~438)
**Changement**: h = 7 * 2^reviews * usefulness^beta (beta=0.5 defaut)
**Champ utilise**: `usefulness` (existe deja, EMA 0.7/0.3 dans _update_usefulness)

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| A1.1 | Arithmetique | reviews=5, usefulness=1.0 | h=224.0 (= ancien) | ecart < 0.01 | ecart >= 0.01 |
| A1.2 | Arithmetique | reviews=5, usefulness=0.5, beta=0.5 | h=224*0.707=158.4 | ecart < 0.1 | ecart >= 0.1 |
| A1.3 | Monotonie | usefulness: 0.1, 0.3, 0.5, 0.7, 1.0 | h strictement croissant | monotone | pas monotone |
| A1.4 | Regression | usefulness=1.0 (defaut tous noeuds) | boot() = baseline exacte | identique | toute difference |
| A1.5 | Differentiation | 2 noeuds, meme acc, usefulness 0.3 vs 0.9 | temperatures differentes | diff > 0.05 | diff < 0.01 |
| A1.6 | Prune safety | prune() apres upgrade | memes DEAD que baseline | identique | branche HOT->DEAD |
| A1.7 | usefulness=0 | usefulness=0.0 | h > 0 (pas de division par zero) | h > 0 | h <= 0 ou crash |

**PIEGE IDENTIFIE**: usefulness=0.0 avec beta=0.5 donnerait 0^0.5 = 0, donc h=0, donc division par zero dans recall.
**SOLUTION**: clamp usefulness a [0.1, 1.0] avant le calcul.

---

### A2 — access_history

**Fichier**: muninn.py, `_ebbinghaus_recall()` + `read_node()` + `compute_temperature()`
**Changement**: nouveau champ `access_history: [timestamps]`, ACT-R base-level activation

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| A2.1 | Arithmetique | timestamps=[1j,3j,30j], d=0.5 | B=ln(1+0.577+0.183)=0.564 | ecart < 0.01 | ecart >= 0.01 |
| A2.2 | Fallback compat | node SANS access_history | genere timestamps synthetiques | fonctionne | crash ou NaN |
| A2.3 | Fallback valeur | node: last_access=5j ago, access_count=3 | 3 timestamps espaces uniformement | resultats coherents | resultats aberrants |
| A2.4 | Ordering | 3x en 1 jour vs 3x sur 3 mois | spread > clustered en recall | spread recall > | spread recall <= |
| A2.5 | Cap | 15 acces accumules | access_history garde les 10 derniers | len <= 10 | len > 10 |
| A2.6 | tree.json size | apres 100 acces | overhead < 200 octets/noeud | taille ok | > 500 octets/noeud |
| A2.7 | Regression | boot avec fallback (pas d'access_history) | memes branches que baseline | identique | different |
| A2.8 | Integration | ACT-R B remplace recall dans scoring | boot() charge memes branches | top 3 identique | top 3 different |

**PIEGE IDENTIFIE**: si on remplace _ebbinghaus_recall par ACT-R, les seuils de prune (R>0.4=hot, R<0.05=dead) n'ont plus de sens car B est sur une echelle differente (log, pas [0,1]).
**SOLUTION**: normaliser B dans [0,1] via sigmoid ou min-max, OU garder Ebbinghaus pour prune et utiliser ACT-R seulement pour le scoring boot.

**DECISION ARCHITECTURALE**: garder _ebbinghaus_recall (avec h adaptatif de A1) pour prune() et temperature(). Ajouter _actr_activation() comme signal SUPPLEMENTAIRE dans boot() scoring (remplace ou complemente le 0.15*recall). Comme ca prune ne change pas = zero risque de regression.

---

### A3 — Sigmoid spreading

**Fichier**: mycelium.py, `spread_activation()` (ligne ~516)
**Changement**: appliquer sigmoid sur l'activation propagee

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| A3.1 | Arithmetique | sigmoid(0, k=5, x0=0.3) | 0.182 | ecart < 0.01 | ecart >= 0.01 |
| A3.2 | Arithmetique | sigmoid(0.5, k=5, x0=0.3) | 0.731 | ecart < 0.01 | ecart >= 0.01 |
| A3.3 | Bruit filtre | activation=0.05 | post-sigmoid < 0.1 | < 0.1 | >= 0.1 |
| A3.4 | Signal preserve | activation=0.8 | post-sigmoid > 0.5 | > 0.5 | <= 0.5 |
| A3.5 | Boot regression | boot "compression" | memes top branches | top 3 identique | top 3 different |
| A3.6 | k=0 (desactive) | sigmoid avec k=0 | retourne 0.5 partout | = 0.5 | != 0.5 |
| A3.7 | Spread order | spread_activation("compression") | memes top 5 concepts | identique | different |

**PIEGE IDENTIFIE**: ou placer le sigmoid? Si on le met dans spread_activation (ligne 516, sur chaque spread), ca change les valeurs intermediaires et donc la propagation aux hops suivants. Si on le met a la FIN (ligne 527, sur results), ca ne filtre que la sortie.
**DECISION**: appliquer a la FIN (post-traitement des resultats), pas pendant la propagation. Raison: le sigmoid pendant la propagation changerait la dynamique multi-hop de facon imprevisible. A la fin, c'est un filtre propre sur les scores finaux.

---

### A4 — Saturation decay

**Fichier**: mycelium.py, `decay()` (ligne ~318)
**Changement**: ajouter terme de saturation -beta*w^2 en plus du bit-shift

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| A4.1 | Arithmetique | w=100, beta=0.001 | saturation_loss=10 | ecart < 0.1 | ecart >= 0.1 |
| A4.2 | Beta=0 | beta=0.0 (defaut) | comportement = ancien exact | identique | toute difference |
| A4.3 | w petit | w=2, beta=0.001 | saturation_loss=0.004 (negligeable) | loss < 0.1 | loss >= 0.1 |
| A4.4 | w enorme | w=10000, beta=0.001 | saturation tue la connexion | dead | survit |
| A4.5 | Entier | resultat apres saturation | reste entier (int) | isinstance int | float |
| A4.6 | Mycelium size | apres decay avec beta>0 | max(count) < 10*mean(count) | ratio < 10 | ratio >= 10 |

**PIEGE IDENTIFIE**: le decay actuel utilise bit-shift (>>), qui est une division entiere par 2^n. Ajouter -beta*w^2 (float) et arrondir en int pourrait creer des effets d'arrondi (petites connexions tuees trop vite).
**SOLUTION**: appliquer la saturation SEULEMENT si w > seuil (ex: w > 50). Les petites connexions gardent le decay normal.

---

### A5 — Spectral gap

**Fichier**: mycelium.py, `detect_zones()` (apres ligne ~667)
**Changement**: retourner spectral_gap = eigenvalues[-2] / eigenvalues[-1]

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| A5.1 | Range | gap value | dans (0, 1] | in range | hors range |
| A5.2 | No crash vide | mycelium < 3 nodes | retourne None | None | exception |
| A5.3 | No crash zero | eigenvalue[-1] = 0 | retourne None | None | division par zero |

Trivial, 5 lignes. Pas de risque.

---

### B1 — Reconsolidation

**Fichier**: muninn.py, dans `boot()` apres chargement d'une branche
**Changement**: si recall < 0.3 et days_since_last > 7, re-compresser avec L10+L11

| ID | Borne | Input | Attendu | PASS | FAIL |
|----|-------|-------|---------|------|------|
| B1.1 | Taille | branche apres reconsolidation | taille <= avant | <= | > |
| B1.2 | Facts | verify_compression sur branche | retention >= 90% | >= 90% | < 85% |
| B1.3 | Idempotence | reconsolidate 2x meme branche | 2eme delta < 5% | < 5% | >= 20% |
| B1.4 | Cooldown | branche chargee < 1 jour ago | PAS reconsolidee | skip | reconsolidee |
| B1.5 | Fresh skip | recall > 0.3 | PAS reconsolidee | skip | reconsolidee |
| B1.6 | No API | reconsolidation sans L9 | utilise L10+L11 seulement | no API call | API call |

**PIEGE IDENTIFIE**: pas de branches dans l'arbre actuel. Impossible de tester B1 en integration.
**SOLUTION**: B1 en dernier. Les upgrades A1-A4 + sessions normales auront cree des branches d'ici la.

---

## PROTOCOLE PAR UPGRADE

```
1. BASELINE      lancer status/boot/prune/verify, sauver output
2. CODE          implementer l'upgrade
3. UNIT TESTS    script test_tierN.py avec les asserts ci-dessus
4. RUN TESTS     python test_tierN.py → tout vert?
5. REGRESSION    relancer baseline → comparer
6. PASS?         oui → commit + push
                 non → rollback (git checkout), debug, retry
```

---

## REDUNDANCE ELIMINEE

4 doublons fusionnes (2 sources → 1 upgrade):
- GARCH alpha + BS-6 h variable → A1 h adaptatif
- ACT-R history + BS-3 non-Markov → A2 access_history
- Graph anomalies + BS-1 spectral gap → A5 + futur B2
- Angles morts + BS-4 Hodge → B3 (post-TIER)

---

## POST-TIER 1 (pour reference, PAS dans cette session)

| # | Upgrade | Source | ~Lignes |
|---|---------|--------|---------|
| B2 | Graph anomaly detection | LITERATURE #16 | ~30 |
| B3 | Angles morts | LITERATURE #18 | ~80 |
| B4 | Endsley L3 Projection | Endsley 1995 | ~100 |
| B5 | Mode trip divergent | Carhart-Harris 2012 | ~100 |
| B6 | Klein RPD session-type | Klein 1986 | ~60 |
| B7 | Live memory injection | LITERATURE #8 | ~80 |
| C1 | Paper "Universal Memory Dynamics" | 7 isomorphismes | papier |
| D1 | Huginn (corbeau pensant) | architecture | gros |

---

*Plan valide. Bornes posees. Code = zero. On mesure avant de couper.*
