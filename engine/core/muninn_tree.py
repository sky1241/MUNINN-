"""Muninn tree structure, boot, prune, and intelligence."""

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from tokenizer import token_count
from _secrets import redact_secrets_text as _redact_secrets_text


class _ModRef:
    """Lazy reference to muninn module — avoids circular import."""
    def __getattr__(self, name):
        return getattr(sys.modules['muninn'], name)
    def __setattr__(self, name, value):
        setattr(sys.modules['muninn'], name, value)

_m = _ModRef()

__all__ = ['BUDGET', '_actr_activation', '_append_session_log', '_atomic_json_write', '_auto_backup_tree', '_days_since', '_ebbinghaus_recall', '_extract_error_fixes', '_get_tree_dir', '_get_tree_meta', '_light_prune', '_load_relevant_sessions', '_load_virtual_branches', '_refresh_tree_paths', '_safe_tree_path', '_sleep_consolidate', '_surface_insights_for_boot', '_surface_known_errors', '_tfidf_relevance', '_tokenize_words', '_tree_lock', '_tree_unlock', 'adapt_k', 'adaptive_boot_budget', 'boot', 'bridge', 'bridge_fast', 'build_tree', 'classify_session', 'cleanup_legacy_tree', 'cleanup_tmp_files', 'compute_hash', 'compute_temperature', 'detect_session_mode', 'diagnose', 'doctor', 'extract_tags', 'grow_branches_from_session', 'huginn_think', 'init_tree', 'inject_memory', 'load_tree', 'predict_next', 'prune', 'read_node', 'recall', 'refresh_tree_metadata', 'save_tree', 'show_status', 'spill_chunks_to_tree']


# ── BUDGET ────────────────────────────────────────────────────────

BUDGET = {
    "root_lines": 100,
    "branch_lines": 150,
    "leaf_lines": 200,
    "tokens_per_line": 16,
    "max_loaded_tokens": 50_000,  # default, overridden by adaptive_boot_budget()
    "compression_ratio": 4.6,
}


def adaptive_boot_budget(context_size: int = None) -> int:
    """Compute boot budget: 15% of context, floor 15K, cap 100K.

    If context_size not given, uses MUNINN_CONTEXT_SIZE env var or 200K default.
    """
    if context_size is None:
        try:
            context_size = int(os.environ.get("MUNINN_CONTEXT_SIZE", 200_000))
        except (ValueError, TypeError):
            context_size = 200_000
    budget = int(context_size * 0.15)
    return max(15_000, min(budget, 100_000))

# ── TREE STRUCTURE ────────────────────────────────────────────────

def _get_tree_dir():
    """Tree lives in target repo's .muninn/tree/, not in Muninn's own memory/.

    BUG-091 follow-up (2026-05-08): the legacy fallback `MUNINN_ROOT / "memory"`
    was the source of the recurring `tree.json b0002.lines=3` CI breakages.
    When tests/code call save_tree() without first setting _REPO_PATH, the
    fallback writes into MUNINN-/memory/tree.json (a tracked git file) and
    pollutes the working tree. Now we use MUNINN-/.muninn/tree/ as the
    fallback too — same shape as the runtime path but never tracked by git.
    """
    if _m._REPO_PATH:
        return _m._REPO_PATH / ".muninn" / "tree"
    return _m.MUNINN_ROOT / ".muninn" / "tree"

def _get_tree_meta():
    return _get_tree_dir() / "tree.json"

# Legacy globals — used everywhere, recomputed via properties


def _refresh_tree_paths():
    """Update _m.TREE_DIR/_m.TREE_META globals after _m._REPO_PATH is set."""
    # update on _m
    _m.TREE_DIR = _get_tree_dir()
    _m.TREE_META = _get_tree_meta()


def cleanup_legacy_tree():
    """C1: Remove memory/tree.json legacy if .muninn/tree/tree.json exists.

    Returns True if legacy was removed, False otherwise.
    """
    if not _m._REPO_PATH:
        return False
    legacy_dir = _m._REPO_PATH / "memory"
    legacy_tree = legacy_dir / "tree.json"
    new_tree = _m._REPO_PATH / ".muninn" / "tree" / "tree.json"

    if legacy_tree.exists() and new_tree.exists():
        try:
            legacy_tree.unlink()
            # Remove legacy .mn files that have copies in .muninn/tree/
            new_tree_dir = _m._REPO_PATH / ".muninn" / "tree"
            for mn_file in legacy_dir.glob("*.mn"):
                if (new_tree_dir / mn_file.name).exists():
                    mn_file.unlink()
            # Remove legacy dir if empty
            remaining = list(legacy_dir.iterdir())
            if not remaining:
                legacy_dir.rmdir()
            return True
        except (OSError, PermissionError):
            pass
    return False


def cleanup_tmp_files():
    """C2: Cleanup orphaned .tmp / .lock files at boot.

    CHUNK B4 (2026-05-08): also clean up stale .lock files. Locks held
    by live processes are short-lived (<5s in _tree_lock); a .lock
    older than 1h is unambiguously stale. Searches both .muninn/ and
    TREE_DIR (which may live outside .muninn/, e.g. memory/ in legacy).

    Returns number of files removed.
    """
    if not _m._REPO_PATH:
        return 0

    removed = 0
    cutoff = time.time() - 3600  # 1 hour
    search_dirs = []
    muninn_dir = _m._REPO_PATH / ".muninn"
    if muninn_dir.exists():
        search_dirs.append(muninn_dir)
    # TREE_DIR may be outside .muninn/ (legacy memory/ layout)
    tree_dir = getattr(_m, "TREE_DIR", None)
    if tree_dir is not None and tree_dir.exists() and tree_dir not in search_dirs:
        # Only add if not already covered by .muninn/ scan
        try:
            tree_dir.relative_to(muninn_dir)
        except (ValueError, AttributeError):
            search_dirs.append(tree_dir)

    patterns = ("*.tmp", "*.lock")
    seen = set()  # avoid double-count if dirs overlap via globs
    try:
        for base in search_dirs:
            for pat in patterns:
                for stale in base.rglob(pat):
                    if stale in seen:
                        continue
                    seen.add(stale)
                    try:
                        if stale.stat().st_mtime < cutoff:
                            stale.unlink()
                            removed += 1
                    except (OSError, PermissionError):
                        pass
    except Exception:
        pass
    return removed


def init_tree():
    # Safety net (added 2026-05-11 PM after test_e2e_pip_install leak): refuse
    # to init a tree under a path that does not belong to the currently bound
    # _REPO_PATH. Pip-install-e + cwd-mismatch could otherwise have init_tree
    # clobber the source repo when a downstream `muninn-mem init` runs in a tmp
    # repo. The check is generous (resolved-path prefix) to tolerate symlinks.
    repo_path = getattr(_m, "_REPO_PATH", None)
    if repo_path is not None:
        try:
            target = _m.TREE_DIR.resolve()
            expected_root = Path(repo_path).resolve()
            if not str(target).startswith(str(expected_root)):
                raise RuntimeError(
                    f"REFUSING init_tree: target {target} is outside "
                    f"the bound repo {expected_root}. This guard catches "
                    f"the test_e2e_pip_install_from_scratch class of leaks."
                )
        except (OSError, ValueError):
            pass  # missing path resolves are fine — init will create them

    _m.TREE_DIR.mkdir(parents=True, exist_ok=True)

    tree = {
        "version": 2,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "budget": BUDGET,
        "codebook_version": "v0.1",
        "nodes": {
            "root": {
                "type": "root",
                "file": "root.mn",
                "lines": 0,
                "max_lines": BUDGET["root_lines"],
                "children": [],
                "last_access": time.strftime("%Y-%m-%d"),
                "access_count": 0,
                "tags": [],
            }
        },
    }

    _atomic_json_write(_m.TREE_META, tree)

    _atomic_text_write(_m.TREE_DIR / "root.mn",
        "# MUNINN|codebook=v0.1\n"
    )

    print(f"  Tree initialized: {_m._safe_path(_m.TREE_DIR)}")
    return tree


def _tree_lock(path: Path, timeout: float = 5.0):
    """H12: Advisory file lock for tree.json (cross-platform).

    Uses msvcrt on Windows, fcntl on Unix. Non-blocking with retry.
    Returns (lock_file, acquired). Caller must close lock_file when done.
    """
    lock_path = path.with_suffix(".lock")
    try:
        lock_f = open(lock_path, "w", encoding="utf-8")
        lock_f.write("L")  # Write 1 byte — msvcrt.locking needs non-empty file
        lock_f.flush()
        if sys.platform == "win32":
            import msvcrt
            for _ in range(int(timeout * 20)):
                try:
                    msvcrt.locking(lock_f.fileno(), msvcrt.LK_NBLCK, 1)
                    return lock_f, True
                except (IOError, OSError):
                    time.sleep(0.05)
        else:
            import fcntl
            for _ in range(int(timeout * 20)):
                try:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return lock_f, True
                except (IOError, OSError):
                    time.sleep(0.05)
        # Timeout — close handle to prevent leak, proceed without lock
        lock_f.close()
        return None, False
    except Exception:
        try:
            lock_f.close()
        except Exception:
            pass
        return None, False


