# BATTERIE DE TESTS REELS — MUNINN V3 — PARTIE 3/3

Suite des parties 1 et 2. Memes regles, meme setup, meme RESULTS_BATTERY_V3.md.

---

# ═══════════════════════════════════════════
# CATEGORIE 11 — PIPELINE END-TO-END
# ═══════════════════════════════════════════

## T11.1 — Compress Transcript complet
```
TYPE DE TEST: pipeline L0-L7+L10+L11 sur un vrai transcript

SETUP: generer un faux transcript JSONL de 100 messages:
  - 40 user messages:
      10 decisions: "I think we should use X", "Let's switch to Y"
      10 questions: "How does Z work?", "What's the status of W?"
      10 bugs: "This crashes when...", "Error: timeout on..."
      10 faits: "accuracy=94.2%", "deployed v3.1 on 2026-03-10", "15ms latency"
  - 40 assistant messages:
      Chacun commence par un tic verbal ("Let me analyze...", "I'll look into...")
      Suivi de contenu reel avec des faits et des decisions
  - 20 tool_results:
      5x "cat somefile.py" (200 lignes de code chacun)
      5x "git diff" (100 lignes chacun)
      5x "ls -la" (50 lignes chacun)
      5x "grep pattern" (30 lignes chacun)
  - Inclure EXACTEMENT ces 5 nombres: 94.2, 15, 3.1, 2026, 4287
  - Inclure 1 faux token: "ghp_ABC123DEF456GHI789JKL012MNO345PQR678"
  - Inclure 3 decisions explicites:
      "decided to use PostgreSQL over MySQL"
      "switched from REST to GraphQL"
      "chose Redis for session caching"

APPEL: compress_transcript(jsonl_path, repo_path=TEMP_REPO)

METRIQUES RATIO:
  □ Le .mn existe dans SESSIONS_DIR
  □ Compter tokens tiktoken (ou len//4 si tiktoken absent) avant et apres
  □ Ratio >= x2.0 minimum (attendu x4+ sur du vrai transcript)
  □ Si ratio < x2.0: FAIL — le pipeline compresse pas assez

METRIQUES FACTS:
  □ "94.2" PRESENT (spot check nombre 1)
  □ "15" PRESENT — utiliser `"15" in mn_text`, PAS `\b15\b` (qui ne matche pas "15ms")
  □ "3.1" PRESENT (version)
  □ "4287" PRESENT
  □ 2 des 3 decisions sont taggees D>
  □ Au moins 1 bug/error est tagge B> ou E>

METRIQUES SECURITE:
  □ "ghp_" ABSENT de la sortie (secret filtre)
  □ "ABC123DEF456" ABSENT
  □ Pas de cle API, token, mot de passe dans la sortie

METRIQUES QUALITE:
  □ Pas de ligne vide consecutive (max 2 newlines d'affilee)
  □ Pas de tic verbal ("Let me analyze", "I'll look into") dans la sortie (P28)
  □ Les code blocks sont compresses (P17)
  □ Les tool_results sont strips (L0)

METRIQUES PERF:
  □ Temps < 60s pour 100 messages
  □ Si > 60s: flag SLOW + identifier le bottleneck
```

## T11.2 — Grow Branches from Session
```
TYPE DE TEST: le .mn genere se segmente en branches

SETUP: un .mn avec 3 sections ##:
  "## API Design\nD> decided REST over GraphQL\nF> 3 endpoints: /users, /items, /search\nF> latency target=50ms"
  "## Database\nD> chose PostgreSQL\nF> 2M rows expected\nB> migration script fails on NULL columns"
  "## Testing\nF> 42 pytest tests passing, pytest fixtures shared\nF> coverage=89%, test coverage tracked\nD> adopted pytest over unittest for testing\nF> CI runs on every push, testing on merge"
    NOTE: les keywords doivent apparaitre 2+ fois pour que extract_tags les detecte.
    Repeter "pytest" et "test/testing" sinon la section a 0 tags et le test echoue.

APPEL: grow_branches_from_session(mn_path, repo_path=TEMP_REPO)

METRIQUES:
  □ tree.json a au moins 3 nouvelles branches
  □ Branche "API Design" a tags incluant "api" ou "rest" ou "graphql"
  □ Branche "Database" a tags incluant "postgresql" ou "sql" ou "migration"
  □ Branche "Testing" a tags incluant "pytest" ou "testing" ou "coverage"
  □ Chaque branche a un .mn dans TREE_DIR
  □ Le mycelium a PLUS d'edges qu'avant (verifie avec COUNT avant/apres)
  □ MERGE: si une branche "API" existait deja, verifier le merge (NCD < 0.4 → merge)
```

