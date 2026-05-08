# CHUNKS À CORRIGER — Audit Run 2 + Run 3 (consolidé)

**Date** : 2026-05-08
**Source** : 8 agents senior (BATTLE_PLAN_AUDIT2_2026-05-08.md)
**Méthodo** : chaque chunk a été VÉRIFIÉ verbatim dans le code actuel (file:line confirmé). Findings agent corrigés/affinés là où nécessaire.

**Statut** : 🟢 **17/32 chunks done** (Phase A 8/8 + Phase B 9/11) — 2026-05-08

| Chunk | Push hash | Tests verts |
|---|---|---|
| **A1** L9 redact_secrets defense-in-depth | `290075d` | 7 |
| **A2** UnicodeDecodeError .mn (4 sites) | `eb29eb1` | 5 |
| **A3** PRAGMA integrity_check helper | `ad152d4` | 5 |
| **A4** transcript_path whitelist | `5858445` | 7 |
| **A5** Lock SQLite reads (9 sites) | `af60c9d` | 5 |
| **A6** Sentinel calibration | `840b3fb` | 17 |
| **A7** Hook integrity manifest + 0750 | `c4c237e` | 6 |
| **A8** Hook log rotation centralisé | `767d52c` | 6 |
| **B1** save_tree hard-fail on lock | `676a5eb` | 4 |
| **B2** bridge_fast granular except | `a1bfdac` | 4 |
| **B3** cache _id_to_name (9 sites) | `ee9438d` | 4 |
| **B4** cleanup orphan .lock files | `bb550d2` | 6 |
| **B5** cube_providers granular | `133bbcb` | 4 |
| **B7** autouse _repo_path_isolate | `5279a1d` | 4 |
| **B8** _get_high_degree single scan | `f216fc8` | 4 |
| **B10** TLS isinstance fix (BUG-091) | `887b082` | 14 |
| **B11** doctor() extensions | `4369c66` | 4 |

**B6** (_REPO_PATH context manager) et **B9** (forge.gen_props refactor — touche `forge.py` standalone) en pending.

### Phase C — 12/13 done (C9 marqué N/A — faux positif agent)

| Chunk | Push hash | Tests verts |
|---|---|---|
| **C1** constraints.txt (pip lock) | `b3e1bbc` | 4 |
| **C2** load_tree schema validation | `6d618b8` | 6 |
| **C3** compress_file size guard 50 MB | `abd5344` | 5 |
| **C4** retire PowerShell ANTHROPIC_API_KEY fallback | `d0bb210` | 3 |
| **C5** isinstance(dict) post json.loads | `6178911` | 6 |
| **C6** .mn magic header + version + CRC32 | `1dcdc7b` | 8 |
| **C7** scripts/backup_mycelium.py | `f45217f` | 7 |
| **C8** version single source via importlib.metadata | `6858f5f` | 3 |
| **C9** *N/A* (cités lignes étaient des f-string templates, pas du code) | — | — |
| **C10+C11** doc env vars + README drift | `cdc1fee` | 5 |
| **C12** CI pytest job (proposed; needs `workflow` scope) | `99ecc89` | 2 + 5 skipped |
| **C13** Dependabot config | `53f2ef5` | 5 |

**Total: 30/32 chunks done (Phase A 8/8 + Phase B 9/11 + Phase C 12/13).**
Pending: B6, B9 (Sky-pending forge.py).
Manual merge required: C12 yaml (token sans `workflow` scope).

---

## ⚠️ Corrections vs rapports agents

Avant de figer la liste, **3 findings agent étaient inexacts** (vérifié à la lecture):

1. **Agent 6 disait `muninn_tree.py:524` lit .mn sans try/except** → **FAUX**. Lignes 523-527 sont DÉJÀ wrappées `try/except (UnicodeDecodeError, PermissionError, OSError)`. À retirer du chunk C2.
2. **Agent 5 disait `compress_file` redact avant `_llm_compress`** → **FAUX**. Aucun appel à `redact_secrets_text` n'est fait dans le pipeline `compress_file()` (`muninn_layers.py:1318-1393`). Le grep confirme: `_redact_secrets_text` n'apparaît qu'à 1 site dans muninn_tree.py:3719 (sur des facts isolés). Le fix C1 doit donc couvrir **TOUS** les appels à `_llm_compress`, pas juste cold-branch.
3. **Agent 3 disait `cube.py:216` est path traversal CRITICAL** → **EXAGÉRÉ**. Le `Path(root) / fname` vient de `os.walk(repo)` qui ne suit pas les symlinks par défaut. Risque réel = LOW, pas CRITICAL. Fix néanmoins recommandé en defense-in-depth.

---

## PHASE A — 8 chunks blockers (4-5h)

### CHUNK A1 — L9 redact_secrets sur **TOUS** les chemins (escaladé)

**Severity**: 🔴 CRITICAL
**Effort**: 30min (élargi vs plan v1)
**Files**:
- `engine/core/muninn_layers.py:1391` (pipeline `compress_file`)
- `engine/core/muninn_tree.py:2887` (cold-branch path)

**Diagnostic verbatim** (`muninn_layers.py:1390-1391`):
```python
# Layer 9: LLM self-compress (optional, for large outputs)
result = _llm_compress(result, context=str(filepath.name))
```

**Diagnostic verbatim** (`muninn_tree.py:2884-2887`):
```python
content = filepath.read_text(encoding="utf-8")
original_lines = len(content.split("\n"))
# Apply L9 (LLM compression) if branch is large enough
compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
```

**Pourquoi c'est cassé**:
`_llm_compress` envoie le texte directement à Anthropic via `client.messages.create(...)` (ligne 1264). Pas de redact dans `_llm_compress` lui-même. Pas de redact en amont dans le pipeline `compress_file`. Pas de redact dans le cold-branch. **Tous les chemins L9 leakent potentiellement des secrets vers l'API**.

