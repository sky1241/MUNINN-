#!/usr/bin/env python3
"""
Muninn — Moteur de compression memoire LLM.
UNIVERSEL — zero hardcode projet. Fonctionne sur n'importe quel repo.

Pipeline: L0 (tool strip) + L1-L7 (regex) + L10-L11 (Carmack) + L9 (LLM, optional).
25 filtres au total, 11 couches de compression.

Usage:
    python muninn.py bootstrap <repo-path>      # Cold start: nourrit le mycelium
    python muninn.py scan <repo-path>           # Scanne un repo, genere codebook local
    python muninn.py compress <fichier>         # Compresse avec universel + mycelium
    python muninn.py tree <fichier>             # Construit l'arbre L-system
    python muninn.py status                     # Etat de l'arbre
    python muninn.py boot [query]               # Charge root + branches pertinentes
    python muninn.py prune [--force]            # Elagage R4
    python muninn.py decode <fichier>           # Decompresse
    python muninn.py feed [--history]           # Nourrit le mycelium depuis transcripts
    python muninn.py verify <fichier>          # Verifie qualite compression (facts, ratio)
"""
__version__ = "0.9.1"

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MUNINN_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(MUNINN_ROOT / "engine" / "core"))
from tokenizer import count_tokens, token_count
try:
    from sentiment import score_sentiment, score_session
    _HAS_SENTIMENT = True
except ImportError:
    _HAS_SENTIMENT = False


# ── COMPRESSION RULES LOADER ────────────────────────────────────
# Two sources of compression rules:
# 1. Universal rules (hardcoded, BPE-native English)
# 2. Mycelium (living codebook, per-repo, grows with usage)

# Universal compression: state words -> short English (BPE-native)
UNIVERSAL_RULES = {
    # French -> English compact (1 token each)
    "COMPLET": "done", "COMPLETE": "done", "COMPLETED": "done", "completed": "done", "complet": "done",
    "VALIDE": "done", "VALIDÉ": "done", "FIXE": "done", "FIXÉ": "done",
    "EN COURS": "wip", "en cours": "wip",
    "ECHOUE": "fail", "ECHOUÉ": "fail", "FAILED": "fail",
    "EN ATTENTE": "todo", "PENDING": "todo",
    "DÉCISION": "decided", "DECISION": "decided",
    # Markdown stripping
    "## ": "", "**": "", "- ": "",
}

# ── L9 PROMPT (single source of truth) ──────────────────────────
# Research-backed design (Chain of Density, anti-summarization framing):
# - "EXTRACT+RESTATE" not "compress" (avoids summarization prior)
# - temperature=0 (factual precision over creative paraphrase)
# - Few-shot example (teaches by showing, not telling)
# - "identify all facts first" (CoD-inspired enumeration before output)
# - stop_reason check (detects silent truncation)
# - max_tokens * 3/4 (pre-compressed text needs more room than raw)
_L9_SYSTEM = (
    "You extract and restate facts for LLM memory. "
    "A future LLM loads your output as its ONLY context. "
    "NEVER add information not in the input. "
    "When unsure whether to keep or drop: KEEP."
)
_L9_PROMPT = (
    "EXTRACT every fact from the input. RESTATE each in minimal tokens.\n"
    "Drop ONLY: filler adverbs, transitions, repetition, greetings, boilerplate.\n\n"
    "KEEP (non-negotiable): numbers+units, names, identifiers, "
    "decisions+WHY, errors+fixes, code signatures.\n"
    "Tables/lists: preserve structure, compress cell text.\n"
    "Prose: 1 fact/line, use -> = | ~ as connectors, ## headers to group.\n\n"
    "EXAMPLE:\n"
    "IN: The dashboard uses a 12px base font with 1.5rem line height. "
    "Charts render at 60fps on devices with more than 256KB cache. "
    "The Garmin API v3.2 provides heart rate data with 95% accuracy at rest.\n"
    "OUT: dashboard: 12px base, 1.5rem line-height | charts 60fps if cache>256KB "
    "| Garmin API v3.2: HR 95% accuracy@rest\n\n"
    "PROCESS: first mentally identify ALL facts/entities, then write output "
    "covering every one. No preamble.\n\n"
)


def load_codebook(repo_path: Path = None) -> dict:
    """Load compression rules: universal + mycelium (if available)."""
    text_rules = dict(UNIVERSAL_RULES)

    # Load mycelium compression rules (living codebook)
    mycelium_rules = {}
    learned_fillers = []
    learned_abbreviations = {}
    if repo_path:
        try:
            if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            mycelium_rules = m.get_compression_rules()
            learned_fillers = m.get_learned_fillers()
            learned_abbreviations = m.get_learned_abbreviations()
        except ImportError:
            pass

    return {
        "text_rules": text_rules,
        "mycelium_rules": mycelium_rules,
        "learned_fillers": learned_fillers,
        "learned_abbreviations": learned_abbreviations,
    }


# Lazy-loaded global
_CB = None
_CB_REPO = None
_REPO_PATH = None
_SKIP_L9 = False
_CORE_DIR = str(Path(__file__).resolve().parent)

# Secret patterns — applied in compress_file and compress_transcript
_SECRET_PATTERNS = [
    r'ghp_[A-Za-z0-9]{20,}',       # GitHub tokens (classic PAT)
    r'sk-[A-Za-z0-9\-._]{20,}',    # API keys (may contain dashes like sk-ant-api03-...)
    r'AKIA[A-Z0-9]{16}',            # AWS access keys
    r'-----BEGIN\s+\w*\s*PRIVATE KEY-----[\s\S]*?-----END',  # Private keys
    r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',  # OAuth Bearer tokens
    r'token[=:]\s*\S{20,}',         # Generic tokens
    r'password[=:]\s*\S+',          # Passwords
    r'xox[bpsar]-[A-Za-z0-9\-]{10,}',  # B16: Slack tokens (xoxb-, xoxp-, xoxs-, xoxa-, xoxr-)
]


def get_codebook():
    global _CB, _CB_REPO
    if _CB is None or _CB_REPO != _REPO_PATH:
        _CB = load_codebook(_REPO_PATH)
        _CB_REPO = _REPO_PATH
    return _CB


# ── SCAN — auto-generate local codebook (R5) ────────────────────

def scan_repo(repo_path: Path):
    """Scan a repo to auto-generate its local codebook.
    Finds frequent words, entities, paths, numbers and assigns short codes.
    This is R5: codebook local per node."""
    repo_path = repo_path.resolve()
    print(f"=== MUNINN SCAN: {repo_path.name} ===")

    # Collect text from documentation and code files (NOT data files)
    all_text = []
    file_count = 0
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv",
                 "dist", "build", "coverage", ".gradle", ".idea",
                 "data", "output", "cache", "caches", ".muninn"}
    # Only scan human-written files, not data/generated
    for pattern in ["**/*.md", "**/*.txt", "**/*.py", "**/*.rs", "**/*.ts",
                    "**/*.js", "**/*.java", "**/*.c", "**/*.h", "**/*.toml",
                    "**/*.yaml", "**/*.yml", "**/*.cfg", "**/*.ini"]:
        for f in repo_path.glob(pattern):
            parts = f.relative_to(repo_path).parts
            if any(p.startswith(".") or p in skip_dirs for p in parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if len(text) < 50_000:  # skip huge generated files
                    all_text.append(text)
                    file_count += 1
            except (PermissionError, OSError):
                continue

    if not all_text:
        print("  No text files found.")
        return

    corpus = "\n".join(all_text)
    print(f"  Scanned: {file_count} files, {len(corpus)} chars")

    # Extract frequent patterns
    words = re.findall(r'[A-Za-zÀ-ÿ_]{4,}', corpus)
    word_counts = Counter(words)

    # Find entities (capitalized multi-word)
    entities = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', corpus)
    entity_counts = Counter(entities)

    # Find paths
    paths = re.findall(r'[a-z_]+/[a-z_/]+', corpus)
    path_counts = Counter(paths)

    # Find repeated numbers
    numbers = re.findall(r'\d[\d,._]{3,}', corpus)
    number_counts = Counter(numbers)

    # Build local codebook
    encode = {}
    # Short code pools
    t1_codes = list("→←×∂∑∫∇∘∙◆◇▸▹§¶†‡")
    t1_idx = 0
    t2_pool = []
    for a in "abcdefghjkmnprstuvwxyz":
        for b in "0123456789":
            t2_pool.append(f"{a}{b}")
    t2_idx = 0

    def next_code(pattern_len):
        nonlocal t1_idx, t2_idx
        if pattern_len >= 6 and t1_idx < len(t1_codes):
            code = t1_codes[t1_idx]
            t1_idx += 1
            return code
        elif t2_idx < len(t2_pool):
            code = t2_pool[t2_idx]
            t2_idx += 1
            return code
        return None

    # Assign codes by savings (most savings first)
    candidates = []

    # Words to never compress (programming keywords, common stopwords)
    skip_words = {
        "print", "return", "import", "from", "self", "class", "with",
        "true", "false", "none", "elif", "else", "pass", "break",
        "continue", "lambda", "yield", "async", "await", "raise",
        "except", "finally", "assert", "global", "nonlocal", "delete",
        "function", "const", "export", "default", "require", "module",
        "this", "that", "have", "been", "will", "would", "could",
        "pour", "dans", "avec", "sont", "plus", "tout", "mais",
        "also", "just", "like", "make", "some", "each", "when",
        "then", "than", "into", "only", "over", "such", "after",
        "name", "type", "data", "file", "path", "list", "dict",
        "True", "False", "None", "open", "read", "write", "close",
        "args", "kwargs", "init", "main", "test", "spec",
        "string", "number", "boolean", "object", "array",
        "append", "extend", "items", "keys", "values", "update",
        "float", "format", "strip", "split", "join", "replace",
        "encoding", "decode", "encode",
    }

    # Top words (4+ chars, 3+ occurrences, not programming keywords)
    for word, count in word_counts.most_common(100):
        if count >= 3 and len(word) >= 4 and word.lower() not in skip_words:
            savings = count * (len(word) - 2)  # assume 2-char code
            candidates.append((word, count, savings, "word"))

    # Top entities
    for entity, count in entity_counts.most_common(30):
        if count >= 2:
            savings = count * (len(entity) - 2)
            candidates.append((entity, count, savings, "entity"))

    # Top path prefixes
    for path, count in path_counts.most_common(20):
        if count >= 3 and len(path) >= 6:
            savings = count * (len(path) - 3)
            candidates.append((path, count, savings, "path"))

    # Top numbers
    for num, count in number_counts.most_common(20):
        if count >= 2 and len(num) >= 4:
            savings = count * (len(num) - 2)
            candidates.append((num, count, savings, "number"))

    # Sort by savings, assign codes
    candidates.sort(key=lambda x: x[2], reverse=True)

    for pattern, count, savings, ptype in candidates[:50]:  # cap at 50 local codes
        code = next_code(len(pattern))
        if code and savings > 10:
            encode[pattern] = code

    # Markdown formatting (always strip)
    encode.update({"## ": "", "**": "", "- ": ""})

    # Save local codebook
    muninn_dir = repo_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)

    local = {
        "version": "v0.1",
        "repo_name": repo_path.name,
        "domain": repo_path.name.lower().replace("-", "_"),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "entries": len(encode),
        "encode": encode,
    }

    local_path = muninn_dir / "local.json"
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(local, f, ensure_ascii=False, indent=2)

    print(f"  Generated: {len(encode)} local codes")
    print(f"  Saved: {local_path}")

    # Show top 15
    print(f"\n  Top codes:")
    shown = [(p, c) for p, c in encode.items() if p not in ("## ", "**", "- ")]
    for pattern, code in shown[:15]:
        orig = next((c[1] for c in candidates if c[0] == pattern), 0)
        print(f"    '{pattern}' -> '{code}' ({orig}x)")


# ── BUDGET ────────────────────────────────────────────────────────

BUDGET = {
    "root_lines": 100,
    "branch_lines": 150,
    "leaf_lines": 200,
    "tokens_per_line": 16,
    "max_loaded_tokens": 30_000,
    "compression_ratio": 4.6,
}

# ── TREE STRUCTURE ────────────────────────────────────────────────

def _get_tree_dir():
    """Tree lives in target repo's .muninn/tree/, not in Muninn's own memory/."""
    if _REPO_PATH:
        return _REPO_PATH / ".muninn" / "tree"
    return MUNINN_ROOT / "memory"

def _get_tree_meta():
    return _get_tree_dir() / "tree.json"

# Legacy globals — used everywhere, recomputed via properties
TREE_DIR = MUNINN_ROOT / "memory"
TREE_META = TREE_DIR / "tree.json"


def _refresh_tree_paths():
    """Update TREE_DIR/TREE_META globals after _REPO_PATH is set."""
    global TREE_DIR, TREE_META
    TREE_DIR = _get_tree_dir()
    TREE_META = _get_tree_meta()


def init_tree():
    TREE_DIR.mkdir(parents=True, exist_ok=True)

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

    with open(TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)

    (TREE_DIR / "root.mn").write_text(
        "# MUNINN|codebook=v0.1\n", encoding="utf-8"
    )

    print(f"  Tree initialized: {TREE_DIR}")
    return tree


def load_tree():
    if not TREE_META.exists():
        return init_tree()
    try:
        with open(TREE_META, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        # SAFETY: backup corrupted file before re-initializing.
        # Prevents data loss from disk errors or power loss mid-write.
        import shutil
        backup = TREE_META.with_suffix(f".corrupted.{int(time.time())}.json")
        try:
            shutil.copy2(str(TREE_META), str(backup))
            print(f"WARNING: tree.json corrupted ({e}), backed up to {backup.name}", file=sys.stderr)
        except Exception:
            print(f"WARNING: tree.json corrupted ({e}), backup failed", file=sys.stderr)
        return init_tree()


def save_tree(tree):
    """Save tree metadata (atomic write via tempfile + rename)."""
    import tempfile, os
    tree["updated"] = time.strftime("%Y-%m-%d")
    TREE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(TREE_DIR), suffix=".tmp", prefix="tree_"
    )
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(TREE_META))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


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
    fill = node.get("lines", 0) / max(node.get("max_lines", 1), 1)
    recall = _ebbinghaus_recall(node)

    # Fill pressure: nodes near budget get hotter (need split/compress)
    fill_heat = fill ** 2  # quadratic: only significant near full

    # 80% recall-driven, 20% fill pressure
    temp = 0.8 * recall + 0.2 * fill_heat
    return round(temp, 2)


def refresh_tree_metadata(tree: dict):
    """Recompute hash + line count + temperature for all nodes."""
    for name, node in tree["nodes"].items():
        filepath = TREE_DIR / node["file"]
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

    filepath = TREE_DIR / node["file"]
    if not filepath.exists():
        return f"ERROR: file '{filepath}' not found"

    # P34: integrity check — skip corrupted branches
    stored_hash = node.get("hash", "")
    if stored_hash and stored_hash != "00000000":
        actual_hash = compute_hash(filepath)
        if actual_hash != stored_hash:
            print(f"WARNING: {name} hash mismatch (stored={stored_hash}, actual={actual_hash}), skipping", file=sys.stderr)
            return ""  # Empty = will be skipped by boot (no content)

    text = filepath.read_text(encoding="utf-8")

    # B1: Reconsolidation — re-compress cold branches at read time
    # Nader 2000: recalled memory is unstable, must be re-stored.
    # Only triggers if: recall < 0.3 AND last_access > 7 days ago AND text > 3 lines
    # Uses L10 (cue distillation) + L11 (rule extraction) — zero API calls.
    # MUST check BEFORE updating access (otherwise recall jumps to ~1.0)
    recall = _ebbinghaus_recall(node)
    days_ago = _days_since(node.get("access_history", [time.strftime("%Y-%m-%d")])[-1]
                           if node.get("access_history")
                           else node.get("last_access", time.strftime("%Y-%m-%d")))

    node["access_count"] = node.get("access_count", 0) + 1
    node["last_access"] = time.strftime("%Y-%m-%d")
    # A2: append to access_history (cap at 10 most recent)
    history = node.get("access_history", [])
    history.append(time.strftime("%Y-%m-%d"))
    node["access_history"] = history[-10:]  # keep last 10
    if recall < 0.3 and days_ago > 7 and text.count("\n") > 3 and name != "root":
        try:
            original_len = len(text)
            reconsolidated = _resolve_contradictions(text)  # C7: resolve stale numbers
            reconsolidated = _cue_distill(reconsolidated)
            reconsolidated = _extract_rules(reconsolidated)
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


# ── KICOMP DENSITY FILTER ────────────────────────────────────────

def _line_density(line: str) -> float:
    """Score a line's information density (0.0 = noise, 1.0 = dense fact).

    Heuristic inspired by KIComp (Expert Systems 2025).
    High density: numbers, key=value, identifiers, short lines with data.
    Low density: filler, repetition, generic statements.
    """
    if not line.strip():
        return 0.0

    score = 0.0
    s = line.strip()

    # Headers always kept (structural)
    if s.startswith("===") or s.startswith("#"):
        return 1.0

    # Tagged lines get base score from tag
    tag_scores = {"D>": 0.9, "B>": 0.8, "E>": 0.7, "F>": 0.8, "A>": 0.7}
    for tag, tscore in tag_scores.items():
        if s.startswith(tag):
            score = max(score, tscore)
            break

    # Numbers boost density (facts, metrics, dates)
    num_count = len(re.findall(r'\d+', s))
    score += min(0.3, num_count * 0.1)

    # Key=value patterns are dense
    kv_count = len(re.findall(r'[a-zA-Z]+=\S+', s))
    score += min(0.2, kv_count * 0.1)

    # Short lines with data are denser than long narrative
    if len(s) < 80 and num_count > 0:
        score += 0.1

    # Identifiers (commit hashes, file paths, function names)
    if re.search(r'[a-f0-9]{7,}|[\w/]+\.\w{1,4}|\w+\(\)', s):
        score += 0.1

    # Long lines without numbers = probably narrative filler
    if len(s) > 120 and num_count == 0:
        score = min(score, 0.1)  # M1 fix: CAP (not floor) long narrative

    return min(1.0, score)


