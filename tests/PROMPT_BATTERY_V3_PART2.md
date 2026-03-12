# BATTERIE DE TESTS REELS — MUNINN V3 — PARTIE 2/3

Suite de la partie 1. Memes regles, meme setup, meme RESULTS_BATTERY_V3.md.

---

# ═══════════════════════════════════════════
# CATEGORIE 6 — BOOT & RETRIEVAL
# ═══════════════════════════════════════════

## T6.1 — Boot basique + scoring decompose
```
TYPE DE TEST: verifier que le bon sous-ensemble de branches est charge + decomposition des scores

SETUP: arbre avec root + 5 branches (chacune 20 lignes, ~320 tokens):
  "api_design":   tags=["rest","api","endpoint"],     contenu parle de REST API
  "database":     tags=["sql","postgres","migration"], contenu parle de SQL
  "frontend":     tags=["react","css","component"],    contenu parle de React
  "devops":       tags=["docker","k8s","deploy"],      contenu parle de containers
  "testing":      tags=["pytest","mock","coverage"],    contenu parle de tests

  Toutes avec last_access recent, usefulness=0.5, recall ~0.7

APPEL: boot("REST API endpoint design", repo_path=TEMP_REPO)

METRIQUES:
  □ Root TOUJOURS charge (invariant)
  □ "api_design" chargee (plus haute relevance pour "REST API endpoint")
  □ Score("api_design").relevance > Score("frontend").relevance
  □ Budget total < 30K tokens (BUDGET["max_loaded_tokens"]=30000)
  □ Les branches chargees sont dans l'ordre de score decroissant

  DECOMPOSITION (pour chaque branche, montrer les 5 composantes):
  score = 0.15*recall + 0.40*relevance + 0.20*activation + 0.10*usefulness + 0.15*rehearsal
  □ Verifier que la somme des poids = 1.0
  □ Verifier que score_total = somme ponderee des composantes
```

## T6.2 — P15 Query Expansion
```
TYPE DE TEST: la query est enrichie via le mycelium

PARAMETRES: P15 strength >= 3 (ligne 2226), get_related top_n=3 (ligne 2225)

SETUP: mycelium ou:
  "REST" ↔ "API" (count=15)
  "REST" ↔ "HTTP" (count=12)
  "REST" ↔ "JSON" (count=8)
  "REST" ↔ "obscure_term" (count=1, strength < 3 → ignore)

APPEL: boot("REST", repo_path=TEMP_REPO)

METRIQUES:
  □ Query expandue contient "API" (strength >= 3)
  □ Query expandue contient "HTTP" (strength >= 3)
  □ Query expandue ne contient PAS "obscure_term" (strength < 3)
  □ len(query_expandue) > len(query_originale)
  □ Des branches sans le mot "REST" mais avec "API" → trouvees
```

## T6.3 — P23 Auto-Continue (query vide)
```
SETUP: session_index.json:
  {"sessions":[{"date":"2026-03-12","concepts":["docker","compose","deploy"],"file":"s.mn"}]}

APPEL: boot("", repo_path=TEMP_REPO) (SANS query)

METRIQUES:
  □ Les concepts "docker","compose","deploy" sont utilises
  □ La branche "devops" est chargee (si arbre de T6.1 en place)
  □ Boot ne crash pas sur query vide
```

## T6.4 — P37 Warm-Up + P22 Session Index
```
SETUP: branch_api avec access_count=5, last_access="2026-03-10"
  session_index.json avec 2 sessions passees

APPEL: boot("api", repo_path=TEMP_REPO)

METRIQUES P37:
  □ branch_api.access_count = 6 (incremente)
  □ branch_api.last_access = "2026-03-12" (aujourd'hui)

METRIQUES P22:
  □ Le session index est consulte (verifier dans les logs)
  □ Top 2 sessions pertinentes identifiees
```

---

# ═══════════════════════════════════════════
# CATEGORIE 7 — FORMULES MATHEMATIQUES EXACTES
# ═══════════════════════════════════════════

### IMPORTANT: pour chaque formule, calculer le resultat ATTENDU a la main, puis comparer avec le code. Un ecart > 5% = FAIL.

