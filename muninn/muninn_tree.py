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

try:
    from .tokenizer import count_tokens, token_count
except ImportError:
    from tokenizer import count_tokens, token_count
try:
    from ._secrets import redact_secrets_text as _redact_secrets_text
except ImportError:
    from _secrets import redact_secrets_text as _redact_secrets_text


class _ModRef:
    """Lazy reference to muninn engine — avoids circular import."""
    def __getattr__(self, name):
        mod = sys.modules.get('muninn._engine') or sys.modules['muninn']
        return getattr(mod, name)
    def __setattr__(self, name, value):
        mod = sys.modules.get('muninn._engine') or sys.modules['muninn']
        setattr(mod, name, value)

_m = _ModRef()

__all__ = ['BUDGET', '_actr_activation', '_append_session_log', '_atomic_json_write', '_auto_backup_tree', '_days_since', '_ebbinghaus_recall', '_extract_error_fixes', '_get_tree_dir', '_get_tree_meta', '_light_prune', '_load_relevant_sessions', '_load_virtual_branches', '_refresh_tree_paths', '_safe_tree_path', '_sleep_consolidate', '_surface_insights_for_boot', '_surface_known_errors', '_tfidf_relevance', '_tokenize_words', '_tree_lock', '_tree_unlock', 'adapt_k', 'adaptive_boot_budget', 'boot', 'bridge', 'bridge_fast', 'build_tree', 'classify_session', 'cleanup_legacy_tree', 'cleanup_tmp_files', 'compute_hash', 'compute_temperature', 'detect_session_mode', 'diagnose', 'doctor', 'extract_tags', 'grow_branches_from_session', 'huginn_think', 'init_tree', 'inject_memory', 'load_tree', 'predict_next', 'prune', 'read_node', 'recall', 'refresh_tree_metadata', 'save_tree', 'show_status']


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
        context_size = int(os.environ.get("MUNINN_CONTEXT_SIZE", 200_000))
    budget = int(context_size * 0.15)
    return max(15_000, min(budget, 100_000))

# ── TREE STRUCTURE ────────────────────────────────────────────────

def _get_tree_dir():
    """Tree lives in target repo's .muninn/tree/, not in Muninn's own memory/."""
    if _m._REPO_PATH:
        return _m._REPO_PATH / ".muninn" / "tree"
    return _m.MUNINN_ROOT / "memory"

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
    """C2: Cleanup orphaned .tmp files in .muninn/ at boot.

    Returns number of .tmp files removed.
    """
    if not _m._REPO_PATH:
        return 0
    muninn_dir = _m._REPO_PATH / ".muninn"
    if not muninn_dir.exists():
        return 0

    removed = 0
    try:
        # Only clean up .tmp files older than 1 hour
        cutoff = time.time() - 3600
        for tmp_file in muninn_dir.rglob("*.tmp"):
            try:
                if tmp_file.stat().st_mtime < cutoff:
                    tmp_file.unlink()
                    removed += 1
            except (OSError, PermissionError):
                pass
    except Exception:
        pass
    return removed