## T11.3 — Feed complet (simulation)
```
TYPE DE TEST: pipeline complet feed_from_hook sans le hook reel

SETUP: transcript JSONL de 50 messages + arbre minimal + mycelium vide

APPEL: simuler le pipeline:
  1. count = feed_from_transcript(jsonl, TEMP_REPO) → mycelium nourri
  2. mn_path, sentiment = compress_transcript(jsonl, TEMP_REPO) → .mn cree
  3. grow_branches_from_session(mn_path, TEMP_REPO) → branches creees
  4. refresh_tree_metadata → temperatures mises a jour
  5. m.sync_to_meta() → meta synce (vers TEMP_META)

METRIQUES ETAPE PAR ETAPE:
  □ Etape 1: count > 0, mycelium edges > 0
  □ Etape 2: .mn existe, taille > 0, ratio > x2
  □ Etape 3: tree.json a root + nouvelles branches
  □ Etape 4: temperatures mises a jour dans tree.json
  □ Etape 5: meta DB a TEMP_META existe, n_synced > 0
  □ TOUT sans crash, temps total < 120s
```

---

# ═══════════════════════════════════════════
# CATEGORIE 12 — EDGE CASES & ROBUSTESSE
# ═══════════════════════════════════════════

## T12.1 — Cold Start total
```
IMPORTANT: avant ce test, reset muninn._CB = None pour vider le cache codebook.
Sinon le codebook d'un test precedent pollue les resultats (bug reel corrige).

SETUP: repo VIDE. Rien du tout.
APPEL: boot("hello world", repo_path=TEMP_REPO)
METRIQUES:
  □ Pas de crash (pas de traceback Python)
  □ Retour propre: root vide ou message "no data"
  □ stderr ne contient pas de traceback non-catche
```

## T12.2 — Fichier .mn corrompu
```
SETUP: ecrire 1024 octets random (os.urandom(1024)) dans branch.mn
  Le referencer dans tree.json avec un hash bidon.

APPEL: boot (charge cette branche) puis prune (tente de la lire)
METRIQUES:
  □ Pas de crash sur boot
  □ Pas de crash sur prune
  □ La branche corrompue est ignoree/signalée
  □ Les autres branches fonctionnent normalement
```

## T12.3 — Mycelium vide (0 connexions)
```
SETUP: Mycelium(TEMP_REPO) sans rien observer

APPELS:
  m.get_related("test")          → []
  m.spread_activation(["test"])  → {} ou []
  m.transitive_inference("test") → []
  m.detect_blind_spots()         → []
  m.detect_anomalies()           → dict avec listes vides
  m.trip(intensity=0.5)          → pas de crash

METRIQUES:
  □ TOUS retournent des collections vides
  □ AUCUN crash (pas d'exception non-catchee)
  □ Temps < 1s chacun
```

## T12.4 — Performance: 500 branches
```
SETUP: generer 500 branches:
  Pour chaque: 20 lignes de contenu random, 3-5 tags random, dates random
  Mycelium avec 1000 connexions random

APPEL: boot("test query", repo_path=TEMP_REPO)

METRIQUES:
  □ Boot termine en < 30s
  □ Budget 30K tokens respecte (pas plus de ~20 branches chargees)
  □ Si > 30s: flag SLOW + profiler pour trouver le bottleneck
    (suspect: I2 O(n²) capping, eigsh spectral, NCD pairwise)
  □ Pas de MemoryError
```

