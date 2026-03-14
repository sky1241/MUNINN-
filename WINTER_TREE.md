# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: MATURE — pipeline complet, 3 TIERs valides
Etat: 56 briques + TIER 1-3 + HUGINN + Bio-Vectors (16 impl). AUDIT V9-V9D: 49 bugs fixes.
Engine: muninn.py 6420 lignes + mycelium.py 2610 lignes + mycelium_db.py 993 lignes = 10023 total
Tests: Battery V4 (50) + Senior (40) + Tree Fixes (12) = 102 PASS, 0 FAIL, 0 SKIP

## Anatomie

```
        [CI]                    +5 Cime (tests/validation)
       /    \
    [.mn]  [.mn]               +4 Feuilles (memoire vivante)
      |      |
   [tree.json]                 +2 Branches (metadata arbre)
      |
   [muninn.py]                 +1 Tronc (moteur principal)
      |
   [mycelium.py]               0  SOL — le champignon vivant
      |
   [tokenizer BPE]            -1 Racines (tokenizer natif Claude)
```

## Etat des briques

| # | Brique | Etat | Action |
|---|--------|------|--------|
| B2 | muninn.py v0.9 | OK | Moteur: 11 couches compression + retrieval intelligent (TF-IDF + Spreading Activation + scoring) |
| B4 | tree.json | OK | Enrichir: hash, temperature |
| B5 | *.mn files | OK | Memoire vivante |
| NEW | mycelium.py | OK | Tracker co-occurrences, fusion, decay |
| B9 | docs/ | OK | LITERATURE.md enrichi (43+ papiers dont 28 bio-vectors) |
| B10 | ci.yml | OK | Tests: tree, engine, mycelium, feed |
| NEW | .claude/settings.local.json | OK | Hooks PreCompact + SessionEnd + Stop -> feed + compress |
| NEW | .muninn/sessions/*.mn | OK | Transcripts compresses (auto-prune 10 derniers) |
| ~~B1~~ | ~~CODEBOOK.json~~ | SUPPRIME | Remplace par UNIVERSAL_RULES + mycelium |
| ~~B3~~ | ~~muninn_codec.py~~ | SUPPRIME | Code sinogramme mort |
| ~~B8~~ | ~~CODEBOOK_TREE.md~~ | SUPPRIME | Index sinogrammes mort |

## Pourquoi c'est dur et pourquoi personne l'a fait

LLMs construits par des "chirurgiens" (codeurs precis, prompts courts).
Ils n'ont pas le probleme de memoire — leurs sessions sont courtes et precises.
Les "bouchers" (vibe coders, sessions longues, bordel) ont le probleme
mais pas les skills pour le resoudre.
Sky est boucher AVEC un LLM pour coder = premiere fois que les deux se croisent.
Muninn = le hachoir. Construit par un boucher, pour les bouchers.
Ce n'est PAS plus dur que construire un LLM. C'est de la plomberie, pas de la recherche.
La partie dure (comprendre QUOI construire) est faite.

## TODO — par priorite

### P0 — Le mycelium (nouveau coeur) [FAIT]
- [x] Designer mycelium.json (format co-occurrences persistant)
- [x] Implementer le tracker de co-occurrences
- [x] Implementer la fusion automatique (concepts frequemment lies -> 1 bloc)
- [x] Implementer le decay (connexions mortes disparaissent)
- [x] Tester: simulation 20 sessions -> 69 connexions, 34 fusions

### P1 — La plomberie (le tuyau qui manque) [FAIT]
- [x] Cold start: `muninn.py bootstrap <repo>` — scanne et nourrit le mycelium
- [x] Hook PreCompact: parse transcript JSONL, nourrit le mycelium avant compaction
- [x] Hook SessionEnd: meme chose, filet de securite en fin de session
- [x] `muninn.py feed <transcript.jsonl>` — nourrit depuis un fichier specifique
- [x] `muninn.py feed --history` — rattrapage: digere tous les transcripts passes
- [x] Idempotent: tracked via .muninn/fed_transcripts.json
- [x] Integre dans .claude/settings.local.json (hooks natifs Claude Code)
- Note: hooks receoivent transcript_path via stdin JSON (decouverte mars 2026)

### P2 — Compresseur v2 (mycelium-aware) [FAIT]
- [x] Codebook loader v2: UNIVERSAL_RULES + mycelium (zero sinogrammes)
- [x] Compresseur utilise fusions mycelium pour strip redondance
- [x] 7 couches de compression: markdown, filler, phrases, nombres, rules, mycelium, facts
- [x] Extraction de faits: nombres+unites, %, key=value, commits, Cohen's d
- [x] Mesure gain tokens REEL (tiktoken, corrige mars 2026):
  - Texte verbeux (verbose_memory): x4.1 (1005->244 tokens, -76%, 100% facts)
  - Roadmap (WINTER_TREE): x2.6 (2751->1043 tokens, -62%, 96% facts)
  - README (deja compact): x1.6 (989->630 tokens, -36%, 93% facts)
  - ATTENTION: anciens chiffres (x7.4 etc) etaient bases sur len//4, faux de ~40%
- [x] Teste sur 2e repo (infernal-wheel): OK, compression universelle

### P3 — Nettoyage [FAIT]
- [x] Supprimer muninn_codec.py (code sinogramme mort)
- [x] Supprimer CODEBOOK.json (remplace par UNIVERSAL_RULES + mycelium)
- [x] Supprimer CODEBOOK_TREE.md (index sinogrammes mort)
- [x] Nettoyer muninn.py: virer sym_to_concept, concept_to_sym, CODEBOOK_PATH
- [x] Reecrire CI: tester tree, engine commands, mycelium (zero sinogramme)
- [x] Fix sys.stdout wrapper (condition encoding != utf-8)

### P4 — Enrichir l'arbre [FAIT]
- [x] tree.json: hash SHA-256 (8 chars) par noeud — detecte changements
- [x] tree.json: score temperature auto-calcule (access + recency + fill)
- [x] Ratios biologiques: budget dynamique par temperature (COCOM 2025)
- [x] Prune utilise temperature au lieu de access_count brut
- [x] Boot utilise temperature pour ranking des branches
- [x] Status affiche barre de temperature visuelle

### P5 — Auto-evolution (compresseur qui apprend) [FAIT]
- [x] Mycelium: get_learned_fillers() — mots noise (10+ connexions, zero fusion)
- [x] Mycelium: get_learned_abbreviations() — fusions fortes -> abreviations
- [x] L2b: fillers dynamiques injectes dans le compresseur depuis mycelium
- [x] L3b: abbreviations dynamiques injectees depuis mycelium
- [x] `muninn.py verify` — mesure qualite compression (facts preserved, ratio, score)
- [x] Boucle complete: feed -> mycelium apprend -> compresseur s'ameliore
- Note: abbreviations emergent quand fusion strength >= 8 (apres ~10+ sessions)

### P6 — Session compression (memoire post-compaction) [FAIT]
- [x] compress_transcript(): transcript JSONL -> .mn compresse dans .muninn/sessions/
- [x] Secret filtering: ghp_ tokens, sk_ API keys, passwords redacted avant compression
- [x] Hook PreCompact: feed mycelium + compress transcript (2 actions en 1)
- [x] Hook feed direct: meme chose en mode CLI
- [x] Boot charge le dernier .mn de session (tail-first si trop gros pour budget)
- [x] Auto-prune: garde les 10 derniers .mn, supprime les anciens
- Note: ratio sur transcripts modeste (~x1.7) car dialogue deja semi-compact

### P7 — Compression pro (9 couches) [FAIT]

#### Brique 1 : Benchmark [FAIT]
- [x] 3 samples (verbose, session, compact) + 40 questions factuelles
- [x] Resultat: 37/40 (92%) PASS — pure text search, zero API
- [x] Token counting reel: tiktoken (ancien len//4 etait faux de ~40%)

#### ~~Brique 2 : LLMLingua-2 (Layer 8)~~ [SUPPRIME]
- Perdait 72% des faits sur texte pre-compresse — inutile
- Code supprime de muninn.py le 2026-03-08

#### Brique 3 : Resume LLM comme Layer 9 [FAIT — BENCHMARKE]
- [x] Claude Haiku resume via API Anthropic (pip install anthropic)
- [x] Fallback gracieux si pas de cle API ou pas de SDK
- [x] Seuil: seulement si >4K chars
- [x] L9 ajoute a compress_file (pas seulement compress_transcript)
- [x] Fallback registre Windows pour API key (setx != process env)
- [x] Teste sur OpenAlex: 50 papers x5.2 ($0.024), 306 papers x4.0 ($0.13)
- [x] SOL.md full pipeline L1-L7+L9: x7.7 (20K->2.6K chars)
- [x] Bootstrap HSBC: x5.4 moyen (LOGIQUE x9.6, METHODOLOGIE x13.8, ARBRE x11.4)
- [x] L9 AUTO-SKIP sur transcripts (commit db258f3, 2026-03-08):
  - Teste: 55MB transcript, regex=3014tok ($0, 10s) vs L9=3319tok ($0.35, 17min)
  - L0 vire 74% du bruit (tool outputs), regex finit le job — L9 n'a plus de gras
  - L9 reste actif sur compress_file, ingest, bootstrap (prose brute: x2-x3 gain)
  - Regle: transcripts=regex suffit, docs bruts=L9 vaut le coup

Pipeline complet (11 couches, 25 filtres):
  L1: markdown strip | L2: filler words | L3: phrase compression
  L4: number shortening | L5: universal rules | L6: mycelium
  L7: fact extraction | L9: LLM self-compress (Haiku API)
L9 v3 (research-backed prompt):
  - "EXTRACT+RESTATE" not "Compress" (anti-summarization framing)
  - temperature=0, max_tokens=100% input, few-shot example, CoD enumeration
  - stop_reason check (detecte truncation silencieuse)
  - Single _L9_SYSTEM + _L9_PROMPT constants (zero duplication)
L9 benchmark: v1=x28/41% facts, v2=x16.6/49%, v3=x10.4/zero truncation
L9 ideal: sessions (tags D>/B>/F> protegent les faits importants)

Concurrence connue:
- Claude-Mem (21K stars): SQLite + Claude API, x10, pas d'arbre ni mycelium
- Letta Code (ex-MemGPT): git-backed markdown, agent complet
- LLMLingua-2 (Microsoft): BERT scorer, x3-20, pas de persistance
- ACON: gradient-free compression guidelines, -26-54% tokens

Ce que Muninn a que les autres n'ont pas:
- 11 couches empilees (regex + LLM), pas juste 1 technique
- Mycelium vivant (codebook qui apprend par co-occurrence)
- L-system fractal (memes regles a chaque niveau)
- Secret filtering
- Fonctionne sans dependances (L1-L7 regex only), GPU et API optionnels

### P8 — Retrieval intelligent (v0.9) [FAIT]
- [x] TF-IDF cosine similarity dans boot() — remplace le tag matching basique
  - Python pur (math + Counter), zero dependance
  - Calcule la similarite entre query et contenu reel des branches .mn
- [x] Scoring Generative Agents (Park et al. 2023):
  score = 0.2*recency + 0.2*importance + 0.6*relevance(query)
  - Recency: decay exponentiel Ebbinghaus (0.995^hours — 1d=0.89, 7d=0.43, 30d=0.03)
  - Importance: log(access_count)
  - Relevance: TF-IDF cosine similarity
- [x] Auto-segmentation dans feed_from_hook():
  - grow_branches_from_session() decoupe les .mn par ## headers
  - Chaque section = une branche avec tags auto-extraits
  - Merge si >50% overlap de tags avec branche existante
  - Fallback chunking si pas de headers
  - L'arbre grossit automatiquement a chaque session
- [x] Teste: "binance trading" -> branches HSBC, "scan glyph" -> branches Yggdrasil

### P9 — Commande ingest + isolation per-repo [FAIT]
- [x] Arbre per-repo: tree.json + branches vivent dans .muninn/tree/ du repo cible
- [x] _get_tree_dir() dynamique: zero contamination cross-repo
- [x] Commande `ingest <fichier|dossier>`: compresse docs de reference -> branches permanentes
- [x] feed --history: compresse transcripts passes ET cree branches (pas juste mycelium)
- [x] Teste: WINTER_TREE.md -> 5 branches x2.9, tags auto-extraits

### P10 — Bug scan + hardening [FAIT]
- [x] Scan 1: _prune_weakest IndexError (sorted_keys epuise si tout fusionne)
- [x] Scan 1: save_tree mkdir manquant avant mkstemp
- [x] Scan 1: get_codebook cache pas invalide quand _REPO_PATH change
- [x] Scan 1: CI assert len>=0 toujours vrai
- [x] Scan 2: load_tree crash sur JSON corrompu -> fallback init_tree()
- [x] Scan 2: max_tokens=0 possible pour API L9 -> max(1, ...)
- [x] Scan 2: fed_transcripts.json crash sur JSON corrompu -> reset gracieux
- [x] Scan 2: test_l8_ordering temp file leak -> try/finally
- [x] Scan 2: CLAUDE.md disait L9 pas teste (faux depuis 2026-03-07)
- [x] Scan 3: parse_transcript TypeError si content ni str ni list
- [x] Scan 3: mycelium.json crash sur JSON corrompu -> re-init gracieux
- [x] Scan 4: verify file existence check + fed_transcripts TypeError guard
- [x] Scan 5: build_tree boucle infinie (pop+append ne retrecit jamais)
- [x] Scan 6: CLEAN — 0 nouveau bug
- Total: 14 bugs corriges, 0 restant (6 scans complets)
- [x] Scan 7 (2026-03-10, 3 agents paralleles, muninn+mycelium+watchdog):
  - muninn.py: ZeroDivisionError x2 (max_lines=0, orig_tokens=0), boucle infinie force-split,
    file handle leaks x2, OSError crash dans feed_watch
  - mycelium.py: unguarded split("|") x4 (crash sur cles malformees), _load missing OSError
  - watchdog.py: erreurs subprocess silencieuses, check existence muninn.py
  - Total: 11 bugs fixes
- [x] Scan 8 (2026-03-10, 3 agents focus data-flow/edge/compression):
  - SECURITY: secrets leaked through compress_file() — now uses _SECRET_PATTERNS constant
  - DATA LOSS: L9 truncation silently accepted — now rejects truncated output
  - DATA LOSS: compress_file dropped content before first ## header — now captures as Preamble
  - CORRECTNESS: project dir matching too broad (substring -name) — now endswith()
  - CRASH: del nodes[m] in sleep_consolidate — now pop(m, None) + safe unlink
  - LEAK: install_hooks file handle — now read_text()
  - COLLISION: feed_watch filename-only key — now project_dir/filename
  - Total: 7 bugs fixes
- [x] Scan 9 (2026-03-10, 3 agents focus concurrency/boot/mycelium-deep):
  - RACE: _MuninnLock (mkdir atomicity + stale detection) pour stop_hook concurrent
  - RACE: feed_from_stop_hook wrapped sous lock (prevent double-feed)
  - PERF: read_node() accepte _tree param, boot() charge/sauve 1 seule fois (etait N load+save)
  - LOGIC: spread_activation propagation sur frontier seulement (pas re-propagation seeds)
  - CRASH: mycelium get_bridges() unguarded split — now len(parts) check
  - CRASH: mycelium pull_from_meta() unguarded split — now len(parts) check
  - MATCH: observe_with_concepts() substring -> word boundary regex (evite faux positifs)
  - WINDOWS: _prune_if_memory_pressure() utilisait GetPhysicallyInstalledMemory (RAM totale) — now GlobalMemoryStatusEx (RAM libre)
  - BLOOM: filtre novelty trop agressif (10% seuil, mots <4 chars) — now 5% seuil, mots >=3 chars, min 10 concepts
  - Total: 10 bugs fixes (dont 2 race conditions, 2 crashes, 1 perf, 1 logic, 1 matching, 1 Windows, 1 bloom, 1 lock)
- [x] Scan 10 (2026-03-10, 4 agents full sweep hooks/tree/CLI/mycelium):
  - SILENT DEATH: feed_from_hook pipeline crash = lost session — now try/except + traceback + hook_log
  - DATA: dedup eviction sorted by msg_count (wrong) — now sorted by session_id (chronological)
  - DATA: _update_usefulness string content iterated chars — now handles str + list[dict]
  - CRASH: _check_fusions unguarded split("|") — now len(parts) check
  - CRASH: decay(days=0) ZeroDivisionError — now early return
  - WINDOWS: GlobalMemoryStatusEx return value unchecked — now guards API failure
  - PERF: _detect_transcript_format read entire 55MB file for JSON check — now first-bytes only
  - CORRUPTION: pull_from_meta shallow dict copy — zones list shared between meta/local — now deepcopy
  - COSMETIC: bloom comment said 10% but code was 5% — comment fixed
  - FIX: watchdog subprocess window spam — pythonw.exe + CREATE_NO_WINDOW
  - Total: 10 bugs fixes (dont 2 data, 2 crash, 1 silent death, 1 corruption, 1 perf, 1 Windows, 1 cosmetic, 1 UX)
- [x] Scan 11 (2026-03-10, suite scan 10 — hooks concurrency hardening):
  - RACE: feed_from_hook now locked (meme lock "hook" que stop_hook — interlocking)
  - RACE: feed_watch now locked (meme lock "hook" — prevent concurrent watch+hook)
  - DATA LOSS: feed_watch saves state per-file (was all-or-nothing, crash = re-process all)
  - DATA LOSS: feed_watch wraps each file in try/except (1 crash doesn't kill all)
  - CORRUPTION: _register_repo atomic write (tempfile + os.replace, was write_text)
  - POLLUTION: sys.path.insert dedup (9 sites insertaient le meme path indefiniment)
  - Total: 6 bugs fixes (dont 2 race, 2 data loss, 1 corruption, 1 pollution)
- [x] Scan 12 (2026-03-10, CLI argument parsing):
  - CLI: prune --force cassé (argparse rejetait --force) — now proper --force flag
  - CLI: feed <file.jsonl> sans --repo utilisait le JSONL comme repo path — now CWD fallback
  - Total: 2 bugs fixes

### P11 — Bootstrap auto-complet [FAIT]
- [x] Format SOL.mn: template machine-optimal (P/E/S/F/K/R) pour root.mn
- [x] generate_root_mn(): scan repo -> root.mn dense auto-genere
- [x] generate_winter_tree(): roadmap humaine auto-generee
- [x] install_hooks(): PreCompact + SessionEnd configures automatiquement
- [x] Un seul `bootstrap` = mycelium + root.mn + WINTER_TREE + hooks
- [x] Teste sur infernal-wheel: 29 lignes, 465 tokens, 8 branches
- Note: format SOL.mn aide le parsing Claude mais ne sauve pas de tokens vs prose
  (BPE optimise pour l'anglais, les | et : coutent autant que des mots)

### P12 — Benchmark complet [FAIT]
- [x] 9 fichiers reels, 3 repos (Yggdrasil, InfernalWheel, Muninn)
- [x] Compression L1-L7: x4.5 moyen (28378->6269 tokens, 78% economises)
- [x] Fact retention: 85% (17/20 questions factuelles)
- [x] Range: x1.3 (compact) a x14.8 (verbeux)
- [x] Ingest infernal-wheel: x11.6 avec L9, 8 branches auto-creees
- [x] Rapport: docs/BENCHMARK_FULL_2026-03-07.md

### P13 — L0 filtre tool outputs [FAIT]
- [x] Filtre dans parse_transcript: tool_use -> 1-line summary, tool_result -> first line
- [x] Teste: 10K-line transcript, 3.4M -> 987K chars (x3.5, 71% stripped)
- [x] Summaries: [read path], [bash: cmd], [edit path], [grep pattern], [glob pattern]

### P14 — Tags de type memoire [FAIT]
- [x] 5 tags: B> bug/fix, E> error, F> fact/metric, D> decision, A> architecture
- [x] Regex classifiers ordered by specificity (F> before A> to avoid "layer" conflict)
- [x] Applied in compress_transcript on each compressed line

### P15 — Query expansion mycelium [FAIT]
- [x] Mycelium.get_related(concept, top_n) method added
- [x] boot() expands query with top-3 related concepts (strength >= 3)
- [x] Ex: "compression layers" -> "compression layers tree memory tokens"

### P16 — Session log dans root.mn [FAIT]
- [x] _append_session_log(): appends "YYYY-MM-DD xRATIO summary" to root.mn R: section
- [x] Keeps last 5 entries, auto-creates R: section if missing
- [x] Cousins see recent session history at boot

### P17 — Compression code blocks [FAIT]
- [x] _compress_code_blocks(): strips code blocks >4 lines to signatures + ...
- [x] Keeps def/class/function/import signatures + short comments
- [x] Short blocks (<=4 lines) kept as-is (config, output)

### P18 — Memoire erreurs/fixes [FAIT]
- [x] _extract_error_fixes(): E> followed by B>/D> -> stored in .muninn/errors.json
- [x] _surface_known_errors(): query word overlap -> surfaces matching fix at boot
- [x] Keeps last 50 error/fix pairs, dedup by error text

### P19 — Dedup branches au boot [FAIT]
- [x] Word-set overlap check at boot: >50% overlap = skip branch
- [x] Prevents loading redundant content that wastes token budget
- [x] Applied before session loading

### P22 — Session index (memoire longue) [FAIT]
- [x] Build .muninn/session_index.json au feed: date, tags (D>,B>,F>), concepts-cles (top 10)
- [x] boot() cherche dans l'index les sessions pertinentes par concept overlap
- [x] Charge les 2 sessions les plus pertinentes en plus de la derniere

### P23 — Auto-continue (boot intelligent) [FAIT]
- [x] Si query vide au boot, charge les top 5 concepts de la derniere session
- [x] Concepts extraits de session_index.json (derniere entree)
- [x] Seamless: "continue" = reload du contexte precedent sans rien taper

### P24 — Preservation causale (le POURQUOI) [FAIT]
- [x] Connecteurs causaux proteges dans compress_line L2 pre-pass
- [x] because, since, therefore, due to, parce que, car, donc, puisque
- [x] "because of" retire de la filler list (etait strip par erreur)

### P25 — Survie par priorite [FAIT]
- [x] Session .mn > 3K tokens -> drop untagged first, keep D>/B>/F> last
- [x] Score: D>=5, B>=4, E>=3, F>=3, A>=2, untagged=1
- [x] Headers (#) et ?FACTS toujours gardes (priority=99)

### P26 — Dedup lignes compressees [FAIT]
- [x] Hash normalise (lowercase, strip punctuation, collapse spaces)
- [x] Lignes identiques ou quasi-identiques -> skip apres premiere occurrence
- [x] Headers et ?FACTS exclus du dedup

### P27 — Dedup lectures fichiers [FAIT]
- [x] parse_transcript: track fichiers lus via dict file_path -> index
- [x] Meme fichier lu N fois -> marque anciennes lectures None, garde la derniere
- [x] Cleanup: filtre None en fin de parse

### P28 — Filtre tics Claude [FAIT]
- [x] Regex _CLAUDE_TICS: "Let me read/check", "I'll now", "Great!", "Looking at"...
- [x] Strip le prefix tic, garde le contenu si remainder >= 25 chars
- [x] Phrases purement tic (< 25 chars apres strip) supprimees entierement

### P29 — Recall mid-session [FAIT]
- [x] `muninn.py recall "query"` — cherche dans sessions + arbre + errors
- [x] Grep les .mn par overlap de mots, top 10 resultats tries par pertinence
- [x] Permet au cousin de chercher dans sa memoire en plein milieu de session

### P30 — Mycelium scaling infini [FAIT]
- [x] Chunking par paragraphe: observe_text split sur \n\n, observe chaque chunk separement
- [x] Semantiquement correct: concepts proches co-occurent, concepts distants non
- [x] Fix MemoryError O(n²) sur gros fichiers (WEB.md 487K crashait)
- [x] MAX_CONNECTIONS=0 (illimite) — le reseau grandit librement
- [x] Safety RAM: _prune_if_memory_pressure() prune 50% si dict > 200MB
- [x] _prune_weakest() optimise (un seul slice au lieu de pop(0) en boucle)
- [x] Teste: infernal-wheel 130 fichiers -> 722K connexions, 6225 fusions, 0 crash
- [x] Benchmark pousse: docs/BENCHMARK_MYCELIUM.md

### P31 — Liane Muninn-Yggdrasil [FAIT — pret a brancher]
- [x] observe_latex(): chunker split sur \section, \subsection, \begin{...}
- [x] observe_with_concepts(): accepte une liste de concepts externes (ex: OpenAlex 65K)
- [x] Auto-detect LaTeX vs plain text dans observe_with_concepts
- [x] Strip commandes LaTeX (\cmd{...} -> contenu, \cmd -> vide, {$^_~\} -> espace)
- [x] Teste sur 3 vrais papers arXiv (.tex depuis E:/arxiv/src/):
  - observe_latex: 459K connexions, top = density|velocity (astro, correct)
  - observe_with_concepts(20 astro concepts): 109 connexions, top = observation|velocity
  - LaTeX chunking > plain chunking (meilleur decoupage que \n\n sur du .tex)
- [ ] Integration Yggdrasil: lancer sur les 2449 tars avec concept_index 65K
- Pre-requis pour full run: apres WT3 (Bible Yggdrasil)
- Note: tars arXiv = .gz imbriques dans .tar, chaque .gz = un paper (.tex ou .tar.gz interne)

### P20 — Mycelium federe (continents + ponts) [FAIT]

Architecture decidee 2026-03-08 (Sky):
- Chaque mycelium reste local a son repo (rien ne change pour l'existant)
- Le Laplacien detecte les clusters semantiques = zones/metiers (pas par repo, par SENS)
- Inversion TF-IDF: cite partout = poids faible mais immortel, rare = poids fort
- Zones auto-nommees par metier (sante, finance, recherche...) via concepts dominants
- Ponts inter-zones par concepts partages (auto-detection, zero config)
- 1 repo peut avoir 2+ zones, 2 repos peuvent partager 1 zone
- DEBRAYABLE: feature flag `federated=False`, si off = comportement actuel inchange

Briques (10/10 done):
- [x] P20.1: flag `federated=False` dans mycelium.py — si off, zero changement
- [x] P20.2: champ `zones` sur chaque connexion (tagged during observe)
- [x] P20.3: inversion TF-IDF — effective_weight = count × log(1 + total_zones / zones_present)
- [x] P20.4: immortalite — connexion dans 3+ zones = skip decay
- [x] P20.5: Laplacien spectral (scipy eigsh + sklearn KMeans) → detection clusters
- [x] P20.6: auto-naming des zones par top-3 concepts (plus haut degre)
- [x] P20.7: get_related() zone-aware (zone courante x2.0 boost)
- [x] P20.8: CLI `muninn.py zones` + `muninn.py detect` + --federated/--zone flags
- [x] P20.9: persistence zones dans mycelium.json (champ "zones" par connexion)
- [x] P20.10: test complet 4 repos (HSBC+shazam+infernal+muninn)

Test integration (2026-03-08):
  114 fichiers, 649K connexions, 4 zones tagged, 11254 ponts inter-zones
  833 connexions immortelles (3+ zones) survivent decay
  Laplacien detecte 5 clusters semantiques auto-nommes
  get_related() zone-aware: trading->HSBC (gestion, optimisation, symbol)

Test L9 full pipeline (2026-03-08) — 4 repos:
  | Repo | Fichiers | Input | Output | Ratio |
  |------|----------|-------|--------|-------|
  | HSBC | 115 | 194K tok | 64K tok | x3.0 |
  | shazam | 45 | 107K tok | 37K tok | x2.9 |
  | infernal | 58 | 535K tok | 87K tok | x6.2 |
  | muninn | 12 | 19K tok | 8K tok | x2.3 |
  | TOTAL | 230 | 855K tok | 196K tok | x4.4 |
  Cout API: ~$0.21 (Haiku), 5 truncations sur 230 fichiers

### P20b — Meta-mycelium (cross-repo sync) [FAIT]
- [x] `sync_to_meta()`: pousse connexions locales vers `~/.muninn/meta_mycelium.json`
- [x] `pull_from_meta(query_concepts)`: tire connexions pertinentes du meta au boot
- [x] Merge: max(count), union(zones), earliest first_seen, latest last_seen
- [x] Auto dans feed_from_hook(): sync apres chaque feed (zero config)
- [x] Auto dans boot(): pull du meta avant query expansion (zero config)
- [x] CLI: `mycelium.py sync <repo>` — sync manuel
- [x] Teste: MUNINN+infernal -> 723K meta, shazam pull 200 connexions pertinentes

### Shopping List — 8 briques implementees (session 2026-03-08)
Recherche complete: 20 techniques evaluees, 8 implementees, 1 impasse, 11 skip.

| Brique | Technique | Status | Gain |
|--------|-----------|--------|------|
| 1 | Meta-Tokens (LZ77 n-grams) | IMPASSE — 0% on compressed text, BPE overhead | - |
| 1b | Encodage binaire des papers | IMPASSE — BPE lit des tokens pas des bits, binaire = x20 plus cher, Shannon | - |
| 3 | Contradiction resolution | FAIT — skeleton last-writer-wins | Correctesse |
| 4 | Semantic RLE | FAIT — collapse debug/retry loops (13msg->5) | 10-30% sessions |
| 5 | Optimal Forgetting | FAIT — re-compress cold branches via L9 in prune | Densite long-terme |
| 6 | NCD dedup (zlib) | FAIT — replaces word-overlap in P19 + grow_branches | 5-8% boot |
| 13 | KIComp density scoring | FAIT — drop low-info lines on boot overflow | 20-30% boot overflow |
| 15 | R1-Compress chunking | FAIT — section-aware L9 API calls (>8K) | Qualite L9 |
| 18 | Context-Aware Merging | FAIT — contradiction+dedup on branch merge | Anti-hallucination |
| 20 | Bloom concept tracking | FAIT — skip <10% novelty branches at boot | 10-15% boot |

Skip: SemHash (NCD does it), token-reducer (redundant L3+L5+L6), Selective-Context (too heavy),
Zstd (wrong level), A-MEM (=mycelium), ACON (needs eval infra), Word Graph (pre-compressed text).

Benchmark final cross-repo (12 fichiers, 4 repos, pipeline L1-L7+L10+L11+L9):
  | Fichier | Repo | Original | Compresse | Ratio |
  |---------|------|----------|-----------|-------|
  | DEPLOYMENT | infernal | 7K tok | 734 tok | **x9.6** |
  | BIOMECANIQUE | infernal | 7K tok | 925 tok | **x7.8** |
  | WEARABLE | infernal | 8K tok | 1080 tok | **x7.4** |
  | HISTORIQUE | HSBC | 6K tok | 910 tok | **x6.3** |
  | WINTER_TREE | muninn | 9K tok | 1380 tok | **x6.2** |
  | YGG BRIEFING | yggdrasil | 2K tok | 514 tok | x4.3 |
  | ARBRE | infernal | 11K tok | 3127 tok | x3.5 |
  | CLAUDE.md | muninn | 2K tok | 774 tok | x3.1 |
  | YGG MYCELIUM | yggdrasil | 2K tok | 746 tok | x2.9 |
  | HSBC ARBRE | HSBC | 3K tok | 1251 tok | x2.7 |
  | README | muninn | 2K tok | 1035 tok | x1.9 |
  | HSBC INDEX | HSBC | 2K tok | 1261 tok | x1.9 |
  Total: 62K -> 14K tokens (**x4.5 moyen**). Zero erreur, zero crash.
  Range: x1.9 (deja compact) a x9.6 (doc structuree).

### L10 — Cue Distillation (le move Carmack) [FAIT]
Insight: le LLM connait deja ~80% de ce qu'on stocke (syntaxe, APIs, patterns).
On ne stocke que les CUES (indices de rappel) + les faits NOVELS (nombres, decisions, commits).
Theorie: Method of Loci (500 BC) + Schema Theory (Bartlett 1932) + Predictive Coding (Rao & Ballard 1999).
Personne n'a applique ca a la compression memoire LLM.
- [x] _novelty_score(): heuristique 11 patterns novel + 5 patterns known + ratios
- [x] _generate_cue(): key+numbers+identifiers+proper_nouns, fallback cascade
- [x] _cue_distill(): threshold=0.35, cue si >30% plus court
- [x] Integre dans compress_file() et compress_transcript() AVANT L9
- [x] Teste: WEARABLE.md x19.4 -> x23.1 (+19%), 402 lignes cued/969
- [x] Reduit input L9 de 38% (60K -> 37K chars) = economie API
- [ ] Option Haiku pour cas ambigus (hybride) — LATER

### L11 — Rule Extraction (Kolmogorov) [FAIT]
Theorie: Kolmogorov 1965 — stocker le programme le plus court, pas les donnees.
- [x] _extract_rules(): detecte pipe-separated entries avec meme unite, factorise
- [x] Integre dans pipeline apres L10, avant L9
- [x] Teste: 3 lignes factorisees sur WEARABLE.md (gain modeste, applicable sur data-heavy)

### Spreading Activation (Carmack move #4) [FAIT]
Theorie: Collins & Loftus 1975 — propagation semantique a travers reseaux ponderes.
- [x] spread_activation(seeds, hops=2, decay=0.5) dans mycelium.py (~60 lignes)
- [x] Construit index d'adjacence, normalise les poids, propage N hops
- [x] boot() scoring: 0.15 recency + 0.15 importance + 0.5 tfidf + 0.2 activation
- [x] Teste: "compression"->tree/tokens/memory, "scan"->yggdrasil/arxiv/papers
- [x] Zero dependance, ~60 lignes, pas de compression mais RETRIEVAL semantique

### Sleep Consolidation (Carmack move #3) [FAIT]
Theorie: Wilson & McNaughton 1994 — consolidation episodique->semantique pendant le sommeil.
- [x] _sleep_consolidate() dans muninn.py (~100 lignes)
- [x] NCD pairwise grouping (threshold=0.6) pour trouver branches similaires
- [x] Concatene + dedup + contradiction resolution + L10 + L11 (zero API)
- [x] Integre dans prune(): cold branches fusionnees avant deletion des dead
- [x] Teste: 2 branches codec (NCD=0.57) fusionnees, 1 architecture preservee
- [x] Tags, access_count, children mis a jour dans l'arbre

### Spaced Repetition (Carmack move #5) [FAIT]
Theorie: Ebbinghaus 1885 (forgetting curve) + Settles & Meeder 2016 (half-life regression, ACL).
Formule: p = 2^(-delta / h), h = 7 * 2^min(reviews, 10) jours.
- [x] _ebbinghaus_recall(node) — calcule probabilite de rappel par branche
- [x] _days_since(date_str) — utilitaire jours depuis derniere visite
- [x] compute_temperature() reecrit: 80% recall + 20% fill_heat (etait 50% access + 30% recency + 20% fill)
- [x] Boot scoring: recall remplace recency+importance, ajout rehearsal_need (branches pres du seuil d'oubli)
- [x] Prune thresholds: R >= 0.4 = hot, R < 0.15 = cold, R < 0.05 = dead (etait temp-based)
- [x] Poids boot: 0.15*recall + 0.40*relevance + 0.20*activation + 0.10*usefulness + 0.15*rehearsal_need
- [x] Refs ajoutees dans docs/LITERATURE.md (5 papiers verifies)
- [x] Tests: 4/4 PASS (unit test, status, prune, boot)

### P40 — Bootstrap Branch Creation (2026-03-10) [FAIT]
Gap: bootstrap scannait les fichiers pour le mycelium + creait root.mn, mais ne creait PAS de branches.
Resultat: apres un bootstrap, l'arbre etait vide — il fallait des sessions de travail pour creer du contenu.
- [x] _bootstrap_branches() dans muninn.py (~50 lignes)
- [x] Selectionne les 20 plus gros .md/.txt (100B-100KB), trie par taille descendante
- [x] Compresse chaque fichier avec compress_file (full pipeline L1-L7+L10+L11)
- [x] Auto-segmente en branches via grow_branches_from_session (merge NCD si overlap)
- [x] Teste: 3 docs -> 5 branches creees au bootstrap (avant: 0)

### P21 — pip install muninn (2026-03-10) [FAIT]
Packaging: pyproject.toml + entry points pour installation via pip.
- [x] pyproject.toml avec setuptools build backend
- [x] engine/__init__.py + engine/core/__init__.py (package structure)
- [x] Entry points: `muninn` (CLI) + `mycelium` (CLI)
- [x] Optional deps: `muninn-memory[tokens]` (tiktoken), `muninn-memory[all]` (+ anthropic)
- [x] Teste: `pip install -e .` + `muninn status` + `muninn boot` + `muninn compress` OK
- [x] README mis a jour avec instructions pip install

### Cleanup memory/ (2026-03-08)
- [x] memory/root.mn et b00-b07.mn contenaient des donnees YGGDRASIL depuis le commit v0 (bc647da)
  - Premier test du moteur: avait utilise MEMORY.md de Ygg comme cobaye
  - Jamais nettoyé par aucun cousin depuis
- [x] Re-bootstrap propre: `muninn.py bootstrap .` genere root.mn Muninn (29 lignes, 393 tokens)
- [x] Copie .muninn/tree/ -> memory/, suppression des 8 branches Ygg
- [x] Arbre maintenant: 1 noeud root, tags=[muninn,compression,mycelium], 0.3% budget
- [x] Benchmark questions corrigees: layers 9->11, version 0.8->0.9.1
- [x] .claude/settings.json: paths hardcodes -> wildcard universel
- [x] SOL_TEMPLATE.md: path Python hardcode -> ${PYTHON_EXE}

### P32 — Hook Stop (zero data perdue) [FAIT]
Bug critique: conversations courtes (pas de PreCompact) + fermeture manuelle (pas de SessionEnd) = data perdue.
Les senior devs font exactement ca: conversations courtes, haute valeur, fermeture rapide.
- [x] Hook `Stop` fire a chaque reponse Claude — seul hook qui garantit la capture
- [x] BUG CORRIGE (2026-03-09): `stop_hook_active` n'est PAS un anti-boucle — Claude Code
  l'envoie TOUJOURS a true dans le JSON du Stop hook. L'ancien guard tuait 100% des captures.
  Vrai anti-boucle = dedup par session_id + msg_count (etait deja la, jamais atteint)
- [x] Dedup: `.muninn/stop_dedup.json` stocke `{session_id: msg_count}`
  - Meme conversation, meme nombre de messages → skip (zero recompression)
  - Nouveau message detecte → feed complet (mycelium + compress + branches + meta-sync)
- [x] Garde les 20 derniers session_id dans le dedup (auto-prune)
- [x] `--trigger stop` flag CLI + `install_hooks()` installe Stop sur nouveaux repos
- [x] Teste: 1er run feed (76 msgs, x2.3), 2eme run skip (dedup), anti-loop OK
- [x] 3 hooks maintenant: PreCompact (contexte plein) + SessionEnd (VS Code ferme) + Stop (chaque reponse)
- [x] `_hook_log()`: log fichier `.muninn/hook_log.txt` sur chaque entree de hook (diagnostic)

### P32b — Auto-install hooks (plug-and-play) [FAIT]
Probleme: Stop hook devait etre ajoute MANUELLEMENT dans chaque repo. Pas scalable.
- [x] `install_hooks()` reecrit: merge hook-par-hook au lieu de skip en bloc
  - Si PreCompact existe mais pas Stop → ajoute seulement Stop (preserve l'existant)
  - Si tous les 3 existent → skip (up-to-date)
  - Preserve les permissions et autres cles du settings.local.json existant
- [x] `upgrade-hooks` commande CLI: `muninn.py upgrade-hooks --repo <path>`
  - Permet de mettre a jour les hooks sur les repos existants sans re-bootstrap
- [x] `~/.muninn/repos.json` registre central — auto-rempli par install_hooks + feed hooks
  - Structure: `{"repos": {"MUNINN-": "C:\\...", "yggdrasil-engine": "C:\\..."}, "updated": "..."}`
  - Sert aussi de base pour P20c (decouverte cross-repo)
- [x] `_register_repo()` appele dans: install_hooks, feed_from_hook, feed_from_stop_hook
- [x] Stale path detection: si hook existe mais pointe vers un vieux muninn.py, met a jour
- [x] Teste: repo avec PreCompact+SessionEnd → Stop ajoute, permissions preservees
- [x] Teste: repo avec vieux path → PreCompact(updated) + SessionEnd + Stop
- [x] Cross-platform: `Path(__file__).resolve()` pour le chemin muninn.py, zero hardcode

### P20c — Virtual Branches (cross-repo tree sync) [FAIT]
Probleme: P20b synchronise le mycelium (co-occurrences) mais PAS le contenu des branches.
Les repos restent des silos — un Claude sur Yggdrasil ne voit pas les branches MUNINN.
- [x] `_load_virtual_branches(query, budget)` dans boot():
  - Lit `~/.muninn/repos.json` pour decouvrir les autres repos
  - Pour chaque repo: charge son tree.json + branches .mn en READ-ONLY
  - Score par TF-IDF (avec query) ou temperature (sans query), poids 0.5x vs local
  - Max 3 branches virtuelles, dans le budget restant apres les locales
  - Prefixe: `repo_name::branch_id` (ex: `MUNINN-::b1593`)
- [x] Cap 50 branches scannees par repo distant (les plus recentes par last_access)
  - MUNINN a 2051 branches — scanner tout serait trop lent
  - 50 = ~2 semaines d'activite, suffisant pour la pertinence
- [x] Nettoyage fantomes: repos supprimes retires auto du registry au boot
- [x] Try/except global par repo distant — jamais de crash boot a cause d'un repo casse
- [x] Aucune ecriture dans les trees d'autres repos — read-only strict
- [x] Dedup P19 (NCD) s'applique aussi aux branches virtuelles
- [x] Teste: boot Yggdrasil query "compression mycelium" → charge 3 branches MUNINN
- [x] Teste: boot Yggdrasil sans query → charge 3 branches MUNINN les plus chaudes
- [x] Teste: boot MUNINN → branches locales remplissent le budget, zero virtual (normal)
- [x] Teste: ghost repo auto-nettoye du registry, stale path auto-corrige
- [x] Les corbeaux se parlent enfin

### P34 — Boot Integrity Check [FAIT]
read_node() verifie le hash SHA-256 avant de charger une branche .mn.
- [x] Compare `compute_hash(filepath)` vs `node["hash"]` stocke dans tree.json
- [x] Mismatch → log warning + retourne vide (branche skippee, fallback sur la suivante)
- [x] Hash "00000000" (branches pas encore hashees) → skip la verification
- [x] Teste: fichier corrompu detecte, branche skippee, boot continue normalement

### P35 — Benchmark Factuel en CI [FAIT]
Le benchmark 37/40 etait un test manuel. Maintenant en CI automatique.
- [x] Step "Benchmark Factual Retention" dans ci.yml
- [x] Seuil monte a 85% (etait 70%) — fail si regression sous 34/40
- [x] Score actuel: 35/40 (88%) — verbose 100%, session 80%, compact 80%
- [x] Zero API, zero dependance externe, reproductible
- [x] 3 samples (verbose, session, compact) × 40 questions factuelles

### P36 — Boot Feedback Loop [FAIT]
Scoring statique → adaptatif. Le boot apprend quelles branches sont utiles par repo.
- [x] `last_boot.json`: sauvegarde la liste des branches chargees a chaque boot
- [x] `_update_usefulness()`: au feed, compare concepts session vs branches du boot
  - Usefulness = fraction de concepts branch qui apparaissent dans la session
  - Exponential moving average: `0.7 * old + 0.3 * new` (lissage, pas de sauts)
  - Default 0.5 (neutre) pour les branches pas encore evaluees
- [x] Scoring boot mis a jour: 0.1*recency + 0.1*importance + 0.45*relevance + 0.2*activation + 0.15*usefulness
- [x] Appele dans feed_from_hook et feed_from_stop_hook (avant compression)
- [x] Per-repo: chaque tree.json stocke ses propres scores d'utilite
- [x] Teste: 13 branches scorees, scores refletent le overlap session/branch

### P37 — Recall --load (mid-session warm-up) [FAIT]
recall() trouvait du contenu mais ne rechauffait pas les branches matchees.
- [x] recall() track les branches tree matchees pendant la recherche
- [x] Met a jour access_count + last_access des branches matchees
- [x] Affiche "(warmed N branches)" dans le header du recall
- [x] Prepare le prochain boot: branches recherchees = plus chaudes = mieux classees
- [x] Teste: recall → access_count 7→8, "warmed 1 branches" affiche

### P38 — Parser Multi-Format [FAIT]
parse_transcript() ne gerait que JSONL (Claude Code). Maintenant: auto-detect + 3 formats.
- [x] `_detect_transcript_format()`: detecte JSONL, JSON, markdown depuis les premiers 500 bytes
- [x] `_parse_json_conversation()`: claude.ai exports (chat_messages, conversation, messages)
- [x] `_parse_markdown_conversation()`: split par ## Human/Assistant/User/Claude headers
- [x] Fallback: format inconnu → traite comme JSONL (comportement original)
- [x] Teste: JSONL 2 texts, JSON 2 texts, Markdown 3 texts — tous corrects
- [x] Benchmark: 35/40 (88%) inchange — zero regression

### Audit Hardening (session 2026-03-09) [FAIT]
6 fixes de robustesse identifies par audit:
- [x] Exception logging: boot() `except: pass` → log to stderr (line ~1948)
- [x] Secrets: +AWS AKIA, private keys, OAuth Bearer tokens (3 patterns ajoutes)
- [x] Prune safety: try/except autour de unlink(), skip node deletion si fichier persist
- [x] tail_lines O(n²): `.insert(0,...)` → `.append()` + `.reverse()`
- [x] NCD dedup: compare last 3 branches seulement (O(1) par branche au lieu de O(n))
- [x] feed_history matching: `repo_name in d.name` → `-{repo_name} in d.name` (evite faux positifs)

### P33 — Decay Exponentiel Ebbinghaus [FAIT]
Bug: commentaire disait `0.995^hours` mais code faisait du lineaire `1.0 - days/90`.
- [x] Recency = `0.995 ** (days_cold * 24)` — courbe exponentielle fidele a Ebbinghaus 1885
- [x] 1 jour=0.89, 7 jours=0.43, 30 jours=0.03, 60 jours=~0 (vs lineaire: 0.99/0.92/0.67/0.33)
- [x] Les branches recentes comptent beaucoup plus, les vieilles disparaissent vite
- [x] 3 lignes modifiees, zero regression sur boot

### Flag --no-l9 + Mass Ingest (session 2026-03-09) [FAIT]
- [x] Flag `--no-l9`: skip L9 (LLM API), utilise seulement les couches gratuites (L1-L7+L10+L11)
- [x] Bootstrap + ingest de 7 repos en une session, $0.00:
  | Repo | Fichiers | Input | Output | Ratio | Branches |
  |------|----------|-------|--------|-------|----------|
  | HSBC-algo-genetic | 1730 md | 4.2M | 173K | x24.5 | 304 |
  | infernal-wheel | 59 md | 2.3M | 248K | x9.2 | 60 |
  | shazam-piano | 53 md | 365K | 81K | x4.5 | 28 |
  | 3d-printer | 36 md | 360K | 89K | x4.1 | 16 |
  | fck-translation | 38 md | 315K | 81K | x3.9 | 85 |
  | yggdrasil-engine | 20 md | 176K | 50K | x3.5 | 76 |
  | p-egal-np | 32 md | 305K | 95K | x3.2 | 142 |
  | TOTAL | 1968 | 8.0M | 817K | x9.8 | 711 |
- [x] Cout L9 estime si actif: ~$238 (surtout Yggdrasil 8.7M lignes)
- [x] L1-L7+L10+L11 gratuit = suffisant pour la majorite des cas

### P41 — Watchdog (poll-based capture) [FAIT]
Probleme: les hooks Stop/PreCompact/SessionEnd ne tirent pas toujours (sessions multiples
ouvertes sur le meme repo, fermeture d'un seul onglet = rien ne fire).
Solution: timer toutes les 15 minutes qui rattrape tout ce qui a ete manque.
- [x] `feed --watch`: compare la taille des JSONL vs `watch_state.json`, ne feed que ce qui a grandi
  - Zero travail si rien n'a change (return instantane)
  - Dedup natif par taille de fichier (pas de recompression si identique)
- [x] `watchdog.py`: itere tous les repos de `~/.muninn/repos.json`, lance `feed --watch` sur chacun
  - Timeout 5min par repo, capture_output (silencieux)
- [x] Tache planifiee Windows `MuninnWatchdog`: toutes les 15 minutes
  - `schtasks /tn MuninnWatchdog`, enabled, survit aux reboots
- [x] Teste: 1er run = feed all, 2eme run = "nothing changed" (instantane)
- Filet garanti: meme si AUCUN hook ne tire, le watchdog rattrape toutes les 15 min

### P42 — Live Mycelium Bridge (2026-03-14) [FAIT]
Probleme: le mycelium n'est utilise qu'au boot (chargement) et au feed (compression).
Pendant la conversation, Claude est DECONNECTE du mycelium — pas de pont semantique live.
Solution: `bridge()` — requete le mycelium mid-session, spreading activation en temps reel.
- [x] `muninn.py bridge "user text"` — extrait concepts, spread activation, retourne:
  - Concepts actives (spreading activation Collins & Loftus 1975)
  - Voisins directs des top seeds
  - Branches matchant les concepts actives
  - Fusions pertinentes
- [x] Stopwords FR+EN (filtre bilingue, >4 chars)
- [x] Auto-observe les concepts du bridge (nourrit le mycelium a chaque requete)
- [x] Edge cases: texte vide, concepts inconnus → messages clairs
- [x] CLI: `bridge` commande ajoutee au parser
- [x] `bridge_fast()`: fast path pour hooks (<0.5s), get_related() au lieu de spread_activation()
  - spread_activation: 10s (full graph) vs get_related: 0.03s (direct neighbors) = 300x
  - bridge_fast total: 0.12s Python, 0.35s end-to-end (incluant startup)
  - Skip observe+save (trop lent, persistence via feed hooks)
- [x] `.claude/hooks/bridge_hook.py`: lit stdin JSON (UserPromptSubmit), appelle bridge_fast()
  - Retourne `[MYCELIUM BRIDGE]` avec concepts actives par seed
  - Messages <10 chars = skip silencieux, erreurs = silencieux
- [x] Hook UserPromptSubmit dans settings.local.json (timeout 5s)
  - Fire sur CHAQUE message user, AVANT que Claude reponde
  - Claude voit le stdout = contexte mycelium injecte automatiquement
Theorie: HippoRAG (Gutierrez & Shu 2024, NeurIPS) + FLARE (Jiang 2023, EMNLP)
Personne ne fait exactement ca: spreading activation sur un mycelium de co-occurrences
vivant avec fusion/decay bio-inspires, mid-conversation.
Etat de l'art scanne:
- MemGPT/Letta (2023): self-directed memory paging
- Mem0 (2024): graph DB write/read chaque tour
- HippoRAG (2024): PageRank sur KG = notre spread_activation
- FLARE/DRAGIN (2023-2024): retrieval mid-generation par confidence/entropie
- Zep/Graphiti (2025): KG temporel avec contradictions
- KBLaM (Microsoft 2025): KB dans l'attention, pas de retrieval step
- A-Mem (2025): Zettelkasten auto-organise
Aucun ne combine: mycelium vivant + compression + spreading activation + bio-vectors.

### P39 — Liane WT3 : Muninn bibliothecaire [TODO — POST-WT3]
Muninn ne stocke pas les papers. Il devient le bibliothecaire personnalise de Sky.
Pre-requis dur: WT3 (Bible SQLite) doit exister avec paper_id -> [concepts].
Principe: nourrir le mycelium avec les concepts de 832K papers scannes.
Le spreading activation devient un moteur de recherche personnalise par les habitudes de Sky.
Pieces existantes: observe_with_concepts(), mycelium (722K conn ok), spreading activation.
A coder (~100 lignes):
- Reverse index `concept -> [paper_ids]` (JSON sur disque, dans .muninn/)
- Script one-shot: lire liste WT3 -> observe_with_concepts() par paper
- Query dans boot: spreading activation -> concepts actives -> reverse index -> paper IDs -> WT3 lookup
Difference avec Yggdrasil: Ygg cherche par metadonnees objectives. Muninn cherche par comment Sky pense.
Yggdrasil construit la liste. Muninn l'avale. Le champignon pousse dessus.
Pas prioritaire. Apres WT3.

### Scan Cross-Domaine Muninn x Yggdrasil (session 2026-03-10) [FAIT]
Recherche: quels domaines scientifiques utilisent les MEMES equations que Muninn?
Methode: scan Uzzi z-scores (172K paires, 65K concepts) + scan glyphes WT2 (833K papers) + web (80 sources).
7 isomorphismes confirmes entre formules Muninn et domaines etrangers:

| # | Muninn | Domaine etranger | Score | Source |
|---|--------|-----------------|-------|--------|
| 1 | F3 TF-IDF | Replicateur-mutateur (bio evo) | 19/20 | cond-mat/0004072 |
| 2 | F8 Decay+cooc | Lotka-Volterra (ecologie) | 19/20 | nlin/0009025 |
| 3 | F3 TF-IDF | Entropie AA positionnelle (biochimie) | 19/20 | physics/0012003 |
| 4 | F4+F8 Spreading+Decay | Quasispecies sigmoid (evolution) | ISOMORPHE | cond-mat/0202047 |
| 5 | F1 Ebbinghaus | Affinity maturation (immunologie) | 18/20 | PNAS+Science 2022 |
| 6 | F5 EMA | EWMA finance | 18/20 | standard + cond-mat/0001117 |
| 7 | F1 Ebbinghaus | Arbesman demi-vie faits | 17/20 | Arbesman 2012 |

Chiffres cles:
- 128 anti-signaux P5 (portes secretes entre domaines)
- 22/23 Type C en Cell Biology (plus gros blind spot)
- 30 equations LaTeX, 60+ variables mappees 1:1
- docs/FORMULES_ETRANGERES.md = compilation finale (7 pistes, mappings, verdicts)
- docs/SCAN_MUNINN_YGG.md = synthese 3 couches (Uzzi + web + glyphes)
- docs/RECHERCHE_WEB_PISTES.md = 10 pistes web evaluees
- docs/PROMPT_YGG_*.md = 3 prompts pour le cousin Yggdrasil

Insight: les formules de Muninn ne sont pas des inventions CS — ce sont des structures
universelles que la biologie, l'evolution, l'ecologie et la finance ont decouvertes
independamment. Darwin = Muninn.

### Briefing Cell Biology — 22 Blind Spots (session 2026-03-10) [RECU]
Source: cousin Yggdrasil. 22/23 paires Type C en cell bio = plus gros blind spot du scan.
3 concepts Muninn (eigenvalues, Markov, exp decay) x 10 concepts bio = 22 trous.
22 papers pionniers sur 833K. 6 blind spots actionables (BS-1 a BS-6).
2 deja integres dans le plan de bataille: BS-6 = A1 (h adaptatif), BS-3 = A2 (access_history).
Detail: docs/BRIEFING_CELLBIO_22BS.md
Papers cles: Cell Systems 2017 (non-Markov), PLOS Bio 2018 (h variable), PNAS 2024 (Mittag-Leffler).
Meta-resultat: Muninn fait deja de la bio cellulaire computationnelle sans le savoir.

### Plan de Bataille TIER 1 — 6 upgrades formula=data (session 2026-03-10) [FAIT]
Bornes de validation strictes AVANT code. Un upgrade = un commit = un push.
Detail complet: docs/PLAN_BATAILLE_TIER1.md
6 upgrades, 36 bornes, all validated (36 PASS, 0 FAIL, 0 SKIP).

| # | Upgrade | Formule cible | Lignes | Sources (convergence) |
|---|---------|---------------|--------|-----------------------|
| A1 | h adaptatif (F1+F5) | h = h_base * 2^reviews * usefulness^beta | ~20 | GARCH + PLOS Bio 2018 + BS-6 |
| A2 | access_history (F1) | B = ln(sum(t_j^(-d))) ACT-R | ~30 | ACT-R + Cell Systems 2017 + BS-3 |
| A3 | Sigmoid spreading (F4) | sigma(x) = 1/(1+e^(-k(x-x0))) | ~30 | cond-mat/0202047 |
| A4 | Saturation decay (F8) | dw = -w/tau - beta*w^2 | ~15 | Lotka-Volterra nlin/0009025 |
| A5 | Spectral gap metric | gap = lambda_2 / lambda_1 | ~5 | Bowman Stanford |
| B1 | Reconsolidation boot | L10+L11 sur branche froide | ~40 | Nader 2000 + DARPA RAM |

Protocole: baseline → code → unit tests → regression → pass/fail → commit.
Pieges identifies: usefulness=0 (clamp 0.1), backward compat tree.json, sigmoid placement, entier decay.
Key results: recall separation 4.3x, reconsolidation 43% reduction, boot overlap 88%.
Commits: 7487e94..2325e05 (8 commits). Tests: tests/test_tier1_*.py.
Backward compat: all defaults reproduce pre-TIER1 behavior exactly.

### Plan de Bataille TIER 2 — Structural Intelligence (session 2026-03-10) [FAIT]
5 upgrades, 32 bornes, all validated (32 PASS, 0 FAIL).

| # | Upgrade | Description | Sources |
|---|---------|-------------|---------|
| B2 | Graph anomaly detection | detect_anomalies() — isolated/hubs/weak_zones | Graph theory |
| B3 | Blind spot detection | detect_blind_spots() — structural holes | Burt 1992 |
| B7 | Live injection | inject_memory() + CLI `inject "fact"` | — |
| B4 | Endsley L3 Prediction | predict_next() via spreading activation | Endsley 1995 |
| B5+B6 | Session mode + RPD type | convergent/divergent + debug/feature/explore/refactor/review | Klein RPD |

Commits: 6d1a685..7e5e287 (5 commits). Tests: tests/test_tier2_*.py.
All 5 upgrades wired into boot() pipeline.

### Plan de Bataille TIER 3 — Mycelium Storage Revolution (session 2026-03-11) [DONE]
C1: Saturation beta active (Lotka-Volterra beta=0.001, freine les connexions monopoles >50 count). 5 bornes.
C2: Boot feedback log — .muninn/boot_feedback.json, tracks blind spots covered/uncovered, last 20 boots. 5 bornes.
C6: CLI diagnose — `muninn.py diagnose` full health: tree/mycelium/anomalies/blind spots/sessions. 5 bornes.
P41: Mycelium auto-referentiel — observe fusions as 2nd-order co-occurrences (1/3 ratio cap). 5 bornes.
C3: Auto-preload predictions — top 3 B4 predictions (score>=0.3) pre-chargees dans boot(). 5 bornes.
C4: Real-time k adaptation — adapt_k() in recall()+inject_memory(), sigmoid k adjusts mid-session. 5 bornes.
C7: Contradiction resolution in B1 — _resolve_contradictions() before L10+L11 in reconsolidation. 5 bornes.
FIX: SQLite PermissionError on Windows — conn.close() before unlink, try/except on locked .db files.
FIX: boot() UnboundLocalError — blind_spot_concepts init before query block.
FIX: mycelium.py relative imports — top-level try/except for package+standalone.
FIX: CI workflow — mycelium.db check (S1 migration) instead of mycelium.json.
CI: VERT (all steps pass: tree, engine, mycelium, benchmark, feed).
Probleme: mycelium.json explose (376 Mo Muninn, 173 Mo Ygg, 946 Mo meta = 1.5 Go total).
4 jours, 103 sessions chez Ygg = 716K connections, 479K fusions. JSON pretty-print = 16M lignes.
VSCode crash, RAM saturee, et ca va empirer (arXiv = 2449 tars a venir).

| # | Upgrade | Description | Gain attendu |
|---|---------|-------------|--------------|
| S1 | SQLite storage | JSON → SQLite normalise (concepts=IDs entiers, WITHOUT ROWID, WAL) | x5 disque, x100 RAM |
| S2 | Epoch-days dates | "2026-03-11" (10 bytes) → entier jours depuis epoch (2 bytes) | Integre dans S1 |
| S3 | Degree filter | Avant fusion: concept avec trop de voisins = stopword = pas de fusion | Universel, zero langue |
| S4 | Auto-translate | tiktoken detect (1 tok=EN, 2+=etranger) → batch Haiku → cache | Universel toutes langues |

Schema SQLite:
```sql
PRAGMA journal_mode=WAL;
CREATE TABLE concepts (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE edges (a INT, b INT, count INT, first_seen INT, last_seen INT, PRIMARY KEY(a,b)) WITHOUT ROWID;
CREATE TABLE fusions (a INT, b INT, form TEXT, strength INT, fused_at INT, PRIMARY KEY(a,b)) WITHOUT ROWID;
CREATE INDEX idx_edges_a ON edges(a);
CREATE INDEX idx_edges_b ON edges(b);
```

Dates: epoch-days depuis 2020-01-01 (entier, bijectif, queryable).
Migration auto: detecte .json → importe → .json.bak.
S3: degre du graphe = detection universelle de stopwords (un mot connecte a tout = bruit).
S4: tokenizer comme detecteur de langue + batch API + cache perpetuel dans la DB.
Ordre: S1+S2 (stockage) → S3 (filtre) → S4 (traduction).
Zero dependance nouvelle (sqlite3 = stdlib, tiktoken deja present, anthropic deja optionnel).

### Audit complet (2026-03-11) — Etat des lieux

**Pipeline compression**: 11 couches (L0-L7, L9, L10, L11) + 7 filtres (P17, P24-P28) = TOUT OPERATIONNEL
**Features P-series**: 20/20 FAIT (P3 supprime, P21 partiel, P42 bridge), toutes branchees et testees
**Shopping list**: 9/20 FAIT, 1 impasse (Meta-Tokens), 6 skip, 2 maybe, 1 later
**Carmack moves**: 5/5 FAIT (L10 cue, L11 rules, sleep consolidation, spreading activation, spaced repetition)
**TIER 1**: 6/6 FAIT (A1-A5, B1), 36 bornes, 100% PASS
**TIER 2**: 5/5 upgrades + 4 wiring FAIT (B2-B7, W1-W6), 74 bornes, 100% PASS
**TIER 3**: 11/11 FAIT (S1-S4, C1-C7, P41), 126 bornes cumul, CI vert
**Cross-domain**: 7 pistes analysees, 4 isomorphismes LaTeX-confirmes (FORMULES_ETRANGERES.md)
**Tests**: 25 fichiers, 126+ bornes, 0 FAIL, 0 SKIP

**Reste a faire**:
- Bio-Vectors: 22 formules planifiees (TIER S: 6, TIER A: 6, TIER B: 4, TIER C: 6 skip)
- P21: publier sur PyPI (pyproject.toml pret)
- P31: full arXiv run (attend WT3)
- P39: liane Yggdrasil (attend WT3)
- Explication A-Z du systeme pour Sky
- P42 bridge: hook automatique UserPromptSubmit (phase 2 — quand Claude Code le supportera)

### Plan HUGINN — "Muninn stocke, Huginn pense" (session 2026-03-11) [DONE]

Base scientifique: BARE Wave Model (Nature 2025) + Entropic Brain (Carhart-Harris 2014).
Le vrai champignon: dn/dt = alpha*n - beta*n*rho (tips naissent, fusionnent avec le reseau).
La psilocybine: baisser beta → tips explorent sans fusionner → entropie monte.

| # | Brique | Description | Bornes | Status |
|---|--------|-------------|--------|--------|
| H1 | Mode trip | trip() — connexions exploratoires cross-cluster (BARE Wave alpha/beta) | 9/9 PASS | DONE |
| H2 | Synthese/reve | dream() — insights pendant sleep consolidation | 7/7 PASS | DONE |
| H3 | Huginn CLI | huginn_think() + CLI think + boot surfacing | 8/8 PASS | DONE |

**Total: 24 bornes, 24 PASS, 0 FAIL.**

H1: trip() dans mycelium.py (~90 lignes)
- Trouve clusters distants (spectral si scipy, BFS fallback sinon)
- Cree connexions exploratoires entre concepts de clusters differents
- Marquees type="dream", decay rapide si pas renforcees par usage reel
- Auto-regulation BARE Wave: alpha*n cree, beta*n*rho limite (quand rho dense, moins de tips)
- Entropie H = -sum(p*log(p)) sur distribution des degres → mesure avant/apres
- Se declenche dans prune() ou CLI `muninn.py trip`
- Commit: 2e47a64

H2: dream() dans mycelium.py (~120 lignes)
- Analyse graphe: strong pairs, absences, validated dreams, cluster imbalance, health
- Ecrit .muninn/insights.json (timestamp, type, concepts, score, text)
- Se declenche dans prune() apres trip()
- Commit: 2fc2f9b

H3: huginn_think() dans muninn.py (~90 lignes)
- Lit insights.json, filtre par pertinence a la query
- Formule en langage naturel avec icones (BOND, BLIND SPOT, CONFIRMED, WARNING, HEALTH)
- CLI: `muninn.py think [query]` — affiche top insights
- Boot: top 3 insights affiches via _surface_insights_for_boot()
- Le deuxieme corbeau d'Odin prend vie
- Commit: 56ef1b3

### Bio-Vectors — Cerveau Biomimetique (session 2026-03-11) [DONE — AUDITED]

Recherche: 11 vecteurs bio-cognitifs pour Muninn. Chacun = angle d'optimisation unique.
Methode: scan Yggdrasil (36 paires, 65K concepts) + JSON 22 formules + scan croise.
Regle d'or: bat l'existant sur une metrique ou POUBELLE. Pas de deco.

Sources scientifiques — 22 formules, 28 papiers primaires, 13 papiers echecs:

#### TIER S — Implementer en premier (6 formules)

| ID | Vecteur | Formule | Source primaire | Application Muninn |
|----|---------|---------|----------------|-------------------|
| V2B | Primate | TD-Learning delta | Schultz, Dayan, Montague (1997) Science 275:1593 | delta module poids mycelium. Recall reussi (delta>0) = renforce. Inutile (delta<0) = accelere decay |
| V5B | Abeille | Cross-inhibition | Seeley et al. (2012) Science 335:108 | Upgrade -beta*w^2. Deux branches en competition, la meilleure gagne |
| V6A | Elephant | Emotional tagging E(a) | Richter-Levin & Akirav (2003) Brain Res Rev 43:247; Frey & Morris (1997) Nature 385:533 | Arousal multiplie poids initial encodage. Hill function gate |
| V6B | Elephant | Valence-modulated decay | Talmi (2013) Curr Dir Psych Sci 22:430; McGaugh (2004) Trends Neurosci 27:456 | h = h_base * (1 + alpha_v*|v| + alpha_a*a). Upgrade direct Ebbinghaus |
| V10A | Chien | VADER sentiment | Hutto & Gilbert (2014) ICWSM | compound = sum(s_i*w_i)/sqrt(sum^2+15). Rule-based, zero LLM. Capteur pour V6 |
| V7B | Fourmi | ACO pheromone | Dorigo, Maniezzo, Colorni (1996) IEEE Trans SMC-B 26:29 | p_ij = tau^a * eta^b / sum. Combine historique + pertinence locale (boot les separe, ACO fusionne) |

#### TIER A — Fort potentiel (6 formules)

| ID | Vecteur | Formule | Source primaire | Application Muninn |
|----|---------|---------|----------------|-------------------|
| V3B | Corbeau | Bayesian ToM | Baker, Saxe, Tenenbaum (2009) Cognition 113:329 | P(goal|actions) = profil utilisateur. Infere le goal depuis les queries |
| V4B | Dauphin | EWC | Kirkpatrick et al. (2017) PNAS 114:3521 | Fisher importance sur decay: h *= (1+F_i). Noeuds critiques decayent lent |
| V9A+ | Planaire | Bioelectric Levin | Shomrat & Levin (2013) J Exp Biol 216:3799; Levin (2012) BioEssays 34:205 | **Fact-level regeneration**: dead branch tagged facts (D>/B>/F>/E>/A>) extracted from .mn and injected into closest survivor via mycelium proximity. Tags also diffuse (original V9A). 12 bornes, zero API. Metric: factual survival rate after prune() |
| V9B | Planaire | Reed-Solomon | Reed & Solomon (1960) JSIAM 8:300 | Redondance n/k. Survit a perte de (n-k)/2 noeuds. Zero protection actuelle dans Muninn |
| V11B | Baleine | Boyd-Richerson 3 biases | Boyd & Richerson (1985) Culture & Evolutionary Process, U Chicago Press | Conformiste + prestige + guide. Auto-organisation poids sans superviseur |
| V3A | Corbeau | Transitive inference | Wynne (1995) J Exp Psych Anim 21:166; Paz-y-Mino et al. (2004) Nature 430:778 | Fermeture transitive A->B->C avec decay beta^distance. Spreading sans ORDRE |

#### TIER B — Utile secondaire (4 formules)

| ID | Vecteur | Formule | Source primaire |
|----|---------|---------|----------------|
| V5A | Abeille | Quorum Hill switch | Dockery & Keener (2001) Bull Math Biol 63:95 |
| V8B | Chauve-souris | Active sensing | Yang, Wolpert, Lengyel (2016) Curr Opin Behav Sci 11:100 |
| V10B | Chien | Russell circumplex | Russell (1980) J Pers Soc Psych 39:1161 |
| V1A | Pieuvre | Coupled oscillator | Yekutieli et al. (2005) J Neurophysiol 94:1443 |

#### TIER C — Doublons ou metriques (6 formules, pas d'implementation)

V1B Laplacien consensus (Olfati-Saber 2004) = on a deja. V2A Scaling (Herculano-Houzel 2009) = metrique.
V4A Unihemispheric (Rattenborg 2000) = archi pas formule. V7A Response threshold (Theraulaz 1998) = sigmoid.
V8A Echolocation (Simmons 1989) = TF-IDF. V11A Song SI (Garland 2011) = BARE Wave.

#### Echecs connus (13 papiers negatifs = temps economise)

| Formule | Echec | Source |
|---------|-------|--------|
| V1A octopus | 2D only, fails 3D | Hanassy et al. (2015) J Exp Biol |
| V1B consensus | Byzantine faults | LeBlanc et al. (2013) IEEE TAC |
| V2A scaling | Fails cetaceans | Mortensen et al. (2014) Frontiers |
| V2B TD | Misses dopamine ramp | Howe et al. (2013) Nature |
| V3A transitive | Simple association? | Vasconcelos (2008) Animal Behaviour |
| V4B EWC | >10 tasks, Fisher crude | Huszar (2018) arXiv:1801.01423 |
| V5B cross-inhib | Deadlock >5 options | Pais et al. (2013) J R Soc Interface |
| V6A emotional tag | Yerkes-Dodson inverted-U | Bergado et al. (2011) |
| V6B valence decay | Fading affect bias | Walker & Skowronski (2009) Mem & Cogn |
| V7A threshold | Over-predicts rigidity | Charbonneau et al. (2013) Behav Ecol |
| V7B ACO | Premature convergence | Stutzle & Hoos (2000) FGCS |
| V10B circumplex | Culturally biased | Gendron et al. (2014) Psych Sci |
| V4A unihemispheric | Coupling unknown | Mascetti (2016) Sleep Med Rev |

#### 3 Carmack Moves identifies (ponts que personne n'a faits)

1. **V9 Planaire -> graph repair** (Ygg cos=-0.001, AUCUN pont dans 65K concepts, zero litterature)
2. **V6 Emotional memory -> graph database** (Ygg cos=-0.015, zero pont)
3. **V1 Pieuvre -> distributed memory control** (Ygg cos=-0.017, zero pont)

#### Validation Yggdrasil — signaux spectraux

Scan 36 paires de concepts sur 65K OpenAlex:
- Signaux forts: amygdala×episodic cos=0.695 (V6 confirme), cognition×emotion cos=0.750 (V10 confirme)
- Signaux moderes: primate×RL cos=0.251 (V2 pont), swarm×ranking cos=0.469 (V5 confirme)
- P4 purs: planarian×distributed cos=-0.001 (V9), cephalopod×distributed cos=-0.017 (V1)
- Faux amis: "active learning"=e-learning, "online learning"=e-learning, "error correction"=econometrie

### Immune System Layer — Recherche (session 2026-03-11) [TODO]

Origine: convergence V9A+ (Levin 2013) avec immunologie computationnelle.
Question: les maths du systeme immunitaire apportent quoi de NOUVEAU a Muninn?

#### 5 modeles evalues, 3 retenus

| Modele | Source primaire | Verdict | Raison |
|--------|---------------|---------|--------|
| Danger Theory (DCA) | Matzinger (1994) Annu Rev Immunol 12:991; Greensmith, Aickelin & Cayzer (2005) ICARIS LNCS 3627:291 | **NOUVEAU — axe orthogonal** | Protection par contexte de session (stress), pas par contenu. Rien dans Muninn ne fait ca. |
| Immune Network (suppression) | Jerne (1974) Ann Immunol 125C:373; Perelson (1989) Immunol Rev 110:5; Farmer, Packard & Perelson (1986) Physica D 22:187 | **NOUVEAU — auto-dedup continu** | Branches similaires se suppriment mutuellement. Remplace le batch NCD de sleep_consolidate par un mecanisme continu. |
| Negative Selection | Forrest, Perelson, Allen & Cherukuri (1994) IEEE S&P:202 | **NOUVEAU — sante memoire** | Self-model detecte branches corrompues/anormales. Zero introspection actuellement. |
| CLONALG (Clonal Selection) | de Castro & Von Zuben (2002) IEEE Trans Evol Comput 6:239 | SKIP — couvert | Ebbinghaus + L10/L11 reconsolidation couvrent deja keep/kill + recompression. |
| ODE idiotypique | Farmer, Packard & Perelson (1986) Physica D 22:187 | SKIP — trop lourd | Mycelium + spreading activation + decay = meme espace fonctionnel. |

#### Formules retenues

**I1 — Danger Theory: session danger score (Matzinger 1994, Greensmith 2005)**

Papier: Matzinger P. "Tolerance, danger, and the extended family." Annu Rev Immunol 1994;12:991-1045.
Algo: Greensmith J, Aickelin U, Cayzer S. "Introducing Dendritic Cells as a Novel Immune-Inspired Algorithm for Anomaly Detection." ICARIS 2005, LNCS 3627:153-167.

```
session_danger = w1 * error_rate + w2 * retry_loops + w3 * topic_switches + w4 * (1 - rle_ratio)

  w1=0.4, w2=0.3, w3=0.2, w4=0.1 (defauts, calibrables)
  error_rate    = lignes E> / lignes totales dans le transcript
  retry_loops   = boucles debug detectees par Semantic RLE (P26, existe deja)
  topic_switches = changements de sujet (nombre de ## headers ou pivots semantiques)
  rle_ratio     = ratio Semantic RLE (13msg->5 = 0.38 = chaotique = danger)

Effet sur la branche:
  h_boosted = h * (1 + gamma * session_danger)     gamma=1.0 defaut

  h = demi-vie Ebbinghaus (Settles & Meeder 2016)
  session danger haute → h augmente → branche survit plus longtemps
  session safe → h inchange → decay normal
```

Injection: `_ebbinghaus_recall()` ligne 419. ~10 lignes. Session danger calcule dans feed_from_hook().

**I2 — Suppression competitive: recall adjustment (Perelson 1989)**

Papier: Perelson AS. "Immune Network Theory." Immunol Rev 1989;110:5-36.
Modele original: dx_i/dt = c*(sum(m_ij*x_j) - sum(s_ik*x_k)) - k*x_i

```
Pour chaque branche i:
  suppression_i = alpha * SUM( sim(i,j) * recall_j )   pour tout j != i ou NCD(i,j) < 0.4

  recall_effectif_i = max(0, recall_i - suppression_i)

  alpha = 0.1 (force de suppression, defaut)
  sim(i,j) = 1 - NCD(i,j)   (NCD = Normalized Compression Distance, Cilibrasi & Vitanyi 2005)
  seuil NCD < 0.4 = branches tres similaires seulement
```

Effet: deux branches quasi-identiques → la plus faible perd du recall → meurt plus vite → auto-dedup.
Injection: `prune()` ligne 3244, avant classification hot/cold/dead. ~20 lignes.
NCD existe deja: `_ncd()` ligne 698.

**I3 — Negative Selection: memory health check (Forrest 1994)**

Papier: Forrest S, Perelson AS, Allen L, Cherukuri R. "Self-Nonself Discrimination in a Computer." IEEE Symposium on Security and Privacy, 1994:202-212.

```
Phase 1 — construire le self-profile (une fois, dans status ou diagnose):
  self = {
    token_density:  median( tokens_par_ligne pour toutes branches ),
    fact_ratio:     median( lignes_taguees / lignes_totales ),
    line_count:     median( nombre_de_lignes ),
  }

Phase 2 — detecter les anomalies (dans prune ou boot):
  distance(b, self) = SUM( |b.metric - self.metric| / self.metric )

  anomaly(b) = 1  si  distance(b, self) > theta    theta=2.0 defaut (2x la mediane)
               0  sinon
```

Effet: branches corrompues, compression ratee, ou drift structure → flaggees avant qu'elles polluent boot().
Injection: `prune()` ou `boot()` comme health check. ~15 lignes.
Utilise: `_count_tokens()` (existe), tag detection (existe).

#### Estimation effort

| Formule | Lignes de code | Fonctions touchees | Dependances |
|---------|---------------|-------------------|-------------|
| I1 Danger Theory | ~10 | _ebbinghaus_recall(), feed_from_hook() | Semantic RLE (P26, existe) |
| I2 Suppression | ~20 | prune() | _ncd() (existe) |
| I3 Negative Selection | ~15 | prune() ou boot(), status | _count_tokens() (existe) |
| **Total** | **~45 lignes** | | **Zero nouvelle dependance** |

#### Ce que ca change au pitch

Aucun systeme de memoire LLM n'a de couche immunitaire:
- Mem0, Letta, Zep: stockent ou oublient. Pas de triage par stress de session.
- MemOS: Memory OS, mais pas d'auto-diagnostic sante.
- Personne ne fait de suppression competitive continue entre unites de memoire.

Muninn aurait: compression (L0-L11) + cerveau (Bio-Vectors) + systeme immunitaire (I1-I3).
Le seul moteur de memoire qui se protege, se diagnostique, et adapte sa survie au contexte.

### AUDIT SENIOR DEV (session 2026-03-11) [DONE]

Audit brutal: chaque feature verifiee dans le code, pas dans les docs.
Resultat: 5 phases de remediation executees, 229+ bornes PASS, 0 FAIL.

#### Verdicts Bio-Vectors apres remediation

| Verdict | Vecteurs | Status |
|---------|----------|--------|
| **REAL** (11) | V2B, V4B, V5B, V7B, V9A, V9B + V1A, V3A, V3B, V5A, V11B (boosted) | Coefficients reels |
| **ACTIVE** (3) | V6A, V6B, V10A | VADER installe, pipeline actif |
| **WIRED** (1) | V10B Circumplex | Branche dans session_index |
| ~~COSMETIC~~ | 0 | Tous boostes en Phase 3 |
| ~~DORMANT~~ | 0 | Tous actives en Phase 1 |
| ~~PHANTOM~~ | 0 | V10B wire en Phase 2 |

#### 5 phases executees

- [x] **PHASE 1**: pip install vaderSentiment → V6A+V6B+V10A actifs
- [x] **PHASE 2**: Fix V8B scored init, V10B wire circumplex, A5 doc as diagnostic
- [x] **PHASE 3**: Boost V1A x100, V3A x2, V3B sigmoid fix, V5A x2.7, V11B x3-7
- [x] **PHASE 4**: 10 biovector tests + C2/C3 remplaces par tests PROD (40+ bornes)
- [x] **PHASE 5**: 9 silent except:pass → stderr, dead code removed (effective_budget, COMPRESSION_BY_TEMP)

Commits: 1f1f86f, daf6845, 0cea991, 26b42f6, cf43e8f

### AUDIT V9 DEEP SCAN (session 2026-03-14) [DONE]

Audit profond mode senior dev: 34 bugs trouves (4 HIGH, 14 MEDIUM, 16 LOW).
Tous corriges + 11 tests battery corriges + L9 API valide.
Battery V4 post-V9: 81 PASS, 0 FAIL, 3 SKIP.

#### HIGH (4) — crashes et data loss
- H1: prune() KeyError apres sleep_consolidate (guard `if name not in nodes`)
- H2: id_to_name reconstruit O(N*M) dans observe() P41 loop (deplace hors boucle)
- H3+H4: missing commit() dans upsert_connection, upsert_fusion, delete_connection, update_connection_count, add_zone_to_edge

#### MEDIUM (14) — logique incorrecte et silent fails
- M1: _line_density max->min (cap not floor), M2: causal regex trailing spaces
- M3: R1-Compress fallback min 2 chunks, M4: last chunk >=1 not >=4
- M5: missing branch file -> continue not break, M6: winter_tree SQLite count
- M7: adapt_k throwaway Mycelium removed, M8: feed_history tracking by path
- M9: query_ids init, M10: _adj_cache invalidation, M11-M12: missing commits
- M13: IntegrityError not sqlite3.Error, M14: PRAGMA foreign_keys=ON

#### LOW (16) — edge cases et inconsistances
- L1: except scope, L2: regex anchors, L3: blind_spots count, L4: variable shadow
- L5: doc mismatch, L6: chars/token estimate, L7: line_counts source, L8: local budget (OK)
- L9: double-close fd, L10: ingest ratio tiktoken, L11: decay threshold 0.01
- L12: min word length 3, L13: CLI SQLite mode, L14: REPLACE->UPSERT migration
- L15: CAST integer comparison, L16: fused_at update

#### Tests battery corriges (11)
T1.1 format JSONL, T1.7 fusion API, T1.10 pipe format, T2.1 code block size,
T3.2 skeleton match, T4.2 import names, T4.4 sigmoid check, T4.9 isolated format,
T4.11 edge threshold, T4.12 get_fusions API, T12.2 corrupted .mn tolerance

### AUDIT V9B — SKIP->PASS + Deep Bug Scan (session 2026-03-14) [DONE]

3 SKIP convertis en vrais tests + 7 bugs trouves par scan profond, tous corriges.
Battery V4 finale: 50 PASS, 0 FAIL, 0 SKIP.

#### Tests SKIP -> PASS (3)
- T13.3: P20c Virtual Branches — cree 2 repos temp, registre remote, boot verifie branch virtuelle chargee
- T13.4: V8B Active Sensing — 3 branches similaires, verifie v8b_clarify dans last_boot.json
- T13.7: C4 Real-Time k Adaptation — teste detect_session_mode + adapt_k (divergent/convergent/balanced)

#### MEDIUM (5) — logique incorrecte et data loss silencieux
- B1: pull_from_meta SQLite sans query = 0 fusions tirees (dict vide stub) -> tire top par strength
- B2: meta sync MAX(count) empechait decay de se propager -> last-writer-wins
- B3: batch_delete_connections commit mid-transaction (perte atomicite) -> inline DELETE
- B4: sleep_consolidate NCD grouping transitif (A~B+A~C fusionnes meme si B!~C) -> verif ALL members
- B5: _append_session_log split R: sur \n\n corrompait root.mn -> split sur ## header

#### LOW (2)
- B6: \ba\b filler strip mangeait "a" dans math/code (a+b) -> strip seulement comme article anglais
- B7: double conn.close() dans mycelium.py init -> supprime

### Senior Dev Battery V9C (session 2026-03-14) [DONE]

40 tests mode cassage de gueule couvrant toutes les fonctions non testees.
3 vrais bugs trouves + corriges pendant l'ecriture des tests.
Total: 90 tests (50 Battery V4 + 40 Senior), tous PASS.

#### Tests (40, 8 categories)
- S1-S5: extract_facts, compress_line edge cases (vide, 10K chars, CJK, Arabic, emoji, math)
- S6-S10: semantic_rle, malformed JSONL, format detection, JSON/MD parsers
- S11-S15: build_tree (petit/gros), generate_root_mn, scan_repo, verify_compression
- S16-S20: boot stress (vide, corrompu, state leak, 50 branches, auto-continue P23)
- S21-S25: prune (0 branches, tout chaud, tout froid, consolidation, ingest)
- S26-S30: mycelium stress (500 concepts, decay, batch ops, date roundtrip, fusions)
- S31-S35: securite (6 patterns secrets), unicode E2E, tree.json corrompu, .mn binaire
- S36-S40: pipeline E2E complet, cue_distill+extract_rules, inject, recall, decode roundtrip

#### Bugs trouves et corriges (3)
- B8: secret pattern ghp_ trop strict (36+ -> 20+) laissait passer tokens courts
- B9: secret pattern sk- ne matchait pas tirets (sk-ant-api03-...) -> [A-Za-z0-9\-._]
- B10: _detect_transcript_format ne reconnaissait pas JSONL 1 ligne ni JSON chat_messages

### AUDIT V9D — Tree Architecture Fix (session 2026-03-14) [DONE]

5 bugs architecturaux dans le cycle pousse/taille de l'arbre.
L'arbre avait explose a 2176 branches de bruit (median 13 lignes, 501 branches <= 5 lignes).
Root cause: `compress_section()` strippait les `## headers`, `grow_branches()` les attendait,
le fallback creait des branches arbitraires sans seuil minimum, et `prune()` n'etait jamais
appele automatiquement. Rebuild one-shot: 2176 → 10 branches propres.
Total: 102 tests (50 V4 + 40 Senior + 12 Tree Fixes), tous PASS.

#### Bugs (5)
- B11: fallback seuil `>=1` au lieu de `>=4` — creait des branches de 2-3 lignes (poussiere)
- B12: compress_transcript n'emettait pas de `## headers` — grow_branches tombait toujours dans le fallback
- B13: pas de cap sur les branches — 2176 branches sans limite
- B14: prune() ne nettoyait pas les branches <= 3 lignes (minimum viable = 4 lignes)
- B15: prune() jamais appele automatiquement — l'arbre poussait sans etre taille

#### Fixes
- B11: restore `>=4` dans grow_branches fallback (commit 341e59e)
- B12: compress_transcript emet `## header` avant chaque section compressee (commit 162cc8a)
- B13: cap a 200 branches dans grow_branches, coldest removed (commit 0753f0b)
- B14: prune() classifie branches <= 3 lignes cold comme dead (commit f10e9ad)
- B15: `_light_prune()` — prune leger (50ms, zero API) appele dans feed_from_hook quand branches > 150 (commit a1d394a)

#### Tree rebuild (one-shot)
2176 branches (fallback garbage) → backup → re-grow depuis 10 sessions .mn → 10 branches propres.
Merge NCD correct: 8/10 sessions ont merge dans les branches existantes (contenu similaire).

#### Tests (12, fichier tests/run_tree_fixes.py)
- T1-T3: B11 — pas de branche < 5 lignes, edge cases 4/5 lignes
- T4-T6: B12 — ## headers survivent compression + P26 dedup + L10/L11
- T7-T9: B13 — cap 250→200, hottest survivent, pas de fichiers orphelins sur disque
- T10-T12: B14 — dust cold meurt, dust hot survit, empty tree no crash

#### Analyse comparative SOTA (sources internet 2024-2026)

Ce que Muninn fait qui est valide par la recherche:
- Sleep consolidation (prune) → valide par LightMem (ICLR 2026, arxiv 2510.18866)
- Pipeline Storage→Reflection→Experience (L0→L1-L7→L10/L11) → valide par survey "From Storage to Experience" (Preprints.org Jan 2026)
- L10 Cue Distillation basee sur connaissance parametrique LLM → unique, personne d'autre ne fait ca
- NCD dedup → similaire au threshold 0.85 de Mem0 (arxiv 2504.19413) et CrewAI
- Spreading Activation retrieval → Collins & Loftus, utilise par plusieurs systemes 2025
- Structured tree memory → valide par StructMemEval (arxiv 2602.11243, Feb 2026) et A-MEM (NeurIPS 2025)

Ce que Muninn fait que personne d'autre ne fait:
- Compression regex pure (zero LLM cost, instantane) — tous les autres utilisent LLM summarization
- Living mycelium codebook (abbreviations apprises par co-occurrence)
- Federated cross-repo memory sharing (meta-mycelium)

Ce que la recherche suggere pour plus tard (non implemente):
- Multi-granularite adaptive (MemGAS 2025): router query vers root OU branches selon le niveau de detail necessaire
- Zettelkasten linking (A-MEM, NeurIPS 2025, arxiv 2502.12110): liens bidirectionnels entre branches
- Graph memory (Mem0[g]): relations explicites entre memories (le mycelium fait les connexions mais pas entre branches)

Verdict: Muninn est aligne avec le SOTA sur l'architecture (hierarchique, consolidation, retrieval multi-signal).
L'avantage unique = regex compression (x143 sur transcripts, 10s vs 17min, $0.00 vs $0.35).
Le LLM builder moyen fait du summarization API. Sky fait du regex. C'est 1000x moins cher et plus rapide.
Les features manquantes (multi-granularite, Zettelkasten) sont des optimisations de retrieval, pas des bugs.

### P21 — PyPI publish [TODO]
- [x] pyproject.toml + setup (FAIT, ligne 516)
- [x] Entry points CLI: muninn + mycelium (FAIT)
- [x] pip install -e . teste OK (FAIT)
- [ ] Publier sur PyPI (pas encore fait)

### Concurrence mise a jour (mars 2026)
- Mem0 (90K stars, $24M YC): graph+vector+KV, memory taxonomy, hosted service
- MemOS v2.0 "Stardust": Memory OS, MemCube abstraction, 159% vs OpenAI memory
- Claude-Mem (21.5K stars): SQLite + Claude API, ~x10, hooks lifecycle
- SimpleMem (jan 2026): semantic lossless, +26.4% F1, 30x fewer tokens
- Always On Memory Agent (Google, mars 2026): SQLite + Gemini, no vector DB
- LongCodeZip (ASE 2025): coarse-then-fine pour code, x5.6
- EHPC (NeurIPS 2025 Spotlight): evaluator heads, +40% QA, training-free
- PCToolkit (IJCAI 2025): benchmark standard prompt compression

Ce que Muninn a que les autres n'ont pas:
- 11 couches empilees (regex + LLM), pas juste 1 technique
- Mycelium vivant (codebook qui apprend par co-occurrence)
- L-system fractal (memes regles a chaque niveau)
- Secret filtering
- Zero dependance obligatoire (L1-L7 regex only), GPU et API optionnels
- Bootstrap one-command (mycelium + root.mn + WINTER_TREE + hooks)

## Pivots de la session 2026-03-06

### Pivot 1 — Sinogrammes = mauvais chemin
Les sinogrammes chinois coutent 2-3 tokens chacun.
Un mot anglais court = 1 token.
Le modele Enigma (substitution 1:1) ne compresse pas, il chiffre.
On veut compresser, pas chiffrer.
Format optimal = anglais compact natif BPE.

### Pivot 2 — Le Mycelium
L'arbre (tree) = structure statique. Le mycelium = reseau vivant.
Tracker de co-occurrences entre concepts, pousse a chaque session,
persiste sur disque. Le mycelium EST le codebook — vivant, pas statique.
Inspire du mycelium d'Yggdrasil (co-occurrences dans 348M papers).

### Pivot 3 — Chirurgien vs Boucher
Les createurs de LLMs sont des chirurgiens qui n'ont pas le probleme.
Les bouchers ont le probleme mais pas les outils.
Muninn = premier outil construit depuis le cote boucher.

## Refs
- Lindenmayer (1968) — L-Systems
- Prusinkiewicz (1990) — Algorithmic Beauty of Plants
- Park et al. (2023) — Generative Agents: memory scoring (recency + importance + relevance)
- Packer et al. (2023) — MemGPT: virtual context management (OS metaphor)
- LLM-Codebook (2025) — codebooks appris > codebooks manuels
- Huff-LLM (2025) — Huffman sur poids LLM
- GQ-VAE (2025) — tokenization variable-length
- LLMLingua (2024) — compression de prompts par self-information
- KVzip (2025) — KV-cache compression x3-4 (modele-side, complementaire Muninn)
- Bartlett (1932) — Schema Theory: memory stores schemas + deviations, not verbatim
- Rao & Ballard (1999) — Predictive Coding: brain stores only prediction errors
- LAMA Probes (Facebook 2019) — cloze tests for parametric knowledge assessment
- Selective-Context (EMNLP 2023) — self-information pruning (token-level, syntactic)
- Prompt Compression Survey (NAACL 2025) — taxonomy: hard/soft prompt methods
