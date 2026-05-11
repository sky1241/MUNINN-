# BATTLE PLAN FINAL PROD v3 — 2026-05-09 (post-9-agents deep audit)

Synthèse de **9 agents en parallèle** lancés après H1-H5.2. Objectif Sky : "le vrai deep audit final, ce qui est réellement en prod, mis à jour."

---

## TL;DR

**Verdict général : prod-grade pour vente B2B AVEC asterisque.** 8/9 agents convergent vers la même observation : code propre, sécu sérieuse, tests solides, CI vert — **mais** quelques drifts visibles à un audit acheteur de 5 minutes (duplication, doc qui ment sur les chiffres, PyPI cassé).

**8 commits H1-H5.2 confirmés en production** (`d6a5fc3` → `81e8703`). 2328/2563 tests run en CI (90.83 %). 0 xfail. Q-modularity 0.673 (good).

---

## 🚨 BLOCKERS (impact production direct, à fixer AVANT de vendre)

### B1. forge-shield PyPI cassé
- **Trouvé par agent web** : `pip download forge-shield` retourne "No matching distribution found" malgré v1.1.0 listée sur PyPI. CLAUDE.md affirme "PyPI binary depuis 2026-05-09" — **faux aujourd'hui**.
- **Local** : 1.1.0 (PyPI), **CI** : 1.1.1 (git tag). Sky tourne donc une version qui peut diverger des property tests CI.
- **Action** : (a) re-uploader les wheels forge-shield 1.1.0+1.1.1 sur PyPI, (b) bumper local `pip install -U git+https://github.com/sky1241/forge.git@v1.1.1`, (c) corriger CLAUDE.md si la PyPI ne sera pas réparée ce mois.
- **Effort** : 30-60 min (cousin pc1) + 1 min local.

### B2. BUG-091 : 3 fichiers md5-identiques + vault.py divergence
- **Trouvé par agents BUGS + architecture** : `cube.py` (1558L), `cube_providers.py` (2124L), `lang_lexicons.py` (1007L) sont **byte-pour-byte identiques** entre `engine/core/` et `muninn/`. Pas des shims, des duplications brutes. **8642L de dette pure visible à un audit.**
- **muninn/vault.py diverge déjà** : `sha256.hexdigest()[:16]` vs engine/core `[:32]`, et le H1 bytearray fix manque côté muninn. **BUG-091 récurre déjà.**
- **BUGS.md contradiction interne** : header ligne 16 dit "fixed via Phase A→D shim refactor", body lignes 448 + 462 disent "OPEN". À reclassifier en **PARTIAL FIX** avec liste explicite.
- **Action** :
  1. Reclassifier BUG-091 PARTIAL dans BUGS.md (5 min)
  2. Choisir une version canonique pour vault.py + faire shim côté muninn/ (30 min)
  3. Convertir cube.py, cube_providers.py, lang_lexicons.py en shims côté muninn/ (1.5h)
- **Effort total** : ~2h, ROI maximal pour B2B (visible immédiatement).

### B3. Model hallucination dans scanner/llm_scanner.py
- **Trouvé par agent web** : `engine/core/scanner/llm_scanner.py:47` utilise `claude-haiku-4-20250414` qui **n'existe pas** dans la doc Anthropic officielle. Probablement une string fictive de test devenue prod.
- **Action** : remplacer par `claude-haiku-4-5-20251001` (ID officiel mai 2026).
- **Effort** : 2 min.

---

## ⚠️ HIGH (qualité production / vente B2B)

### H1. Bumps dépendances majeurs

| Lib | Installé | Latest | Pourquoi bumper |
|---|---|---|---|
| **anthropic** | 0.96.0 | 0.100.0 | 4 versions de retard. v0.97 = CMA Memory public beta (concurrent direct), v0.95 = breaking change Bedrock auth, v0.100 = managed agents multi-agents |
| **cryptography** | 46.0.7 | 48.0.0 | CVE-2026-39892 déjà patché en 46.0.7, mais 48.0.0 ajoute des améliorations |

- **Action** : `pip install -U anthropic cryptography` + tests + commit.
- **Effort** : 30 min (incluant tests de régression sur les 6 modules qui importent anthropic).

### H2. Constraints.txt sous-pinné
- **Trouvé par agent security** : seuls tiktoken==0.12.0 et anthropic==0.96.0 sont pinnés. **cryptography, urllib3, requests, PyYAML, hypothesis** dérivent. Installation reproductible incomplète.
- **Action** : ajouter pins pour les 5 libs critiques.
- **Effort** : 10 min.