## T7.1 — Ebbinghaus Recall
```
FORMULE: p = 2^(-delta / h)
  h = h_base * 2^min(reviews, 10) * usefulness^beta * V6B_factor * V4B_factor * I1_factor
  h_base = 7 jours (ligne 457)
  beta = 0.5 (ligne 427)

CAS 1 (basique, tous facteurs = 1):
  delta=1j, reviews=0, usefulness=1.0, valence=0, arousal=0, fisher=0, danger=0
  h = 7 * 2^0 * 1.0^0.5 * 1 * 1 * 1 = 7.0
  recall = 2^(-1/7) = 0.9057
  □ Code retourne ≈ 0.906 (tolerance +-0.01)

CAS 2 (reviews boostent h):
  delta=7j, reviews=3, usefulness=1.0, reste=0
  h = 7 * 2^3 = 56.0
  recall = 2^(-7/56) = 2^(-0.125) = 0.9170
  □ Code retourne ≈ 0.917

CAS 3 (usefulness baisse h — A1):
  delta=7j, reviews=0, usefulness=0.1
  h = 7 * 1 * 0.1^0.5 = 7 * 0.3162 = 2.214
  recall = 2^(-7/2.214) = 2^(-3.162) = 0.1117
  □ Code retourne ≈ 0.112

CAS 4 (valence booste h — V6B):
  delta=7j, reviews=0, usefulness=1.0, valence=-0.8, arousal=0.5
  V6B_factor = 1 + 0.3*|(-0.8)| + 0.2*0.5 = 1 + 0.24 + 0.10 = 1.34
  h = 7 * 1.34 = 9.38
  recall = 2^(-7/9.38) = 2^(-0.746) = 0.5962
  □ Code retourne ≈ 0.596

CAS 5 (Fisher booste h — V4B):
  delta=7j, reviews=0, usefulness=1.0, fisher=0.8
  V4B_factor = 1 + 0.5*0.8 = 1.40
  h = 7 * 1.40 = 9.80
  recall = 2^(-7/9.80) = 2^(-0.714) = 0.6099
  □ Code retourne ≈ 0.610

CAS 6 (danger booste h — I1):
  delta=7j, reviews=0, usefulness=1.0, danger_score=0.7
  I1_factor = 1 + 0.7 = 1.70
  h = 7 * 1.70 = 11.9
  recall = 2^(-7/11.9) = 2^(-0.588) = 0.6647
  □ Code retourne ≈ 0.665

CAS 7 (TOUT combine):
  delta=14j, reviews=2, usefulness=0.8, valence=-0.5, arousal=0.3, fisher=0.6, danger=0.4
  h = 7 * 2^2 * 0.8^0.5 * (1+0.3*0.5+0.2*0.3) * (1+0.5*0.6) * (1+0.4)
  h = 7 * 4 * 0.8944 * 1.21 * 1.30 * 1.40
  h = 7 * 4 * 0.8944 * 1.21 * 1.30 * 1.40 = 54.92
  recall = 2^(-14/54.92) = 2^(-0.2549) = 0.8381
  □ Code retourne ≈ 0.838

CAS 8 (edge: usefulness=None → clamp a 0.1):
  □ Pas de crash, usefulness traite comme 0.1

CAS 9 (edge: delta=0 → recall ≈ 1.0):
  □ Code retourne ≈ 1.0

CAS 10 (edge: delta=365j, reviews=0, usefulness=0.1):
  h = 7 * 0.1^0.5 = 2.214
  recall = 2^(-365/2.214) ≈ 0 (10^-50 magnitude)
  □ Code retourne ≈ 0.0 (pas NaN, pas Inf)
```

## T7.2 — A2 ACT-R Base-Level Activation (Anderson 1993)
```
FORMULE: B = ln(sum(t_j^(-d)))
  d = 0.5 (ligne 479)
  t_j = jours depuis j-eme acces (minimum 1 pour eviter 0^(-0.5))
  Blend: recall_final = 0.7 * ebbinghaus + 0.3 * actr_normalized (ligne 2419)
  actr_normalized = sigmoid(B) = 1/(1+exp(-B))

CAS 1 (5 acces connus):
  t = [1, 3, 7, 14, 30] jours
  sum = 1^(-0.5) + 3^(-0.5) + 7^(-0.5) + 14^(-0.5) + 30^(-0.5)
      = 1.0 + 0.5774 + 0.3780 + 0.2673 + 0.1826
      = 2.4053
  B = ln(2.4053) = 0.8776
  actr_norm = 1/(1+exp(-0.8776)) = 1/(1+0.4159) = 0.7063
  □ B ≈ 0.878 (tolerance +-0.05)
  □ actr_norm ≈ 0.706

CAS 2 (blend avec Ebbinghaus):
  Si ebbinghaus = 0.7:
  recall_final = 0.7*0.7 + 0.3*0.706 = 0.49 + 0.212 = 0.702
  □ recall_final ≈ 0.702

CAS 3 (historique synthetique — pas d'access_history):
  Code synthetise: spread count acces uniformement sur days_ago
  access_count=5, last_access=10j ago
  → t_j = [2, 4, 6, 8, 10] jours (espace uniformement)
  sum = 0.7071 + 0.5 + 0.4082 + 0.3536 + 0.3162 = 2.2851
  B = ln(2.2851) = 0.8263
  □ B ≈ 0.826

CAS 4 (edge: historique VIDE, access_count=0):
  □ Pas de crash
  □ B = 0 ou valeur par defaut → actr_norm = 0.5

CAS 5 (edge: access_history_cap = 10):
  15 acces fournis → seuls les 10 plus recents comptes (ligne 596)
  □ len(acces utilises) = 10, pas 15
```