def init_tree():
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

    with open(_m.TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)

    (_m.TREE_DIR / "root.mn").write_text(
        "# MUNINN|codebook=v0.1\n", encoding="utf-8"
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
    lock_f, _ = _tree_lock(_m.TREE_META)
    try:
        with open(_m.TREE_META, encoding="utf-8") as f:
            tree = json.load(f)
        # Validate all node file paths to prevent path traversal
        tree_dir_resolved = str(_m.TREE_DIR.resolve())
        for name, node in tree.get("nodes", {}).items():
            if "file" in node:
                resolved = str((_m.TREE_DIR / node["file"]).resolve())
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
    """Save tree metadata (atomic write via tempfile + rename). H12: file locked."""
    import tempfile, os
    tree["updated"] = time.strftime("%Y-%m-%d")
    _m.TREE_DIR.mkdir(parents=True, exist_ok=True)
    lock_f, _ = _tree_lock(_m.TREE_META)
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
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    finally:
        _tree_unlock(lock_f)


def _atomic_json_write(path: Path, data, indent: int = 2):
    """Atomic JSON write via tempfile + os.replace. Prevents corruption on concurrent read."""
    import tempfile, os
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp_path, str(path))
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
        return max(0, (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days)
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
                filepath.write_text(reconsolidated, encoding="utf-8")
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

def build_tree(filepath: Path):
    """R3: compress BEFORE split. R2: split if over budget."""
    tree = load_tree()

    compressed = _m.compress_file(filepath)
    comp_lines = compressed.split("\n")

    print(f"\n  Source: {filepath.name}")
    print(f"  Original: {filepath.stat().st_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Lines: {len(comp_lines)}")

    if len(comp_lines) <= BUDGET["root_lines"]:
        root_path = _m.TREE_DIR / "root.mn"
        root_path.write_text(compressed, encoding="utf-8")
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
                (_m.TREE_DIR / branch_file).write_text(section, encoding="utf-8")
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
                (_m.TREE_DIR / branch_file).write_text(overflow, encoding="utf-8")
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
        root_path.write_text("\n".join(root_lines), encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(root_lines)
        tree["nodes"]["root"]["children"] = [n for n in tree["nodes"] if n != "root"]
        save_tree(tree)
        print(f"\n  Root: {len(root_lines)} lines, {branch_id} branches")


# ── AUTO-SEGMENTATION (Brique 3) ─────────────────────────────────

def grow_branches_from_session(mn_path: Path, session_sentiment: dict = None):
    """Auto-segment a compressed .mn file into tree branches.

    Splits the session by ## headers (already created by compress_transcript).
    Each section becomes a branch with auto-extracted tags.
    Merges into existing branch if >50% tag overlap (avoids duplication).
    V6B: Propagates session valence/arousal to branch nodes for decay modulation.
    """
    if not mn_path.exists():
        return 0

    content = mn_path.read_text(encoding="utf-8")
    if not content.strip():
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
                existing_text = existing_file.read_text(encoding="utf-8")
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
                old = filepath.read_text(encoding="utf-8")
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
                    filepath.write_text(merged_text, encoding="utf-8")
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
            branch_path.write_text(body, encoding="utf-8")

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

    return sorted(tags)[:10]


def _load_virtual_branches(query: str, budget_tokens: int) -> list:
    """P20c: Load read-only branches from other repos registered in repos.json.

    Returns list of (prefixed_name, text, token_count) tuples.
    Virtual branches are scored by TF-IDF at 0.5x weight vs local branches.
    Max 3 virtual branches loaded, max 50 scanned per repo. Read-only.
    """
    MAX_VIRTUAL = 3
    MAX_SCAN_PER_REPO = 50  # Cap: only scan most recent branches per repo
    WEIGHT_FACTOR = 0.5

    repos = _m._load_repos_registry()
    if not repos:
        return []

    current_repo = _m._REPO_PATH.resolve() if _m._REPO_PATH else None
    if not current_repo:
        return []

    # Collect candidate branches from other repos
    candidates = []  # (repo_name, branch_name, text, tokens, relevance)
    dead_repos = []  # repos to clean from registry

    for repo_name, repo_str in repos.items():
        try:
            repo_p = Path(repo_str)
            # Skip current repo
            if repo_p.resolve() == current_repo:
                continue
            # Check repo still exists
            if not repo_p.exists():
                dead_repos.append(repo_name)
                continue
            tree_dir = repo_p / ".muninn" / "tree"
            tree_meta = tree_dir / "tree.json"
            if not tree_meta.exists():
                continue

            tree_data = json.loads(tree_meta.read_text(encoding="utf-8"))
            other_nodes = tree_data.get("nodes", {})

            # Cap: only scan N most recent branches (by last_access)
            branch_items = [
                (bname, bnode) for bname, bnode in other_nodes.items()
                if bname != "root"
            ]
            branch_items.sort(
                key=lambda x: x[1].get("last_access", "2000-01-01"), reverse=True
            )
            branch_items = branch_items[:MAX_SCAN_PER_REPO]

            branch_contents = {}
            for bname, bnode in branch_items:
                bfile = tree_dir / bnode.get("file", "")
                if bfile.exists():
                    try:
                        text = bfile.read_text(encoding="utf-8")
                        if text.strip():
                            branch_contents[bname] = text
                    except (OSError, UnicodeDecodeError):
                        continue

            if not branch_contents:
                continue

            # Score by TF-IDF if query, else by temperature
            if query:
                scores = _tfidf_relevance(query, branch_contents)
                for bname, text in branch_contents.items():
                    score = scores.get(bname, 0.0) * WEIGHT_FACTOR
                    if score > 0.01:
                        tok = token_count(text)
                        candidates.append((repo_name, bname, text, tok, score))
            else:
                # No query: take hottest branches (by temperature)
                for bname, text in branch_contents.items():
                    bnode_data = other_nodes.get(bname, {})
                    temp = bnode_data.get("temperature", 0.0) * WEIGHT_FACTOR
                    if temp > 0.01:
                        tok = token_count(text)
                        candidates.append((repo_name, bname, text, tok, temp))

        except Exception:
            continue  # Never crash boot because of a broken remote repo

    # Clean dead repos from registry
    if dead_repos:
        try:
            reg_path = _m._repos_registry_path()
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
            for name in dead_repos:
                registry.get("repos", {}).pop(name, None)
            reg_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    if not candidates:
        return []

    # Sort by score descending, take top MAX_VIRTUAL within budget
    candidates.sort(key=lambda x: x[4], reverse=True)
    result = []
    used_tokens = 0
    for repo_name, bname, text, tok, score in candidates:
        if len(result) >= MAX_VIRTUAL:
            break
        if used_tokens + tok > budget_tokens:
            continue
        prefixed = f"{repo_name}::{bname}"
        result.append((prefixed, text, tok))
        used_tokens += tok

    return result


def boot(query: str = "") -> str:
    """R7: load root + relevant branches based on query.

    Scoring (Generative Agents, Park et al. 2023):
      score = α×recency + β×importance + γ×relevance(query)
    where relevance uses TF-IDF cosine similarity on branch content.
    """
    # Adaptive boot budget based on context size
    BUDGET["max_loaded_tokens"] = adaptive_boot_budget()

    tree = load_tree()
    nodes = tree["nodes"]

    root_text = read_node("root", _tree=tree)
    loaded = [("root", root_text)]

    # A6: Boot pre-warm by git diff — load concepts from modified files
    if _m._REPO_PATH:
        try:
            r = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1"],
                cwd=str(_m._REPO_PATH), capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                diff_files = r.stdout.strip().split("\n")
                diff_concepts = set()
                for f in diff_files[:20]:
                    # Extract concept-like words from file paths
                    parts = re.findall(r'[a-zA-Z]{3,}', f.replace("/", " ").replace("\\", " "))
                    diff_concepts.update(p.lower() for p in parts if len(p) >= 4)
                if diff_concepts and not query:
                    query = " ".join(list(diff_concepts)[:10])
        except Exception:
            pass  # git not available or no commits

    # P23: Auto-continue — if no query, use last session's concepts
    if not query and _m._REPO_PATH:
        index_path = _m._REPO_PATH / ".muninn" / "session_index.json"
        if index_path.exists():
            try:
                idx = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(idx, list) and idx:
                    last = idx[-1]
                    concepts = last.get("concepts", [])[:5]
                    if concepts:
                        query = " ".join(concepts)
            except (json.JSONDecodeError, OSError):
                pass

    # Defaults for variables set inside the query block (C2, B3, B4, V8B)
    blind_spot_concepts = set()
    blind_spots = []
    prediction_scores = {}
    scored = []

    if query:
        # P15: Query expansion via mycelium co-occurrences
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            try:
                from .mycelium import Mycelium
            except ImportError:
                from mycelium import Mycelium
            m = Mycelium(_m._REPO_PATH or Path("."))

            # P20b: Pull relevant cross-repo knowledge from meta-mycelium
            query_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', query.lower())
            pulled = m.pull_from_meta(query_concepts=query_words)
            if pulled > 0:
                m.save()

            expanded = set(query_words)
            for word in query_words:
                for related, strength in m.get_related(word, top_n=3):
                    if strength >= 3:  # only strong connections
                        expanded.add(related)
            if expanded - set(query_words):
                query = query + " " + " ".join(expanded - set(query_words))
        except Exception as e:
            print(f"  mycelium query expansion skipped: {e}", file=sys.stderr)

        # Load branch contents for TF-IDF scoring
        branch_contents = {}
        for name, node in nodes.items():
            if name == "root":
                continue
            filepath = _m.TREE_DIR / node["file"]
            try:
                branch_contents[name] = filepath.read_text(encoding="utf-8", errors="ignore")
            except (FileNotFoundError, OSError):
                # Fallback: use tags as content (file may have been pruned concurrently)
                branch_contents[name] = " ".join(node.get("tags", []))

        # TF-IDF relevance scores (0-1)
        relevance_scores = _tfidf_relevance(query, branch_contents)

        # B5: Adapt sigmoid k based on session mode (convergent/divergent)
        try:
            session_mode = detect_session_mode()
            m._sigmoid_k = session_mode["suggested_k"]  # type: ignore[possibly-undefined]
        except Exception as e:
            print(f"  [warn] B5 session mode: {e}", file=sys.stderr)

        # Spreading Activation (Collins & Loftus 1975) — semantic boost
        # Propagates activation through mycelium to find branches that
        # share NO keywords but are semantically connected via co-occurrence
        activation_scores = {}  # branch_name -> activation bonus
        activated_set = {}  # concept -> activation strength (for V5A quorum)
        try:
            activated = m.spread_activation(query_words, hops=2, decay=0.5, top_n=50)  # type: ignore[possibly-undefined]
            if activated:
                # Map activated concepts to branches that contain them
                activated_set = {c: a for c, a in activated}
                for bname, bcontent in branch_contents.items():
                    bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                    overlap = bwords & set(activated_set.keys())
                    if overlap:
                        # Activation score = sum of activations for matching concepts
                        act_score = sum(activated_set[w] for w in overlap)
                        # Cap at 1.0 (don't penalize broad connections)
                        activation_scores[bname] = min(1.0, act_score)
        except Exception as e:
            print(f"  [warn] spreading activation: {e}", file=sys.stderr)

        # V3A: Transitive inference (Wynne 1995, Paz-y-Mino 2004)
        # Ordered chain reasoning: A->B->C infers A->C with decaying strength.
        # Complements spreading activation — tracks multiplicative path strength.
        transitive_scores = {}  # branch_name -> transitive bonus
        try:
            for qw in query_words[:5]:  # top 5 query words to limit compute
                inferred = m.transitive_inference(qw, max_hops=3, beta=0.5, top_n=20)  # type: ignore[possibly-undefined]
                if inferred:
                    inferred_set = {c: s for c, s in inferred}
                    for bname, bcontent in branch_contents.items():
                        bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                        overlap = bwords & set(inferred_set.keys())
                        if overlap:
                            t_score = sum(inferred_set[w] for w in overlap)
                            t_norm = min(1.0, t_score / max(len(overlap), 1))
                            transitive_scores[bname] = max(
                                transitive_scores.get(bname, 0), t_norm)
        except Exception as e:
            print(f"  [warn] V3A transitive: {e}", file=sys.stderr)

        # B3: Detect blind spots — boost branches that fill structural holes
        blind_spot_concepts = set()
        blind_spots = []
        try:
            blind_spots = m.detect_blind_spots(top_n=20)  # type: ignore[possibly-undefined]
            for a, b, _ in blind_spots:
                blind_spot_concepts.add(a)
                blind_spot_concepts.add(b)
        except Exception as e:
            print(f"  [warn] B3 blind spots: {e}", file=sys.stderr)

        # B4: Predict next branches — get prediction scores
        prediction_scores = {}
        try:
            predictions = predict_next(current_concepts=query_words, top_n=20, _mycelium=m)
            prediction_scores = {name: score for name, score in predictions}
        except Exception as e:
            print(f"  [warn] B4 predictions: {e}", file=sys.stderr)

        # V3B: Bayesian Theory of Mind — infer user goal from recent queries
        # (Baker, Saxe, Tenenbaum 2009, Cognition)
        # P(goal|actions) ~ exp(-cost) * prior
        # actions = last 3-5 session queries, goal = branch topic alignment
        btom_scores = {}  # branch_name -> goal alignment score
        if _m._REPO_PATH:
            try:
                import math
                index_path = _m._REPO_PATH / ".muninn" / "session_index.json"
                if index_path.exists():
                    idx = json.loads(index_path.read_text(encoding="utf-8"))
                    if isinstance(idx, list) and len(idx) >= 2:
                        # Collect concepts from last 5 sessions (actions)
                        recent = idx[-5:]
                        action_concepts = {}  # concept -> frequency across recent sessions
                        for sess in recent:
                            for c in sess.get("concepts", []):
                                action_concepts[c] = action_concepts.get(c, 0) + 1
                        if action_concepts:
                            # Normalize to probabilities
                            total_freq = sum(action_concepts.values())
                            action_probs = {c: f / total_freq for c, f in action_concepts.items()}
                            # Score each branch by goal alignment
                            for bname, bcontent in branch_contents.items():
                                try:
                                    bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                                    overlap = bwords & set(action_probs.keys())
                                    if overlap:
                                        alignment = sum(action_probs[w] for w in overlap)
                                        prior = nodes.get(bname, {}).get("usefulness") or 0.5
                                        # V3B fix: sigmoid instead of exp(-1/x) which kills signal
                                        posterior = (alignment / (alignment + 1.0)) * prior
                                        btom_scores[bname] = min(1.0, posterior)
                                except (KeyError, TypeError):
                                    continue
            except Exception as e:
                print(f"  [warn] V3B BToM: {e}", file=sys.stderr)

        # B6: Adjust scoring weights by session type
        w_recall = 0.15
        w_relevance = 0.40
        w_activation = 0.20
        w_usefulness = 0.10
        w_rehearsal = 0.15
        try:
            session_type = classify_session()
            stype = session_type.get("type", "unknown")
            if stype == "debug":
                # Debug: boost recall (recent errors), reduce rehearsal
                w_recall = 0.20
                w_usefulness = 0.10
                w_rehearsal = 0.10
            elif stype == "explore":
                # Explore: boost activation (spread wider)
                w_activation = 0.30
                w_relevance = 0.30
                w_recall = 0.10
                w_usefulness = 0.15
            elif stype == "review":
                # Review: boost rehearsal (need to re-read)
                w_rehearsal = 0.25
                w_relevance = 0.35
                w_recall = 0.10
        except Exception as e:
            print(f"  [warn] B6 classify_session: {e}", file=sys.stderr)

        # V11B: Boyd-Richerson cultural transmission pre-compute (Boyd & Richerson 1985)
        # (1) Conformist bias: tag frequency across all branches (popular = boosted)
        # (2) Prestige bias: td_value from V2B (successful history)
        # (3) Guided variation: correction toward mean usefulness (mu=0.1)
        _tag_freq = {}  # tag -> count of branches with that tag
        _all_usefulness = []
        for _n, _nd in nodes.items():
            if _n == "root":
                continue
            for _t in _nd.get("tags", []):
                _tag_freq[_t] = _tag_freq.get(_t, 0) + 1
            _all_usefulness.append(_nd.get("usefulness", 0.5))
        _n_branches = max(1, len(_all_usefulness))
        _mean_usefulness = sum(_all_usefulness) / _n_branches if _all_usefulness else 0.5
        # Normalize tag frequencies to [0,1]
        _max_tag_freq = max(_tag_freq.values()) if _tag_freq else 1
        # Pre-cache tag sets for V1A coupling (avoids 13M set() constructions)
        _tag_sets_cache = {n: set(nd.get("tags", [])) for n, nd in nodes.items() if n != "root"}
        # V1A: Build tag -> [branches] index for O(1) coupling lookup (was O(n) per tag)
        _tag_to_branches = {}
        for _n, _nd in nodes.items():
            if _n == "root":
                continue
            for _t in _nd.get("tags", []):
                _tag_to_branches.setdefault(_t, []).append(_n)

        # Generative Agents scoring: recency + importance + relevance + activation
        scored = []
        for name, node in nodes.items():
            if name == "root":
                continue

            # Recall probability (Ebbinghaus/Settles spaced repetition)
            recall = _ebbinghaus_recall(node)

            # A2: ACT-R base-level activation (Anderson 1993)
            import math
            actr_raw = _actr_activation(node)
            actr_norm = 1.0 / (1.0 + math.exp(-actr_raw))  # sigmoid -> [0,1]
            recall_blended = 0.7 * recall + 0.3 * actr_norm

            # Relevance: TF-IDF cosine similarity
            relevance = relevance_scores.get(name, 0.0)

            # Activation: spreading activation bonus (Collins & Loftus 1975)
            activation = activation_scores.get(name, 0.0)

            # P36: Usefulness — feedback from past sessions (0.5 = neutral default)
            usefulness = node.get("usefulness", 0.5)

            # Rehearsal need: branches near forgetting threshold
            rehearsal_need = max(0.0, 1.0 - abs(recall - 0.2) / 0.2) if 0.05 < recall < 0.4 else 0.0

            # Base score with B6-adjusted weights
            total = (w_recall * recall_blended + w_relevance * relevance +
                     w_activation * activation + w_usefulness * usefulness +
                     w_rehearsal * rehearsal_need)

            # V7B: ACO pheromone scoring (Dorigo, Maniezzo, Colorni 1996)
            # p_ij = tau^alpha * eta^beta — combines history (tau) and local relevance (eta)
            # tau = usefulness * recall (pheromone = past success * freshness)
            # eta = relevance (heuristic = current query match)
            # alpha=1, beta=2 (beta>alpha = favor local relevance over history)
            tau = max(0.01, usefulness * recall_blended)  # pheromone deposit
            eta = max(0.01, relevance)  # local heuristic
            aco_score = min(1.0, tau * (eta ** 2))  # tau^1 * eta^2, clamped
            # Additive bonus: reward branches with strong history + relevance
            total += 0.05 * aco_score

            # B3: Blind spot bonus — branches covering structural holes get +0.05
            tags = set(node.get("tags", []))
            if tags & blind_spot_concepts:
                total += 0.05

            # V3A: Transitive inference bonus — branches reachable via ordered chains
            t_score = transitive_scores.get(name, 0.0)
            if t_score > 0:
                total += 0.10 * t_score  # V3A: max +0.10 (was 0.05, cosmetic)

            # B4: Prediction bonus — predicted branches get +0.03 * prediction_score
            pred_score = prediction_scores.get(name, 0.0)
            if pred_score > 0:
                total += 0.03 * min(1.0, pred_score)

            # V3B: BToM goal alignment bonus (Baker, Saxe, Tenenbaum 2009)
            btom_score = btom_scores.get(name, 0.0)
            if btom_score > 0:
                total += 0.04 * btom_score  # max +0.04

            # V11B: Boyd-Richerson 3 cultural biases (Boyd & Richerson 1985)
            # (1) Conformist bias: dp = beta*p*(1-p)*(2p-1)
            #     p = fraction of branches sharing this tag profile (popularity)
            _node_tags = node.get("tags", [])
            if _node_tags and _tag_freq:
                _p = sum(_tag_freq.get(t, 0) for t in _node_tags) / (_max_tag_freq * max(1, len(_node_tags)))
                _p = max(0.01, min(0.99, _p))
                _conform_dp = 0.3 * _p * (1.0 - _p) * (2.0 * _p - 1.0)  # beta=0.3
                total += 0.15 * _conform_dp  # V11B fix: was 0.02 (cosmetic)

            # (2) Prestige bias: p' = sum(w_i * p_i) — td_value as prestige
            _td_value = node.get("td_value", 0.5)
            _prestige = _td_value * usefulness  # prestige = success * usefulness
            total += 0.06 * _prestige  # V11B fix: was 0.02 (cosmetic)

            # (3) Guided variation: delta = mu*(p_opt - p)
            #     Pushes score toward population mean usefulness (convergence)
            _mu = 0.1
            _guided_delta = _mu * (_mean_usefulness - usefulness)
            total += 0.06 * _guided_delta  # V11B fix: was 0.02 (cosmetic)

            # V5A: Quorum sensing Hill switch (Waters & Bassler 2005)
            # Activate ONLY when enough neighbors are co-activated (quorum)
            # f(A) = A^n / (K^n + A^n), activated = number of activated co-occurring tags
            _node_tags_set = set(node.get("tags", []))
            if _node_tags_set and activated_set:
                # Count how many spreading-activation concepts overlap with this branch's tags
                _activated_count = sum(1 for t in _node_tags_set if t in activated_set)
                _K_quorum = 2.0  # threshold: need at least ~2 activated neighbors
                _n_hill = 3      # Hill coefficient (steepness)
                if _activated_count > 0:
                    _quorum = (_activated_count ** _n_hill) / (
                        _K_quorum ** _n_hill + _activated_count ** _n_hill)
                    total += 0.03 * _quorum  # V5A: max +0.03 (tuned by retrieval benchmark)

            # V1A: Coupled oscillator (Yekutieli et al. 2005)
            # Temperature coupling: branches connected via mycelium push toward each other
            # tau_coupling = sum_j C_ij * (temp_j - temp_i)
            # Uses _tag_to_branches index (O(1) lookup) instead of O(n) brute-force.
            _my_temp = node.get("temperature", 0.5)
            _coupling_sum = 0.0
            for _t in list(_node_tags_set)[:3]:  # top 3 tags for coupling
                for _sname in _tag_to_branches.get(_t, []):
                    if _sname == name:
                        continue
                    _other_temp = nodes.get(_sname, {}).get("temperature", 0.5)
                    _coupling_sum += 0.02 * (_other_temp - _my_temp)
                    break  # one coupling per tag
            total += max(-0.02, min(0.02, _coupling_sum))  # V1A: tuned by retrieval benchmark

            if total > 0.01:
                scored.append((name, total))

        scored.sort(key=lambda x: x[1], reverse=True)

        # V5B: Cross-inhibition winner-take-all (Seeley et al. 2012, Science)
        # When top branches have similar scores (within 15%), they cross-inhibit.
        # Better branch (higher r) wins. beta controls inhibition strength.
        # dNA/dt = rA*(1-NA/K)*NA - beta*NB*NA
        # Scores normalized to [0,1] before LV, then denormalized back.
        _beta_inhib = 0.05  # inhibition strength (tuned by retrieval benchmark)
        _K_inhib = 1.0      # carrying capacity
        _max_iter = 5
        if _beta_inhib > 0 and len(scored) >= 2:
            top_score = scored[0][1]
            if top_score > 0:
                # Only top 5 competitors (not all within 15% — that killed relevant branches)
                competitors = scored[:5]
                if len(competitors) >= 2:
                    # Normalize to [0,1] for LV dynamics (avoid scale mismatch)
                    pop = {n: s / top_score for n, s in competitors}
                    for _ in range(_max_iter):
                        new_pop = {}
                        for n, s in pop.items():
                            r = relevance_scores.get(n, 0.1)
                            growth = r * (1.0 - s / _K_inhib) * s
                            inhibition = sum(_beta_inhib * pop[peer] * s
                                            for peer in pop if peer != n)
                            new_s = s + 0.1 * (growth - inhibition)  # dt=0.1
                            new_pop[n] = max(0.001, min(_K_inhib, new_s))
                        pop = new_pop
                    # Denormalize back to original scale and update
                    score_map = dict(scored)
                    for n, s in pop.items():
                        score_map[n] = s * top_score  # restore scale
                    scored = sorted(score_map.items(), key=lambda x: x[1], reverse=True)

        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]

        # Bloom-style concept tracking: skip branches that add <5% new concepts
        loaded_concepts = set()
        # Seed with root concepts
        root_words = set(re.findall(r'[a-zA-Z]{4,}', root_text.lower()))
        loaded_concepts.update(root_words)

        for name, score in scored:
            node = nodes[name]
            node_tokens = node["lines"] * BUDGET["tokens_per_line"]
            if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                break
            # Check concept novelty before committing to load
            branch_text = read_node(name, _tree=tree)
            branch_concepts = set(re.findall(r'[a-zA-Z]{3,}', branch_text.lower()))
            new_concepts = branch_concepts - loaded_concepts
            if len(branch_concepts) > 10 and len(new_concepts) / len(branch_concepts) < 0.05:
                continue  # <5% new concepts, skip this branch
            loaded_concepts.update(branch_concepts)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens

        # C3: Auto-preload top predictions that weren't already loaded
        loaded_names = {n for n, _ in loaded}
        if prediction_scores:
            top_preds = sorted(prediction_scores.items(), key=lambda x: x[1], reverse=True)
            for pred_name, pred_score in top_preds[:3]:  # max 3 preloads
                if pred_name in loaded_names or pred_name not in nodes:
                    continue
                if pred_score < 0.3:
                    break  # only preload strong predictions
                node = nodes[pred_name]
                node_tokens = node["lines"] * BUDGET["tokens_per_line"]
                if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                    break
                branch_text = read_node(pred_name, _tree=tree)
                if branch_text:
                    loaded.append((pred_name, branch_text))
                    loaded_tokens += node_tokens
                    loaded_names.add(pred_name)
    else:
        ranked = sorted(
            [(n, d) for n, d in nodes.items() if n != "root"],
            key=lambda x: x[1].get("temperature", 0),
            reverse=True,
        )
        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]
        for name, node in ranked[:3]:
            node_tokens = node["lines"] * BUDGET["tokens_per_line"]
            if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                break
            branch_text = read_node(name, _tree=tree)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens

    # Save tree once after all reads (access_count/last_access updated in-place)
    save_tree(tree)

    # P20c: Virtual branches — read-only branches from other repos
    remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
    if remaining_budget > 500 and _m._REPO_PATH:
        virtual = _load_virtual_branches(query or "", remaining_budget)
        for vname, vtext, vtokens in virtual:
            loaded.append((vname, vtext))
            loaded_tokens += vtokens

    # C2: Boot feedback log — record which blind spots were covered
    if blind_spot_concepts and loaded:
        covered = set()
        uncovered = set()
        for a, b, reason in blind_spots:
            pair = f"{a}|{b}"
            loaded_tags = set()
            for _, text in loaded:
                loaded_tags.update(re.findall(r'[a-zA-Z]{3,}', text.lower()))
            if a in loaded_tags and b in loaded_tags:
                covered.add(pair)
            else:
                uncovered.add(pair)
        feedback = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "query": query or "",
            "blind_spots_total": len(blind_spot_concepts),
            "covered": list(covered),
            "uncovered": list(uncovered),
            "branches_loaded": [n for n, _ in loaded],
        }
        feedback_path = (_m._REPO_PATH or _m.MUNINN_ROOT) / ".muninn" / "boot_feedback.json"
        try:
            import json as _json
            history = []
            if feedback_path.exists():
                history = _json.loads(feedback_path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = [history]
            history.append(feedback)
            history = history[-20:]  # keep last 20 boots
            feedback_path.write_text(_json.dumps(history, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"  [warn] boot feedback: {e}", file=sys.stderr)

    # P19: Dedup branches — skip if NCD similarity > 0.6 (too similar)
    deduped = []
    loaded_texts = []
    for name, text in loaded:
        if name == "root":
            deduped.append((name, text))
            loaded_texts.append(text)
            continue
        is_dup = False
        for prev_text in loaded_texts[-3:]:  # compare last 3 only (O(1) per branch)
            if not text or not prev_text:
                continue
            ncd = _m._ncd(text, prev_text)
            if ncd < 0.4:  # NCD < 0.4 = very similar content
                is_dup = True
                break
        if not is_dup:
            deduped.append((name, text))
            loaded_texts.append(text)

    output = []
    for name, text in deduped:
        output.append(f"=== {name} ===")
        output.append(text)

    # Load latest session .mn if it exists (tail-first if too large)
    sessions_dir = _m._REPO_PATH / ".muninn" / "sessions" if _m._REPO_PATH else _m.MUNINN_ROOT / ".muninn" / "sessions"
    if sessions_dir.exists():
        session_files = sorted(sessions_dir.glob("*.mn"))
        if session_files:
            latest = session_files[-1]
            session_text = latest.read_text(encoding="utf-8")
            remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
            session_tokens = token_count(session_text)

            if session_tokens <= remaining_budget:
                output.append(f"=== last_session ({latest.stem}) ===")
                output.append(session_text)
                loaded_tokens += session_tokens
            elif remaining_budget > 200:
                max_chars = remaining_budget * 3
                session_lines = session_text.split("\n")
                tail_lines = []
                char_count = 0
                for line in reversed(session_lines):
                    if char_count + len(line) + 1 > max_chars:
                        break
                    tail_lines.append(line)
                    char_count += len(line) + 1
                tail_lines.reverse()
                if tail_lines:
                    output.append(f"=== last_session ({latest.stem}) [tail] ===")
                    output.append("\n".join(tail_lines))
                    loaded_tokens += token_count("\n".join(tail_lines))

            # P22: Search session index for relevant past sessions
            if query and _m._REPO_PATH:
                remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
                if remaining_budget > 500:
                    _load_relevant_sessions(
                        query, sessions_dir, latest.name, remaining_budget, output
                    )

    # P18: Surface known error fixes if query matches
    if query and _m._REPO_PATH:
        error_hints = _surface_known_errors(_m._REPO_PATH, query)
        if error_hints:
            output.append("\n=== known_fixes ===")
            output.append(error_hints)

    # H3: Surface Huginn insights at boot
    if _m._REPO_PATH:
        huginn_output = _surface_insights_for_boot(query)
        if huginn_output:
            output.append("\n" + huginn_output)

    # V8B: Active sensing — info-theoretic disambiguation (Yang et al. 2016)
    # a* = argmax_a I(X;Y|a) — when uncertain, identify the concept that
    # would best disambiguate the top candidate branches.
    # Only triggered when top 3 scores are within 10% of each other.
    _v8b_hint = ""
    try:
        if query and len(scored) >= 3:
            _top3 = scored[:3]
            _spread = _top3[0][1] - _top3[2][1]
            if _spread < 0.10 * _top3[0][1] and _top3[0][1] > 0.01:
                # High uncertainty — find the most discriminative concept
                import math as _math
                _concept_dist = {}  # concept -> set of branches containing it (among top 3)
                for _sn, _ in _top3:
                    for _tag in nodes.get(_sn, {}).get("tags", []):
                        _concept_dist.setdefault(_tag, set()).add(_sn)
                # Best concept = one that splits top 3 most evenly (max entropy)
                _best_concept, _best_entropy = "", 0.0
                for _c, _branches_with in _concept_dist.items():
                    _p = len(_branches_with) / 3.0
                    if 0 < _p < 1:
                        _h = -_p * _math.log2(_p) - (1 - _p) * _math.log2(1 - _p)
                        if _h > _best_entropy:
                            _best_entropy = _h
                            _best_concept = _c
                if _best_concept:
                    _v8b_hint = _best_concept
    except Exception as e:
        print(f"  [warn] V8B active sensing: {e}", file=sys.stderr)

    # P36: Save boot manifest for feedback loop
    if _m._REPO_PATH:
        try:
            boot_manifest = {
                "branches": [name for name, _ in deduped if name != "root"],
                "query": query or "",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if _v8b_hint:
                boot_manifest["v8b_clarify"] = _v8b_hint
            manifest_path = _m._REPO_PATH / ".muninn" / "last_boot.json"
            manifest_path.write_text(json.dumps(boot_manifest), encoding="utf-8")
        except OSError:
            pass

    # KIComp: density scoring — drop low-information lines if over budget
    full_text = "\n".join(output)
    total_tokens = token_count(full_text)
    if total_tokens > BUDGET["max_loaded_tokens"]:
        full_text = _m._kicomp_filter(full_text, BUDGET["max_loaded_tokens"])

    # A8: Prune warning — warn if many dead branches
    try:
        branches = {k: v for k, v in nodes.items() if k != "root"}
        if branches:
            cold_count = sum(1 for v in branches.values()
                             if _ebbinghaus_recall(v) < 0.1)
            pct = cold_count / len(branches) * 100
            if pct > 45:
                full_text += (f"\n\n[MUNINN] {pct:.0f}% branches are cold "
                              f"({cold_count}/{len(branches)}). "
                              f"Consider running: muninn prune --force")
    except Exception:
        pass

    return full_text


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
        try:
            from .mycelium import Mycelium
        except ImportError:
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
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        try:
            from .mycelium import Mycelium
        except ImportError:
            from mycelium import Mycelium
        m = Mycelium(repo)
    except Exception:
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

    return "\n".join(lines)


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
            try:
                from .mycelium import Mycelium
            except ImportError:
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


# ── SLEEP CONSOLIDATION (Wilson & McNaughton 1994) ───────────────

def _sleep_consolidate(cold_branches: list[tuple[str, dict]], nodes: dict,
                       ncd_threshold: float = 0.6) -> list[tuple[str, str]]:
    """Consolidate similar cold branches into single dense branches.

    Like the brain during sleep: episodic memories (sessions) get merged
    into semantic memory (general rules). Uses NCD to find similar branches,
    then merges + re-compresses with the existing pipeline (dedup,
    contradiction resolution, L10, L11). Zero API cost.

    Args:
        cold_branches: list of (name, node_dict) for cold branches
        nodes: full tree nodes dict (for in-place mutation)
        ncd_threshold: max NCD distance to consider branches similar (0-1)

    Returns:
        list of (merged_name, merged_content) for newly created branches
    """
    if len(cold_branches) < 2:
        return []

    # P8: Cap to top-20 coldest branches by recall score to avoid O(n^2) NCD
    MAX_NCD_BRANCHES = 20
    if len(cold_branches) > MAX_NCD_BRANCHES:
        cold_branches = sorted(cold_branches,
                               key=lambda x: _ebbinghaus_recall(x[1]))[:MAX_NCD_BRANCHES]

    # 1. Read all cold branch contents
    contents = {}
    for name, node in cold_branches:
        filepath = _m.TREE_DIR / node["file"]
        try:
            contents[name] = filepath.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            pass

    if len(contents) < 2:
        return []

    # 2. Compute NCD pairwise and group similar branches
    names = list(contents.keys())
    merged_into = {}  # name -> group_leader
    groups = {}  # leader -> [members]

    for i in range(len(names)):
        if names[i] in merged_into:
            continue
        leader = names[i]
        groups[leader] = [leader]
        for j in range(i + 1, len(names)):
            if names[j] in merged_into:
                continue
            # Check similarity against ALL existing group members, not just leader
            all_similar = all(
                _m._ncd(contents[m], contents[names[j]]) < ncd_threshold
                for m in groups[leader]
            )
            if all_similar:
                groups[leader].append(names[j])
                merged_into[names[j]] = leader

    # 3. Consolidate each group with 2+ members
    results = []
    for leader, members in groups.items():
        if len(members) < 2:
            continue

        # Concatenate all branch contents
        combined = "\n".join(contents[m] for m in members)

        # Line-level dedup (exact + near)
        seen_lines = set()
        deduped = []
        for line in combined.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in seen_lines:
                continue
            seen_lines.add(stripped)
            deduped.append(line)
        combined = "\n".join(deduped)

        # Run through existing compression pipeline (free, no API)
        combined = _m._resolve_contradictions(combined)
        combined = _m._cue_distill(combined)
        combined = _m._extract_rules(combined)

        # Name the consolidated branch (strip existing _consolidated suffix to avoid stacking)
        base_leader = re.sub(r'(_consolidated)+$', '', leader)
        merged_name = f"{base_leader}_consolidated"

        # Write the consolidated file
        merged_file = f"{merged_name}.mn"
        merged_path = _m.TREE_DIR / merged_file
        merged_path.write_text(combined, encoding="utf-8")

        # Collect tags from all merged branches
        all_tags = set()
        for m in members:
            node = nodes.get(m, {})
            all_tags.update(node.get("tags", []))

        # Prioritize sole-carrier tags (V9B protection: don't lose unique concepts)
        # Count how many OTHER branches (not in this merge group) carry each tag
        _other_branches = {n: nd for n, nd in nodes.items()
                          if n not in members and n != "root" and nd.get("type") == "branch"}
        _sole_tags = []  # tags only carried by members of this merge
        _common_tags = []
        for t in sorted(all_tags):
            carried_elsewhere = any(t in _ob.get("tags", []) for _ob in _other_branches.values())
            if not carried_elsewhere:
                _sole_tags.append(t)
            else:
                _common_tags.append(t)
        # Sole-carrier tags first, then fill remaining slots with common tags
        _final_tags = _sole_tags + [t for t in _common_tags if t not in _sole_tags]

        # Create consolidated node in tree
        nodes[merged_name] = {
            "type": "branch",
            "file": merged_file,
            "lines": len(combined.split("\n")),
            "max_lines": 150,
            "tags": _final_tags[:max(10, len(_sole_tags))],  # keep ALL sole-carriers even if >10
            "temperature": 0.1,  # warm enough to not get immediately pruned
            "access_count": max(nodes.get(m, {}).get("access_count", 0) for m in members),  # X9: max not sum, prevents immortalization
            "last_access": max(nodes.get(m, {}).get("last_access", time.strftime("%Y-%m-%d")) for m in members),
            "created": time.strftime("%Y-%m-%d"),
            "usefulness": round(max(nodes.get(m, {}).get("usefulness", 0.5) for m in members), 3),
            "td_value": round(max(nodes.get(m, {}).get("td_value", 0.5) for m in members), 4),
            "fisher_importance": round(max(nodes.get(m, {}).get("fisher_importance", 0.0) for m in members), 4),
        }

        # Add as child of root
        if "children" in nodes.get("root", {}):
            nodes["root"]["children"].append(merged_name)

        # Remove old branches
        for m in members:
            node = nodes.get(m)
            if node:
                old_path = _m.TREE_DIR / node["file"]
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
            if m in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(m)
            nodes.pop(m, None)

        orig_lines = sum(len(contents[m].split("\n")) for m in members)
        results.append((merged_name, combined))
        print(f"  CONSOLIDATED {len(members)} branches -> {merged_name}: "
              f"{orig_lines} -> {len(combined.split(chr(10)))} lines")

    return results


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


def _surface_insights_for_boot(query: str = "") -> str:
    """H3: Surface top 3 relevant insights at boot time."""
    insights = huginn_think(query=query, top_n=3)
    if not insights:
        return ""
    lines = ["=== huginn_insights ==="]
    for ins in insights:
        lines.append(f"  {ins['formatted']}")
    return "\n".join(lines)


# ── PRUNE (R4) ───────────────────────────────────────────────────

def _light_prune():
    """B15: Fast auto-prune for hooks — kills dead + dust only.

    No L9 recompression, no sleep consolidation, no H1/H2 dreams.
    Just Ebbinghaus recall check + B14 dust removal + file cleanup.
    Runs in < 1s even on 2000+ branches.
    """
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

    branches = {n: d for n, d in nodes.items() if n != "root"}
    if not branches:
        return 0

    removed = 0
    for name in list(branches.keys()):
        node = branches[name]
        recall = _ebbinghaus_recall(node)
        lines = node.get("lines", 0)
        temp = node.get("temperature", 0)

        # Dead: forgotten (R < 0.05) OR dust (<=3 lines and cold)
        is_dead = recall < 0.05
        is_dust = lines <= 3 and temp < 0.3

        if is_dead or is_dust:
            # Delete file
            branch_file = _m.TREE_DIR / node.get("file", "")
            if branch_file.exists():
                branch_file.unlink()
            # Remove from tree
            del nodes[name]
            root_children = nodes.get("root", {}).get("children", [])
            if name in root_children:
                root_children.remove(name)
            removed += 1

    if removed > 0:
        save_tree(tree)
        print(f"  LIGHT PRUNE: removed {removed} dead/dust branches ({len(nodes)-1} remaining)", file=sys.stderr)
    return removed


def _auto_backup_tree():
    """A7: Auto-backup tree before destructive prune.

    Creates .muninn/backups/prune_before_<timestamp>.tar.gz
    """
    if not _m._REPO_PATH:
        return
    backup_dir = _m._REPO_PATH / ".muninn" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"prune_before_{ts}.tar.gz"
    try:
        import tarfile
        with tarfile.open(str(backup_path), "w:gz") as tar:
            tar.add(str(_m.TREE_DIR), arcname="tree")
        print(f"  A7: Tree backed up to {backup_path.name}", file=sys.stderr)
        # Keep only last 5 backups
        backups = sorted(backup_dir.glob("prune_before_*.tar.gz"))
        for old in backups[:-5]:
            old.unlink()
    except Exception as e:
        print(f"  A7: Backup failed: {e}", file=sys.stderr)


def prune(dry_run: bool = True):
    """R4: promote hot, demote cold, kill dead. Uses temperature score."""
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

    # A7: Auto-backup before destructive prune
    if not dry_run:
        _auto_backup_tree()

    branches = {n: d for n, d in nodes.items() if n != "root"}
    if not branches:
        print("  No branches to prune.")
        return

    print(f"=== MUNINN PRUNE (R4) === {'[DRY RUN]' if dry_run else ''}")
    print(f"  Branches: {len(branches)}")
    print()

    # V9B: Reed-Solomon redundancy (Reed & Solomon 1960)
    # Compute concept redundancy: how many branches carry each concept.
    # Branches that are sole carriers (redundancy=1) of concepts get protection.
    # d_min >= n-k+1: minimum distance determines correction capability.
    _concept_carriers = {}  # concept -> set of branch names
    for bname, bnode in branches.items():
        for tag in bnode.get("tags", []):
            _concept_carriers.setdefault(tag, set()).add(bname)
    # Fragile concepts: carried by only 1 branch (redundancy=1, no error correction)
    _fragile_branches = set()  # branches that are sole carriers
    for concept, carriers in _concept_carriers.items():
        if len(carriers) == 1:
            _fragile_branches.update(carriers)

    # I2: Competitive Suppression (Perelson 1989)
    # Similar branches suppress each other's recall — the weaker one dies faster.
    # recall_eff_i = recall_i - alpha * sum(NCD_sim(i,j) * recall_j) for NCD < 0.4
    _i2_alpha = 0.1
    _branch_recalls = {}
    for bname, bnode in branches.items():
        _branch_recalls[bname] = _ebbinghaus_recall(bnode)
    # I2: Only apply competitive suppression to non-hot branches (recall < 0.4).
    # Hot branches won't be pruned anyway — O(n²) NCD on all branches is catastrophic
    # (486s on 2106 branches = 4.4M zlib calls). Pre-filter to at-risk branches only.
    _suppression = {b: 0.0 for b in branches}
    _atrisk = [b for b in branches if _branch_recalls[b] < 0.4]
    if 2 <= len(_atrisk) <= 500:  # skip if too few or too many (safety cap)
        _branch_content = {}
        for bname in _atrisk:
            bnode = branches[bname]
            fpath = _m.TREE_DIR / bnode.get("file", "")
            if fpath.is_file():
                try:
                    _branch_content[bname] = fpath.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    _branch_content[bname] = ""
        _atrisk_names = list(_branch_content.keys())
        for i in range(len(_atrisk_names)):
            bi = _atrisk_names[i]
            if not _branch_content.get(bi):
                continue
            for j in range(i + 1, len(_atrisk_names)):
                bj = _atrisk_names[j]
                if not _branch_content.get(bj):
                    continue
                ncd = _m._ncd(_branch_content[bi], _branch_content[bj])
                if ncd < 0.4:  # very similar
                    sim = 1.0 - ncd
                    _suppression[bi] += sim * _branch_recalls.get(bj, 0)
                    _suppression[bj] += sim * _branch_recalls.get(bi, 0)
    # Apply suppression to effective recall
    _effective_recall = {}
    for bname in branches:
        _effective_recall[bname] = max(0.0,
            _branch_recalls[bname] - _i2_alpha * _suppression[bname])

    # I3: Negative Selection (Forrest 1994)
    # Detect anomalous branches by comparing to median profile.
    # Anomalies (too long, zero facts, extreme density) get demoted to cold.
    _i3_anomalies = set()
    if len(branches) >= 3:
        import statistics
        _line_counts = []
        _fact_ratios = []
        for bname, bnode in branches.items():
            lc = bnode.get("lines", 0)
            # Compute fact ratio from tags in content
            fpath = _m.TREE_DIR / bnode.get("file", "")
            tagged = 0
            total = max(1, lc)
            if fpath.is_file():
                try:
                    text = fpath.read_text(encoding="utf-8")
                    for tl in text.split("\n"):
                        st = tl.strip()
                        if st and st[:2] in ("D>", "B>", "F>", "E>", "A>"):
                            tagged += 1
                    lc = len(text.split("\n"))
                    total = max(1, lc)
                except (OSError, UnicodeDecodeError):
                    pass
            _line_counts.append(lc)
            _fact_ratios.append(tagged / total)

        _med_lines = statistics.median(_line_counts) if _line_counts else 10
        _med_facts = statistics.median(_fact_ratios) if _fact_ratios else 0.3

        for idx, (bname, bnode) in enumerate(branches.items()):
            lc = _line_counts[idx] if idx < len(_line_counts) else 0
            fr = _fact_ratios[idx] if idx < len(_fact_ratios) else 0
            dist = 0.0
            if _med_lines > 0:
                dist += abs(lc - _med_lines) / max(_med_lines, 1)
            if _med_facts > 0:
                dist += abs(fr - _med_facts) / max(_med_facts, 0.01)
            elif fr == 0:
                pass  # zero facts when median is also zero = not anomalous
            if dist > 2.0:
                _i3_anomalies.add(bname)

    hot, cold, dead = [], [], []

    for name, node in branches.items():
        temp = node.get("temperature", 0)
        acc = node.get("access_count", 0)
        recall = _effective_recall[name]  # I2: use suppressed recall
        days_ago = _days_since(node.get("last_access", time.strftime("%Y-%m-%d")))

        # I3: Anomalous branches get demoted to cold regardless of recall
        if name in _i3_anomalies and recall >= 0.15:
            cold.append((name, days_ago))
            print(f"  I3 ANOMALY {name}: R={recall:.2f} demoted to cold (abnormal profile)")
            continue

        # Spaced repetition thresholds (Settles 2016):
        # R > 0.4 = hot (strong recall), R < 0.05 = dead (forgotten)
        # 0.05 <= R < 0.15 = cold (fading, candidate for re-compression)
        if recall >= 0.4:
            hot.append((name, temp))
            print(f"  HOT  {name}: R={recall:.2f} t={temp:.2f} h={7*(2**min(acc,10)):.0f}d acc={acc}")
        elif recall < 0.05:
            # V9B: Protect fragile branches (sole carriers of unique concepts)
            if name in _fragile_branches:
                cold.append((name, days_ago))  # demote to cold instead of dead
                print(f"  V9B  {name}: R={recall:.3f} PROTECTED (sole carrier) -> cold")
            else:
                dead.append((name, days_ago))
                print(f"  DEAD {name}: R={recall:.3f} t={temp:.2f} cold {days_ago}d")
        elif recall < 0.15:
            cold.append((name, days_ago))
            print(f"  COLD {name}: R={recall:.2f} t={temp:.2f} cold {days_ago}d")
        else:
            print(f"  OK   {name}: R={recall:.2f} t={temp:.2f} acc={acc}")

    # B14: Dust branch cleanup — branches with <= 3 lines are noise
    # (minimum viable content = 4+ lines, below that no useful information)
    dust = []
    for name, node in list(branches.items()):
        if name in dict(dead):
            continue  # already dead, will be handled below
        if name in _fragile_branches:
            continue  # V9B: sole carriers protected even if small
        lines = node.get("lines", 0)
        if lines <= 3 and node.get("temperature", 0) < 0.3:
            dust.append(name)
    if dust:
        for name in dust:
            # Move from cold/hot to dead
            dead.append((name, _days_since(nodes[name].get("last_access", time.strftime("%Y-%m-%d")))))
            # Remove from cold list if present
            cold[:] = [(n, d) for n, d in cold if n != name]
        print(f"  B14 DUST: {len(dust)} branches <= 3 lines -> dead ({', '.join(dust[:10])})")

    recompressed = 0
    if not dry_run:
        # Optimal Forgetting: re-compress cold branches with L9
        # Cold branches get deeper compression before potential deletion
        for name, days in cold:
            if name not in nodes:
                continue  # H1 fix: may have been removed by _sleep_consolidate
            node = nodes[name]
            filepath = _m.TREE_DIR / node["file"]
            if not filepath.exists():
                continue
            content = filepath.read_text(encoding="utf-8")
            original_lines = len(content.split("\n"))
            # Apply L9 (LLM compression) if branch is large enough
            compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
            if compressed != content:
                filepath.write_text(compressed, encoding="utf-8")
                new_lines = len(compressed.split("\n"))
                node["lines"] = new_lines
                recompressed += 1
                print(f"  RE-COMPRESSED {name}: {original_lines} -> {new_lines} lines")

        # H10: Snapshot tree before sleep consolidation (for rollback)
        _pre_consolidate_snapshot = json.dumps(tree, indent=2, ensure_ascii=False)

        # Sleep Consolidation (Wilson & McNaughton 1994)
        # Merge similar cold branches into single dense branches
        cold_branch_data = [(name, nodes[name]) for name, _ in cold if name in nodes]
        try:
            consolidated = _sleep_consolidate(cold_branch_data, nodes)
        except Exception as e:
            # H10: Rollback tree to pre-consolidation state
            print(f"  H10 ROLLBACK: consolidation failed ({e}), restoring tree snapshot")
            tree.update(json.loads(_pre_consolidate_snapshot))
            consolidated = 0

        # MYCELIUM DECAY — clean dead connections during prune (like the tree)
        # decay() was never called before, causing unbounded growth (14.9M edges, 1.3GB).
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            try:
                from .mycelium import Mycelium
            except ImportError:
                from mycelium import Mycelium
            m_decay = Mycelium(_m._REPO_PATH or Path("."))
            dead_edges = m_decay.decay()
            if dead_edges > 0:
                m_decay.save()
                print(f"  MYCELIUM DECAY: {dead_edges} dead connections removed")
            else:
                print(f"  MYCELIUM DECAY: 0 dead (all connections healthy)")
        except Exception as e:
            print(f"  MYCELIUM DECAY skipped: {e}", file=sys.stderr)

        # H1: Mode trip — psilocybine exploration during sleep
        # Create dream connections between distant clusters (BARE Wave model)
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            try:
                from .mycelium import Mycelium
            except ImportError:
                from mycelium import Mycelium
            m = Mycelium(_m._REPO_PATH or Path("."))
            trip_result = m.trip(intensity=0.5, max_dreams=15)
            if trip_result["created"] > 0:
                m.save()
                print(f"  H1 TRIP: {trip_result['created']} dream connections "
                      f"(entropy {trip_result['entropy_before']:.2f} -> "
                      f"{trip_result['entropy_after']:.2f})")
            # H2: Dream/synthesis — generate insights during sleep
            dream_insights = m.dream()
            if dream_insights:
                print(f"  H2 DREAM: {len(dream_insights)} insights generated")
                for ins in dream_insights[:3]:
                    print(f"    [{ins['type']}] {ins['text'][:80]}")
        except Exception as e:
            print(f"  H1/H2 skipped: {e}", file=sys.stderr)

        # V9A+: Fact-level regeneration (Shomrat & Levin 2013)
        # Before deleting dead branches, extract tagged facts (D>/B>/F>/E>/A>)
        # from the dying .mn file and inject them into the closest surviving branch.
        # The content survives, not just the tag labels.
        _regen_tag_re = re.compile(r'^[DBFEA]>\s')
        _regen_facts_total = 0
        _regen_tags_total = 0
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            try:
                from .mycelium import Mycelium
            except ImportError:
                from mycelium import Mycelium
            m_regen = Mycelium(_m._REPO_PATH or Path("."))
            # H1 fix: compute surviving from CURRENT nodes (after sleep_consolidate)
            dead_set = {n for n, _ in dead}
            surviving = {n for n in nodes if n != "root" and n not in dead_set}
            # Pre-cache survivor tags to avoid repeated set() construction (M3 fix)
            _surv_tags = {s: set(nodes[s].get("tags", [])) for s in surviving}

            for name, days in dead:
                if name not in nodes:
                    continue
                try:
                    dead_node = nodes[name]
                    dead_tags = set(dead_node.get("tags", []))
                    dead_file = dead_node.get("file", "")
                    if not dead_file:
                        continue  # M1 fix: no file key
                    dead_filepath = _m.TREE_DIR / dead_file

                    # --- Step 1: Read .mn file and extract tagged facts ---
                    facts = []
                    if dead_filepath.is_file():
                        try:
                            content = dead_filepath.read_text(encoding="utf-8")
                            for line in content.split("\n"):
                                stripped = line.strip()
                                if _regen_tag_re.match(stripped):
                                    facts.append(stripped)
                        except (OSError, UnicodeDecodeError):
                            pass  # fallback to tag-only diffusion

                    # --- Step 2: Find best surviving branch ---
                    best_survivor = None
                    best_score = -1

                    # Strategy A: mycelium proximity
                    for dtag in list(dead_tags)[:5]:
                        related = m_regen.get_related(dtag, top_n=10)
                        for concept, strength in related:
                            for sname in surviving:
                                if sname not in nodes:
                                    continue  # H2 fix: skip stale refs
                                if concept in _surv_tags.get(sname, set()):
                                    if strength > best_score:
                                        best_score = strength
                                        best_survivor = sname

                    # Strategy B: most tags in common
                    if best_survivor is None and dead_tags:
                        max_overlap = 0
                        for sname in surviving:
                            if sname not in nodes:
                                continue
                            overlap = len(dead_tags & _surv_tags.get(sname, set()))
                            if overlap > max_overlap:
                                max_overlap = overlap
                                best_survivor = sname

                    # Strategy C: most recently accessed surviving branch
                    if best_survivor is None:
                        latest_access = ""
                        for sname in surviving:
                            if sname not in nodes:
                                continue
                            la = nodes[sname].get("last_access", "")
                            if la > latest_access:
                                latest_access = la
                                best_survivor = sname

                    if best_survivor is None:
                        continue  # no survivors at all

                    # --- Step 3: Inject facts into survivor .mn ---
                    if facts:
                        surv_file = nodes[best_survivor].get("file", "")
                        if not surv_file:
                            continue  # M1 fix
                        survivor_filepath = _m.TREE_DIR / surv_file
                        survivor_content = ""
                        if survivor_filepath.is_file():
                            try:
                                survivor_content = survivor_filepath.read_text(encoding="utf-8")
                            except (OSError, UnicodeDecodeError):
                                pass

                        # Dedup: don't inject facts already present in survivor
                        existing_lines = set(l.strip() for l in survivor_content.split("\n"))
                        new_facts = [f for f in facts if f not in existing_lines]

                        if new_facts:
                            # Build REGEN section
                            regen_header = f"## REGEN: {name} ({time.strftime('%Y-%m-%d')})"
                            # Idempotency: if this REGEN header exists, skip
                            if regen_header not in survivor_content:
                                regen_block = "\n" + regen_header + "\n" + "\n".join(new_facts) + "\n"
                                combined = survivor_content.rstrip() + regen_block

                                # Budget check: if > 200 lines, recompress with L10+L11
                                if combined.count("\n") > 200:
                                    combined = _m._cue_distill(combined)
                                    combined = _m._extract_rules(combined)

                                survivor_filepath.write_text(combined, encoding="utf-8")
                                _regen_facts_total += len(new_facts)
                                # Update hash + line count so boot() P34 integrity check passes
                                nodes[best_survivor]["hash"] = compute_hash(survivor_filepath)
                                nodes[best_survivor]["lines"] = combined.count("\n") + 1

                    # --- Step 4: Tag diffusion (original V9A logic, always runs) ---
                    if dead_tags:
                        for dtag in list(dead_tags)[:5]:
                            related = m_regen.get_related(dtag, top_n=5)
                            for concept, strength in related:
                                for sname in surviving:
                                    if sname not in nodes:
                                        continue
                                    stags = _surv_tags.get(sname, set())
                                    if concept in stags and dtag not in stags:
                                        nodes[sname].setdefault("tags", []).append(dtag)
                                        _surv_tags[sname].add(dtag)  # update cache
                                        _regen_tags_total += 1
                                        break

                except (KeyError, TypeError, OSError) as e:
                    print(f"  V9A+ regen skipped for {name}: {e}", file=sys.stderr)
                    continue  # M7 fix: per-branch error handling

            if _regen_facts_total > 0 or _regen_tags_total > 0:
                print(f"  V9A+ REGEN: {_regen_facts_total} facts + "
                      f"{_regen_tags_total} tags diffused to survivors")
        except Exception as e:
            import traceback
            print(f"  V9A+ regen failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        for name, days in dead:
            if name not in nodes:
                continue  # may have been consolidated already
            node = nodes[name]
            filepath = _m.TREE_DIR / node["file"]
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    print(f"  WARNING: could not delete {_m._safe_path(filepath)}: {e}", file=sys.stderr)
                    continue  # don't remove node if file still exists
            del nodes[name]
            if name in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(name)
            print(f"  DELETED {name}")

        save_tree(tree)

    print(f"\n  Summary: {len(hot)} hot, {len(cold)} cold "
          f"({recompressed if not dry_run else '?'} recompressed, "
          f"{len(consolidated) if not dry_run else '?'} consolidated), {len(dead)} dead")


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


def doctor():
    """Pre-flight environment check — runs in <5s, green/red per check."""
    print("=== MUNINN DOCTOR ===\n")
    ok_count = 0
    fail_count = 0

    def _ok(label, detail=""):
        nonlocal ok_count
        ok_count += 1
        print(f"  [OK] {label}" + (f" — {detail}" if detail else ""))

    def _fail(label, detail=""):
        nonlocal fail_count
        fail_count += 1
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))

    def _warn(label, detail=""):
        print(f"  [WARN] {label}" + (f" — {detail}" if detail else ""))

    # 1. Python version (>= 3.10)
    v = sys.version_info
    if v >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro}", "need >= 3.10")

    # 2. SQLite version (>= 3.24 for UPSERT, WAL)
    try:
        import sqlite3
        sv = sqlite3.sqlite_version
        if tuple(int(x) for x in sv.split(".")) >= (3, 24):
            _ok(f"SQLite {sv}")
        else:
            _fail(f"SQLite {sv}", "need >= 3.24 for WAL/UPSERT")
    except Exception as e:
        _fail("SQLite", str(e))

    # 3. tiktoken (required for token counting)
    try:
        import tiktoken
        _ok("tiktoken installed")
    except ImportError:
        _fail("tiktoken missing", "pip install tiktoken")

    # 4. cryptography (optional — for AES-256)
    try:
        from cryptography.fernet import Fernet
        _ok("cryptography installed (AES-256 ready)")
    except ImportError:
        _warn("cryptography not installed", "pip install cryptography (needed for AES-256)")

    # 5. anthropic (optional — for L9)
    try:
        import anthropic
        _ok("anthropic installed (L9 ready)")
    except ImportError:
        _warn("anthropic not installed", "pip install anthropic (optional, for L9)")

    # 6. .muninn directory
    repo = _m._REPO_PATH or Path(".").resolve()
    muninn_dir = repo / ".muninn"
    if muninn_dir.exists():
        _ok(f".muninn/ exists ({repo.name})")
    else:
        _fail(f".muninn/ missing in {repo}", "run: muninn init")

    # 7. Write permissions
    if muninn_dir.exists():
        try:
            test_file = muninn_dir / ".doctor_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            _ok("Write permissions OK")
        except Exception as e:
            _fail("Write permissions", str(e))

    # 8. tree.json exists and is valid JSON
    tree_path = muninn_dir / "tree" / "tree.json" if muninn_dir.exists() else None
    if tree_path and tree_path.exists():
        try:
            data = json.loads(tree_path.read_text(encoding="utf-8"))
            n_nodes = len(data.get("nodes", {}))
            _ok(f"tree.json valid ({n_nodes} nodes)")
        except Exception as e:
            _fail("tree.json corrupted", str(e))
    elif muninn_dir.exists():
        # Try legacy path
        legacy = repo / "memory" / "tree.json"
        if legacy.exists():
            _ok(f"tree.json found (legacy path)")
        else:
            _warn("tree.json not found", "run: muninn bootstrap <repo>")

    # 9. mycelium.db exists and is readable
    db_path = muninn_dir / "mycelium.db" if muninn_dir.exists() else None
    if db_path and db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            # Try both schemas: edges (SQLite tier3) or connections (legacy)
            try:
                count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            except sqlite3.OperationalError:
                count = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
            conn.close()
            _ok(f"mycelium.db valid ({count:,} connections)")
        except Exception as e:
            _fail("mycelium.db", str(e))
    elif muninn_dir.exists():
        _warn("mycelium.db not found", "run: muninn bootstrap <repo>")

    # 10. Encoding check — scan repo for non-UTF8 files that could crash boot
    if muninn_dir.exists():
        bad_files = []
        scan_dirs = [muninn_dir / "tree", muninn_dir / "sessions"]
        for d in scan_dirs:
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.suffix in (".mn", ".json"):
                    try:
                        f.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, PermissionError):
                        bad_files.append(str(f.name))
        if bad_files:
            _fail(f"Encoding issues in {len(bad_files)} file(s)", ", ".join(bad_files[:5]))
        else:
            _ok("All .mn/.json files are valid UTF-8")

    # 11. Disk space (warn if < 500MB free)
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(repo))
        free_mb = free // (1024 * 1024)
        if free_mb > 500:
            _ok(f"Disk space: {free_mb:,} MB free")
        else:
            _warn(f"Disk space low: {free_mb} MB free", "< 500 MB")
    except Exception:
        pass  # Not critical

    # 12. RAM check (warn if < 512MB available)
    try:
        import psutil
        avail = psutil.virtual_memory().available // (1024 * 1024)
        if avail > 512:
            _ok(f"RAM: {avail:,} MB available")
        else:
            _warn(f"RAM low: {avail} MB available")
    except ImportError:
        pass  # psutil optional

    # 13. I4: Sync backend health
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        try:
            from .sync_backend import sync_doctor
        except ImportError:
            from sync_backend import sync_doctor
        sync_result = sync_doctor()
        for check, info in sync_result.items():
            if info.get("ok"):
                _ok(f"Sync {check}", info.get("detail", ""))
            else:
                _fail(f"Sync {check}", info.get("detail", ""))
    except Exception as e:
        _warn(f"Sync check skipped", str(e))

    # Summary
    print(f"\n{'='*40}")
    if fail_count == 0:
        print(f"  ALL GREEN — {ok_count} checks passed")
    else:
        print(f"  {fail_count} FAIL, {ok_count} OK — fix issues above")
    print(f"{'='*40}")

    return {"ok": ok_count, "fail": fail_count}


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
        try:
            from .mycelium import Mycelium
        except ImportError:
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


