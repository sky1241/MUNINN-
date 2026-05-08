# BATTLE PLAN — AUDIT SENIOR DEV (Runs 2 + 3)

**Date** : 2026-05-08 (v2 — consolidé après Run 3)
**Auteur** : Sky + Claude (8 agents senior parallèles, 2 vagues)
**Statut** : 🔴 TODO — 56 issues identifiées, 8 blocker à fixer avant nouvelle feature
**Méthodologie** : 8 agents Explore en parallèle (4 axes Run 2 + 4 axes Run 3 orthogonaux), output verbatim, file:line traçable.

---

## §0 Résumé exécutif (90s)

### Le constat

L'audit Run 1 (fonctionnel) disait "tout est branché". Run 2 (threading, perf, errors, tests) a trouvé 31 issues. Run 3 (security, data integrity, codebase rot, CI/supply chain) a trouvé **25 issues supplémentaires** dont **3 nouvelles CRITICAL**.

### Ce que Run 3 a révélé que Run 2 n'avait pas vu

1. **L9 cold-branch leak** (`muninn_tree.py:2887`): la compression LLM des branches envoie le contenu .mn directement à l'API Anthropic **SANS appeler `redact_secrets_text()`** — alors que `compress_file()` le fait. Si une .mn contient un token oublié, il part chez Anthropic.
2. **UnicodeDecodeError sur .mn truncated** (`muninn_tree.py:524, 751, 812, 827`): si un process est tué pendant l'écriture d'un .mn, le fichier contient des séquences UTF-8 incomplètes. `grow_branches_from_session()` crash → tout le pipeline ingestion s'arrête.
3. **Pas de `PRAGMA integrity_check` au boot**: si mycelium.db corrompue (fsync, ext4 bug, disk full pendant write), `bridge_fast()` retourne `""` silencieusement (generic except). User ne sait jamais.
4. **Sentinel false-positives observés LIVE**: 5+ déclenchements pendant l'audit lui-même sur des prompts sans secrets. Cry-wolf — Sky finit par ignorer les vrais warnings.
5. **MUNINN_META_PATH undocumented**: env var qui peut redirect le mycelium vers n'importe quel chemin, jamais documentée.
6. **Pas de lockfile**: `tiktoken>=0.5`, `anthropic>=0.20` non-pinnés. Builds non-reproductibles.

### Note senior dev consolidée : **6/10**

(Run 2 disait 6.5/10, Run 3 a trouvé pire en sécurité — note baissée.)

Excellente discipline RULE 4/5, forge, BUG_TRACKER, anti-bullshit doc. **MAIS** dette technique cumulée + 1 data leak inconnu + 1 crash possible du pipeline ingestion. Pas un ship-blocker mais un sleep-disturbing.

### Plan en 4 phases

| Phase | Effort | Contenu | Pourquoi |
|---|---|---|---|
| **A — Security + data integrity** | 4-5h | 8 blockers (data leak L9, .mn crash, integrity check, path traversal, locks, sentinel, hook integrity) | Sécurité + corruption silencieuse. Avant toute nouvelle feature. |
| **B — Robustesse + observabilité** | 3-4h | Cache id_to_name, hook log rotation, tests rouges, schema tree, _REPO_PATH race | Performance + audit trail. |
| **C — Hygiène + supply chain** | 3-4h | Lockfile, version sync, dependabot, doc drift, MUNINN_META_PATH doc | Reproductibilité + clarté. |
| **D — Parking lot** | variable | Property tests cosmétiques, watchdog dead code, naming, LFS, CHANGELOG | Documenté, pas urgent. |

**Total Phases A+B+C ≈ 10-13h**. Phase D = backlog ouvert.

---

## §1 Inventaire complet — 56 issues consolidées

Format : `[Run] [Severity] file:line — issue (source agent)`.

### CRITICAL (7) — 4 NEW depuis Run 3

