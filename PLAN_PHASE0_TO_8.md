# MUNINN — Plan Federated Sync + Hardening (71 briques)

Genere le 2026-03-27. Baseline: 1098 tests, ~7 FAIL (API only), ~7 SKIP.

---

## Phase 0 — Fixes immediats (17 briques)

- [x] **X1** Secret scrub 7 entry points (observe_text, feed, bootstrap, ingest, inject, CLI, cube x2) + defense dans observe_text() [S]
- [x] **X1b** Purge secrets existants dans mycelium.db + meta_mycelium.db [S]
- [x] **X2** UTC epoch — datetime.now(timezone.utc).date() partout [XS]
- [x] **X3** Indexes manquants — 4 composites sur edges/concepts/edge_zones [S]
- [x] **X4** Schema versioning (PRAGMA user_version) + migration idempotency (flag debut+fin) [S]
- [x] **X5** Fix days_to_date() fallback — retourne today() pas "2026-01-01" [XS]
- [x] **X6** Fix saturation loss — float pas int (count=1000 crashe a 1) [XS]
- [x] **X7** Fix feed progress — ecrire APRES mycelium.save() pas avant [XS]
- [x] **X8** Fix DB handle leak — fermer retour migrate_from_json() [XS]
- [x] **X9** Fix access_count reset dans prune (branches immortalisees) [XS]
- [x] **X10** Fix CAST qui casse l'index dans decay WHERE clause [XS] (deja fixe)
- [x] **X11** Fix L2/L3 order — L3 (phrases) AVANT L2 (fillers) [XS]
- [x] **X12** Fix Bearer regex — minimum 20 chars pour eviter false positive prose [XS]
- [x] **X13** Fix hex false positive L10 — word boundary \b[a-f0-9]{7,40}\b [XS]
- [ ] **X14** Config path validation — type check + traversal + symlink [S]
- [ ] **X15** install_hooks() atomic write (tempfile+replace) [XS]
- [ ] **X16** Learned fillers seuil minimum (20+ occurrences avant d'appliquer) [XS]

**Tests Phase 0**: ~45 tests unitaires + 5 tests regression integration
**Regression**: python forge.py apres chaque brique

---

## Phase 1 — Fondation (7 briques)

- [ ] **F1** SyncBackend ABC — interface push/pull/status/migrate + SyncPayload dataclass [S]
- [ ] **F2** SharedFileBackend — extraire sync actuel de mycelium.py dans classe propre [M]
- [ ] **F3** Factory + Config — lire config -> retourner le bon backend, retro-compatible [S]
- [ ] **F4** Rewiring Mycelium — sync_to_meta()/pull_from_meta() deleguent au backend [M]
- [ ] **F5** SyncPayload serializer — export/import delta (edges+fusions+zones) en JSON [S]
- [ ] **F6** Env var MUNINN_META_PATH override (CI/Docker) [XS]
- [ ] **F7** Config atomic write — tempfile+replace pour config.json partout [S]

**Tests Phase 1**: ~25 tests (2 repos + shared meta -> sync roundtrip)

---

## Phase 2 — Hardening (13 briques)

- [ ] **H1** Sync audit log — table sync_log (timestamp, user, repo, action, count, errors) [S]
- [ ] **H2** Pre-sync snapshot + rollback — savepoint SQLite avant merge, rollback_to_last_good() [M]
- [ ] **H3** Integrity checksums — SHA256 sur payload, validation au pull [S]
- [ ] **H4** Tombstones — table deleted_edges, prune enregistre avant suppression, pull respecte [M]
- [ ] **H5** Fusion conflict resolution — vote par nombre de zones utilisant chaque forme [S]
- [ ] **H6** Dynamic degree filter — percentile ajuste selon population meta (5% / sqrt(n_repos)) [S]
- [ ] **H7** Offline resilience — edges 3+ zones dans meta = pas de decay local [S]
- [ ] **H8** Per-repo filter on pull — pull ne ramene que les concepts pertinents [S]
- [ ] **H9** Disk full guard — check espace disque avant atomic writes [XS]
- [ ] **H10** Prune rollback — snapshot arbre avant sleep_consolidate [S]
- [ ] **H11** Network timeout — timeout sur mkdir/exists/open NAS (5s default) [S]
- [ ] **H12** Tree file lock — flock/fcntl sur tree.json pour boot/prune concurrent [S]
- [ ] **H13** ConceptTranslator thread lock — singleton avec threading.Lock [XS]

**Tests Phase 2**: ~45 tests (inject corruption -> verifie recovery/rollback)

---

## Phase 3 — Backend Git (5 briques)

- [ ] **G1** GitBackend core — push/pull via bare repo git local [L]
- [ ] **G2** Conflict CRDT — merge automatique sur conflit git (MAX count, union zones) [S]
- [ ] **G3** Auto-init — muninn sync --init-git /path cree le repo [S]
- [ ] **G4** Remote support — clone/fetch/push vers Gitea/GitLab/SSH [M]
- [ ] **G5** Delta sync — exporter que les edges avec last_seen >= last_sync_day [M]

**Tests Phase 3**: ~20 tests (bare git repo + clone + push/pull -> CRDT merge)

---

## Phase 4 — Backend TLS (4 briques)

- [ ] **T1** Wire SyncServer merge — push fait le vrai CRDT merge, pull retourne des donnees [M]
- [ ] **T2** TLSBackend class — implemente SyncBackend via SyncClient existant [S]
- [ ] **T3** Server CLI — muninn serve --port 9477 [S]
- [ ] **T4** Auth + ACL — verifier cert CN = user autorise, permissions par zone [M]

**Tests Phase 4**: ~15 tests (localhost server + client cert + push/pull)

---

## Phase 5 — Integration (5 briques)

- [ ] **I1** CLI commands — sync --status/--backend/--migrate/--export/--import [M]
- [ ] **I2** Migration tool — backend-to-backend avec verification row count [M]
- [ ] **I3** Hook verify — verifier les 5 call sites avec chaque backend [S]
- [ ] **I4** Doctor check — sante backend + integrite meta dans doctor() [S]
- [ ] **I5** Export/Import JSON — dump meta complet en JSON pour backup + import [S]

**Tests Phase 5**: ~20 tests (CLI subprocess -> verifie stdout + exit code)

---

## Phase 6 — Scale + Performance (10 briques)

- [ ] **P1** Concurrent SharedFile — backoff exponentiel + jitter pour 120 users NAS [M]
- [ ] **P2** Zone cleanup — supprimer zones orphelines (repos supprimes) dans prune() [S]
- [ ] **P3** Growth limits — MAX_CONNECTIONS=5M soft limit + quota par zone + VACUUM periodique [M]
- [ ] **P4** Observability — sync.log rotatif + metriques croissance + CLI muninn sync --health [S]
- [ ] **P5** Cache id_to_name global — utiliser _db._id_to_name au lieu de reconstruire 14x/session [S]
- [ ] **P6** Batch deletes dans decay() — executemany() au lieu de loop [XS]
- [ ] **P7** Single-pass detect_zones — virer le double scan edges [S]
- [ ] **P8** NCD cap — top-20 branches par heuristique, pas O(n^2) complet dans prune [M]
- [ ] **P9** Cycles table TTL cleanup — DELETE FROM cycles WHERE age > 30d [XS]
- [ ] **P10** Secret patterns cache global — compiler regex une seule fois [XS]

**Tests Phase 6**: ~30 tests (100K edges -> benchmark timing < seuil)

---

## Phase 7 — Intelligence (8 briques)

- [ ] **A1** Fusion threshold adaptatif — max(2, sqrt(n_concepts) * 0.4) [XS]
- [ ] **A2** Decay half-life adaptatif — scale avec sessions/jour du repo [XS]
- [ ] **A3** Orphan cleanup auto — DELETE concepts sans edges quand orphans > 20% [XS]
- [ ] **A4** Auto-vacuum quand decay() > 10s — PRAGMA optimize + reindex [XS]
- [ ] **A5** Spreading activation hops adaptatif — 1 hop si dense, 3 si sparse [XS]
- [ ] **A6** Boot pre-warm par git diff — charger branches liees aux fichiers modifies [S]
- [ ] **A7** Auto-backup avant prune destructif — .muninn/backups/prune_before_<ts>.tar.gz [S]
- [ ] **A8** Prune warning au boot — "45% branches mortes, run prune" [XS]

**Tests Phase 7**: ~25 tests (avant/apres adaptatif -> verifie que threshold change)

---

## Phase 8 — Cleanup (2 briques)

- [ ] **C1** Supprimer memory/tree.json legacy (3 branches vs 167 dans .muninn/tree/) [XS]
- [ ] **C2** Cleanup orphaned .tmp files au boot [XS]

**Tests Phase 8**: ~5 tests

---

## Recap

| Phase | Briques | Focus | Tests |
|-------|---------|-------|-------|
| 0 | 17 | Bugs + securite + regex | ~50 |
| 1 | 7 | Abstraction sync + config | ~25 |
| 2 | 13 | Solide + reseau + locks | ~45 |
| 3 | 5 | Backend git | ~20 |
| 4 | 4 | Backend reseau TLS | ~15 |
| 5 | 5 | CLI + migration + doctor | ~20 |
| 6 | 10 | 120 users + bottlenecks | ~30 |
| 7 | 8 | Adaptatif + auto | ~25 |
| 8 | 2 | Legacy + tmp | ~5 |
| **Total** | **71** | | **~235** |

## Workflow par brique

1. Code la brique
2. Test manuel rapide
3. Ecris le test Python (pytest, tempdir, assert, try/finally)
4. `python -m pytest tests/test_Xn.py -v` -> passe
5. `python forge.py` -> regression globale passe
6. git add + commit + push

## Bugs reels trouves (14)

B1: DB handle leak migrate_from_json() -> X8
B2: days_to_date fallback hardcode -> X5
B3: saturation loss int truncation -> X6
B4: id_to_name dead code -> P5
B5: feed progress avant save -> X7
B6: migration crash = data wipe -> X4
B7: access_count jamais reset -> X9
B8: L2 casse L3 (ordre compression) -> X11
B9: Bearer false positive -> X12
B10: Hex false positive L10 -> X13
B11: UTF-8 BOM pas gere -> mineur, skip
B12: CubeConfig.save non-atomique -> F7
B13: Cycles table unbounded -> P9
B14: Orphaned .tmp file -> C2