def _tree_unlock(lock_f):
    """H12: Release tree file lock."""
    if lock_f is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(lock_f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            import fcntl
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        lock_f.close()
    except Exception:
        pass


def load_tree():
    if not _m.TREE_META.exists():
        return init_tree()
    lock_f, acquired = _tree_lock(_m.TREE_META)
    if not acquired:
        print("WARNING: tree lock timeout on load_tree, proceeding anyway", file=sys.stderr)
    try:
        with open(_m.TREE_META, encoding="utf-8") as f:
            tree = json.load(f)
        # CHUNK C2 (2026-05-08): schema validation. JSON may be syntactically
        # valid but missing required keys (`version`, `nodes`) or be a
        # list/str/int payload entirely. Treat that the same as JSONDecodeError
        # (backup + init_tree) instead of crashing later in the pipeline.
        if not isinstance(tree, dict):
            raise ValueError(f"tree.json root is not a dict (got {type(tree).__name__})")
        missing = [k for k in ("version", "nodes") if k not in tree]
        if missing:
            raise ValueError(f"tree.json missing required keys: {missing}")
        if not isinstance(tree.get("nodes"), dict):
            raise ValueError("tree.json `nodes` is not a dict")
        # Validate all node file paths to prevent path traversal
        tree_dir_resolved = os.path.normcase(str(_m.TREE_DIR.resolve()))
        for name, node in tree.get("nodes", {}).items():
            if "file" in node:
                resolved = os.path.normcase(str((_m.TREE_DIR / node["file"]).resolve()))
                if not resolved.startswith(tree_dir_resolved + os.sep) and resolved != tree_dir_resolved:
                    print(f"WARNING: path traversal in tree node '{name}': {node['file']}, sanitized", file=sys.stderr)
                    node["file"] = f"{name}.mn"
        return tree
    except (json.JSONDecodeError, ValueError) as e:
        # SAFETY: backup corrupted file before re-initializing.
        import shutil
        backup = _m.TREE_META.with_suffix(f".corrupted.{int(time.time())}.json")
        try:
            shutil.copy2(str(_m.TREE_META), str(backup))
            print(f"WARNING: tree.json corrupted ({e}), backed up to {backup.name}", file=sys.stderr)
        except Exception:
            print(f"WARNING: tree.json corrupted ({e}), backup failed", file=sys.stderr)
        return init_tree()
    finally:
        _tree_unlock(lock_f)


def save_tree(tree):
    """Save tree metadata (atomic write via tempfile + rename). H12: file locked.

    CHUNK B1 (2026-05-08): hard-fail on lock timeout instead of proceeding.
    Two concurrent save_tree calls that both pass a soft warning and both
    write a tempfile race on os.replace -> second wins, first writer's
    changes silently lost. Raise TimeoutError so the caller can retry.
    """
    import tempfile, os
    tree["updated"] = time.strftime("%Y-%m-%d")
    _m.TREE_DIR.mkdir(parents=True, exist_ok=True)
    lock_f, acquired = _tree_lock(_m.TREE_META)
    if not acquired:
        # Cleanup the lock file handle if one was opened
        try:
            if lock_f is not None:
                lock_f.close()
        except Exception:
            pass
        raise TimeoutError(
            f"save_tree could not acquire {_m.TREE_META}.lock within timeout. "
            "Another writer holds it; retry or wait."
        )
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(_m.TREE_DIR), suffix=".tmp", prefix="tree_"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False, indent=2)
            # Windows: os.replace can fail if target is open by another thread
            for _attempt in range(3):
                try:
                    os.replace(tmp_path, str(_m.TREE_META))
                    break
                except PermissionError:
                    time.sleep(0.05)
            else:
                os.replace(tmp_path, str(_m.TREE_META))
            from _secrets import secure_perms
            secure_perms(_m.TREE_META)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    finally:
        _tree_unlock(lock_f)


def _atomic_json_write(path: Path, data, indent: int = 2):
    """Atomic JSON write via tempfile + os.replace. Prevents corruption on concurrent read."""
    import tempfile, os
    from _secrets import secure_perms
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        for _attempt in range(3):
            try:
                os.replace(tmp_path, str(path))
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    secure_perms(path)


def _atomic_text_write(path: Path, text: str):
    """Atomic text write via tempfile + os.replace. For .mn branch/root files."""
    import tempfile
    from _secrets import secure_perms
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(text)
        for _attempt in range(3):
            try:
                os.replace(tmp_path, str(path))
                secure_perms(path)
                return
            except PermissionError:
                time.sleep(0.05)
        os.replace(tmp_path, str(path))  # Final try
        secure_perms(path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _safe_tree_path(filename: str) -> Path:
    """Resolve a tree node filename into a safe path within _m.TREE_DIR.
    Prevents path traversal via crafted node['file'] values."""
    filepath = (_m.TREE_DIR / filename).resolve()
    tree_dir_resolved = _m.TREE_DIR.resolve()
    if not str(filepath).startswith(str(tree_dir_resolved) + os.sep) and filepath != tree_dir_resolved:
        raise ValueError(f"Path traversal blocked: {filename}")
    return filepath


def compute_hash(filepath: Path) -> str:
    """SHA-256 hash of file content (first 8 hex chars)."""
    if not filepath.exists():
        return "0" * 8
    content = filepath.read_bytes()
    return hashlib.sha256(content).hexdigest()[:8]


def _ebbinghaus_recall(node: dict, _h_beta: float = 0.5,
                       _alpha_v: float = 0.3, _alpha_a: float = 0.2,
                       _lambda_ewc: float = 0.5) -> float:
    """Spaced repetition recall probability (Settles & Meeder 2016).

    p = 2^(-delta / h)

    where delta = days since last access, h = half-life.
    Half-life doubles with each review (load at boot), starting at 7 days.
    A branch loaded 5 times has h = 7 * 2^5 = 224 days — very stable.

    A1 upgrade: h is now modulated by usefulness (proxy for importance).
    h = 7 * 2^reviews * usefulness^beta
    When usefulness=1.0 (default), behavior is identical to pre-A1.
    Sources: GARCH (Bollerslev 1986), PLOS Bio 2018 (antibody half-lives), BS-6.

    V6B upgrade: h is further modulated by valence and arousal (Talmi 2013).
    h(v,a) = h_base * (1 + alpha_v * |v| + alpha_a * a)
    Emotional memories (high |valence| or arousal) decay SLOWER.
    When valence=0 and arousal=0 (default), behavior is identical to pre-V6B.
    Sources: Talmi 2013 (Curr Dir Psychol Sci), McGaugh 2004 (Trends Neurosci).

    V4B upgrade: EWC Fisher importance (Kirkpatrick et al. 2017, PNAS).
    h *= (1 + lambda_ewc * F_i) where F_i = fisher_importance (0-1).
    High-F branches (critical for past recalls) decay SLOWER.
    When fisher_importance is absent (default 0), behavior is identical to pre-V4B.
    """
    delta = _days_since(node.get("last_access", time.strftime("%Y-%m-%d")))
    reviews = node.get("access_count", 0)
    usefulness = max(0.1, node.get("usefulness", 1.0))  # clamp [0.1, 1.0] — A1.7 safety
    half_life = 7.0 * (2 ** min(reviews, 10)) * (usefulness ** _h_beta)

    # V6B: Valence-modulated decay (Talmi 2013)
    valence = node.get("valence", 0.0)
    arousal = max(0.0, node.get("arousal", 0.0))  # clamp: arousal is always >= 0
    half_life *= (1.0 + _alpha_v * abs(valence) + _alpha_a * arousal)

    # V4B: EWC Fisher importance (Kirkpatrick 2017)
    fisher = max(0.0, min(1.0, node.get("fisher_importance", 0.0)))
    half_life *= (1.0 + _lambda_ewc * fisher)

    # I1: Danger Theory DCA (Greensmith 2008)
    # Chaotic sessions (errors, retries, topic switches) produce more durable branches.
    # h *= (1 + gamma * danger_score). When danger_score=0 (default), no effect.
    danger = max(0.0, min(1.0, node.get("danger_score", 0.0)))
    half_life *= (1.0 + danger)  # gamma=1.0 implicit

    if half_life <= 0:
        return 0.0
    return 2.0 ** (-delta / half_life)


def _actr_activation(node: dict, _d: float = 0.5) -> float:
    """ACT-R base-level activation (Anderson 1993).

    B = ln(sum(t_j^(-d)))

    where t_j = days since j-th access, d = decay parameter (0.5 default).
    Uses access_history if available, falls back to synthetic timestamps
    from last_access + access_count.

    A2 upgrade: captures non-Markov memory — WHEN matters, not just HOW MANY.
    Sources: ACT-R (Anderson 1993), Cell Systems 2017 (non-Markov), BS-3.

    Returns activation on [~-5, ~3] scale. Used as bonus in boot() scoring,
    NOT as replacement for _ebbinghaus_recall (which stays for prune/temperature).
    """
    import math
    history = node.get("access_history", [])

    if not history:
        # Fallback: synthesize timestamps from last_access + access_count
        last = node.get("last_access", time.strftime("%Y-%m-%d"))
        count = max(1, node.get("access_count", 1))
        days_ago = max(1, _days_since(last))
        # Spread count accesses uniformly from days_ago to 1 day ago
        if count == 1:
            history = [last]
        else:
            from datetime import datetime, timedelta
            try:
                base = datetime.strptime(last, "%Y-%m-%d")
            except ValueError:
                base = datetime.now()
            step = max(1, days_ago // count)
            history = [(base - timedelta(days=step * i)).strftime("%Y-%m-%d")
                       for i in range(min(count, 10))]

    if not history:
        return 0.0

    total = 0.0
    for ts in history:
        t_j = max(1, _days_since(ts))  # at least 1 day to avoid 0^(-d)
        total += t_j ** (-_d)

    if total <= 0:
        return 0.0
    return math.log(total)


def _days_since(date_str: str) -> int:
    """Days since a YYYY-MM-DD date string. Returns 90 on parse error."""
    try:
        from datetime import timezone
        return max(0, (datetime.now(timezone.utc) - datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)).days)
    except ValueError:
        return 90


def compute_temperature(node: dict) -> float:
    """Temperature score: how "hot" is this node (0.0=frozen, 1.0+=burning).

    Based on:
    - Ebbinghaus recall probability (spaced repetition, Settles 2016)
    - fill ratio (fuller = hotter, needs attention)

    The recall probability naturally encodes both recency and access count
    through the half-life model: h = 7 * 2^reviews.
    """
    fill = min(1.0, node.get("lines", 0) / max(node.get("max_lines", 1), 1))
    recall = _ebbinghaus_recall(node)

    # Fill pressure: nodes near budget get hotter (need split/compress)
    fill_heat = fill ** 2  # quadratic: only significant near full

    # 80% recall-driven, 20% fill pressure
    temp = 0.8 * recall + 0.2 * fill_heat
    return round(temp, 2)


def refresh_tree_metadata(tree: dict):
    """Recompute hash + line count + temperature for all nodes."""
    for name, node in tree["nodes"].items():
        filepath = _m.TREE_DIR / node["file"]
        node["hash"] = compute_hash(filepath)
        if filepath.is_file():
            try:
                actual_lines = len(filepath.read_text(encoding="utf-8").split("\n"))
                node["lines"] = actual_lines
            except (OSError, UnicodeDecodeError):
                pass
        node["temperature"] = compute_temperature(node)


def read_node(name: str, _tree: dict | None = None) -> str:
    """Read a branch .mn file. P34: verify hash integrity before loading.

    If _tree is provided, uses it (avoids repeated load/save in boot loops).
    access_count and last_access are updated in-place; caller should save_tree() once.
    """
    tree = _tree or load_tree()
    node = tree["nodes"].get(name)
    if not node:
        return f"ERROR: node '{name}' not found"

    filepath = _m.TREE_DIR / node["file"]
    if not filepath.exists():
        return f"ERROR: file '{filepath}' not found"

    # P34: integrity check — skip corrupted branches
    stored_hash = node.get("hash", "")
    if stored_hash and stored_hash != "00000000":
        actual_hash = compute_hash(filepath)
        if actual_hash != stored_hash:
            print(f"WARNING: {name} hash mismatch (stored={stored_hash}, actual={actual_hash}), skipping", file=sys.stderr)
            return ""  # Empty = will be skipped by boot (no content)

    try:
        text = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError) as e:
        print(f"WARNING: cannot read {name}: {e}", file=sys.stderr)
        return ""

    # B1: Reconsolidation — re-compress cold branches at read time
    # Nader 2000: recalled memory is unstable, must be re-stored.
    # Only triggers if: recall < 0.3 AND last_access > 7 days ago AND text > 3 lines
    # Uses L10 (cue distillation) + L11 (rule extraction) — zero API calls.
    # MUST check BEFORE updating access (otherwise recall jumps to ~1.0)
    recall = _ebbinghaus_recall(node)
    access_hist = node.get("access_history", [])
    if access_hist:
        last_date = access_hist[-1]
    else:
        last_date = node.get("last_access", time.strftime("%Y-%m-%d"))
    days_ago = _days_since(last_date)

    node["access_count"] = node.get("access_count", 0) + 1
    node["last_access"] = time.strftime("%Y-%m-%d")
    # A2: append to access_history (cap at 10 most recent)
    history = node.get("access_history", [])
    history.append(time.strftime("%Y-%m-%d"))
    node["access_history"] = history[-10:]  # keep last 10
    if recall < 0.3 and days_ago > 7 and text.count("\n") > 3 and name != "root":
        try:
            original_len = len(text)
            reconsolidated = _m._resolve_contradictions(text)  # C7: resolve stale numbers
            reconsolidated = _m._cue_distill(reconsolidated)
            reconsolidated = _m._extract_rules(reconsolidated)
            # B1.1: only save if it got smaller (never inflate)
            if len(reconsolidated) < original_len:
                _atomic_text_write(filepath, reconsolidated)
                node["hash"] = compute_hash(filepath)
                node["lines"] = reconsolidated.count("\n") + 1
                text = reconsolidated
        except Exception:
            pass  # fail silently — reconsolidation is best-effort

    if _tree is None:
        save_tree(tree)

    return text