### H3. pip-audit en CI
- **Trouvé par agent security** : aucun scanner CVE en CI. Sans ça, claim "secure deps" est non-vérifié.
- **Action** : `pip install pip-audit` + ajouter step CI `pip-audit -r requirements.txt -c constraints.txt --strict`.
- **Effort** : 15 min.

### H4. CHANGELOG + README chiffres mentent
- **Trouvé par agent docs** : CHANGELOG ligne 3 dit `cube_providers.py 1244` mais réel = **2124L** (+880L drift !). README dit "27 subcommands" mais argparse a 29. README dit "muninn.py 2104" mais réel = 2187.
- **Action** : régénérer la ligne via `wc -l engine/core/*.py` et les compteurs README.
- **Effort** : 15 min.

### H5. WINTER_TREE.md stale 17 jours
- **Trouvé par agent docs** : entête dit "Mis à jour 2026-04-22, Engine ~22K lignes, 18 fichiers". Réel : 25K, 23 fichiers. CLAUDE.md référence ce doc qui ment.
- **Action** : (a) banner `> ⚠️ STALE — see CHANGELOG.md` (1 min) ou (b) régénérer (15 min).

### H6. Models clients exposent encore claude-opus-4-6
- **Trouvé par agent web** : `cube_providers.py`, `muninn/ui/ai_config.py` exposent `claude-opus-4-6` au lieu du flagship actuel `claude-opus-4-7`.
- **Action** : ajouter `claude-opus-4-7` à la liste, garder 4-6 en legacy.
- **Effort** : 5 min.

### H7. CI deps Node 20 deprecated juin 2026
- **Trouvé par agent CI** : `actions/checkout@v4` + `actions/setup-python@v5` sont sur Node 20, deprecated. **2 PRs Dependabot ouvertes** prêtes à merger.
- **Action** : merger PR #1 + PR #2 (vérifier en local que ça passe). Optionnellement ajouter cache pip + concurrency + timeout-minutes.
- **Effort** : 30 min total avec les 3 best practices.

### H8. CI 187 tests jamais collectés
- **Trouvé par agent tests** : `test_chunk_a7_hook_integrity.py` (14 tests) ignored en CI. Soit on le fixe pour CI, soit on le retire. Les `eval_harness_chunk*` ignored sont cosmétiques (0 tests inside, mais le flag est OK).
- **Action** : décider — fix (rendre manifest installable en GHA) ou suppression. Si suppression, retirer le `--ignore` de ci.yml.
- **Effort** : 30-90 min selon décision.

---

## 📊 MEDIUM (dette architecturale, à attaquer cette semaine)

### M1. boot() 656L = monstre architectural #1
- **Trouvé par agent architecture** : `engine/core/muninn_tree.py:1204 boot()` fait **656 lignes**. Top 1 fonction monstre. `muninn_tree.py` a aussi le top Wavelet 11.1M (instabilité énorme).
- **Action** : extract method en série — `_load_root`, `_load_branches`, `_inject_session_recall`, `_surface_known_errors`. Forge --gen-props avant/après.
- **Effort** : 2-3h.

### M2. cube_providers.py split par provider (4 modules)
- **Trouvé par agent architecture** : `cube_providers.py` 2124L = top Carmack 0.470. Contient OllamaProvider, AnthropicProvider, OpenAIProvider, MockProvider. Splittable proprement en 4 fichiers ~400-500L.
- **Action** : extract chaque provider dans son propre fichier sous `engine/core/providers/<name>.py`. Façade `cube_providers.py` qui ré-export.
- **Effort** : 3-4h.

### M3. H6 split mycelium.py (re-évalué honnêtement)
- **Trouvé par agent mycelium** : 6-9h vraiment, pas 3-5h. 5 sous-modules naturels (Core, Zones, Activation, Dream, Meta). 320 tests référencent Mycelium → audit imports +1-2h. Non urgent : mycelium pas top 5 carmack.
- **Action** : reporter mais pas oublier. Dédier une session dédiée.
- **Effort** : 6-9h en mode focused.

### M4. 10 méthodes mycelium orphelines (~250L)
- **Trouvé par agent mycelium** : `observe_with_concepts`, `adaptive_fusion_threshold`, `adaptive_decay_half_life`, `cleanup_orphan_concepts`, `cleanup_orphan_zones`, `vacuum_if_needed`, `effective_weight`, `adaptive_hops`, `get_zones`, `get_bridges`. Plan de wire pour chacune.
- **Action** : itérer 1 par 1 dans une session dédiée (style H3).
- **Effort** : 3-4h pour les 10.