## T12.5 — Unicode et caracteres speciaux
```
DONNEES:
  A: "The build succeeded 🎉 with 0 errors"
  B: "压缩比 x4.5 在测试中"
  C: "Le système a échoué à 14h30"
  D: "test\x00value"  (null byte)
  E: "line1\r\nline2\rline3"  (mixed line endings)

APPEL: compress_line() sur chaque

METRIQUES:
  □ A: pas de crash, "0 errors" PRESENT
  □ B: pas de crash, "x4.5" PRESENT
  □ C: pas de crash, "14h30" PRESENT
  □ D: pas de crash (null byte ignore ou strip)
  □ E: pas de crash (line endings normalises)
```

## T12.6 — Lock concurrent
```
SETUP: creer un lock file dans .muninn/hook.lock
APPEL: tenter un feed pendant que le lock existe

METRIQUES:
  □ Le feed attend ou retourne proprement
  □ STALE_SECONDS = 600 (ligne 5396) → si lock a plus de 10 min, il est casse
  □ Pas de deadlock (timeout respecte)
  □ tree.json pas corrompu
```

---

# ═══════════════════════════════════════════
# CATEGORIE 13 — BRICKS RESTANTES
# ═══════════════════════════════════════════

## T13.1 — B1 Reconsolidation (Nader 2000)
```
PARAMETRES (ligne 605-611):
  recall < 0.3
  age > 7 jours
  lines > 3

TYPE DE TEST: re-compression a la lecture des branches cold

SETUP: branche avec:
  recall=0.2, last_access=14 jours ago, 25 lignes
  Contenu: mix de faits tagges et de narratif generique

  Branche exclue: recall=0.5 (trop frais) OU 2 lignes (trop courte)

APPEL: charger la branche (reconsolidation at read time)

METRIQUES:
  □ La branche eligible (recall=0.2, 14j, 25 lignes): lignes_apres < lignes_avant
  □ L10 + L11 appliques (cue distillation + rule extraction)
  □ Les faits tagges D>/B>/F> sont PRESERVES apres reconsolidation
  □ Les lignes narratives generiques sont compressees
  □ La branche avec recall=0.5 n'est PAS re-compressée
  □ La branche avec 2 lignes n'est PAS re-compressée
```

## T13.2 — KIComp Information Density Filter (lignes 632-752)
```
TYPE DE TEST: suppression des lignes basse-densite quand le budget deborde

FORMULE _line_density(line):
  Base par tag: D>=0.9, F>=0.8, B>=0.8, E>=0.7, A>=0.7
  Sans tag: base ≈ 0.1-0.3 selon longueur
  +0.1 par match \d (max +0.3)
  +0.1 par match key=value (max +0.2)
  Short+data (len<80 + digits): +0.1
  Hash/filepath/function: +0.1
  Long narrative (len>120, no digits): score=0.1

DONNEES (10 lignes):
  L1: "D> decided to use Redis"                     → densite=0.9
  L2: "F> accuracy=94.2% (x4.5 improvement)"        → densite=0.8 + 0.3(digits) + 0.2(kv) = cap 1.0
  L3: "B> crash at commit a1b2c3d line 73"           → densite=0.8 + 0.2(digits) + 0.1(hash) = cap 1.0
  L4: "The implementation continues to evolve as we work through the various challenges ahead" → densite=0.1 (long, no digits)
  L5: "I think this is probably going to be fine"    → densite~0.15
  L6: "processed 1.2M rows in 3.5s"                 → densite~0.3 + 0.3(digits) = 0.6
  L7: "Another narrative line without facts"         → densite~0.1
  L8: "E> TypeError: NoneType has no attribute X"    → densite=0.7
  L9: "Yet another line of commentary"              → densite~0.1
  L10: "A> microservice architecture, 12 services"  → densite=0.7 + 0.1(digit) = 0.8

  BUDGET: 7 lignes

  Ordre par densite decroissante: L2/L3(1.0) > L1(0.9) > L10(0.8) > L8(0.7) > L6(0.6) > L5(0.15) > L4/L7/L9(0.1)
  Keep top 7: L2, L3, L1, L10, L8, L6, L5

  NOTE KIComp V4: les lignes taggees (D>/B>/F>/E>/A>) sont PROTEGEES du drop second-pass.
  Meme si leur densite est < 0.98, elles ne sont jamais dans le pool de suppression.
  Verifier: lignes avec densite=0.0 doivent TOUTES etre en bas du classement (sous les non-zero).

METRIQUES:
  □ L4 ("continues to evolve") ABSENT (densite 0.1, narratif long)
  □ L7 ("without facts") ABSENT
  □ L9 ("commentary") ABSENT
  □ L1 (D>) PRESENT — protege par tag meme si densite < 0.98
  □ L2 (F> avec chiffres) PRESENT
  □ L3 (B> avec commit hash) PRESENT
  □ L8 (E>) PRESENT — protege par tag
  □ Total lignes = 7
  □ Toutes les lignes a densite=0.0 sont classees SOUS les lignes a densite > 0
  □ Les densites calculees par le code matchent les calculs ci-dessus (+-0.1)
```