# ── TF-IDF RETRIEVAL ─────────────────────────────────────────────

def _tokenize_words(text: str) -> list:
    """Split text into lowercase word tokens for TF-IDF."""
    return re.findall(r'[a-z0-9_]+', text.lower())


def _tfidf_relevance(query: str, documents: dict) -> dict:
    """Compute TF-IDF cosine similarity between query and documents.

    Args:
        query: search string
        documents: {name: text_content} dict

    Returns:
        {name: relevance_score} dict, scores in [0, 1]
    """
    import math

    if not documents or not query.strip():
        return {}

    query_tokens = _tokenize_words(query)
    if not query_tokens:
        return {}

    # Tokenize all documents
    doc_tokens = {name: _tokenize_words(text) for name, text in documents.items()}

    # Build vocabulary from query terms only (faster, focused)
    vocab = set(query_tokens)

    # Document frequency: how many docs contain each term
    n_docs = len(doc_tokens)
    df = Counter()
    for tokens in doc_tokens.values():
        seen = set(tokens) & vocab
        for term in seen:
            df[term] += 1

    # IDF: log(N / df), with smoothing
    idf = {term: math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1
           for term in vocab}

    # TF-IDF vector for query
    q_tf = Counter(query_tokens)
    q_vec = {term: q_tf[term] * idf.get(term, 0) for term in vocab}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    # TF-IDF + cosine similarity for each document
    scores = {}
    for name, tokens in doc_tokens.items():
        if not tokens:
            scores[name] = 0.0
            continue
        d_tf = Counter(tokens)
        d_vec = {term: d_tf.get(term, 0) * idf.get(term, 0) for term in vocab}
        d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
        dot = sum(q_vec[t] * d_vec[t] for t in vocab)
        scores[name] = dot / (q_norm * d_norm)

    return scores


# ── TREE BUILD ────────────────────────────────────────────────────

def build_tree(filepath):
    """R3: compress BEFORE split. R2: split if over budget.

    BUG-108 fix (brick 18): wrap input with Path() so callers can pass str.
    Also raise ValueError instead of crashing on empty / nonexistent input.
    """
    if not filepath:
        raise ValueError("build_tree requires a non-empty filepath")
    if not isinstance(filepath, Path):
        filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"build_tree: {filepath} does not exist")

    tree = load_tree()

    compressed = _m.compress_file(filepath)
    comp_lines = compressed.split("\n")

    print(f"\n  Source: {filepath.name}")
    print(f"  Original: {filepath.stat().st_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Lines: {len(comp_lines)}")

    if len(comp_lines) <= BUDGET["root_lines"]:
        root_path = _m.TREE_DIR / "root.mn"
        _atomic_text_write(root_path, compressed)
        tree["nodes"]["root"]["lines"] = len(comp_lines)
        tree["nodes"]["root"]["last_access"] = time.strftime("%Y-%m-%d")
        save_tree(tree)
        print(f"  Fits in root ({len(comp_lines)}/{BUDGET['root_lines']} lines)")
    else:
        print(f"  Exceeds root budget, splitting...")
        header = comp_lines[0]
        sections = []
        current = []
        for line in comp_lines[1:]:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                if current:
                    sections.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append("\n".join(current))

        root_lines = [header]
        branch_id = 0

        for section in sections:
            sec_lines = section.split("\n")
            first_line = sec_lines[0][:60]
            tags = extract_tags(section)

            if len(root_lines) + len(sec_lines) <= BUDGET["root_lines"]:
                root_lines.extend(sec_lines)
            else:
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                _atomic_text_write(_m.TREE_DIR / branch_file, section)
                root_lines.append(f"\u2192{branch_name}:{first_line}")

                tree["nodes"][branch_name] = {
                    "type": "branch",
                    "file": branch_file,
                    "lines": len(sec_lines),
                    "max_lines": BUDGET["branch_lines"],
                    "children": [],
                    "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0,
                    "tags": tags,
                }
                tree["nodes"]["root"]["children"].append(branch_name)
                branch_id += 1
                print(f"    Branch {branch_name}: {len(sec_lines)} lines [{','.join(tags[:3])}]")

        # Enforce R1
        if len(root_lines) > BUDGET["root_lines"]:
            print(f"  WARNING: root {len(root_lines)} > {BUDGET['root_lines']}, force-splitting")
            overflow_refs = []
            max_overflow = BUDGET["root_lines"] // 4  # Cap refs to 25% of root, keep 75% content
            while len(root_lines) > BUDGET["root_lines"] - len(overflow_refs) and len(overflow_refs) < max_overflow:
                overflow = root_lines.pop()
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                _atomic_text_write(_m.TREE_DIR / branch_file, overflow)
                overflow_refs.append(f"\u2192{branch_name}:{overflow[:50]}")
                tree["nodes"][branch_name] = {
                    "type": "branch", "file": branch_file,
                    "lines": 1, "max_lines": BUDGET["branch_lines"],
                    "children": [], "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0, "tags": [],
                }
                branch_id += 1
            root_lines.extend(overflow_refs)

        root_path = _m.TREE_DIR / "root.mn"
        _atomic_text_write(root_path, "\n".join(root_lines))
        tree["nodes"]["root"]["lines"] = len(root_lines)
        tree["nodes"]["root"]["children"] = [n for n in tree["nodes"] if n != "root"]
        save_tree(tree)
        print(f"\n  Root: {len(root_lines)} lines, {branch_id} branches")


# ── AUTO-SEGMENTATION (Brique 3) ─────────────────────────────────