**Ce qu'il faut faire**:
- Option A (sûre): ajouter `text = _redact_secrets_text(text)` en première ligne de `_llm_compress` lui-même. Une seule modif, couvre tous les callers.
- Option B (plus explicite): ajouter le redact aux 2 sites callers (compress_file + cold-branch).

Recommandation: **Option A** — le redact dans `_llm_compress` est defense-in-depth et garantit qu'aucun futur caller ne pourra leaker.

**Tests à écrire** (`tests/test_l9_redaction.py`):
1. `test_llm_compress_redacts_ghp_token`: appeler `_llm_compress("api_key=ghp_REAL_LOOKING_TOKEN_PATTERN_xxxxxxxx")`, mocker `client.messages.create` pour capturer l'input réel envoyé, asserter que `ghp_` n'apparaît pas dans le call.
2. `test_llm_compress_redacts_sk_token`: idem avec `sk-...`.
3. `test_compress_file_redacts_before_l9`: créer un fichier temp avec un token, appeler `compress_file(tmp)`, mocker l'API, asserter token absent.
4. `test_cold_branch_redacts_before_l9`: forcer le path `prune` cold-branch avec une .mn contenant un token, asserter token absent à l'API.

**Validation finale**:
```bash
pytest tests/test_l9_redaction.py -v  # 4 passed
grep -n "_redact_secrets_text\|redact_secrets" engine/core/muninn_layers.py  # doit montrer l'appel
```

---

### CHUNK A2 — UnicodeDecodeError handlers sur .mn (3 sites confirmés)

**Severity**: 🔴 CRITICAL
**Effort**: 30min
**Files**: `engine/core/muninn_tree.py` lignes **751, 812, 827, 2884**

**Diagnostic verbatim** (`muninn_tree.py:751`):
```python
def grow_branches_from_session(mn_path: Path, session_sentiment: dict = None):
    ...
    if not mn_path.exists():
        return 0

    content = mn_path.read_text(encoding="utf-8")  # ← l.751 PAS PROTÉGÉ
```

**Diagnostic verbatim** (`muninn_tree.py:811-812`):
```python
if existing_file.exists():
    existing_text = existing_file.read_text(encoding="utf-8")  # ← l.812 PAS PROTÉGÉ
```

**Diagnostic verbatim** (`muninn_tree.py:827`):
```python
old = filepath.read_text(encoding="utf-8")  # ← l.827 PAS PROTÉGÉ
```