## T7.3 — V4B EWC Fisher Importance (Kirkpatrick 2017)
```
FORMULE:
  fisher_raw = access_count * usefulness * td_value
  fisher_importance = fisher_raw / max(all_fisher_raw) ∈ [0, 1]
  Effet: h *= (1 + lambda_ewc * fisher) avec lambda_ewc=0.5

SETUP: 3 branches:
  A: access=20, usefulness=0.9, td_value=0.8 → raw = 20*0.9*0.8 = 14.4
  B: access=5,  usefulness=0.3, td_value=0.2 → raw = 5*0.3*0.2 = 0.3
  C: access=10, usefulness=0.6, td_value=0.5 → raw = 10*0.6*0.5 = 3.0

  max_raw = 14.4
  fisher_A = 14.4/14.4 = 1.0
  fisher_B = 0.3/14.4 = 0.021
  fisher_C = 3.0/14.4 = 0.208

METRIQUES:
  □ fisher_A ≈ 1.0
  □ fisher_B ≈ 0.021
  □ fisher_C ≈ 0.208
  □ h_A_boost = 1 + 0.5*1.0 = 1.50 (50% plus long a oublier)
  □ h_B_boost = 1 + 0.5*0.021 = 1.01 (quasi rien)
  □ h_C_boost = 1 + 0.5*0.208 = 1.10
  □ fisher_A > fisher_C > fisher_B (ordre strict)
```

## T7.4 — V2B TD-Learning (Schultz/Dayan/Montague 1997)
```
FORMULE:
  delta = reward + gamma * V(next) - V(current)
  V(current) += alpha * delta
  gamma=0.9, alpha=0.1 (lignes 5344-5345)
  reward = concept_overlap / branch_concepts ∈ [0,1]
  V(next) = mean_td across all branches

SETUP: branche avec td_value=0.5, usefulness=0.4
  Session concepts overlap = 3/5 → reward = 0.6
  Mean td across all branches = 0.3

  delta = 0.6 + 0.9*0.3 - 0.5 = 0.6 + 0.27 - 0.5 = 0.37
  new_td = 0.5 + 0.1*0.37 = 0.537
  usefulness_new = 0.7*0.4 + 0.3*0.6 + max(0, 0.37)*0.1 = 0.28 + 0.18 + 0.037 = 0.497

METRIQUES:
  □ delta ≈ 0.37
  □ new_td ≈ 0.537 (tolerance +-0.02)
  □ usefulness ≈ 0.497 (tolerance +-0.02)
  □ td_value clampe dans [0, 1]
  □ usefulness clampe dans [0, 1]
  □ PIEGE: reward=0 (aucun overlap) → delta negatif → td_value baisse
```

---

# ═══════════════════════════════════════════
# CATEGORIE 8 — PRUNING AVANCE
# ═══════════════════════════════════════════

## T8.1 — I1 Danger Theory (Greensmith 2008)
```
FORMULE (lignes 5023-5042):
  danger = 0.4*error_rate + 0.3*retry_rate + 0.2*switch_rate + 0.1*chaos_ratio
  error_rate = (lignes E>) / total_lignes
  retry_rate = min(1.0, count(retry|debug|fix|error|traceback) / total * 5)
  switch_rate = min(1.0, topic_switches / total * 10)
  chaos_ratio = min(1.0, max(0, 1 - ratio/5))
  danger clampe [0, 1]

SESSION A (chaotique):
  20 lignes dont:
    5x "E> error: ..." (error_rate = 5/20 = 0.25)
    8x contenant "retry|debug|fix" (retry_rate = min(1, 8/20*5) = min(1, 2.0) = 1.0)
    6x topic switches (switch_rate = min(1, 6/20*10) = min(1, 3.0) = 1.0)
    ratio compressé = 2.0 (chaos_ratio = min(1, max(0, 1-2/5)) = 0.6)
  danger_A = 0.4*0.25 + 0.3*1.0 + 0.2*1.0 + 0.1*0.6
           = 0.10 + 0.30 + 0.20 + 0.06 = 0.66
  □ danger_A ≈ 0.66

SESSION B (calme):
  20 lignes dont:
    0x E> (error_rate = 0)
    0x retry/debug/fix (retry_rate = 0)
    1x topic switch (switch_rate = min(1, 1/20*10) = 0.5)
    ratio = 8.0 (chaos_ratio = max(0, 1-8/5) = max(0, -0.6) = 0)
  danger_B = 0.4*0 + 0.3*0 + 0.2*0.5 + 0.1*0 = 0.10
  □ danger_B ≈ 0.10

METRIQUES:
  □ danger_A ≈ 0.66 > 0.5 (session chaotique)
  □ danger_B ≈ 0.10 < 0.2 (session calme)
  □ danger_A > danger_B * 3 (ecart significatif)
  □ Effet sur h: h_A *= (1 + 0.66) = 1.66x → branche de session chaotique oublie 66% plus lentement
```