def _safe_read_mn(path: Path) -> str | None:
    """Read a .mn / branch file safely. Returns None if corrupted/unreadable.

    CHUNK A2 (2026-05-08): a process killed mid-write to a .mn leaves the
    file with truncated UTF-8 sequences. `read_text(encoding="utf-8")`
    raises UnicodeDecodeError which previously killed the entire ingestion
    pipeline (grow_branches_from_session, prune cold-branch).

    Callers must handle None (skip / fallback / continue). See
    docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A2.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        print(f"WARNING: corrupted .mn {_m._safe_path(path)}: {e}", file=sys.stderr)
        return None
    except OSError as e:
        print(f"WARNING: unreadable .mn {_m._safe_path(path)}: {e}", file=sys.stderr)
        return None


def grow_branches_from_session(mn_path: Path, session_sentiment: dict = None):
    """Auto-segment a compressed .mn file into tree branches.

    Splits the session by ## headers (already created by compress_transcript).
    Each section becomes a branch with auto-extracted tags.
    Merges into existing branch if >50% tag overlap (avoids duplication).
    V6B: Propagates session valence/arousal to branch nodes for decay modulation.
    """
    if not mn_path.exists():
        return 0

    content = _safe_read_mn(mn_path)
    if content is None or not content.strip():
        return 0

    # Split by ## headers (compress_transcript already creates these)
    sections = re.split(r'^(## .+)$', content, flags=re.MULTILINE)

    # Pair headers with their content
    segments = []
    i = 0
    # Skip any content before first header
    if sections and not sections[0].startswith("## "):
        i = 1
    while i < len(sections):
        header = sections[i].strip() if i < len(sections) else ""
        body = sections[i + 1].strip() if i + 1 < len(sections) else ""
        if header.startswith("## ") and body and body.count("\n") >= 4:
            segments.append((header, body))
        i += 2

    # Fallback: no headers found, chunk by lines
    if not segments:
        lines = [l for l in content.split("\n") if l.strip()]
        if len(lines) < 3:
            return 0
        chunk_size = max(5, len(lines) // 4)  # ~4 chunks
        for j in range(0, len(lines), chunk_size):
            chunk = lines[j:j + chunk_size]
            header = f"## {chunk[0][:60].strip()}"
            body = "\n".join(chunk)
            if body.count("\n") >= 4:  # B11 fix: min 5 lines to avoid dust branches
                segments.append((header, body))
            elif segments:
                # B17: small tail chunk -> merge into previous segment instead of dropping
                prev_header, prev_body = segments[-1]
                segments[-1] = (prev_header, prev_body + "\n" + body)

    if not segments:
        return 0

    tree = load_tree()
    nodes = tree["nodes"]
    created = 0

    # Find next branch ID
    existing_ids = [int(n[1:]) for n in nodes if n.startswith("b") and n[1:].isdigit()]
    next_id = max(existing_ids, default=-1) + 1

    for header, body in segments:
        tags = extract_tags(body)
        tag_set = set(tags)

        # Check for overlap with existing branches (merge if NCD < 0.4 or tag overlap > 50%)
        merged = False
        for name, node in nodes.items():
            if name == "root":
                continue
            # Try NCD first (content-based), fallback to tag overlap
            existing_file = _m.TREE_DIR / node["file"]
            should_merge = False
            if existing_file.exists():
                # A2: skip NCD if .mn truncated → falls back to tag overlap
                existing_text = _safe_read_mn(existing_file)
                if existing_text and body:
                    ncd = _m._ncd(body, existing_text)
                    should_merge = ncd < 0.4
            if not should_merge:
                existing_tags = set(node.get("tags", []))
                if existing_tags and tag_set:
                    overlap = len(tag_set & existing_tags) / max(len(tag_set | existing_tags), 1)
                    should_merge = overlap > 0.5
            if should_merge:
                # Context-Aware Merge: append + resolve contradictions + dedup
                filepath = _m.TREE_DIR / node["file"]
                if not filepath.exists():
                    print(f"  WARNING: branch file missing: {_m._safe_path(filepath)}, creating new branch", file=sys.stderr)
                    continue  # M5 fix: fall through to create new branch instead of losing data
                # A2: skip merge if existing .mn truncated → fall through to create new branch
                old = _safe_read_mn(filepath)
                if old is None:
                    print(f"  WARNING: branch file corrupted: {_m._safe_path(filepath)}, creating new branch", file=sys.stderr)
                    continue
                # Combine old + new content
                merged_text = old + "\n" + header + "\n" + body
                # Resolve contradictions (last-writer-wins)
                merged_text = _m._resolve_contradictions(merged_text)
                # Dedup lines (exact + normalized)
                seen = set()
                deduped = []
                for dline in merged_text.split("\n"):
                    norm = re.sub(r'[^\w\s]', '', dline.lower()).strip()
                    norm = re.sub(r'\s+', ' ', norm)
                    if not norm:
                        continue
                    if norm in seen:
                        continue
                    seen.add(norm)
                    deduped.append(dline)
                merged_text = "\n".join(deduped)
                new_lines = merged_text.split("\n")
                max_l = node.get("max_lines", 150)
                if len(new_lines) <= max_l:
                    _atomic_text_write(filepath, merged_text)
                    node["lines"] = len(new_lines)
                    node["tags"] = sorted(set(node.get("tags", [])) | tag_set)[:10]
                    # V6B: Update sentiment (weighted average old + new)
                    if session_sentiment is not None:
                        old_v = node.get("valence", 0.0)
                        old_a = node.get("arousal", 0.0)
                        new_v = session_sentiment.get("mean_valence", 0.0)
                        new_a = session_sentiment.get("mean_arousal", 0.0)
                        # EMA: 70% old + 30% new (recent sessions influence more gradually)
                        node["valence"] = round(0.7 * old_v + 0.3 * new_v, 4)
                        node["arousal"] = round(0.7 * old_a + 0.3 * new_a, 4)
                    merged = True
                    break

        if not merged:
            # Create new branch
            branch_name = f"b{next_id:02d}"
            branch_file = f"{branch_name}.mn"
            branch_path = _m.TREE_DIR / branch_file
            lines = body.split("\n")
            _atomic_text_write(branch_path, body)

            new_node = {
                "type": "branch",
                "file": branch_file,
                "lines": len(lines),
                "max_lines": 150,
                "children": [],
                "last_access": time.strftime("%Y-%m-%d"),
                "access_count": 0,
                "tags": tags[:10],
                "hash": "00000000",
                "temperature": 0.1,
            }
            # V6B: Propagate session sentiment to branch for valence-modulated decay
            if session_sentiment is not None:
                new_node["valence"] = session_sentiment.get("mean_valence", 0.0)
                new_node["arousal"] = session_sentiment.get("mean_arousal", 0.0)
                # I1: Propagate danger score for Danger Theory DCA
                if session_sentiment.get("danger_score", 0) > 0:
                    new_node["danger_score"] = session_sentiment["danger_score"]
            nodes[branch_name] = new_node
            # Add to root's children
            if branch_name not in nodes.get("root", {}).get("children", []):
                nodes.setdefault("root", {}).setdefault("children", []).append(branch_name)

            next_id += 1
            created += 1

    # B13: Cap branches at MAX_BRANCHES to prevent tree explosion
    MAX_BRANCHES = 200
    branch_nodes = [(n, nd) for n, nd in nodes.items() if n != "root"]
    if len(branch_nodes) > MAX_BRANCHES:
        # Sort by temperature (coldest first), then by access_count
        branch_nodes.sort(key=lambda x: (x[1].get("temperature", 0), x[1].get("access_count", 0)))
        to_remove = branch_nodes[:len(branch_nodes) - MAX_BRANCHES]
        for name, node in to_remove:
            # Delete branch file
            branch_file = _m.TREE_DIR / node["file"]
            if branch_file.exists():
                branch_file.unlink()
            # Remove from tree
            del nodes[name]
            # Remove from root's children
            root_children = nodes.get("root", {}).get("children", [])
            if name in root_children:
                root_children.remove(name)
        print(f"  B13 branch cap: removed {len(to_remove)} coldest branches (>{MAX_BRANCHES})", file=sys.stderr)

    refresh_tree_metadata(tree)
    save_tree(tree)

    if created > 0:
        print(f"  Auto-segmentation: {len(segments)} sections -> {created} new branches", file=sys.stderr)

    return created


# ── BOOT INTELLIGENCE (R7) ──────────────────────────────────────

def extract_tags(text: str) -> list[str]:
    """Extract semantic tags from text — repo-agnostic.
    Uses word frequency + mycelium concept matching.
    Filters stopwords (EN+FR) and short noise words for branch discrimination."""
    # Expanded stoplist: common EN + FR words that pollute tags
    _STOP = {
        # English
        "this", "that", "with", "from", "have", "been", "will", "what",
        "when", "where", "which", "there", "their", "about", "would",
        "could", "should", "some", "other", "than", "then", "them",
        "these", "those", "also", "just", "like", "into", "over",
        "only", "very", "each", "more", "most", "such", "much",
        "make", "made", "does", "done", "here", "come", "came",
        "take", "took", "good", "well", "back", "know", "want",
        "give", "need", "still", "even", "after", "before", "between",
        "under", "through", "same", "first", "last", "long", "great",
        "little", "right", "while", "think", "every", "being", "going",
        # French
        "pour", "dans", "avec", "sont", "plus", "tout", "mais",
        "elle", "elles", "nous", "vous", "leur", "cette", "faire",
        "fait", "dire", "peut", "comme", "bien", "aussi", "encore",
        "donc", "alors", "quand", "rien", "autre", "meme", "sans",
        "etre", "avoir", "tres", "trop", "deja", "avant", "apres",
        "parce", "entre", "depuis", "vers", "chez", "voila",
        "faut", "sur", "pas", "non", "oui", "bon", "ton", "par",
        "fais", "devrait", "laisse", "maintenant", "continu",
        "commence", "finit", "ensuite", "regarde",
        # Noise from compressed text
        "aie", "ais", "alle", "aile", "aire", "ante", "amener",
        "attend", "avait", "bord", "dure", "ease",
        # Generic tool/context noise (present in most branches)
        "users", "ludov", "user", "bash", "grep", "exit", "true",
        "false", "none", "text", "file", "path", "import", "json",
        "get", "let", "uses", "tool",
    }
    tags = set()
    text_lower = text.lower()

    # 1. Extract technical keywords: word-boundary match, min 4 chars
    # Keywords first — they're the most discriminating for branch selection
    tech_words = re.findall(r'\b[a-z_][a-z_0-9]{3,}\b', text_lower)
    _kw_thresh = 3 if len(text) > 500 else 2
    for word, count in Counter(tech_words).most_common(20):
        if count >= _kw_thresh and word not in _STOP and len(tags) < 10:
            tags.add(word)

    # 2. Add capitalized entities not yet captured (proper nouns, acronyms)
    entities = re.findall(r'\b[A-Z][A-Za-z]{2,}\b', text)
    _ent_thresh = 2 if len(text) > 500 else 1
    for entity, count in Counter(entities).most_common(8):
        e_low = entity.lower()
        if count >= _ent_thresh and e_low not in _STOP and e_low not in tags and len(tags) < 10:
            tags.add(e_low)

    # 3. Extract technical identifiers (snake_case)
    identifiers = re.findall(r'\b[a-z_]+(?:_[a-z]+)+\b', text_lower)
    for ident, count in Counter(identifiers).most_common(5):
        if count >= 2 and ident not in _STOP and ident not in tags and len(tags) < 10:
            tags.add(ident)

    # CHUNK 5: Enrich tags with mycelium concepts if available.
    # get_related() finds semantically linked concepts that pure regex misses.
    if tags and _m._REPO_PATH:
        try:
            if _m._CORE_DIR not in sys.path:
                sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(_m._REPO_PATH)
            for seed in list(tags)[:3]:  # top 3 tags as seeds
                related = m.get_related(seed, top_n=3)
                for concept, _w in related:
                    if concept not in _STOP and len(concept) >= 4 and len(tags) < 10:
                        tags.add(concept)
            m.close()
        except Exception:
            pass  # Graceful: tags work without mycelium

    return sorted(tags)[:10]


def spill_chunks_to_tree(repo_path: Path, dropped_chunks: list[str],
                         source_id: str = "") -> list[str]:
    """BUG-104 fix (2026-05-10) — spill chunks must-keep dropped par L12.

    Quand le packer L12 BudgetMem doit dropper des chunks must-keep faute de
    place dans le budget, au lieu de les perdre on les écrit dans des branches
    dédiées du tree. Boot() les retrouvera via TF-IDF + spreading activation
    sur les concepts (extract_tags).

    Pattern : calque V9A+ regen (Shomrat & Levin 2013 planère) appliqué à L12
    au lieu de prune. L'info ne disparaît pas, elle migre dans la couche
    persistante au lieu d'être détruite.

    Args:
        repo_path: racine du repo (pour résoudre TREE_DIR via _refresh_tree_paths
            si besoin). Si None ou non-existant, no-op (returns []).
        dropped_chunks: liste des textes des chunks must-keep qui n'ont pas tenu
            dans le budget L12. Vide → no-op.
        source_id: identifiant optionnel de la session/transcript source
            (utilisé dans le nom de la branche pour traçabilité).

    Returns:
        list[str] des branch names créées (ex: ["b07", "b08"]). Vide si
        no-op (pas de chunks ou repo_path manquant).

    Side effects:
        - Crée 1 fichier .mn par chunk dans .muninn/tree/
        - Update tree.json (sous lock _tree_lock interne à save_tree)
    """
    if not dropped_chunks or not repo_path:
        return []
    repo_path = Path(repo_path)
    if not repo_path.exists():
        return []
    # Filtre chunks vides ou trop courts (< 3 lignes = dust, B14)
    valid_chunks = [c for c in dropped_chunks
                    if isinstance(c, str) and c.strip() and c.count("\n") >= 2]
    if not valid_chunks:
        return []

    try:
        tree = load_tree()
    except Exception as e:
        # Pas de tree → on ne peut pas spiller, fallback silencieux (les facts
        # restent dans le transcript .jsonl original, donc pas perdus).
        print(f"  [BUG-104 spill] tree load failed: {e}", file=sys.stderr)
        return []

    nodes = tree.get("nodes", {})
    # Trouve next_id en scannant les b00/b01/... existants
    existing_ids = []
    for n in nodes:
        if n.startswith("b") and n[1:].isdigit():
            existing_ids.append(int(n[1:]))
    next_id = (max(existing_ids) + 1) if existing_ids else 0

    branch_names = []
    today = time.strftime("%Y-%m-%d")
    tree_dir = _m.TREE_DIR or (repo_path / ".muninn" / "tree")
    if not tree_dir.exists():
        try:
            tree_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return []

    for idx, chunk in enumerate(valid_chunks):
        branch_name = f"b{next_id + idx:02d}"
        branch_file = f"{branch_name}.mn"
        branch_path = tree_dir / branch_file
        # Header L12 SPILL pour traçabilité
        spill_marker = f"## L12_SPILL"
        if source_id:
            spill_marker += f" {source_id}"
        spill_marker += f" ({today})"
        body = f"{spill_marker}\n{chunk.rstrip()}\n"
        try:
            _atomic_text_write(branch_path, body)
        except OSError as e:
            print(f"  [BUG-104 spill] write failed for {branch_name}: {e}",
                  file=sys.stderr)
            continue

        try:
            chunk_tags = extract_tags(chunk)[:10]
        except Exception:
            chunk_tags = []

        nodes[branch_name] = {
            "type": "branch",
            "file": branch_file,
            "lines": body.count("\n") + 1,
            "max_lines": 150,
            "tags": chunk_tags,
            "temperature": 0.1,  # warm enough not to be immediately pruned
            "access_count": 0,
            "last_access": today,
            "created": today,
            "usefulness": 0.5,
            "td_value": 0.5,
            "fisher_importance": 0.0,
            "spilled_from_l12": True,  # BUG-104 marker
        }
        # Add as child of root for proper tree linking
        if "children" in nodes.get("root", {}):
            if branch_name not in nodes["root"]["children"]:
                nodes["root"]["children"].append(branch_name)
        try:
            nodes[branch_name]["hash"] = compute_hash(branch_path)
        except OSError:
            pass

        branch_names.append(branch_name)

    if branch_names:
        try:
            refresh_tree_metadata(tree)
            save_tree(tree)
        except Exception as e:
            print(f"  [BUG-104 spill] save_tree failed: {e}", file=sys.stderr)
            # Files were written, tree.json may be partially updated.
            # Subsequent boot() will still find the .mn files via tree
            # resync on next refresh_tree_metadata call.

    return branch_names


def recall(query: str) -> str:
    """P29: Mid-session memory search. Searches session index + .mn files + tree branches.

    Returns the most relevant lines from past sessions matching the query.
    Designed to be called via `muninn.py recall "search terms"` mid-conversation.
    """
    repo = _m._REPO_PATH or Path(".")
    query_words = set(re.findall(r'[A-Za-z]{4,}', query.lower()))
    if not query_words:
        return "RECALL: empty query"

    results = []

    # 1. Search session index for relevant sessions
    index_path = repo / ".muninn" / "session_index.json"
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(index, list):
                for entry in index:
                    concepts = set(entry.get("concepts", []))
                    overlap = len(query_words & concepts)
                    if overlap > 0:
                        # Search tagged lines for matches
                        for tagged in entry.get("tagged", []):
                            tagged_words = set(re.findall(r'[A-Za-z]{4,}', tagged.lower()))
                            if query_words & tagged_words:
                                results.append((overlap + 1, entry.get("date", "?"), tagged))
                        # If no tagged match, still note the session
                        if not any(r[2].startswith(t[:20]) for r in results for t in entry.get("tagged", [])):
                            results.append((overlap, entry.get("date", "?"),
                                          f"[session {entry.get('file', '?')}] concepts: {', '.join(concepts & query_words)}"))
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Grep .mn files for matching lines
    sessions_dir = repo / ".muninn" / "sessions"
    if sessions_dir.exists():
        for mn_file in sorted(sessions_dir.glob("*.mn"), reverse=True)[:10]:
            try:
                text = mn_file.read_text(encoding="utf-8", errors="ignore")
                for line in text.split("\n"):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    line_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
                    overlap = len(query_words & line_words)
                    if overlap >= 2:
                        date = mn_file.stem[:8]  # YYYYMMDD from filename
                        results.append((overlap, date, stripped[:150]))
            except OSError:
                continue

    # 3. Search tree branches (P37: also warm up matched branches)
    matched_branches = set()
    if _m.TREE_DIR.exists():
        for mn_file in _m.TREE_DIR.glob("*.mn"):
            if mn_file.name == "root.mn":
                continue
            try:
                text = mn_file.read_text(encoding="utf-8", errors="ignore")
                for line in text.split("\n"):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    line_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
                    overlap = len(query_words & line_words)
                    if overlap >= 2:
                        results.append((overlap, mn_file.stem, stripped[:150]))
                        matched_branches.add(mn_file.stem)
            except OSError:
                continue

    # 4. Check error/fix memory
    error_hints = _surface_known_errors(repo, query)
    if error_hints:
        for hint in error_hints.split("\n"):
            results.append((5, "errors", hint))

    if not results:
        return f"RECALL: nothing found for '{query}'"

    # P37: Warm up matched tree branches (update access_count + last_access)
    if matched_branches:
        try:
            tree = load_tree()
            for bname in matched_branches:
                node = tree["nodes"].get(bname)
                if node:
                    node["access_count"] = node.get("access_count", 0) + 1
                    node["last_access"] = time.strftime("%Y-%m-%d")
                    # A2: update access_history
                    history = node.get("access_history", [])
                    history.append(time.strftime("%Y-%m-%d"))
                    node["access_history"] = history[-10:]
            save_tree(tree)
        except Exception:
            pass

    # Sort by relevance (overlap score), dedup, take top 10
    results.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    output = [f"RECALL: '{query}' — {len(results)} matches"]
    warmed = f" (warmed {len(matched_branches)} branches)" if matched_branches else ""
    output[0] += warmed
    for score, source, text in results:
        if text in seen:
            continue
        seen.add(text)
        output.append(f"  [{source}] {text}")
        if len(output) >= 12:  # max 10 results + header
            break

    # C4: Real-time k adaptation based on recall concepts
    adapt_k(list(query_words))

    return "\n".join(output)


# ── P41: Live Mycelium Bridge ────────────────────────────────────

def bridge(text: str, top_n: int = 10, hops: int = 2,
           include_branches: bool = True) -> str:
    """P41: Live mycelium bridge — query the mycelium mid-session.

    Extracts concepts from user text, spreads activation through the
    mycelium, and returns activated concepts + relevant branch snippets.
    This is the LIVE CONNECTION between the conversation and the mycelium.

    Unlike recall() which greps .mn files for keywords, bridge() uses
    the semantic network to find concepts the user DIDN'T mention but
    that are strongly connected to what they're talking about.

    Theory: HippoRAG (Gutierrez & Shu 2024) + Collins & Loftus 1975
    Pattern: FLARE/DRAGIN mid-conversation retrieval

    Args:
        text: user message or text to bridge from
        top_n: max activated concepts to return
        hops: spreading activation depth (2 = neighbors of neighbors)
        include_branches: also search tree branches for activated concepts

    Returns:
        Formatted string with activated concepts and branch matches.
    """
    repo = _m._REPO_PATH or Path(".")

    # Extract concepts from text (same logic as observe)
    words = re.findall(r'[A-Za-z\u00c0-\u024f]{4,}', text.lower())
    # Filter stopwords (EN + FR)
    stop = {"that", "this", "with", "from", "have", "been", "were", "will",
            "would", "could", "should", "their", "there", "about", "which",
            "when", "what", "your", "they", "them", "than", "then", "also",
            "just", "only", "some", "more", "very", "most", "each", "into",
            "over", "after", "before", "between", "under", "through", "does",
            "here", "where", "being", "other", "such", "these", "those",
            "like", "want", "need", "know", "think", "said", "many",
            "comme", "pour", "avec", "dans", "mais", "plus", "tout",
            "faire", "sont", "elle", "nous", "vous", "leur", "même",
            "encore", "aussi", "donc", "quand", "rien", "bien", "fait",
            "dire", "veux", "faut", "peut", "suis", "sera", "etre",
            "avoir", "chez", "vers", "sans", "sous", "tres", "trop",
            "autre", "cette", "entre", "parce", "alors", "juste",
            "toute", "toutes", "tous", "celle", "ceux"}
    concepts = [w for w in words if w not in stop and len(w) >= 4]
    if not concepts:
        return "BRIDGE: no concepts extracted from text"

    # Deduplicate while preserving order
    seen = set()
    unique_concepts = []
    for c in concepts:
        if c not in seen:
            seen.add(c)
            unique_concepts.append(c)
    concepts = unique_concepts

    # Load mycelium and spread activation
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        from mycelium import Mycelium
        m = Mycelium(repo)
    except Exception as e:
        return f"BRIDGE: mycelium load failed: {e}"

    activated = m.spread_activation(concepts, hops=hops, top_n=top_n)
    if not activated:
        return f"BRIDGE: no activation from [{', '.join(concepts[:5])}]"

    # Also get direct neighbors for top 3 seed concepts
    direct = {}
    for seed in concepts[:3]:
        neighbors = m.get_related(seed, top_n=5)
        if neighbors:
            direct[seed] = neighbors

    # Format output
    output = [f"BRIDGE: [{', '.join(concepts[:8])}] -> {len(activated)} activated concepts"]
    output.append("")

    # Activated concepts (spreading activation results)
    output.append("  ACTIVATED (spreading activation):")
    for concept, score in activated[:top_n]:
        bar = "#" * int(score * 20)
        output.append(f"    {concept:<30} {score:.3f} {bar}")

    # Direct neighbors
    if direct:
        output.append("")
        output.append("  DIRECT NEIGHBORS:")
        for seed, neighbors in direct.items():
            nbr_str = ", ".join(f"{n}({w:.0f})" for n, w in neighbors[:5])
            output.append(f"    {seed}: {nbr_str}")

    # Search tree branches for activated concepts
    if include_branches and _m.TREE_DIR.exists():
        activated_words = {c for c, _ in activated[:top_n]}
        branch_hits = []
        for mn_file in _m.TREE_DIR.glob("*.mn"):
            if mn_file.name == "root.mn":
                continue
            try:
                text_content = mn_file.read_text(encoding="utf-8", errors="ignore")
                content_words = set(re.findall(r'[A-Za-z]{4,}', text_content.lower()))
                overlap = activated_words & content_words
                if len(overlap) >= 2:
                    # Find the most relevant lines
                    best_lines = []
                    for line in text_content.split("\n"):
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"):
                            continue
                        line_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
                        line_overlap = len(activated_words & line_words)
                        if line_overlap >= 1:
                            best_lines.append((line_overlap, stripped[:120]))
                    best_lines.sort(key=lambda x: x[0], reverse=True)
                    branch_hits.append((len(overlap), mn_file.stem, best_lines[:3]))
            except OSError:
                continue

        if branch_hits:
            branch_hits.sort(key=lambda x: x[0], reverse=True)
            output.append("")
            output.append("  BRANCH MATCHES:")
            for score, branch, lines in branch_hits[:5]:
                output.append(f"    [{branch}] ({score} concepts)")
                for _, line in lines:
                    output.append(f"      {line}")

    # Fusions that involve activated concepts
    fusions = m.get_fusions()
    relevant_fusions = []
    activated_set = {c for c, _ in activated}
    seed_set = set(concepts)
    for key, fusion in fusions.items():
        parts = set(fusion.get("concepts", []))
        if parts & (activated_set | seed_set):
            relevant_fusions.append(fusion)

    if relevant_fusions:
        output.append("")
        output.append("  ACTIVE FUSIONS:")
        for f in relevant_fusions[:5]:
            output.append(f"    {' + '.join(f['concepts'])} -> {f.get('form', '?')} (strength: {f.get('strength', 0):.0f})")

    # Observe the bridge query itself (feed the mycelium with this interaction)
    try:
        m.observe(concepts[:10])
        m.save()
    except Exception:
        pass  # non-critical

    return "\n".join(output)


def bridge_fast(text: str, top_n: int = 5) -> str:
    """P42 fast path: lightweight bridge for hooks (<0.5s target).

    Uses get_related() (direct neighbors) instead of spread_activation()
    (full graph traversal). 300x faster on large myceliums.

    Returns compact context for injection into Claude's conversation.
    """
    repo = _m._REPO_PATH or Path(".")

    # Extract concepts (same filter as bridge())
    words = re.findall(r'[A-Za-z\u00c0-\u024f]{4,}', text.lower())
    stop = {"that", "this", "with", "from", "have", "been", "were", "will",
            "would", "could", "should", "their", "there", "about", "which",
            "when", "what", "your", "they", "them", "than", "then", "also",
            "just", "only", "some", "more", "very", "most", "each", "into",
            "over", "after", "before", "between", "under", "through", "does",
            "here", "where", "being", "other", "such", "these", "those",
            "like", "want", "need", "know", "think", "said", "many",
            "comme", "pour", "avec", "dans", "mais", "plus", "tout",
            "faire", "sont", "elle", "nous", "vous", "leur", "même",
            "encore", "aussi", "donc", "quand", "rien", "bien", "fait",
            "dire", "veux", "faut", "peut", "suis", "sera", "etre",
            "avoir", "chez", "vers", "sans", "sous", "tres", "trop",
            "autre", "cette", "entre", "parce", "alors", "juste",
            "toute", "toutes", "tous", "celle", "ceux"}
    concepts = []
    seen = set()
    for w in words:
        if w not in stop and w not in seen and len(w) >= 4:
            seen.add(w)
            concepts.append(w)
    if not concepts:
        return ""

    # Load mycelium
    # CHUNK B2 (2026-05-08): differentiate failure modes so silent
    # empty bridge no longer hides real errors from the user.
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        from mycelium import Mycelium
        m = Mycelium(repo)
    except (ImportError, ModuleNotFoundError):
        # mycelium module unavailable — typically dev env without all deps
        print("[MUNINN BRIDGE] mycelium module unavailable", file=sys.stderr)
        return ""
    except FileNotFoundError:
        # First run, no mycelium DB yet — no signal needed
        return ""
    except Exception as e:
        # Real, unexpected failure — log for audit + warn user
        print(f"[MUNINN BRIDGE] mycelium init failed: {e}", file=sys.stderr)
        try:
            from _hook_logger import log_hook_event
            log_hook_event("bridge_fast", "mycelium_init", e)
        except Exception:
            pass
        return ""

    # get_related for top seeds (fast path — no full graph scan)
    all_neighbors = {}
    for seed in concepts[:5]:
        neighbors = m.get_related(seed, top_n=top_n)
        if neighbors:
            all_neighbors[seed] = neighbors

    if not all_neighbors:
        return ""

    # Compact output
    lines = ["[MYCELIUM BRIDGE]"]
    for seed, neighbors in all_neighbors.items():
        nbrs = ", ".join(f"{n}" for n, w in neighbors[:5])
        lines.append(f"  {seed} -> {nbrs}")

    # Skip observe+save in fast path — too slow for hooks.
    # The full bridge() or feed hooks handle persistence.

    output = "\n".join(lines)

    # Anti-Adversa: defense-in-depth in case a poisoned mycelium concept
    # contains a chained command sequence that would inject 50+ shell
    # subcommands into Claude's context. See _secrets.clamp_chained_commands
    # and docs/CLAUDE_CODE_LEAK_INTEL.md section 10.
    try:
        from _secrets import clamp_chained_commands
        output, _ = clamp_chained_commands(output)
    except Exception:
        pass  # never break the fast-path on a defense failure

    return output


# ── B4: Endsley L3 Prediction ────────────────────────────────────

def predict_next(current_concepts: list[str] = None, top_n: int = 5,
                  _mycelium=None) -> list[tuple[str, float]]:
    """B4: Predict which branches will be needed next.

    Uses spreading activation from current session concepts to find
    branches the user hasn't loaded yet but likely will need.
    Endsley Level 3 = projection of future state from current situation.

    Args:
        current_concepts: concepts seen so far (if None, reads from last session)
        top_n: how many predictions to return

    Returns:
        list of (branch_name, prediction_score) sorted descending.
    Source: Endsley 1995 (Situation Awareness), Collins & Loftus 1975
    """
    repo = _m._REPO_PATH or Path(".")

    # Get current concepts from session or parameter
    if not current_concepts:
        # Try to extract from last session index
        index_path = repo / ".muninn" / "session_index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(index, list) and index:
                    current_concepts = index[-1].get("concepts", [])
            except (json.JSONDecodeError, OSError):
                pass
        if not current_concepts:
            return []

    # Spread activation through mycelium (reuse instance if provided by boot)
    try:
        if _mycelium is not None:
            m = _mycelium
        else:
            if _m._CORE_DIR not in sys.path:
                sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo)
        activated = m.spread_activation(current_concepts, hops=2, top_n=50)
    except Exception:
        activated = []

    if not activated:
        return []

    # Load tree to find unloaded branches
    tree = load_tree()
    nodes = tree["nodes"]
    activated_set = {c for c, _ in activated}
    activated_dict = dict(activated)

    # Score each branch by how many activated concepts it covers
    predictions = []
    for name, node in nodes.items():
        if node.get("type") != "branch":
            continue
        tags = set(node.get("tags", []))
        if not tags:
            continue
        # Score = sum of activation for matching tags
        overlap = tags & activated_set
        if overlap:
            score = sum(activated_dict.get(t, 0) for t in overlap)
            # Penalize recently accessed (already loaded = less useful to predict)
            recall = _ebbinghaus_recall(node)
            if recall > 0.8:
                score *= 0.3  # heavily penalize already-fresh branches
            predictions.append((name, score))

    predictions.sort(key=lambda x: -x[1])
    return predictions[:top_n]


# ── B5: Session mode detection (convergent/divergent) ────────────

def detect_session_mode(concepts: list[str] = None) -> dict:
    """B5: Detect if current session is convergent or divergent.

    Convergent: focused work (debug, fix) — few unique concepts, high repetition.
    Divergent: exploratory (brainstorm, research) — many unique concepts, low repetition.

    Uses concept diversity ratio: unique_concepts / total_mentions.
    High ratio (>0.6) = divergent, low ratio (<0.4) = convergent.

    Returns dict with:
      - mode: "convergent" | "divergent" | "balanced"
      - diversity: float in [0, 1]
      - suggested_k: sigmoid k value for spreading activation
      - concept_count: number of unique concepts

    Source: Carhart-Harris 2012 (entropic brain), Guilford 1967 (divergent thinking)
    """
    repo = _m._REPO_PATH or Path(".")

    # Get concepts from parameter or last session
    if not concepts:
        index_path = repo / ".muninn" / "session_index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(index, list) and index:
                    concepts = index[-1].get("concepts", [])
            except (json.JSONDecodeError, OSError):
                pass
        if not concepts:
            return {"mode": "balanced", "diversity": 0.5, "suggested_k": 10, "concept_count": 0}

    # Compute diversity: unique / total
    total = len(concepts)
    unique = len(set(concepts))
    diversity = unique / max(total, 1)

    # Classify
    if diversity > 0.6:
        mode = "divergent"
        suggested_k = 5    # low k = wide sigmoid = more exploration
    elif diversity < 0.4:
        mode = "convergent"
        suggested_k = 20   # high k = sharp sigmoid = tight focus
    else:
        mode = "balanced"
        suggested_k = 10   # default

    return {
        "mode": mode,
        "diversity": round(diversity, 4),
        "suggested_k": suggested_k,
        "concept_count": unique,
    }


def adapt_k(concepts: list[str] = None):
    """C4: Real-time sigmoid k adaptation.

    Recalculates session mode from current concepts and updates the
    mycelium's sigmoid_k. Called mid-session by recall() and inject_memory().
    """
    try:
        mode = detect_session_mode(concepts)
        # M7 fix: don't create a throwaway Mycelium — just return the mode info.
        # The k value is applied by callers that have a persistent Mycelium instance.
        return {"old_k": 10, "new_k": mode["suggested_k"], "mode": mode["mode"],
                "diversity": mode["diversity"]}
    except Exception:
        return {"old_k": 10, "new_k": 10, "mode": "balanced", "diversity": 0.5}


# ── B6: Klein RPD session-type classification ────────────────────

def classify_session(concepts: list[str] = None, tagged_lines: list[str] = None) -> dict:
    """B6: Recognize session type from concept and tag patterns.

    Session types:
      - debug: error/fix patterns, E> tags dominant
      - feature: new concepts, D> decision tags
      - explore: high diversity, many unique concepts
      - refactor: code concepts dominant, low diversity
      - review: B> benchmark tags, F> fact tags

    Returns dict with:
      - type: str (one of the above)
      - confidence: float in [0, 1]
      - tag_profile: dict of tag counts

    Source: Klein 1986 (Recognition-Primed Decision)
    """
    repo = _m._REPO_PATH or Path(".")

    # Get data from parameters or session index
    # Only fall back to index when BOTH are missing — if concepts are provided
    # explicitly, don't load tagged_lines from index (they would dominate scoring)
    if not concepts and not tagged_lines:
        index_path = repo / ".muninn" / "session_index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(index, list) and index:
                    entry = index[-1]
                    concepts = entry.get("concepts", [])
                    tagged_lines = entry.get("tagged", [])
            except (json.JSONDecodeError, OSError):
                pass

    if not concepts and not tagged_lines:
        return {"type": "unknown", "confidence": 0.0, "tag_profile": {}}

    # Count tag types
    tag_counts = {"E": 0, "D": 0, "B": 0, "F": 0, "A": 0}
    for line in (tagged_lines or []):
        for prefix in tag_counts:
            if line.startswith(f"{prefix}>"):
                tag_counts[prefix] += 1
                break

    total_tags = sum(tag_counts.values())

    # Compute concept diversity
    mode_info = detect_session_mode(concepts)
    diversity = mode_info["diversity"]

    # Concept keyword signals (B6: concepts themselves hint at session type)
    concept_lower = {c.lower() for c in (concepts or [])}
    debug_words = {"bug", "crash", "fix", "error", "traceback", "exception", "fail", "broken"}
    feature_words = {"feature", "add", "new", "implement", "create", "build"}
    explore_words = {"explore", "search", "find", "investigate", "scan", "discover"}
    refactor_words = {"refactor", "clean", "rename", "move", "reorganize", "simplify"}
    review_words = {"review", "audit", "benchmark", "test", "verify", "check"}

    concept_debug = len(concept_lower & debug_words)
    concept_feature = len(concept_lower & feature_words)
    concept_explore = len(concept_lower & explore_words)
    concept_refactor = len(concept_lower & refactor_words)
    concept_review = len(concept_lower & review_words)

    # Classify by dominant signal (tags + concept keywords + diversity)
    scores = {
        "debug": tag_counts["E"] * 3 + (1.0 - diversity) * 2 + concept_debug * 3,
        "feature": tag_counts["D"] * 2 + diversity * 2 + concept_feature * 3,
        "explore": diversity * 5 + mode_info["concept_count"] * 0.1 + concept_explore * 3,
        "refactor": (1.0 - diversity) * 3 + (tag_counts["A"] * 2 if tag_counts["A"] else 0) + concept_refactor * 3,
        "review": tag_counts["B"] * 3 + tag_counts["F"] * 2 + concept_review * 3,
    }

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    total_score = sum(scores.values())
    confidence = best_score / max(total_score, 0.01)

    return {
        "type": best_type,
        "confidence": round(confidence, 4),
        "tag_profile": tag_counts,
    }


# ── H3: HUGINN — the thinking raven ─────────────────────────────

def huginn_think(query: str = "", top_n: int = 5) -> list[dict]:
    """H3: Formulate insights in natural language. The second raven speaks.

    Reads .muninn/insights.json (written by dream()), filters by relevance
    to query, and formats as human-readable messages.
    Source: Norse mythology — Huginn (thought) + Muninn (memory).

    Returns list of dicts: {type, text, score, age, formatted}.
    """
    repo = _m._REPO_PATH or Path(".")
    insights_path = repo / ".muninn" / "insights.json"
    if not insights_path.exists():
        return []

    try:
        raw = json.loads(insights_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not raw:
        return []

    # Age calculation (days since insight)
    now = time.strftime("%Y-%m-%d")
    for ins in raw:
        ts = ins.get("timestamp", "")[:10]
        try:
            from datetime import datetime
            delta = (datetime.strptime(now, "%Y-%m-%d") - datetime.strptime(ts, "%Y-%m-%d")).days
        except (ValueError, TypeError):
            delta = 0
        ins["age_days"] = delta

    # Filter by query relevance if query provided
    if query:
        q_words = set(query.lower().split())
        scored = []
        for ins in raw:
            concepts = ins.get("concepts", [])
            text = ins.get("text", "").lower()
            # Score: concept match + text word overlap
            match = sum(1 for w in q_words if any(w in c.lower() for c in concepts))
            match += sum(0.5 for w in q_words if w in text)
            ins["relevance"] = match
            scored.append(ins)
        # Keep only relevant (>0) or top by score if nothing matches
        relevant = [s for s in scored if s["relevance"] > 0]
        if relevant:
            raw = sorted(relevant, key=lambda x: (-x["relevance"], -x.get("score", 0)))
        else:
            raw = sorted(raw, key=lambda x: -x.get("score", 0))

    # Format each insight as natural language
    TYPE_ICONS = {
        "strong_pair": "BOND",
        "absence": "BLIND SPOT",
        "validated_dream": "CONFIRMED",
        "imbalance": "WARNING",
        "health": "HEALTH",
    }

    results = []
    for ins in raw[:top_n]:
        itype = ins.get("type", "insight")
        icon = TYPE_ICONS.get(itype, "INSIGHT")
        text = ins.get("text", "")
        score = ins.get("score", 0)
        age = ins.get("age_days", 0)
        age_str = "today" if age == 0 else f"{age}d ago"

        formatted = f"[{icon}] {text} (score={score}, {age_str})"
        results.append({
            "type": itype,
            "text": text,
            "score": score,
            "age": age,
            "formatted": formatted,
        })

    return results


# ── STATUS ────────────────────────────────────────────────────────

def show_status():
    tree = load_tree()
    nodes = tree["nodes"]

    # Refresh hash + temperature
    refresh_tree_metadata(tree)
    save_tree(tree)

    print("=== MUNINN TREE ===")
    print(f"  Version: {tree['version']}")
    print(f"  Updated: {tree.get('updated', '?')}")
    print(f"  Nodes: {len(nodes)}")
    print()

    total_lines = 0
    for name, node in nodes.items():
        ntype = node["type"]
        prefix = {"root": "R", "branch": "B", "leaf": "L"}.get(ntype, "?")
        fill = node["lines"] / max(node["max_lines"], 1) * 100
        over = " OVER!" if node["lines"] > node["max_lines"] else ""
        total_lines += node["lines"]
        h = node.get("hash", "?")[:8]
        temp = node.get("temperature", 0)
        temp_bar = "=" * int(temp * 10) + "-" * (10 - int(temp * 10))
        tags = f" [{','.join(node.get('tags', [])[:3])}]" if node.get("tags") else ""
        print(f"  [{prefix}] {name}: {node['lines']}/{node['max_lines']} "
              f"({fill:.0f}%){over} t={temp:.2f}[{temp_bar}] #{h}{tags}")

    est_tokens = total_lines * BUDGET["tokens_per_line"]
    est_compressed = est_tokens / BUDGET["compression_ratio"]
    print(f"\n  Total: {total_lines} lines")
    print(f"  Budget: ~{est_compressed:.0f}/{BUDGET['max_loaded_tokens']} tokens "
          f"({est_compressed / BUDGET['max_loaded_tokens'] * 100:.1f}%)")

    # H3.1 (2026-05-09): expose mycelium growth_stats inline. Lazy import +
    # try/except so a corrupt mycelium does not break `muninn-mem status`.
    try:
        try:
            from mycelium import Mycelium
        except ImportError:
            from engine.core.mycelium import Mycelium
        repo = _m._REPO_PATH or Path(".").resolve()
        g = Mycelium(repo).growth_stats()
        print(f"\nGrowth (mycelium):")
        print(f"  Concepts:    {g.get('concepts', 0)}")
        print(f"  Connections: {g.get('connections', 0)} / {g.get('max_connections', 0)}"
              f" {'(AT LIMIT)' if g.get('at_limit') else ''}")
    except Exception as exc:
        print(f"\nGrowth: <unavailable: {exc}>", file=sys.stderr)


def diagnose():
    """C6: Full health diagnostic — tree + mycelium + anomalies + blind spots."""
    print("=== MUNINN DIAGNOSE ===\n")

    # 1. Tree health
    tree = load_tree()
    nodes = tree["nodes"]
    branches = {k: v for k, v in nodes.items() if k != "root"}
    total_lines = sum(n["lines"] for n in nodes.values())
    overfull = [k for k, v in nodes.items() if v["lines"] > v["max_lines"]]
    cold = [k for k, v in branches.items()
            if _ebbinghaus_recall(v) < 0.1]
    hot = [k for k, v in branches.items()
           if _ebbinghaus_recall(v) > 0.8]

    print(f"[TREE] {len(nodes)} nodes, {total_lines} lines")
    print(f"  Hot (recall>0.8): {len(hot)}")
    print(f"  Cold (recall<0.1): {len(cold)}")
    if overfull:
        print(f"  OVERFULL: {', '.join(overfull)}")
    else:
        print("  No overfull branches")

    # 2. Mycelium health
    print()
    try:
        from mycelium import Mycelium
        m = Mycelium(_m._REPO_PATH or Path(".").resolve())
        if m._db is not None:
            n_conns = m._db.connection_count()
            n_fusions = len(m._db.get_all_fusions())
        else:
            n_conns = len(m.data.get("connections", {}))
            n_fusions = len(m.data.get("fusions", {}))
        print(f"[MYCELIUM] {n_conns:,} connections, {n_fusions:,} fusions")
        print(f"  Beta: {m.SATURATION_BETA}, Threshold: {m.SATURATION_THRESHOLD}")

        # A5: Spectral gap
        if hasattr(m, '_spectral_gap') and m._spectral_gap is not None:
            print(f"  Spectral gap: {m._spectral_gap:.4f}")

        # B2: Anomalies
        try:
            anomalies = m.detect_anomalies()
            iso = len(anomalies.get("isolated", []))
            hubs = anomalies.get("hubs", [])
            weak = anomalies.get("weak_zones", [])
            print(f"  Isolated nodes: {iso}")
            if hubs:
                print(f"  Hub monopolies: {', '.join(h[0] for h in hubs[:5])}")
            if weak:
                print(f"  Weak zones: {', '.join(weak[:5])}")
        except Exception as e:
            print(f"  Anomaly detection: {e}")

        # B3: Blind spots
        try:
            spots = m.detect_blind_spots(top_n=10)
            if spots:
                print(f"  Blind spots: {len(spots)}")
                for a, b, reason in spots[:3]:
                    print(f"    {a} <-> {b} ({reason})")
            else:
                print("  Blind spots: none detected")
        except Exception as e:
            print(f"  Blind spots: {e}")

    except Exception as e:
        print(f"[MYCELIUM] Not available: {e}")

    # 3. Boot feedback
    print()
    feedback_path = (_m._REPO_PATH or Path(".").resolve()) / ".muninn" / "boot_feedback.json"
    if feedback_path.exists():
        try:
            import json as _json
            history = _json.loads(feedback_path.read_text(encoding="utf-8"))
            if isinstance(history, list) and history:
                last = history[-1]
                print(f"[BOOT FEEDBACK] Last boot: {last.get('timestamp', '?')}")
                print(f"  Query: {last.get('query', '(none)')}")
                print(f"  Blind spots covered: {len(last.get('covered', []))}/{last.get('blind_spots_total', '?')}")
                print(f"  Branches loaded: {len(last.get('branches_loaded', []))}")
            else:
                print("[BOOT FEEDBACK] No history yet")
        except Exception:
            print("[BOOT FEEDBACK] Error reading feedback")
    else:
        print("[BOOT FEEDBACK] No feedback file yet (run boot first)")

    # 4. Sessions
    print()
    sessions_dir = (_m._REPO_PATH or Path(".").resolve()) / ".muninn" / "sessions"
    if sessions_dir.exists():
        mn_files = list(sessions_dir.glob("*.mn"))
        print(f"[SESSIONS] {len(mn_files)} compressed transcripts")
        if mn_files:
            newest = max(mn_files, key=lambda p: p.stat().st_mtime)
            print(f"  Latest: {newest.name}")
    else:
        print("[SESSIONS] No sessions directory")

    print("\n=== DIAGNOSE COMPLETE ===")


def _append_session_log(repo_path: Path, compressed: str, ratio: float):
    """Append a 1-line session summary to root.mn's R: section."""
    root_path = repo_path / ".muninn" / "tree" / "root.mn"
    if not root_path.exists():
        return

    # Extract a summary: first non-header, non-empty line from compressed
    summary = ""
    for line in compressed.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("?FACTS"):
            # Strip memory tags for the log
            for tag in ("D>", "B>", "E>", "F>", "A>"):
                if line.startswith(tag):
                    line = line[2:]
                    break
            summary = line[:80]
            break

    if not summary:
        summary = "session compressed"

    date = time.strftime("%Y-%m-%d")
    log_line = f"  {date} x{ratio:.1f} {summary}"

    root_text = root_path.read_text(encoding="utf-8")

    # Find R: section and append
    if "\nR:\n" in root_text:
        # Insert after R: header, keep only last 5 entries
        parts = root_text.split("\nR:\n", 1)
        # R: section ends at next ## header or EOF (not \n\n which can appear inside entries)
        r_rest_match = re.search(r'\n(?=##\s)', parts[1])
        if r_rest_match:
            r_section = [parts[1][:r_rest_match.start()], parts[1][r_rest_match.start():]]
        else:
            r_section = [parts[1]]
        existing_lines = [l for l in r_section[0].split("\n") if l.strip()]
        # Dedup: don't append if this exact line already exists
        if log_line not in existing_lines:
            existing_lines.append(log_line)
        # Also dedup any historical duplicates
        seen = set()
        deduped = []
        for el in existing_lines:
            if el not in seen:
                seen.add(el)
                deduped.append(el)
        existing_lines = deduped[-5:]  # keep last 5
        rest = r_section[1] if len(r_section) > 1 else ""
        new_text = parts[0] + "\nR:\n" + "\n".join(existing_lines) + "\n"
        if rest:
            new_text += "\n" + rest
        _atomic_text_write(root_path, new_text)
    else:
        # No R: section yet — append one
        root_text = root_text.rstrip() + f"\n\nR:\n{log_line}\n"
        _atomic_text_write(root_path, root_text)