| # | Run | File:line | Issue | Agent |
|---|---|---|---|---|
| C1 | R3 | `muninn_tree.py:2887` | **[NEW]** L9 cold-branch envoie .mn à Anthropic SANS `redact_secrets_text()` — data leak | A5 |
| C2 | R3 | `muninn_tree.py:524, 751, 812, 827` | **[NEW]** `read_text()` sans except UnicodeDecodeError → crash pipeline ingestion sur .mn truncated | A6 |
| C3 | R3 | mycelium.db boot | **[NEW]** Pas de `PRAGMA integrity_check` → corruption silencieuse, `bridge_fast` retourne `""` | A6 |
| C4 | R2 | `cube.py:216` | Path traversal: `Path(root) / fname` sans validation | A3 |
| C5 | R2 | `muninn_feed.py:1139` | `Path(transcript_path)` sans `is_relative_to` — lecture arbitraire | A3 |
| C6 | R2 | `muninn_feed.py:1085, 1115` | `_log_sync_error` swallow → log-of-log perdu | A3 |
| C7 | R2 | `bridge_hook.py:107` | 616 erreurs `stdin_parse` accumulées depuis 2026-04-24 dans `~/.muninn/hook_errors.log` | A3 |

### HIGH (15) — 6 NEW depuis Run 3

| # | Run | File:line | Issue | Agent |
|---|---|---|---|---|
| H1 | R3 | `bridge_hook.py:58-90` | **[NEW]** Sentinel cry-wolf (entropy 2.8 trop bas, "auth"/"key" dans triggers, 5+ FP/session observés live) | A5 |
| H2 | R3 | `.claude/hooks/*.py` (9 fichiers) | **[NEW]** World-readable, no checksum/signature → modification = code execution next session | A5 |
| H3 | R3 | `muninn_tree.py:235, 269` (`_tree_lock`) | **[NEW]** Lock advisory avec timeout=5s mais procède quand même si fail → 2 writers concurrents = silent loss | A6 |
| H4 | R3 | `muninn_tree.py:2098` (`bridge_fast`) | **[NEW]** Generic `except Exception` → empty string silencieux, user ne sait pas que mycelium est cassé | A6 |
| H5 | R3 | `memory/tree.lock` orphan | **[NEW]** `cleanup_tmp_files()` ligne 114 ne tourne pas, locks restent (1 byte file daté 06:51) | A6 |
| H6 | R3 | `pyproject.toml` | **[NEW]** Pas de lockfile, `tiktoken>=0.5`, `anthropic>=0.20` — builds non-reproductibles | A8 |
| H7 | R2 | `mycelium_db.py:329` (get_meta) | SELECT sans lock — read pendant write concurrent | A1 |
| H8 | R2 | `mycelium_db.py:354, 430, 472` | `get_connection`, `get_all_*`, `connection_count` mêmes risques | A1 |
| H9 | R2 | `mycelium_db.py:254` | `_migrate_schema()` sans lock — 2 process = DB corrompue | A1 |
| H10 | R2 | `mycelium.py` (7 sites: 879, 627, 434, 1291, 1614, 1676, 1857) | `id_to_name = {v:k for k,v}` recréé non-caché | A2 |
| H11 | R2 | `wal_monitor.py:99` | Checkpoint WAL fail silent, DB 1.2GB peut fragmenter | A3 |
| H12 | R2 | `cube_providers.py:1301` | `get_related_cubes` fail → `[]` → bridge_fast injecte zéro contexte sans warn | A3 |
| H13 | R2 | `mycelium_db.py:254` (mid-migration) | Crash laisse `_migration_in_progress=1` → deadlock open suivant | A3 |
| H14 | R3 | env `MUNINN_META_PATH` | **[NEW]** Permet redirect mycelium n'importe où, undocumented (RED dans agent 7) | A7 |
| H15 | R3 | `muninn/_engine.py` (2100 LOC) | **[NEW]** Pas un shim — duplicate bridge, drift risk avec `engine/core/muninn.py` | A7 |

### MEDIUM (19) — 12 NEW depuis Run 3