## T8.2 — I2 Competitive Suppression (Perelson 1989)
```
FORMULE (lignes 3440-3480):
  effective_recall = recall - alpha * sum(NCD_sim * recall_j)
  alpha = 0.1 (ligne 3443)
  Seulement si NCD < 0.4 ET recall < 0.4

SETUP: 3 branches, toutes recall=0.30:
  A et B: NCD(A,B) = 0.25 (tres similaires)
  A et C: NCD(A,C) = 0.80 (tres differentes)
  B et C: NCD(B,C) = 0.75

  Pour A: suppression par B uniquement (NCD < 0.4)
    eff_recall_A = 0.30 - 0.1 * (1-0.25) * 0.30 = 0.30 - 0.1*0.75*0.30 = 0.30 - 0.0225 = 0.2775

  Pour B: suppression par A
    eff_recall_B = 0.30 - 0.1 * (1-0.25) * 0.30 = 0.2775

  Pour C: aucune suppression (NCD > 0.4 avec tout le monde)
    eff_recall_C = 0.30

METRIQUES:
  □ eff_recall_A ≈ 0.278 (supprime par B)
  □ eff_recall_B ≈ 0.278 (supprime par A)
  □ eff_recall_C = 0.30 exactement (pas de suppression)
  □ eff_recall_C > eff_recall_A (C gagne car unique)
  □ PIEGE: branche avec recall=0.5 → PAS touchee (seuil 0.4, ligne 3451)
```

## T8.3 — I3 Negative Selection (Forrest 1994)
```
FORMULE (lignes 3482-3523):
  dist = |lines - median_lines| / median_lines + |fact_ratio - median_fact_ratio| / median_fact_ratio
  Si dist > 2.0 → anomalie → demote

SETUP: 5 branches:
  Normal_1: 20 lignes, 5 tags (fact_ratio=0.25)
  Normal_2: 25 lignes, 7 tags (fact_ratio=0.28)
  Normal_3: 18 lignes, 4 tags (fact_ratio=0.22)
  Anomale:  500 lignes, 0 tags (fact_ratio=0.00)
  Petite:   3 lignes, 3 tags (fact_ratio=1.00)

  median_lines ≈ 20, median_fact_ratio ≈ 0.25

  Anomale: dist = |500-20|/20 + |0-0.25|/0.25 = 24 + 1 = 25.0 >> 2.0 → ANOMALIE
  Normal_1: dist = |20-20|/20 + |0.25-0.25|/0.25 = 0 + 0 = 0.0 → OK
  Petite: dist = |3-20|/20 + |1.0-0.25|/0.25 = 0.85 + 3.0 = 3.85 → ANOMALIE aussi

METRIQUES:
  □ Anomale demotee (dist=25 >> 2.0)
  □ Normal_1 PAS touchee (dist=0)
  □ Petite: documenter si demotee ou pas (dist=3.85 > 2.0 → devrait etre demotee)
  □ Seuil demote: recall >= 0.15 (ligne 3534) — si recall < 0.15 deja cold, pas besoin
```

## T8.4 — V5B Cross-Inhibition Winner-Take-All (Seeley et al. 2012)
```
FORMULE (lignes 2524-2554):
  dN/dt = r*(1-N/K)*N - beta*sum(N_j*N)
  beta=0.05, K=1.0, dt=0.1, 5 iterations
  Normalise avant, denormalise apres

SETUP: 3 branches scores initiaux = [0.80, 0.75, 0.30]
  top_score = 0.80
  Normalise: [1.00, 0.9375, 0.375]

  5 iterations dt=0.1 avec beta=0.05, K=1.0, r=1.0:
  (Calcul simplifie — le code fait Euler forward)

  Iteration 1:
    N0 = 1.0:  growth = 1*(1-1/1)*1 = 0, inhib = 0.05*(0.9375+0.375)*1 = 0.0656
               new = 1.0 + 0.1*(0 - 0.0656) = 0.9934
    N1 = 0.9375: growth = 1*(1-0.9375)*0.9375 = 0.0586, inhib = 0.05*(1+0.375)*0.9375 = 0.0645
               new = 0.9375 + 0.1*(0.0586-0.0645) = 0.9369
    N2 = 0.375: growth = 1*(1-0.375)*0.375 = 0.2344, inhib = 0.05*(1+0.9375)*0.375 = 0.0363
               new = 0.375 + 0.1*(0.2344-0.0363) = 0.3948

METRIQUES:
  □ Apres 5 iterations, N0 a BAISSE (inhibition par les autres)
  □ N1 a baisse aussi mais PLUS que N0 (le plus faible des deux forts perd plus)
  □ N2 (0.375) a MONTE (logistic growth depasse l'inhibition car loin de K)
  □ L'ecart entre N0 et N1 s'est AGRANDI (winner-take-all)
  □ Floor respecte: aucun score < 0.001 (ligne 2548)
  □ Denormalise: scores finaux = Ni * top_score
  □ PIEGE: le winner-take-all ne change pas l'ORDRE dans ce cas (0.80 reste premier)
    mais DIMINUE l'ecart entre 1er et 3eme
```