### M5. 14 docs obsolètes à archiver
- **Trouvé par agent docs** : `BATTLE_PLAN_BUG091`, `BATTLE_PLAN_AUDIT2/3`, `CI_PROPOSED_*`, `BRANCHEMENT_FORGE_v1.1.1`, `HANDOFF_*`, `COUSIN_PROMPT`, `BENCHMARK_*` (mars), `TIER1/2/3_*`, etc.
- **Action** : `mkdir docs/archive/ && git mv <14 fichiers>`.
- **Effort** : 10 min.

### M6. CLAUDE.md "État du projet (avril 2026)" stale
- **Trouvé par agent docs** : section ligne 205-212 dit "Engine ~19K lignes, 14 fichiers, 6 hooks". Réel : 25K, 23, 9.
- **Action** : régénérer ou retirer la section, pointer CHANGELOG.
- **Effort** : 5 min.

---

## 🔒 SECURITY POLISH (rien de critique, polish défendable)

S1. **`verify=False` côté SyncClient** : exiger env var `MUNINN_TLS_INSECURE=1` + audit JSONL trace. (15 min)
S2. **RSA 2048 → 3072 ou ECDSA P-256** dans `generate_certs()`. (10 min)
S3. **hooks.sha256sum cwd-mismatch** : documenter exécution depuis repo root OU régénérer chemins relatifs. (10 min)
S4. **pre_tool_use_bash_secrets faux positifs** : raffiner regex pour ne pas bloquer `find -name "*.key"` sur audit.
S5. **Permissions sur _secrets.py / vault.py source** : 755 → 644 (défense en profondeur sur multi-user host).

**Verdict agent security** : "Sky peut vendre sans avoir honte". Aucune trouvaille critique. Travail P0+P0bis sérieux.

---

## 📚 STRATÉGIQUE B2B (à investir pour vendre)

### Concurrence 2026 (agent web)

Le marché "AI Agent Memory Frameworks" en mai 2026 est dominé par 4 titans :
- **Mem0** (mem0.ai) — 3-tier memory hybrid
- **Zep** — server async, summarization, temporal
- **Letta** (ex-MemGPT) — Memory-as-OS, paging
- **Cognee** — knowledge graph
- **Supermemory** — API memory layer

🚨 **Menace native** : Anthropic a sorti **Claude Memory Tool** (`memory_20250818`) + **Memory for Managed Agents** (avril 2026) — read/write filesystem, audit logs, gratuit, intégré, déjà adopté par Netflix/Rakuten/Wisedocs. **Ça mange notre lunch sur "persistance simple".**