| # | Run | File:line | Issue | Agent |
|---|---|---|---|---|
| M1 | R2 | `bridge_hook.py:138-139` | `muninn._REPO_PATH` global mutable, race entre hooks parallèles | A1 |
| M2 | R2 | `tests/*.py` (multi) | Tests modifient `_REPO_PATH` global sans fixture autouse | A1 |
| M3 | R2 | `mycelium.py:866-888` | `_get_high_degree_concepts` UNION ALL exécuté 2× | A2 |
| M4 | R2 | `muninn_layers.py:1337` | `read_text()` charge fichier entier — OOM-prone ≥50MB | A2 |
| M5 | R2 | `test_props_*.py` (10 fichiers, ~300 tests) | Property tests = smoke only, zéro assertion comportementale | A4 |
| M6 | R2 | `test_brick20_architecture.py` | FAILS — `gen_props()` >200L viole invariant | A4 |
| M7 | R2 | `test_phase4_tls.py` | FAILS — `isinstance` rejette shim TLSBackend (BUG-091 régression) | A4 |
| M8 | R2 | `mycelium.py:1384` | Fallback JSON full scan O(E) | A2 |
| M9 | R3 | `muninn_layers.py:1255-1258` | **[NEW]** PowerShell fallback pour ANTHROPIC_API_KEY + `subprocess.TimeoutExpired` non géré | A5 |
| M10 | R3 | `watchdog.py`, `sync_backend.py:90+` | **[NEW]** `json.loads` sans `isinstance(dict)` post-parse | A5 |
| M11 | R3 | `engine/core/muninn_tree.py` (load_tree) | **[NEW]** Pas de schema validation — `{"foo": "bar"}` est JSON valide mais crash au runtime | A6 |
| M12 | R3 | `.mn` files | **[NEW]** Pas de magic header / version / CRC — anciens .mn lus avec mauvaise sémantique | A6 |
| M13 | R3 | mycelium.db backup | **[NEW]** Backup-2026-04-30 (8j stale), pas d'incremental WAL backup | A6 |
| M14 | R3 | `engine/core/muninn.py:21` vs `muninn/__init__.py:18` | **[NEW]** Version drift 0.9.1 vs 0.9.2 — pas de single source of truth | A7 |
| M15 | R3 | `muninn.py` (top + l.727, 876, 1012) | **[NEW]** Imports répétés dans fonctions (json, os, sys, re) — code smell | A7 |
| M16 | R3 | env `MUNINN_CONTEXT_SIZE`, `MUNINN_L12_BUDGET`, `MUNINN_GL_SOFTWARE` | **[NEW]** Env vars non-documentées dans README/CLAUDE.md | A7 |
| M17 | R3 | README.md | **[NEW]** "11 layers" (réel = 12), "MEMORY.md ~200L" (fichier inexistant), "zero deps" (faux), "Linux only" (Windows fallbacks présents), "100% regex" (L9 = API) | A7 |
| M18 | R3 | `.github/workflows/ci.yml` | **[NEW]** Très minimaliste — pas de pytest collection standard, pas de mypy, pas de coverage, pas de `pytest -m "not slow"` | A8 |
| M19 | R3 | `.github/` | **[NEW]** Pas de Dependabot/Renovate — updates manuels | A8 |

### LOW (15) — 6 NEW depuis Run 3

| # | Run | File:line | Issue | Agent |
|---|---|---|---|---|
| L1 | R2 | `mycelium_db.py:76` | `check_same_thread=False` suppose 1 instance/process | A1 |
| L2 | R2 | `muninn_layers.py:15, 27, 39` | Import failure cascade swallowed | A3 |
| L3 | R2 | `scanner/report.py:514-517` | Double-bare-except dans `_dc_to_dict()` | A3 |
| L4 | R2 | `muninn_feed.py:1060` | Lock stale removal silent | A3 |
| L5 | R2 | `sync_backend.py:452` | `Path(cfg["meta_path"])` sans whitelist | A3 |
| L6 | R2 | `bridge_hook.py:132` | Path relatif `__file__.parent.parent.parent` fragile | A3 |
| L7 | R2 | `muninn.py:521, 562` | `os.replace()` fail silencieux | A3 |
| L8 | R2 | `anomalies.jsonl` | 477 anomalies non-revalidées, jamais purgées | A3 |
| L9 | R2 | (CI) | Pas de step `forge.py --gen-props` par module en CI | A4 |
| L10 | R2 | `mycelium.py:424` | `O(N²)` pairs sur clean list (acceptable car N=10-50) | A2 |
| L11 | R2 | `muninn/__init__.py` | Pas de test CI vérifiant `dir(muninn) == dir(engine.core)` | A4 |
| L12 | R2 | (multi) | Pas de logging framework central, seul scanner/ utilise `logging` | A3 |
| L13 | R3 | `engine/core/watchdog.py` (57L) + shim (57L) | **[NEW]** 0 imports — code mort orphelin (intended Windows Task Scheduler, jamais wired) | A7 |
| L14 | R3 | naming | **[NEW]** `repo_path` vs `_REPO_PATH` vs `MUNINN_REPO` — 3 styles pour même concept | A7 |
| L15 | R3 | `muninn/ui/templates/*.png` (12 fichiers, ~40MB) | **[NEW]** PNG committés, pas de Git LFS | A8 |