## T13.3 — P20c Virtual Branches
```
PARAMETRES: MAX_VIRTUAL=3, WEIGHT_FACTOR=0.5 (lignes 2069-2071)

SETUP:
  repos.json avec 2 repos: TEMP_REPO et TEMP_REPO_2
  TEMP_REPO_2 a un arbre avec 5 branches pertinentes a la query

APPEL: boot("api design", repo_path=TEMP_REPO)

METRIQUES:
  □ Des branches de TEMP_REPO_2 apparaissent en mode "virtual"
  □ Max 3 branches virtuelles (MAX_VIRTUAL)
  □ Leur score est multiplie par 0.5 (WEIGHT_FACTOR)
  □ Elles ne sont PAS modifiees (read-only — pas de warm-up dessus)
  □ Si TEMP_REPO a assez de branches pertinentes, les virtuelles sont en bas du classement
```

## T13.4 — V8B Active Sensing (Yang et al. 2016)
```
TYPE DE TEST: branches informatives boostees, redondantes penalisees

APPEL: scoring avec V8B actif pendant boot

METRIQUES:
  □ Branche qui AJOUTE des concepts non couverts → bonus
  □ Branche dont les concepts sont deja couverts par des branches chargees → penalite
  □ Le bonus est mesurable (pas +-0.001)
  □ Documenter l'impact: combien de positions gagnees/perdues dans le classement
```

## T13.5 — P29 Recall Mid-Session Search
```
APPEL: recall("redis caching", repo_path=TEMP_REPO)
  Doit chercher dans: sessions, tree branches, errors

METRIQUES:
  □ Retourne des resultats pertinents (contenant "redis" ou "caching")
  □ Cherche dans les .mn des sessions
  □ Cherche dans les branches de l'arbre
  □ Cherche dans errors.json
  □ Pas de crash si aucun resultat
```

## T13.6 — P18 Error/Fix Pairs
```
SETUP: errors.json avec:
  [{"error":"TypeError: NoneType","fix":"add None guard at line 42","date":"2026-03-10"}]

APPEL: boot("TypeError crash", repo_path=TEMP_REPO)

METRIQUES:
  □ L'erreur/fix est surfacee pendant le boot (console ou contenu charge)
  □ La query "TypeError" matche l'erreur stockee
  □ Le fix "add None guard" est visible
  □ Une query sans rapport ("docker deploy") ne surface PAS cette erreur
```

