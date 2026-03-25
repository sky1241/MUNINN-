# BATTLEPLAN — Scanner de Securite Muninn

## Concept
Transformer Muninn en scanner de securite intelligent. Pas un concurrent de Snyk/SonarQube. Un scanner qui utilise la memoire, le graphe, et la propagation epidemiologique pour trouver les failles plus vite et plus intelligemment.

## Architecture
Le scanner n'est PAS un nouveau produit. C'est une extension de Muninn:
1. Le Cube scanne le repo, detecte le langage, construit le graphe de dependances
2. Muninn charge la branche "bible_<langage>" dans le contexte (comprimee)
3. Le LLM (Haiku — pas Opus, trop cher pour du volume) lit le code avec la bible en memoire
4. Le graphe de dependances dit ou regarder en priorite (propagation epidemio)
5. Triple passe: LLM ratisse large → regex deterministes sur TOUT le code → AST confirme les complexes
6. Ce qui passe 2+ passes = flag confirme. Ce qui passe qu'une seule = maybe.
7. Mode degrade: si API LLM down, passes regex + AST tournent quand meme. Le scanner marche sans LLM, juste moins bien.

## La Bible des Bugs
Index comprime de toutes les failles connues, organisee par langage.

### Sources (tout est public et gratuit)
- **CWE (Common Weakness Enumeration)**: 933 types de failles. La taxonomie de reference. https://cwe.mitre.org/
- **OWASP Top 10 + Testing Guide**: patterns d'attaque par categorie. https://owasp.org/
- **CVE Database (NVD)**: ~250K entrees, filtrer par pertinence code (pas infra). https://nvd.nist.gov/
- **Semgrep Rules (open source)**: ~3000 regles, 30+ langages. https://github.com/semgrep/semgrep-rules
- **CodeQL Queries (GitHub)**: regles de detection par langage. https://github.com/github/codeql
- **Bandit (Python)**: regles specifiques Python. https://github.com/PyCQA/bandit
- **GoSec (Go)**: regles specifiques Go. https://github.com/securego/gosec
- **ESLint Security (JS/TS)**: plugin securite. https://github.com/eslint-community/eslint-plugin-security

### Structure de la Bible
```
bible/
  go.mn          — bugs Go comprime (~2000 tokens)
  python.mn      — bugs Python comprime
  javascript.mn  — bugs JS/TS comprime
  rust.mn        — bugs Rust comprime
  java.mn        — bugs Java comprime
  c_cpp.mn       — bugs C/C++ comprime
  sql.mn         — bugs SQL/injection comprime
  config.mn      — bugs config (docker-compose ports, nginx headers, .env, yaml secrets)
  universal.mn   — patterns cross-langage (secrets, crypto, auth)
```

Chaque fichier .mn = bible comprimee par Muninn. Le LLM charge la branche du langage detecte + universal.mn (TOUJOURS) + config.mn si fichiers config detectes.

MULTI-LANGAGE: un repo peut avoir Python + JS + Go. Le Cube detecte le langage PAR FICHIER. Chaque fichier est scanne avec la bible de SON langage. Le LLM charge la bible du langage courant, pas toutes.

### Contenu par branche (exemple Go)
```
Page 1: Injection (SQL, command, LDAP, XSS)
Page 2: Race conditions (goroutines, channels, mutex)
Page 3: Memory (buffer overflow, nil pointer, use-after-free)
Page 4: Crypto (weak hash, hardcoded keys, bad random)
Page 5: Auth (broken access control, missing checks, privilege escalation)
Page 6: Input validation (path traversal, SSRF, open redirect)
Page 7: Error handling (ignored errors, info leak in errors)
Page 8: Dependencies (known CVE in go.mod imports)
```

### Format interne (pour le LLM, PAS pour un humain)
Pas verbeux. Pas de descriptions. Juste ce que le LLM a besoin:
```
[INJ-SQL] sev:CRIT | pattern: string concat in query | regex:python="execute\(.+%|execute\(.+\+|execute\(.+format" regex:java="Statement.+execute.+\+" regex:go="fmt.Sprintf.+SELECT|Exec\(.+\+" | fix: parameterized | CWE-89
[INJ-CMD] sev:CRIT | pattern: os.exec with user input | regex:python="subprocess\.(call|run|Popen)\(.+input|os\.system\(" regex:go="exec\.Command\(.+\+" | fix: allowlist | CWE-78
[RACE-01] sev:HIGH | pattern: shared var no mutex | regex:go="go func.+\w+\s*=" | fix: sync.Mutex | CWE-362
```
Comprime par Muninn, ca devient encore plus dense.

## Modele Epidemiologique

### Analogie
- Fichier = cellule
- Faille = infection
- Dependance = vecteur de transmission
- R0 = nombre de fichiers qui dependent du fichier infecte
- Patient zero = fichier source de la faille
- Propagation = les fichiers qui importent/utilisent le code vulnerable

### Maths
- **SIR Model** (Susceptible-Infected-Recovered): chaque fichier est S, I ou R
- **R0 = degre sortant du noeud dans le graphe de dependances**
- **Centralite**: deux metriques combinées:
  - **Degree centrality** (nombre de connexions) → trouve les hubs (fichiers tres importes)
  - **Betweenness centrality** (nombre de plus courts chemins qui passent par le noeud) → trouve les ponts (fichiers qui connectent deux clusters). ATTENTION: n'existe PAS encore dans cube.py, a implementer dans B-SCAN-04 (algo de Brandes, O(n*m)).
  - Un fichier peut etre hub OU pont OU les deux. Les deux sont critiques mais pour des raisons differentes.