def _extract_error_fixes(repo_path: Path, compressed: str):
    """P18: Extract error->fix pairs from tagged compressed text.

    Scans for E> lines followed by B> or D> lines = error+solution pairs.
    Stores in .muninn/errors.json for auto-surfacing at boot.
    """
    errors_path = repo_path / ".muninn" / "errors.json"
    try:
        errors = json.loads(errors_path.read_text(encoding="utf-8")) if errors_path.exists() else []
        if not isinstance(errors, list):
            errors = []
    except (json.JSONDecodeError, OSError):
        errors = []

    lines = compressed.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("E>"):
            continue
        error_text = stripped[2:].strip()
        # Look ahead for a fix (B> or D>) within next 3 lines
        fix_text = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            next_line = lines[j].strip()
            if next_line.startswith("B>"):
                fix_text = next_line[2:].strip()
                break
            elif next_line.startswith("D>"):
                fix_text = next_line[2:].strip()
                break
        if error_text and fix_text:
            entry = {
                "error": error_text[:200],
                "fix": fix_text[:200],
                "date": time.strftime("%Y-%m-%d"),
            }
            # Avoid duplicates
            if not any(e.get("error") == entry["error"] for e in errors):
                errors.append(entry)

    # Keep last 50 entries
    errors = errors[-50:]
    _atomic_json_write(errors_path, errors)