def _load_relevant_sessions(query: str, sessions_dir: Path, latest_name: str,
                            budget: int, output: list):
    """P22: Search session index and load relevant past sessions at boot."""
    repo_path = sessions_dir.parent.parent  # .muninn/sessions -> repo
    index_path = repo_path / ".muninn" / "session_index.json"
    if not index_path.exists():
        return

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(index, list):
            return
    except (json.JSONDecodeError, OSError):
        return

    # Score each session by concept overlap with query
    query_words = set(re.findall(r'[A-Za-z]{4,}', query.lower()))
    if not query_words:
        return

    scored = []
    for entry in index:
        if entry.get("file") == latest_name:
            continue  # skip the one already loaded
        concepts = set(entry.get("concepts", []))
        overlap = len(query_words & concepts)
        # Also check tagged lines for query words
        for tagged_line in entry.get("tagged", []):
            tagged_words = set(re.findall(r'[A-Za-z]{4,}', tagged_line.lower()))
            overlap += len(query_words & tagged_words) * 0.5
        if overlap > 0:
            scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Load top 2 relevant sessions (if .mn file still exists)
    loaded = 0
    for score, entry in scored[:2]:
        mn_file = sessions_dir / entry.get("file", "")
        if not mn_file.exists():
            continue
        text = mn_file.read_text(encoding="utf-8")
        tokens = token_count(text)
        if tokens > budget:
            continue
        output.append(f"=== relevant_session ({entry.get('file', '?')}, {entry.get('date', '?')}) ===")
        output.append(text)
        budget -= tokens
        loaded += 1

    return loaded


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
        root_path.write_text(new_text, encoding="utf-8")
    else:
        # No R: section yet — append one
        root_text = root_text.rstrip() + f"\n\nR:\n{log_line}\n"
        root_path.write_text(root_text, encoding="utf-8")


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


