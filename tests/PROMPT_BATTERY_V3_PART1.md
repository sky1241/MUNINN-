# BATTERIE DE TESTS REELS — MUNINN V3 — PARTIE 1/3

## TON ROLE

Tu es un testeur. Tu ne repares rien, tu ne modifies rien, tu ne proposes rien.
Tu testes le code TEL QUEL et tu donnes les resultats avec des chiffres.
Tu ecris TOUT dans `tests/RESULTS_BATTERY_V3.md` au fur et a mesure.

## REGLES ABSOLUES

1. **JAMAIS grep le source pour "verifier" qu'une feature existe.** Tu APPELLES le code et tu mesures la SORTIE.
2. **Chaque test cree ses propres donnees** dans un repertoire temporaire. Rien de hardcode.
3. **Verdict: PASS / FAIL / SKIP** (SKIP = dependance manquante, API key absente).
4. **Un test qui ne PEUT PAS echouer n'est pas un test.** Si ta verif passe meme sur du code vide, refais ton test.
5. **Tu ne modifies JAMAIS le code source de Muninn.**
6. **Log chaque resultat dans `tests/RESULTS_BATTERY_V3.md`** au fur et a mesure — pas a la fin.
7. **Chronometre chaque test.** Note le temps. > 60s = flag SLOW.
8. **Fais les categories dans l'ordre.** Si un import plante, note et passe a la suivante.
9. **ATTENTION META-MYCELIUM**: le vrai meta est a ~/.muninn/meta_mycelium.db (795Mo). NE PAS le polluer. Monkey-patch le chemin META_DIR dans mycelium.py vers un repertoire temporaire.
10. **Python**: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`
11. **Pour chaque test FAIL**: donne la ligne exacte du code qui pose probleme et le root cause.
12. **Les formules mathematiques sont donnees avec chaque test.** Calcule le resultat ATTENDU a la main AVANT d'appeler le code, puis compare. Si le code donne un resultat different, c'est FAIL.

## SETUP COMMUN

```python
import sys, os, json, tempfile, shutil, time, hashlib, re, struct, zlib, math
from pathlib import Path

ENGINE_DIR = Path(r"c:\Users\ludov\MUNINN-\engine\core")
sys.path.insert(0, str(ENGINE_DIR))

TEMP_REPO = Path(tempfile.mkdtemp(prefix="muninn_test_"))
MUNINN_DIR = TEMP_REPO / ".muninn"
MUNINN_DIR.mkdir()
TREE_DIR = MUNINN_DIR / "tree"
TREE_DIR.mkdir()
SESSIONS_DIR = MUNINN_DIR / "sessions"
SESSIONS_DIR.mkdir()
MEMORY_DIR = TEMP_REPO / "memory"
MEMORY_DIR.mkdir()
TREE_FILE = MEMORY_DIR / "tree.json"

TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))

# ═══════════════════════════════════════════
# MONKEY-PATCH META-MYCELIUM — CRITIQUE
# Le vrai meta est a ~/.muninn/meta_mycelium.db (795Mo).
# Si tu ne fais pas ce patch, sync_to_meta() et pull_from_meta()
# vont ECRIRE dans le vrai meta de Sky et le polluer.
# ═══════════════════════════════════════════
from mycelium import Mycelium as _MycPatch

# Sauvegarder les originaux pour restore
_orig_meta_path = _MycPatch.meta_path
_orig_meta_db_path = _MycPatch.meta_db_path

# Patcher les methodes statiques vers TEMP_META
_MycPatch.meta_path = staticmethod(lambda: TEMP_META / "meta_mycelium.json")
_MycPatch.meta_db_path = staticmethod(lambda: TEMP_META / "meta_mycelium.db")

# Verification: si ca pointe encore vers ~/.muninn/, STOP
assert "muninn_meta_" in str(_MycPatch.meta_db_path()), \
    f"META PATCH FAILED — pointe vers {_MycPatch.meta_db_path()}, ABORT"

print(f"TEMP_REPO: {TEMP_REPO}")
print(f"TEMP_META: {TEMP_META}")
print(f"META patche vers: {_MycPatch.meta_db_path()}")
```

Cleanup a la fin: `shutil.rmtree(TEMP_REPO); shutil.rmtree(TEMP_META)`

## SIGNATURES MYCELIUM — REFERENCE RAPIDE

Le cousin DOIT utiliser ces signatures exactes. Pas deviner.

```python
from mycelium import Mycelium
from mycelium_db import MyceliumDB

# Constructeur — cree le DB automatiquement si absent
m = Mycelium(repo_path=TEMP_REPO)                              # mode normal
m = Mycelium(repo_path=TEMP_REPO, federated=True, zone="test") # mode federe

# Observer des concepts (cree les connexions)
m.observe(["python", "flask", "web"])                     # liste de concepts
m.observe(["python", "flask"], arousal=0.7)               # avec arousal V6A
m.observe_text("Python Flask web API endpoint REST")      # extraction auto depuis texte

# Recuperer les connexions
m.get_related("python", top_n=5) → [(concept, weight), ...]  # paires liees
m.spread_activation(["python"], hops=2, decay=0.5, top_n=20) → [(concept, activation), ...]
m.transitive_inference("python", max_hops=3, beta=0.5, top_n=15) → [(concept, strength), ...]

# Analyse reseau
m.detect_anomalies() → {"isolated": [...], "hubs": [...], "weak_zones": [...]}
m.detect_blind_spots(top_n=20) → [(concept_a, concept_b, reason), ...]

# Creatif
m.trip(intensity=0.5, max_dreams=20) → {"created": N, "entropy_before": X, "entropy_after": Y, "dreams": [...]}
m.dream() → [{"type": "...", "text": "...", "score": N}, ...]

# Meta (PATCHE vers TEMP_META — voir setup)
m.sync_to_meta() → n_synced (int)
m.pull_from_meta(query_concepts=["python"], max_pull=200) → n_pulled (int)

# Persistence
m.save()
m.close()

# Acces direct DB (pour verifications SQL)
db = MyceliumDB(MUNINN_DIR / "mycelium.db")
db.connection_count() → int
db.fusion_count() → int
db.has_connection("python", "flask") → bool
db.neighbors("python", top_n=10) → [(concept, count), ...]
db.concept_degree("python") → int
db.all_degrees() → {concept: degree, ...}
db.upsert_fusion("machine", "learning", form="ML", strength=10)  # injection manuelle
db.get_zones_for_edge("python", "flask") → ["zone_A", "zone_B"]
db.close()