def inject_memory(fact: str, repo_path: Path = None):
    """B7: Inject a fact into the tree mid-session.

    Creates or appends to a 'live' branch. The fact is immediately
    available in the next boot/recall without waiting for session end.
    Also feeds the mycelium so the concept graph learns immediately.

    Source: LITERATURE #8 (live memory), Park et al. 2023
    """
    if not fact or not fact.strip():
        print("ERROR: empty fact")
        return

    repo = repo_path or _m._REPO_PATH or Path(".").resolve()
    repo = Path(repo).resolve()

    # CRITICAL (2026-05-11 PM, follow-up to BUG-111): propagate _REPO_PATH
    # to the package namespace BEFORE load_tree/init_tree call so the
    # init_tree guard recognizes this tree dir as legitimate. Same pattern
    # as bootstrap_mycelium and the `muninn-mem init` handler.
    _m._REPO_PATH = repo
    try:
        import muninn as _pkg
        _pkg._REPO_PATH = repo
    except Exception:
        pass
    _refresh_tree_paths()

    with _m._MuninnLock(repo):
        # Ensure tree exists
        tree = load_tree()
        nodes = tree["nodes"]

        # Find or create the 'live' branch
        live_name = None
        for name, node in nodes.items():
            if node.get("type") == "branch" and "live_inject" in node.get("tags", []):
                live_name = name
                break

        # Use the correct tree directory (_m.TREE_DIR, not memory/branches/)
        tree_dir = _get_tree_dir()
        tree_dir.mkdir(parents=True, exist_ok=True)

        if live_name:
            # Append to existing live branch
            mn_path = tree_dir / nodes[live_name]["file"]
            existing = ""
            if mn_path.exists():
                existing = mn_path.read_text(encoding="utf-8")
            new_content = existing.rstrip() + "\n" + f"D> {fact.strip()}" + "\n"
        else:
            # Create new live branch
            existing_ids = [int(n[1:]) for n in nodes if n.startswith("b") and n[1:].isdigit()]
            next_id = max(existing_ids, default=-1) + 1
            live_name = f"b{next_id:04d}"
            new_content = f"## Live Injection\nD> {fact.strip()}\n"

            import time
            nodes[live_name] = {
                "type": "branch",
                "file": f"{live_name}.mn",
                "lines": 0,
                "max_lines": 150,
                "children": [],
                "parent": "root",
                "tags": ["live_inject", "injection"],
                "access_count": 1,
                "last_access": time.strftime("%Y-%m-%d"),
                "usefulness": 1.0,
                "temperature": 0.8,
            }

        # Write branch file to tree directory
        mn_path = tree_dir / nodes[live_name]["file"]
        _atomic_text_write(mn_path, new_content)

        # Update metadata
        nodes[live_name]["hash"] = compute_hash(mn_path)
        nodes[live_name]["lines"] = len(new_content.split("\n"))

        save_tree(tree)

        # Feed mycelium with the fact's concepts
        try:
            if _m._CORE_DIR not in sys.path:
                sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo)
            m.observe_text(_redact_secrets_text(fact))
            m.save()
        except Exception:
            pass  # Mycelium feed is best-effort

        lines = new_content.count("\n")
        print(f"MUNINN INJECT: '{fact[:60]}' -> {live_name} ({lines} lines)")

        # C4: Real-time k adaptation after injection
        fact_concepts = re.findall(r'[A-Za-z]{4,}', fact.lower())
        if fact_concepts:
            adapt_k(fact_concepts)

        return live_name