## T13.7 — C4 Real-Time k Adaptation
```
PARAMETRES: k ajuste en temps reel pendant le boot (lignes 2901, 6019)

APPEL: boot avec session en cours qui a un pattern specifique

METRIQUES:
  □ k est ajuste selon la diversite des concepts de la session
  □ Le k final est different du k initial (10) si la session n'est pas balanced
  □ L'effet du k est visible dans les scores de spreading activation
```

---

# ═══════════════════════════════════════════
# CATEGORIE 14 — TESTS GLOBAUX DE COHERENCE
# ═══════════════════════════════════════════

## T14.1 — Score final = somme ponderee exacte
```
TYPE DE TEST: verifier que le score de chaque branche est la somme ponderee des 5 composantes + tous les bonus bio

Pour CHAQUE branche chargee au boot:
  score_base = w_recall*recall + w_relevance*relevance + w_activation*activation + w_usefulness*usefulness + w_rehearsal*rehearsal_need
  bonus_total = V1A + V3A + V3B + V5A + V5B + V7B + V11B_conform + V11B_prestige + V11B_guided + B3 + B4
  score_final = score_base + bonus_total

METRIQUES:
  □ Recalculer score_base a la main pour 3 branches → match code (+-0.01)
  □ Recalculer chaque bonus individuellement → match code (+-0.005)
  □ score_final = score_base + bonus_total (+-0.01)
  □ Le bonus total max theorique: V1A(0.02) + V3A(0.10) + V3B(0.04) + V5A(0.03) + V5B(0.10) + V7B(0.05) + V11B(0.15+0.06+0.06) + B3(0.05) + B4(0.03) = 0.59
    CALCUL: 0.02+0.10+0.04+0.03+0.05+0.15+0.06+0.06+0.05+0.03 = 0.59 (PAS 0.49 — erreur d'arithmetique corrigee)
  □ Verifier que le bonus total d'aucune branche ne depasse 0.59
```

## T14.2 — Impact reel des bio-vecteurs sur le classement
```
TYPE DE TEST: est-ce que les bio-vecteurs CHANGENT l'ordre des branches?

SETUP: 10 branches avec scores base proches (+-0.05)

APPEL A: boot avec tous les bio-vecteurs actifs
APPEL B: boot avec AUCUN bio-vecteur (juste score_base)
  (si pas desactivable: calculer score_base manuellement et comparer)

METRIQUES:
  □ Classement A != Classement B (au moins 1 permutation)
  □ Combien de branches changent de position? N permutations sur 10
  □ Si 0 permutations: les bio-vecteurs n'ont AUCUN impact reel → DOCUMENTER
  □ Top 1 est le meme ou different?
  □ Bonus moyen par branche (tous vecteurs confondus)
  □ Bonus median
  □ Quels vecteurs ont le plus d'impact? (trier par bonus moyen)
```

## T14.3 — Cycle complet: feed → boot → prune → boot
```
TYPE DE TEST: le systeme entier tourne sans regression

SETUP: TEMP_REPO vide

ETAPE 1: bootstrap(TEMP_REPO) → arbre initial
ETAPE 2: feed un transcript de 50 messages → branches, mycelium, meta
ETAPE 3: boot("api design") → verifier branches chargees
ETAPE 4: feed un 2eme transcript (30 messages) → nouvelles branches, merges
ETAPE 5: simuler le passage du temps (patcher last_access a 60 jours ago)
ETAPE 6: prune() → des branches meurent, V9A+ regenere
ETAPE 7: boot("api design") → verifier que les faits regeneres sont accessibles

METRIQUES:
  □ Etape 1-2: pas de crash
  □ Etape 3: au moins 1 branche pertinente chargee
  □ Etape 4: branches existantes mergees OU nouvelles creees
  □ Etape 6: au moins 1 branche dead, V9A+ trigger
  □ Etape 7: les faits tagges de la branche morte sont dans un survivant
  □ Le mycelium a grandi entre etape 1 et etape 7
  □ Temps total < 5 minutes
```

---

# ═══════════════════════════════════════════
# RESUME FINAL
# ═══════════════════════════════════════════