# Constantes modifiables par instance
m.FUSION_THRESHOLD = 5       # co-occur N fois → fusion
m.DECAY_HALF_LIFE = 30       # jours avant halving
m.IMMORTAL_ZONE_THRESHOLD = 3 # 3+ zones = immortel
m.DEGREE_FILTER_PERCENTILE = 0.05  # top 5% = stopwords
m.MIN_CONCEPT_LEN = 3        # ignore mots < 3 chars
```

**Ce qui marche sur DB vide (retourne [] ou {} sans crash):**
observe, get_related, spread_activation, transitive_inference,
detect_anomalies, detect_blind_spots, trip, dream, save, close

**Ce qui a besoin de donnees pour etre utile (mais crash pas si vide):**
get_related (retourne []), spread_activation (retourne []),
detect_blind_spots (retourne [] si < 10 connexions),
trip (retourne empty si < 20 connexions)

**Deps optionnelles (graceful fallback si absentes):**
- scipy/sklearn: pour detect_zones() seulement
- anthropic: pour S4 traduction seulement
- tiktoken: pour detection langue seulement

---

# ═══════════════════════════════════════════
# CATEGORIE 1 — COMPRESSION (L0-L7, L10, L11)
# ═══════════════════════════════════════════

### Ce qu'on teste: chaque couche compresse un type specifique de bruit. Le test doit verifier que CE bruit specifique est reduit ET que les faits sont intacts.

## T1.1 — L0 Tool Output Strip
```
TYPE DE TEST: ratio + preservation contenu

DONNEE: transcript JSONL 50 messages dont 15 tool_result de 200+ lignes chacun
  (simule des git diff, cat de fichiers, ls -la). Les messages user/assistant
  contiennent des faits: "accuracy=94.2%", "latency=15ms", "decided to use Redis".

APPEL: la fonction L0 strip sur le transcript

METRIQUES OBLIGATOIRES:
  □ ratio = tokens_avant / tokens_apres >= 2.0 (attendu ~x3.9 sur du vrai)
  □ Chaque tool_result de 200 lignes → max 3 lignes en sortie
  □ Texte user/assistant: comparer mot-a-mot avant/apres. 0 perte autorisee.
  □ "accuracy=94.2%" PRESENT dans la sortie
  □ "latency=15ms" PRESENT
  □ "decided to use Redis" PRESENT

PIEGE: un tool_result qui contient "D> decided to switch to PostgreSQL"
  (fait important DANS un tool output). Verifier si L0 le garde ou le perd.
  → Si perdu: documenter. C'est un comportement a noter.
```

## T1.2 — L1 Markdown Strip
```
TYPE DE TEST: pattern removal + content preservation

DONNEE: "## Architecture Decision\n**Critical**: the `API` uses a > 99.9% SLA\n- point one\n- point two"

APPEL: compress_line() ou compress_section()

METRIQUES:
  □ "##" absent → compter les occurrences, doit etre 0
  □ "**" absent → 0 occurrences
  □ "`" absent → 0 occurrences
  □ ">" (blockquote marker, pas le > de SLA) absent
  □ "Architecture" PRESENT
  □ "Critical" PRESENT
  □ "API" PRESENT
  □ "99.9%" PRESENT (nombre exact)
  □ "SLA" PRESENT
  □ len(sortie) < len(entree)
```

## T1.3 — L2 Filler Words + P24 Causal Protection
```
TYPE DE TEST: suppression selective (fillers OUT, causals IN, word boundaries OK)

DONNEES:
  A: "I basically think that actually the implementation is essentially working correctly"
  B: "The factually accurate report was actually groundbreaking"
  C: "We changed it because the old one leaked memory"
  D: "The system failed since we deployed version 3"
  E: "Therefore we decided to rollback immediately"

APPEL: compress_line() sur chaque

METRIQUES L2 (filler removal):
  □ A: "basically" ABSENT (filler)
  □ A: "actually" ABSENT (filler)
  □ A: "essentially" ABSENT (filler)
  □ A: "implementation" PRESENT (pas un filler)
  □ A: "working" PRESENT
  □ A: "correctly" PRESENT

METRIQUES WORD BOUNDARY (anti-regression — c'etait un bug corrige dans l'audit):
  □ B: "factually" PRESENT — le regex \bactually\b ne doit PAS manger "factually"
  □ Tester aussi: "eventually" (contient "actually"? non, mais tester quand meme)
  □ Tester: "COMPLETEMENT" — L5 "COMPLET→done" ne doit PAS transformer "COMPLETEMENT" en "doneMENT"

METRIQUES P24 (causal connector protection):
  □ C: "because" PRESENT (causal protege)
  □ D: "since" PRESENT (causal protege)
  □ E: "Therefore" PRESENT (causal protege)
  □ CONTRE-PREUVE: sans P24, "because" serait un candidat filler. Verifier qu'il survit grace a P24.
```

## T1.4 — L3 Phrase Compression
```
TYPE DE TEST: substitution de phrases longues → courtes

DONNEES:
  A: "in order to achieve the desired outcome"
  B: "we need to take into account all factors"
  C: "at the end of the day the result was good"
  D: "as a matter of fact the test passed"

APPEL: compress_line() sur chaque

METRIQUES:
  □ A: "in order to" → max 2 mots de remplacement (attendu: "to")
  □ B: "take into account" → max 2 mots (attendu: "consider")
  □ C: "at the end of the day" → max 2 mots (attendu: "ultimately" ou supprime)
  □ D: "as a matter of fact" → max 2 mots
  □ Pour chaque: len(sortie) / len(entree) < 0.75
  □ CONTROLE: une phrase qui ne matche aucun pattern → INCHANGÉE
```

## T1.5 — L4 Number Compression
```
TYPE DE TEST: transformation numerique correcte + preservation precision

DONNEES:
  A: "The file has 1000000 lines"           → "1M"
  B: "It weighs 2500000 bytes"              → "2.5M" ou "2500K"
  C: "Version 2.0.1 released yesterday"     → "2.0.1" INCHANGE (semver)
  D: "Accuracy is 0.9423"                   → "0.9423" INCHANGE (precision)
  E: "From 1500ms down to 150ms"            → "1500" ET "150" preserves
  F: "Commit a1b2c3d fixes issue #4287"     → "a1b2c3d" ET "#4287" INCHANGES (hash + issue)

APPEL: compress_line() sur chaque