**Différenciation MUNINN** :
- Compression x1.6-x4.1 mesurée tiktoken (personne d'autre ne benchmark publiquement)
- 12 couches regex zero-dep (vs Mem0/Zep qui exigent vectordb + LLM call)
- Mycelium = co-occurrence learning (pas RAG)
- Cross-repo federation
- Offline-first

### Standards B2B manquants

1. **SOC 2 Type I** — 8-12 semaines, $20-35k. Indispensable dès le 1er deal enterprise.
2. **Threat model OWASP-LLM-2025** — pas de doc dans le repo, à rédiger.
3. **OWASP Top 10 Agentic 2026** — sorti 2026, on est dans le scope (agent memory).
4. **GDPR** — pas de mention RTBF/export utilisateur sur `.muninn/mycelium.db`.
5. **Page security/trust + DPA + SLA** — aucun artefact B2B classique.

**Action stratégique** : avant de vendre, monter une page `docs/SECURITY.md` + `docs/THREAT_MODEL.md` + lancer SOC 2 Type I.

---

## ✅ CONFIRMÉ EN PRODUCTION (ne rien toucher)

- **0 xfail** dans tout le repo (post-H5.2)
- **0 assert True bullshit** (le seul match est dans le test du détecteur anti-`assert True`)
- **0 token leak** dans git history (87 hits = fixtures, placeholders AWS officiels, regex scanner)
- **0 GitHub issue ouverte** (tracker externe = pas de drift)
- **0 forge.py local** (find = empty)
- **TLS 1.3 only**, pas de downgrade 1.2
- **AES-256-GCM + PBKDF2 600k iterations** (OWASP 2023)
- **secure_perms() sur ~50 sites** dans 12 fichiers
- **9 hooks .claude/hooks/ chmod 0o750** + manifest sha256sum
- **CI : 12/12 success consécutifs** sur les commits H1-H5.2
- **Q-modularity 0.673** (good — modules well isolated)
- **Top 5 Carmack convergent** entre carmack/predict/anomaly (3 mêmes coupables : cube_providers, muninn, muninn_tree)
- **Tests : 2328/2563 PASS en CI** (90.83 %)
- **forge_metrics + cube_live wiring effectif** (UI consume le PyPI forge en live)
- **muninn zones + growth_stats wirées** (4/4 méthodes mycelium ex-orphelines en prod)

---

## 🎯 PLAN D'ATTAQUE PRIORISÉ

### CE SOIR (90 min, easy wins immediate)
1. **B2.1** Reclassifier BUG-091 PARTIAL dans BUGS.md (5 min)
2. **B3** Fix `claude-haiku-4-20250414` → `claude-haiku-4-5-20251001` dans scanner/llm_scanner.py (2 min)
3. **H4** Régénérer CHANGELOG ligne 3 + README chiffres (15 min)
4. **H5** Banner WINTER_TREE.md stale (1 min)
5. **H6** Ajouter `claude-opus-4-7` aux listes models (5 min)
6. **M5** `mkdir docs/archive/ && git mv` 14 docs obsolètes (10 min)
7. **M6** Refresh CLAUDE.md "État du projet" → mai 2026 (5 min)
8. **H1** Bump anthropic 0.96 → 0.100 + cryptography 46.0.7 → 48.0.0 + tests (30 min)
9. **H2** Pin cryptography/urllib3/requests/PyYAML dans constraints.txt (10 min)
10. **Commit + push final**

### CETTE SEMAINE (8-12h)
- **B2.2-3** Convertir 3 fichiers md5-identiques en shims côté muninn/ (1.5h)
- **B2.4** Fix vault.py divergence (30 min)
- **B1** Re-publier forge-shield sur PyPI (30-60 min, cousin pc1)
- **H3** pip-audit en CI (15 min)
- **H7** Merger Dependabot PRs #1+#2 + cache pip + concurrency + timeout (30 min)
- **H8** Décider du sort de test_chunk_a7_hook_integrity (90 min max)
- **M1** Split `boot()` 656L (3h)
- **M2** Split `cube_providers.py` par provider (4h)

### AVANT DE VENDRE B2B (~40h cumulé)
- **M3** H6 mycelium split honnête (6-9h)
- **M4** 10 méthodes mycelium orphelines wirées (3-4h)
- **Stratégique** SOC 2 Type I démarrage (8-12 semaines, parallèle)
- **Stratégique** Threat model OWASP-LLM-2025 (4h)
- **Stratégique** Page security/trust + DPA + SLA (4h)
- **Stratégique** Benchmark public vs Mem0/Zep/Letta (8h)

---

## 📊 BILAN DE LA JOURNÉE 2026-05-09

**Avant la session** :
- Forge interne 3 copies (280K)
- 4 méthodes mycelium dead
- 11 tests "workflow not merged"
- 2 xfails
- forge_metrics non consommé
- CHANGELOG à jour à mars
- WINTER_TREE à jour à 22 avril

**Après H1-H5.2 + cleanup** :
- 1 seul forge (PyPI 1.1.1 git tag, à fixer côté PyPI 1.1.0 wheel)
- 4/4 méthodes mycelium ex-orphelines wirées (`muninn status` + `muninn zones`)
- 0 test "workflow not merged"
- **0 xfail**
- forge_metrics consommé par `cube_live.py` UX
- CHANGELOG à jour à 9 mai (chiffres LOC à corriger sur ligne 3)
- WINTER_TREE toujours stale (action item H5)
- **9 commits sur main** : `d6a5fc3` → `81e8703`
- **Q-modularity stable** : 0.673 (baseline 0.678, dans le bruit)
- **CI 12/12 success**

**Reste avant vente B2B** : ~40h cumulé répartis sur les 3 strates ci-dessus. Pas un mois, pas une semaine — quelques jours focused si Sky maintient le rythme observé (2h pour ce qui était estimé 5h).

---

## Sources

- 9 sub-agents lancés en parallèle 2026-05-09 21h-22h CEST.
- Topics : forge intégration, test suite, mycelium wiring, CI, security, architecture, BUGS.md, docs, web ecosystem.
- Tous les rapports détaillés conservés dans le transcript de session.
- Pas d'estimation conservative x3 : agents instruits de donner l'estimation honnête.