### Total : **7 CRITICAL + 15 HIGH + 19 MEDIUM + 15 LOW = 56 issues** (31 Run 2 + 25 Run 3).

---

## §2 Phase A — SECURITY + DATA INTEGRITY (4-5h)

**Règle**: rien d'autre ne mergera tant que ces 8 ne sont pas verts.

### A1 — L9 redact_secrets sur cold-branch (15min) [C1]

**Source**: Agent 5 (security depth)

**Fichier**: `engine/core/muninn_tree.py:2887`

**Diagnostic verbatim**:
```python
# Ligne 2887 actuelle:
compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
```

`compress_file()` (l.1344) appelle `_redact_secrets_text(content)` AVANT `_llm_compress`. Le path cold-branch zappe cette étape. Si une .mn contient un token oublié (échec de redaction antérieur, encoding issue), il part chez Anthropic en clair.

**Fix**:
```python
content = _redact_secrets_text(content)  # ← ajouter avant
compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
```

**Test à écrire**:
```python
def test_cold_branch_redacts_before_llm(monkeypatch):
    captured = []
    monkeypatch.setattr(_m, "_llm_compress", lambda c, **kw: captured.append(c) or c)
    # Mock une .mn avec un token
    branch_path.write_text("api_key=ghp_REAL_LOOKING_TOKEN_PATTERN_12345678")
    cold_branch_compress(branch_path, name="test")
    assert "ghp_" not in captured[0]
```

**Verbatim verification**:
```bash
grep -n "_redact_secrets_text\|_llm_compress" engine/core/muninn_tree.py
pytest tests/test_l9_redaction.py -v
```

### A2 — UnicodeDecodeError handlers sur .mn (30min) [C2]

**Source**: Agent 6 (data integrity)

**Fichiers**: `engine/core/muninn_tree.py` lignes **524, 751, 812, 827**

**Diagnostic**: 4 sites `Path.read_text(encoding="utf-8")` sans try/except. Si `.mn` truncated (process killed mid-write), UnicodeDecodeError tue le pipeline ingestion entier. Ligne 1209 utilise déjà `errors="ignore"` correctement — manque la cohérence sur les autres sites.

**Fix simple (option 1)**: ajouter `errors="ignore"` partout :
```python
text = path.read_text(encoding="utf-8", errors="ignore")
```

**Fix robuste (option 2)**: helper centralisé:
```python
def _safe_read_mn(path: Path) -> str | None:
    """Read .mn file, return None if truncated/corrupted."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        _log_corruption("mn_truncated", path, e)
        return None
```

**Recommandation**: option 2 + appeler `_log_corruption` pour audit trail (sinon corruption silencieuse).

**Test**:
```python
def test_grow_branches_handles_truncated_mn(tmp_path):
    bad = tmp_path / "bad.mn"
    bad.write_bytes(b"## valid\nfact:\xc3\xa9 ok\n## broken\n\xc3")  # truncated UTF-8
    # ne doit pas crash
    grow_branches_from_session(bad, repo_root=tmp_path)
```

**Verbatim verification**:
```bash
grep -n "read_text(encoding" engine/core/muninn_tree.py
pytest tests/test_mn_corruption.py -v
```