- **Laplacien du graphe** (deja dans le Cube, cube.py:2704) → detecte les clusters isoles vs connectes
- **Cheeger bound** (deja dans le Cube, cube.py:2760) → identifie les goulots d'etranglement
- **Seuil epidemique** (Pastor-Satorras & Vespignani 2001): λ_c = <k> / <k²>. Si le graphe est scale-free, λ_c → 0 = toute faille se propage. <k> et <k²> existent deja dans cube.py:2015-2025.
- **Seuil de percolation** (Molloy & Reed 1995): p_c = 1 / (κ - 1), κ = <k²>/<k>. Au-dela de p_c, le repo entier est compromis.
- **DebtRank** (Battiston 2012): propagation d'impact systemique. h_i(t+1) = min(1, h_i(t) + Σ W_ji·h_j(t)·(1-h_j(t-1))). Mesure l'IMPACT, pas juste la distance.
- **Heat Kernel** (Kondor & Lafferty 2002): u(t) = exp(-t·L) · u(0). Propagation EXACTE via Laplacien. Remplace le BFS par une diffusion probabiliste.
- **Goldbeter-Koshland switch** (1981): score = x^n / (K^n + x^n). Scoring NON-LINEAIRE — 5 deps = LOW, 15 deps = CRIT, le basculement est un cliff, pas une rampe.
- **Free Energy surprise** (Friston 2010): fichier "surprenant" = structurellement different de ses voisins. Utilise NCD (deja dans cube.py:1544) pour mesurer la distance. Detecte les vulns par la STRUCTURE, pas le contenu.
- **Influence Minimization** (Kempe-Kleinberg-Tardos 2003, inverse): greedy (1-1/e)-optimal pour trouver les k fichiers a PATCHER pour tuer la propagation.
- **MAPK cascade amplification** (Huang & Ferrell 1996): chaque couche de dependance MULTIPLIE le risque. n_eff ≈ n₁ × n₂ × ... × n_L. Une faille LOW qui traverse 4 couches → potentiellement CRIT.
- **Competing Epidemics** (Prakash 2012): quand 2+ failles se propagent en meme temps, celle avec β·λ₁(A)/δ le plus grand gagne. Sert a prioriser quel patch en premier.

### Priorite de scan (formule composite)
Remplace l'ancien `R0 * centralite * temperature` par un score multi-signal:
```
priority(f) = (
    0.25 * goldbeter(R0(f), K=10, n=4)     # switch non-lineaire sur le R0
    + 0.20 * free_energy_surprise(f)         # anomalie structurelle
    + 0.20 * betweenness(f)                  # fichier-pont
    + 0.20 * temperature(f)                  # chaud = modifie souvent
    + 0.15 * cheeger_bottleneck(f)           # goulot d'etranglement
)

goldbeter(x, K, n) = x^n / (K^n + x^n)     # Hill function
free_energy_surprise(f) = |mean_NCD(f, voisins) - mean_NCD_global| / std_NCD_global
```

### Propagation (DebtRank + Heat Kernel)
Deux modes complementaires:
1. **DebtRank** (mode par defaut, pure Python): propagation iterative avec importance ponderee. Distingue "50 fichiers de tests touches" de "3 fichiers core touches".
2. **Heat Kernel** (si numpy disponible): propagation exacte via exponentielle du Laplacien. Plus precis, plus lent.

### En pratique
1. Cube construit le graphe
2. B-SCAN-04 calcule R0, degree, betweenness, seuil epidemique, seuil de percolation
3. B-SCAN-05 trie par score composite (Goldbeter + Free Energy + betweenness + temperature + Cheeger)
4. Scan les noeuds critiques en premier (top 20%)
5. Si infection trouvee → DebtRank ou Heat Kernel sur le graphe → blast radius probabiliste
6. Influence Minimization → recommandation "quels fichiers patcher en priorite"
7. Pas besoin de tout scanner. 20% des fichiers couvrent 80% du risque.

## Pipeline de Scan

```
ETAPE 1: Cache check (B-SCAN-12)
  → SHA-256 par fichier vs scan precedent
  → delta: fichiers modifies + nouveaux seulement (sauf --full)

ETAPE 2: Cube scanne le repo
  → langage detecte
  → graphe de dependances construit
  → R0 (degre sortant) + centralite (betweenness + degree) par noeud

ETAPE 3: Muninn charge bible
  → bible_<langage>.mn + universal.mn (TOUJOURS les deux)
  → budget: 5000-10000 tokens

ETAPE 4 (en parallele):
  4a: LLM passe 1 (ratissage large, mode degrade: skip si API down)
    → lit les fichiers haute priorite (top 20% R0, min 10 fichiers)
    → flag les patterns suspects
  4b: Regex passe 2 (filet de securite, tourne TOUJOURS)
    → regex par langage + universal sur TOUT le code (ou delta)
    → inclut les 24+ secret patterns existants de muninn.py

ETAPE 5: AST passe 3 (confirmation)
  → sur l'union des suspects (4a + 4b)
  → elimine les faux positifs (prepared statements, sanitized inputs)
  → V1: intra-fonction. V2: cross-function taint.

ETAPE 6: Merge + Dedup
  → union des 3 passes, dedup par fichier+ligne
  → confiance: confirmed (2+ passes) / maybe (1 passe) / fp (AST infirme)
  → gere le cas ou 4a est vide (mode degrade)

ETAPE 7: Propagation
  → pour chaque flag confirme, BFS sur le graphe
  → blast radius par faille

ETAPE 8: Rapport + exit code
  → failles confirmees + localisation + fix propose
  → propagation map
  → flags: couverture incomplete si imports dynamiques detectes
  → EXIT CODE: 0=clean, 1=findings, 2=critiques
```

## Ce qui existe deja dans Muninn
- Cube: graphe de dependances, AST structurel, SHA-256, 6 langages ✓
- Secret filtering: 24+ patterns ✓
- Mycelium: co-occurrences, spreading activation ✓
- Compression: bible → branche .mn ✓
- Laplacien, Cheeger, centralite: dans cube.py ✓
- Triple passe LLM + regex + filtre: pattern existant dans le pipeline ✓

