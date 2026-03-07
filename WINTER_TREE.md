# MUNINN — Winter Tree (Baobab)

Type: Baobab (gros tronc, petites branches)
Phase: CROISSANCE — le tronc est trouve, on fait pousser
Etat: 26 briques vivantes (P0-P28), 2 en roadmap (P20-P21), 3 supprimees (P3), 14 bugs corriges (P10)

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
| B2 | muninn.py v0.9 | OK | Moteur: 9 couches compression + retrieval intelligent (TF-IDF + scoring) |
| B4 | tree.json | OK | Enrichir: hash, temperature |
| B5 | *.mn files | OK | Memoire vivante |
| NEW | mycelium.py | OK | Tracker co-occurrences, fusion, decay |
| B9 | docs/ | OK | LITERATURE.md enrichi (15+ papiers) |
| B10 | ci.yml | OK | Tests: tree, engine, mycelium, feed |
| NEW | .claude/settings.local.json | OK | Hooks PreCompact + SessionEnd -> feed + compress |
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

#### Brique 2 : LLMLingua-2 comme Layer 8 [FAIT — a optimiser]
- [x] pip install llmlingua (BERT ~1 GB, CPU, zero API)
- [x] Integre comme couche 8, singleton cache, skip si <2K chars
- ATTENTION: sur texte pre-compresse, L8 perd 72% des faits (rate=0.5)
- TODO: ajuster le rate ou changer l'ordre (L8 avant L1-L7)

#### Brique 3 : Resume LLM comme Layer 9 [FAIT — TESTE]
- [x] Claude Haiku resume via API Anthropic (pip install anthropic)
- [x] Fallback gracieux si pas de cle API ou pas de SDK
- [x] Seuil: seulement si >4K chars
- [x] L9 ajoute a compress_file (pas seulement compress_transcript)
- [x] Fallback registre Windows pour API key (setx != process env)
- [x] Teste sur OpenAlex: 50 papers x5.2 ($0.024), 306 papers x4.0 ($0.13)
- [x] SOL.md full pipeline L1-L7+L9: x7.7 (20K->2.6K chars)
- [x] Bootstrap HSBC: x5.4 moyen (LOGIQUE x9.6, METHODOLOGIE x13.8, ARBRE x11.4)

Pipeline complet (9 couches):
  L1: markdown strip | L2: filler words | L3: phrase compression
  L4: number shortening | L5: universal rules | L6: mycelium
  L7: fact extraction | L8: LLMLingua-2 (BERT) | L9: LLM self-compress

Concurrence connue:
- Claude-Mem (21K stars): SQLite + Claude API, x10, pas d'arbre ni mycelium
- Letta Code (ex-MemGPT): git-backed markdown, agent complet
- LLMLingua-2 (Microsoft): BERT scorer, x3-20, pas de persistance
- ACON: gradient-free compression guidelines, -26-54% tokens

Ce que Muninn a que les autres n'ont pas:
- 9 couches empilees (regex + BERT + LLM), pas juste 1 technique
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
  - Recency: decay lineaire 90j depuis last_access
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

### P20 — Mycelium cross-repo [TODO — GROS]
- [ ] Meta-mycelium: merge les fusions de tous les repos bootstrappes
- [ ] Quand on bosse sur repo A, concepts de repo B disponibles
- [ ] Les "lianes" entre projets (cf CROSS_PROJECTS_ROADMAP Yggdrasil)

### P21 — pip install muninn [TODO — GROS]
- [ ] pyproject.toml + setup
- [ ] Entry point CLI: `muninn bootstrap .`
- [ ] README install instructions
- [ ] Publier sur PyPI

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
- 9 couches empilees (regex + BERT + LLM), pas juste 1 technique
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