def _kicomp_filter(text: str, max_tokens: int) -> str:
    """Drop lowest-density lines until text fits in token budget.

    Preserves structural lines (headers, separators) and high-density facts.
    Based on: KIComp (Expert Systems 2025) — information density scoring.
    V6 fix: uses per-line token estimates instead of re-encoding entire text
    per dropped line (was 35s / 1116 calls, now O(n) single pass).
    """
    total_tokens = token_count(text)
    if total_tokens <= max_tokens:
        return text

    lines = text.split("\n")
    # Estimate tokens per line using len//3 (compressed text has shorter words,
    # so BPE produces more tokens per char than the usual len//4 estimate).
    line_tokens = [max(1, len(line) // 3) for line in lines]

    scored = [(i, line, _line_density(line)) for i, line in enumerate(lines)]

    # Sort by density ascending (lowest first = first to drop)
    droppable = [(i, line, d) for i, line, d in scored
                 if d < 0.9 and not line.strip().startswith("===") and not line.startswith("#")]
    droppable.sort(key=lambda x: x[2])

    # Drop lowest-density lines until estimated tokens fit budget
    # Use 95% target to compensate for len//4 underestimation
    target = int(max_tokens * 0.95)
    dropped = set()
    running_tokens = total_tokens
    for idx, _, _ in droppable:
        if running_tokens <= target:
            break
        dropped.add(idx)
        running_tokens -= line_tokens[idx]

    remaining = [(i, line) for i, line in enumerate(lines) if i not in dropped]
    current = "\n".join(line for _, line in remaining)

    # One final accurate count
    final_tokens = token_count(current)

    # Second pass with accurate per-line token counts if still over budget
    # Raise density threshold to 0.98 — willing to drop more to respect budget
    if final_tokens > max_tokens and remaining:
        remaining_scored = []
        for i, line in remaining:
            d = _line_density(line)
            tag = line.strip()[:2]
            if d < 0.98 and tag not in ("D>", "B>", "F>", "E>", "A>") and not line.strip().startswith("===") and not line.startswith("#"):
                remaining_scored.append((i, line, d, token_count(line)))
        remaining_scored.sort(key=lambda x: x[2])  # lowest density first
        for idx, _, _, ltok in remaining_scored:
            if final_tokens <= max_tokens:
                break
            dropped.add(idx)
            final_tokens -= ltok
        current = "\n".join(line for i, line in enumerate(lines) if i not in dropped)
        final_tokens = token_count(current)

    # Final pass: if still over, trim lines from the end (least important position)
    if final_tokens > max_tokens:
        final_lines = current.split("\n")
        while final_lines and final_tokens > max_tokens:
            removed = final_lines.pop()
            final_tokens -= token_count(removed)
        current = "\n".join(final_lines)
        final_tokens = token_count(current)

    if dropped:
        print(f"  KIComp: dropped {len(dropped)} low-density lines "
              f"(budget: {max_tokens} tokens, final: {final_tokens} tokens)", file=sys.stderr)

    return current


# ── NCD SIMILARITY ───────────────────────────────────────────────

def _ncd(a: str, b: str) -> float:
    """Normalized Compression Distance — semantic similarity via zlib.

    NCD(a,b) = (C(a+b) - min(C(a), C(b))) / max(C(a), C(b))
    Returns 0.0 (identical) to 1.0 (completely different).
    Based on: Cilibrasi & Vitanyi 2005.
    """
    if a == b:
        return 0.0
    if not a or not b:
        return 1.0
    import zlib
    ab = a.encode("utf-8")
    bb = b.encode("utf-8")
    ca = len(zlib.compress(ab))
    cb = len(zlib.compress(bb))
    cab = len(zlib.compress(ab + bb))
    return (cab - min(ca, cb)) / max(ca, cb) if max(ca, cb) > 0 else 0.0


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


# ── COMPRESS ──────────────────────────────────────────────────────

def compress_line(line: str) -> str:
    """Compress a single line using all compression layers.

    Layer 1: Markdown stripping
    Layer 2: Filler word removal (articles, prepositions, connectors)
    Layer 3: Common phrase collapsing
    Layer 4: Number compression (150,000 -> 150K)
    Layer 5: Universal text rules
    Layer 6: Mycelium fusion stripping
    Layer 7: Key-value extraction from natural language
    """
    if not line:
        return line or ""
    # P14/P25: tagged lines (D>/B>/F>/E>/A>) are already classified — skip compression
    if len(line) >= 2 and line[:2] in ("B>", "E>", "F>", "D>", "A>"):
        return line
    cb = get_codebook()
    result = line

    # L1: Strip markdown formatting
    result = re.sub(r"^#{1,4}\s+", "", result)
    result = result.replace("**", "")
    result = re.sub(r"^-\s+", "", result)
    result = result.replace("`", "")

    # L2 pre-pass: protect fillers that carry meaning between numbers/math
    # "2 of the 5" must not become "2 5", "log of n" must stay
    _PROTECTED = re.findall(
        r'\d+\s+(?:of|to|in|at|by|for)\s+(?:the\s+)?\d+',
        result, flags=re.IGNORECASE
    )
    _MATH_PROTECTED = re.findall(
        r'(?:log|sum|product|ratio|percentage)\s+of\b',
        result, flags=re.IGNORECASE
    )
    # P24: Protect causal connectors — "because X" carries the WHY
    _CAUSAL_PROTECTED = re.findall(
        r'(?:because|since|therefore|so that|due to|parce que?|car|donc|puisque)\s+\S+',
        result, flags=re.IGNORECASE
    )
    # Replace protected spans with placeholders
    _placeholders = {}
    for i, span in enumerate(_PROTECTED + _MATH_PROTECTED + _CAUSAL_PROTECTED):
        placeholder = f"__PROT{i}__"
        _placeholders[placeholder] = span
        result = result.replace(span, placeholder, 1)

    # L2: Filler word removal — these carry zero information in memory notes
    _FILLER = [
        # Articles & determiners (case-insensitive safe ones)
        r"\bthe\b",
        r"\ble\b", r"\bla\b", r"\bles\b", r"\bun\b", r"\bune\b", r"\bdes\b",
        # Connectors & filler verbs
        r"\bwas\b", r"\bwere\b", r"\bis\b", r"\bare\b", r"\bbeen\b",
        r"\bwhich\b", r"\bthat\b", r"\bthis\b",
        r"\bby\b", r"\bof\b", r"\bfor\b", r"\bin\b", r"\bon\b", r"\bat\b",
        r"\bto\b", r"\bwith\b", r"\bfrom\b", r"\binto\b",
        r"\band\b", r"\bbut\b", r"\bor\b",
        # Verbose phrases (longest first)
        r"\bapproximately\b", r"\bcurrently\b", r"\bproperly\b",
        r"\bcorresponds to\b", r"\binstead of\b",
        r"\bbased on\b", r"\bin order to\b",
        r"\bnow\b", r"\balso\b", r"\bjust\b", r"\bstill\b",
        # Common verbal tics
        r"\bbasically\b", r"\bactually\b", r"\bessentially\b",
        r"\bobviously\b", r"\bsimply\b", r"\breally\b", r"\bprobably\b",
        # French fillers
        r"\best\b", r"\bqui\b", r"\bque\b", r"\bdans\b", r"\bavec\b",
        r"\bpour\b", r"\bplus\b", r"\btout\b", r"\bmais\b",
    ]
    for filler in _FILLER:
        result = re.sub(filler, "", result, flags=re.IGNORECASE)
    # "a"/"an": case-sensitive, only as English articles (before a word, not standalone "a" in math/code)
    result = re.sub(r"\ba (?=[a-z])", "", result)
    result = re.sub(r"\ban (?=[a-z])", "", result)

    # L2b: Learned fillers from mycelium (words in 10+ connections, never fused)
    for filler_word in cb.get("learned_fillers", []):
        result = re.sub(rf"\b{re.escape(filler_word)}\b", "", result, flags=re.IGNORECASE)

    # L2 post-pass: restore protected spans
    for placeholder, original_span in _placeholders.items():
        result = result.replace(placeholder, original_span)

    # L3: Common phrase collapsing
    _PHRASES = [
        (r"take\s+into\s+account", "consider"),
        (r"take\s+account", "consider"),
        (r"in\s+order\s+to", "to"),
        (r"as\s+a\s+result\s+of", "from"),
        (r"not properly closing", "not closing"),
        (r"was not", "!"),
        (r"instead of growing unboundedly", "stable"),
        (r"per frame", "/frame"),
        (r"per time frame", "/frame"),
        (r"per commit", "/commit"),
        (r"per second", "/s"),
        (r"one per", "1/"),
        (r"runs on", "on"),
        (r"well under", "<"),
        (r"no accuracy loss", "acc=same"),
        (r"all passing", "pass"),
        (r"not found", "missing"),
        (r"not properly", "badly"),
        (r"Fixed by", "fix:"),
        (r"Optimized", "opt"),
        (r"Implemented", "impl"),
        (r"Decided to use", "use"),
        (r"Considering", "maybe"),
        (r"Migrated", "moved"),
        (r"Total parameters", "params"),
        (r"Total test count", "tests"),
        (r"Test coverage", "cov"),
        (r"Inference time", "infer"),
        (r"Total latency", "latency"),
        (r"Memory usage", "mem"),
        (r"Target latency", "target"),
        (r"each recording", "each"),
        (r"continuous use", "runtime"),
        (r"overall", "avg"),
        (r"critical path", "crit"),
    ]
    for pattern, replacement in _PHRASES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # L3b: Learned abbreviations from mycelium (strong fusions -> shorter form)
    _result_lower = result.lower()
    for long_form, short_form in cb.get("learned_abbreviations", {}).items():
        if long_form in _result_lower:
            result = re.sub(rf"\b{re.escape(long_form)}\b", short_form, result,
                          count=1, flags=re.IGNORECASE)
            _result_lower = result.lower()

    # L4: Compress large numbers
    def shorten_number(m):
        n = int(m.group(0).replace(",", ""))
        if n >= 1_000_000:
            return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K" if n % 1_000 == 0 else f"{n / 1_000:.1f}K"
        return str(n)

    result = re.sub(r"\d{1,3}(?:,\d{3})+", shorten_number, result)

    # L5: Apply text rules (longest first to avoid partial matches)
    # Use word-boundary regex to prevent substring corruption
    # (e.g. "completed" must NOT become "doneed" from rule "complete"->"done")
    for pattern in sorted(cb["text_rules"].keys(), key=len, reverse=True):
        escaped = re.escape(pattern)
        # Only use \b around patterns that start/end with word characters
        prefix = r'\b' if re.match(r'\w', pattern[0]) else ''
        suffix = r'\b' if re.match(r'\w', pattern[-1]) else ''
        result = re.sub(rf'{prefix}{escaped}{suffix}', cb["text_rules"][pattern], result)

    # L6: Mycelium-aware compression: strong fusions = predictable pairs.
    # Only drop shorter concept if it appears exactly once AND near the other.
    strong_fusions = {k: v for k, v in cb["mycelium_rules"].items()
                      if v["strength"] >= 10}
    result_lower = result.lower()
    for key, rule in strong_fusions.items():
        a, b = rule["concepts"]
        if a in result_lower and b in result_lower:
            drop = b if len(b) <= len(a) else a
            keep = a if drop == b else b
            # Only drop if the concept appears exactly once (not used independently)
            drop_count = len(re.findall(rf'\b{re.escape(drop)}\b', result_lower))
            if drop_count == 1:
                # Only drop if within 5 words of the kept concept
                pattern = rf'\b{re.escape(keep)}\b.{{0,40}}\b{re.escape(drop)}\b|\b{re.escape(drop)}\b.{{0,40}}\b{re.escape(keep)}\b'
                if re.search(pattern, result_lower):
                    result = re.sub(rf'\s+\b{re.escape(drop)}\b', '', result,
                                  count=1, flags=re.IGNORECASE)
                    result_lower = result.lower()

    # L7: Extract key=value patterns from natural language
    # "accuracy: 94.2%" -> "acc=94.2%"
    # "takes 45ms" -> "45ms"
    result = re.sub(r"[Aa]ccuracy\s*[:=]?\s*", "acc=", result)
    result = re.sub(r"[Ll]atency\s*[:=]?\s*", "lat=", result)
    result = re.sub(r"[Cc]overage\s*[:=]?\s*", "cov=", result)
    result = re.sub(r"takes\s+", "", result)
    result = re.sub(r"around\s+", "~", result)
    result = re.sub(r"approximately\s+", "~", result)
    result = re.sub(r"stays stable\s+", "stable ", result)

    # Clean up: collapse multiple spaces, strip
    result = re.sub(r"\s{2,}", " ", result).strip()
    # Remove trailing/leading punctuation artifacts
    result = re.sub(r"^\s*[,;]\s*", "", result)
    result = re.sub(r"\s+[,;]\s*$", "", result)

    return result


def extract_facts(text: str) -> list[str]:
    """Extract key facts from natural language text.

    Pulls out: numbers+units, percentages, key=value pairs, commits,
    dates, filenames, technical terms. Drops narrative filler.
    """
    if not text:
        return []
    facts = []

    # Numbers with units (45ms, 2.3 TB, 4096 samples, etc.)
    for m in re.finditer(r'(\d+[\d.,]*)\s*(ms|MB|GB|TB|Hz|fps|GPUs?|hours?|minutes?|seconds?|samples?|bins?|frames?|parameters?|million|K|M)\b', text):
        val, unit = m.group(1), m.group(2)
        # Shorten units
        unit_map = {"hours": "h", "hour": "h", "minutes": "min", "seconds": "s",
                    "second": "s", "samples": "smp", "sample": "smp",
                    "parameters": "params", "million": "M", "GPUs": "GPU",
                    "bins": "bins", "frames": "frames"}
        unit = unit_map.get(unit, unit)
        facts.append(f"{val}{unit}")

    # Percentages (94.2%, 87%)
    for m in re.finditer(r'(\d+\.?\d*)\s*%', text):
        facts.append(f"{m.group(1)}%")

    # key: value patterns (only if value wasn't already captured as number+unit)
    existing_nums = {f.split("=")[-1].rstrip("%") for f in facts}
    for m in re.finditer(r'([A-Za-z][\w\s]*?):\s*(\d[\d.,]*\s*\w+)', text):
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        # Skip if the numeric part is already in facts
        num_part = re.match(r'[\d.,]+', val)
        if num_part and any(num_part.group(0) in f for f in facts):
            continue
        if len(key) <= 20 and key not in ("the", "a", "an", "to", "in", "on"):
            facts.append(f"{key}={val}")

    # x-ratios (x4.1, x9.6, x143)
    for m in re.finditer(r'\bx(\d+\.?\d*)\b', text):
        facts.append(f"x{m.group(1)}")

    # Dates (2026-03-11, 2025/12/01)
    for m in re.finditer(r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b', text):
        facts.append(m.group(1))

    # Version numbers (v0.9.1, Python 3.13) — skip if preceded by $ (dollar amount)
    for m in re.finditer(r'\bv?(\d+\.\d+(?:\.\d+)?)\b', text):
        val = m.group(1)
        if val not in [f.rstrip('%') for f in facts]:  # avoid dupes with percentages
            if m.start() > 0 and text[m.start() - 1] == '$':
                continue  # skip dollar amounts — captured below
            facts.append(f"v{val}" if text[m.start()] == 'v' else val)

    # Dollar costs ($0.21, $1.50)
    for m in re.finditer(r'\$(\d+\.?\d*)', text):
        facts.append(f"${m.group(1)}")

    # Commit hashes (require at least one letter to avoid pure-digit false positives)
    for m in re.finditer(r'\b([a-f0-9]{7,12})\b', text):
        val = m.group(1)
        if re.search(r'[a-f]', val):  # must contain a hex letter, not just digits
            facts.append(val)

    # Filenames and paths
    for m in re.finditer(r'\b[\w/]+\.(?:py|rs|ts|js|json|yaml|yml|toml|md|gz|npz|npy)\b', text):
        facts.append(m.group(0))

    # Cohen's d
    for m in re.finditer(r"Cohen's\s+d\s*=\s*([\d.]+)", text):
        facts.append(f"d={m.group(1)}")

    # p-values
    for m in re.finditer(r"p\s*=\s*([\d.e-]+)", text):
        facts.append(f"p={m.group(1)}")

    return list(dict.fromkeys(facts))  # deduplicate preserving order


# ── MEMORY TYPE TAGGER ─────────────────────────────────────────
# Tags compressed lines with their memory type for prioritized retrieval.
# D> = decision, B> = bug/fix, F> = fact/metric, A> = architecture, E> = error

_TAG_PATTERNS = [
    ("B>", re.compile(
        r"(?i)(bug|fix|patch|crash|broke|broken|repair|hotfix|regression|"
        r"workaround|corrig[eé]|r[eé]par[eé])"
    )),
    ("E>", re.compile(
        r"(?i)(error|exception|traceback|failed|failure|TypeError|ValueError|"
        r"KeyError|IndexError|ImportError|AttributeError|SyntaxError|"
        r"FileNotFoundError|RuntimeError|erreur|echou[eé])"
    )),
    ("F>", re.compile(
        r"(?i)(x\d+\.?\d*|ratio|benchmark|token|percent|%|\d+\.\d+[sx]|"
        r"mesur[eé]|metric|gain|score|accuracy|retention|cost\s*[:=]|"
        r"latency|throughput|p\d{2,3}|req/s|\d+ms|\d+s\b|perf)"
    )),
    ("D>", re.compile(
        r"(?i)(decid|decision|chose|pivot|switch|adopt|drop|keep|use instead|"
        r"go with|won't|will use|prefer|opted|choix|on garde|on vire|on prend)"
    )),
    ("A>", re.compile(
        r"(?i)(architect|structure|design|pattern|pipeline|module|"
        r"refactor|abstract|interface|class\s+\w|inherit|compos)"
    )),
]


def tag_memory_type(line: str) -> str:
    """Classify a compressed line by memory type. Returns tagged line or original."""
    if not line:
        return line or ""
    # Don't double-tag
    if len(line) >= 2 and line[:2] in ("B>", "E>", "F>", "D>", "A>"):
        return line
    for tag, pattern in _TAG_PATTERNS:
        if pattern.search(line):
            return f"{tag}{line}"
    return line


def compress_section(header: str, lines: list[str]) -> str:
    cb = get_codebook()
    text_rules = cb["text_rules"]

    # Extract state — uses universal symbols only
    state = "?"
    state_words = {
        "COMPLET": "✓", "COMPLETE": "✓", "DONE": "✓",
        "VALIDE": "✓", "VALIDÉ": "✓", "FIXE": "✓", "FIXÉ": "✓",
        "EN COURS": "⟳", "IN PROGRESS": "⟳",
        "PRÊT": "◉", "READY": "◉",
        "FAILED": "✗", "ECHOUE": "✗", "ECHOUÉ": "✗",
    }
    for pattern, code in sorted(state_words.items(), key=lambda x: len(x[0]), reverse=True):
        if pattern in header.upper():
            state = code
            # Strip state word with dash prefix (e.g. "— COMPLETE")
            header = re.sub(
                rf"\s*[—\-]+\s*{re.escape(pattern)}", "",
                header, flags=re.IGNORECASE
            )
            # Also strip state word at end without dash (e.g. "x4.5 VALIDE")
            header = re.sub(
                rf"\s+{re.escape(pattern)}\s*$", "",
                header, flags=re.IGNORECASE
            )
            break

    # Extract session/version markers
    session = ""
    m = re.search(r"\(session\s+(\d+)", header, re.IGNORECASE)
    if m:
        session = f"@s{m.group(1)}"
        header = re.sub(r"\s*\(session\s+\d+.*?\)", "", header, flags=re.IGNORECASE)

    # Extract date from header
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", header)
    if dm:
        session = f"@{dm.group(1)}" if not session else session
        header = re.sub(r"\s*[—\-]+\s*\d{4}-\d{2}-\d{2}", "", header)

    header = re.sub(r"^#+\s*", "", header).strip()

    for pattern in sorted(text_rules.keys(), key=len, reverse=True):
        header = re.sub(rf'\b{re.escape(pattern)}\b', text_rules[pattern], header)

    compressed_header = f"{state}{header}{session}"

    # Gather body text
    body_text = "\n".join(line for line in lines if line.strip())

    # Detect sub-sections (### headers within the section)
    subsections = []
    current_sub_header = None
    current_sub_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### ") or stripped.startswith("## "):
            if current_sub_header:
                subsections.append((current_sub_header, current_sub_lines))
            current_sub_header = re.sub(r"^#{1,4}\s+", "", stripped)
            current_sub_lines = []
        else:
            current_sub_lines.append(stripped)

    if current_sub_header:
        subsections.append((current_sub_header, current_sub_lines))

    # If we have subsections, compress each one as a fact-line
    if subsections:
        result = compressed_header + ":"
        for sub_h, sub_lines in subsections:
            sub_text = "\n".join(sub_lines)
            facts = extract_facts(sub_text)

            # Compress sub-header
            sub_h_compressed = compress_line(sub_h)

            # Detect state in sub-header
            sub_state = ""
            for pattern, code in state_words.items():
                if pattern in sub_h.upper():
                    sub_state = code
                    sub_h_compressed = re.sub(
                        rf"\s*[—\-]+\s*{re.escape(pattern)}", "",
                        sub_h_compressed, flags=re.IGNORECASE
                    )
                    break

            if facts:
                fact_str = "|".join(facts[:8])  # cap at 8 facts per subsection
                result += f"\n  {sub_state}{sub_h_compressed}:{fact_str}"
            else:
                # Fall back to line-by-line compression
                compressed_lines = [compress_line(l) for l in sub_lines if l.strip()]
                compressed_lines = [l for l in compressed_lines if l]
                if compressed_lines:
                    result += f"\n  {sub_state}{sub_h_compressed}:{compressed_lines[0]}"
                    for cl in compressed_lines[1:3]:  # max 3 detail lines
                        result += f"\n    {cl}"
        return result

    # No subsections: compress line by line with fact extraction
    body = []
    for line in lines:
        if not line.strip():
            continue
        cl = compress_line(line)
        if cl:
            body.append(cl)

    if sum(len(b) for b in body) < 120:
        return f"{compressed_header}:{('|'.join(body))}"
    else:
        result = compressed_header + ":"
        for b in body:
            result += f"\n  {b}"
        return result


def _resolve_contradictions(text: str) -> str:
    """Resolve numeric contradictions — last-writer-wins.

    When the same entity has different numeric values at different points,
    keep only the LATEST value. Prevents stale facts from persisting.
    Based on: Stanford NLP 2008 (Finding Contradictions in Text).

    Example: "ratio x7.4" then later "ratio x4.1" → keeps only "ratio x4.1"
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    # Strategy: two lines "contradict" if they are identical EXCEPT for the numbers.
    # Replace all numbers with a placeholder, then group by this "skeleton".
    # Within each group, keep only the LAST line (most recent = most correct).
    num_val = re.compile(
        r'[x×]?\d+(?:[.,]\d+)?(?:%|K|M|ms|s|px|x|GB|MB|KB|tokens?|lines?|tok)?'
    )

    skeleton_last = {}  # skeleton -> (line_text, line_index)
    contradictions = {}  # skeleton -> set of line indices to remove
    for i, line in enumerate(lines):
        if line.startswith("#") or line.startswith("?FACTS") or not line.strip():
            continue
        # Build skeleton: replace all numbers with placeholder, then lowercase
        skel = num_val.sub("_NUM_", line).strip().lower()
        skel = re.sub(r'\s+', ' ', skel)
        # Only track lines that HAVE numbers (no numbers = no contradiction possible)
        if "_num_" not in skel:
            continue
        if skel in skeleton_last:
            old_text, old_idx = skeleton_last[skel]
            if old_text != line:
                # Guard: numbered list items (1. X, 2. X) are NOT contradictions.
                # Detect: skeleton starts with _NUM_ + list marker, lines are near-consecutive.
                is_list_item = (
                    (re.match(r'^_num_[\.\)]\s', skel)       # numbered: 1. X, 2) X
                     or re.match(r'^[-*]\s', line.strip()))   # bullet: - X, * X
                    and abs(i - old_idx) <= 5  # within 5 lines of each other
                )
                if not is_list_item:
                    # Same structure, different numbers = contradiction
                    if skel not in contradictions:
                        contradictions[skel] = set()
                    contradictions[skel].add(old_idx)
        skeleton_last[skel] = (line, i)

    if not contradictions:
        return text

    # Collect all line indices to remove
    remove_indices = set()
    for indices in contradictions.values():
        remove_indices.update(indices)

    # Only remove lines where the ENTIRE line is about the contradicted fact
    # (don't remove lines that contain other important info)
    # Safety: only remove if line is short (< 100 chars) — long lines likely have other content
    safe_removes = set()
    for idx in remove_indices:
        if len(lines[idx].strip()) < 100:
            safe_removes.add(idx)

    if not safe_removes:
        return text

    result_lines = [line for i, line in enumerate(lines) if i not in safe_removes]
    removed = len(safe_removes)
    print(f"  Contradiction resolution: {removed} stale lines removed "
          f"({len(contradictions)} entities updated)", file=sys.stderr)

    return "\n".join(result_lines)


# ── L10: CUE DISTILLATION ─────────────────────────────────────────
# Theory: Method of Loci (500 BC) + Schema Theory (Bartlett 1932)
# + Predictive Coding (Rao & Ballard 1999).
# The LLM already knows ~80% of what we store (APIs, syntax, patterns).
# Only store NOVEL facts (numbers, decisions, commits) + minimal CUES
# for generic knowledge that the LLM can reconstruct from memory.

# Regex patterns for detecting novel (project-specific) content
_NOVEL_PATTERNS = [
    re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}'),                    # dates
    re.compile(r'[a-f0-9]{7,40}'),                               # commit hashes
    re.compile(r'x\d+\.?\d*'),                                   # ratios (x4.1, x19.4)
    re.compile(r'\$\d+'),                                        # costs ($0.024)
    re.compile(r'\d+\.?\d*[KMBkm](?:\b|$)'),                    # quantities (348M, 65K)
    re.compile(r'\d+%'),                                         # percentages
    re.compile(r'v\d+\.\d+'),                                    # versions (v0.9)
    re.compile(r'P\d{1,2}\b'),                                   # project phases (P13)
    re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+'),                 # CamelCase identifiers
    re.compile(r'(?<!\b[ei])[\w/\\]{2,}\.\w{1,4}\b'),             # file paths (skip e.g/i.e)
    re.compile(r'Sharpe|BLEU|F1|accuracy|precision|recall', re.I),  # metrics names
]

# Patterns indicating generic/known knowledge (LLM can reconstruct)
_KNOWN_PATTERNS = [
    re.compile(r'^(?:according to|as per|following|based on)\b', re.I),
    re.compile(r'^(?:the|a|an)\s+(?:standard|default|typical|common|recommended)\b', re.I),
    re.compile(r'\bMaterial Design\b|\bWCAG\b|\bApple HIG\b', re.I),
    re.compile(r'\bguidelines?\s+(?:state|recommend|suggest)\b', re.I),
    re.compile(r'\bbest practices?\b', re.I),
]


def _novelty_score(line: str) -> float:
    """Score how NOVEL a line is (0.0=generic knowledge, 1.0=unique fact).

    High novelty: project-specific numbers, dates, commits, decisions.
    Low novelty: framework docs, standard patterns, API descriptions.
    """
    if not line:
        return 0.0
    s = line.strip()
    if not s:
        return 0.0

    # Headers and tagged lines are structural/novel — always keep
    if s.startswith("#") or s.startswith("===") or s.startswith("?"):
        return 1.0
    for tag in ("D>", "B>", "E>", "F>", "A>"):
        if s.startswith(tag):
            return 0.9

    # Code comments and code lines — keep as-is (context-dependent)
    if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return 0.8
    # Code patterns (braces, imports, XML)
    if re.match(r'^[\.\{\}</@]', s) or s.startswith("import ") or s.startswith("val "):
        return 0.8

    score = 0.0

    # Novel indicators: project-specific content
    for pat in _NOVEL_PATTERNS:
        matches = pat.findall(s)
        if matches:
            score += 0.15 * len(matches)

    # Known indicators: generic framework knowledge
    for pat in _KNOWN_PATTERNS:
        if pat.search(s):
            score -= 0.3

    # Ratio of numbers to words — high ratio = data-dense = novel
    words = s.split()
    if words:
        num_tokens = sum(1 for w in words if re.search(r'\d', w))
        num_ratio = num_tokens / len(words)
        score += num_ratio * 0.3

    # Key=value density — structured data is novel
    kv_count = len(re.findall(r'\w+=\S+', s))
    score += min(0.3, kv_count * 0.1)

    # Pipe-separated values — dense fact lines
    if s.count('|') >= 2:
        score += 0.2

    # Long text without any numbers or identifiers = likely generic
    if len(s) > 100 and not re.search(r'\d', s):
        score = min(score, 0.15)

    # Floor: lines with dates, commits, or ratios are ALWAYS novel (factual data).
    # Prevents these from being mangled by _generate_cue() below threshold.
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}|[a-f0-9]{7,40}|x\d+\.?\d*', s):
        score = max(score, 0.35)

    return max(0.0, min(1.0, score))


def _generate_cue(line: str) -> str:
    """Compress a KNOWN line into a minimal retrieval cue (2-10 tokens).

    Extracts the key concept identifier that will trigger the LLM's
    parametric memory to reconstruct the full knowledge.
    """
    s = line.strip()

    # If line has a key: value format, keep just key + any numbers
    kv_match = re.match(r'^(\w[\w_]*)\s*[:=]\s*(.+)', s)
    if kv_match:
        key = kv_match.group(1)
        value = kv_match.group(2)
        # Keep numbers WITH surrounding context (word before + after number)
        nums_with_ctx = re.findall(r'(?:\w+\s+)?\d+[\.\d]*\s*(?:[a-zA-Z%]+)?', value)
        # Keep CamelCase identifiers (API names, class names)
        identifiers = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', value)
        # Keep proper nouns (capitalized words that aren't sentence starters)
        proper_nouns = re.findall(r'(?:^|[\s,])((?:[A-Z][\w]*\s*){1,3})', value)
        proper_nouns = [p.strip() for p in proper_nouns if len(p.strip()) > 2]
        kept = [n.strip() for n in nums_with_ctx[:4]] + identifiers[:2] + proper_nouns[:2]
        if kept:
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for k in kept:
                if k.lower() not in seen:
                    seen.add(k.lower())
                    unique.append(k)
            return f"{key}: {', '.join(unique)}"
        # No numbers or identifiers — just the key as cue
        return key

    # If line has pipe-separated entries, keep first identifier + count
    if '|' in s:
        parts = [p.strip() for p in s.split('|')]
        # Extract just the key names
        keys = []
        for p in parts:
            km = re.match(r'^(\w[\w_]*)', p)
            if km:
                keys.append(km.group(1))
        if keys:
            return ' | '.join(keys[:5])

    # Fallback: extract the most specific noun phrases (capitalized words + adjacent)
    important = re.findall(r'[A-Z][\w]*(?:\s+[A-Z][\w]*)*', s)
    # Also grab any numbers with context
    nums = re.findall(r'(?:\w+\s+)?\d+[\.\d]*\s*(?:[a-zA-Z%]+)?', s)
    all_parts = important[:3] + [n.strip() for n in nums[:3]]
    if all_parts:
        return ' | '.join(all_parts)

    # Last resort: first N words (enough for the LLM to reconstruct)
    words = s.split()
    return ' '.join(words[:min(8, len(words))])


def _cue_distill(text: str, threshold: float = 0.35) -> str:
    """L10: Cue Distillation — replace generic knowledge with minimal cues.

    Lines with novelty_score < threshold are compressed to retrieval cues.
    Lines with novelty_score >= threshold are kept verbatim (novel facts).

    Theory: Predictive Coding (Rao & Ballard 1999) — only store prediction errors.
    The LLM's parametric memory already contains generic knowledge.
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    result = []
    cued = 0
    kept = 0

    for line in lines:
        s = line.strip()
        if not s:
            result.append(line)
            continue

        score = _novelty_score(s)

        if score >= threshold:
            result.append(line)
            kept += 1
        else:
            cue = _generate_cue(s)
            if cue and len(cue) < len(s) * 0.7:  # Only cue if actually shorter
                result.append(cue)
                cued += 1
            else:
                result.append(line)  # Keep if cue not shorter
                kept += 1

    if cued > 0:
        print(f"  L10 Cue Distillation: {cued} lines cued, {kept} kept "
              f"(threshold={threshold})", file=sys.stderr)

    return "\n".join(result)


# ── L11: RULE EXTRACTION ──────────────────────────────────────────
# Theory: Kolmogorov complexity (1965) — store the shortest PROGRAM
# that generates the data, not the data itself.
# Detect repeated key=value structures and factorize into rules.

def _extract_rules(text: str) -> str:
    """L11: Rule Extraction — factorize repeated key=value patterns.

    Detects lines with multiple key=value or key: value pairs sharing
    the same unit/structure and condenses them into a single rule line.

    Example:
      battery_drain: 9min screen | 1% GPS | 5% BT | 15% WiFi
      -> battery_drain: screen=9min GPS=1% BT=5% WiFi=15%
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    result = []
    factorized = 0

    for line in lines:
        s = line.strip()
        if not s:
            result.append(line)
            continue

        # Detect pipe-separated key-value entries with shared units
        if '|' in s and s.count('|') >= 2:
            parts = [p.strip() for p in s.split('|')]

            # Try to extract key: entries from each part
            kvs = []
            for p in parts:
                m = re.match(r'^(\w[\w_\s]*?)\s*[:=]\s*(.+)', p)
                if m:
                    kvs.append((m.group(1).strip(), m.group(2).strip()))

            # If most parts are key=value and values share a unit pattern
            if len(kvs) >= 3 and len(kvs) >= len(parts) * 0.6:
                # Extract common unit suffix
                values = [v for _, v in kvs]
                units = set()
                for v in values:
                    u = re.findall(r'[a-zA-Z%]+$', v)
                    if u:
                        units.add(u[0])

                if len(units) == 1:
                    # All same unit — factorize
                    unit = units.pop()
                    compact_parts = []
                    for k, v in kvs:
                        num = re.match(r'[\d\.]+', v)
                        if num:
                            compact_parts.append(f"{k}={num.group()}")
                        else:
                            compact_parts.append(f"{k}={v}")
                    rule_line = f"({unit}) " + ", ".join(compact_parts)
                    result.append(rule_line)
                    factorized += 1
                    continue

        result.append(line)

    if factorized > 0:
        print(f"  L11 Rule Extraction: {factorized} lines factorized",
              file=sys.stderr)

    return "\n".join(result)


def _llm_compress_chunk(text: str, client, context: str = "") -> tuple:
    """Compress a single chunk via Claude Haiku API. Returns text unchanged on failure."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max(1, token_count(text)),
            temperature=0,
            system=_L9_SYSTEM,
            messages=[{"role": "user", "content":
                _L9_PROMPT + f"INPUT ({len(text)} chars):\n{text}"
            }],
        )
        compressed = response.content[0].text
        truncated = response.stop_reason == "max_tokens"
        if truncated:
            print(f"  L9 WARNING: truncated, keeping original [{context}]", file=sys.stderr)
            return text, response.usage
        if len(compressed) < len(text) * 0.9:
            return compressed, response.usage
        return text, response.usage
    except Exception as e:
        print(f"  L9 ERROR: {e} [{context}]", file=sys.stderr)
        return text, None


def _llm_compress(text: str, context: str = "") -> str:
    """Layer 9: LLM self-compress via Claude Haiku API.

    R1-Compress: chunks text by ## sections for better coherence.
    Returns text unchanged if unavailable.
    """
    if len(text) <= 4000:
        return text
    if globals().get('_SKIP_L9', False):
        return text
    try:
        import os, subprocess as _sp
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            try:
                _r = _sp.run(['powershell', '-Command',
                    "[System.Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')"],
                    capture_output=True, text=True, timeout=5)
                api_key = _r.stdout.strip() or None
            except Exception:
                pass
        if not api_key:
            return text
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # R1-Compress: chunk by sections for better fact retention
        if len(text) > 8000:
            chunks = re.split(r'(?=^## )', text, flags=re.MULTILINE)
            chunks = [c for c in chunks if c.strip()]

            # Fallback: if no ## headers found, split by line count
            if len(chunks) < 2:
                lines = text.split("\n")
                chunk_size = max(1, len(lines) // max(2, len(text) // 6000))  # M3 fix: at least 2 chunks
                chunks = []
                for i in range(0, len(lines), chunk_size):
                    chunk = "\n".join(lines[i:i + chunk_size])
                    if chunk.strip():
                        chunks.append(chunk)

            if len(chunks) >= 2:
                compressed_chunks = []
                total_in, total_out = 0, 0
                for i, chunk in enumerate(chunks):
                    if len(chunk) < 200:  # too small to compress
                        compressed_chunks.append(chunk)
                        continue
                    result, usage = _llm_compress_chunk(
                        chunk, client, context=f"{context}:chunk{i}")
                    compressed_chunks.append(result)
                    if usage:
                        total_in += usage.input_tokens
                        total_out += usage.output_tokens

                llm_compressed = "\n".join(compressed_chunks)
                if len(llm_compressed) < len(text) * 0.9:
                    print(f"  Layer 9 (LLM): {len(text)} -> {len(llm_compressed)} chars "
                          f"(API: {total_in}in+{total_out}out) "
                          f"[{len(chunks)} chunks] [{context}]", file=sys.stderr)
                    return llm_compressed
                return text

        # Single-chunk compression for smaller texts
        result, usage = _llm_compress_chunk(text, client, context=context)
        if len(result) < len(text) * 0.9:
            api_str = f"(API: {usage.input_tokens}in+{usage.output_tokens}out)" if usage else ""
            print(f"  Layer 9 (LLM): {len(text)} -> {len(result)} chars "
                  f"{api_str} [{context}]", file=sys.stderr)
            return result
        return text
    except ImportError:
        return text  # anthropic not installed
    except Exception as e:
        print(f"  Layer 9 ERROR: {e} [{context}]", file=sys.stderr)
        return text


def compress_file(filepath: Path) -> str:
    text = filepath.read_text(encoding="utf-8")

    # Redact secrets before any compression
    for pat in _SECRET_PATTERNS:
        text = re.sub(pat, '[REDACTED]', text)

    lines = text.split("\n")

    sections = []
    current_header = None
    current_lines = []

    for line in lines:
        if line.startswith("## "):
            if current_header or current_lines:
                sections.append((current_header or "## Preamble", current_lines))
            current_header = line
            current_lines = []
        elif line.startswith("# ") and not line.startswith("## "):
            continue
        else:
            current_lines.append(line)

    if current_header or current_lines:
        sections.append((current_header or "## Preamble", current_lines))

    output = ["# MUNINN|codebook=v0.1"]
    for header, slines in sections:
        compressed = compress_section(header, slines)
        output.append(compressed)

    result = "\n".join(output)

    # Contradiction resolution (last-writer-wins on numeric facts)
    result = _resolve_contradictions(result)

    # L10: Cue Distillation — BEFORE L9 (filter generic knowledge early)
    result = _cue_distill(result)

    # L11: Rule Extraction — factorize repeated key=value patterns
    result = _extract_rules(result)

    # Layer 9: LLM self-compress (optional, for large outputs)
    result = _llm_compress(result, context=str(filepath.name))

    return result


# ── TREE BUILD ────────────────────────────────────────────────────

def build_tree(filepath: Path):
    """R3: compress BEFORE split. R2: split if over budget."""
    tree = load_tree()

    compressed = compress_file(filepath)
    comp_lines = compressed.split("\n")

    print(f"\n  Source: {filepath}")
    print(f"  Original: {filepath.stat().st_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Lines: {len(comp_lines)}")

    if len(comp_lines) <= BUDGET["root_lines"]:
        root_path = TREE_DIR / "root.mn"
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
                (TREE_DIR / branch_file).write_text(section, encoding="utf-8")
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
            while len(root_lines) > BUDGET["root_lines"] - len(overflow_refs) and len(overflow_refs) < BUDGET["root_lines"] - 1:
                overflow = root_lines.pop()
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                (TREE_DIR / branch_file).write_text(overflow, encoding="utf-8")
                overflow_refs.append(f"\u2192{branch_name}:{overflow[:50]}")
                tree["nodes"][branch_name] = {
                    "type": "branch", "file": branch_file,
                    "lines": 1, "max_lines": BUDGET["branch_lines"],
                    "children": [], "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0, "tags": [],
                }
                branch_id += 1
            root_lines.extend(overflow_refs)

        root_path = TREE_DIR / "root.mn"
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
            existing_file = TREE_DIR / node["file"]
            should_merge = False
            if existing_file.exists():
                existing_text = existing_file.read_text(encoding="utf-8")
                if existing_text and body:
                    ncd = _ncd(body, existing_text)
                    should_merge = ncd < 0.4
            if not should_merge:
                existing_tags = set(node.get("tags", []))
                if existing_tags and tag_set:
                    overlap = len(tag_set & existing_tags) / max(len(tag_set | existing_tags), 1)
                    should_merge = overlap > 0.5
            if should_merge:
                # Context-Aware Merge: append + resolve contradictions + dedup
                filepath = TREE_DIR / node["file"]
                if not filepath.exists():
                    print(f"  WARNING: branch file missing: {filepath}, creating new branch", file=sys.stderr)
                    continue  # M5 fix: fall through to create new branch instead of losing data
                old = filepath.read_text(encoding="utf-8")
                # Combine old + new content
                merged_text = old + "\n" + header + "\n" + body
                # Resolve contradictions (last-writer-wins)
                merged_text = _resolve_contradictions(merged_text)
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
            branch_path = TREE_DIR / branch_file
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
            branch_file = TREE_DIR / node["file"]
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
    Uses word frequency + mycelium concept matching."""
    tags = set()
    text_lower = text.lower()

    # Match mycelium fused concepts present in text
    cb = get_codebook()
    for key, rule in cb["mycelium_rules"].items():
        for concept in rule["concepts"]:
            if concept in text_lower:
                tags.add(concept)

    # Extract high-frequency capitalized words as tags (entity detection)
    # Match both "Capitalized" and "SQLite" (mixed-case technical terms)
    entities = re.findall(r'\b[A-Z][A-Za-z]{2,}\b', text)
    # Adaptive threshold: count >= 2 for long texts, >= 1 for short texts
    _ent_thresh = 2 if len(text) > 500 else 1
    for entity, count in Counter(entities).most_common(5):
        if count >= _ent_thresh:
            tags.add(entity.lower())

    # Extract technical keywords generically
    tech_words = re.findall(r'\b[a-z]{4,}\b', text_lower)
    # Adaptive threshold: count >= 3 for long texts, >= 2 for short texts
    _kw_thresh = 3 if len(text) > 500 else 2
    for word, count in Counter(tech_words).most_common(10):
        if count >= _kw_thresh and word not in ("this", "that", "with", "from", "have",
                                        "been", "will", "pour", "dans", "avec",
                                        "sont", "dans", "plus", "tout", "mais"):
            tags.add(word)

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

    repos = _load_repos_registry()
    if not repos:
        return []

    current_repo = _REPO_PATH.resolve() if _REPO_PATH else None
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
            reg_path = _repos_registry_path()
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
    tree = load_tree()
    nodes = tree["nodes"]

    root_text = read_node("root", _tree=tree)
    loaded = [("root", root_text)]

    # P23: Auto-continue — if no query, use last session's concepts
    if not query and _REPO_PATH:
        index_path = _REPO_PATH / ".muninn" / "session_index.json"
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
            if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(_REPO_PATH or Path("."))

            # P20b: Pull relevant cross-repo knowledge from meta-mycelium
            query_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', query.lower())
            pulled = m.pull_from_meta(query_concepts=query_words, max_pull=200)
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
            filepath = TREE_DIR / node["file"]
            if filepath.exists():
                branch_contents[name] = filepath.read_text(encoding="utf-8", errors="ignore")
            else:
                # Fallback: use tags as content
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
        if _REPO_PATH:
            try:
                import math
                index_path = _REPO_PATH / ".muninn" / "session_index.json"
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
                                        prior = nodes[bname].get("usefulness") or 0.5
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
                # Debug: boost recall (recent errors) + usefulness
                w_recall = 0.20
                w_usefulness = 0.15
                w_rehearsal = 0.10
            elif stype == "explore":
                # Explore: boost activation (spread wider)
                w_activation = 0.30
                w_relevance = 0.30
                w_recall = 0.10
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
                    _other_temp = nodes[_sname].get("temperature", 0.5)
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
    if remaining_budget > 500 and _REPO_PATH:
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
        feedback_path = (_REPO_PATH or MUNINN_ROOT) / ".muninn" / "boot_feedback.json"
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
            ncd = _ncd(text, prev_text)
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
    sessions_dir = _REPO_PATH / ".muninn" / "sessions" if _REPO_PATH else MUNINN_ROOT / ".muninn" / "sessions"
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
            if query and _REPO_PATH:
                remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
                if remaining_budget > 500:
                    _load_relevant_sessions(
                        query, sessions_dir, latest.name, remaining_budget, output
                    )

    # P18: Surface known error fixes if query matches
    if query and _REPO_PATH:
        error_hints = _surface_known_errors(_REPO_PATH, query)
        if error_hints:
            output.append("\n=== known_fixes ===")
            output.append(error_hints)

    # H3: Surface Huginn insights at boot
    if _REPO_PATH:
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
    if _REPO_PATH:
        try:
            boot_manifest = {
                "branches": [name for name, _ in deduped if name != "root"],
                "query": query or "",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if _v8b_hint:
                boot_manifest["v8b_clarify"] = _v8b_hint
            manifest_path = _REPO_PATH / ".muninn" / "last_boot.json"
            manifest_path.write_text(json.dumps(boot_manifest), encoding="utf-8")
        except OSError:
            pass

    # KIComp: density scoring — drop low-information lines if over budget
    full_text = "\n".join(output)
    total_tokens = token_count(full_text)
    if total_tokens > BUDGET["max_loaded_tokens"]:
        full_text = _kicomp_filter(full_text, BUDGET["max_loaded_tokens"])

    return full_text


def recall(query: str) -> str:
    """P29: Mid-session memory search. Searches session index + .mn files + tree branches.

    Returns the most relevant lines from past sessions matching the query.
    Designed to be called via `muninn.py recall "search terms"` mid-conversation.
    """
    repo = _REPO_PATH or Path(".")
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
    if TREE_DIR.exists():
        for mn_file in TREE_DIR.glob("*.mn"):
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
    repo = _REPO_PATH or Path(".")

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
        if _CORE_DIR not in sys.path:
            sys.path.insert(0, _CORE_DIR)
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
    if include_branches and TREE_DIR.exists():
        activated_words = {c for c, _ in activated[:top_n]}
        branch_hits = []
        for mn_file in TREE_DIR.glob("*.mn"):
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
    repo = _REPO_PATH or Path(".")

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
        if _CORE_DIR not in sys.path:
            sys.path.insert(0, _CORE_DIR)
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
    repo = _REPO_PATH or Path(".")

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
            if _CORE_DIR not in sys.path:
                sys.path.insert(0, _CORE_DIR)
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
    repo = _REPO_PATH or Path(".")

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
    repo = _REPO_PATH or Path(".")

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


# ── DECODE ────────────────────────────────────────────────────────

def decode_line(line: str) -> str:
    cb = get_codebook()
    result = line

    reverse_rules = {v: k for k, v in cb["text_rules"].items()
                     if len(v) > 0 and v != k}
    for code in sorted(reverse_rules.keys(), key=len, reverse=True):
        if code in result:
            result = result.replace(code, reverse_rules[code])

    return result


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

    # 1. Read all cold branch contents
    contents = {}
    for name, node in cold_branches:
        filepath = TREE_DIR / node["file"]
        if filepath.exists():
            contents[name] = filepath.read_text(encoding="utf-8")

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
                _ncd(contents[m], contents[names[j]]) < ncd_threshold
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
        combined = _resolve_contradictions(combined)
        combined = _cue_distill(combined)
        combined = _extract_rules(combined)

        # Name the consolidated branch (strip existing _consolidated suffix to avoid stacking)
        base_leader = re.sub(r'(_consolidated)+$', '', leader)
        merged_name = f"{base_leader}_consolidated"

        # Write the consolidated file
        merged_file = f"{merged_name}.mn"
        merged_path = TREE_DIR / merged_file
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
            "access_count": sum(nodes.get(m, {}).get("access_count", 0) for m in members),
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
                old_path = TREE_DIR / node["file"]
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
    repo = _REPO_PATH or Path(".")
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
            branch_file = TREE_DIR / node.get("file", "")
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


def prune(dry_run: bool = True):
    """R4: promote hot, demote cold, kill dead. Uses temperature score."""
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

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
            fpath = TREE_DIR / bnode.get("file", "")
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
                ncd = _ncd(_branch_content[bi], _branch_content[bj])
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
            fpath = TREE_DIR / bnode.get("file", "")
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
            filepath = TREE_DIR / node["file"]
            if not filepath.exists():
                continue
            content = filepath.read_text(encoding="utf-8")
            original_lines = len(content.split("\n"))
            # Apply L9 (LLM compression) if branch is large enough
            compressed = _llm_compress(content, context=f"cold-branch:{name}")
            if compressed != content:
                filepath.write_text(compressed, encoding="utf-8")
                new_lines = len(compressed.split("\n"))
                node["lines"] = new_lines
                recompressed += 1
                print(f"  RE-COMPRESSED {name}: {original_lines} -> {new_lines} lines")

        # Sleep Consolidation (Wilson & McNaughton 1994)
        # Merge similar cold branches into single dense branches
        cold_branch_data = [(name, nodes[name]) for name, _ in cold if name in nodes]
        consolidated = _sleep_consolidate(cold_branch_data, nodes)

        # H1: Mode trip — psilocybine exploration during sleep
        # Create dream connections between distant clusters (BARE Wave model)
        try:
            if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(_REPO_PATH or Path("."))
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
            if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
            from mycelium import Mycelium
            m_regen = Mycelium(_REPO_PATH or Path("."))
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
                    dead_filepath = TREE_DIR / dead_file

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
                        survivor_filepath = TREE_DIR / surv_file
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
                                    combined = _cue_distill(combined)
                                    combined = _extract_rules(combined)

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
            filepath = TREE_DIR / node["file"]
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    print(f"  WARNING: could not delete {filepath}: {e}", file=sys.stderr)
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
        m = Mycelium(_REPO_PATH or Path(".").resolve())
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
    feedback_path = (_REPO_PATH or Path(".").resolve()) / ".muninn" / "boot_feedback.json"
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
    sessions_dir = (_REPO_PATH or Path(".").resolve()) / ".muninn" / "sessions"
    if sessions_dir.exists():
        mn_files = list(sessions_dir.glob("*.mn"))
        print(f"[SESSIONS] {len(mn_files)} compressed transcripts")
        if mn_files:
            newest = max(mn_files, key=lambda p: p.stat().st_mtime)
            print(f"  Latest: {newest.name}")
    else:
        print("[SESSIONS] No sessions directory")

    print("\n=== DIAGNOSE COMPLETE ===")


# ── READ (analysis) ──────────────────────────────────────────────

def analyze_file(filepath: Path) -> dict:
    cb = get_codebook()
    text = filepath.read_text(encoding="utf-8")
    lines = text.count("\n")
    chars = len(text)

    hits = {}
    for pattern, code in cb["text_rules"].items():
        count = text.count(pattern)
        if count > 0:
            saved_chars = count * (len(pattern) - len(code))
            if saved_chars > 0:
                hits[pattern] = {"count": count, "code": code, "saved": saved_chars}

    total_saved = sum(h["saved"] for h in hits.values())
    tokens_before = token_count(text)
    tokens_after = tokens_before - (total_saved // 4)  # approx savings

    return {
        "file": str(filepath), "lines": lines, "chars": chars,
        "tokens_est": tokens_before, "codebook_hits": hits,
        "chars_saved": total_saved, "tokens_after": tokens_after,
        "ratio": round(tokens_before / max(tokens_after, 1), 2),
    }


# ── BOOTSTRAP (cold start) ────────────────────────────────────────

def bootstrap_mycelium(repo_path: Path):
    """Cold start: scan repo files and feed the mycelium.

    Reads all human-written files (code, docs, config) and feeds them
    to the mycelium as co-occurrence observations. This bootstraps the
    living codebook from scratch on a new repo.
    """
    repo_path = repo_path.resolve()
    print(f"=== MUNINN BOOTSTRAP: {repo_path.name} ===")

    if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
    from mycelium import Mycelium

    m = Mycelium(repo_path)
    m.start_session()

    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv",
                 "dist", "build", "coverage", ".gradle", ".idea",
                 "data", "output", "cache", "caches", ".muninn"}

    file_count = 0
    for pattern in ["**/*.md", "**/*.txt", "**/*.py", "**/*.rs", "**/*.ts",
                    "**/*.js", "**/*.java", "**/*.c", "**/*.h", "**/*.toml",
                    "**/*.yaml", "**/*.yml", "**/*.cfg", "**/*.ini",
                    "**/*.mn"]:
        for f in repo_path.glob(pattern):
            parts = f.relative_to(repo_path).parts
            if any(p.startswith(".") or p in skip_dirs for p in parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if len(text) < 50_000:
                    m.observe_text(text)
                    file_count += 1
            except (PermissionError, OSError):
                continue

    m.save()
    print(f"  Scanned: {file_count} files")
    print(f"\n{m.status()}")

    rules = m.get_compression_rules()
    if rules:
        print(f"\n  Compression rules ({len(rules)}):")
        for key, rule in list(rules.items())[:15]:
            print(f"    {rule['concepts']} -> '{rule['form']}' (strength={rule['strength']})")

    # Generate root.mn (SOL.mn format) + WINTER_TREE.md + hooks
    generate_root_mn(repo_path, file_count, m)
    generate_winter_tree(repo_path, file_count, m)
    install_hooks(repo_path)

    # P40: Create branches from scanned files (not just root + mycelium)
    _bootstrap_branches(repo_path, skip_dirs)


def _bootstrap_branches(repo_path: Path, skip_dirs: set):
    """P40: Create branches from repo docs during bootstrap.

    Selects the most important markdown/text files (by size, descending),
    compresses each with compress_file, and auto-segments into branches
    via grow_branches_from_session. Caps at 20 files to keep bootstrap fast.
    """
    candidates = []
    for pattern in ["**/*.md", "**/*.txt"]:
        for f in repo_path.glob(pattern):
            parts = f.relative_to(repo_path).parts
            if any(p.startswith(".") or p in skip_dirs for p in parts):
                continue
            try:
                size = f.stat().st_size
                if 100 < size < 100_000:  # Skip tiny and huge files
                    candidates.append((size, f))
            except OSError:
                continue

    # Sort by size descending (bigger docs = more content), cap at 20
    candidates.sort(reverse=True)
    candidates = candidates[:20]

    if not candidates:
        return

    mn_dir = TREE_DIR
    mn_dir.mkdir(parents=True, exist_ok=True)

    total_branches = 0
    for _size, f in candidates:
        try:
            compressed = compress_file(f)
            if len(compressed.strip()) < 30:
                continue
            mn_temp = mn_dir / f"_bootstrap_{f.stem}.mn"
            mn_temp.write_text(compressed, encoding="utf-8")
            created = grow_branches_from_session(mn_temp)
            total_branches += created
            if mn_temp.exists():
                mn_temp.unlink()
        except Exception as exc:
            print(f"  WARNING: branch creation failed for {f.name}: {exc}", file=sys.stderr)
            continue

    if total_branches > 0:
        print(f"  P40: {len(candidates)} docs -> {total_branches} branches created")


def generate_root_mn(repo_path: Path, file_count: int, mycelium):
    """Generate root.mn in dense machine-optimal format (SOL.mn template)."""
    repo_path = repo_path.resolve()

    # Detect project info
    name = repo_path.name
    total_lines = 0
    file_map = []
    langs = Counter()
    ext_map = {
        ".py": "python", ".rs": "rust", ".ts": "typescript", ".js": "javascript",
        ".java": "java", ".c": "c", ".h": "c", ".go": "go", ".rb": "ruby",
        ".md": "markdown", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    }
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv",
                 "dist", "build", ".muninn", "data", "output", "cache"}

    for f in sorted(repo_path.rglob("*")):
        if not f.is_file():
            continue
        parts = f.relative_to(repo_path).parts
        if any(p.startswith(".") or p in skip_dirs for p in parts):
            continue
        ext = f.suffix.lower()
        if ext in ext_map:
            langs[ext_map[ext]] += 1
        try:
            lines = len(f.read_text(encoding="utf-8", errors="ignore").split("\n"))
            total_lines += lines
            rel = str(f.relative_to(repo_path)).replace("\\", "/")
            if lines > 50 and ext in ext_map:
                file_map.append((rel, lines))
        except (PermissionError, OSError):
            continue

    # Sort by size, keep top 15
    file_map.sort(key=lambda x: x[1], reverse=True)
    file_map = file_map[:15]

    # Main language
    main_lang = langs.most_common(1)[0][0] if langs else "unknown"

    # Detect deps from common files
    deps = []
    for dep_file in ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml"]:
        if (repo_path / dep_file).exists():
            deps.append(dep_file)

    # Entry point guess (largest code file)
    code_exts = {".py", ".rs", ".ts", ".js", ".java", ".c", ".go"}
    entry = next((f for f, l in file_map if Path(f).suffix in code_exts), file_map[0][0] if file_map else name)

    # Top mycelium concepts
    top_concepts = []
    if mycelium._db is not None:
        degree = mycelium._db.all_degrees()
        top_concepts = [c for c, _ in sorted(degree.items(), key=lambda x: -x[1])[:10]]
        n_conns = mycelium._db.connection_count()
    else:
        conns = mycelium.data.get("connections", {})
        n_conns = len(conns)
        concept_count = Counter()
        for key, conn in conns.items():
            parts = key.split("|")
            if len(parts) == 2:
                for p in parts:
                    concept_count[p] += conn["count"]
        top_concepts = [c for c, _ in concept_count.most_common(10)]

    # Recent commits
    recent = []
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--oneline", "-5", "--format=%as %s"],
            cwd=str(repo_path), capture_output=True, text=True, encoding="utf-8", timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    recent.append(line.strip())
    except Exception:
        pass

    # Build root.mn
    if mycelium._db is not None:
        n_fusions = len(mycelium._db.get_all_fusions())
    else:
        n_fusions = len(mycelium.data.get("fusions", {}))
    lines = [
        f"P:{name}|{main_lang}|{total_lines}L|{file_count}files",
        f"E:{entry}",
        f"S:bootstrap|{time.strftime('%Y-%m-%d')}|mycelium:{n_conns}conn,{n_fusions}fusions",
        "",
        "F:",
    ]
    for fpath, flines in file_map:
        lines.append(f"  {fpath} {flines}L")

    if top_concepts:
        lines.append("")
        lines.append(f"K:{','.join(top_concepts)}")

    if recent:
        lines.append("")
        lines.append("R:")
        for r in recent:
            lines.append(f"  {r}")

    content = "\n".join(lines)

    # Write to tree (load_tree FIRST to avoid init_tree overwriting root.mn)
    _refresh_tree_paths()
    TREE_DIR.mkdir(parents=True, exist_ok=True)
    tree = load_tree()
    root_path = TREE_DIR / "root.mn"
    root_path.write_text(content, encoding="utf-8")
    tree["nodes"]["root"]["lines"] = len(lines)
    tree["nodes"]["root"]["last_access"] = time.strftime("%Y-%m-%d")
    tree["nodes"]["root"]["tags"] = top_concepts[:7]
    save_tree(tree)

    from tokenizer import token_count
    tok = token_count(content)
    print(f"\n  root.mn generated: {len(lines)} lines, {tok} tokens")
    print(f"  Format: SOL.mn (machine-optimal)")


def generate_winter_tree(repo_path: Path, file_count: int, mycelium):
    """Generate WINTER_TREE.md (human-readable project overview)."""
    repo_path = repo_path.resolve()
    name = repo_path.name

    # Detect structure
    dirs = set()
    code_files = 0
    doc_files = 0
    for f in repo_path.rglob("*"):
        if not f.is_file():
            continue
        parts = f.relative_to(repo_path).parts
        skip = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build", ".muninn"}
        if any(p in skip for p in parts):
            continue
        if len(parts) > 1:
            dirs.add(parts[0])
        ext = f.suffix.lower()
        if ext in {".py", ".rs", ".ts", ".js", ".java", ".c", ".go"}:
            code_files += 1
        elif ext in {".md", ".txt"}:
            doc_files += 1

    if mycelium._db is not None:
        conns = mycelium._db.connection_count()
        fusions = mycelium._db.fusion_count()
    else:
        conns = len(mycelium.data.get("connections", {}))
        fusions = len(mycelium.data.get("fusions", {}))

    content = f"""# {name} — Winter Tree

Type: Auto-genere par Muninn bootstrap
Date: {time.strftime('%Y-%m-%d')}

## Structure

- Fichiers scannes: {file_count}
- Dossiers principaux: {', '.join(sorted(dirs)[:10])}
- Code: {code_files} fichiers
- Docs: {doc_files} fichiers

## Mycelium

- Connexions: {conns}
- Fusions: {fusions}

## TODO

- [ ] Verifier que le bootstrap a capture les bons concepts
- [ ] Lancer `muninn.py ingest <docs>` pour les documents de reference
- [ ] Utiliser le projet normalement — l'arbre grandit tout seul

## Notes

Ce fichier a ete genere automatiquement par `muninn.py bootstrap`.
Modifie-le librement — c'est ta carte de route.
"""

    wt_path = repo_path / "WINTER_TREE.md"
    if not wt_path.exists():
        wt_path.write_text(content, encoding="utf-8")
        print(f"  WINTER_TREE.md generated for human")
    else:
        print(f"  WINTER_TREE.md exists, skipped (not overwriting)")


def _repos_registry_path() -> Path:
    """Path to the shared repos registry (~/.muninn/repos.json)."""
    return Path.home() / ".muninn" / "repos.json"


def _load_repos_registry() -> dict:
    """Load the repos registry. Returns {repo_name: absolute_path_str, ...}."""
    reg_path = _repos_registry_path()
    if not reg_path.exists():
        return {}
    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        return data.get("repos", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _register_repo(repo_path: Path):
    """Register a repo in ~/.muninn/repos.json for P20c cross-repo discovery."""
    repo_path = repo_path.resolve()
    reg_path = _repos_registry_path()
    reg_path.parent.mkdir(parents=True, exist_ok=True)

    registry = {}
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            registry = {}

    repos = registry.get("repos", {})
    repo_key = repo_path.name
    repo_str = str(repo_path)

    if repos.get(repo_key) == repo_str:
        return  # Already registered with same path

    repos[repo_key] = repo_str
    registry["repos"] = repos
    registry["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    # Atomic write to prevent concurrent hook corruption
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(reg_path.parent), suffix=".tmp")
    fd_closed = False
    try:
        os.write(fd, json.dumps(registry, indent=2, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        fd_closed = True
        os.replace(tmp, str(reg_path))
    except Exception:
        if not fd_closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(f"  Repo registered: {repo_key} -> {repo_str}")


def install_hooks(repo_path: Path):
    """Install Claude Code hooks for automatic feed on PreCompact/SessionEnd/Stop.

    P32: Merges hook-by-hook instead of skipping when hooks key exists.
    Also registers repo in ~/.muninn/repos.json for P20c cross-repo discovery.
    """
    repo_path = repo_path.resolve()
    muninn_engine = Path(__file__).resolve()
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    feed_cmd = f'python "{muninn_engine}" feed --repo "{repo_path}"'
    stop_cmd = f'python "{muninn_engine}" feed --repo "{repo_path}" --trigger stop'
    required_hooks = {
        "PreCompact": [{"type": "command", "command": feed_cmd}],
        "SessionEnd": [{"type": "command", "command": feed_cmd}],
        "Stop": [{"type": "command", "command": stop_cmd}],
    }

    # Load existing settings or start fresh
    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            existing = {}

    existing_hooks = existing.get("hooks", {})
    installed = []

    # Merge hook-by-hook: add missing hooks, update stale paths
    for hook_name, hook_entries in required_hooks.items():
        if hook_name not in existing_hooks:
            existing_hooks[hook_name] = hook_entries
            installed.append(hook_name)
        else:
            # Check if existing hook points to a stale muninn.py path
            existing_cmds = [e.get("command", "") for e in existing_hooks[hook_name]]
            new_cmd = hook_entries[0]["command"]
            if any("muninn.py" in c for c in existing_cmds) and new_cmd not in existing_cmds:
                existing_hooks[hook_name] = hook_entries
                installed.append(f"{hook_name}(updated)")

    if not installed:
        print(f"  Hooks already up-to-date (PreCompact + SessionEnd + Stop)")
    else:
        existing["hooks"] = existing_hooks
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"  Hooks installed: {' + '.join(installed)}")

    # Register repo in ~/.muninn/repos.json for P20c cross-repo discovery
    _register_repo(repo_path)


# ── VERIFY (compression quality check) ────────────────────────────

def verify_compression(filepath: Path):
    """Compress -> report what was kept, what was lost, quality score.

    Checks:
    1. Fact retention: are all numbers/metrics preserved?
    2. Entity retention: are all named entities preserved?
    3. Compression ratio achieved
    4. Learned rules report (what the mycelium contributed)
    """
    original = filepath.read_text(encoding="utf-8")
    compressed = compress_file(filepath)

    # Extract facts from original and compressed
    orig_facts = extract_facts(original)
    comp_facts = extract_facts(compressed)

    # Find preserved and lost facts
    preserved = [f for f in orig_facts if f in compressed]
    lost = [f for f in orig_facts if f not in compressed]

    # Token counts (real if tiktoken installed, estimate otherwise)
    orig_tokens, tok_method = count_tokens(original)
    comp_tokens, _ = count_tokens(compressed)
    ratio = orig_tokens / max(comp_tokens, 1)

    # Report learned rules contribution
    cb = get_codebook()
    learned_fillers = cb.get("learned_fillers", [])
    learned_abbrevs = cb.get("learned_abbreviations", {})

    # Count how many learned fillers were actually stripped
    filler_hits = 0
    for filler in learned_fillers:
        filler_hits += len(re.findall(rf"\b{re.escape(filler)}\b", original, re.IGNORECASE))

    # Count abbreviation hits
    abbrev_hits = 0
    for long_form in learned_abbrevs:
        abbrev_hits += len(re.findall(rf"\b{re.escape(long_form)}\b", original, re.IGNORECASE))

    print(f"=== MUNINN VERIFY: {filepath.name} ===")
    print(f"\n  Compression ({tok_method}):")
    print(f"    {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}, -{(orig_tokens - comp_tokens) / max(orig_tokens, 1) * 100:.0f}%)")
    print(f"\n  Facts ({len(orig_facts)} found):")
    print(f"    Preserved: {len(preserved)}/{len(orig_facts)}")
    if lost:
        print(f"    Lost: {lost[:10]}")
    else:
        print(f"    Lost: none")
    print(f"\n  Mycelium contribution:")
    print(f"    Learned fillers: {len(learned_fillers)} rules, {filler_hits} hits in this file")
    print(f"    Learned abbreviations: {len(learned_abbrevs)} rules, {abbrev_hits} hits in this file")
    print(f"    Mycelium fusions (L6): {len(cb['mycelium_rules'])} rules")
    print(f"\n  Quality score: ", end="")
    fact_retention = len(preserved) / max(len(orig_facts), 1)
    if fact_retention >= 0.9 and ratio >= 2.0:
        print(f"EXCELLENT (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    elif fact_retention >= 0.7 and ratio >= 1.5:
        print(f"GOOD (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    elif fact_retention >= 0.5:
        print(f"OK (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    else:
        print(f"POOR (facts={fact_retention:.0%}, ratio=x{ratio:.1f}) — losing too many facts")


# ── FEED (P1 — hooks pipeline) ────────────────────────────────────

def _compress_code_blocks(text: str) -> str:
    """P17: Compress code blocks in text — keep signatures, drop bodies.

    Replaces ```...``` blocks with function/class signatures + '...' placeholder.
    Non-code blocks (e.g., ```json, ```yaml) are kept as-is if short (<5 lines).
    """
    def _compress_block(match):
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2)

        # Keep short blocks as-is (config, output, etc.)
        lines = code.strip().split("\n")
        if len(lines) <= 4:
            return match.group(0)

        # For code: extract signatures (def, class, function, const, etc.)
        sigs = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(def |class |async def |function |const |let |var |export |import |from )", stripped):
                sigs.append(stripped)
            elif re.match(r"^(#|//|/\*)", stripped) and len(stripped) < 80:
                sigs.append(stripped)  # keep short comments

        if sigs:
            return f"```{lang}\n" + "\n".join(sigs) + "\n  ...\n```"
        else:
            # No signatures found — keep first 2 lines + ellipsis
            return f"```{lang}\n" + "\n".join(lines[:2]) + "\n  ...\n```"

    return re.sub(r"```(\w*)\n(.*?)```", _compress_block, text, flags=re.DOTALL)


def _parse_json_conversation(filepath: Path) -> list[str]:
    """P38: Parse claude.ai JSON export (conversations format)."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return []

    texts = []
    # Handle various JSON conversation formats
    messages = []
    if isinstance(data, dict):
        # claude.ai format: {"chat_messages": [...]} or {"conversation": [...]}
        messages = data.get("chat_messages", data.get("conversation",
                   data.get("messages", data.get("content", []))))
    elif isinstance(data, list):
        messages = data

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        # Extract text content
        content = msg.get("content", msg.get("text", ""))
        if isinstance(content, str) and len(content.strip()) >= 10:
            texts.append(content.strip())
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    t = part.get("text", "")
                    if len(t.strip()) >= 10:
                        texts.append(t.strip())
                elif isinstance(part, str) and len(part.strip()) >= 10:
                    texts.append(part.strip())
    return texts


def _parse_markdown_conversation(filepath: Path) -> list[str]:
    """P38: Parse markdown conversation (## Human / ## Assistant headers)."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    texts = []
    current = []
    for line in text.split("\n"):
        if re.match(r'^##\s*(Human|Assistant|User|Claude)', line, re.IGNORECASE):
            if current:
                block = "\n".join(current).strip()
                if len(block) >= 10:
                    texts.append(block)
                current = []
        else:
            current.append(line)
    if current:
        block = "\n".join(current).strip()
        if len(block) >= 10:
            texts.append(block)
    return texts


def _detect_transcript_format(filepath: Path) -> str:
    """P38: Detect transcript format from file content.

    Returns: 'jsonl', 'json', 'markdown', or 'unknown'.
    """
    try:
        first_bytes = filepath.read_bytes()[:500]
        first_text = first_bytes.decode("utf-8", errors="ignore").strip()
    except OSError:
        return "unknown"

    # JSONL: first line is a valid JSON object
    first_line = first_text.split("\n")[0].strip()
    if first_line.startswith("{"):
        try:
            obj = json.loads(first_line)
            # Check if it's a single JSON file (not JSONL)
            # JSONL = multiple lines starting with {
            lines = first_text.split("\n")
            json_lines = sum(1 for l in lines[:5] if l.strip().startswith("{"))
            if json_lines >= 2:
                return "jsonl"
            # Single JSON object with known keys = could be JSONL (1 msg) or json conversation
            if isinstance(obj, dict):
                if any(k in obj for k in ("messages", "chat_messages", "conversation", "content")):
                    return "json"
                # Single JSONL line (e.g. {"type": "user", ...})
                if "type" in obj or "role" in obj:
                    return "jsonl"
        except json.JSONDecodeError:
            pass

    # JSON: starts with [ (array of messages). Don't read whole file to validate —
    # if first bytes look like JSON array and it's not JSONL, assume json.
    if first_text.startswith("["):
        return "json"

    # Markdown: contains ## headers (Human/Assistant or any section)
    if re.search(r'^#{1,3}\s+\S', first_text, re.MULTILINE):
        return "markdown"

    return "unknown"


def parse_transcript(jsonl_path: Path) -> list[str]:
    """Parse a transcript and extract text messages.

    P38: Auto-detects format: JSONL (Claude Code), JSON (claude.ai), markdown.
    L0 FILTER: strips tool results (77% of transcript) down to 1-line summaries.
    Keeps: user messages, assistant text, tool call names + args (not results).
    """
    # P38: Multi-format detection
    fmt = _detect_transcript_format(jsonl_path)
    if fmt == "json":
        return _parse_json_conversation(jsonl_path)
    elif fmt == "markdown":
        return _parse_markdown_conversation(jsonl_path)
    # Default: JSONL (Claude Code) — fall through to original parser

    # P28: Claude verbal tics — full sentences that carry zero information
    _CLAUDE_TICS = re.compile(
        r"^("
        r"Let me (?:read|check|look|examine|search|find|see|verify|review|update|analyze|explore|open)"
        r"|I'll (?:now |start |begin |go ahead and )?"
          r"(?:read|check|look|examine|search|find|see|verify|review|update|analyze|fix|implement|create|add|make|write)"
        r"|(?:Here's|Here is) what (?:I found|I see|the .+ looks like|we have)"
        r"|(?:Now |OK(?:ay)?,? )?(?:let me|I'll) (?:take a look|have a look|investigate|dig into)"
        r"|(?:Great|Perfect|Good|Excellent|Sure|Alright|Got it|Understood)[.!,]?\s*(?:Let me|I'll|Now)?"
        r"|Looking (?:at|into|through) (?:the |this |that )?"
        r"|I (?:can see|notice|observe) (?:that )?"
        r"|(?:Based on|From) (?:the |my |this |what )?(?:analysis|review|reading|examination|investigation)"
        r"|This (?:looks|seems|appears) (?:like |to be )?"
        r"|I've (?:made|completed|finished|updated|fixed|implemented|added|created) the"
        r")",
        re.IGNORECASE
    )
    texts = []
    # P27: Track file reads — only keep last read per file
    file_reads = {}  # file_path -> (index_in_texts, summary, result)

    with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            content = message.get("content", [])

            if isinstance(content, str):
                texts.append(content)
                continue

            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "text":
                    text = block.get("text", "")
                    if len(text) >= 20:
                        # P17: compress code blocks in text
                        if "```" in text:
                            text = _compress_code_blocks(text)
                        # P28: Strip Claude verbal tics prefix (keep content after tic)
                        filtered_lines = []
                        for tline in text.split("\n"):
                            stripped = tline.strip()
                            m = _CLAUDE_TICS.match(stripped)
                            if m:
                                # Keep the rest of the line after the tic
                                remainder = stripped[m.end():].strip().lstrip(".,;:!").strip()
                                if len(remainder) >= 10:
                                    filtered_lines.append(remainder)
                                # else: pure tic sentence, drop entirely
                            else:
                                filtered_lines.append(tline)
                        text = "\n".join(filtered_lines).strip()
                        if len(text) >= 10:
                            texts.append(text)

                elif btype == "tool_use":
                    # L0: keep tool name + key args as 1-line summary
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    if name in ("Read", "read"):
                        fpath = inp.get('file_path', '?')
                        summary = f"[read {fpath}]"
                        # P27: mark previous reads of same file for removal
                        if fpath in file_reads:
                            old_idx = file_reads[fpath]
                            texts[old_idx] = None  # mark tool_use for removal
                            # Also mark the tool_result that follows (-> ...)
                            if old_idx + 1 < len(texts) and texts[old_idx + 1] and texts[old_idx + 1].startswith("->"):
                                texts[old_idx + 1] = None
                        file_reads[fpath] = len(texts)
                    elif name in ("Edit", "edit"):
                        summary = f"[edit {inp.get('file_path', '?')}]"
                    elif name in ("Write", "write"):
                        summary = f"[write {inp.get('file_path', '?')}]"
                    elif name in ("Bash", "bash"):
                        cmd = inp.get("command", "?")[:80]
                        summary = f"[bash: {cmd}]"
                    elif name in ("Grep", "grep"):
                        summary = f"[grep '{inp.get('pattern', '?')}' in {inp.get('path', '.')}]"
                    elif name in ("Glob", "glob"):
                        summary = f"[glob {inp.get('pattern', '?')}]"
                    elif name == "Agent":
                        summary = f"[agent: {inp.get('description', '?')}]"
                    else:
                        summary = f"[{name}]"
                    texts.append(summary)

                elif btype == "tool_result":
                    # L0: strip tool results to first line only
                    rc = block.get("content", "")
                    if isinstance(rc, str) and rc.strip():
                        first_line = rc.split("\n")[0][:100]
                        if first_line.strip():
                            texts.append(f"-> {first_line}")

    # P27: Remove None-marked duplicate reads
    texts = [t for t in texts if t is not None]

    return texts


def feed_from_transcript(jsonl_path: Path, repo_path: Path):
    """Feed the mycelium from a single transcript JSONL file.
    V6A: Per-message arousal via VADER -> passed to observe() for emotional tagging.
    Chunked: saves every FEED_CHUNK_SIZE messages to avoid timeout on large transcripts.
    Resumable: tracks offset in .muninn/feed_progress.json to resume after interruption.
    """
    FEED_CHUNK_SIZE = 50  # save mycelium every N messages

    if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
    from mycelium import Mycelium

    # Resume support: check how many messages we already fed for this file
    progress_path = repo_path / ".muninn" / "feed_progress.json"
    progress = {}
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            progress = {}

    file_key = jsonl_path.name
    file_size = jsonl_path.stat().st_size
    prev = progress.get(file_key, {})
    # If file size changed since last progress, start fresh (file grew)
    offset = prev.get("offset", 0) if prev.get("size", 0) == file_size else 0

    texts = parse_transcript(jsonl_path)
    if not texts:
        print(f"  No text messages found in {jsonl_path.name}")
        return 0, []

    if offset >= len(texts):
        print(f"  Already fed {offset}/{len(texts)} messages from {jsonl_path.name}")
        return len(texts), texts

    if offset > 0:
        print(f"  Resuming feed from message {offset}/{len(texts)} ({jsonl_path.name})")

    m = Mycelium(repo_path)
    m.start_session()

    fed = 0
    for i in range(offset, len(texts)):
        text = texts[i]
        # V6A: Score arousal per message for emotional tagging
        msg_arousal = 0.0
        if _HAS_SENTIMENT:
            s = score_sentiment(text)
            msg_arousal = s["arousal"]
        m.observe_text(text, arousal=msg_arousal)
        fed += 1

        # Checkpoint every FEED_CHUNK_SIZE messages
        if fed % FEED_CHUNK_SIZE == 0:
            m.save()
            progress[file_key] = {"offset": offset + fed, "size": file_size}
            progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    # Final save
    m.save()
    progress[file_key] = {"offset": len(texts), "size": file_size}
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    return len(texts), texts  # Return texts for reuse by compress_transcript


def _semantic_rle(texts: list[str]) -> list[str]:
    """Collapse debug/retry loops in transcript messages.

    Detects sequences where the same action is retried multiple times
    (error→fix→error→fix→success) and condenses them.

    Patterns detected:
    1. Repeated similar error messages → keep first + last + count
    2. Retry sequences (try→fail→try→fail→success) → "tried A,B(fail); C worked"
    3. Consecutive reads of related files → merge into one line

    Returns filtered texts list (shorter or same length).
    """
    if len(texts) < 4:
        return texts

    result = []
    i = 0
    collapsed_count = 0

    # Error/retry detection patterns
    error_pats = re.compile(
        r'(?:error|fail|exception|traceback|errno|cannot|could not|unable|'
        r'not found|permission denied|syntax error|import error|'
        r'TypeError|ValueError|KeyError|AttributeError|NameError|IndexError|'
        r'FileNotFoundError|ModuleNotFoundError)',
        re.IGNORECASE
    )
    retry_pats = re.compile(
        r'(?:let me try|trying|attempt|retry|let me fix|fixing|'
        r'let me check|checking again|running again|re-run)',
        re.IGNORECASE
    )

    while i < len(texts):
        text = texts[i]

        # Detect start of error/retry loop
        if error_pats.search(text) and i + 2 < len(texts):
            # Scan ahead for a retry loop
            loop_start = i
            loop_errors = [text]
            loop_retries = []
            j = i + 1

            while j < len(texts):
                t = texts[j]
                is_error = bool(error_pats.search(t))
                is_retry = bool(retry_pats.search(t))

                if is_error:
                    loop_errors.append(t)
                    j += 1
                elif is_retry:
                    loop_retries.append(t)
                    j += 1
                else:
                    break

            loop_len = j - loop_start

            if loop_len >= 3 and (len(loop_errors) >= 2 or len(loop_retries) >= 2):
                # Collapse: keep first error, count, and the resolution
                first_err = loop_errors[0][:120]
                last_err = loop_errors[-1][:120]
                # Check if next message after loop is a success/fix
                resolution = ""
                if j < len(texts):
                    next_text = texts[j]
                    if not error_pats.search(next_text):
                        resolution = " -> " + next_text[:80]
                        j += 1

                collapsed = (
                    f"[RLE:{len(loop_errors)} errors, {len(loop_retries)} retries] "
                    f"{first_err}"
                )
                if last_err != first_err:
                    collapsed += f" ... {last_err}"
                collapsed += resolution

                result.append(collapsed)
                collapsed_count += loop_len
                i = j
                continue

        result.append(text)
        i += 1

    if collapsed_count > 0:
        print(f"  Semantic RLE: {collapsed_count} messages collapsed "
              f"({len(texts)} -> {len(result)})", file=sys.stderr)

    return result


def compress_transcript(jsonl_path: Path, repo_path: Path, texts: list = None) -> tuple:
    """Compress a transcript JSONL into a dense .mn session file.

    Extracts user+assistant messages, compresses each with the 7-layer
    pipeline, writes result to .muninn/sessions/<timestamp>.mn.
    Returns the path to the written .mn file.
    Accepts pre-parsed texts to avoid double parse_transcript call.
    """
    if texts is None:
        texts = parse_transcript(jsonl_path)
    if not texts:
        return None, None

    # Strip secrets before compression
    for i, text in enumerate(texts):
        for pat in _SECRET_PATTERNS:
            texts[i] = re.sub(pat, '[REDACTED]', texts[i])

    # Semantic RLE: collapse debug/retry loops
    # Detects sequences of similar messages (error→retry→error→retry→success)
    # and condenses them into a summary.
    texts = _semantic_rle(texts)

    # Build a pseudo-markdown from transcript messages for compress_section
    sections = []
    current_topic = []
    current_header = "## Session context"

    for text in texts:
        # If text looks like a new topic (long enough, starts with capital or #)
        if text.startswith("## ") or text.startswith("# "):
            if current_topic:
                sections.append((current_header, current_topic))
            current_header = text if text.startswith("## ") else f"## {text.lstrip('# ')}"
            current_topic = []
        else:
            current_topic.append(text)

    if current_topic:
        sections.append((current_header, current_topic))

    # If no markdown headers found, chunk by message groups
    if len(sections) == 1 and len(texts) > 10:
        sections = []
        chunk_size = max(5, len(texts) // 6)  # ~6 sections max
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i:i + chunk_size]
            # Use first non-trivial line as header
            header_text = chunk[0][:80].strip()
            header_text = re.sub(r"[#\n]", "", header_text)
            sections.append((f"## {header_text}", chunk))

    # Compress each section (tags applied AFTER L9, not here)
    # B12: Emit ## headers so grow_branches_from_session() can segment by topic
    output = ["# MUNINN|session_compressed"]
    for header, lines in sections:
        compressed = compress_section(header, lines)
        if compressed and len(compressed) > 5:
            # Preserve ## header for grow_branches segmentation
            if header.startswith("## "):
                output.append(header)
            output.append(compressed)

    # Add facts summary at the end
    all_text = "\n".join(texts)
    facts = extract_facts(all_text)
    if facts:
        output.append(f"?FACTS:{' | '.join(facts[:30])}")

    result = "\n".join(output)

    # P26: Dedup compressed lines (exact + normalized)
    seen_hashes = set()
    deduped_lines = []
    for dline in result.split("\n"):
        if dline.startswith("#") or dline.startswith("?FACTS"):
            deduped_lines.append(dline)
            continue
        # Normalize: lowercase, strip extra spaces, remove punctuation for fuzzy match
        norm = re.sub(r'[^\w\s]', '', dline.lower()).strip()
        norm = re.sub(r'\s+', ' ', norm)
        if not norm:
            deduped_lines.append(dline)  # preserve blank lines as structural separators
            continue
        if norm in seen_hashes:
            continue
        seen_hashes.add(norm)
        deduped_lines.append(dline)
    result = "\n".join(deduped_lines)

    # Contradiction resolution (last-writer-wins on numeric facts)
    result = _resolve_contradictions(result)

    # L10: Cue Distillation — BEFORE L9 (filter generic knowledge early)
    result = _cue_distill(result)

    # L11: Rule Extraction — factorize repeated key=value patterns
    result = _extract_rules(result)

    # Layer 9: SKIP on transcripts — regex already achieves x100+ on tool-heavy
    # transcripts, L9 adds no value (tested: 3014 vs 3319 tokens, L9 is worse).
    # L9 is only useful on raw prose (compress_file, ingest, bootstrap).

    # P14: Tag memory types AFTER L9 (so tags survive rewriting)
    tagged_lines = []
    for rline in result.split("\n"):
        if rline.strip() and not rline.startswith("#") and not rline.startswith("?FACTS"):
            tagged_lines.append(tag_memory_type(rline))
        else:
            tagged_lines.append(rline)
    result = "\n".join(tagged_lines)

    # P25: Priority survival — if too many lines, drop low-priority first
    _TAG_PRIORITY = {"D>": 5, "B>": 4, "E>": 3, "F>": 3, "A>": 2}
    result_tokens = token_count(result)
    max_session_tokens = 3000  # session .mn should fit in ~3K tokens
    if result_tokens > max_session_tokens:
        lines_with_priority = []
        for pline in result.split("\n"):
            stripped = pline.strip()
            if stripped.startswith("#") or stripped.startswith("?FACTS"):
                lines_with_priority.append((99, pline))  # always keep
            else:
                priority = 1  # default: untagged
                for tag, prio in _TAG_PRIORITY.items():
                    if stripped.startswith(tag):
                        priority = prio
                        break
                lines_with_priority.append((priority, pline))
        # Sort by priority (descending), keep highest priority lines until budget
        # But preserve original order within same priority
        by_priority = sorted(enumerate(lines_with_priority),
                             key=lambda x: (-x[1][0], x[0]))
        kept_indices = set()
        running_tokens = 0
        for orig_idx, (prio, pline) in by_priority:
            line_tokens = max(1, len(pline) // 4)  # estimate, avoid per-line tiktoken
            if running_tokens + line_tokens <= max_session_tokens:
                kept_indices.add(orig_idx)
                running_tokens += line_tokens
        # Rebuild in original order
        result = "\n".join(
            pline for i, (_, pline) in enumerate(lines_with_priority)
            if i in kept_indices
        )

    # Write to .muninn/sessions/ — dedup by transcript source
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    mn_path = sessions_dir / f"{timestamp}.mn"

    # Dedup: check if this transcript was already compressed (same source, same size)
    # Prevents PreCompact+SessionEnd and repeated Stop hooks from creating duplicate .mn files
    dedup_path = repo_path / ".muninn" / "compressed_transcripts.json"
    dedup_state = {}
    if dedup_path.exists():
        try:
            dedup_state = json.loads(dedup_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dedup_state = {}

    source_key = jsonl_path.name if 'jsonl_path' in dir() else timestamp
    source_size = jsonl_path.stat().st_size if 'jsonl_path' in dir() and jsonl_path.exists() else 0
    prev_entry = dedup_state.get(source_key, {})

    if prev_entry.get("size", 0) == source_size and source_size > 0:
        # Same transcript, same size — overwrite the existing .mn instead of creating new one
        existing_mn = sessions_dir / prev_entry.get("mn_file", "")
        if existing_mn.exists():
            mn_path = existing_mn  # overwrite same file

    mn_path.write_text(result, encoding="utf-8")

    # Track which transcript produced which .mn
    dedup_state[source_key] = {"size": source_size, "mn_file": mn_path.name, "timestamp": timestamp}
    dedup_path.write_text(json.dumps(dedup_state, indent=2), encoding="utf-8")

    # Keep only last 10 session files (oldest get pruned)
    session_files = sorted(sessions_dir.glob("*.mn"))
    for old_file in session_files[:-10]:
        old_file.unlink()

    orig_tokens, tok_method = count_tokens(all_text)
    comp_tokens = token_count(result)
    ratio = orig_tokens / max(comp_tokens, 1)
    print(f"MUNINN SESSION ({tok_method}): {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}) -> {mn_path.name}")

    # P16: Append 1-line session summary to root.mn
    _append_session_log(repo_path, result, ratio)

    # P18: Extract error/fix pairs for auto-surfacing
    _extract_error_fixes(repo_path, result)

    # V10A: Score sentiment on RAW messages (before compression strips emotional cues)
    session_sentiment = None
    if _HAS_SENTIMENT:
        session_sentiment = score_session(texts)

    # P22: Update session index for future retrieval
    _danger = _update_session_index(repo_path, mn_path, result, ratio, session_sentiment)

    # I1: Piggyback danger_score into session_sentiment for grow_branches_from_session
    if _danger and _danger > 0:
        if session_sentiment is None:
            session_sentiment = {"mean_valence": 0.0, "mean_arousal": 0.0,
                                 "peak_valence": 0.0, "peak_arousal": 0.0,
                                 "n_positive": 0, "n_negative": 0, "n_neutral": 0}
        session_sentiment["danger_score"] = _danger

    return mn_path, session_sentiment


def _update_session_index(repo_path: Path, mn_path: Path, compressed: str, ratio: float,
                          session_sentiment: dict = None):
    """P22: Add session entry to .muninn/session_index.json for boot search."""
    index_path = repo_path / ".muninn" / "session_index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        if not isinstance(index, list):
            index = []
    except (json.JSONDecodeError, OSError):
        index = []

    # Extract tagged lines (D>, B>, F> are high-value)
    tagged = []
    for line in compressed.split("\n"):
        stripped = line.strip()
        for tag in ("D>", "B>", "F>", "E>", "A>"):
            if stripped.startswith(tag):
                tagged.append(stripped[:120])
                break

    # Extract key concepts (top words by frequency, excluding short/common)
    words = re.findall(r'[A-Za-z]{4,}', compressed.lower())
    stop = {"this", "that", "with", "from", "have", "been", "will", "into",
            "also", "just", "more", "some", "then", "than", "when", "what",
            "each", "line", "file", "text", "here", "there", "about"}
    word_freq = {}
    for w in words:
        if w not in stop:
            word_freq[w] = word_freq.get(w, 0) + 1
    top_concepts = sorted(word_freq, key=word_freq.get, reverse=True)[:10]

    # I1: Danger Theory DCA (Greensmith 2008)
    # Compute session danger signal from error rate, retry patterns, topic switches.
    _total_lines = max(1, len(compressed.split("\n")))
    _error_lines = sum(1 for l in compressed.split("\n") if l.strip().startswith("E>"))
    _error_rate = _error_lines / _total_lines
    _retry_count = len(re.findall(r'(?i)\b(retry|debug|fix|error|traceback|failed)\b', compressed))
    _retry_rate = min(1.0, _retry_count / max(1, _total_lines) * 5)
    _topic_switches = 0
    _prev_concepts = set()
    for line in compressed.split("\n"):
        stripped = line.strip()
        if stripped.startswith("D>") or stripped.startswith("B>"):
            cur_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
            if _prev_concepts and len(cur_words & _prev_concepts) == 0:
                _topic_switches += 1
            _prev_concepts = cur_words
    _switch_rate = min(1.0, _topic_switches / max(1, _total_lines) * 10)
    _chaos_ratio = min(1.0, max(0.0, 1.0 - (ratio / 5.0))) if ratio > 0 else 0.5
    _danger_score = round(
        0.4 * _error_rate + 0.3 * _retry_rate + 0.2 * _switch_rate + 0.1 * _chaos_ratio, 4)

    entry = {
        "file": mn_path.name,
        "date": time.strftime("%Y-%m-%d"),
        "ratio": round(ratio, 1),
        "concepts": top_concepts,
        "tagged": tagged[:15],  # max 15 tagged lines per session
        "danger_score": _danger_score,  # I1
    }

    # V10A: VADER sentiment (scored on RAW messages in compress_transcript)
    if session_sentiment is not None:
        entry["sentiment"] = {
            "mean_valence": session_sentiment["mean_valence"],
            "mean_arousal": session_sentiment["mean_arousal"],
            "peak_valence": session_sentiment["peak_valence"],
            "peak_arousal": session_sentiment["peak_arousal"],
            "n_positive": session_sentiment["n_positive"],
            "n_negative": session_sentiment["n_negative"],
            "n_neutral": session_sentiment["n_neutral"],
        }
        # V10B: Russell circumplex mapping — emotional label for the session
        try:
            from sentiment import circumplex_map
            affect = circumplex_map(
                session_sentiment["mean_valence"],
                session_sentiment["mean_arousal"],
            )
            entry["sentiment"]["quadrant"] = affect["quadrant"]
            entry["sentiment"]["label"] = affect["label"]
        except ImportError:
            pass

    # Dedup by filename
    index = [e for e in index if e.get("file") != mn_path.name]
    index.append(entry)

    # Keep last 50 sessions in index (even if .mn files are pruned to 10)
    index = index[-50:]
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    return _danger_score  # I1: propagate to grow_branches_from_session


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
        mn_file = sessions_dir / entry["file"]
        if not mn_file.exists():
            continue
        text = mn_file.read_text(encoding="utf-8")
        tokens = token_count(text)
        if tokens > budget:
            continue
        output.append(f"=== relevant_session ({entry['file']}, {entry.get('date', '?')}) ===")
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
            if not any(e["error"] == entry["error"] for e in errors):
                errors.append(entry)

    # Keep last 50 entries
    errors = errors[-50:]
    errors_path.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")


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
        # Check if query words overlap with error text
        # Strip punctuation for matching (e.g. "TypeError:" should match "TypeError")
        error_words = set(re.findall(r'[a-z0-9_]+', entry["error"].lower()))
        query_words = set(re.findall(r'[a-z0-9_]+', query_lower))
        overlap = error_words & query_words
        if len(overlap) >= 1:  # at least 1 word match
            hints.append(f"KNOWN: {entry['error']} -> FIX: {entry['fix']}")
    return "\n".join(hints[:3])  # max 3 hints


def _update_usefulness(repo_path: Path, jsonl_path: Path):
    """P36: Boot Feedback Loop — score which boot branches were actually useful.

    Compares concepts from the session transcript against concepts from branches
    loaded at boot. Branches whose concepts appeared in the session get a higher
    usefulness_score in tree.json. This adapts scoring per-repo over time.
    """
    manifest_path = repo_path / ".muninn" / "last_boot.json"
    if not manifest_path.exists():
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    boot_branches = manifest.get("branches", [])
    if not boot_branches:
        return

    # Extract concepts from session transcript
    session_concepts = set()
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, str):
                        words = re.findall(r'[a-zA-Z]{4,}', content.lower())
                        session_concepts.update(words)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                words = re.findall(r'[a-zA-Z]{4,}', part["text"].lower())
                                session_concepts.update(words)
                except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return

    if not session_concepts:
        return

    # Load tree and score branches
    tree = load_tree()
    nodes = tree["nodes"]
    tree_dir = _get_tree_dir()
    updated = False

    # V2B fix: compute mean td_value across all branches for proper Bellman backup
    _all_td = [nodes[b].get("td_value", 0.5) for b in boot_branches
                if b in nodes and "::" not in b]
    _mean_td = sum(_all_td) / max(1, len(_all_td)) if _all_td else 0.5

    for bname in boot_branches:
        if bname not in nodes or "::" in bname:  # skip virtual branches
            continue
        node = nodes[bname]
        bfile = tree_dir / node.get("file", "")
        if not bfile.exists():
            continue
        try:
            branch_text = bfile.read_text(encoding="utf-8")
        except OSError:
            continue

        branch_concepts = set(re.findall(r'[a-zA-Z]{4,}', branch_text.lower()))
        if not branch_concepts:
            continue

        # Usefulness = fraction of branch concepts that appeared in session
        overlap = branch_concepts & session_concepts
        reward = len(overlap) / len(branch_concepts)  # r_t in [0, 1]

        # V2B: TD-Learning reward prediction error (Schultz, Dayan, Montague 1997)
        # delta_t = r_t + gamma * V(s_next) - V(s_t)
        # V(s_t) <- V(s_t) + alpha * delta_t
        # gamma=0.9 (future discount), alpha=0.1 (learning rate)
        _gamma = 0.9
        _alpha_td = 0.1
        v_current = node.get("td_value", 0.5)  # V(s), default 0.5
        # V(s_next) ~ mean V across all branches (mean-field Bellman backup)
        v_next = _mean_td
        delta = reward + _gamma * v_next - v_current
        v_new = v_current + _alpha_td * delta
        v_new = max(0.0, min(1.0, v_new))  # clamp [0, 1]
        node["td_value"] = round(v_new, 4)
        node["td_delta"] = round(delta, 4)  # store last delta for debugging

        # Usefulness updated via EMA as before, now also informed by TD
        # Branches with positive delta (better than expected) get boosted
        old_score = node.get("usefulness", 0.5)
        # Blend: 70% old + 30% reward, plus TD bonus (delta > 0 = surprise boost)
        td_bonus = max(0.0, delta) * 0.1  # positive surprise adds up to +0.1
        node["usefulness"] = round(max(0.0, min(1.0, 0.7 * old_score + 0.3 * reward + td_bonus)), 3)

        # V4B: EWC Fisher importance (Kirkpatrick et al. 2017)
        # F_i = proxy for how critical this branch is to system performance.
        # Computed as normalized(access_count * usefulness * td_value).
        # High-F branches get slower decay in _ebbinghaus_recall.
        _ac = node.get("access_count", 0)
        _u = node["usefulness"]
        _tv = node.get("td_value", 0.5)
        # Raw Fisher: product of usage signals, normalize later
        _fisher_raw = _ac * _u * _tv
        node["_fisher_raw"] = round(_fisher_raw, 4)

        updated = True

    # V4B: Normalize Fisher importance to [0, 1] across all updated branches
    if updated:
        max_fisher = max((nodes[b].get("_fisher_raw", 0) for b in boot_branches
                          if b in nodes), default=1.0)
        for bname in boot_branches:
            if bname in nodes and "_fisher_raw" in nodes[bname]:
                if max_fisher > 0:
                    nodes[bname]["fisher_importance"] = round(
                        nodes[bname]["_fisher_raw"] / max_fisher, 4)
                else:
                    nodes[bname]["fisher_importance"] = 0.0
                del nodes[bname]["_fisher_raw"]

    if updated:
        save_tree(tree)


class _MuninnLock:
    """Simple file lock using mkdir atomicity + PID tracking. Prevents concurrent hook execution."""
    STALE_SECONDS = 300  # 5 min — reduced from 10 because PID check catches dead processes faster

    def __init__(self, repo_path: Path, name: str = "hook", timeout: int = 120):
        self.lock_dir = repo_path / ".muninn" / f"{name}.lock"
        self.pid_file = self.lock_dir / "pid"
        self.timeout = timeout

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if process with given PID is still running."""
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, PermissionError, AttributeError):
            return False

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.lock_dir.mkdir(parents=True, exist_ok=False)
                # Write PID so stale detection can check if owner is alive
                try:
                    self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
                except OSError:
                    pass
                return self
            except FileExistsError:
                # Check if lock owner is still alive (PID-based fast detection)
                should_break = False
                try:
                    if self.pid_file.exists():
                        owner_pid = int(self.pid_file.read_text(encoding="utf-8").strip())
                        if not self._is_pid_alive(owner_pid):
                            should_break = True  # Owner dead, break immediately
                except (OSError, ValueError):
                    pass

                if not should_break:
                    # Fallback: time-based stale detection
                    try:
                        age = time.time() - self.lock_dir.stat().st_mtime
                        if age > self.STALE_SECONDS:
                            should_break = True
                    except OSError:
                        pass

                if should_break:
                    import shutil
                    shutil.rmtree(self.lock_dir, ignore_errors=True)
                    continue

                if time.time() > deadline:
                    raise TimeoutError(f"Muninn lock '{self.lock_dir}' held too long")
                time.sleep(1)

    def __exit__(self, *args):
        import shutil
        shutil.rmtree(self.lock_dir, ignore_errors=True)


def _hook_log(repo_path: Path, message: str):
    """Append a timestamped line to .muninn/hook_log.txt for debugging."""
    try:
        log_path = repo_path / ".muninn" / "hook_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def feed_from_hook(repo_path: Path):
    """Called by PreCompact/SessionEnd hook. Reads transcript_path from stdin JSON."""
    hook_event = "PreCompact/SessionEnd"
    _hook_log(repo_path, f"ENTER feed_from_hook (repo={repo_path.name})")
    if sys.stdin.isatty():
        print(f"MUNINN {hook_event}: no stdin (tty mode). Use 'feed --history' for manual.", file=sys.stderr)
        sys.exit(1)
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
        hook_event = hook_input.get("hook_event_name", hook_event)
    except (json.JSONDecodeError, EOFError) as e:
        print(f"MUNINN {hook_event}: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        print(f"MUNINN {hook_event}: no transcript_path in hook data", file=sys.stderr)
        sys.exit(1)

    jsonl_path = Path(transcript_path)
    if not jsonl_path.exists():
        print(f"MUNINN {hook_event}: transcript not found: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"MUNINN {hook_event}: processing {jsonl_path.name} for {repo_path.name}", file=sys.stderr)

    # Lock to prevent concurrent hooks (Stop + PreCompact) from racing on tree.json
    try:
        lock = _MuninnLock(repo_path, "hook", timeout=120)
        lock.__enter__()
    except TimeoutError:
        print(f"MUNINN {hook_event}: lock timeout, skipping", file=sys.stderr)
        return

    try:
        # 0. P36: Update usefulness scores before anything modifies the tree
        _update_usefulness(repo_path, jsonl_path)

        # 1. Feed mycelium (co-occurrences)
        count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
        print(f"MUNINN FEED: {count} messages -> mycelium ({repo_path.name})")

        # 2. Compress transcript into a .mn session file (reuse parsed texts)
        mn_path, session_sentiment = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

        # 3. Auto-segment into tree branches (Brique 3)
        # V6B: Pass session sentiment to branches for valence-modulated decay
        if mn_path:
            grow_branches_from_session(mn_path, session_sentiment=session_sentiment)

        # 4. Refresh tree temperatures
        tree = load_tree()
        refresh_tree_metadata(tree)
        save_tree(tree)

        # B15: Auto-prune when branches exceed cap
        # Light prune: kills dead + dust only (no L9, no consolidation)
        branch_count = len([n for n in tree["nodes"] if n != "root"])
        if branch_count > 150:
            print(f"MUNINN AUTO-PRUNE: {branch_count} branches > 150, running light prune", file=sys.stderr)
            _light_prune()

        # 5. P20b: Sync to meta-mycelium (cross-repo memory)
        try:
            if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            pushed = m.sync_to_meta()
            print(f"MUNINN SYNC: {pushed} connections -> meta-mycelium")
        except Exception as e:
            print(f"MUNINN SYNC warning: {e}", file=sys.stderr)

        # P20c: Ensure repo is registered for cross-repo discovery
        _register_repo(repo_path)
    except Exception as e:
        _hook_log(repo_path, f"CRITICAL feed_from_hook crashed: {e}")
        print(f"MUNINN {hook_event} CRASHED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        lock.__exit__(None, None, None)


def feed_from_stop_hook(repo_path: Path):
    """Called by Stop hook. Debounced: only feeds when new messages exist.

    P32: captures short conversations that never trigger PreCompact/SessionEnd.
    Uses message count dedup to avoid reprocessing the same conversation 50x.
    """
    _hook_log(repo_path, "ENTER feed_from_stop_hook")
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        raw = ""
    if not raw.strip():
        _hook_log(repo_path, "EXIT no stdin data")
        print("MUNINN STOP: no stdin data received", file=sys.stderr)
        return
    try:
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print(f"MUNINN STOP: invalid JSON on stdin: {raw[:200]}", file=sys.stderr)
        return

    # Note: stop_hook_active is always True in Claude Code Stop events.
    # Anti-loop protection is handled by the dedup mechanism below (line count check).

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        print("MUNINN STOP: no transcript_path in hook data", file=sys.stderr)
        return
    jsonl_path = Path(transcript_path)
    if not jsonl_path.exists():
        print(f"MUNINN STOP: transcript not found: {jsonl_path}", file=sys.stderr)
        return

    session_id = hook_input.get("session_id", jsonl_path.stem)

    # Lock to prevent concurrent stop hooks from racing
    try:
        lock = _MuninnLock(repo_path, "hook", timeout=120)
        lock.__enter__()
    except TimeoutError:
        print("MUNINN STOP: lock timeout, skipping", file=sys.stderr)
        return

    try:
        _feed_from_stop_hook_locked(repo_path, jsonl_path, session_id)
    finally:
        lock.__exit__(None, None, None)


def _feed_from_stop_hook_locked(repo_path: Path, jsonl_path: Path, session_id: str):
    """Inner stop hook logic, called under lock."""
    # Count messages in transcript for dedup
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            msg_count = sum(1 for _ in f)
    except OSError:
        return
    if msg_count == 0:
        return

    # Dedup file: {session_id: last_fed_count}
    dedup_path = repo_path / ".muninn" / "stop_dedup.json"
    dedup = {}
    if dedup_path.exists():
        try:
            dedup = json.loads(dedup_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dedup = {}

    last_count = dedup.get(session_id, 0)
    if msg_count <= last_count:
        return  # Nothing new, skip

    # New messages detected — feed the full conversation
    print(f"MUNINN STOP: {msg_count - last_count} new messages (session {session_id[:8]})")

    # 0. P36: Update usefulness scores
    _update_usefulness(repo_path, jsonl_path)

    # 1. Feed mycelium
    count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
    print(f"MUNINN FEED: {count} messages -> mycelium ({repo_path.name})")

    # 2. Compress transcript (reuse parsed texts)
    mn_path, session_sentiment = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

    # 3. Auto-segment into branches
    if mn_path:
        grow_branches_from_session(mn_path, session_sentiment=session_sentiment)

    # 4. Refresh tree
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)

    # 5. Sync to meta-mycelium
    try:
        if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
        from mycelium import Mycelium
        m = Mycelium(repo_path)
        pushed = m.sync_to_meta()
        print(f"MUNINN SYNC: {pushed} connections -> meta-mycelium")
    except Exception as e:
        print(f"MUNINN SYNC warning: {e}", file=sys.stderr)

    # P20c: Ensure repo is registered for cross-repo discovery
    _register_repo(repo_path)

    # 6. Update dedup — keep only last 20 sessions
    dedup[session_id] = msg_count
    if len(dedup) > 20:
        oldest = sorted(dedup.keys())[:len(dedup) - 20]  # session_ids are timestamp-based, lexicographic = chronological
        for k in oldest:
            del dedup[k]
    dedup_path.parent.mkdir(parents=True, exist_ok=True)
    dedup_path.write_text(json.dumps(dedup, indent=2), encoding="utf-8")


def feed_history(repo_path: Path):
    """Feed mycelium from all past transcript JSONL files for this project.

    Scans ~/.claude/projects/<project>/ for .jsonl files and digests them.
    Tracks which files have been digested in .muninn/fed_transcripts.json.
    """
    if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
    from mycelium import Mycelium

    # Find the project's transcript directory
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        print(f"ERROR: {claude_dir} not found")
        sys.exit(1)

    # Find matching project dirs (repo name encoded in path)
    repo_name = repo_path.name
    project_dirs = []
    for d in claude_dir.iterdir():
        if d.is_dir() and d.name.endswith(f"-{repo_name}"):
            project_dirs.append(d)

    if not project_dirs:
        print(f"  No project directories found matching '{repo_name}'")
        return

    # Load already-fed transcript list
    muninn_dir = repo_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)
    fed_path = muninn_dir / "fed_transcripts.json"
    fed = set()
    if fed_path.exists():
        try:
            with open(fed_path, encoding="utf-8") as f:
                fed = set(json.load(f))
        except (json.JSONDecodeError, ValueError, TypeError):
            print("WARNING: fed_transcripts.json corrupted, resetting", file=sys.stderr)

    # Lock to prevent concurrent history + hook from racing
    try:
        lock = _MuninnLock(repo_path, "hook", timeout=120)
        lock.__enter__()
    except TimeoutError:
        print("MUNINN HISTORY: lock timeout, skipping", file=sys.stderr)
        return

    m = Mycelium(repo_path)
    total_messages = 0
    new_files = 0

    try:
        for project_dir in project_dirs:
            # Top-level .jsonl files (main sessions)
            for jsonl_file in sorted(project_dir.glob("*.jsonl")):
                file_key = str(jsonl_file)
                if file_key in fed:
                    continue

                texts = parse_transcript(jsonl_file)
                if texts:
                    m.start_session()
                    for text in texts:
                        m.observe_text(text)
                    total_messages += len(texts)
                    new_files += 1

                fed.add(file_key)

                # Checkpoint every file (not all-or-nothing)
                if new_files % 3 == 0:
                    m.save()
                    with open(fed_path, "w", encoding="utf-8") as f:
                        json.dump(sorted(fed), f, indent=2)

            # Subagent transcripts (top-level and inside session subdirectories)
            subagent_dirs = []
            top_sa = project_dir / "subagents"
            if top_sa.exists():
                subagent_dirs.append(top_sa)
            for sub_dir in project_dir.iterdir():
                if sub_dir.is_dir():
                    sa_dir = sub_dir / "subagents"
                    if sa_dir.exists():
                        subagent_dirs.append(sa_dir)

            for sa_dir in subagent_dirs:
                for jsonl_file in sorted(sa_dir.glob("*.jsonl")):
                    file_key = str(jsonl_file)
                    if file_key in fed:
                        continue
                    texts = parse_transcript(jsonl_file)
                    if texts:
                        m.start_session()
                        for text in texts:
                            m.observe_text(text)
                        total_messages += len(texts)
                        new_files += 1
                    fed.add(file_key)

        if total_messages > 0:
            m.save()

        # Save fed list
        with open(fed_path, "w", encoding="utf-8") as f:
            json.dump(sorted(fed), f, indent=2)
    finally:
        lock.__exit__(None, None, None)

    print(f"=== MUNINN FEED HISTORY ===")
    print(f"  New transcripts: {new_files}")
    print(f"  Messages digested: {total_messages}")
    print(f"  Total fed transcripts: {len(fed)}")
    if total_messages > 0:
        print(f"\n{m.status()}")

    # Compress transcripts into .mn and auto-segment into branches
    # M8 fix: track compressed files by path (not stem — stems don't match .mn timestamps)
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    compressed_path = muninn_dir / "compressed_transcripts.json"
    compressed = {}
    if compressed_path.exists():
        try:
            with open(compressed_path, encoding="utf-8") as f:
                raw = json.load(f)
                # Handle both old format (list) and new format (dict)
                if isinstance(raw, list):
                    compressed = {k: {} for k in raw}
                else:
                    compressed = raw
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    for project_dir in project_dirs:
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            file_key = str(jsonl_file)
            if file_key in compressed:
                continue
            mn_path, _sent = compress_transcript(jsonl_file, repo_path)
            if mn_path:
                created = grow_branches_from_session(mn_path, session_sentiment=_sent)
                if created > 0:
                    print(f"  {jsonl_file.name}: {created} branches created")
            compressed[file_key] = {"mn_file": mn_path.name if mn_path else None}
    with open(compressed_path, "w", encoding="utf-8") as f:
        json.dump(compressed, f, indent=2)

    # Refresh tree
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)


def feed_watch(repo_path: Path):
    """P41: Poll-based feed — scans active transcripts every N minutes.

    Finds the Claude project dir for this repo, checks each .jsonl for size
    changes since last poll, and feeds only those that grew. Uses
    .muninn/watch_state.json to track {filename: last_size_bytes}.
    Zero work if nothing changed.
    """
    _hook_log(repo_path, "ENTER feed_watch")

    # Find project dir
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        print(f"MUNINN WATCH: {claude_dir} not found", file=sys.stderr)
        return

    repo_name = repo_path.name
    project_dirs = [d for d in claude_dir.iterdir()
                    if d.is_dir() and d.name.endswith(f"-{repo_name}")]
    if not project_dirs:
        print(f"MUNINN WATCH: no project dir for '{repo_name}'", file=sys.stderr)
        return

    # Load watch state
    state_path = repo_path / ".muninn" / "watch_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}

    # Find transcripts that grew or have incomplete feed
    changed = []
    changed_keys = {}  # jsonl_path -> state key (for deferred state update)
    for project_dir in project_dirs:
        for jsonl_file in project_dir.glob("*.jsonl"):
            key = f"{project_dir.name}/{jsonl_file.name}"
            try:
                current_size = jsonl_file.stat().st_size
            except OSError:
                continue
            last_size = state.get(key, 0)
            if current_size > last_size:
                changed.append(jsonl_file)
                changed_keys[str(jsonl_file)] = (key, current_size)
            elif last_size > 0:
                # B.4 fix: check if prior feed was incomplete (state says done but
                # compress/branches may have failed). Re-include if .mn session
                # doesn't exist for this file yet. feed_from_transcript handles
                # "already complete" efficiently via feed_progress.json offset check.
                sessions_dir = repo_path / ".muninn" / "sessions"
                if sessions_dir.exists():
                    # Simple heuristic: if state recorded this file but no session
                    # was created in the last 24h, retry the compress+grow pipeline
                    from datetime import datetime
                    recent_sessions = [
                        s for s in sessions_dir.glob("*.mn")
                        if (datetime.now().timestamp() - s.stat().st_mtime) < 86400
                    ]
                    if not recent_sessions:
                        changed.append(jsonl_file)
                        changed_keys[str(jsonl_file)] = (key, current_size)

    if not changed:
        _hook_log(repo_path, "EXIT watch: nothing changed")
        return

    print(f"MUNINN WATCH: {len(changed)} transcript(s) changed")

    # Lock to prevent concurrent watch + hook from racing
    try:
        lock = _MuninnLock(repo_path, "hook", timeout=120)
        lock.__enter__()
    except TimeoutError:
        print("MUNINN WATCH: lock timeout, skipping", file=sys.stderr)
        return

    fed_count = 0
    try:
        for jsonl_path in changed:
            try:
                _hook_log(repo_path, f"WATCH feeding {jsonl_path.name}")

                # Step 1: Feed mycelium (chunked + resumable — survives timeout)
                count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
                print(f"  FEED: {count} messages -> mycelium ({jsonl_path.name})")

                # Step 2: Compress transcript (reuse parsed texts)
                mn_path, _sent = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

                # Step 3: Auto-segment into branches
                if mn_path:
                    grow_branches_from_session(mn_path, session_sentiment=_sent)

                # Save state AFTER full pipeline (feed+compress+grow) succeeds
                ck = changed_keys.get(str(jsonl_path))
                if ck:
                    state[ck[0]] = ck[1]
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

                fed_count += 1
                _hook_log(repo_path, f"WATCH fed ok {jsonl_path.name}: {count} msgs")
            except Exception as e:
                print(f"  WATCH error on {jsonl_path.name}: {e}", file=sys.stderr)
                _hook_log(repo_path, f"WATCH error {jsonl_path.name}: {e}")
                import traceback
                traceback.print_exc(file=sys.stderr)

        if fed_count > 0:
            # Refresh tree
            tree = load_tree()
            refresh_tree_metadata(tree)
            save_tree(tree)

            # Sync to meta-mycelium
            try:
                if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
                from mycelium import Mycelium
                m = Mycelium(repo_path)
                pushed = m.sync_to_meta()
                print(f"  SYNC: {pushed} connections -> meta-mycelium")
            except Exception as e:
                print(f"  SYNC warning: {e}", file=sys.stderr)

            _register_repo(repo_path)
    finally:
        lock.__exit__(None, None, None)

    _hook_log(repo_path, f"WATCH done: {fed_count}/{len(changed)} transcript(s) fed")


def ingest(filepath: Path, repo_path: Path):
    """Ingest a reference document (or all .md in a folder) into the tree as permanent branches.

    Compresses with full pipeline (L1-L7+L9), then auto-segments into branches.
    Use case: bibles UX, docs de reference, specs — anything you want available via boot.
    """
    files_to_ingest = []
    if filepath.is_dir():
        files_to_ingest = sorted(filepath.glob("**/*.md"))
        if not files_to_ingest:
            files_to_ingest = sorted(filepath.glob("**/*.txt"))
        print(f"=== MUNINN INGEST: {filepath.name} ({len(files_to_ingest)} files) ===")
    elif filepath.is_file():
        files_to_ingest = [filepath]
        print(f"=== MUNINN INGEST: {filepath.name} ===")
    else:
        print(f"ERROR: {filepath} not found")
        return

    total_branches = 0
    total_original = 0
    total_compressed = 0

    for f in files_to_ingest:
        content = f.read_text(encoding="utf-8", errors="replace")
        if len(content.strip()) < 50:
            continue

        total_original += token_count(content)

        # Compress with full pipeline
        compressed = compress_file(f)
        total_compressed += token_count(compressed)

        # Write as .mn in repo's .muninn/tree/ for auto-segmentation
        mn_dir = repo_path / ".muninn" / "tree"
        mn_dir.mkdir(parents=True, exist_ok=True)
        mn_temp = mn_dir / f"_ingest_{f.stem}.mn"
        mn_temp.write_text(compressed, encoding="utf-8")

        # Auto-segment into branches
        created = grow_branches_from_session(mn_temp)
        total_branches += created

        # Clean up temp file (branches are already stored)
        if mn_temp.exists():
            mn_temp.unlink()

        orig_tok = token_count(content)
        comp_tok = token_count(compressed)
        ratio = orig_tok / max(comp_tok, 1)
        print(f"  {f.name}: {orig_tok} -> {comp_tok} tokens (x{ratio:.1f}), {created} branches")

    # Nourrit aussi le mycelium avec le contenu
    if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
    from mycelium import Mycelium
    m = Mycelium(repo_path)
    m.start_session()
    for f in files_to_ingest:
        content = f.read_text(encoding="utf-8", errors="replace")
        if content.strip():
            m.observe_text(content)
    m.save()

    # Refresh tree
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)

    ratio = total_original / max(total_compressed, 1)
    print(f"\n  Total: {total_original} -> {total_compressed} tokens (x{ratio:.1f})")
    print(f"  Branches created: {total_branches}")
    print(f"  Mycelium updated")


# ── B7: Live memory injection ─────────────────────────────────────

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

    repo = repo_path or _REPO_PATH or Path(".").resolve()

    # Ensure tree exists
    tree = load_tree()
    nodes = tree["nodes"]

    # Find or create the 'live' branch
    live_name = None
    for name, node in nodes.items():
        if node.get("type") == "branch" and "live_inject" in node.get("tags", []):
            live_name = name
            break

    # Use the correct tree directory (TREE_DIR, not memory/branches/)
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
        if _CORE_DIR not in sys.path:
            sys.path.insert(0, _CORE_DIR)
        from mycelium import Mycelium
        m = Mycelium(repo)
        m.observe_text(fact)
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


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.9 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap", "feed", "verify",
        "ingest", "recall", "bridge", "upgrade-hooks", "inject", "diagnose", "trip", "think",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
    parser.add_argument("--history", action="store_true", help="Feed from all past transcripts")
    parser.add_argument("--watch", action="store_true", help="Poll-based feed: only process transcripts that grew since last check")
    parser.add_argument("--no-l9", action="store_true", help="Skip L9 (LLM API) — use only free layers")
    parser.add_argument("--trigger", choices=["hook", "stop"], default="hook",
                        help="Hook trigger type (hook=PreCompact/SessionEnd, stop=Stop)")
    parser.add_argument("--force", action="store_true", help="Force operation (e.g., prune without dry-run)")

    args = parser.parse_args()

    # Global flag to skip L9
    global _SKIP_L9
    _SKIP_L9 = getattr(args, 'no_l9', False)

    # Set repo path for local codebook loading
    if args.repo:
        _REPO_PATH = Path(args.repo).resolve()
        _refresh_tree_paths()

    if args.command == "init":
        init_tree()
        return

    if args.command == "status":
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        show_status()
        return

    if args.command == "diagnose":
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        diagnose()
        return

    if args.command == "trip":
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        repo = _REPO_PATH or Path(".")
        if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
        from mycelium import Mycelium
        m = Mycelium(repo)
        intensity = 0.7 if args.force else 0.5
        result = m.trip(intensity=intensity, max_dreams=20)
        if result["created"] > 0:
            m.save()
        print(f"=== HUGINN TRIP (H1) ===")
        print(f"  Intensity: {intensity}")
        print(f"  Dream connections: {result['created']}")
        print(f"  Entropy: {result['entropy_before']:.4f} -> {result['entropy_after']:.4f} "
              f"(delta: {result.get('entropy_delta', 0):+.4f})")
        if result.get("reason"):
            print(f"  Note: {result['reason']}")
        for d in result["dreams"][:10]:
            print(f"    {d['from']} <-> {d['to']} (zones: {d['zones'][0][:20]}|{d['zones'][1][:20]})")
        if result["created"] > 10:
            print(f"    ... and {result['created'] - 10} more")
        return

    if args.command == "think":
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        query = args.file or ""
        insights = huginn_think(query=query, top_n=10)
        print("=== HUGINN THINK (H3) ===")
        if not insights:
            print("  No insights yet. Run `muninn.py prune` to generate (dream runs during sleep).")
        else:
            for ins in insights:
                print(f"  {ins['formatted']}")
            print(f"\n  {len(insights)} insight(s) total")
        return

    if args.command == "scan":
        if not args.file:
            print("ERROR: repo path required. Usage: muninn.py scan <repo-path>")
            sys.exit(1)
        scan_repo(Path(args.file))
        return

    if args.command == "bootstrap":
        if not args.file:
            print("ERROR: repo path required. Usage: muninn.py bootstrap <repo-path>")
            sys.exit(1)
        _REPO_PATH = Path(args.file).resolve()
        _refresh_tree_paths()
        bootstrap_mycelium(Path(args.file))
        return

    if args.command == "upgrade-hooks":
        repo = Path(args.repo or args.file or ".").resolve()
        if not (repo / ".muninn").exists():
            print(f"ERROR: {repo} is not a Muninn repo (no .muninn/ directory)")
            sys.exit(1)
        install_hooks(repo)
        return

    if args.command == "feed":
        # --repo is authoritative. For direct file mode without --repo, use CWD (not the JSONL path).
        if args.repo:
            repo = Path(args.repo).resolve()
        elif args.file and Path(args.file).suffix == ".jsonl":
            repo = Path(".").resolve()  # don't use JSONL path as repo
        else:
            repo = Path(args.file or ".").resolve()
        _REPO_PATH = repo
        _refresh_tree_paths()
        if args.watch:
            feed_watch(repo)
        elif args.history:
            feed_history(repo)
        elif args.file and Path(args.file).suffix == ".jsonl":
            # Direct file mode: feed from a specific transcript
            count, parsed_texts = feed_from_transcript(Path(args.file), repo)
            print(f"MUNINN FEED: {count} messages -> mycelium ({repo.name})")
            _mn, _sent = compress_transcript(Path(args.file), repo, texts=parsed_texts)
            # Match hook behavior: grow branches + refresh tree + sync meta
            if _mn:
                grow_branches_from_session(_mn, session_sentiment=_sent)
            tree = load_tree()
            refresh_tree_metadata(tree)
            save_tree(tree)
            try:
                if _CORE_DIR not in sys.path: sys.path.insert(0, _CORE_DIR)
                from mycelium import Mycelium
                m = Mycelium(repo)
                pushed = m.sync_to_meta()
                print(f"MUNINN SYNC: {pushed} connections -> meta-mycelium")
            except Exception as e:
                print(f"MUNINN SYNC warning: {e}", file=sys.stderr)
        elif args.trigger == "stop":
            # P32: Stop hook — debounced feed
            feed_from_stop_hook(repo)
        else:
            # Hook mode: read transcript_path from stdin
            feed_from_hook(repo)
        return

    if args.command == "ingest":
        if not args.file:
            print("ERROR: file or folder required. Usage: muninn.py ingest <file-or-folder> --repo <repo-path>")
            sys.exit(1)
        repo = Path(args.repo or ".").resolve()
        _REPO_PATH = repo
        _refresh_tree_paths()
        ingest(Path(args.file), repo)
        return

    if args.command == "inject":
        if not args.file:
            print('ERROR: fact required. Usage: muninn.py inject "important fact here"')
            sys.exit(1)
        repo = Path(args.repo or ".").resolve()
        _REPO_PATH = repo
        _refresh_tree_paths()
        inject_memory(args.file, repo)
        return

    if args.command == "recall":
        if not args.file:
            print("ERROR: query required. Usage: muninn.py recall \"search terms\"")
            sys.exit(1)
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        result = recall(args.file)
        print(result)
        return

    if args.command == "bridge":
        if not args.file:
            print('ERROR: text required. Usage: muninn.py bridge "user message or concepts"')
            sys.exit(1)
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        result = bridge(args.file)
        print(result)
        return

    if args.command == "boot":
        # If no --repo, try to use current dir if it has .muninn/
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        result = boot(args.file or "")
        print(result)
        return

    if args.command == "prune":
        prune(dry_run=not args.force)
        return

    if args.command == "decode":
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
        else:
            text = sys.stdin.read()
        for line in text.split("\n"):
            print(decode_line(line))
        return

    if args.command == "verify":
        if not args.file:
            print("ERROR: file required. Usage: muninn.py verify <file>")
            sys.exit(1)
        fp = Path(args.file)
        if not fp.exists():
            print(f"ERROR: {fp} not found")
            sys.exit(1)
        verify_compression(fp)
        return

    if not args.file:
        print("ERROR: file argument required")
        sys.exit(1)

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"ERROR: {filepath} not found")
        sys.exit(1)

    if args.command == "read":
        stats = analyze_file(filepath)
        print(f"\n=== MUNINN READ: {filepath.name} ===")
        print(f"  Lines: {stats['lines']}, Tokens (est): {stats['tokens_est']}")
        print(f"\n  Top codebook hits:")
        for pattern, info in sorted(stats["codebook_hits"].items(),
                                     key=lambda x: x[1]["saved"], reverse=True)[:15]:
            print(f"    {info['count']:3d}x '{pattern}' -> '{info['code']}' (saves {info['saved']})")
        print(f"\n  Tokens: {stats['tokens_est']} -> {stats['tokens_after']} (x{stats['ratio']})")

    elif args.command == "compress":
        compressed = compress_file(filepath)
        print(compressed)
        orig = filepath.stat().st_size
        comp = len(compressed)
        print(f"\n# {orig} -> {comp} chars (x{orig / max(comp, 1):.1f})")

    elif args.command == "tree":
        build_tree(filepath)


if __name__ == "__main__":
    main()