**Diagnostic verbatim** (`muninn_tree.py:2884` — bonus, agent 6 ne l'a pas listé):
```python
content = filepath.read_text(encoding="utf-8")  # cold-branch, l.2884 PAS PROTÉGÉ
```

**Note**: ligne 524 (`read_node`) est DÉJÀ protégée — agent 6 s'est trompé là-dessus.

**Pourquoi c'est cassé**:
Si un .mn est tronqué (process killed pendant write), `read_text(encoding="utf-8")` lève `UnicodeDecodeError`. Aucun handler → exception remonte → `grow_branches_from_session` crash → tout le pipeline ingestion `feed_from_hook` s'arrête.

**Ce qu'il faut faire**:
1. Créer un helper `_safe_read_mn(path: Path) -> str | None` dans `muninn_tree.py` qui:
   - Lit le fichier en UTF-8
   - Catch `UnicodeDecodeError`, `OSError`
   - Log l'erreur via le futur `_hook_logger` (chunk A8)
   - Retourne `None` (caller skip si None)
2. Remplacer les 4 sites par `text = _safe_read_mn(path); if text is None: continue/return 0`.

**Tests à écrire** (`tests/test_mn_corruption_resilience.py`):
1. `test_grow_branches_handles_truncated_utf8`: écrire `.mn` avec UTF-8 tronqué (`b"## sec\nfact:é ok\n## br\n\xc3"`), appeler `grow_branches_from_session`, vérifier no crash + count==0.
2. `test_merge_branch_handles_corrupt_existing`: créer un branche existante, corrompre son `.mn` (truncated UTF-8), appeler `grow_branches_from_session` avec nouveau contenu, vérifier no crash + nouveau .mn créé sans tenter merge.
3. `test_cold_branch_recompress_handles_corrupt`: appeler `prune()` avec une cold branch dont le .mn est truncated, vérifier que prune complete sans crash et que la branch est marquée.

**Validation finale**:
```bash
pytest tests/test_mn_corruption_resilience.py -v  # 3 passed
grep -n "read_text(encoding" engine/core/muninn_tree.py  # tous les sites doivent passer par _safe_read_mn
```

---

### CHUNK A3 — PRAGMA integrity_check au boot mycelium

**Severity**: 🔴 CRITICAL
**Effort**: 20min
**File**: `engine/core/mycelium_db.py` (`__init__` ou helper)

**Diagnostic verbatim**: `grep -n "PRAGMA integrity_check" engine/core/mycelium_db.py` → **0 matches**. Le fichier configure `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA foreign_keys=ON`, mais jamais d'integrity_check.

**Pourquoi c'est cassé**:
Si la DB est corrompue (fsync issue, ext4 bug, kill -9 pendant un commit, disk full), `sqlite3.connect()` réussit mais les queries retournent des données incohérentes. `bridge_fast()` (`muninn_tree.py:2098`) a un `except Exception: return ""` → l'utilisateur voit juste un bridge silencieux. Pas de signal de corruption.

**Ce qu'il faut faire**:
1. Ajouter méthode `_check_integrity(self) -> tuple[bool, str]` dans `MyceliumDB`:
   - Exécute `PRAGMA integrity_check` (retourne "ok" ou liste d'erreurs)
   - Exécute `PRAGMA wal_checkpoint(RESTART)` pour merger WAL avant utilisation
   - Retourne `(True, "ok")` ou `(False, error_message)`
2. Appeler dans `__init__` après `_open` mais une seule fois (coût ~100-500ms sur 1.2GB):
   - Si fail → log erreur + lever `IntegrityError` OU continuer en mode dégradé (à décider avec Sky).
3. Optionnel: skip l'integrity_check si DB <100MB (test path) via flag.

**Tests à écrire** (`tests/test_mycelium_db_integrity.py`):
1. `test_integrity_ok_on_fresh_db`: créer une DB neuve, asserter `_check_integrity() == (True, "ok")`.
2. `test_integrity_fails_on_garbage`: écrire `b"NOT A SQLITE FILE"` dans le path, asserter que l'init lève une exception claire.
3. `test_integrity_fails_on_truncated`: créer une DB normale, tronquer à 1KB, asserter detection.

**Validation finale**:
```bash
pytest tests/test_mycelium_db_integrity.py -v
python -c "import sys; sys.path.insert(0,'engine/core'); from mycelium_db import MyceliumDB; db = MyceliumDB('.muninn/mycelium.db'); print(db._check_integrity())"
# attendu: (True, 'ok')
```

---

### CHUNK A4 — Path validation `transcript_path` (hook input)

**Severity**: 🟡 HIGH (downgraded de CRITICAL après vérif)
**Effort**: 15min
**File**: `engine/core/muninn_feed.py:1134-1142`

**Diagnostic verbatim** (`muninn_feed.py:1134-1142`):
```python
transcript_path = hook_input.get("transcript_path")
if not transcript_path:
    print(f"MUNINN {hook_event}: no transcript_path in hook data", file=sys.stderr)
    sys.exit(1)

jsonl_path = Path(transcript_path)
if not jsonl_path.exists():
    print(f"MUNINN {hook_event}: transcript not found: {_m._safe_path(jsonl_path)}", file=sys.stderr)
    sys.exit(1)
```

**Pourquoi c'est cassé**:
`transcript_path` vient du JSON stdin envoyé par Claude Code. Pas de validation que le path est sous `~/.claude/projects/...`. Si une payload malicieuse arrive (process compromise local), peut faire lire `/etc/passwd` ou exfiltrer fichiers privés.

**Note `cube.py:216`**: même catégorie mais path vient de `os.walk(repo)` qui follow_links=False. Risque réel quasi nul. Defense-in-depth optionnelle. **Pas dans Phase A** — déplacer en Phase B.

**Ce qu'il faut faire**:
1. Whitelist: `jsonl_path.resolve()` doit être sous `Path.home() / ".claude" / "projects"`.
2. Si pas: `sys.exit(1)` avec message clair.

**Tests à écrire** (`tests/test_hook_path_validation.py`):
1. `test_feed_refuses_etc_passwd`: simuler hook input avec `transcript_path="/etc/passwd"`, asserter SystemExit + message stderr.
2. `test_feed_refuses_outside_claude_projects`: simuler `transcript_path="/tmp/evil.jsonl"`, asserter refusé.
3. `test_feed_accepts_valid_claude_path`: simuler chemin réaliste sous `~/.claude/projects/`, asserter ouverture.

**Validation finale**:
```bash
pytest tests/test_hook_path_validation.py -v
```

---

### CHUNK A5 — Lock SQLite reads + migration (mycelium_db.py)

**Severity**: 🟡 HIGH
**Effort**: 45min
**File**: `engine/core/mycelium_db.py`

**Diagnostic verbatim** (sites confirmés ligne par ligne):

```python
# l.254 _migrate_schema — pas de with self._lock
def _migrate_schema(self):
    current = self._conn.execute("PRAGMA user_version").fetchone()[0]
    ...

# l.327 get_meta — pas de with self._lock
def get_meta(self, key: str, default: str = None) -> str:
    row = self._conn.execute(
        "SELECT value FROM meta WHERE key = ?", (key,)
    ).fetchone()

# l.346 get_connection — pas de with self._lock sur le SELECT (ligne 354)
# l.430 get_all_connections — pas de lock
# l.470 connection_count — pas de lock
# l.475 fusion_count — pas de lock
# l.480 has_connection — pas de lock
# l.493 has_fusion — pas de lock
```

`set_meta` (l.336) et `_get_or_create_concept` (l.283) ont déjà `with self._lock:`. Asymétrie.

**Pourquoi c'est cassé**:
SQLite WAL mode permet readers et writers en parallèle, mais Python sqlite3 module a un threading model fragile sans lock côté app. Sous concurrence, un read pendant write peut voir un état mi-commit (rare mais constatable). `_migrate_schema` sans lock est encore pire: 2 process qui ouvrent la DB simultanément peuvent both START migration → INSERT/PRAGMA en concurrence → DB en état incohérent.

**Ce qu'il faut faire**:
1. Wrapper avec `with self._lock:` les fonctions:
   - `_migrate_schema` (du début ligne 256 à la fin ligne 270)
   - `get_meta` (l.327-332)
   - `get_connection` (autour des SELECT l.354-368)
   - `get_all_connections` (l.428-447)
   - `get_all_fusions` (l.450-468)
   - `connection_count` (l.470-473)
   - `fusion_count` (l.475-478)
   - `has_connection` (l.488-490)
   - `has_fusion` (l.501-503)
2. Note: `_concept_name` (l.309) a DÉJÀ le lock — bon modèle à suivre.

**Tests à écrire** (`tests/test_mycelium_db_concurrency.py`):
1. `test_concurrent_read_write_no_corruption`: 2 threads writer (`set_meta`) + 4 threads reader (`get_meta`) sur 1000 itérations. Asserter aucune exception.
2. `test_concurrent_migrate_no_double_init`: créer 2 instances `MyceliumDB(same_path)` en thread parallèles, asserter qu'une seule fait la migration.
3. `test_get_all_connections_consistent_under_write`: thread writer ajoute 1000 edges, thread reader call `get_all_connections()` 100x, asserter chaque snapshot a une longueur monotone.

**Validation finale**:
```bash
pytest tests/test_mycelium_db_concurrency.py -v
python forge.py --gen-props engine/core/mycelium_db.py
pytest tests/test_props_mycelium_db.py -q
```

---

### CHUNK A6 — Sentinel calibration (recalibrate triggers + entropy)

**Severity**: 🟡 HIGH
**Effort**: 30min
**File**: `.claude/hooks/bridge_hook.py:58-90`

**Diagnostic verbatim** (`bridge_hook.py:58-90`):
```python
_SECRET_TRIGGERS = re.compile(
    r'(?:cl[eé]|key|password|mdp|mot de passe|passwd|secret|token|passphrase'
    r'|api.?key|credentials?|auth)',
    re.IGNORECASE
)

def _check_secrets(prompt):
    ...
    # 2. Check for password-like strings near trigger words
    if _SECRET_TRIGGERS.search(prompt):
        words = prompt.split()
        for word in words:
            clean = word.strip('.,;:!?\'"/()[]{}')
            if len(clean) >= 6 and _has_char_diversity(clean) and _shannon_entropy(clean) > 2.8:
                return "[MUNINN SENTINEL] You may have typed a password..."
```

**Observation LIVE** (audit en cours): Sentinel a déclenché ~7 fois pendant cette session sur des prompts SANS secret réel — uniquement à cause des mots `secret`, `key`, `auth` dans des phrases du genre "audit security patterns" ou "secret_key in code". User finit par ignorer les warnings (cry-wolf).

**Pourquoi c'est cassé**:
- Pas de word boundaries → `secret` matche dans `secretariat`, `secrets.py`, etc.
- Triggers `auth`, `key` seuls trop génériques (matchent dans tout discours technique sur la sécurité).
- Entropy threshold 2.8 trop bas → matche des mots anglais courants.

**Ce qu'il faut faire**:
1. Ajouter word boundaries: `r'\b(?:cl[eé]|key|password|...|auth)\b'`.
2. Retirer `auth` et `key` standalone (gardés `api.?key`, `auth_token`, etc.).
3. Élever entropy threshold de `2.8` → `3.5` pour le check trigger-adjacent (passwords/hashes, pas mots anglais).
4. Optionnel: whitelist de mots techniques courants (`secretariat`, `secrets`, `keystone`, `keychain`).
5. **Note importante**: la branche standalone (sans trigger) à la ligne 87 a entropy `> 3.5` — ne pas y toucher, c'est déjà OK.

**Tests à écrire** (`tests/test_sentinel_calibration.py`):
1. `test_sentinel_no_fp_on_audit_jargon`: liste de 20 prompts d'audit (incluant ceux observés live), asserter que TOUS retournent `None`.
2. `test_sentinel_still_catches_real_token`: tokens réalistes (`ghp_xxx...`, `sk-xxx...`, password high-entropy comme `Tr0ub4dor&3xxx`), asserter détection.
3. `test_sentinel_fp_rate_below_5_percent`: dataset de 100 prompts dev courants, asserter <5% de FP.

**Validation finale**:
```bash
pytest tests/test_sentinel_calibration.py -v
# observation manuelle pendant 1 session entière: pas plus de 1-2 warnings sur des secrets non-réels
```

---

### CHUNK A7 — Hook integrity (sha256sum + perms)

**Severity**: 🟡 HIGH
**Effort**: 30min
**Files**: `.claude/hooks/*.py` (9 fichiers)

**Diagnostic verbatim**:
```
-rwxr-xr-x 1 sky sky 6061  8 mai 06:53 .claude/hooks/bridge_hook.py
-rwxr-xr-x 1 sky sky 5643 23 avr 18:32 .claude/hooks/config_change_hook.py
-rwxr-xr-x 1 sky sky 3290 23 avr 18:32 .claude/hooks/notification_audit_hook.py
... (9 fichiers tous en 0755 = world-readable, world-executable)
```

**Pourquoi c'est cassé**:
Permissions `-rwxr-xr-x` (mode 0755). Pas de checksum vérifié avant exec. Quelqu'un avec accès au home (process malveillant local, rsync mal configuré, repo cloné depuis un fork malveillant) peut modifier `bridge_hook.py` → code execution dans la prochaine session Claude Code.

**Ce qu'il faut faire**:
1. Générer `.claude/hooks/hooks.sha256sum` et le commiter:
   ```bash
   cd .claude/hooks && sha256sum *.py > hooks.sha256sum && git add hooks.sha256sum
   ```
2. Au début de chaque hook, ajouter une fonction `_verify_self()` qui:
   - Lit `hooks.sha256sum`
   - Calcule le sha256 du fichier courant (`Path(__file__).read_bytes()`)
   - Compare. Si mismatch: stderr warning + `sys.exit(0)` (silent pour ne pas casser Claude Code).
3. Restreindre permissions: `chmod 0750 .claude/hooks/*.py` (owner+group, pas world).
4. Ajouter step CI: `sha256sum -c .claude/hooks/hooks.sha256sum` doit passer.

**Tests à écrire** (`tests/test_hook_integrity.py`):
1. `test_all_hooks_have_known_sha`: lire `hooks.sha256sum`, calculer sha pour chaque .py présent, asserter match.
2. `test_modified_hook_fails_verify` (subprocess): créer copie d'un hook avec 1 byte différent, vérifier qu'il exit silencieusement.

**Validation finale**:
```bash
sha256sum -c .claude/hooks/hooks.sha256sum
ls -la .claude/hooks/*.py | head -3  # doit montrer -rwxr-x--- (0750)
pytest tests/test_hook_integrity.py -v
```

---

### CHUNK A8 — Hook log rotation + audit trail centralisé

**Severity**: 🔴 CRITICAL (couvre C6+C7)
**Effort**: 30min
**Files**:
- Nouveau: `engine/core/_hook_logger.py`
- Modifs: `.claude/hooks/bridge_hook.py:_log_hook_error`, `engine/core/muninn_feed.py:_log_sync_error` (l.1100-1116)

**Diagnostic verbatim** (`muninn_feed.py:1115-1116`):
```python
        except Exception:
            pass
```

**Diagnostic verbatim** (état actuel `~/.muninn/hook_errors.log`):
```
644 lines accumulated since 2026-04-24 (14 days)
46 [bridge_hook:stdin_parse]  ← supposé fixé par commit 10c1049 mais entrées persistent
```

**Pourquoi c'est cassé**:
- `_log_sync_error` dans muninn_feed swallow ses propres erreurs (`except Exception: pass` l.1115). Si le disque est plein ou le fichier read-only, le logging-of-logging est perdu silencieusement → pas d'audit trail du tout.
- Pas de rotation: fichier croît sans limite.
- Pas d'alerting: 644 erreurs en 14 jours sans signal à Sky.

**Ce qu'il faut faire**:
1. Nouveau module `engine/core/_hook_logger.py` avec `RotatingFileHandler` (1MB max, 3 backups).
2. Migrer `bridge_hook._log_hook_error` ET `muninn_feed._log_sync_error` vers ce logger commun (importer + appeler).
3. **Pour le swallow `except: pass`**: remplacer par fallback stderr (au minimum, le user voit l'erreur dans le terminal Claude Code).
4. Action immédiate sur les 644 erreurs accumulées:
   - `sort ~/.muninn/hook_errors.log | uniq -c | sort -rn | head -20` → analyser les 46 stdin_parse pour comprendre pourquoi le fix n'a pas pris.
   - Archiver: `mv ~/.muninn/hook_errors.log ~/.muninn/hook_errors.log.archive_2026-05-08`.

**Tests à écrire** (`tests/test_hook_logger.py`):
1. `test_rotation_at_1mb`: spam 1.1MB de logs, asserter que le fichier ne dépasse pas 1MB et que `hook_errors.log.1` existe.
2. `test_log_to_stderr_when_file_unwritable`: monkeypatch `open()` pour lever PermissionError, asserter que stderr contient le message.
3. `test_legacy_log_hook_error_still_works`: appel direct à `bridge_hook._log_hook_error("test", Exception("x"))`, asserter ligne ajoutée.

**Validation finale**:
```bash
wc -l ~/.muninn/hook_errors.log  # < 1000 (après rotation)
ls -la ~/.muninn/hook_errors.log*  # 1-3 backups visibles
pytest tests/test_hook_logger.py -v
```

---

## PHASE B — 10 chunks robustesse + observabilité (3-4h)

### CHUNK B1 — `_tree_lock` timeout = silent loss

**Severity**: 🟡 HIGH
**Effort**: 30min
**File**: `engine/core/muninn_tree.py:173-200, 233, 267`

**Diagnostic verbatim** (`muninn_tree.py:233-235` dans `load_tree`):
```python
lock_f, acquired = _tree_lock(_m.TREE_META)
if not acquired:
    print("WARNING: tree lock timeout on load_tree, proceeding anyway", file=sys.stderr)
```

Idem ligne 267 dans `save_tree`.

**Pourquoi c'est cassé**:
Si timeout (5s) → "proceed anyway". Deux `save_tree` concurrents peuvent both procéder → both write tempfile → race sur `os.replace` → second writer wins, premier écrase. Silent loss.

**Ce qu'il faut faire**:
- Pour `save_tree`: convertir timeout en hard failure (`raise TimeoutError`).
- Pour `load_tree`: garder warning + proceed (read-only, moins critique). Optionnel: retry avec backoff.

**Tests à écrire** (`tests/test_tree_lock_save.py`):
1. `test_save_tree_blocks_when_locked`: thread A acquiert lock, thread B `save_tree` doit lever TimeoutError.
2. `test_load_tree_proceeds_warning_under_lock`: thread A acquiert lock, thread B `load_tree` retourne tree (best-effort).

---

### CHUNK B2 — `bridge_fast` generic except → silent ""

**Severity**: 🟡 HIGH
**Effort**: 20min
**File**: `engine/core/muninn_tree.py:2093-2099`

**Diagnostic verbatim**:
```python
try:
    if _m._CORE_DIR not in sys.path:
        sys.path.insert(0, _m._CORE_DIR)
    from mycelium import Mycelium
    m = Mycelium(repo)
except Exception:
    return ""
```

**Pourquoi c'est cassé**:
N'importe quelle erreur (DB corrompue, ImportError, FileNotFound) → empty bridge silencieux. User ne sait pas que mycelium est cassé.

**Ce qu'il faut faire**:
1. Différencier les erreurs:
   - `ImportError` → log warning "mycelium module unavailable", continuer.
   - `FileNotFoundError` (DB absent) → log info, continuer (premier run).
   - Autre exception → log via `_hook_logger` (chunk A8) avec traceback, retourner `""`.
2. Optionnel: ajouter compteur de fallbacks dans `~/.muninn/health.json` pour `muninn doctor`.

**Tests à écrire**: `tests/test_bridge_fast_failure_modes.py` avec 3 cas (DB absent, ImportError mocké, mycelium corrompu).

---

### CHUNK B3 — Cache `_id_to_name` dans `mycelium.py` (7 sites)

**Severity**: 🟡 HIGH
**Effort**: 30min
**File**: `engine/core/mycelium.py` lignes **434, 627, 879, 1291, 1614, 1676, 1857**

**Diagnostic**: à chaque site, pattern:
```python
id_to_name = {v: k for k, v in self._db._concept_cache.items()}
```

Recréé 7 fois. Sur DB Sky (180K concepts), ~400µs par appel × N sites × M fonctions/session = 50-100ms perdus inutilement.

**Note**: `mycelium_db.py:276` a déjà `self._id_to_name` exposé directement dans le DB. Donc le fix pourrait être encore plus simple: utiliser `self._db._id_to_name` directement aux 7 sites.

**Ce qu'il faut faire**:
- Option A: cache lazy `self._id_to_name_cache` dans Mycelium, invalidé sur reload.
- Option B (simpler): aux 7 sites, remplacer `id_to_name = {v:k for k,v in self._db._concept_cache.items()}` par `id_to_name = self._db._id_to_name` (déjà existe!).

Recommandation: Option B. C'est juste un oubli — la DB expose déjà la table inverse.

**Tests à écrire** (`tests/test_id_to_name_consistency.py`):
1. `test_id_to_name_matches_concept_cache`: après chargement DB, asserter `set(db._id_to_name.values()) == set(db._concept_cache.keys())`.
2. `test_get_compression_rules_uses_db_id_to_name`: monkeypatch `_concept_cache` à un dict vide, asserter que la fonction utilise toujours `_id_to_name`.

---

### CHUNK B4 — Cleanup `tree.lock` orphan

**Severity**: 🟡 MEDIUM
**Effort**: 15min
**File**: `engine/core/muninn_tree.py:114` (`cleanup_tmp_files`)

**Diagnostic verbatim**: `memory/tree.lock` (1 byte file daté 06:51). `cleanup_tmp_files` existe (l.114) mais n'est pas appelée régulièrement.

**Ce qu'il faut faire**:
1. Appeler `cleanup_tmp_files()` au boot de `muninn` (CLI entry point).
2. Étendre la fonction pour purger `*.lock` orphan >1h.

**Tests**: `tests/test_cleanup_orphan_locks.py` — créer un .lock daté il y a 2h, appeler cleanup, asserter supprimé.

---

### CHUNK B5 — `cube_providers.get_related_cubes` empty silent

**Severity**: 🟡 HIGH
**Effort**: 30min
**File**: `engine/core/cube_providers.py:1301`

**Diagnostic** (depuis agent 3): `except Exception: return []`. Caller bridge_fast voit `[]` et injecte zero contexte sans warning.

**Ce qu'il faut faire**:
1. Différencier "vraiment 0 résultats" vs "exception swallowed".
2. Si exception: log via `_hook_logger`, retourner sentinel `None`.
3. Caller bridge_fast: si `None` → warn user, sinon traiter `[]` normalement.

**Tests**: `tests/test_cube_providers_failure.py` — DB corrompue mock, asserter `None` retourné.

---

### CHUNK B6 — `_REPO_PATH` global → context manager

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**Files**: `engine/core/muninn.py` (global), `bridge_hook.py:138-139`, `subagent_start_hook.py`

**Diagnostic** (`bridge_hook.py:138-139`):
```python
muninn._REPO_PATH = Path(repo_path).resolve()
muninn._refresh_tree_paths()
```

**Pourquoi c'est cassé**: 2 hooks parallèles → race sur le global.

**Ce qu'il faut faire**:
1. Ajouter context manager `muninn.repo_context(repo_path: Path)` qui save/restore avec `threading.RLock`.
2. Refactor hooks pour utiliser `with muninn.repo_context(repo_path):` au lieu d'assignation directe.

**Tests**: `tests/test_repo_context_concurrent.py` — 4 threads, chacun avec son repo, asserter aucun cross-contamination.

---

### CHUNK B7 — Fixture autouse `_repo_path_isolate`

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**File**: `tests/conftest.py`

**Diagnostic**: les tests modifient `muninn._REPO_PATH` à la main, sans cleanup garanti. Si un test crash avant restore → pollution des tests suivants.

**Ce qu'il faut faire**:
1. Dans `tests/conftest.py`, ajouter:
   ```python
   @pytest.fixture(autouse=True)
   def _repo_path_isolate(monkeypatch, tmp_path):
       """Restore _REPO_PATH after every test."""
       import muninn
       orig = getattr(muninn, '_REPO_PATH', None)
       yield
       muninn._REPO_PATH = orig
       muninn._refresh_tree_paths()
   ```
2. Adapter `pytest -n auto` (parallel) — chaque worker isolé.

---

### CHUNK B8 — UNION ALL 2× percentile → CTE single query

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**File**: `engine/core/mycelium.py:866-888` (`_get_high_degree_concepts`)

**Diagnostic** (depuis agent 2): UNION ALL exécuté 2× pour calculer percentile + filtrer. Sur 11K edges = 2× full scan + 2× GROUP BY.

**Ce qu'il faut faire**: réécrire en CTE unique:
```sql
WITH degrees AS (
  SELECT id, COUNT(*) as deg FROM (SELECT a as id FROM edges UNION ALL SELECT b FROM edges)
  GROUP BY id
)
SELECT id FROM degrees WHERE deg >= (SELECT deg FROM degrees ORDER BY deg DESC LIMIT 1 OFFSET ?)
```

**Tests**: bench avant/après, asserter ≥30% gain sur 10K+ edges.

---

### CHUNK B9 — Refactor `gen_props()` <200L

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**File**: `forge.py` (3 copies dans MUNINN- + 1 standalone)

**⚠️ DÉPENDANCE SKY**: forge.py est maintenu en standalone à `/home/sky/Bureau/forge/`. Sky débugge activement. **Confirmer avec Sky avant de toucher** quelle copie est canonical.

**Diagnostic**: `test_brick20_architecture.py` FAILS. `gen_props()` >200L viole l'invariant.

**Ce qu'il faut faire** (après confirmation):
1. Refactor en 3 sous-fonctions: `_parse_signatures`, `_filter_destructive`, `_emit_test_code`.

---

### CHUNK B10 — TLS `isinstance` fix ou xfail

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**File**: `tests/test_phase4_tls.py`

**Diagnostic**: `isinstance(obj, TLSBackend)` rejette le shim version. Régression BUG-091 partielle.

**Ce qu'il faut faire**:
- Court terme: `@pytest.mark.xfail(reason="BUG-091 dual-import — see docs/BATTLE_PLAN_BUG091")`.
- Long terme: investigation sur `muninn/sync_tls.py` — assurer qu'il fait `from engine.core.sync_tls import TLSBackend` (pas une redéfinition).

---

### CHUNK B11 — `muninn doctor` command

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**File**: nouveau ou intégré dans `engine/core/muninn.py` CLI

**Note**: `doctor` apparaît déjà dans `__all__` de `muninn_tree.py` (l.28) — soit déjà partiellement implémenté, soit stub.

**Ce qu'il faut faire**:
1. Vérifier l'état actuel de `doctor` (read code).
2. Étendre pour:
   - Check `tree.json` schema validation
   - Run `mycelium_db._check_integrity()`
   - Cleanup `.lock` orphelins >1h
   - Check growth `~/.muninn/hook_errors.log`
   - Report stderr structuré + exit code (0=OK, 1=warnings, 2=critical)

**Tests**: `tests/test_doctor_command.py` — chaque check isolément.

---

## PHASE C — 12 chunks hygiène + supply chain (3-4h)

### CHUNK C1 — Lockfile dépendances

**Severity**: 🟡 HIGH
**Effort**: 30min
**File**: `pyproject.toml`, nouveau `requirements.lock`

**Diagnostic**: `tiktoken>=0.5`, `anthropic>=0.20` (ranges, non pinnés).

**Ce qu'il faut faire**:
1. `pip-compile pyproject.toml -o requirements.lock` (ou `poetry lock`).
2. Commiter `requirements.lock`.
3. CI: `pip install -r requirements.lock` au lieu de `pip install -e .`.

---

### CHUNK C2 — Schema validation `load_tree`

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**File**: `engine/core/muninn_tree.py` (`load_tree`)

**Diagnostic**: `load_tree` catch `JSONDecodeError` mais pas le cas `{"foo": "bar"}` (JSON valide, schema faux).

**Ce qu'il faut faire**:
- Ajouter validation manuelle des champs requis (`version`, `nodes`, `budget`) après `json.load`. Si manquant: backup + `init_tree()`.
- Pas besoin de jsonschema (dépendance) — validation manuelle suffit.

---

### CHUNK C3 — Compress_file chunking ≥50MB

**Severity**: 🟡 MEDIUM
**Effort**: 2h
**File**: `engine/core/muninn_layers.py:1337`

**Diagnostic**: `text = filepath.read_text(encoding="utf-8")` charge fichier entier. OOM-prone sur transcripts géants.

**Ce qu'il faut faire**:
- Split par section `text.split("##")` en streaming.
- Compresser chaque section indépendamment.
- Concaténer.

---

### CHUNK C4 — PowerShell fallback ANTHROPIC_API_KEY

**Severity**: 🟡 MEDIUM
**Effort**: 20min
**File**: `engine/core/muninn_layers.py:1254-1260`

**Diagnostic verbatim**:
```python
_r = _sp.run(['powershell', '-Command',
    "[System.Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')"],
    capture_output=True, text=True, timeout=5)
api_key = _r.stdout.strip() or None
```

**Ce qu'il faut faire**:
1. Retirer le bloc PowerShell (legacy Windows). Sky est sur Linux maintenant.
2. Si nécessaire de garder pour Windows: ajouter `subprocess.TimeoutExpired` handler explicite.
3. Validation format clé (longueur min 20).

---

### CHUNK C5 — `isinstance(dict)` post-`json.loads`

**Severity**: 🟡 MEDIUM
**Effort**: 20min
**Files**: `engine/core/watchdog.py:29`, `engine/core/sync_backend.py:90+`

**Diagnostic**: `data = json.loads(...)` puis `data.get(...)` sans isinstance check.

**Ce qu'il faut faire**: après chaque `json.loads`, ajouter `if not isinstance(data, dict): raise/skip`.

---

### CHUNK C6 — `.mn` magic header + version

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**File**: `engine/core/muninn_feed.py` (writes `.mn`), `engine/core/muninn_tree.py` (reads `.mn`)

**Ce qu'il faut faire**:
1. Au write: première ligne = `# MUNINN|v2|<crc32>`.
2. Au read: parse + valide CRC. Si fail: skip avec log.
3. Backwards-compat: si pas de header, traiter comme v1 legacy.

---

### CHUNK C7 — Backup WAL incremental mycelium

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**File**: nouveau script `scripts/backup_mycelium.sh`

**Diagnostic**: `mycelium.db.backup-2026-04-30` (8 jours stale).

**Ce qu'il faut faire**:
1. Script daily: `PRAGMA wal_checkpoint(TRUNCATE)` + `cp mycelium.db mycelium.db.YYYY-MM-DD`.
2. Garder 7 jours.
3. Documenter procédure restore.

---

### CHUNK C8 — Version sync 0.9.1 → 0.9.2 + git tag + single-source

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**Files**: `engine/core/muninn.py:21`, `muninn/__init__.py:18`, `pyproject.toml`

**Diagnostic**: drift 0.9.1 vs 0.9.2.

**Ce qu'il faut faire**:
1. Single source of truth: `pyproject.toml [project] version = "0.9.2"`.
2. Tous les `__version__` lisent depuis `importlib.metadata.version("muninn")`.
3. `git tag -a v0.9.2`.

---

### CHUNK C9 — Consolider imports répétés dans `muninn.py`

**Severity**: 🟢 LOW
**Effort**: 30min
**File**: `engine/core/muninn.py` (l.23 top + l.727, 876, 1012)

**Ce qu'il faut faire**: déplacer tous les `import json, os, sys, re` au top du module.

---

### CHUNK C10 — Documenter env vars

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**Files**: `CLAUDE.md`, `README.md`

**Diagnostic**: `MUNINN_META_PATH` (RED — non doc), `MUNINN_CONTEXT_SIZE`, `MUNINN_L12_BUDGET`, `MUNINN_GL_SOFTWARE` non documentées.

**Ce qu'il faut faire**: section `## Configuration / Env vars` dans CLAUDE.md avec tableau.

---

### CHUNK C11 — README cleanup (drift)

**Severity**: 🟡 MEDIUM
**Effort**: 30min
**File**: `README.md`

**Drift à corriger**:
- "11 layers" → 12 (ou "11 + L12 BudgetMem opt-in")
- "MEMORY.md ~200L" → fichier inexistant, retirer
- "zero deps" → "core zéro deps, L9 et L12 nécessitent anthropic + tiktoken"
- "Linux only" → "Linux primary, Windows fallback partiel"
- "100% regex" → "L0-L7+L10+L11 regex, L9 = API"

---

### CHUNK C12 — CI: pytest standard + mypy + coverage

**Severity**: 🟡 MEDIUM
**Effort**: 1h
**File**: `.github/workflows/ci.yml`

**Diagnostic**: CI utilise inline `python3 -` au lieu de pytest collection standard.

**Ce qu'il faut faire**:
1. Ajouter step `pytest tests/ -m "not slow" --cov=engine --cov=muninn`.
2. `mypy engine muninn --ignore-missing-imports`.
3. `permissions: { contents: read }` explicite.

---

### CHUNK C13 — Dependabot

**Severity**: 🟢 LOW
**Effort**: 15min
**File**: nouveau `.github/dependabot.yml`

**Ce qu'il faut faire**: weekly check pip + github-actions.

---

## PHASE D — Parking lot

| # | Issue | Décision |
|---|---|---|
| D1 | 300 property tests = smoke only | Garder. Ajouter 5-10 tests comportementaux par module critique. |
| D2 | Fallback JSON full scan O(E) | Pre-index `_conns_index`. Peu utilisé en prod. |
| D3 | `cube.py:216` defense-in-depth | Optionnel, risque réel quasi nul (os.walk no-symlinks). |
| D4 | `watchdog.py` dead code | **Décider avec Sky**: wire (Windows officiel) ou supprimer. |
| D5 | Naming `repo_path/_REPO_PATH/MUNINN_REPO` | Standardiser après B6 (context manager). |
| D6 | 40MB PNG committés | Préemptif `.gitattributes` LFS si croissance. |
| D7 | `anomalies.jsonl` 477 stale | Cron purge >7j. |
| D8 | CI `forge --gen-props` par module | Step CI matrix. |
| D9 | Logging framework central | Étendre `_hook_logger` à `_muninn_logger`. |
| D10 | Drift `muninn/_engine.py` (2100L) | Audit drift et reduce to shim si possible. |
| D11 | Tests CI `dir(muninn) == dir(engine.core)` | Anti-drift check. |
| D12 | Import failure cascade `muninn_layers` | `muninn.health()` qui expose modules dégradés. |

---

## RÉSUMÉ — Liste des chunks à corriger

### Phase A (critiques — 4-5h, 8 chunks)
1. **A1** L9 redact_secrets sur tous les chemins (`muninn_layers.py:1391` + `muninn_tree.py:2887`)
2. **A2** UnicodeDecodeError handlers .mn (`muninn_tree.py:751, 812, 827, 2884`)
3. **A3** PRAGMA integrity_check au boot (`mycelium_db.py`)
4. **A4** Path validation `transcript_path` (`muninn_feed.py:1139`)
5. **A5** Lock SQLite reads + migrate (`mycelium_db.py:254, 327, 346, 430, 470, 480, 493`)
6. **A6** Sentinel calibration (`bridge_hook.py:58-90`)
7. **A7** Hook integrity (sha256sum + 0750)
8. **A8** Hook log rotation centralisé (`muninn_feed.py:1115` + nouveau `_hook_logger.py`)

### Phase B (robustesse — 3-4h, 11 chunks)
9. **B1** `_tree_lock` timeout = hard fail sur save
10. **B2** `bridge_fast` granular except
11. **B3** Cache `_id_to_name` (7 sites mycelium.py)
12. **B4** Cleanup `tree.lock` orphan
13. **B5** `cube_providers.get_related_cubes` granular
14. **B6** `_REPO_PATH` context manager
15. **B7** Fixture `_repo_path_isolate` autouse
16. **B8** UNION ALL → CTE single query
17. **B9** Refactor `gen_props()` <200L (DEMANDER SKY)
18. **B10** TLS xfail ou fix isinstance
19. **B11** `muninn doctor` command

### Phase C (hygiène — 3-4h, 13 chunks)
20. **C1** Lockfile pip-compile
21. **C2** Schema validation load_tree
22. **C3** Compress_file chunking
23. **C4** Retirer PowerShell fallback
24. **C5** isinstance(dict) post json.loads
25. **C6** .mn magic header + CRC
26. **C7** Backup WAL incremental
27. **C8** Version sync + tag
28. **C9** Imports consolidés muninn.py
29. **C10** Documenter env vars
30. **C11** README drift cleanup
31. **C12** CI pytest standard
32. **C13** Dependabot

### Phase D (parking lot — backlog)
12 items documentés, traités au fil de l'eau.

---

**Total : 32 chunks Phase A+B+C, ~10-13h. Phase A obligatoire avant nouvelles features.**

Pour chaque chunk: file:line confirmé verbatim, diagnostic, fix prescrit, tests à écrire avant le fix (TDD), commande de validation finale.