def _surface_known_errors(repo_path: Path, query: str) -> str:
    """P18: Check if query matches a known error pattern. Returns fix hint or empty."""
    errors_path = repo_path / ".muninn" / "errors.json"
    if not errors_path.exists():
        return ""
    try:
        errors = json.loads(errors_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    query_lower = query.lower()
    hints = []
    for entry in errors:
        if not isinstance(entry, dict) or "error" not in entry or "fix" not in entry:
            continue
        # Check if query words overlap with error text
        # Strip punctuation for matching (e.g. "TypeError:" should match "TypeError")
        error_words = set(re.findall(r'[a-z0-9_]+', entry["error"].lower()))
        query_words = set(re.findall(r'[a-z0-9_]+', query_lower))
        overlap = error_words & query_words
        if len(overlap) >= 2:  # at least 2 word match (1 was too noisy)
            hints.append(f"KNOWN: {entry['error']} -> FIX: {entry['fix']}")
    return "\n".join(hints[:3])  # max 3 hints


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
        mn_path.write_text(new_content, encoding="utf-8")

        # Update metadata
        nodes[live_name]["hash"] = compute_hash(mn_path)
        nodes[live_name]["lines"] = len(new_content.split("\n"))

        save_tree(tree)

        # Feed mycelium with the fact's concepts
        try:
            if _m._CORE_DIR not in sys.path:
                sys.path.insert(0, _m._CORE_DIR)
            try:
                from .mycelium import Mycelium
            except ImportError:
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