# P3 split (2026-05-10) — ensure muninn_tree itself is registered before any
# sub-module (muninn_tree_doctor / _prune / _boot) tries to `from muninn_tree
# import _m, …`. setdefault is idempotent and a no-op on the canonical load.
# Conditional on `__name__ in sys.modules` because `spec_from_file_location +
# module_from_spec + exec_module` (used by test_chunk_d11) bypasses the
# automatic sys.modules registration — KeyError otherwise.
_self_mod = sys.modules.get(__name__)
if _self_mod is not None:
    sys.modules.setdefault('muninn_tree', _self_mod)


# P3.1 (2026-05-10) — re-export doctor() from extracted sub-module so external
# code keeps working with `from muninn_tree import doctor` and the existing
# muninn/muninn_tree.py shim re-export list stays correct.
from muninn_tree_doctor import doctor  # noqa: E402,F401

# P3.2 (2026-05-10) — re-export prune cluster from muninn_tree_prune.py.
# Keeps `from muninn_tree import prune, _sleep_consolidate, _light_prune,
# _auto_backup_tree` working unchanged. muninn_feed.py imports
# `_m._sleep_consolidate` and `_m._light_prune` via the proxy — still resolves
# because the muninn package re-exports through `muninn._engine` ← muninn.muninn_tree.
from muninn_tree_prune import (  # noqa: E402,F401
    _auto_backup_tree,
    _light_prune,
    _sleep_consolidate,
    prune,
)

# P3.3 (2026-05-10) — re-export boot cluster from muninn_tree_boot.py. Must
# be the LAST import because recall() (defined in this file) calls
# `_surface_known_errors` — Python resolves names at call time so the
# re-export below makes the symbol reachable before any actual invocation.
from muninn_tree_boot import (  # noqa: E402,F401
    _load_relevant_sessions,
    _load_virtual_branches,
    _surface_insights_for_boot,
    _surface_known_errors,
    boot,
)
