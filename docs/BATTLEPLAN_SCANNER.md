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
- **Priorite de scan = R0 * centralite * temperature**
- **Centralite**: deux metriques combinées:
  - **Degree centrality** (nombre de connexions) → trouve les hubs (fichiers tres importes)
  - **Betweenness centrality** (nombre de plus courts chemins qui passent par le noeud) → trouve les ponts (fichiers qui connectent deux clusters)
  - Un fichier peut etre hub OU pont OU les deux. Les deux sont critiques mais pour des raisons differentes.
- **Laplacien du graphe** (deja dans le Cube) → detecte les clusters isoles vs connectes
- **Cheeger bound** → identifie les goulots d'etranglement (un fichier qui connecte deux clusters = point critique, correle avec betweenness)

### En pratique
1. Cube construit le graphe
2. Calcul du R0 par noeud
3. Tri par R0 * centralite (descending)
4. Scan les noeuds critiques en premier
5. Si infection trouvee → propagation sur le graphe → scan les voisins
6. Pas besoin de tout scanner. 20% des fichiers couvrent 80% du risque.

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

### B-SCAN-04: R0 Calculator
- INPUT: graphe de dependances du Cube (build_neighbor_graph() + parse_dependencies())
- OUTPUT: dictionnaire {fichier: {R0: int, degree_centrality: float, betweenness_centrality: float, temperature: float}}
- NOTE: degree = nb connexions directes (hubs). betweenness = nb plus courts chemins qui passent par le noeud (ponts). Les deux sont utiles.
- TEST: sur un repo connu, verifier que les hubs ont le degree le plus haut et que les fichiers-ponts ont le betweenness le plus haut
- DEPENDANCES: Cube graphe existant (build_neighbor_graph, parse_dependencies). Brique isolee cote scanner.

### B-SCAN-05: Priority Ranker
- INPUT: output de B-SCAN-04
- OUTPUT: liste ordonnee de fichiers par priorite = R0 * centralite * temperature
- TEST: le fichier le plus modifie et le plus importe est en haut
- DEPENDANCES: B-SCAN-04

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

### B-SCAN-10: Propagation Engine
- INPUT: failles confirmees de B-SCAN-09 + graphe de dependances
- OUTPUT: blast radius par faille {faille_id, fichiers_impactes[], profondeur}
- ATTENTION CYCLES: le graphe de dependances peut avoir des cycles (A→B→C→A). Le BFS DOIT avoir un visited set pour pas boucler a l'infini.
- TEST: BFS sur le graphe, chaque fichier dependant est liste avec sa distance. Tester aussi un graphe avec cycle pour verifier que ca boucle pas.
- DEPENDANCES: B-SCAN-09, Cube graphe existant

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

### B-SCAN-13: Report Generator
- INPUT: output de B-SCAN-09 + B-SCAN-10 + B-SCAN-11
- OUTPUT: rapport lisible (markdown + json) avec failles, propagation, couverture, flags
- EXIT CODE: 0 = aucune faille. 1 = failles non-critiques. 2 = failles critiques. (pour CI/CD futur)
- TEST: le rapport est parsable, chaque faille a localisation + fix + blast radius. Verifier les 3 exit codes.
- DEPENDANCES: B-SCAN-09, B-SCAN-10, B-SCAN-11

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

## Pas maintenant
- GUI (osef)
- Certification ANSSI (plus tard)
- CVE database live updates (v2)
- CI/CD integration (v2)
- Multi-repo scan (v2, mais le meta-mycelium pose les bases)