### A3 — PRAGMA integrity_check au boot mycelium (20min) [C3]

**Source**: Agent 6 (data integrity)

**Fichier**: `engine/core/mycelium_db.py` (ajouter dans `__init__` ou `_open`)

**Fix**:
```python
def _check_integrity(self) -> bool:
    cur = self._conn.execute("PRAGMA integrity_check")
    result = cur.fetchone()[0]
    if result != "ok":
        # Log corruption + tentative récupération
        _log_corruption("mycelium_db_integrity", self.db_path, result)
        return False
    # Optionnel: PRAGMA wal_checkpoint(RESTART) pour merger WAL avant utilisation
    self._conn.execute("PRAGMA wal_checkpoint(RESTART)")
    return True
```

À appeler une fois au boot, pas à chaque connexion (coût ~100-500ms sur 1.2GB).

**Test**:
```python
def test_corrupted_db_detected(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"NOT A SQLITE FILE")
    with pytest.raises(IntegrityError):  # ou retour False + log
        MyceliumDB(db_path)
```

**Verbatim verification**:
```bash
python -c "import sys; sys.path.insert(0,'engine/core'); from mycelium_db import MyceliumDB; db = MyceliumDB('.muninn/mycelium.db'); print(db._check_integrity())"
# attendu: True
```

### A4 — Path traversal hardening (15min) [C4, C5]

**Source**: Agent 3 (errors/observability)

**Fichiers**: `engine/core/cube.py:216`, `engine/core/muninn_feed.py:1139`

**Patch type**:
```python
def _safe_join(root: Path, fname: str) -> Path:
    candidate = (Path(root) / fname).resolve()
    root_resolved = Path(root).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError(f"Path traversal refused: {fname}")
    return candidate
```

**Tests** (TDD):
```python
def test_cube_refuses_dotdot():
    with pytest.raises(ValueError):
        cube._read_cube_file(repo_root, "../../etc/passwd")

def test_feed_refuses_absolute_outside():
    with pytest.raises(ValueError):
        muninn_feed.feed_transcript("/etc/passwd")
```

**Verbatim verification**:
```bash
pytest tests/test_path_traversal.py -v  # 2 passed
```

### A5 — Lock SQLite reads + migration (30min) [H7, H8, H9, H13]

**Source**: Agent 1 (threading)

**Fichier**: `engine/core/mycelium_db.py`