## T8.5 — Sleep Consolidation (Wilson & McNaughton 1994)
```
TYPE DE TEST: merge de branches similaires + re-compression

PARAMETRES: NCD threshold = 0.6 (ligne 3168)

SETUP: 3 branches COLD:
  cold_a.mn (15 lignes): "api rest endpoint json flask routing middleware auth jwt validation"
  cold_b.mn (12 lignes): "api rest endpoint json django routing views models ORM migrations"
  cold_c.mn (10 lignes): "quantum physics electron photon duality wavelength frequency"

  NCD(a,b) ≈ 0.35 (similaires — memes mots de base + variantes)
  NCD(a,c) ≈ 0.85 (completement differents)
  NCD(b,c) ≈ 0.85

APPEL: _sleep_consolidate([cold_a, cold_b, cold_c], nodes)

METRIQUES:
  □ cold_a et cold_b MERGEES en 1 branche (NCD < 0.6)
  □ cold_c PAS mergee (NCD > 0.6 avec a et b)
  □ Le merge contient "flask" ET "django" (contenu des 2)
  □ "api rest endpoint json" apparait 1 seule fois (dedup)
  □ L10 + L11 appliques au merge (re-compression)
  □ Total branches apres: 2 (merge_ab + c), pas 3
  □ Le noeud merge_ab a les tags COMBINES de a et b
  □ V9B: si cold_a avait un tag unique, il est dans le merge (sole-carrier preserved)
```

## T8.6 — H1 Trip Mode (BARE Wave, Carhart-Harris 2014)
```
FORMULE (mycelium.py lignes 1621-1747):
  dn/dt = alpha*n - beta*n*rho
  alpha = 0.04 * (1 + intensity) = 0.04 * 1.5 = 0.06 (intensity=0.5)
  beta = 0.02 * (1 - intensity*0.8) = 0.02 * 0.6 = 0.012
  tip_survival = alpha - beta * rho_local
  rho_local = (degree_a + degree_b) / 2
  Creer connexion si tip_survival >= 0 OU random() < intensity

SETUP: mycelium avec 2 clusters separes:
  Cluster 1: python, flask, jinja (tous connectes, degree ~3)
  Cluster 2: quantum, physics, electron (tous connectes, degree ~3)
  AUCUNE connexion entre les clusters.

APPEL: m.trip(intensity=0.5, max_dreams=15)

METRIQUES:
  □ De nouvelles connexions ENTRE les clusters (dream connections)
  □ tip_survival pour rho=3: 0.06 - 0.012*3 = 0.024 > 0 → creer
  □ tip_survival pour rho=100: 0.06 - 0.012*100 = -1.14 < 0 → probabiliste
  □ len(dreams) <= 15 (max_dreams)
  □ Entropy calculee: H_after != H_before (la distribution change)
  □ Les connexions creees sont entre clusters distants (pas intra-cluster)
  □ Pas de crash, temps < 30s
```

## T8.7 — H3 Huginn Insights
```
TYPE DE TEST: insights en langage naturel pertinents a la query

SETUP: mycelium avec paires fortes + trous structurels + reves
  .muninn/insights.json avec des entrees variees

APPEL: huginn_think(query_concepts=["api"], top_n=5)

METRIQUES:
  □ Retourne liste de dicts avec champs type + text
  □ len(resultats) <= 5
  □ Types valides: "strong_pair", "structural_hole", "dream", "cluster", "health"
  □ text contient des mots (langage naturel), pas du JSON brut
  □ Au moins 1 insight est lie a "api" (pertinence)
  □ Pas de crash sur query vide
```

---

# ═══════════════════════════════════════════
# CATEGORIE 9 — EMOTIONAL (V6A, V6B, V10A, V10B)
# ═══════════════════════════════════════════