METRIQUES:
  □ A: contient "1M", ne contient plus "1000000"
  □ B: contient "2.5M" ou "2500K"
  □ C: "2.0.1" EXACTEMENT present (pas "2M" ni "2.0" ni rien d'autre)
  □ D: "0.9423" EXACTEMENT present
  □ E: "1500" ET "150" tous deux presents
  □ F: "a1b2c3d" ET "4287" presents
```

## T1.6 — L5 Universal Rules
```
TYPE DE TEST: substitution regle + word boundary

DONNEES:
  A: "Status: COMPLETED"                    → doit contenir "done"
  B: "Le processus est EN COURS"            → doit contenir "wip"
  C: "Le build a ECHOUE hier"               → doit contenir "fail"
  D: "PARTIELLEMENT termine"                → NE DOIT PAS devenir "doneMENT" ou autre
  E: "COMPLETEMENT fini"                    → NE DOIT PAS devenir "doneMENT"

APPEL: compress_line()

METRIQUES:
  □ A: "done" PRESENT, "COMPLETED" ABSENT
  □ B: "wip" PRESENT, "EN COURS" ABSENT
  □ C: "fail" PRESENT, "ECHOUE" ABSENT
  □ D: "PARTIELLEMENT" PRESENT OU equivalent, PAS de "done" partial
  □ E: "COMPLETEMENT" PRESENT OU equivalent, PAS de "doneMENT"
     (Ce bug "doneMENT" etait reel — corrige dans l'audit avec \b word boundary)
```

## T1.7 — L6 Mycelium Fusion Strip
```
TYPE DE TEST: fusion conditionnelle (avec/sans mycelium = controle)

SETUP: creer Mycelium(TEMP_REPO).
  Injecter une fusion: ("machine", "learning") avec strength >= 5
  (FUSION_THRESHOLD = 5, mycelium.py ligne 51)

DONNEE: "the machine learning model is ready"

APPEL A: compress_line() AVEC ce mycelium
APPEL B: compress_line() SANS mycelium (controle)

METRIQUES:
  □ AVEC: un des deux mots est strip ou fusionne. len(sortie_A) < len(sortie_B)
  □ SANS: "machine learning" INTACT
  □ "model" PRESENT dans les 2 cas
  □ "ready" PRESENT dans les 2 cas
  □ Le controle SANS mycelium est OBLIGATOIRE sinon le test prouve rien
```

## T1.8 — L7 Key-Value Extraction
```
TYPE DE TEST: detection pattern + preservation nombres exacts

DONNEE: "the accuracy is 94.2% and the loss decreased to 0.031 after 50 epochs"

APPEL: compress_line()

METRIQUES:
  □ "94.2%" present EXACTEMENT (pas 94% ni 94.20%)
  □ "0.031" present EXACTEMENT
  □ "50" present
  □ Format compact: la sortie contient au moins un "=" ou ":" entre un mot et un nombre
  □ len(sortie) / len(entree) < 0.7
```

## T1.9 — L10 Cue Distillation (Bartlett 1932 + Rao & Ballard 1999)
```
TYPE DE TEST: connaissance generique → cue minimal, faits specifiques → preserves

La logique L10 (lignes 1499-1539):
  - _novelty_score(line): compte patterns novel (dates, commits, x\d+, $, %) minus patterns generic
  - seuil: novelty < 0.35 → compresse en cue
  - cue_length_ratio = 0.7 (le cue doit etre < 70% de la ligne originale)
  - _generate_cue(line): extrait premier nom + premier verbe + premier nombre/entite, max 8 mots

DONNEE GENERIQUE (10 lignes expliquant gradient descent — novelty_score < 0.35):
  "Gradient descent is an optimization algorithm used in machine learning.
   It works by computing the gradient of the loss function with respect to parameters.
   The learning rate determines the step size at each iteration.
   When the gradient reaches zero, we have found a local minimum.
   Stochastic gradient descent uses random mini-batches for efficiency.
   Batch normalization helps stabilize the training process.
   Momentum adds a fraction of the previous update to the current one.
   Weight decay adds L2 regularization to prevent overfitting.
   The Adam optimizer combines momentum with adaptive learning rates.
   Convergence depends on the loss landscape smoothness."

DONNEE SPECIFIQUE (3 lignes — novelty_score >= 0.35 car chiffres/dates):
  "F> our learning rate is 0.003 after tuning on 2026-03-10"
  "D> decided to switch from Adam to SGD — saved $47/day on GPU costs"
  "F> model accuracy jumped from x2.1 to x4.5 after L10 changes (commit a3f7b2d)"

APPEL: _cue_distill(texte_complet)

METRIQUES:
  □ Les 10 lignes generiques → reduites (total lignes sortie < 10 pour cette partie)
  □ Chaque cue est < 70% de la ligne originale (cue_length_ratio=0.7, ligne 1528)
  □ Le mot "gradient" apparait encore (comme cue de rappel)
  □ L'explication COMPLETE n'est PLUS la (pas 10 lignes de gradient descent)
  □ "0.003" PRESENT (fait specifique, novelty >= 0.35)
  □ "2026-03-10" PRESENT (date specifique)
  □ "Adam to SGD" PRESENT (decision specifique)
  □ "$47/day" PRESENT (cout specifique)
  □ "a3f7b2d" PRESENT (commit hash)
  □ "x4.5" PRESENT (metrique specifique)
  □ Ratio total: lignes_sortie / lignes_entree < 0.7
```

## T1.10 — L11 Rule Extraction (Kolmogorov 1965)
```
TYPE DE TEST: factorisation de patterns repetitifs

La logique L11 (lignes 1547-1611):
  - Detecte des lignes pipe-separated avec key=value
  - Condition: len(kvs) >= 3 et >= 60% des parts sont k=v
  - Extrait le suffixe unitaire commun (%, min, ms, s)
  - Factorise en 1 ligne compacte

DONNEE A (pattern clair — doit factoriser):
  "module_api: status=done, tests=42, cov=89%"
  "module_auth: status=wip, tests=18, cov=67%"
  "module_db: status=done, tests=31, cov=91%"
  "module_cache: status=fail, tests=5, cov=23%"
  "module_queue: status=done, tests=27, cov=84%"
  "module_log: status=wip, tests=12, cov=55%"

DONNEE B (PAS de pattern — ne doit PAS factoriser):
  "The API handles REST requests"
  "Users authenticate via JWT tokens"
  "Database uses connection pooling"

APPEL: _extract_rules(texte_A + texte_B)

METRIQUES:
  □ Donnee A: nombre de lignes en sortie < 6 (le pattern est factorise)
  □ TOUTES les valeurs preservees: 42, 18, 31, 5, 27, 12, 89, 67, 91, 23, 84, 55
  □ Tous les noms preserves: api, auth, db, cache, queue, log
  □ Donnee B: les 3 lignes sont INTACTES (pas de pattern → pas de factorisation)
  □ Donnee B: "REST" PRESENT, "JWT" PRESENT, "pooling" PRESENT
```

## T1.11 — L9 LLM Compress (OPTIONNEL — PAYANT)
```
PREREQ: `import anthropic` + ANTHROPIC_API_KEY dans env. Si absent → SKIP.
DONNEE: texte de 500+ tokens technique avec 5 faits numeriques.
APPEL: _llm_compress() avec R1 chunking (section-chunked pour textes > 8K)
METRIQUES:
  □ ratio tokens_apres / tokens_avant < 0.5
  □ Les 5 faits numeriques TOUS presents en sortie
  □ Temps < 30s
  □ PIEGE: texte DEJA compresse par L0-L7 → L9 devrait ajouter peu (x130 vs x143 regex seul)
VERDICT: SKIP si pas de cle API. NOTER le cout $.
```

---

# ═══════════════════════════════════════════
# CATEGORIE 2 — FILTRES TRANSCRIPT
# ═══════════════════════════════════════════

## T2.1 — P17 Code Block Compression
```
DONNEE: "Voici le fix:\n```python\ndef calculate_score(branch):\n    recall = compute_recall(branch)\n    return recall * 0.8 + 0.2\n```\nCa marche maintenant."

APPEL: compression avec P17

METRIQUES:
  □ Le bloc ```python...``` (3 lignes de code) → max 1 ligne en sortie
  □ "Voici le fix" PRESENT
  □ "Ca marche maintenant" PRESENT
  □ Le nombre de lignes entre ``` et ``` est reduit a 1
```

## T2.2 — P25 Priority Survival + KIComp Density
```
TYPE DE TEST: les lignes taggees survivent les coupes budget

La logique KIComp (lignes 632-752):
  - _line_density: D>=0.9, B>=0.8, F>=0.8, E>=0.7, A>=0.7, untagged base=0.1-0.3
  - +0.1 per digit, max +0.3 pour nombres
  - +0.1 per kv pattern, max +0.2
  - Drop lowest-density lines until budget respecte

DONNEE: 25 lignes:
  3x "D> decided to use X" (densite 0.9)
  2x "B> bug: Y crashes" (densite 0.8)
  2x "F> metric=42%" (densite 0.8)
  18x "The implementation continues to progress nicely" (densite ~0.1, pas de chiffre, pas de tag)

BUDGET: forcer a 12 lignes max

METRIQUES:
  □ Les 3 lignes D> TOUTES presentes (densite 0.9 = top priority)
  □ Les 2 lignes B> TOUTES presentes (densite 0.8)
  □ Les 2 lignes F> TOUTES presentes (densite 0.8)
  □ Total lignes <= 12
  □ Ce sont les 18 non-taggees qui sautent en priorite
  □ PIEGE: mettre une ligne non-taggee EN PREMIER dans le texte → elle doit quand meme sauter
  □ PIEGE: une ligne non-taggee avec des chiffres "processed 1.2M rows in 3.5s"
    → densite plus haute (~0.4-0.5) → survit plus longtemps que les pures narratives
```

## T2.3 — P26 Line Dedup
```
DONNEE:
  L1: "F> accuracy=94.2% on test set"
  L2: "F> accuracy=94.2% on test set"            (doublon exact)
  L3: "F> accuracy=94.2% on the test set"         (quasi — "the" en plus)
  L4: "F> latency=15ms on production"              (unique)
  L5: "D> decided to use Redis"                    (unique)

APPEL: dedup (P26)

METRIQUES:
  □ L1 et L2: un seul survit (doublon exact elimine)
  □ L3: elimine OU fusionne avec L1 (fuzzy match — 1 mot de difference)
  □ L4: PRESENT (unique)
  □ L5: PRESENT (unique)
  □ Total lignes en sortie: 3 (1 accuracy + 1 latency + 1 redis)
```

## T2.4 — P27 Last Read Only
```
DONNEE: transcript JSONL:
  Msg 5:  tool_result contenant "CONFIG_V1 = True" (1ere lecture config.py)
  Msg 15: tool_result contenant "CONFIG_V2 = True" (2eme lecture)
  Msg 25: tool_result contenant "CONFIG_V3 = True" (3eme lecture)
  Les 3 lisent le meme fichier "config.py".

APPEL: compress_transcript

METRIQUES:
  □ "CONFIG_V3" PRESENT (derniere version)
  □ "CONFIG_V1" ABSENT
  □ "CONFIG_V2" ABSENT
  □ Le mot "config.py" apparait au plus 1 fois dans la section pertinente
```

## T2.5 — P28 Claude Verbal Tics
```
DONNEE:
  "Let me analyze this for you. The API has 3 endpoints.
   I'll take a look at the code. Function foo() returns 42.
   Here's what I found: the bug is in line 73.
   I'd be happy to help with that. The fix requires changing auth.py."

APPEL: compress

METRIQUES (tics supprimes):
  □ "Let me analyze this for you" ABSENT
  □ "I'll take a look at the code" ABSENT
  □ "Here's what I found:" ABSENT
  □ "I'd be happy to help with that" ABSENT

METRIQUES (faits preserves):
  □ "3 endpoints" PRESENT
  □ "foo()" PRESENT
  □ "42" PRESENT
  □ "line 73" PRESENT
  □ "auth.py" PRESENT
```

## T2.6 — P38 Multi-Format Detection
```
FICHIERS:
  A: test.jsonl — 5 lignes: {"role":"user","content":"hello"}\n{"role":"assistant"...
  B: test.json  — {"messages":[{"role":"user"}]}
  C: test.md    — "# Session\n## Topic\nContent"
  D: vide.txt   — 0 octets

APPEL: detection format sur chaque

METRIQUES:
  □ A → JSONL
  □ B → JSON
  □ C → MD/Markdown
  □ D → pas de crash (retour default ou erreur propre)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 3 — TAGGING (P14, C7)
# ═══════════════════════════════════════════

## T3.1 — P14 Memory Type Tags
```
TYPE DE TEST: classification de lignes par patterns

La logique P14 (lignes 1104-1143, lignes 1133-1143 pour les patterns):
  D>: decid|chose|pivot|switch|adopt
  B>: bug|fix|patch|crash|broke|repair
  F>: x\d+|ratio|benchmark|%|\d+\.\d+[sx]
  E>: error|exception|traceback|failed|TypeError
  A>: architect|design|pattern|refactor

DONNEES:
  A: "We decided to use PostgreSQL instead of MySQL"           → D>
  B: "Bug: the auth middleware crashes on empty tokens"         → B>
  C: "The API handles 10K requests per second at p99=15ms"     → F>
  D: "Error: connection timeout after 30s on host db-prod-3"   → E>
  E: "The system uses a microservice architecture with 12 svc" → A>
  F: "The meeting went well today"                              → aucun tag (ou F> si "meeting" matche)
  G: ""                                                         → pas de crash
  H: "decided to fix the architecture bug"                      → quel tag gagne? D? B? A? documenter la priorite

METRIQUES:
  □ A commence par "D>"
  □ B commence par "B>"
  □ C commence par "F>" (contient "10K" et "p99=15ms" → patterns F>)
  □ D commence par "E>"
  □ E commence par "A>"
  □ F: pas de crash, tag acceptable ou absent
  □ G: pas de crash
  □ H: documenter quel tag est applique quand plusieurs matchent — c'est un test de PRIORITE
```

## T3.2 — C7 Contradiction Resolution (Stanford NLP 2008)
```
TYPE DE TEST: last-writer-wins sur meme skeleton numerique

La logique C7 (lignes 1269-1340):
  skeleton = line.lower() avec \d+ remplace par _NUM_
  Si 2 lignes ont le meme skeleton mais des nombres differents → garder la derniere
  Guards: pas les listes numerotees (1. X), pas les bullets, pas les lignes > 100 chars

DONNEE:
  L3:  "accuracy=92% on val set"
  L7:  "latency=50ms at peak"
  L18: "accuracy=97% on val set after fine-tuning"
  L22: "throughput=1200 req/s"
  L25: "1. Install Python"                    (liste numerotee — NE PAS toucher)
  L26: "2. Run tests"                         (liste numerotee — NE PAS toucher)

APPEL: resolve_contradictions()

METRIQUES:
  □ "accuracy=92%" ABSENT (L3 supprimee — meme skeleton que L18)
  □ "accuracy=97%" PRESENT (L18 survit — derniere)
  □ "latency=50ms" PRESENT (pas de contradiction)
  □ "throughput=1200" PRESENT (pas de contradiction)
  □ "1. Install Python" PRESENT (guard: liste numerotee protegee)
  □ "2. Run tests" PRESENT (guard: liste numerotee protegee)
  □ Nombre de lignes supprimees = exactement 1
```

---

# ═══════════════════════════════════════════
# CATEGORIE 4 — MYCELIUM CORE
# ═══════════════════════════════════════════

## T4.1 — S1 SQLite Storage + Observe
```
TYPE DE TEST: stockage normalise + co-occurrence correcte

SETUP: m = Mycelium(TEMP_REPO)
APPEL: observer 3 paragraphes:
  P1: "Python Flask web API endpoint REST JSON"
  P2: "Python Django web framework template ORM"
  P3: "Rust memory safety ownership borrow checker"

METRIQUES STRUCTURE:
  □ .muninn/mycelium.db existe, taille > 0
  □ SQL: SELECT COUNT(*) FROM concepts → > 0
  □ SQL: SELECT COUNT(*) FROM edges → > 0
  □ concept_id pour "python" est un INTEGER (pas une string)

METRIQUES CO-OCCURRENCE:
  □ Edge (python, flask) existe avec count >= 1 (P1)
  □ Edge (python, web) existe avec count >= 2 (P1 + P2)
  □ Edge (python, django) existe avec count >= 1 (P2)
  □ Edge (python, rust) N'EXISTE PAS (jamais dans le meme paragraphe)
  □ Edge (rust, memory) existe avec count >= 1 (P3)
  □ Edge (flask, django) N'EXISTE PAS (jamais ensemble)

METRIQUES SEMANTIQUE:
  □ get_related("python") contient "flask" ET "django" ET "web"
  □ get_related("rust") contient "memory" ET "safety"
  □ get_related("python") ne contient PAS "rust"
```

## T4.2 — S2 Epoch-Days
```
TYPE DE TEST: conversion aller-retour exacte

La logique S2 (mycelium_db.py ~ligne 20-52):
  epoch_days = (date - 2020-01-01).days
  Donc 2020-01-01 = jour 0

CALCULS A LA MAIN:
  2020-01-01 → 0
  2020-01-02 → 1
  2020-12-31 → 365 (2020 est bissextile)
  2024-02-29 → 365+365+366+365 + 31+29 = 1521 (bissextile)
  2026-03-12 → compter: 2020(366)+2021(365)+2022(365)+2023(365)+2024(366)+2025(365) + jan(31)+feb(28)+12-1
             = 366+365+365+365+366+365+31+28+11 = 2262

APPEL: fonctions epoch_days() et from_epoch_days()

METRIQUES:
  □ "2020-01-01" → 0
  □ "2020-01-02" → 1
  □ "2024-02-29" → 1521 (ou la bonne valeur — CALCULER exactement)
  □ "2026-03-12" → 2262 (ou la bonne valeur)
  □ Aller-retour: epoch_days("2024-02-29") → from_epoch_days(result) → "2024-02-29"
  □ Pas de crash sur aucune date
```

## T4.3 — S3 Degree Filter (top 5% stopwords)
```
TYPE DE TEST: les concepts trop connectes sont bloques de la fusion

PARAMETRES: DEGREE_FILTER_PERCENTILE = 0.05 (mycelium.py ligne 58)

SETUP: observer 100 paragraphes. Dans CHAQUE paragraphe:
  - "data" apparait (sera dans le top 5%)
  - 3 concepts random differents a chaque fois
  Puis observer 10 paragraphes ou "flask" et "python" co-occurrent.

METRIQUES:
  □ degre("data") > degre("flask") (beaucoup plus connecte)
  □ "data" est dans le top 5% par degre
  □ Tenter de forcer une fusion "data"+"analysis" (count artificiellement eleve)
    → la fusion est BLOQUEE (S3 protege)
  □ "flask"+"python" PEUT fusionner si count >= 5 (pas dans top 5%)
```

## T4.4 — Spreading Activation (Collins & Loftus 1975)
```
TYPE DE TEST: propagation semantique avec decay mesurable

La logique (mycelium.py lignes 958-1048):
  activation[seed] = 1.0
  hop 1: spread = activation[node] * weight * decay^1
  hop 2: spread = activation[node] * weight * decay^2
  Hub penalty: weight *= 0.1 if hub
  Min-max normalization finale

PARAMETRES: hops=2, decay=0.5, top_n=50 (muninn.py ligne 2261)

SETUP: mycelium avec chaine lineaire:
  python ↔ flask (count=20)
  flask ↔ jinja (count=15)
  jinja ↔ templates (count=10)
  templates ↔ html (count=5)
  + concept isole: quantum ↔ physics (count=20)

APPEL: m.spread_activation(["python"], hops=2, decay=0.5, top_n=50)

METRIQUES:
  □ "flask" active (hop 1), score > 0
  □ "jinja" active (hop 2), score > 0
  □ score("flask") > score("jinja") (decay par hop)
  □ "templates" PAS active (hop 3, hops=2)
  □ "html" PAS active (hop 4)
  □ "quantum" PAS active (deconnecte)
  □ "physics" PAS active (deconnecte)
  □ len(resultats) <= 50

METRIQUES QUANTITATIVES:
  Avec decay=0.5:
  □ score("flask") ≈ 2 * score("jinja") (ratio ~decay, tolerance +-30%)
     (pas exact car normalisation et poids variables)
  □ score("python") est le seed = plus haut score (ou absent car seed)
```

## T4.5 — A3 Sigmoid Post-Filter
```
TYPE DE TEST: les scores faibles sont ecrases, les forts preserves

La logique A3 (mycelium.py ligne 67, 1034-1035):
  sigmoid(x) = 1 / (1 + exp(-k * (x - x0)))
  k = 10 (_sigmoid_k, ligne 67)
  x0 = 0.5 (point d'inflexion)

CALCULS A LA MAIN:
  sigmoid(0.1) = 1/(1+exp(-10*(0.1-0.5))) = 1/(1+exp(4)) = 1/55.6 ≈ 0.018
  sigmoid(0.3) = 1/(1+exp(-10*(0.3-0.5))) = 1/(1+exp(2)) = 1/8.39 ≈ 0.119
  sigmoid(0.5) = 1/(1+exp(0)) = 0.5 (point d'inflexion)
  sigmoid(0.7) = 1/(1+exp(-10*(0.7-0.5))) = 1/(1+exp(-2)) = 1/1.135 ≈ 0.881
  sigmoid(0.9) = 1/(1+exp(-10*(0.9-0.5))) = 1/(1+exp(-4)) = 1/1.018 ≈ 0.982

METRIQUES:
  □ Score 0.1 → sigmoid ≈ 0.018 (ecrase, tolerance +-0.01)
  □ Score 0.3 → sigmoid ≈ 0.119
  □ Score 0.5 → sigmoid ≈ 0.500
  □ Score 0.7 → sigmoid ≈ 0.881
  □ Score 0.9 → sigmoid ≈ 0.982
  □ L'ORDRE est preserve: si A > B avant sigmoid, A > B apres
  □ PIEGE: verifier que le sigmoid est applique APRES le spreading, pas avant
```

## T4.6 — V3A Transitive Inference (Wynne 1995)
```
TYPE DE TEST: chaine ordonnee avec decay multiplicatif

La logique (mycelium.py lignes 1050-1111):
  V(A→C) = strength(A,B) * strength(B,C) * beta^hops
  beta = 0.5, max_hops = 3, top_n = 20
  Normalise: edge_weight / max_weight
  BFS avec relaxation (garder le chemin le plus fort)

SETUP: mycelium avec chaine:
  A ↔ B (count=20, norm_weight=1.0)
  B ↔ C (count=15, norm_weight=0.75)
  C ↔ D (count=10, norm_weight=0.50)
  D ↔ E (count=5, norm_weight=0.25)

APPEL: m.transitive_inference("A", max_hops=3, beta=0.5, top_n=20)

CALCULS ATTENDUS:
  B: 1.0 * 0.5^1 = 0.500
  C: 1.0 * 0.75 * 0.5^2 = 0.188
  D: 1.0 * 0.75 * 0.50 * 0.5^3 = 0.047

METRIQUES:
  □ B trouve, score ≈ 0.50 (tolerance +-30% car normalisation)
  □ C trouve, score ≈ 0.19
  □ D trouve, score ≈ 0.05
  □ score(B) > score(C) > score(D) (decroissant strict)
  □ E PAS trouve (hop 4, max_hops=3)
  □ Avec max_hops=1: seul B trouve
  □ len(resultats) <= 20
```

## T4.7 — NCD Similarity (Cilibrasi & Vitanyi 2005)
```
TYPE DE TEST: distance semantique par compression

Formule: NCD(a,b) = (C(ab) - min(C(a),C(b))) / max(C(a),C(b))
  C(x) = len(zlib.compress(x.encode()))

DONNEES:
  A = "python flask api web server endpoint json rest"
  B = "python flask web api endpoint json rest server"
  C = "quantum physics electron photon wave particle duality"
  D = A (copie exacte)
  E = "" (vide)

CALCULS A LA MAIN (approximatifs, zlib compresse):
  NCD(A,B) devrait etre < 0.3 (presque identique, mots permutes)
  NCD(A,C) devrait etre > 0.6 (domaines differents)
  NCD(A,D) devrait etre ≈ 0.0 (identique)

METRIQUES:
  □ NCD(A,B) < 0.4 (seuil merge, ligne 1920)
  □ NCD(A,C) > 0.6 (seuil dedup, ligne 2658)
  □ NCD(A,D) < 0.1 (identique)
  □ 0.0 <= NCD <= 1.0 pour tous les cas
  □ NCD(E,E) → pas de crash (division par zero potentielle)
  □ Seuils du code: < 0.4 = merge (I2), < 0.6 = dedup (P19/sleep), > 0.6 = different
```

## T4.8 — B3 Blind Spot Detection (Burt 1992)
```
TYPE DE TEST: detection de trous structurels

La logique (mycelium.py lignes 1485-1613):
  Heuristique transitive: A-B fort, B-C fort, A-C absent → trou
  Score = degree_a * degree_c
  min_degree = 5

SETUP: mycelium ou:
  A ↔ B (count=20, degree(A)=10, degree(B)=15)
  B ↔ C (count=20, degree(C)=8)
  A ↔ C ABSENT (trou structurel)
  D ↔ E (count=20, degree(D)=3, degree(E)=2) — degree trop faible pour detection

APPEL: m.detect_blind_spots(top_n=20)

METRIQUES:
  □ Paire (A, C) identifiee comme trou structurel
  □ Score = degree(A) * degree(C) = 10 * 8 = 80
  □ Paire (A, B) PAS un trou (deja connectes)
  □ Paire (D, E) ignoree car degree < 5
  □ Resultat a au moins 1 entree
```

## T4.9 — B2 Graph Anomaly Detection
```
TYPE DE TEST: detection hubs/isolates/weak zones

La logique (mycelium.py lignes 1419-1481):
  Isolated: degree <= 1
  Hubs: degree > mean + 2*std
  Weak zones: AVG(count) < 2

SETUP: mycelium avec:
  - "isolated_concept": 0 connexions (injecte comme concept sans edge)
  - "hub_concept": 50+ connexions (connecte a 50 concepts differents)
  - "normal_concept": 5 connexions

METRIQUES:
  □ "isolated" dans anomalies["isolated"] (ou equivalent)
  □ "hub_concept" dans anomalies["hubs"]
  □ "normal_concept" PAS dans les anomalies
  □ Les hubs ont degree > mean + 2*std (verifier le calcul)
```

## T4.10 — P20 Federated Zones + Immortalite
```
TYPE DE TEST: tagging par zone + immortalite (3+ zones)

PARAMETRES: IMMORTAL_ZONE_THRESHOLD = 3 (mycelium.py ligne 55)

SETUP:
  observer("python flask web", zone="repo_A")
  observer("python django web", zone="repo_B")
  observer("python fastapi web", zone="repo_C")

METRIQUES:
  □ Edge "python"↔"web" a des zones: repo_A, repo_B, repo_C (3 zones)
  □ "python"↔"web" est IMMORTEL (3 >= IMMORTAL_ZONE_THRESHOLD)
  □ Appliquer decay → "python"↔"web" ne decay PAS (immortel)
  □ Edge "flask"↔"web" est dans 1 zone (repo_A) → PAS immortel → decay normal
```

## T4.11 — P20b Meta-Mycelium Sync + Pull
```
TYPE DE TEST: round-trip cross-repo

ATTENTION: monkey-patch vers TEMP_META, pas ~/.muninn/

SETUP:
  m1 = Mycelium(TEMP_REPO) avec 50 connexions dont (python, flask, count=10)
  Appel: m1.sync_to_meta()

  Creer TEMP_REPO_2. m2 = Mycelium(TEMP_REPO_2) (vide)
  Appel: m2.pull_from_meta(query_concepts=["python"], max_pull=200)

METRIQUES:
  □ sync retourne n_synced >= 50
  □ Meta DB dans TEMP_META existe, taille > 0
  □ pull retourne n_pulled > 0
  □ m2.get_related("python") contient "flask"
  □ n_pulled <= 200 (max_pull respecte)
  □ Les connexions tirees ont les bons counts (pas reset a 0)
```

## T4.12 — P41 Self-Referential Growth
```
TYPE DE TEST: les fusions deviennent des concepts observables

SETUP: mycelium avec fusion ("machine", "learning") → "ML"
APPEL: observer les fusions comme concepts de second ordre

METRIQUES:
  □ "ML" ou la fusion apparait comme concept dans la DB
  □ Timeout 10s — si recursion infinie, FAIL + documenter
  □ La connexion de second ordre existe entre la fusion et d'autres concepts
```

---

# ═══════════════════════════════════════════
# CATEGORIE 5 — TREE & BRANCHES
# ═══════════════════════════════════════════

## T5.1 — Load/Save arbre
```
SETUP: ecrire tree.json:
{
  "root": {"file":"root.mn","tags":["project"],"temperature":1.0,
           "last_access":"2026-03-12","access_count":10,
           "usefulness":0.8,"valence":0.0,"arousal":0.0},
  "branch_api": {"file":"branch_api.mn","tags":["api","rest","flask"],
                 "temperature":0.8,"last_access":"2026-03-11","access_count":5,
                 "usefulness":0.7,"valence":0.1,"arousal":0.2},
  "branch_db": {"file":"branch_db.mn","tags":["database","sql"],
                "temperature":0.3,"last_access":"2026-02-15","access_count":2,
                "usefulness":0.3,"valence":-0.2,"arousal":0.5}
}
+ ecrire root.mn, branch_api.mn, branch_db.mn dans TREE_DIR

APPEL: load_tree() + save_tree() + reload

METRIQUES:
  □ 3 noeuds charges
  □ root.temperature == 1.0
  □ branch_api.tags == ["api","rest","flask"]
  □ Round-trip: save puis reload → donnees identiques (comparer JSON)
```

## T5.2 — P34 Integrity Check
```
SETUP: 2 branches. Hash CORRECT pour branch_api. Hash FAUX "0000dead" pour branch_db.

APPEL: boot ou load avec integrity check (lignes 586-592)

METRIQUES:
  □ branch_api chargee (hash OK)
  □ branch_db REJETÉE ou SIGNALÉE (hash mismatch)
  □ Pas de crash
  □ Log indiquant le probleme
```

## T5.3 — R4 Prune complet
```
TYPE DE TEST: classification HOT/COLD/DEAD + V9B protection

PARAMETRES:
  HOT: recall >= 0.4 (ligne 3542)
  COLD: recall < 0.15 (ligne 3553)
  DEAD: recall < 0.05 (ligne 3545)

SETUP: arbre avec 4 branches + mycelium:
  "hot_branch": last_access=hier, access_count=20, usefulness=0.8
    → h = 7 * 2^10_cap * 0.8^0.5 ≈ grande valeur → recall >> 0.4
  "cold_branch": last_access=20j ago, access_count=3, usefulness=0.5
    → calculer recall exact, doit etre entre 0.05 et 0.4
  "dead_branch": last_access=200j ago, access_count=1, usefulness=0.1
    → recall << 0.05
  "sole_carrier": meme profil que dead_branch MAIS
    tag unique "quantum_teleportation_xyz" que personne d'autre n'a

APPEL: prune(dry_run=False)

METRIQUES:
  □ hot_branch: INCHANGÉE, .mn present
  □ cold_branch: presente, potentiellement re-compressée
  □ dead_branch: SUPPRIMÉE — .mn absent, noeud absent de tree.json
  □ sole_carrier (V9B): PAS supprimee malgre recall < 0.05
    Console contient "PROTECTED (sole carrier)"
    .mn encore present
```

## T5.4 — V9A+ Fact Regeneration (Shomrat & Levin 2013)
```
TYPE DE TEST: extraction faits tagges + injection dans survivant

La logique V9A+ (lignes 3605-3747):
  1. Lire .mn de la morte, extraire lignes ^[DBFEA]>
  2. Trouver survivant par: mycelium proximity → tag overlap → recency
  3. Injecter dans section "## REGEN: {dead_name} ({date})"
  4. Si > 200 lignes: re-appliquer L10+L11
  5. Diffuser tags morts vers survivants via get_related

SETUP:
  "dying_branch": DEAD (recall=0.01), .mn:
    "D> decided to use Redis for session caching"
    "F> latency=200ms before, latency=15ms after Redis"
    "B> bug: Redis connection pool exhausted at 10K concurrent"
    "some untagged explanation about how caching works in general"

  "survivor_branch": HOT (recall=0.8)
    tags: ["redis", "api", "performance"]
    .mn: 10 lignes de contenu existant

  Mycelium: "redis" ↔ "caching" (count=10)

APPEL: prune()

METRIQUES EXTRACTION:
  □ 3 faits tagges extraits de dying_branch (D>, F>, B>)
  □ La ligne non-taggee n'est PAS extraite

METRIQUES INJECTION:
  □ survivor.mn contient "## REGEN: dying_branch (2026-03-12)"
  □ "decided to use Redis for session caching" PRESENT dans survivor.mn
  □ "latency=200ms" et "latency=15ms" PRESENTS
  □ "Redis connection pool exhausted at 10K" PRESENT
  □ "how caching works in general" ABSENT (non-taggee, perdue)

METRIQUES DEDUP:
  □ Si un fait est DEJA dans survivor.mn, il n'est PAS reinjecte (doublon)

METRIQUES TAG DIFFUSION:
  □ "caching" (tag de dying) est ajoute aux tags de survivor dans tree.json

METRIQUES BUDGET:
  □ Si survivor depasse 200 lignes apres injection: L10+L11 appliques (ligne 3712)
    → tester avec un survivor de 195 lignes + 10 faits injectes = 205 > 200

CONSOLE:
  □ "V9A+ REGEN: 3 facts + N tags diffused to survivors"
```

## T5.5 — V9A+ sans survivant
```
SETUP: arbre avec 1 seule branche DEAD, pas de survivant.
APPEL: prune()
METRIQUES:
  □ Pas de crash
  □ Branche supprimee
  □ Console: PAS de "V9A+ REGEN" (rien a injecter)
```

## T5.6 — V9A+ selection du meilleur survivant (3 strategies)
```
TYPE DE TEST: verifier les 3 strategies de fallback dans l'ordre

SETUP A (strategie mycelium):
  dying: tags=["redis","caching"]
  survivor_1: tags=["database","sql"] — PAS de lien mycelium avec redis
  survivor_2: tags=["cache","performance"] — mycelium: "redis"↔"cache" (count=10)
  → V9A+ doit choisir survivor_2 (mycelium proximity)

SETUP B (strategie tag overlap):
  dying: tags=["redis","caching","memory"]
  survivor_1: tags=["redis","memory","api"] — 2 tags en commun
  survivor_2: tags=["docker","k8s"] — 0 tags en commun
  Mycelium: aucun lien pertinent
  → V9A+ doit choisir survivor_1 (overlap=2 > overlap=0)

SETUP C (strategie recency):
  dying: tags=["alpha"]
  survivor_1: last_access="2026-01-01"
  survivor_2: last_access="2026-03-12"
  Mycelium: aucun lien. Tags: aucun overlap.
  → V9A+ doit choisir survivor_2 (plus recent)

METRIQUES: pour chaque setup, verifier que le BON survivant est choisi.
```

## T5.7 — B7 Live Injection
```
APPEL: inject("SQLite is faster than JSON for 100K+ entries", repo_path=TEMP_REPO)

METRIQUES:
  □ tree.json a un nouveau noeud
  □ Le .mn contient "SQLite" et "100K"
  □ Temperature du nouveau noeud = 0.1 (new_branch_temperature, ligne 1999)
  □ Le mycelium a des connexions pour "sqlite" et "json"
  □ Les tags du noeud incluent des concepts pertinents
```

## T5.8 — P40 Bootstrap
```
SETUP: 3 fichiers Python dans TEMP_REPO:
  api.py (50 lignes, classe APIServer)
  db.py (40 lignes, classe Database)
  auth.py (30 lignes, fonction authenticate)

APPEL: bootstrap(TEMP_REPO)

METRIQUES:
  □ tree.json existe avec root + branches
  □ root.mn existe et non-vide
  □ mycelium.db a edges > 0
  □ "APIServer" ou "api" present quelque part dans les branches
  □ Temps < 30s
```

## T5.9 — P16 Session Log
```
SETUP: root.mn avec section "R:" contenant 5 entrees:
  "R: s1 api design | s2 database | s3 testing | s4 deploy | s5 monitoring"

APPEL: ajouter session "s6 security audit"

METRIQUES:
  □ root.mn contient "s6 security audit"
  □ root.mn contient exactement 5 entrees dans R: (s2,s3,s4,s5,s6)
  □ "s1 api design" ABSENT (ejecte — max 5)
```

## T5.10 — P19 Branch Dedup
```
SETUP: 3 branches:
  branch_a.mn: "python flask api rest endpoint json web server"
  branch_b.mn: "python flask api rest endpoint json web server" (copie)
  branch_c.mn: "quantum physics electron photon duality"

APPEL: detection dedup (seuil NCD = 0.6, ligne 2658)

METRIQUES:
  □ NCD(a,b) < 0.1 (identiques)
  □ branch_a et branch_b identifiees comme doublons
  □ branch_c PAS identifiee comme doublon avec a ou b
  □ Apres dedup: 2 branches restent (a ou b + c), pas 3
```

---

Fin de la partie 1/3.
La partie 2 couvre: categories 6-10 (Boot, Formules, Pruning avance, Emotional, Scoring avance).
La partie 3 couvre: categories 11-15 (Pipeline, Edge cases, Integration, Virtual branches, Bio-vecteurs specifiques).