**Sites à wrapper avec `with self._lock:`**:
- `get_meta` (l.329)
- `get_connection` (l.354)
- `get_all_connections`, `get_all_fusions`, `get_zone_*` (l.430+)
- `connection_count`, `has_connection`, `has_fusion` (l.472+)
- `_migrate_schema` (l.254 — lock dès le début, jusqu'au PRAGMA user_version final)

**Test stress**:
```python
def test_concurrent_read_write_no_corruption(tmp_path):
    db = MyceliumDB(tmp_path / "test.db")
    errors = []
    def writer():
        for i in range(1000):
            try: db.set_meta(f"k{i}", str(i))
            except Exception as e: errors.append(("w", e))
    def reader():
        for i in range(1000):
            try: db.get_meta(f"k{i % 100}")
            except Exception as e: errors.append(("r", e))
    threads = [Thread(target=writer) for _ in range(2)] + \
              [Thread(target=reader) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
```

**Verbatim verification**:
```bash
pytest tests/test_mycelium_db_concurrency.py -v
python forge.py --gen-props engine/core/mycelium_db.py
pytest tests/test_props_mycelium_db.py -q
```

### A6 — Sentinel calibration (recalibrate, 30min) [H1]

**Source**: Agent 5 (security depth) — observé LIVE 5+ fois pendant cet audit

**Fichier**: `.claude/hooks/bridge_hook.py:58-90`

**Constat**: pendant la session d'audit, le `[MUNINN SENTINEL]` a déclenché 5+ fois sur des messages SANS secret réel — uniquement à cause des mots "secret"/"key"/"auth" dans la conversation sur la sécurité du code lui-même. Cry-wolf.

**Code actuel**:
```python
_SECRET_TRIGGERS = re.compile(
    r'(?:cl[eé]|key|password|mdp|mot de passe|passwd|secret|token|passphrase'
    r'|api.?key|credentials?|auth)',
    re.IGNORECASE
)
# ...
if len(clean) >= 6 and _has_char_diversity(clean) and _shannon_entropy(clean) > 2.8:
    return "[MUNINN SENTINEL] You may have typed a password..."
```

**Fix**:
1. Word boundaries: `r'\b(?:cl[eé]|key|...)\b'` au lieu de match-anywhere.
2. Retirer `auth` et `key` seuls (trop communs); garder `api.?key`, `auth_token`, etc.
3. Élever entropy threshold: `> 2.8` → `> 3.5` (passwords/hashes only, pas mots anglais).
4. Whitelist mots techniques courants ("authentication", "secretariat", "keystone", "secret_key" en code).

**Test**:
```python
def test_sentinel_no_false_positive_on_audit_jargon():
    cases = [
        "Lis le code de _check_secrets dans bridge_hook",
        "On va auditer les keys du mycelium",
        "Le pattern auth_trigger est trop large",
    ]
    for c in cases:
        assert _check_secrets(c) is None, f"FP on: {c}"

def test_sentinel_still_catches_real_token():
    assert _check_secrets("token=ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH") is not None
```

**Verbatim verification**: après fix, run un export du transcript de cette session et compter les triggers vs vraies leaks.

### A7 — Hooks integrity (sha256sum + perms) (20min) [H2]

**Source**: Agent 5 (security depth)

**Fichiers**: `.claude/hooks/*.py` (9 fichiers)

**Constat**: `-rwxr-xr-x` (world-readable, world-executable). Pas de checksum vérifié avant exec. Quelqu'un qui modifie `bridge_hook.py` = code execution dans la prochaine session Claude Code.

**Fix**:
1. Générer `hooks.sha256sum`, le commiter:
   ```bash
   cd .claude/hooks && sha256sum *.py > hooks.sha256sum
   git add hooks.sha256sum
   ```
2. Au début de chaque hook, valider:
   ```python
   def _verify_self():
       expected = (Path(__file__).parent / "hooks.sha256sum").read_text()
       actual = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
       if actual not in expected:
           sys.stderr.write(f"[MUNINN SECURITY] Hook checksum mismatch: {Path(__file__).name}\n")
           sys.exit(0)  # exit silent pour ne pas casser Claude Code
   ```
3. Restreindre permissions: `chmod 0750 .claude/hooks/*.py`.

**Note RULE 2**: c'est un changement défensif, pas destructif. Pas besoin de confirmation supplémentaire.

### A8 — Hook log rotation + audit trail (20min) [C6, C7]

**Source**: Agent 3 (errors/observability)

**Fichier nouveau**: `engine/core/_hook_logger.py`

**Patch**:
```python
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
import logging

LOG_PATH = Path.home() / ".muninn" / "hook_errors.log"
LOG_MAX_BYTES = 1_000_000  # 1 MB
LOG_BACKUP_COUNT = 3

def get_hook_logger():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("muninn.hooks")
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s:%(funcName)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    return logger
```

**Migrer** `bridge_hook._log_hook_error` + `muninn_feed._log_sync_error` vers ce logger commun.

**Action immédiate** sur les 616 erreurs accumulées:
```bash
sort ~/.muninn/hook_errors.log | uniq -c | sort -rn | head -20  # pattern dominant
mv ~/.muninn/hook_errors.log ~/.muninn/hook_errors.log.archive_2026-05-08
```

---

## §3 Phase B — Robustesse + observabilité (3-4h)

| # | Issue | Effort | Source |
|---|---|---|---|
| H3 | `_tree_lock` timeout=5s mais procède quand même → silent loss | 30min | Agent 6 |
| H4 | `bridge_fast` generic `except` → empty silent | 20min | Agent 6 |
| H5 | `tree.lock` orphan cleanup (`cleanup_tmp_files` ne tourne pas) | 15min | Agent 6 |
| H10 | Cache `_id_to_name` (7 sites mycelium.py) | 30min | Agent 2 |
| H11 | WAL checkpoint fail logged | 15min | Agent 3 (couvert par A8) |
| H12 | `cube_providers.get_related_cubes` empty silent | 30min | Agent 3 |
| H14 | `MUNINN_META_PATH` documentation | 10min | Agent 7 |
| H15 | Audit drift `muninn/_engine.py` vs `engine/core/muninn.py` | 1h | Agent 7 |
| M1 | `_REPO_PATH` global mutable → context manager | 1h | Agent 1 |
| M2 | Fixture autouse `_repo_path_isolate` | 30min | Agent 1 |
| M3 | UNION ALL 2× percentile → CTE single query | 30min | Agent 2 |
| M6 | Refactor `gen_props()` <200L | 1h | Agent 4 (confirmer avec Sky pour forge.py canonical) |
| M7 | xfail TLS test ou fix `isinstance` | 30min | Agent 4 |
| M11 | Schema validation `load_tree()` (jsonschema/manuel) | 30min | Agent 6 |

### `doctor` command [NEW Run3]

Agent 6 propose une commande `muninn doctor` qui:
- Check `tree.json` schema
- Check `mycelium.db` integrity
- Cleanup `.lock` orphelins >1h
- Check `.mn` CRC (si on ajoute le header version)
- Report stderr + exit code

Estimé: **1h** pour version basique. À ajouter en Phase B si bandwidth.

---

## §4 Phase C — Hygiène + supply chain (3-4h)

| # | Issue | Effort | Source |
|---|---|---|---|
| H6 | Lockfile (`pip-compile` ou `poetry lock`) | 30min | Agent 8 |
| M4 | `compress_file` chunking par section ≥50MB | 2h | Agent 2 |
| M9 | Retirer PowerShell fallback ANTHROPIC_API_KEY + TimeoutExpired | 20min | Agent 5 |
| M10 | `isinstance(dict)` post-`json.loads` (watchdog, sync_backend) | 20min | Agent 5 |
| M12 | `.mn` magic header `# MUNINN\|v2\|<crc>` | 1h | Agent 6 |
| M13 | Backup strategy continue WAL incremental | 1h | Agent 6 |
| M14 | Version sync 0.9.1 → 0.9.2 + git tag + single-source | 30min | Agent 7, 8 |
| M15 | Consolider imports répétés dans `muninn.py` | 30min | Agent 7 |
| M16 | Documenter env vars dans CLAUDE.md §Configuration | 30min | Agent 7 |
| M17 | README cleanup (12 layers, retirer "MEMORY.md", "zero deps", "Linux only", "100% regex") | 30min | Agent 7 |
| M18 | CI: ajouter `pytest tests/ -m "not slow"`, `mypy`, coverage | 1h | Agent 8 |
| M19 | `.github/dependabot.yml` weekly | 15min | Agent 8 |

---

## §5 Phase D — Parking lot

| # | Issue | Décision |
|---|---|---|
| M5 | 300 property tests = smoke only | **Garder** comme regression-crash. Ajouter 5-10 tests comportementaux par module critique en mode lent. |
| M8 | Fallback JSON full scan O(E) | Pre-index `_conns_index` au load. Peu utilisé en prod (Sky a SQLite). |
| L1, L11 | Single-instance assumption + drift shim | Test CI `assert set(dir(muninn._engine)) >= set(dir(engine.core.muninn))`. |
| L2 | Import failure cascade `muninn_layers` | Ajouter `muninn.health()`. |
| L3 | Double-bare-except `_dc_to_dict` | Couvert par A8 logger. |
| L8 | `anomalies.jsonl` 477 stale | Cron purge >7j. |
| L9 | CI `forge --gen-props` par module | Step CI matrix. |
| L12 | Logging framework central | Étendre `_hook_logger` à `_muninn_logger`. |
| L13 | `watchdog.py` dead code (Windows Task Scheduler) | **Décider avec Sky**: wire (Windows support officiel) ou supprimer. |
| L14 | Naming `repo_path/_REPO_PATH/MUNINN_REPO` | Standardiser après refactor M1 (context manager). |
| L15 | 40MB PNG committés | Préemptif: `.gitattributes` LFS si croissance. |
| L4-L7, L10 | Divers low-impact | Couverts au fur et à mesure. |

---

## §6 Ce qu'on NE FAIT PAS

- **Pas de refactor architecture muninn/ ↔ engine/core/.** BUG-091 fermé. Shims marchent (sauf `_engine.py` à auditer en H15).
- **Pas de purge mycelium local (67% orphans).** Dette de données, pas de code. Sky décidera.
- **Pas de touche à L9 LLM compress** sauf le fix C1 (redact_secrets). Coût API, désactivé par défaut.
- **Pas de fix BUG-104 L12 BudgetMem.** 3-4h refactor, parking lot, opt-in.
- **Pas de touche à `forge.py` sans Sky.** 4 copies, dont 1 standalone que Sky débugge. Pour M6, demander avant.
- **Pas de Git LFS migration.** Peut casser des workflows; préemptif `.gitattributes` seulement.
- **Pas de migration vers Poetry.** `pip-tools` (`requirements.lock`) suffit pour H6.

---

## §7 Validation finale (Phase A done)

**Commandes verbatim — copier-coller, capturer la sortie dans le commit**:

```bash
# 1. Test suite verte (incluant nouveaux tests Phase A)
pytest tests/ -q --tb=no 2>&1 | tail -3

# 2. Path traversal blocked
pytest tests/test_path_traversal.py -v

# 3. Concurrency stress
pytest tests/test_mycelium_db_concurrency.py -v

# 4. Mycelium integrity
python -c "import sys; sys.path.insert(0,'engine/core'); from mycelium_db import MyceliumDB; db = MyceliumDB('.muninn/mycelium.db'); print('integrity OK' if db._check_integrity() else 'CORRUPTED')"

# 5. .mn corruption tolerance
pytest tests/test_mn_corruption.py -v

# 6. L9 redaction
pytest tests/test_l9_redaction.py -v

# 7. Sentinel false positive rate
python tests/sentinel_fp_check.py  # script à écrire, run sur 100 prompts d'audit

# 8. Hook integrity
sha256sum -c .claude/hooks/hooks.sha256sum

# 9. Hook log fresh
wc -l ~/.muninn/hook_errors.log

# 10. Bridge_fast latency (regression check)
time python -c "import sys; sys.path.insert(0,'engine/core'); from pathlib import Path; import muninn; muninn._REPO_PATH=Path('.').resolve(); muninn._refresh_tree_paths(); print(muninn.bridge_fast('mycelium tree compression'))"
# attendu: <0.5s
```

**Tous OK = Phase A done, on peut reprendre les nouvelles features. Phase B/C en background.**

---

## §8 Sources verbatim — 8 agents senior

| Agent | Run | Axe | Durée | Output tokens |
|---|---|---|---|---|
| A1 | R2 | Threading & state | 87s | ~4K |
| A2 | R2 | Performance | 132s | ~6K |
| A3 | R2 | Errors & observability | 62s | ~4K |
| A4 | R2 | Test quality | 305s | ~4K |
| A5 | R3 | Security depth | 152s | ~5K |
| A6 | R3 | Data integrity & failure modes | 105s | ~5K |
| A7 | R3 | Codebase rot & API surface | 183s | ~5K |
| A8 | R3 | CI/CD & supply chain | 114s | ~5K |

Chaque ligne du tableau §1 est traçable à un `file:line` cité par un agent. Les outputs complets sont dans le transcript de la session (jsonl) du 2026-05-08.

---

## §9 Estimation totale

| Phase | Effort | Cumulatif |
|---|---|---|
| A — Security + data integrity | 4-5h | 5h |
| B — Robustesse + observabilité | 3-4h | 9h |
| C — Hygiène + supply chain | 3-4h | 13h |
| D — Parking lot | variable | backlog |

**Phase A obligatoire avant prod sérieuse. B+C peuvent s'étaler sur 2-3 semaines.** D = on traite au fil de l'eau quand on touche le module concerné.

**Note senior dev consolidée actuelle**: 6/10. Après Phase A: ~7.5/10. Après Phase B+C: ~8.5/10.