## T9.1 — V6A Emotional Tagging (Hill function, Richter-Levin 2003)
```
TYPE DE TEST: scoring d'arousal par message

DONNEES:
  A: "CRITICAL BUG: the entire production database is DOWN!! Users can't login!! FIX NOW!!"
  B: "The test suite passed. All 42 tests green. No issues."
  C: "I wonder if we should maybe consider possibly looking into the logging"

APPEL: emotional scoring sur chaque

METRIQUES:
  □ arousal(A) > 0.6 (message intense: majuscules, "!!", "CRITICAL", "DOWN")
  □ arousal(B) < 0.3 (message calme)
  □ arousal(C) < 0.2 (message hesitant/mou)
  □ arousal(A) > arousal(B) > arousal(C) (ordre strict)
  □ valence(A) < 0 (negatif: bug, down)
  □ valence(B) > 0 (positif: passed, green)
```

## T9.2 — V6B Valence-Modulated Decay (Talmi 2013)
```
FORMULE: h *= (1 + alpha_v * |valence| + alpha_a * arousal)
  alpha_v=0.3, alpha_a=0.2 (ligne 428)

CAS 1 (session negative intense):
  valence=-0.8, arousal=0.7
  factor = 1 + 0.3*0.8 + 0.2*0.7 = 1 + 0.24 + 0.14 = 1.38
  h *= 1.38 → 38% plus lent a oublier
  □ factor ≈ 1.38

CAS 2 (session positive calme):
  valence=+0.5, arousal=0.1
  factor = 1 + 0.3*0.5 + 0.2*0.1 = 1 + 0.15 + 0.02 = 1.17
  □ factor ≈ 1.17

CAS 3 (session neutre):
  valence=0.0, arousal=0.0
  factor = 1 + 0 + 0 = 1.00 (pas de modulation)
  □ factor = 1.00 exactement

METRIQUES:
  □ factor(cas1) > factor(cas2) > factor(cas3) (ordre strict)
  □ h_negative / h_neutral = 1.38 / 1.00 = 1.38 (38% difference — mesurable)
  □ PIEGE: valence=0 → factor=1.0 → pas d'impact (correct)
```

## T9.3 — V10B Russell Circumplex
```
TYPE DE TEST: mapping (valence, arousal) → quadrant emotionnel

Russell 1980: 2 axes, 4 quadrants:
  Haut-droit:   valence>0, arousal>0.5 → excited/happy
  Haut-gauche:  valence<0, arousal>0.5 → angry/stressed
  Bas-droit:    valence>0, arousal<0.5 → calm/content
  Bas-gauche:   valence<0, arousal<0.5 → sad/bored

METRIQUES:
  □ (v=+0.8, a=0.7) → quadrant positif-actif ("excited" ou equivalent)
  □ (v=-0.8, a=0.7) → quadrant negatif-actif ("angry"/"stressed")
  □ (v=+0.5, a=0.1) → quadrant positif-passif ("calm"/"content")
  □ (v=-0.5, a=0.1) → quadrant negatif-passif ("sad"/"bored")
  □ (v=0.0, a=0.0) → "neutral" ou equivalent
  □ Pas de crash sur valeurs extremes (v=1.0, a=1.0)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 10 — SCORING AVANCE
# ═══════════════════════════════════════════

## T10.1 — V5A Quorum Sensing Hill Switch (Waters & Bassler 2005)
```
FORMULE: f(A) = A^n / (K^n + A^n)
  K=2.0, n=3, bonus_max=0.03 (lignes 2497-2502)
  A = nombre de tags co-actives (via spreading activation)