| Cat | Tests | Quoi | Specifique? |
|-----|-------|------|-------------|
| 1  | 11 | Compression L0-L11 | Ratio + faits preserves + word boundary |
| 2  | 6  | Filtres P17-P38 | Patterns specifiques a chaque filtre |
| 3  | 2  | Tagging P14 + C7 | Scores par tag + skeleton matching |
| 4  | 12 | Mycelium complet | SQLite + NCD + spreading + transitive + zones |
| 5  | 10 | Tree & branches | R4 + V9A+ 3 strategies + V9B + bootstrap |
| 6  | 4  | Boot & retrieval | Scoring decompose + expansion + auto-continue |
| 7  | 4  | Formules exactes | Ebbinghaus 10 cas + ACT-R + Fisher + TD |
| 8  | 7  | Pruning avance | I1 danger + I2 suppression + I3 anomaly + V5B WTA + Sleep + Trip + Huginn |
| 9  | 3  | Emotional | V6A arousal + V6B decay + V10B circumplex |
| 10 | 6  | Scoring avance | V5A Hill 6pts + V1A oscillator + V7B ACO 3cas + V11B 3biais + B4 predict + B5/B6 modes |
| 11 | 3  | Pipeline E2E | Compress + grow + feed complet |
| 12 | 6  | Edge cases | Cold start + corrupt + vide + perf 500 + unicode + lock |
| 13 | 7  | Briques restantes | B1 reconsol + KIComp + P20c virtual + V8B sensing + P29 recall + P18 errors + C4 |
| 14 | 3  | Coherence globale | Score = somme + impact reel bio-vecteurs + cycle complet |
| **TOTAL** | **84** | | |

---

## FORMAT DE SORTIE POUR CHAQUE TEST

```markdown
## T7.1 — Ebbinghaus Recall
- STATUS: PASS
- CAS 1: attendu=0.906, obtenu=0.907, delta=0.001 ✓
- CAS 2: attendu=0.917, obtenu=0.918, delta=0.001 ✓
- CAS 3: attendu=0.112, obtenu=0.110, delta=0.002 ✓
- CAS 4: attendu=0.596, obtenu=0.598, delta=0.002 ✓
- CAS 5: attendu=0.610, obtenu=0.611, delta=0.001 ✓
- CAS 6: attendu=0.665, obtenu=0.664, delta=0.001 ✓
- CAS 7: attendu=0.838, obtenu=0.840, delta=0.002 ✓
- CAS 8: usefulness=None → clamp 0.1, pas de crash ✓
- CAS 9: delta=0 → recall=1.000 ✓
- CAS 10: delta=365 → recall≈0.0, pas NaN ✓
- TIME: 0.003s
```

Ou en cas d'echec:

```markdown
## T10.4 — V11B Conformist Bias
- STATUS: FAIL
- CAS p=0.5: attendu dp=0.000, obtenu dp=0.015
- ROOT CAUSE: le code utilise (2p-1) mais SANS le facteur beta=0.3 → formule incomplete
- CODE: ligne 2476, manque la multiplication par _conform_beta
- IMPACT: bonus conformiste 3.3x trop fort
- TIME: 0.01s
```

---

## INSTRUCTIONS FINALES

1. Lance les 84 tests dans l'ordre des categories
2. Log chaque resultat dans tests/RESULTS_BATTERY_V3.md AU FUR ET A MESURE
3. Ne t'arrete pas au premier FAIL — continue tous les tests
4. A la fin, genere un resume:
   - X PASS / Y FAIL / Z SKIP
   - Top 5 bugs les plus critiques (FAIL avec le plus d'impact)
   - Top 3 briques qui ont ZERO impact mesurable (bonus toujours 0 ou +-0.001)
   - Temps total de la batterie
5. Ne modifie JAMAIS le code source
6. Ne propose JAMAIS de fix — juste les faits

C'est un audit. Pas une session de debug. Les chiffres parlent.