## Ce qui existe PAS encore (attention)
- Taint analysis / data flow cross-function (le Cube fait de l'AST structurel, PAS du security taint tracking)
- Regex de detection par langage (faut les ecrire ou les importer de Semgrep)
- Cache de resultats de scan (faut definir le format de stockage)

## Filets de securite (anti faux-negatifs)

Le LLM rate des trucs. C'est un fait. Le pipeline doit compenser:

### Triple passe, pas double
1. **LLM** — ratisse large sur les noeuds haute priorite (top 20%)
2. **Regex deterministes** — tournent sur TOUT le code, pas seulement les suspects LLM. Si le LLM a rate un SQL injection evident, le regex le choppe. Filet de securite incompressible.
3. **AST** — pour les patterns complexes que ni le LLM ni le regex voient (taint propagation, data flow cross-function)

### Scan incrementiel (git diff)
On rescanne PAS tout le repo a chaque run. Le Cube track deja les SHA-256 par fichier:
- Hash identique → fichier pas touche → skip
- Hash different → fichier modifie → rescan
- Nouveau fichier → scan complet
- Premier run = scan total. Runs suivants = delta seulement.
- Gain: x100 sur les runs suivants pour un repo actif.

### Dependances dynamiques (angle mort)
Le graphe du Cube voit les imports statiques. Il voit PAS:
- Reflection (Java, Go, Python)
- Dynamic imports (`importlib`, `require()` avec variable)
- Dependency injection (Spring, etc)
- Plugin systems
- Eval / exec avec string

Le R0 calcule est SOUS-ESTIME quand ces patterns existent. Le rapport DOIT inclure un flag "couverture incomplete: X fichiers utilisent des imports dynamiques" pour pas donner un faux sentiment de securite.

### Temperature du Cube = risque
Les cubes chauds (souvent modifies) sont plus dangereux. Formule de priorite mise a jour:

```
priorite = R0 * centralite * temperature
```

Un fichier modifie 50 fois en un mois avec un R0 de 30 et une centralite haute = bombe a retardement. Il passe en premier.

## Validation du scanner

### Benchmark obligatoire avant release
Tester sur des repos volontairement vulnerables:
- **OWASP WebGoat** (Java) — https://github.com/WebGoat/WebGoat
- **OWASP Juice Shop** (JS/TS) — https://github.com/juice-shop/juice-shop
- **DVWA** (PHP) — https://github.com/digininja/DVWA
- **Damn Vulnerable Python App** — https://github.com/anxolerd/dvpwa
- **Go Vulnerable** — https://github.com/Contrast-Security-OSS/go-test-bench

### Test de la bible comprimee
La compression peut bouffer des patterns critiques. Test:
1. Bible brute sur repo vulnerable → liste de failles trouvees (reference)
2. Bible comprimee sur meme repo → liste de failles trouvees
3. Diff. Si la comprimee rate des trucs que la brute trouve → compression trop aggressive sur cette branche. Ajuster.

Seuil acceptable: 0% de perte sur les failles critiques. Tolerance maybe sur les low/info.

## BRIQUES — Construction atomique

REGLE: chaque brique est independante, testable seule, assemblable apres. On code UNE brique, on la teste, on passe a la suivante. JAMAIS deux en meme temps. JAMAIS d'assemblage avant que toutes les briques soient vertes.

### B-SCAN-01: Bible Scraper
- INPUT: sources brutes (CWE XML, Semgrep YAML, OWASP markdown)
- TELECHARGE les sources automatiquement si pas presentes localement. Cache dans .muninn/scanner_sources/. Premier run = telecharge. Runs suivants = utilise le cache. Flag --refresh pour forcer re-telechargement.
- OUTPUT: fichiers .json structures par langage dans .muninn/scanner_data/bible/. Un fichier par langage + un universal.json (secrets, crypto, auth — patterns cross-langage).
- FORMAT: chaque entree = {id, severity: CRIT/HIGH/MED/LOW/INFO, pattern_description, regex_per_language: {python: "...", go: "...", ...}, fix, cwe_ref}
- TEST: le JSON parse, chaque entree a un id + severity + pattern + fix + CWE ref + au moins un regex
- DEPENDANCES: aucune. Brique isolee.

### B-SCAN-02: Bible Compressor
- INPUT: fichiers .json de B-SCAN-01 (depuis .muninn/scanner_data/bible/)
- OUTPUT: fichiers .mn dans .muninn/scanner_data/bible_mn/. Un par langage + universal.mn.
- NOTE: universal.mn se charge TOUJOURS en plus de la bible du langage detecte.
- TEST: decompresser et verifier que 100% des patterns critiques (sev=CRIT) sont presents
- DEPENDANCES: B-SCAN-01 + Muninn compression existante (compress_file())

### B-SCAN-03: Bible Validator
- INPUT: bible .mn comprimee + repo vulnerable connu (WebGoat, Juice Shop, etc)
- OUTPUT: rapport de couverture (failles trouvees par bible brute vs comprimee)
- TEST OFFLINE: inclure dans tests/scanner/fixtures/ un mini repo vulnerable synthetique (3-5 fichiers Python/JS avec des failles connues injectees). PAS besoin de cloner WebGoat pour les tests unitaires. Les repos externes c'est pour la validation finale manuelle.
- TEST: 0% de perte sur critiques. Si perte → ajuster compression.
- DEPENDANCES: B-SCAN-01, B-SCAN-02

### B-SCAN-04: R0 Calculator + Graph Metrics
- INPUT: graphe de dependances du Cube (build_neighbor_graph() + parse_dependencies())
- OUTPUT: dictionnaire {fichier: {R0: int, degree_centrality: float, betweenness_centrality: float, temperature: float, cheeger_bottleneck: bool}}
- OUTPUT GLOBAL: {lambda_c: float, percolation_pc: float, regime: "local"|"systemic"}
- NOTE: degree = nb connexions directes (hubs). betweenness = nb plus courts chemins qui passent par le noeud (ponts). Les deux sont utiles.
- **BETWEENNESS**: algorithme de Brandes (2001), O(n*m). N'EXISTE PAS dans cube.py, a coder from scratch. Pour 5000 fichiers × 45K edges ≈ 2-5 secondes.
- **SEUIL EPIDEMIQUE** (Pastor-Satorras & Vespignani 2001): λ_c = <k>/<k²>. <k> et <k²> existent deja (cube.py:2015-2025). Si λ_c < 0.05 → regime "systemic" = toute faille se propage. Sinon → regime "local".
- **SEUIL PERCOLATION** (Molloy & Reed 1995): κ = <k²>/<k>, p_c = 1/(κ-1). Pourcentage critique de fichiers infectes au-dela duquel le repo est condamne.
- TEST: sur un repo connu, verifier que les hubs ont le degree le plus haut et que les fichiers-ponts ont le betweenness le plus haut. Verifier lambda_c et p_c sur graphe scale-free vs graphe regulier.
- DEPENDANCES: Cube graphe existant (build_neighbor_graph, parse_dependencies). Brique isolee cote scanner.
- REF: Pastor-Satorras & Vespignani "Epidemic spreading in scale-free networks" PRL 2001 (~8000 citations). Molloy & Reed "A critical point for random graphs" 1995. Brandes "A faster algorithm for betweenness centrality" 2001.

### B-SCAN-05: Priority Ranker (Carmack scoring)
- INPUT: output de B-SCAN-04 + NCD depuis Cube (cube.py:1544)
- OUTPUT: liste ordonnee de fichiers par score composite
- **FORMULE COMPOSITE** (remplace l'ancien R0 * centralite * temperature):
```
priority(f) = 0.25 * goldbeter(R0, K=10, n=4)
            + 0.20 * free_energy_surprise(f)
            + 0.20 * betweenness_norm(f)
            + 0.20 * temperature(f)
            + 0.15 * cheeger_bottleneck(f)
```
- **GOLDBETER-KOSHLAND** (1981): Hill function `x^n / (K^n + x^n)`. Switch non-lineaire. K=10 = seuil de basculement a 10 dependances. n=4 = pente du cliff. En dessous de K = score faible. Au-dessus = score sature a 1.0.
- **FREE ENERGY SURPRISE** (Friston 2010): pour chaque fichier, calculer la distance NCD moyenne a ses voisins dans le graphe. Un fichier structurellement different de ses voisins = surprenant = suspect. `surprise(f) = |mean_NCD(f, neighbors) - global_mean| / global_std`. Utilise compute_ncd() de cube.py:1544 (zlib, stdlib).
- **MAPK AMPLIFICATION** (Huang & Ferrell 1996): bonus pour les fichiers deep dans la chaine de dependances. `depth_bonus = 1.0 + 0.1 * max_dependency_depth(f)`. Un fichier LOW a profondeur 4 peut valoir un HIGH a profondeur 1.
- TEST: le fichier le plus modifie, le plus importe, ET le plus surprenant est en haut. Un fichier isole avec zero import est en bas meme s'il est chaud.
- DEPENDANCES: B-SCAN-04
- REF: Goldbeter & Koshland PNAS 1981 (~3000 citations). Friston "The free-energy principle" Nature Reviews Neuroscience 2010 (~7000 citations). Huang & Ferrell PNAS 1996 "MAPK cascades" (~2000 citations).

### B-SCAN-06: LLM Scanner (passe 1)
- INPUT: fichiers prioritaires (top 20% de B-SCAN-05, minimum 10 fichiers) + bible .mn (B-SCAN-02)
- OUTPUT: liste de suspects {fichier, ligne, type_faille, confiance}
- LLM: Haiku (pas Opus). Budget API: estimer avant de lancer. ~0.001$/fichier.
- RATE LIMITING: max 10 requetes/seconde. Batching: grouper les petits fichiers dans un seul prompt (jusqu'a 4K tokens par batch). Estimer le cout total AVANT de lancer et afficher a l'utilisateur.
- MODE DEGRADE: si API down, skip cette passe. Les passes regex + AST tournent sans.
- PROMPT TEMPLATE (critique, le cousin DOIT l'utiliser):
```
You are a security auditor. Below is a vulnerability bible for {language}, followed by source code.
Find ALL security vulnerabilities in the code. For each finding, output EXACTLY:
FILE:{path} LINE:{number} TYPE:{vulnerability_id} SEVERITY:{CRIT|HIGH|MED|LOW} DESC:{one-line}
If no vulnerabilities found, output: CLEAN
Do NOT explain. Do NOT add commentary. Only the format above.

=== BIBLE ===
{bible_mn_content}

=== CODE ===
{file_content}
```
- TEST: sur repo vulnerable connu, trouve au moins 80% des failles critiques
- DEPENDANCES: B-SCAN-02, B-SCAN-05

### B-SCAN-07: Regex Filters (passe 2)
- INPUT: TOUT le code du repo (ou delta si incremental via B-SCAN-12)
- OUTPUT: liste de matches {fichier, ligne, pattern_id, CWE, severity}
- NOTE: les regex sont PAR LANGAGE. B-SCAN-01 fournit regex_per_language. Cette brique selectionne les regex du bon langage (detecte par le Cube).
- TEST: sur repo vulnerable connu, trouve 100% des patterns regex connus
- DEPENDANCES: B-SCAN-01 (les patterns bruts avec regex par langage). Brique isolee du LLM.

### B-SCAN-08: AST Analyzer (passe 3)
- INPUT: fichiers suspects (union LLM + regex)
- OUTPUT: confirmations/infirmations avec data flow analysis
- TEST: elimine les faux positifs evidents (prepared statements, sanitized inputs)
- ATTENTION: c'est la brique la plus dure. Le Cube fait de l'AST structurel (arbre syntaxique). Le taint analysis (suivre une variable user-input a travers les fonctions jusqu'au sink dangereux) c'est un niveau au-dessus. V1: se limiter a l'intra-fonction (variable definie et utilisee dans la meme fonction). V2: cross-function taint.
- DEPENDANCES: Cube AST existant. Mais necessite extension pour taint tracking.

### B-SCAN-09: Merger + Dedup
- INPUT: outputs de B-SCAN-06 + B-SCAN-07 + B-SCAN-08. B-SCAN-06 PEUT ETRE VIDE (mode degrade, API down). Le merger gere: si 06 est None/vide, merge seulement 07+08.
- OUTPUT: liste unifiee {fichier, ligne, type, severity, confiance: confirmed/maybe/fp, sources: [llm/regex/ast]}
- REGLE confiance: confirmed = 2+ sources concordent. maybe = 1 source seule. fp = AST infirme explicitement.
- TEST: pas de doublons (dedup par fichier+ligne+type), chaque faille a au moins une source et un niveau de confiance. Tester aussi le cas 06=vide.
- DEPENDANCES: B-SCAN-06 (optionnel), B-SCAN-07, B-SCAN-08

### B-SCAN-10: Propagation Engine (DebtRank + Heat Kernel)
- INPUT: failles confirmees de B-SCAN-09 + graphe de dependances + output B-SCAN-04 (importance par fichier)
- OUTPUT: blast radius par faille {faille_id, fichiers_impactes: {fichier: proba_impact}, systemic_loss: float}
- **MODE 1 — DebtRank** (Battiston 2012, mode par defaut, pure Python):
```python
# h_i = stress du fichier i (0=sain, 1=mort)
# W_ji = poids de la dependance j→i (normalise)
# v_i = importance du fichier (LOC * temperature * degree / max)
h[infected] = 1.0  # patient zero
for t in range(max_rounds):  # converge en 5-10 rounds
    for i in all_files:
        if h[i] < 1.0:
            h[i] = min(1.0, h[i] + sum(W[j][i] * h[j] * (1 - h_prev[j]) for j in neighbors))
systemic_loss = sum(h[i] * v[i] for i in all_files)  # perte totale ponderee
```
  Distingue "50 tests touches" (v faible) de "3 fichiers auth touches" (v enorme).
- **MODE 2 — Heat Kernel** (si numpy/scipy dispo):
```python
# L = Laplacien (existe dans cube.py:2704)
# u(0) = vecteur initial (1.0 pour fichier infecte, 0.0 sinon)
# u(t) = expm(-t * L) @ u(0)  # scipy.sparse.linalg.expm_multiply
# u(t)[i] = proba que le fichier i soit impacte au temps t
```
  Plus precis que DebtRank, necessite scipy. Fallback → DebtRank.
- **COMPETING EPIDEMICS** (Prakash 2012): quand 2+ failles trouvees, celle avec le plus grand β·λ₁(A)/δ se propage en premier. λ₁ = plus grande eigenvalue de la matrice d'adjacence (spectral radius). Sert a ordonner les patches.
- ATTENTION CYCLES: DebtRank converge naturellement (h capped a 1.0). Heat Kernel aussi (exponentielle decroissante). Pas de visited set necessaire.
- TEST: sur graphe connu, verifier que DebtRank et Heat Kernel donnent des blast radius coherents. Fichier core (LOC=5000, degree=30) doit avoir impact >> fichier test (LOC=100, degree=2). Tester graphe avec cycle.
- DEPENDANCES: B-SCAN-09, B-SCAN-04 (pour importance v_i), Cube graphe existant
- REF: Battiston et al. "DebtRank: Too Central to Fail?" Scientific Reports 2012 (~800 citations). arXiv: 1301.6115, 1504.01857, 1512.04460, 1503.00621. Prakash et al. "Winner Takes All" ICDM 2012. Kondor & Lafferty "Diffusion Kernels on Graphs" ICML 2002.

### B-SCAN-11: Dynamic Import Detector
- INPUT: code source
- OUTPUT: liste de fichiers avec imports dynamiques + flag couverture incomplete
- TEST: detecte eval, exec, importlib, require(variable), reflection, DI containers
- DEPENDANCES: aucune. Brique isolee. Regex simple.

### B-SCAN-12: Incremental Cache
- INPUT: SHA-256 par fichier (Cube existant) + resultats scan precedent
- OUTPUT: liste de fichiers a rescanner (delta)
- STOCKAGE: .muninn/scan_cache.json = {fichier: {sha256, last_scan_date, findings[]}}
- TEST: modifier un fichier, verifier qu'il est dans le delta. Ne pas modifier, verifier qu'il est skip.
- DEPENDANCES: Cube SHA-256 existant. Brique isolee.

### B-SCAN-13: Report Generator (avec metriques epidemio + patch plan)
- INPUT: output de B-SCAN-09 + B-SCAN-10 + B-SCAN-11 + B-SCAN-04 (metriques globales)
- OUTPUT: rapport lisible (markdown + json) avec:
  - Failles + localisation + fix propose + blast radius (DebtRank)
  - **SECTION EPIDEMIO**: regime du repo (local/systemic), seuil epidemique λ_c, seuil de percolation p_c, % fichiers infectes vs p_c
  - **SECTION PATCH PLAN** (Influence Minimization, Kempe-Kleinberg-Tardos 2003 inverse):
    - Liste ordonnee des k fichiers a patcher pour maximiser la reduction de propagation
    - Algorithme greedy: a chaque etape, choisir le fichier dont le patch reduit le plus le systemic_loss (DebtRank avec ce fichier "immunise")
    - Complexite O(k * n * propagation_rounds). Pour k=10 patches, n=5000 fichiers → ~5 secondes.
  - **SECTION AMPLIFICATION** (MAPK cascade): failles LOW qui traversent 3+ couches de dependances → flag "amplified risk"
  - Propagation map, couverture, flags imports dynamiques
- EXIT CODE: 0 = aucune faille. 1 = failles non-critiques. 2 = failles critiques. (pour CI/CD futur)
- TEST: le rapport est parsable, chaque faille a localisation + fix + blast radius. Section epidemio presente avec lambda_c et p_c. Patch plan ordonne. Verifier les 3 exit codes.
- DEPENDANCES: B-SCAN-09, B-SCAN-10, B-SCAN-11, B-SCAN-04
- REF: Kempe, Kleinberg & Tardos "Maximizing the Spread of Influence" KDD 2003 (~12000 citations). Huang & Ferrell PNAS 1996.

### B-SCAN-14: Orchestrator
- INPUT: chemin du repo + options (--full | --incremental | --dry-run | --no-llm)
- OUTPUT: rapport final
- ROLE: enchaine B-SCAN-12 (cache) → 04 → 05 → 06+07 en parallele → 08 → 09 → 10 → 11 → 13. Charge la bible (02).
- --dry-run: montre ce qui serait scanne sans scanner
- --no-llm: mode degrade, passes regex + AST seulement
- --incremental: delta seulement (defaut apres premier run)
- --full: force rescan total
- TEST: lancer sur un repo vulnerable, obtenir un rapport complet sans intervention
- DEPENDANCES: TOUTES les briques. C'est la DERNIERE brique. On l'assemble quand tout est vert.

### Ordre de construction
```
Phase 1 — Data (pas de code scanner, juste les donnees)
  B-SCAN-01 → B-SCAN-02 → B-SCAN-03

Phase 2 — Briques isolees (testables independamment)
  B-SCAN-04, B-SCAN-07, B-SCAN-08, B-SCAN-11, B-SCAN-12
  (toutes en parallele, aucune dependance entre elles)

Phase 3 — Briques dependantes
  B-SCAN-05 (besoin de 04)
  B-SCAN-06 (besoin de 02 + 05)

Phase 4 — Assemblage
  B-SCAN-09 (merge)
  B-SCAN-10 (propagation)
  B-SCAN-13 (rapport)

Phase 5 — Orchestrator
  B-SCAN-14 (tout ensemble, la derniere)
```

### Regle pour le LLM qui construit
- UNE brique par session
- Chaque brique a son propre fichier dans engine/core/scanner/
- Chaque brique a ses propres tests dans tests/scanner/
- On teste AVANT de passer a la suivante
- Si un test echoue on corrige AVANT de continuer
- L'orchestrator c'est la FIN pas le DEBUT
- Si t'as envie d'assembler avant que tout soit vert: NON
- Apres chaque brique: `python forge.py` + `python forge.py --diff`. ZERO regression toleree.
- Chaque scan doit LOGGER: debut, fin, duree, nb fichiers scannes, nb findings par severite. Fichier log: .muninn/scan_log.jsonl (append-only, comme vault_audit.jsonl)

## INTEGRATION MUNINN — Ou ca va dans le code

### Structure fichiers (a creer)
```
engine/
  core/
    scanner/              ← NOUVEAU dossier
      __init__.py
      bible_scraper.py    ← B-SCAN-01
      bible_compressor.py ← B-SCAN-02
      bible_validator.py  ← B-SCAN-03
      r0_calculator.py    ← B-SCAN-04
      priority_ranker.py  ← B-SCAN-05
      llm_scanner.py      ← B-SCAN-06
      regex_filters.py    ← B-SCAN-07
      ast_analyzer.py     ← B-SCAN-08
      merger.py           ← B-SCAN-09
      propagation.py      ← B-SCAN-10
      dynamic_detector.py ← B-SCAN-11
      cache.py            ← B-SCAN-12
      report.py           ← B-SCAN-13
      orchestrator.py     ← B-SCAN-14
tests/
  scanner/                ← NOUVEAU dossier
    __init__.py           ← OBLIGATOIRE pour pytest discovery
    test_scan_b01.py      ← tests B-SCAN-01
    test_scan_b02.py      ← tests B-SCAN-02
    ...
    test_scan_b14.py      ← tests B-SCAN-14

.muninn/                  ← runtime data (PAS dans le package pip)
  scanner_sources/        ← sources CWE/Semgrep telechargees (cache)
  scanner_data/
    bible/                ← bibles .json brutes par langage
    bible_mn/             ← bibles .mn comprimees
  scan_cache.json         ← cache incrementiel (B-SCAN-12)
```

### Conventions de code Muninn (RESPECTER)
- **Dataclasses** pour toutes les structures de donnees:
```python
@dataclass
class Finding:
    file: str
    line: int
    type: str
    severity: str  # CRIT/HIGH/MED/LOW/INFO
    cwe: str
    confidence: str  # confirmed/maybe/fp
    source: str  # llm/regex/ast
    fix: str = ""
    blast_radius: list[str] = field(default_factory=list)
```
- **snake_case** pour fonctions, **PascalCase** pour classes, **UPPER_SNAKE** pour constantes
- **Fonctions privees**: `_leading_underscore`
- **Imports triple fallback** (comme cube.py):
```python
try:
    from engine.core.scanner.bible_scraper import scrape_bible
except ImportError:
    try:
        from .bible_scraper import scrape_bible
    except ImportError:
        from bible_scraper import scrape_bible
```
- **Zero dependances externes**. Stdlib Python only. Sauf pour le LLM (anthropic, optionnel).
- **SQLite avec WAL** si besoin de persistence (pattern de CubeStore dans cube.py)
- **Pure Python 3.10+**

### Ce qui existe et que tu REUTILISES (pas recoder)
- `cube.py:scan_repo()` → scan les fichiers, detecte le langage. Tu l'appelles, tu le recodes PAS.
- `cube.py:ScannedFile` → dataclass fichier scanne. Tu l'utilises.
- `cube.py:build_neighbor_graph()` → graphe de dependances. C'est ton graphe pour le R0.
- `cube.py:parse_dependencies()` → extrait les imports. C'est tes aretes.
- `cube.py:Cube.sha256` → hash par fichier. C'est ton cache incrementiel.
- `cube.py:Cube.temperature` → temperature par cube. C'est ton facteur de risque.
- `cube.py:extract_ast_hints()` → AST structurel. Base pour B-SCAN-08 (mais PAS suffisant pour taint).
- `cube.py:CubeStore` → pattern SQLite. Copie-le pour scan_cache.
- `muninn.py:_SECRET_PATTERNS` → 24+ regex secrets. Integre-les dans B-SCAN-07.
- `muninn.py:compress_file()` → compression. Pour creer les bibles .mn.

### Enregistrement CLI
Dans `muninn.py:main()` (ligne ~7122), ajouter `"security-scan"` dans la liste `choices` de argparse.
Ajouter le bloc:
```python
elif args.command == "security-scan":
    from engine.core.scanner.orchestrator import run_scan
    run_scan(repo=args.repo or args.file or ".",
             full=args.full,
             no_llm=args.no_llm,
             dry_run=args.dry_run)
```

## TESTS — Regles absolues

### Chaque brique a ses propres tests
- Fichier: `tests/scanner/test_scan_b{NN}.py`
- Convention: classe `TestBSCAN{NN}{NomBrique}` avec methodes `test_<cas>`
- Framework: **pytest** (comme tout Muninn)
- Fixtures: `@pytest.fixture` avec `tmp_path` pour les fichiers temporaires

### Pattern de test (copie ca)
```python
import pytest
from engine.core.scanner.bible_scraper import scrape_cwe, scrape_semgrep

class TestBSCAN01BibleScraper:
    """B-SCAN-01: Bible Scraper — extrait les patterns de failles par langage."""

    @pytest.fixture
    def sample_cwe_xml(self, tmp_path):
        """Mini CWE XML pour test."""
        xml = tmp_path / "cwe_sample.xml"
        xml.write_text('<...>')
        return xml

    def test_scrape_produces_valid_json(self, sample_cwe_xml):
        result = scrape_cwe(sample_cwe_xml)
        assert isinstance(result, dict)
        for lang, entries in result.items():
            for entry in entries:
                assert "id" in entry
                assert "severity" in entry
                assert "pattern" in entry
                assert "cwe" in entry

    def test_each_entry_has_at_least_one_regex(self, sample_cwe_xml):
        result = scrape_cwe(sample_cwe_xml)
        for lang, entries in result.items():
            for entry in entries:
                assert "regex" in entry and len(entry["regex"]) > 0
```

### Forge — validation obligatoire
Apres chaque brique, lancer:
```bash
cd C:\Users\ludov\MUNINN-
python forge.py                    # tous les tests passent
python forge.py --diff             # pas de regression
```

**REGLE**: si forge.py montre un FAIL ou une regression, tu corriges AVANT de passer a la brique suivante. Pas de compromis. Pas de skip. Pas de "on verra plus tard".

### Tests sur repos vulnerables (B-SCAN-03 et validation finale)
Cloner dans un dossier temporaire:
```bash
git clone https://github.com/juice-shop/juice-shop /tmp/test_vuln_js
git clone https://github.com/WebGoat/WebGoat /tmp/test_vuln_java
```
Lancer le scanner dessus. Comparer les resultats avec les failles connues et documentees de ces repos.

## CARMACK MOVES — Recherche Yggdrasil (2026-03-25)

Scan Yggdrasil sur 833K papiers, 69M co-occurrences, 65K concepts OpenAlex.
175 paires domaine × securite testees. Resultats: 62 trous absolus (co-occ=0), 97 quasi-trous (<5), 2 ponts forts.
Donnees brutes: docs/ygg_carmack_security.json. Outil de requete: docs/ygg_query_wt3.py.

### TIER S — Integre dans les briques (cout minimal, gain maximal)

| # | Formule | Brique | Ref | Co-occ Ygg | Cout |
|---|---------|--------|-----|-----------|------|
| 1 | Seuil epidemique λ_c = <k>/<k²> | B-SCAN-04, B-SCAN-13 | Pastor-Satorras & Vespignani PRL 2001 | epidemic×software=0 papiers. epidemic×scale-free=20 papiers | 1 ligne |
| 2 | Percolation p_c = 1/(κ-1) | B-SCAN-04, B-SCAN-13 | Molloy & Reed 1995 | percolation×software=0 papiers | 1 ligne |
| 4 | DebtRank h_i(t+1) = min(1, h_i + Σ W·h_j·(1-h_j_prev)) | B-SCAN-10 | Battiston et al. Scientific Reports 2012 | DebtRank=4 papiers (arXiv: 1301.6115, 1504.01857, 1512.04460, 1503.00621). ZERO lie au software | ~40 lignes |
| 16 | Goldbeter-Koshland x^n/(K^n+x^n) | B-SCAN-05 | Goldbeter & Koshland PNAS 1981. 1 papier Ygg (1306.1904), 24 "ultrasensitivity" | ~10 lignes |

### TIER A — Integre dans les briques (plus de boulot, gros gain)

| # | Formule | Brique | Ref | Co-occ Ygg | Cout |
|---|---------|--------|-----|-----------|------|
| 6 | Heat Kernel u(t) = exp(-tL)·u(0) | B-SCAN-10 | Kondor & Lafferty ICML 2002 | heat kernel×graph=12 papiers (1410.3168, 1312.3035). heat×security=0.00 absolu | ~30 lignes + scipy optionnel |
| 9 | Free Energy surprise (Mahalanobis/NCD) | B-SCAN-05 | Friston Nature Reviews Neuroscience 2010 | free energy×anomaly=0 papiers | ~25 lignes |
| 13 | Influence Minimization inverse greedy | B-SCAN-13 | Kempe-Kleinberg-Tardos KDD 2003 | influence×maximization=21 papiers | ~40 lignes |
| 17 | MAPK cascade amplification n_eff = Π n_i | B-SCAN-05, B-SCAN-13 | Huang & Ferrell PNAS 1996 | MAPK×cascade=3 papiers (1508.07822, q-bio/0702051, 0710.5195) | ~15 lignes |

### TIER B — V2 (utile mais pas prioritaire ou redondant)

| # | Formule | Raison report V2 | Ref |
|---|---------|------------------|-----|
| 3 | Competing Epidemics β·λ₁(A)/δ | Utile quand 2+ failles. Edge case V1. | Prakash et al. ICDM 2012 |
| 5 | Eisenberg-Noe clearing (point fixe) | Plus complexe que DebtRank, meme resultat | Eisenberg & Noe 2001. 0 papier Ygg |
| 7 | Ising T_c = J·<k²>/<k> | Redondant avec #1 (seuil epidemique) | Ising 1925. Ising×software=0 papiers |
| 8 | Fisher-KPP c* = 2√(Dr) | Cool mais impossible a calibrer sans temporel | Fisher 1937, Kolmogorov 1937 |
| 10 | Biased Competition inhibition | Redondant avec Belief Propagation + Survey Propagation existants | Desimone & Duncan 1995. 0 papier Ygg |
| 11 | Levins Metapopulation c·λ₁ > e_min | Redondant avec #2 (percolation) | Levins 1969. metapopulation×network=11 papiers |
| 12 | Island Biogeography | Redondant avec Survey Propagation filter existant | MacArthur & Wilson 1967 |
| 14 | UCB1 Bandit x̄ + c√(ln N/n) | Besoin de scan iteratif (V2) | Auer et al. 2002. bandit×security=0 papiers |
| 15 | Secretary Problem 1/e | Gain marginal. Early exit. | Dynkin 1963. 18 papiers Ygg |
| 18 | Cytokine storm feedback | Detection de regression de patch. V2. | 0 papier Ygg (arXiv=pas biomedical) |
| 19 | Receptor clustering Hill synergy | Vuln chaining LOW+LOW+LOW→CRIT. V2. | receptor×cluster×signal=1 papier (1309.0868) |

### Deserts scientifiques confirmes (trous structurels purs)

9 recherches a ZERO papiers dans 833K articles:
- `percolation + software` = 0
- `epidemic + software` = 0
- `Ising + software` = 0
- `bandit + security` = 0
- `free energy + anomaly` = 0
- `vulnerability + cascade` = 0
- `biased competition` = 0
- `Eisenberg + Noe` = 0
- `cytokine + storm` = 0

3 deserts par domaine (co-occ = 0.00 sur TOUS les concepts securite):
- **Physique statistique × Security**: Ising, percolation, heat equation, phase transition
- **Biologie cellulaire × Security**: signal transduction, apoptosis, phosphorylation, cytokine
- **Ecologie × Security**: population dynamics, metapopulation, ecological network

### Code existant reutilisable (verifie dans le code, pas assume)

| Composant | Fichier | Lignes | Dependencies | Note |
|-----------|---------|--------|-------------|------|
| Laplacien L=D-A | cube.py | 2704-2706 | numpy | Eigenvalues PAS stockees (jetees apres) |
| Cheeger λ₂ + Fiedler | cube.py | 2760-2801 | numpy | Retourne bottlenecks |
| Belief Propagation | cube.py | 2806-2853 | RIEN | Pure Python, 15 iter |
| Temperature | cube.py | 1854-1876 | RIEN | 0.4×perp + 0.4×(1-success) + 0.2×failures |
| Neighbor graph | cube.py | 939-996 | RIEN | Max 9 voisins, dict of lists |
| <k> et <k²> | cube.py | 2015-2025 | RIEN | Dans compute_gods_number |
| NCD | cube.py | 1544-1568 | zlib (stdlib) | Proxy mutual information |
| Tononi degeneracy | cube.py | 2880-2910 | zlib | Criticite vs redondance |
| Spreading activation | mycelium.py | 1003-1093 | RIEN | Pure Python |
| Blind spots (Burt) | mycelium.py | 1530-1658 | RIEN | Structural holes |
| Betweenness centrality | — | — | — | **N'EXISTE PAS. A coder (Brandes 2001).** |
| Degree centrality normalisee | — | — | — | **N'EXISTE PAS. Trivial: degree/max_degree.** |

### Outils de recherche Ygg (pour creuser plus)

Donnees brutes: `docs/ygg_carmack_security.json` (175 paires, co-occurrences, papiers)
Outil CLI: `docs/ygg_query_wt3.py` — requete directe dans WT3 (833K papiers)
```bash
python docs/ygg_query_wt3.py concept "percolation"          # trouver un concept
python docs/ygg_query_wt3.py title "DebtRank"                # chercher des papiers
python docs/ygg_query_wt3.py cooc 56807 54548                # co-occurrence Ising × Computer security
python docs/ygg_query_wt3.py hole "game theory" "vulnerability"  # trou structurel
python docs/ygg_query_wt3.py axes                            # resume complet
```
Interpreteur: C:/Users/ludov/AppData/Local/Programs/Python/Python313/python.exe
Toujours PYTHONIOENCODING=utf-8

## Pas maintenant
- GUI (osef)
- Certification ANSSI (plus tard)
- CVE database live updates (v2)
- CI/CD integration (v2)
- Multi-repo scan (v2, mais le meta-mycelium pose les bases)