CALCULS A LA MAIN (3 points sur la courbe):
  A=0: f = 0/8 = 0.000         → bonus = 0.03*0 = 0.000
  A=1: f = 1/9 = 0.111         → bonus = 0.03*0.111 = 0.003
  A=2: f = 8/16 = 0.500        → bonus = 0.03*0.5 = 0.015 (point d'inflexion a K=2)
  A=3: f = 27/35 = 0.771       → bonus = 0.03*0.771 = 0.023
  A=5: f = 125/133 = 0.940     → bonus = 0.03*0.94 = 0.028
  A=10: f = 1000/1008 = 0.992  → bonus = 0.03*0.992 = 0.030

METRIQUES:
  □ A=0 → bonus ≈ 0.000
  □ A=1 → bonus ≈ 0.003
  □ A=2 → bonus ≈ 0.015 (point d'inflexion: 50% du max)
  □ A=3 → bonus ≈ 0.023
  □ A=5 → bonus ≈ 0.028
  □ A=10 → bonus ≈ 0.030 (saturation)
  □ La courbe est SIGMOIDE: lente en bas, rapide au milieu, sature en haut
  □ Le point d'inflexion est a A=K=2.0 (biologiquement correct)
  □ Bonus TOUJOURS dans [0, 0.03]
```

## T10.2 — V1A Coupled Oscillator (Yekutieli 2005)
```
FORMULE (lignes 2504-2517):
  coupling_sum = sum(C * (temp_j - temp_i)) pour les branches liees
  C = 0.02 par connexion (coupling strength)
  Bonus = clamp(coupling_sum, -0.02, +0.02)

  Pour les top 3 tags de la branche, trouver UN sibling avec ce tag.
  coupling_sum += 0.02 * (sibling_temp - my_temp)

SETUP:
  branch_cold: temp=0.2, tags=["api","rest","json"]
  branch_hot_1: temp=0.9, tags=["api","auth"]       (partage "api")
  branch_hot_2: temp=0.8, tags=["rest","endpoint"]   (partage "rest")
  branch_far:   temp=0.5, tags=["quantum"]            (rien en commun)

  Pour branch_cold:
    tag "api" → sibling branch_hot_1: coupling += 0.02*(0.9-0.2) = 0.014
    tag "rest" → sibling branch_hot_2: coupling += 0.02*(0.8-0.2) = 0.012
    tag "json" → pas de sibling avec "json": coupling += 0
    total = 0.026, clampe a +0.02

METRIQUES:
  □ bonus(branch_cold) = +0.02 (clampe au max, tire vers le haut par les voisins chauds)
  □ Si branch_cold est seule (pas de voisins) → bonus = 0.00
  □ Si branch est PLUS chaude que ses voisins → bonus NEGATIF (tire vers le bas)
    Ex: branch_hot temp=0.9, voisin temp=0.3: coupling = 0.02*(0.3-0.9) = -0.012
  □ Bonus toujours dans [-0.02, +0.02]
  □ L'EFFET: les branches convergent en temperature (oscillateurs couples se synchronisent)
```

## T10.3 — V7B ACO Pheromone (Dorigo 1996)
```
FORMULE (lignes 2438-2447):
  tau = max(0.01, usefulness * recall)  (pheromone = historique)
  eta = max(0.01, relevance)            (heuristique locale = pertinence query)
  aco_score = min(1.0, tau^1 * eta^2)
  bonus = 0.05 * aco_score
  bonus_max = 0.05

CAS 1 (branche utile + pertinente):
  usefulness=0.8, recall=0.7, relevance=0.9
  tau = 0.8*0.7 = 0.56
  eta = 0.9
  aco = min(1.0, 0.56 * 0.81) = min(1.0, 0.4536) = 0.4536
  bonus = 0.05*0.4536 = 0.0227
  □ bonus ≈ 0.023

CAS 2 (branche inutile):
  usefulness=0.1, recall=0.1, relevance=0.9
  tau = max(0.01, 0.01) = 0.01
  aco = min(1.0, 0.01 * 0.81) = 0.0081
  bonus = 0.05*0.0081 = 0.0004
  □ bonus ≈ 0.000 (quasi nul malgre haute relevance — pas de pheromone)

CAS 3 (branche utile mais pas pertinente):
  usefulness=0.9, recall=0.9, relevance=0.1
  tau = 0.81
  eta = max(0.01, 0.1) = 0.1
  aco = min(1.0, 0.81 * 0.01) = 0.0081
  bonus = 0.0004
  □ bonus ≈ 0.000 (eta^2 ecrase — la pertinence domine car beta=2)

METRIQUES:
  □ Cas 1 >> Cas 2 et Cas 3 (il faut les DEUX: pheromone + pertinence)
  □ eta^2 penalise fortement la non-pertinence (beta=2 dans Dorigo)
  □ Bonus dans [0, 0.05]
```

## T10.4 — V11B Boyd-Richerson 3 Biases Culturels
```
TYPE DE TEST: 3 formules distinctes, chacune testee separement

BIAIS 1 — CONFORMISTE (lignes 2476-2477):
  dp = beta * p * (1-p) * (2p-1)
  beta = 0.3, bonus_max = 0.15

  CALCULS (5 points sur la courbe logistique):
    p=0.1: dp = 0.3 * 0.1 * 0.9 * (0.2-1) = 0.3 * 0.09 * (-0.8) = -0.0216
           bonus = 0.15 * max(0, -0.0216) = 0.000 (negatif → 0)
    p=0.3: dp = 0.3 * 0.3 * 0.7 * (-0.4) = -0.0252
           bonus = 0.000
    p=0.5: dp = 0.3 * 0.5 * 0.5 * 0 = 0.000 (point d'inflexion!)
           bonus = 0.000
    p=0.7: dp = 0.3 * 0.7 * 0.3 * 0.4 = 0.0252
           bonus = 0.15 * 0.0252 = 0.004
    p=0.9: dp = 0.3 * 0.9 * 0.1 * 0.8 = 0.0216
           bonus = 0.15 * 0.0216 = 0.003

  □ p < 0.5 → bonus = 0 (impopulaire penalise, ou ignore)
  □ p = 0.5 → bonus = 0 (point neutre)
  □ p > 0.5 → bonus > 0 (populaire booste)
  □ POINT D'INFLEXION a p=0.5 (dp change de signe — biologiquement correct)
  □ Bonus max ≈ 0.004 dans cette range (loin du 0.15 max — car dp est petit)

BIAIS 2 — PRESTIGE (lignes 2482):
  prestige = td_value * usefulness
  bonus = 0.06 * prestige
  bonus_max = 0.06

  □ td=0.9, usefulness=0.8: prestige=0.72, bonus=0.043
  □ td=0.1, usefulness=0.1: prestige=0.01, bonus=0.001
  □ Bonus dans [0, 0.06]

BIAIS 3 — GUIDED VARIATION (lignes 2488):
  guided = mu * (mean_usefulness - usefulness)
  mu = 0.1
  bonus = 0.06 * max(0, guided)

  □ usefulness=0.3, mean=0.6: guided=0.1*(0.6-0.3)=0.03, bonus=0.06*0.03=0.002
  □ usefulness=0.8, mean=0.6: guided=0.1*(0.6-0.8)=-0.02, bonus=0 (negatif → 0)
  □ Branche SOUS la moyenne: boost (exploration encouragee)
  □ Branche AU-DESSUS: pas de boost
```

## T10.5 — B4 Predict Next (Endsley L3)
```
FORMULE (lignes 2909-2982):
  1. spread_activation(current_concepts) → activated concepts
  2. Score branche = sum(activation[tag] for tag in branch.tags)
  3. Penalite: si recall > 0.8, score *= 0.3 (deja frais)
  4. Retourner top_n non-chargees

SETUP: session parle de ["api","rest"]
  Spreading: "api"→"endpoint"(0.8), "api"→"json"(0.6), "rest"→"http"(0.7)
  branch_endpoint: tags=["endpoint","json"], recall=0.3 (pas frais)
  branch_loaded: tags=["api","rest"], recall=0.9 (deja chargee + frais)
  branch_unrelated: tags=["quantum"], recall=0.2

  score_endpoint = 0.8 + 0.6 = 1.4 (pas de penalite car recall < 0.8)
  score_loaded = activation("api") + activation("rest") mais recall=0.9 → *0.3
  score_unrelated = 0 (aucun tag active)

METRIQUES:
  □ branch_endpoint en tete des predictions
  □ branch_loaded penalisee (recall > 0.8 → *0.3)
  □ branch_unrelated score ≈ 0
  □ BUG A VERIFIER: predict_next retourne des CONCEPTS ou des BRANCHES?
    Le code de scoring (ligne 2459-2462) attend des branches.
    Si mismatch → bonus B4 vaut toujours 0 → DOCUMENTER
  □ bonus_max = 0.03 (ligne 2462)
```

## T10.6 — B5 Session Mode + B6 RPD Type
```
B5 — SESSION MODE (lignes 3025-3033):
  diversity = nb_concepts_uniques / total_concepts
  Si diversity > 0.6 → "divergent", k=5 (sigmoid large, explore)
  Si diversity < 0.4 → "convergent", k=20 (sigmoid sharp, focus)
  Sinon → "balanced", k=10

  Session A: 20 concepts, 18 uniques → diversity=0.9 → "divergent", k=5
  Session B: 20 concepts, 5 uniques (repetes) → diversity=0.25 → "convergent", k=20
  Session C: 20 concepts, 10 uniques → diversity=0.5 → "balanced", k=10

  □ Session A → k=5
  □ Session B → k=20
  □ Session C → k=10
  □ L'effet du k: spreading activation avec k=5 est PLUS large (plus de resultats faibles survivent)
    vs k=20 qui est sharp (seuls les forts survivent)

B6 — RPD TYPE (lignes 2353-2378):
  Classifie par patterns dans la session.

  VERIFIER les poids:
    base:    recall=0.15, relevance=0.40, activation=0.20, usefulness=0.10, rehearsal=0.15
    debug:   recall=0.20, usefulness=0.15, rehearsal=0.10 (+ les autres a ajuster)
    explore: activation=0.30, relevance=0.30, recall=0.10
    review:  rehearsal=0.25, relevance=0.35, recall=0.10

  □ INVARIANT: la somme des 5 poids = 1.0 pour CHAQUE mode
    base:    0.15+0.40+0.20+0.10+0.15 = 1.00 ✓
    debug:   0.20+?+?+0.15+0.10 = verifier = 1.00?
    explore: 0.10+0.30+0.30+?+? = verifier = 1.00?
    review:  0.10+0.35+?+?+0.25 = verifier = 1.00?
  □ Si somme != 1.0 pour un mode → BUG
```

---

Fin de la partie 2/3.
La partie 3 couvre: Pipeline end-to-end, Edge cases, KIComp, Reconsolidation B1, Virtual branches P20c, V8B Active Sensing, et le resume final.
