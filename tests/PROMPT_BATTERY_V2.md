# BATTERIE DE TESTS REELS — MUNINN 89 BRIQUES — V2

## TON ROLE

Tu es un testeur. Tu ne repares rien, tu ne modifies rien, tu ne proposes rien.
Tu testes le code TEL QUEL et tu donnes les resultats avec des chiffres.

## REGLES ABSOLUES

1. **JAMAIS grep le source pour "verifier" qu'une feature existe.** Tu APPELLES le code et tu mesures la SORTIE.
2. **Chaque test cree ses propres donnees** dans un repertoire temporaire. Rien de hardcode.
3. **Verdict: PASS / FAIL / SKIP** (SKIP = dependance manquante, API key absente).
4. **Un test qui ne PEUT PAS echouer n'est pas un test.** Si ta verif passe meme sur du code vide, refais ton test.
5. **Tu ne modifies JAMAIS le code source de Muninn.**
6. **Log chaque resultat dans `tests/RESULTS_BATTERY_V2.md`** au fur et a mesure — pas a la fin.
7. **Chronometre chaque test.** Note le temps. > 60s = flag SLOW.
8. **Fais les categories dans l'ordre.** Si un import plante, note et passe a la suivante.
9. **ATTENTION META-MYCELIUM**: le vrai meta est a ~/.muninn/meta_mycelium.db (795Mo). NE PAS le polluer. Utilise un meta temporaire (variable d'env ou monkey-patch le chemin).
10. **Python**: `C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe`

## SETUP COMMUN

```python
import sys, os, json, tempfile, shutil, time, hashlib, re, struct, zlib
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

# Redirect meta-mycelium to temp (NE PAS TOUCHER le vrai)
TEMP_META = Path(tempfile.mkdtemp(prefix="muninn_meta_"))

print(f"TEMP_REPO: {TEMP_REPO}")
print(f"TEMP_META: {TEMP_META}")
```

A la fin de TOUS les tests: `shutil.rmtree(TEMP_REPO); shutil.rmtree(TEMP_META)`

---

# ═══════════════════════════════════════════
# CATEGORIE 1 — COMPRESSION (L0-L7, L10, L11)
# ═══════════════════════════════════════════

## T1.1 — L0 Tool Output Strip
```
DONNEE: transcript JSONL 50 messages dont 15 tool_result de 200+ lignes chacun
  (simule des git diff, cat de fichiers, ls -la)
APPEL: la fonction L0 strip sur le transcript
METRIQUES:
  □ Ratio tokens_avant / tokens_apres >= 2.0 (attendu ~x3.9 sur du vrai transcript)
  □ Chaque tool_result de 200 lignes → max 3 lignes en sortie
  □ Messages user et assistant = INTACTS (compare avant/apres, 0 perte)
  □ PIEGE: un tool_result qui contient "decided to use Redis" (fait important)
    → le resume 1 ligne doit garder "Redis" (pas juste "[tool output stripped]")
```

## T1.2 — L1 Markdown Strip
```
DONNEE: "## Architecture\n**Critical**: the `API` uses a > 99.9% SLA\n- point 1\n- point 2"
APPEL: compress_line() ou compress_section()
METRIQUES:
  □ "##" absent de la sortie
  □ "**" absent de la sortie
  □ "`" absent de la sortie
  □ ">" (quote) absent de la sortie
  □ "Architecture", "Critical", "API", "99.9%", "SLA" tous PRESENTS
  □ len(sortie) < len(entree)
```

## T1.3 — L2 Filler Words + Word Boundary
```
DONNEE A: "I basically think that actually the implementation is essentially working correctly"
DONNEE B: "The factually accurate report was actually useful"
APPEL: compress_line() sur A et B
METRIQUES:
  □ Sortie A: "basically" ABSENT, "actually" ABSENT, "essentially" ABSENT
  □ Sortie A: "implementation" PRESENT, "working" PRESENT
  □ Sortie B: "factually" PRESENT (word boundary — ne doit PAS etre touche)
  □ DONNEE C (P24 causal): "because the server crashed" → "because" PRESENT
  □ DONNEE D (P24 causal): "since we deployed v2" → "since" PRESENT
  □ DONNEE E (P24 causal): "therefore we rolled back" → "therefore" PRESENT
```

## T1.4 — L3 Phrase Compression
```
DONNEE: "in order to achieve the desired outcome we need to take into account all the factors"
APPEL: compress_line()
METRIQUES:
  □ "in order to" → raccourci (attendu: "to" ou similaire, max 3 mots)
  □ "take into account" → raccourci (attendu: "consider" ou similaire)
  □ len(sortie) / len(entree) < 0.75
```

## T1.5 — L4 Number Compression
```
DONNEES:
  A: "The file has 1000000 lines"
  B: "weighs 2500000 bytes"
  C: "version 2.0.1 released"
  D: "accuracy is 0.942"
  E: "latency dropped from 1500ms to 150ms"
APPEL: compress_line() sur chacune
METRIQUES:
  □ A: "1000000" → "1M"
  □ B: "2500000" → "2.5M" ou "2500K"
  □ C: "2.0.1" INCHANGE (c'est un semver, pas un nombre a compresser)
  □ D: "0.942" PRESERVÉ exactement (precision importante)
  □ E: "1500" et "150" preserves (les 2 chiffres, pas juste le dernier)
```

## T1.6 — L5 Universal Rules
```
DONNEES:
  A: "Status: COMPLETED"      → doit contenir "done"
  B: "EN COURS de traitement"  → doit contenir "wip"
  C: "Le build a ECHOUE"       → doit contenir "fail"
  D: "PARTIELLEMENT termine"   → INCHANGÉ (pas dans les regles, ne doit PAS matcher partial)
APPEL: compress_line()
METRIQUES:
  □ A → "done" present, "COMPLETED" absent
  □ B → "wip" present, "EN COURS" absent
  □ C → "fail" present, "ECHOUE" absent
  □ D → "PARTIELLEMENT" PRESENT ou equivalent, PAS remplace par erreur
```

## T1.7 — L6 Mycelium Fusion Strip
```
SETUP: creer Mycelium(TEMP_REPO). Injecter manuellement une fusion:
  ("machine", "learning") → strength >= FUSION_THRESHOLD (=5, mycelium.py ligne 51)
DONNEE: "the machine learning model is ready"
APPEL: compress_line() avec ce mycelium
METRIQUES:
  □ AVEC mycelium: un des deux mots ("machine" ou "learning") est supprime ou fusionne
  □ SANS mycelium (controle): "machine learning" INTACT dans la sortie
  □ "model" et "ready" presents dans les 2 cas
```

## T1.8 — L7 Key-Value Extraction
```
DONNEE: "the accuracy is 94.2% and the loss decreased to 0.031"
APPEL: compress_line()
METRIQUES:
  □ Sortie contient "94.2%" (nombre exact)
  □ Sortie contient "0.031" (nombre exact)
  □ Format key=value ou equivalent compact (pas la phrase entiere)
  □ len(sortie) < len(entree) * 0.7
```

## T1.9 — L10 Cue Distillation
```
DONNEE: 10 lignes expliquant le gradient descent (connaissance generique LLM):
  "Gradient descent is an optimization algorithm. It iteratively adjusts
   parameters by computing the gradient of the loss function. The learning
   rate controls the step size. When the gradient is zero, we've reached
   a local minimum. Stochastic gradient descent uses random mini-batches..."
PLUS 2 lignes de faits SPECIFIQUES au projet:
  "F> our learning rate is 0.003 after tuning on 2026-03-10"
  "D> decided to switch from Adam to SGD because of memory constraints"

APPEL: _cue_distill() (seuil de novelty = 0.35, code ligne 1499)
METRIQUES:
  □ Sortie PLUS COURTE que entree: ratio < 0.7 (L10 vise 0.7 cue_length_ratio, ligne 1528)
  □ L'explication generique du gradient descent est REMPLACEE par un indice court
  □ "0.003" PRESENT dans la sortie (fait specifique)
  □ "2026-03-10" PRESENT (date specifique)
  □ "Adam to SGD" PRESENT (decision specifique)
  □ Le mot "gradient" apparait encore (comme cue) mais pas les 10 lignes d'explication
```

## T1.10 — L11 Rule Extraction (Kolmogorov)
```
DONNEE: 6 lignes avec pattern repetitif:
  "module_api: status=done, tests=42, cov=89%"
  "module_auth: status=wip, tests=18, cov=67%"
  "module_db: status=done, tests=31, cov=91%"
  "module_cache: status=fail, tests=5, cov=23%"
  "module_queue: status=done, tests=27, cov=84%"
  "module_log: status=wip, tests=12, cov=55%"

APPEL: _extract_rules()
METRIQUES:
  □ Nombre de lignes en sortie < 6 (le pattern est factorise)
  □ Toutes les VALEURS specifiques preservees: 42, 18, 31, 5, 27, 12, 89, 67, 91, 23, 84, 55
  □ Les noms de modules preserves: api, auth, db, cache, queue, log
  □ Le pattern "status=X, tests=N, cov=N%" est extrait ou factorise
```

## T1.11 — L9 LLM Compress (OPTIONNEL — PAYANT)
```
PREREQ: ANTHROPIC_API_KEY dans l'env. Si absent → SKIP.
DONNEE: texte de 500+ tokens (un vrai paragraphe technique).
APPEL: _llm_compress()
METRIQUES:
  □ Ratio tokens_apres / tokens_avant < 0.5
  □ 5 faits numeriques de l'entree → tous presents dans la sortie
  □ Temps < 30s
  □ Note: cout API en $ si mesurable
VERDICT: SKIP si pas de cle API
```

---

# ═══════════════════════════════════════════
# CATEGORIE 2 — FILTRES TRANSCRIPT (P17, P24, P25, P26, P27, P28, P38)
# ═══════════════════════════════════════════

## T2.1 — P17 Code Block Compression
```
DONNEE: "Voici le fix:\n```python\ndef calculate_score(branch):\n    recall = compute_recall(branch)\n    return recall * 0.8 + 0.2\n```\nCa marche maintenant."
APPEL: compression
METRIQUES:
  □ Les 3 lignes de code → max 1 ligne en sortie (genre "[code python 3L]")
  □ "Voici le fix" present
  □ "Ca marche maintenant" present
  □ Le contenu du code (les noms de fonctions) peut disparaitre
```

## T2.2 — P24 Causal Connector Protection (deja dans T1.3)
```
Couvert dans T1.3 DONNEES C/D/E. Verifier ici que c'est bien P24 qui agit:
  □ Desactiver P24 (si possible) → "because" DISPARAIT sous L2
  □ Activer P24 → "because" SURVIT
  Si P24 n'est pas desactivable separement, noter que le test est indirect.
```

## T2.3 — P25 Priority Survival
```
DONNEE: 25 lignes dont:
  - 3 lignes "D> decided ..."  (poids D>=5 selon P25, ligne 856)
  - 2 lignes "B> bug: ..."     (poids B>=4)
  - 20 lignes non taggees       (poids=1)
BUDGET: forcer a 10 lignes max

APPEL: la fonction de budget cut / KIComp
METRIQUES:
  □ Les 3 lignes D> sont TOUTES dans la sortie (5 tests: chercher chaque texte exact)
  □ Les 2 lignes B> sont TOUTES dans la sortie
  □ Le nombre total de lignes <= 10
  □ Ce sont les non-taggees qui ont saute
  □ PIEGE: mettre une ligne non-taggee AVANT les taggees → elle doit quand meme sauter
```

## T2.4 — P26 Line Dedup
```
DONNEE:
  Ligne 1: "F> accuracy=94.2% on test set"
  Ligne 2: "F> accuracy=94.2% on test set"            (doublon exact)
  Ligne 3: "F> accuracy=94.2% on the test set"         (quasi-doublon: "the" en plus)
  Ligne 4: "F> latency=15ms on production"              (unique)

APPEL: dedup
METRIQUES:
  □ Doublon exact: 1 seul exemplaire survit (Ligne 1 OU 2, pas les deux)
  □ Quasi-doublon (Ligne 3): survit OU est fusionne avec Ligne 1 (1 seul reste)
  □ Ligne 4: INTACTE (pas un doublon)
  □ Total lignes en sortie: 2 (un accuracy + un latency)
```

## T2.5 — P27 Last Read Only
```
DONNEE: transcript JSONL avec:
  Message 5:  tool_result "cat config.py" → version_a du contenu
  Message 15: tool_result "cat config.py" → version_b (modifie)
  Message 25: tool_result "cat config.py" → version_c (re-modifie)

APPEL: compress_transcript
METRIQUES:
  □ Seule version_c (la derniere) apparait dans la sortie
  □ Un mot unique a version_a: ABSENT
  □ Un mot unique a version_b: ABSENT
  □ Un mot unique a version_c: PRESENT
```

## T2.6 — P28 Claude Verbal Tics
```
DONNEE:
  "Let me analyze this for you. The API has 3 endpoints.
   I'll take a look at the code. Function foo() returns 42.
   Here's what I found: the bug is in line 73."

APPEL: compress
METRIQUES:
  □ "Let me analyze this for you" ABSENT
  □ "I'll take a look at the code" ABSENT
  □ "Here's what I found:" ABSENT
  □ "3 endpoints" PRESENT (fait)
  □ "foo()" PRESENT (fait)
  □ "42" PRESENT (fait)
  □ "line 73" PRESENT (fait)
```

## T2.7 — P38 Multi-Format Detection
```
FICHIER A: test.jsonl — 5 lignes JSON valides ({"role":"user","content":"hello"})
FICHIER B: test.json  — {"messages": [{"role":"user","content":"hello"}]}
FICHIER C: test.md    — "# Session\n## Topic 1\nContent here"

APPEL: detection de format sur chacun
METRIQUES:
  □ A detecte comme JSONL
  □ B detecte comme JSON
  □ C detecte comme MD/Markdown
  □ Pas de crash sur aucun
  □ Un fichier VIDE → pas de crash (retourne un type par defaut ou erreur propre)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 3 — TAGGING (P14, C7)
# ═══════════════════════════════════════════

## T3.1 — P14 Memory Type Tags
```
DONNEES (5 lignes):
  A: "We decided to use PostgreSQL instead of MySQL"
  B: "Bug: the auth middleware crashes on empty tokens"
  C: "The API handles 10K requests per second at p99=15ms"
  D: "Error: connection timeout after 30s on host db-prod-3"
  E: "The system uses a microservice architecture with 12 services"

APPEL: fonction P14 tag_line() ou equivalent
METRIQUES:
  □ A → commence par "D>" (decision). Tag score = 0.9 (ligne 652)
  □ B → commence par "B>" (bug/blocker). Tag score = 0.8
  □ C → commence par "F>" (fact). Tag score = 0.8
  □ D → commence par "E>" (error). Tag score = 0.7
  □ E → commence par "A>" (architecture). Tag score = 0.7
  □ Ligne ambigue "The test passed" → un tag ou pas, mais PAS de crash
  □ Ligne vide "" → PAS de crash, pas de tag
```

## T3.2 — C7 Contradiction Resolution
```
DONNEE:
  Ligne 3:  "accuracy=92% on val set"
  Ligne 18: "accuracy=97% on val set after fine-tuning"
  Ligne 7:  "latency=50ms at peak"
  Ligne 22: "throughput=1200 req/s"

APPEL: resolve_contradictions()
METRIQUES:
  □ "accuracy=92%" ABSENT (stale, remplacee)
  □ "accuracy=97%" PRESENT (derniere valeur)
  □ "latency=50ms" PRESENT (pas en contradiction avec autre chose)
  □ "throughput=1200" PRESENT (pas en contradiction)
  □ Nombre de lignes supprimees = exactement 1 (seule la vieille accuracy part)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 4 — MYCELIUM (S1-S3, NCD, Spreading, V3A, B2, B3, P20, P41)
# ═══════════════════════════════════════════

## T4.1 — S1 SQLite Storage
```
SETUP: Mycelium(TEMP_REPO)
APPEL: observer 3 paragraphes:
  P1: "Python Flask web API endpoint REST JSON"
  P2: "Python Django web framework template ORM"
  P3: "Rust memory safety ownership borrow checker"

METRIQUES:
  □ Fichier .muninn/mycelium.db existe et taille > 0
  □ SELECT COUNT(*) FROM concepts > 0
  □ SELECT COUNT(*) FROM edges > 0
  □ "python" a concept_id = un entier (pas une string)
  □ Edge (python, flask) existe avec count >= 1
  □ Edge (python, rust) n'existe PAS (jamais dans le meme paragraphe)
  □ Edge (python, web) existe (co-occurrence dans P1 et P2, count >= 2)
```

## T4.2 — S2 Epoch-Days
```
APPEL: fonctions epoch_days() et from_epoch_days() (mycelium_db.py ligne ~20-52)
METRIQUES:
  □ "2020-01-01" → 0
  □ "2026-03-12" → 2263 (verifie: (2026-2020)*365 + jours bissextiles + 71 jours)
  □ Aller-retour: date → epoch → date = meme date
  □ PIEGE: "2024-02-29" (bissextile) → convertit et reconvertit sans erreur
```

## T4.3 — S3 Degree Filter (top 5% = stopwords)
```
SETUP: Mycelium(TEMP_REPO). Observer 100 paragraphes ou "data" apparait dans CHACUN
  avec 100 concepts differents a chaque fois.
  Puis observer 10 paragraphes ou "flask" apparait avec 3 concepts.

APPEL: verifier le degre de "data" vs "flask"
METRIQUES:
  □ degre("data") >> degre("flask")
  □ "data" est dans le top 5% (DEGREE_FILTER_PERCENTILE = 0.05, mycelium.py ligne 58)
  □ "data" est BLOQUÉ de la fusion (ne peut pas fusionner meme avec count eleve)
  □ "flask" PEUT fusionner (pas dans le top 5%)
```

## T4.4 — Observe + Get Related
```
SETUP: observer 20 paragraphes ou "compression" et "tokens" co-occurrent.
APPEL: m.get_related("compression", top_n=5)
METRIQUES:
  □ "tokens" dans les resultats
  □ strength > 0
  □ Resultats tries par strength decroissant
  □ m.get_related("xyzzy_nonexistent", top_n=5) → liste vide, PAS de crash
  □ len(resultats) <= 5 (top_n respecte)
```

## T4.5 — P20 Federated Zones
```
SETUP: observer avec zone="repo_A", puis avec zone="repo_B"
METRIQUES:
  □ La table edge_zones a des entrees pour "repo_A" et "repo_B"
  □ IMMORTAL_ZONE_THRESHOLD = 3 (ligne 55): un concept dans 3+ zones = immortel
  □ Observer le meme concept dans 3 zones → verifier qu'il skip le decay
```

## T4.6 — P20b Meta-Mycelium Sync + Pull
```
ATTENTION: utiliser TEMP_META, PAS ~/.muninn/
SETUP: creer mycelium local avec 50 connexions, dont (python, flask, count=10)
APPEL: m.sync_to_meta() → puis creer un 2eme mycelium VIDE → m2.pull_from_meta(["python"], max_pull=200)

METRIQUES:
  □ sync retourne n_synced >= 50
  □ meta DB a TEMP_META existe, taille > 0
  □ pull retourne n_pulled > 0
  □ m2.get_related("python") retourne "flask" (venu du meta)
  □ max_pull respecte: n_pulled <= 200 (MAX_PULL, muninn.py ligne 2219)
```

## T4.7 — NCD Similarity
```
DONNEES:
  A = "python flask api web server endpoint json rest"
  B = "python flask web api endpoint json rest server"
  C = "quantum physics electron photon wave particle duality"

APPEL: ncd(A, B) et ncd(A, C)
METRIQUES:
  □ ncd(A, B) < 0.4 (tres similaires — seuil merge, ligne 1920)
  □ ncd(A, C) > 0.6 (tres differents — seuil dedup, ligne 2658)
  □ 0.0 <= ncd <= 1.0 pour tous les cas
  □ ncd(A, A) ≈ 0.0 (identique)
  □ ncd("", "") → pas de crash (division par zero potentielle)
```

## T4.8 — Spreading Activation
```
SETUP: mycelium avec chaine forte:
  "python" ↔ "flask" (count=20)
  "flask" ↔ "jinja" (count=15)
  "jinja" ↔ "templates" (count=10)
  "quantum" ↔ "physics" (count=20, deconnecte du reste)

APPEL: m.spread_activation(["python"], hops=2, decay=0.5, top_n=50)
  (parametres par defaut: hops=2, decay=0.5, top_n=50 — ligne 2261)

METRIQUES:
  □ "flask" active avec score > 0 (hop 1)
  □ "jinja" active avec score > 0 (hop 2)
  □ score("flask") > score("jinja") (decay 0.5 par hop)
  □ "templates" PAS active (hop 3, mais hops=2)
  □ "quantum" PAS active (pas connecte a python)
  □ len(resultats) <= 50
```

## T4.9 — A3 Sigmoid Post-Filter
```
APPEL: spread_activation avec sigmoid actif (_sigmoid_k=10, mycelium.py ligne 67)
METRIQUES:
  □ Scores faibles (< 0.1) → ecrases vers ~0 par le sigmoid
  □ Scores forts (> 0.5) → preserves (sigmoid sature vers 1)
  □ L'ORDRE des resultats est preserve (rank preservation)
  □ sigmoid(0.5) ≈ 0.5 (point d'inflexion, avec k=10 et x0=0.5)
```

## T4.10 — V3A Transitive Inference
```
SETUP: mycelium avec chaine ordonnee:
  A → B (count=20), B → C (count=15), C → D (count=10)
APPEL: m.transitive_inference("A", max_hops=3, beta=0.5, top_n=20)
  (parametres: max_hops=3, beta=0.5, top_n=20 — ligne 2282)

METRIQUES:
  □ B trouve (hop 1), score S_B
  □ C trouve (hop 2), score S_C < S_B (decay multiplicatif beta=0.5)
  □ D trouve (hop 3), score S_D < S_C
  □ S_B / S_C ≈ 2 (ratio ~1/beta)
  □ Avec max_hops=1: D PAS trouve
  □ len(resultats) <= 20
```

## T4.11 — P41 Self-Referential Growth
```
SETUP: mycelium avec fusion ("machine", "learning") → "ML"
APPEL: la fonction de croissance self-referentielle (observe les fusions comme concepts)
METRIQUES:
  □ "ML" apparait comme concept dans la DB
  □ Pas de recursion infinie (timeout 10s)
  □ La connexion de second ordre existe
```

## T4.12 — B2 Graph Anomaly Detection
```
SETUP: mycelium ou:
  - "isolated_concept" a 0 connexions
  - "hub_concept" a 100+ connexions (connecte a tout)
  - "normal_concept" a 5-10 connexions

APPEL: m.detect_anomalies()
METRIQUES:
  □ "isolated_concept" detecte (type "isolated")
  □ "hub_concept" detecte (type "hub")
  □ "normal_concept" PAS dans les anomalies
  □ Retourne une structure avec type + concept name
```

## T4.13 — B3 Blind Spot Detection
```
SETUP: mycelium ou:
  A ↔ B fort (count=20), B ↔ C fort (count=20), A ↔ C ABSENT

APPEL: m.detect_blind_spots(top_n=20) (ligne 2300)
METRIQUES:
  □ La paire (A, C) est identifiee comme trou structurel
  □ La paire (A, B) n'est PAS un trou (deja connectes)
  □ Score du trou > 0
  □ Resultat contient au moins 1 entree
```

---

# ═══════════════════════════════════════════
# CATEGORIE 5 — TREE & BRANCHES
# ═══════════════════════════════════════════

## T5.1 — Arbre minimal load/save
```
SETUP: ecrire tree.json:
  {
    "root": {"file": "root.mn", "tags": ["project"], "temperature": 1.0,
             "last_access": "2026-03-12", "access_count": 10},
    "branch_api": {"file": "branch_api.mn", "tags": ["api", "rest", "flask"],
                   "temperature": 0.8, "last_access": "2026-03-11", "access_count": 5},
    "branch_db": {"file": "branch_db.mn", "tags": ["database", "sql", "migration"],
                  "temperature": 0.3, "last_access": "2026-02-15", "access_count": 2}
  }
  + ecrire les .mn correspondants dans TREE_DIR.

APPEL: load_tree()
METRIQUES:
  □ 3 noeuds charges (root + 2 branches)
  □ root.temperature == 1.0
  □ branch_api.tags contient "api"
  □ save_tree() puis reload → donnees identiques
```

## T5.2 — P34 Integrity Check
```
SETUP: arbre avec 2 branches. Calculer le vrai hash de branch_api.mn.
  Mettre le BON hash dans tree.json pour branch_api.
  Mettre un MAUVAIS hash "0000dead" pour branch_db.

APPEL: boot ou load avec integrity check (ligne 586-592)
METRIQUES:
  □ branch_api: chargee normalement (hash OK)
  □ branch_db: SIGNALÉE comme corrompue ou SKIPPÉE
  □ Pas de crash
```

## T5.3 — P19 Branch Dedup (NCD > 0.6)
```
SETUP: 2 branches avec contenu quasi-identique:
  branch_a.mn: "python flask api rest endpoint json web server"
  branch_b.mn: "python flask api rest endpoint json web server"  (copie exacte)

APPEL: fonction de dedup (seuil NCD = 0.6, ligne 2658)
METRIQUES:
  □ NCD(a, b) < 0.6 (quasi-identiques)
  □ Dedup identifie les 2 comme duplicatas
  □ Une seule survit apres dedup
```

## T5.4 — R4 Prune complet
```
SETUP: arbre avec 4 branches + mycelium avec leurs tags:
  - "hot_branch": last_access=hier, access_count=20 → recall > 0.4
  - "cold_branch": last_access=il y a 20 jours, access_count=3 → recall entre 0.05 et 0.4
  - "dead_branch": last_access=il y a 200 jours, access_count=1 → recall < 0.05
  - "sole_carrier": last_access=il y a 200 jours, access_count=1, MAIS tag unique
    "unique_concept_xyz" que PERSONNE d'autre n'a → V9B protection

  Seuils du code:
    HOT: recall >= 0.4 (ligne 3542)
    COLD: recall < 0.15 (ligne 3553) — attention: le code dit < 0.15 pas < 0.4
    DEAD: recall < 0.05 (ligne 3545)

APPEL: prune(dry_run=True) puis prune(dry_run=False)

METRIQUES dry_run:
  □ Affiche les categories sans rien supprimer
  □ Tous les fichiers .mn encore presents

METRIQUES real:
  □ hot_branch: INCHANGEE, fichier present
  □ cold_branch: toujours la, eventuellement re-compressée
  □ dead_branch (pas sole carrier): SUPPRIMÉE, fichier .mn absent, noeud absent de tree.json
  □ sole_carrier (V9B): PAS SUPPRIMÉE malgre recall < 0.05
    → demotee en cold (ligne 3549: "PROTECTED (sole carrier) -> cold")
    → fichier .mn encore present
```

## T5.5 — V9A+ Fact Regeneration
```
SETUP:
  - "dying_branch": DEAD (recall=0.01), .mn contient:
      "D> decided to use Redis for caching"
      "F> latency dropped from 200ms to 15ms"
      "B> bug in auth: empty token crash"
      "some untagged noise line"
  - "survivor_branch": HOT (recall=0.8), tags en commun avec dying (ou mycelium lie)
  - Tags de dying_branch dans tree.json: ["redis", "caching", "auth"]
  - Tags de survivor_branch dans tree.json: ["redis", "api", "performance"]
  - Mycelium: "redis" ↔ "caching" (count=10), "redis" ↔ "api" (count=8)

APPEL: prune() (V9A+ se declenche lignes 3605-3747)

METRIQUES:
  □ Le .mn de survivor_branch contient maintenant une section "## REGEN: dying_branch"
  □ La ligne "D> decided to use Redis for caching" est dans le survivor
  □ La ligne "F> latency dropped from 200ms to 15ms" est dans le survivor
  □ La ligne "B> bug in auth: empty token crash" est dans le survivor
  □ La ligne "some untagged noise line" est ABSENTE du survivor (non-taggee = perdue)
  □ Le .mn de dying_branch est SUPPRIMÉ
  □ Les tags "caching" et "auth" sont diffuses a survivor (tag diffusion step 4)
  □ Nombre de faits regeneres = 3 (console: "V9A+ REGEN: 3 facts + N tags")
  □ Si survivor > 200 lignes apres injection: L10+L11 re-appliques (ligne 3712)
```

## T5.6 — V9A+ sans survivant
```
SETUP: arbre avec 1 seule branche (DEAD), pas de root avec tags.
APPEL: prune()
METRIQUES:
  □ Pas de crash
  □ La branche est supprimee
  □ Les faits sont PERDUS (comportement attendu actuel)
  □ Console: PAS de "V9A+ REGEN" (rien a regenerer vers)
```

## T5.7 — P16 Session Log
```
SETUP: root.mn existant avec section "R:" contenant 5 entrees
APPEL: ajouter une 6eme entree
METRIQUES:
  □ root.mn contient 5 entrees (la plus ancienne ejectee)
  □ La nouvelle entree est LA (la 6eme)
  □ La 1ere ancienne est PARTIE (max 5)
```

## T5.8 — B7 Live Injection
```
APPEL: inject("SQLite is faster than JSON for 100K+ entries", repo_path=TEMP_REPO)
METRIQUES:
  □ tree.json a un nouveau noeud
  □ Le .mn du nouveau noeud contient "SQLite" et "100K"
  □ Le mycelium a des connexions pour "sqlite" et "json"
  □ Le noeud a temperature = 0.1 (new_branch_temperature, ligne 1999)
```

## T5.9 — P40 Bootstrap Branches
```
SETUP: 3 fichiers .py dans TEMP_REPO (avec du contenu realiste, 50 lignes chacun)
APPEL: bootstrap(TEMP_REPO)
METRIQUES:
  □ tree.json existe et a root + au moins 1 branche
  □ root.mn existe et contient un resume
  □ mycelium.db a des connexions
  □ Le contenu des fichiers .py a nourri les branches (spot check: un nom de classe present)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 6 — BOOT & RETRIEVAL
# ═══════════════════════════════════════════

## T6.1 — Boot basique avec scoring
```
SETUP: arbre avec root + 5 branches:
  - "api_design": tags=["rest","api","endpoint"], contenu parle de REST
  - "database": tags=["sql","postgres","migration"], contenu parle de SQL
  - "frontend": tags=["react","css","component"], contenu parle de UI
  - "devops": tags=["docker","k8s","deploy"], contenu parle de containers
  - "testing": tags=["pytest","mock","coverage"], contenu parle de tests

APPEL: boot("REST API endpoint design", repo_path=TEMP_REPO)

METRIQUES:
  □ Root TOUJOURS charge
  □ "api_design" chargee (relevance score = plus haut des 5)
  □ Le score de "api_design" > score de "frontend" (plus pertinent)
  □ Budget total < 30K tokens (BUDGET["max_loaded_tokens"]=30000, ligne 322)
  □ Le boot retourne les branches dans l'ordre de score decroissant
```

## T6.2 — P15 Query Expansion via mycelium
```
SETUP: mycelium ou:
  "REST" ↔ "API" (count=15, strength >= 3 → seuil P15, ligne 2226)
  "REST" ↔ "HTTP" (count=12)
  "REST" ↔ "JSON" (count=10)
  + branches comme T6.1

APPEL: boot("REST", repo_path=TEMP_REPO)

METRIQUES:
  □ La query expandue contient "API" et/ou "HTTP" et/ou "JSON"
  □ Des branches qui parlent de "API" sans le mot "REST" sont trouvees
  □ Le nombre de termes expands > le nombre de termes originaux
```

## T6.3 — P23 Auto-Continue
```
SETUP: session_index.json avec derniere session:
  {"sessions": [{"date": "2026-03-12", "concepts": ["docker", "compose", "deploy"]}]}

APPEL: boot("", repo_path=TEMP_REPO)  (query VIDE)

METRIQUES:
  □ Les concepts "docker", "compose", "deploy" sont utilises comme query
  □ La branche "devops" est chargee (si l'arbre de T6.1 est en place)
```

## T6.4 — P37 Warm-Up
```
SETUP: branch_api avec access_count=5, last_access="2026-03-10"
APPEL: boot("api", repo_path=TEMP_REPO) → branch_api est chargee
METRIQUES:
  □ access_count passe a 6 (incrementé, ligne 2870-2879)
  □ last_access passe a "2026-03-12" (aujourd'hui)
```

## T6.5 — Scoring multi-facteur (poids 0.15/0.40/0.20/0.10/0.15)
```
SETUP:
  - "recent_trivial": access hier, recall=0.9, MAIS contenu="weather forecast today"
  - "old_relevant": access il y a 30j, recall=0.05, MAIS contenu="REST API endpoint design"

APPEL: boot("REST API", repo_path=TEMP_REPO)

METRIQUES:
  □ Score de "old_relevant" > score de "recent_trivial"
  □ Parce que w_relevance=0.40 >> w_recall=0.15
  □ Decomposer le score: montrer les 5 composantes pour chaque branche
  □ Verifier: 0.15*recall + 0.40*relevance + 0.20*activation + 0.10*usefulness + 0.15*rehearsal = total
```

---

# ═══════════════════════════════════════════
# CATEGORIE 7 — FORMULES SCORING
# ═══════════════════════════════════════════

## T7.1 — Ebbinghaus Recall
```
PARAMETRES: h_base=7 jours (ligne 457), reviews_cap=10

CALCULS ATTENDUS:
  □ delta=1j, h=7, reviews=0: recall = 2^(-1/7) = 0.9057 (tolerance +-0.01)
  □ delta=7j, h=7, reviews=0: recall = 2^(-7/7) = 0.5000
  □ delta=30j, h=7, reviews=0: recall = 2^(-30/7) = 0.0503
  □ delta=0j: recall ≈ 1.0
  □ delta=1j, reviews=3: h = 7 * 2^3 = 56 → recall = 2^(-1/56) = 0.9877

VERIFIER: les valeurs calculees par le code matchent ces chiffres.
```

## T7.2 — A1 Adaptive Half-Life
```
PARAMETRES: _h_beta=0.5 (ligne 427), usefulness clampe [0.1, 1.0] (ligne 456)

CALCULS:
  □ usefulness=0.9: h = 7 * 0.9^0.5 = 7 * 0.9487 = 6.64 jours
  □ usefulness=0.1: h = 7 * 0.1^0.5 = 7 * 0.3162 = 2.21 jours
  □ usefulness=None: doit PAS crasher (clamp a 0.1 ou default)
  □ h(useful=0.9) / h(useful=0.1) ≈ 3.0 (la branche utile decroit 3x plus lentement)
```

## T7.3 — A2 ACT-R Base-Level
```
PARAMETRES: _d=0.5 (ligne 479), blend 70/30 (ligne 2419)

SETUP: branche accedee a t=[1, 3, 7, 14, 30] jours
CALCUL:
  B = ln(1^(-0.5) + 3^(-0.5) + 7^(-0.5) + 14^(-0.5) + 30^(-0.5))
    = ln(1.0 + 0.577 + 0.378 + 0.267 + 0.183)
    = ln(2.405) = 0.878

  recall_actr = sigmoid(B) ou mapping equivalent
  recall_final = 0.7 * recall_ebbinghaus + 0.3 * recall_actr

METRIQUES:
  □ Le B calcule par le code ≈ 0.878 (tolerance +-0.05)
  □ recall_final est entre recall_ebbinghaus et recall_actr
  □ PIEGE: historique VIDE → B = -inf ou 0 → pas de crash
  □ access_history_cap respecte: max 10 entrees (ligne 596)
```

## T7.4 — V4B EWC Fisher Importance
```
PARAMETRES: _lambda_ewc=0.5 (ligne 429), fisher clampe [0.0, 1.0] (ligne 465)

SETUP: branche accedee 20x dans les 7 derniers jours (Fisher haute = critique)
  vs branche accedee 1x il y a 60 jours (Fisher basse)

METRIQUES:
  □ Fisher de la branche critique > Fisher de la branche rare
  □ Valeurs dans [0, 1]
  □ La branche critique a un bonus qui la protege du pruning
```

---

# ═══════════════════════════════════════════
# CATEGORIE 8 — PRUNING AVANCE (I1-I3, V5B, Sleep, Dreams)
# ═══════════════════════════════════════════

## T8.1 — I1 Danger Theory
```
PARAMETRES: danger_score clampe [0, 1] (ligne 471)

SETUP: 2 sessions:
  Session A (chaotique): 10 messages dont 5 erreurs, 3 retries, 2 changements de direction
  Session B (calme): 10 messages, 0 erreurs, flow lineaire

APPEL: calculer le danger score des 2
METRIQUES:
  □ danger_A > 0.5 (session chaotique = high danger)
  □ danger_B < 0.2 (session calme = low danger)
  □ danger_A > danger_B (l'ecart est significatif, pas +-0.01)
  □ Les branches de session A ont h plus grand (I1 boost durabilite via gamma_danger)
```

## T8.2 — I2 Competitive Suppression
```
PARAMETRES: _i2_alpha=0.1 (ligne 3443), seuil NCD < 0.4 (ligne 3442), recall < 0.4 (ligne 3451)

SETUP: 3 branches toutes avec recall=0.3 (dans la zone I2):
  - branch_a: contenu A (unique)
  - branch_b: contenu similaire a A (NCD(a,b) < 0.4)
  - branch_c: contenu totalement different (NCD(a,c) > 0.7)

APPEL: I2 dans prune
METRIQUES:
  □ effective_recall de branch_a OU branch_b baisse (l'une supprime l'autre)
  □ effective_recall de branch_c INCHANGEE (pas similaire)
  □ La plus faible des deux similaires est penalisee de _i2_alpha * overlap
```

## T8.3 — I3 Negative Selection
```
PARAMETRES: anomaly_demote_threshold = 0.15 (ligne 3534)

SETUP: branche anormale: 500 lignes, 0 tags, 0 faits numeriques
  + branche normale: 20 lignes, 5 tags, 3 faits numeriques

APPEL: I3 dans prune
METRIQUES:
  □ Branche anormale: temperature baisse (demotee si recall >= 0.15)
  □ Branche normale: temperature INCHANGÉE
```

## T8.4 — Sleep Consolidation
```
PARAMETRES: NCD seuil = 0.6 (ligne 3168)

SETUP: 2 branches COLD avec contenu similaire (NCD < 0.6):
  cold_a.mn: "api rest endpoint json flask routing middleware"
  cold_b.mn: "api rest endpoint json django routing views"

APPEL: _sleep_consolidate([cold_a, cold_b], nodes)
METRIQUES:
  □ 2 branches → 1 branche mergee
  □ Le merge contient "flask" ET "django" (contenu des 2)
  □ Les lignes dupliquees sont eliminees ("api rest endpoint json" 1 seule fois)
  □ L10 + L11 appliques au merge
  □ Le noeud en trop est supprime de tree.json
```

## T8.5 — H1 Trip Mode (BARE Wave)
```
PARAMETRES: alpha_base=0.04, beta_base=0.02 (mycelium.py ligne 1668-1669)
  intensity=0.5 (ligne 3590), max_dreams=15 (ligne 3590)

APPEL: m.trip(intensity=0.5, max_dreams=15)
METRIQUES:
  □ Retourne une liste de "dreams" (nouvelles connexions ou insights)
  □ len(dreams) <= 15
  □ Chaque dream a des champs type + text (ou equivalent)
  □ Pas de crash, temps < 30s
```

## T8.6 — H3 Huginn Insights
```
SETUP: mycelium avec paires fortes et trous structurels

APPEL: huginn_think(query_concepts=["api"], top_n=5) (ligne 3316)
METRIQUES:
  □ Retourne liste de dicts avec type + text
  □ Types valides: strong_pair, structural_hole, dream, etc.
  □ Texte en langage naturel (pas du JSON brut)
  □ len(resultats) <= 5
  □ Les insights sont lies a "api" (pas random)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 9 — EMOTIONAL (V6A, V6B, V10A, V10B)
# ═══════════════════════════════════════════

## T9.1 — V6A Emotional Tagging (Hill function)
```
DONNEE A: "CRITICAL BUG: the entire production database is down!! Users can't login!!"
DONNEE B: "The test suite passed. All 42 tests green."

APPEL: emotional scoring
METRIQUES:
  □ arousal(A) > 0.5 (message intense)
  □ arousal(B) < 0.3 (message calme)
  □ La difference est > 0.2 (pas du bruit)
```

## T9.2 — V6B Valence-Modulated Decay
```
PARAMETRES: _alpha_v=0.3, _alpha_a=0.2 (ligne 428)

SETUP: 2 branches meme age (delta=14 jours):
  - negative_branch: valence=-0.8 (session ou tout a casse)
  - neutral_branch: valence=0.0

APPEL: calculer le decay / half-life des 2
METRIQUES:
  □ h_negative > h_neutral (memoire negative decroit PLUS LENTEMENT)
  □ Le ratio h_negative/h_neutral > 1.1 (difference mesurable, pas cosmetique)
  □ Formule: h *= (1 + _alpha_v * abs(valence) + _alpha_a * arousal)
```

## T9.3 — V10B Russell Circumplex
```
APPEL avec differentes combinaisons valence/arousal:
  □ valence=+0.8, arousal=+0.7 → quadrant "excited"/"happy" (haut-droit)
  □ valence=-0.8, arousal=+0.7 → quadrant "angry"/"stressed" (haut-gauche)
  □ valence=+0.5, arousal=+0.1 → quadrant "calm"/"content" (bas-droit)
  □ valence=-0.5, arousal=+0.1 → quadrant "sad"/"bored" (bas-gauche)
  □ Pas de crash sur valence=0, arousal=0
```

---

# ═══════════════════════════════════════════
# CATEGORIE 10 — BOOT SCORING AVANCE (V5A, V7B, V11B, B4-B6)
# ═══════════════════════════════════════════

## T10.1 — V5A Quorum Sensing (Hill function)
```
PARAMETRES: K=2.0, n=3 (lignes 2497-2498), bonus_max=0.03 (ligne 2502)

SETUP:
  - branch_popular: tag "api" present dans 8 autres branches (quorum atteint)
  - branch_niche: tag "quantum_xyz" present dans 0 autres branches

CALCUL attendu pour branch_popular:
  tag_count("api") = 8 parmi N branches. freq = 8/N
  Hill = freq^3 / (2.0^3 + freq^3)

METRIQUES:
  □ bonus(popular) > 0 et <= 0.03
  □ bonus(niche) ≈ 0 (pas de quorum)
  □ La Hill function a un seuil net autour de K=2.0
```

## T10.2 — V7B ACO Pheromone
```
PARAMETRES: bonus_max=0.05 (ligne 2447), floor=0.01 (lignes 2443-2444)

SETUP:
  - branch_visited: access_count=20 (beaucoup de pheromone)
  - branch_fresh: access_count=1

METRIQUES:
  □ aco_bonus(visited) > aco_bonus(fresh)
  □ aco_bonus dans [0, 0.05]
  □ Formule: tau^1 * eta^2, avec tau=pheromone, eta=heuristic
```

## T10.3 — V11B Boyd-Richerson 3 Biases
```
PARAMETRES: _conform_beta=0.3 (ligne 2476), conform_max=0.15 (ligne 2477),
  prestige_max=0.06 (ligne 2482), guided_max=0.06 (ligne 2488)

SETUP: 10 branches avec access_counts varies (1, 2, 3, 5, 8, 13, 21, 34, 55, 89)

METRIQUES CONFORMISTE:
  □ Branches avec access_count=89 (populaire): bonus conformiste > 0.10
  □ Branches avec access_count=1 (impopulaire): bonus conformiste ≈ 0
  □ La courbe logistique dp = beta*p*(1-p)*(2p-1) a point d'inflexion a p=0.5

METRIQUES PRESTIGE:
  □ Bonus prestige dans [0, 0.06]
  □ Branches de "sessions longues" (proxy prestige) boostees

METRIQUES GUIDED:
  □ Bonus guided dans [0, 0.06]
  □ Branches nouvelles avec faible historique = plus d'exploration
```

## T10.4 — B4 Predict Next
```
PARAMETRES: top_n=5 (ligne 2909)

SETUP: arbre + mycelium + concepts de session ["API", "REST"]
APPEL: predict_next(current_concepts=["API", "REST"], top_n=5)

METRIQUES:
  □ Retourne une liste de max 5 elements
  □ Les elements sont des CONCEPTS (ou des branches — documenter lequel)
  □ Les concepts sont lies a API/REST (pas random)
  □ BUG CONNU A VERIFIER: si ca retourne des concepts mais le scoring attend
    des branches → documenter si le bonus B4 vaut toujours 0
    (bonus_max=0.03 ligne 2462, mais mismatch concept/branch → bonus effectif?)
```

## T10.5 — B5 Session Mode
```
PARAMETRES: k_divergent=5, k_convergent=20, k_balanced=10 (lignes 3025-3033)
  diversity_divergent > 0.6, diversity_convergent < 0.4 (lignes 3025-3028)

SETUP:
  Session A: 20 concepts tous differents (haute diversite > 0.6)
  Session B: 5 concepts repetes 4x chacun (basse diversite < 0.4)

APPEL: detect session mode
METRIQUES:
  □ Session A → "divergent", sigmoid k = 5 (large, explore)
  □ Session B → "convergent", sigmoid k = 20 (sharp, focus)
  □ Session mixte → "balanced", k = 10
```

## T10.6 — B6 RPD Type + Weight Adjust
```
APPEL: detect RPD type pour differents contextes

METRIQUES:
  □ Session avec beaucoup d'erreurs → "debug"
    Poids ajustes: w_recall=0.20, w_usefulness=0.15 (lignes 2364-2365)
  □ Session exploratoire → "explore"
    Poids ajustes: w_activation=0.30, w_relevance=0.30 (lignes 2369-2370)
  □ Session review → "review"
    Poids ajustes: w_rehearsal=0.25, w_relevance=0.35 (lignes 2374-2375)
  □ La somme des poids = 1.0 TOUJOURS (invariant)
```

---

# ═══════════════════════════════════════════
# CATEGORIE 11 — PIPELINE END-TO-END
# ═══════════════════════════════════════════

## T11.1 — Compress Transcript complet
```
SETUP: generer un faux transcript JSONL de 100 messages:
  - 40 user messages (questions, decisions, bugs)
  - 40 assistant messages (avec verbal tics, explications)
  - 20 tool_results (git diff, cat fichier, ls)
  - Inclure: 5 nombres importants (42, 94.2%, 15ms, 2026-03-12, v3.1)
  - Inclure: 1 faux token GitHub "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  - Inclure: 3 decisions explicites ("decided to...", "we chose...", "switched from X to Y")
  - Taille: ~50K tokens minimum

APPEL: compress_transcript(jsonl_path, repo_path=TEMP_REPO)

METRIQUES:
  □ Le .mn de sortie existe dans SESSIONS_DIR
  □ Ratio tokens: input/output >= 2.0 (minimum, attendu x4+ sur du vrai)
  □ Les 5 nombres sont TOUS dans la sortie (chercher chacun)
  □ Le token GitHub "ghp_" est ABSENT de la sortie (secret filtre)
  □ Au moins 2 des 3 decisions sont taggees D>
  □ Temps < 60s pour 100 messages
  □ Le fichier .mn a des lignes taggees (D>, B>, F>, E>, A>)
  □ Pas de ligne vide consecutive (> 2 newlines d'affilee)
```

## T11.2 — Grow Branches from Session
```
SETUP: un .mn avec 3 sections:
  "## API Design\nD> decided REST over GraphQL\nF> 3 endpoints: /users, /items, /search"
  "## Database\nD> chose PostgreSQL\nF> 2M rows expected\nB> migration script fails on NULL"
  "## Testing\nF> 42 tests passing\nF> coverage=89%"

APPEL: grow_branches_from_session(mn_path, repo_path=TEMP_REPO)

METRIQUES:
  □ tree.json a au moins 3 nouvelles branches (ou merge avec existantes)
  □ Chaque branche a des tags extraits de sa section
  □ branche "API Design" a tags incluant "api" ou "rest"
  □ branche "Database" a tags incluant "postgresql" ou "sql"
  □ Le mycelium a ete nourri (edges > 0 avant vs apres)
```

## T11.3 — Feed complet (simulation hook)
```
SETUP: transcript JSONL de 50 messages + arbre avec root + mycelium vide

APPEL: simuler le pipeline feed complet:
  1. feed_from_transcript (mycelium)
  2. compress_transcript
  3. grow_branches_from_session
  4. refresh_tree_metadata
  5. sync_to_meta (vers TEMP_META)

METRIQUES:
  □ Mycelium: edges > 0 apres feed
  □ Session .mn: existe et non-vide
  □ Branches: au moins 1 nouvelle branche
  □ Tree: metadata a jour (temperatures, dates)
  □ Meta: synce (n_synced > 0)
  □ TOUT sans crash, temps total < 120s
```

---

# ═══════════════════════════════════════════
# CATEGORIE 12 — EDGE CASES & ROBUSTESSE
# ═══════════════════════════════════════════

## T12.1 — Cold Start total
```
SETUP: repo vide. Rien. Pas de tree.json, pas de mycelium.db, pas de sessions.
APPEL: boot("hello world", repo_path=TEMP_REPO)
METRIQUES:
  □ Pas de crash
  □ Retour propre (root vide ou message "no data")
  □ Pas de traceback Python dans stderr
```

## T12.2 — Fichier .mn corrompu (binaire)
```
SETUP: ecrire 1024 octets random dans un .mn + le referencer dans tree.json
APPEL: boot ou prune qui doit lire ce fichier
METRIQUES:
  □ Pas de crash (UnicodeDecodeError catche)
  □ La branche est ignoree ou signalée
  □ Les autres branches fonctionnent normalement
```

## T12.3 — Mycelium vide (0 connexions)
```
SETUP: Mycelium(TEMP_REPO) fraichement cree, rien observe
APPEL:
  m.get_related("test") → []
  m.spread_activation(["test"]) → {}
  m.transitive_inference("test") → []
  m.detect_blind_spots() → []
  m.detect_anomalies() → []

METRIQUES:
  □ TOUS retournent des collections vides
  □ AUCUN crash
  □ Temps < 1s chacun
```

## T12.4 — Performance: 500 branches
```
SETUP: generer 500 branches avec contenu random (20 lignes chacune, tags random)
APPEL: boot("test query", repo_path=TEMP_REPO)
METRIQUES:
  □ Boot termine en < 30 secondes
  □ Budget 30K tokens respecte (pas plus de ~20 branches chargees)
  □ RAM < 500Mo pendant le boot
  □ Si > 30s: flag SLOW + noter le bottleneck
```

## T12.5 — Unicode et caracteres speciaux
```
DONNEES:
  - Texte avec emojis: "The build succeeded 🎉 with 0 errors"
  - Texte CJK: "压缩比 x4.5"
  - Texte accents: "Le système a échoué à 14h30"
  - Texte avec \0 (null byte): "test\x00value"

APPEL: compress_line() sur chacun
METRIQUES:
  □ Emojis: pas de crash, "0 errors" PRESENT
  □ CJK: pas de crash, "x4.5" PRESENT
  □ Accents: pas de crash, "14h30" PRESENT
  □ Null byte: pas de crash (ignore ou strip)
```

## T12.6 — Lock concurrent
```
SETUP: lancer 2 operations en parallele sur le meme repo (2 threads ou 2 process)
METRIQUES:
  □ Le lock empeche la corruption de tree.json
  □ Le 2eme process attend (ou retourne une erreur propre)
  □ STALE_SECONDS = 600 (10 minutes, ligne 5396) → lock expire apres
  □ Pas de deadlock
```

---

# ═══════════════════════════════════════════
# CATEGORIE 13 — INTEGRATION V2B, V1A, V5B, B1
# ═══════════════════════════════════════════

## T13.1 — V2B TD-Learning
```
PARAMETRES: gamma=0.9, alpha=0.1 (lignes 5344-5345), bonus_max=0.1 (ligne 5359)

SETUP: branche accedee 3x. A chaque acces, les concepts de la session matchent la branche.
APPEL: _update_usefulness avec TD-learning

METRIQUES:
  □ usefulness augmente a chaque acces (reward positif)
  □ La formule Bellman: delta = reward + gamma*V(next) - V(current)
  □ usefulness clampe dans [0, 1] (ligne 5360)
  □ Le bonus TD dans le scoring boot est dans [0, 0.1]
```

## T13.2 — V1A Coupled Oscillator
```
PARAMETRES: coupling_step=0.02, bonus dans [-0.02, +0.02] (ligne 2515-2517)

SETUP: 2 branches avec tags qui co-occurrent fortement dans le mycelium
APPEL: scoring avec V1A

METRIQUES:
  □ Bonus V1A dans [-0.02, +0.02]
  □ Branches couplees (tags lies) → bonus positif
  □ Branches decouplees → bonus ≈ 0
  □ L'impact est FAIBLE (+-0.02 max) — documenter si ca change le classement ou pas
```

## T13.3 — V5B Cross-Inhibition
```
PARAMETRES: _beta_inhib=0.05, _K_inhib=1.0, dt=0.1 (lignes 2529-2547)

SETUP: 3 branches avec scores initiaux [0.8, 0.75, 0.3]
  Les 2 premieres sont similaires (se concurrencent).

APPEL: V5B Lotka-Volterra
METRIQUES:
  □ La plus forte (0.8) gagne: son score monte ou reste
  □ La concurrente (0.75) perd: son score baisse
  □ La differente (0.3) n'est pas touchee
  □ floor = 0.001 (ligne 2548): aucun score ne descend a 0
```

## T13.4 — B1 Reconsolidation
```
PARAMETRES: recall < 0.3, age > 7 jours, lines > 3 (ligne 605-611)

SETUP: branche avec recall=0.2, age=14 jours, 20 lignes

APPEL: reconsolidation at read time
METRIQUES:
  □ La branche est re-compressée (L10+L11 appliques)
  □ Nombre de lignes apres < nombre de lignes avant
  □ Les faits tagges sont preserves
  □ PIEGE: branche avec recall=0.5 (trop haute) → PAS re-compressée
  □ PIEGE: branche avec 2 lignes (trop courte) → PAS re-compressée
```

---

# ═══════════════════════════════════════════
# CATEGORIE 14 — P20c VIRTUAL BRANCHES + V8B ACTIVE SENSING
# ═══════════════════════════════════════════

## T14.1 — P20c Virtual Branches
```
PARAMETRES: MAX_VIRTUAL=3, WEIGHT_FACTOR=0.5 (lignes 2069-2071)

SETUP: 2 repos dans repos.json. Repo B a des branches avec du contenu pertinent a la query.

APPEL: boot("relevant query", repo_path=TEMP_REPO)
METRIQUES:
  □ Des branches de repo B apparaissent comme "virtuelles" (read-only)
  □ Leur poids est 0.5x (WEIGHT_FACTOR)
  □ Max 3 branches virtuelles chargees (MAX_VIRTUAL)
  □ Les branches virtuelles ne sont PAS modifiees (read-only)
```

## T14.2 — V8B Active Sensing
```
APPEL: le scoring avec V8B actif
METRIQUES:
  □ V8B booste les branches qui apportent le plus d'INFORMATION nouvelle
  □ Les branches redondantes (deja couvertes par d'autres) sont penalisees
  □ Documenter le bonus effectif et son impact sur l'ordre
```

---

# ═══════════════════════════════════════════
# RESUME FINAL
# ═══════════════════════════════════════════

| Cat | Tests | Quoi |
|-----|-------|------|
| 1  | 11 | Compression L0-L11 avec ratios et fact preservation |
| 2  | 7  | Filtres P17-P38 avec patterns specifiques |
| 3  | 2  | Tagging P14 scores + C7 contradiction |
| 4  | 13 | Mycelium S1-S3, NCD, spreading, V3A, B2, B3, P20 |
| 5  | 9  | Tree R4, V9A+, V9B, P16, P19, P34, P40, B7 |
| 6  | 5  | Boot R7, P15, P22, P23, P37 avec scores |
| 7  | 4  | Formules Ebbinghaus, A1, A2, V4B avec calculs exacts |
| 8  | 6  | Pruning I1-I3, Sleep, Dreams H1-H3 |
| 9  | 3  | Emotional V6A, V6B, V10B |
| 10 | 6  | Scoring V5A, V7B, V11B, B4-B6 avec parametres |
| 11 | 3  | Pipeline end-to-end feed+compress+grow |
| 12 | 6  | Edge cases: cold start, corrupt, perf, unicode, lock |
| 13 | 4  | Integration V2B, V1A, V5B, B1 |
| 14 | 2  | Virtual branches P20c + Active Sensing V8B |
| **TOTAL** | **81** | |

Chaque test a:
- Des DONNEES specifiques (pas "du texte")
- Des METRIQUES avec des CHIFFRES (pas "ca marche")
- Des PIEGES pour detecter les faux positifs
- Les PARAMETRES exacts du code avec numeros de ligne
- Un VERDICT clair: PASS/FAIL/SKIP

## A LA FIN

1. Generer `tests/RESULTS_BATTERY_V2.md` avec tous les resultats
2. Compter: X PASS / Y FAIL / Z SKIP
3. Pour chaque FAIL: root cause + ligne du code fautive
4. Pour chaque SKIP: raison (API key? lib manquante?)
5. Temps total de la batterie
6. Les 3 bugs les plus critiques trouves (s'il y en a)
