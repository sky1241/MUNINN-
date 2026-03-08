#!/usr/bin/env python3
"""
Muninn v0.8 — Moteur de compression memoire LLM.
UNIVERSEL — zero hardcode projet. Fonctionne sur n'importe quel repo.

8 couches de compression:
  L1-L7: Regex (markdown, filler, phrases, nombres, rules, mycelium, facts)
  L9: LLM self-compress (Claude API, optional, pip install anthropic)

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
import argparse
import hashlib
import io
import json
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


# ── COMPRESSION RULES LOADER ────────────────────────────────────
# Two sources of compression rules:
# 1. Universal rules (hardcoded, BPE-native English)
# 2. Mycelium (living codebook, per-repo, grows with usage)

# Universal compression: state words -> short English (BPE-native)
UNIVERSAL_RULES = {
    # French -> English compact (1 token each)
    "COMPLET": "done", "COMPLETE": "done", "complet": "done",
    "VALIDE": "done", "VALIDÉ": "done", "FIXE": "done", "FIXÉ": "done",
    "EN COURS": "wip", "en cours": "wip",
    "ECHOUE": "fail", "ECHOUÉ": "fail", "FAILED": "fail",
    "EN ATTENTE": "todo", "PENDING": "todo",
    "DÉCISION": "decided", "DECISION": "decided",
    # Markdown stripping
    "## ": "", "**": "", "- ": "",
}


def load_codebook(repo_path: Path = None) -> dict:
    """Load compression rules: universal + mycelium (if available)."""
    text_rules = dict(UNIVERSAL_RULES)

    # Load mycelium compression rules (living codebook)
    mycelium_rules = {}
    learned_fillers = []
    learned_abbreviations = {}
    if repo_path:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            mycelium_rules = m.get_compression_rules()
            learned_fillers = m.get_learned_fillers()
            learned_abbreviations = m.get_learned_abbreviations()
        except (ImportError, Exception):
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

# Biological ratios: compression varies by temperature (COCOM 2025)
# Hot nodes get more space (detail), cold nodes get compressed harder
COMPRESSION_BY_TEMP = {
    "hot":  1.5,   # t >= 0.5 — light compression, keep detail
    "warm": 3.0,   # 0.2 <= t < 0.5 — moderate compression
    "cold": 6.0,   # t < 0.2 — heavy compression, summary only
}


def effective_budget(node: dict) -> int:
    """Dynamic budget: hot nodes get more lines, cold nodes fewer.

    Instead of fixed max_lines, scale by temperature.
    Hot nodes: max_lines * 1.5 (more room)
    Cold nodes: max_lines * 0.5 (compress harder)
    """
    base = node.get("max_lines", 150)
    temp = node.get("temperature", 0.3)
    if temp >= 0.5:
        return int(base * 1.3)  # hot: 30% more room
    elif temp < 0.2:
        return int(base * 0.6)  # cold: 40% less room
    return base  # warm: standard

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
    except (json.JSONDecodeError, ValueError):
        print("WARNING: tree.json corrupted, re-initializing", file=sys.stderr)
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


def compute_temperature(node: dict) -> float:
    """Temperature score: how "hot" is this node (0.0=frozen, 1.0=burning).

    Based on:
    - access_count (more access = hotter)
    - recency (accessed recently = hotter)
    - fill ratio (fuller = hotter, needs attention)

    Inspired by COCOM (2025): variable compression by importance.
    Root 1.5x, hot branches 3x, cold leaves 6x.
    """
    access = node.get("access_count", 0)
    last = node.get("last_access", "2026-01-01")
    fill = node.get("lines", 0) / max(node.get("max_lines", 1), 1)

    # Recency: days since last access (0 = today)
    try:
        days_cold = (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days
    except ValueError:
        days_cold = 90

    # Access heat: log scale, caps at ~1.0 for 10+ accesses
    import math
    access_heat = min(1.0, math.log1p(access) / math.log1p(10))

    # Recency heat: 1.0 = today, decays to 0 over 90 days
    recency_heat = max(0.0, 1.0 - days_cold / 90)

    # Fill pressure: nodes near budget get hotter (need split/compress)
    fill_heat = fill ** 2  # quadratic: only significant near full

    # Weighted combination
    temp = 0.5 * access_heat + 0.3 * recency_heat + 0.2 * fill_heat
    return round(temp, 2)


def refresh_tree_metadata(tree: dict):
    """Recompute hash + temperature for all nodes."""
    for name, node in tree["nodes"].items():
        filepath = TREE_DIR / node["file"]
        node["hash"] = compute_hash(filepath)
        node["temperature"] = compute_temperature(node)


def read_node(name: str) -> str:
    tree = load_tree()
    node = tree["nodes"].get(name)
    if not node:
        return f"ERROR: node '{name}' not found"

    filepath = TREE_DIR / node["file"]
    if not filepath.exists():
        return f"ERROR: file '{filepath}' not found"

    node["access_count"] = node.get("access_count", 0) + 1
    node["last_access"] = time.strftime("%Y-%m-%d")
    save_tree(tree)

    return filepath.read_text(encoding="utf-8")


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
        r'(?:because|since|therefore|so that|due to|parce que?|car |donc |puisque)\s+\S+',
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
        # Articles & determiners
        r"\bthe\b", r"\ba\b", r"\ban\b",
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
        # French fillers
        r"\best\b", r"\bqui\b", r"\bque\b", r"\bdans\b", r"\bavec\b",
        r"\bpour\b", r"\bplus\b", r"\btout\b", r"\bmais\b",
    ]
    for filler in _FILLER:
        result = re.sub(filler, "", result, flags=re.IGNORECASE)

    # L2b: Learned fillers from mycelium (words in 10+ connections, never fused)
    for filler_word in cb.get("learned_fillers", []):
        result = re.sub(rf"\b{re.escape(filler_word)}\b", "", result, flags=re.IGNORECASE)

    # L2 post-pass: restore protected spans
    for placeholder, original_span in _placeholders.items():
        result = result.replace(placeholder, original_span)

    # L3: Common phrase collapsing
    _PHRASES = [
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
    for long_form, short_form in cb.get("learned_abbreviations", {}).items():
        if long_form in result.lower():
            result = re.sub(rf"\b{re.escape(long_form)}\b", short_form, result,
                          count=1, flags=re.IGNORECASE)

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
    for pattern in sorted(cb["text_rules"].keys(), key=len, reverse=True):
        result = result.replace(pattern, cb["text_rules"][pattern])

    # L6: Mycelium-aware compression: strong fusions = predictable pairs.
    # Only drop shorter concept if it appears exactly once AND near the other.
    strong_fusions = {k: v for k, v in cb["mycelium_rules"].items()
                      if v["strength"] >= 10}
    for key, rule in strong_fusions.items():
        a, b = rule["concepts"]
        result_lower = result.lower()
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

    # Commit hashes
    for m in re.finditer(r'\b([a-f0-9]{7,12})\b', text):
        facts.append(m.group(1))

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
        r"mesur[eé]|metric|gain|score|accuracy|retention|cost\s*[:=])"
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
    # Don't double-tag
    if line and len(line) >= 2 and line[:2] in ("B>", "E>", "F>", "D>", "A>"):
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
    for pattern, code in state_words.items():
        if pattern in header.upper():
            state = code
            header = re.sub(
                rf"\s*[—\-]+\s*{re.escape(pattern)}", "",
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
        header = header.replace(pattern, text_rules[pattern])

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


def compress_file(filepath: Path) -> str:
    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")

    sections = []
    current_header = None
    current_lines = []

    for line in lines:
        if line.startswith("## "):
            if current_header:
                sections.append((current_header, current_lines))
            current_header = line
            current_lines = []
        elif line.startswith("# ") and not line.startswith("## "):
            continue
        else:
            current_lines.append(line)

    if current_header:
        sections.append((current_header, current_lines))

    output = ["# MUNINN|codebook=v0.1"]
    for header, slines in sections:
        compressed = compress_section(header, slines)
        output.append(compressed)

    result = "\n".join(output)

    # Layer 9: LLM self-compress (optional, for large outputs)
    if len(result) > 4000:
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
            if api_key:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max(1, token_count(result) // 4),
                    messages=[{"role": "user", "content": (
                        "Compress this into ultra-dense notes. Rules:\n"
                        "- Keep ALL facts: numbers, dates, names, file paths, commits, decisions\n"
                        "- Strip all filler, transitions, greetings, confirmations\n"
                        "- Use shorthand: -> for leads to, = for equals, | for separators\n"
                        "- One fact per line, no full sentences\n"
                        "- Target: 20% of original length, 100% of facts\n"
                        "- Output raw compressed text, no preamble\n\n"
                        f"TEXT ({len(result)} chars):\n{result}"
                    )}],
                )
                llm_compressed = response.content[0].text
                if len(llm_compressed) < len(result) * 0.8:
                    print(f"  Layer 9 (LLM): {len(result)} -> {len(llm_compressed)} chars "
                          f"(API: {response.usage.input_tokens}in+{response.usage.output_tokens}out)",
                          file=sys.stderr)
                    result = llm_compressed
        except ImportError:
            pass
        except Exception as e:
            print(f"  Layer 9 warning: {e}", file=sys.stderr)

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
            while len(root_lines) > BUDGET["root_lines"] - len(overflow_refs):
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

def grow_branches_from_session(mn_path: Path):
    """Auto-segment a compressed .mn file into tree branches.

    Splits the session by ## headers (already created by compress_transcript).
    Each section becomes a branch with auto-extracted tags.
    Merges into existing branch if >50% tag overlap (avoids duplication).
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
        if header.startswith("## ") and body and len(body) > 20:
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
            if len(body) > 20:
                segments.append((header, body))

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

        # Check for overlap with existing branches (merge if >50% overlap)
        merged = False
        for name, node in nodes.items():
            if name == "root":
                continue
            existing_tags = set(node.get("tags", []))
            if existing_tags and tag_set:
                overlap = len(tag_set & existing_tags) / max(len(tag_set | existing_tags), 1)
                if overlap > 0.5:
                    # Merge: append content to existing branch
                    filepath = TREE_DIR / node["file"]
                    if filepath.exists():
                        old = filepath.read_text(encoding="utf-8")
                        # Respect max_lines budget
                        new_lines = old.split("\n") + ["", header] + body.split("\n")
                        max_l = node.get("max_lines", 150)
                        if len(new_lines) <= max_l:
                            filepath.write_text("\n".join(new_lines), encoding="utf-8")
                            node["lines"] = len(new_lines)
                            # Add new tags
                            node["tags"] = sorted(set(node.get("tags", [])) | tag_set)[:10]
                            merged = True
                            break

        if not merged:
            # Create new branch
            branch_name = f"b{next_id:02d}"
            branch_file = f"{branch_name}.mn"
            branch_path = TREE_DIR / branch_file
            lines = body.split("\n")
            branch_path.write_text(body, encoding="utf-8")

            nodes[branch_name] = {
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
            # Add to root's children
            if branch_name not in nodes.get("root", {}).get("children", []):
                nodes.setdefault("root", {}).setdefault("children", []).append(branch_name)

            next_id += 1
            created += 1

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
    entities = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
    for entity, count in Counter(entities).most_common(5):
        if count >= 2:
            tags.add(entity.lower())

    # Extract technical keywords generically
    tech_words = re.findall(r'\b[a-z]{4,}\b', text_lower)
    for word, count in Counter(tech_words).most_common(10):
        if count >= 3 and word not in ("this", "that", "with", "from", "have",
                                        "been", "will", "pour", "dans", "avec",
                                        "sont", "dans", "plus", "tout", "mais"):
            tags.add(word)

    return sorted(tags)[:10]


def boot(query: str = "") -> str:
    """R7: load root + relevant branches based on query.

    Scoring (Generative Agents, Park et al. 2023):
      score = α×recency + β×importance + γ×relevance(query)
    where relevance uses TF-IDF cosine similarity on branch content.
    """
    tree = load_tree()
    nodes = tree["nodes"]

    root_text = read_node("root")
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

    if query:
        # P15: Query expansion via mycelium co-occurrences
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from mycelium import Mycelium
            m = Mycelium(_REPO_PATH or Path("."))
            query_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', query.lower())
            expanded = set(query_words)
            for word in query_words:
                for related, strength in m.get_related(word, top_n=3):
                    if strength >= 3:  # only strong connections
                        expanded.add(related)
            if expanded - set(query_words):
                query = query + " " + " ".join(expanded - set(query_words))
        except Exception:
            pass  # mycelium not available — use original query

        # Load branch contents for TF-IDF scoring
        branch_contents = {}
        for name, node in nodes.items():
            if name == "root":
                continue
            filepath = TREE_DIR / node["file"]
            if filepath.exists():
                branch_contents[name] = filepath.read_text(encoding="utf-8")
            else:
                # Fallback: use tags as content
                branch_contents[name] = " ".join(node.get("tags", []))

        # TF-IDF relevance scores (0-1)
        relevance_scores = _tfidf_relevance(query, branch_contents)

        # Generative Agents scoring: recency + importance + relevance
        scored = []
        for name, node in nodes.items():
            if name == "root":
                continue

            # Recency: exponential decay (0.995^hours_since_access)
            last = node.get("last_access", "2026-01-01")
            try:
                days_cold = (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days
            except ValueError:
                days_cold = 90
            recency = max(0.0, 1.0 - days_cold / 90)

            # Importance: log-scaled access count
            import math
            access = node.get("access_count", 0)
            importance = min(1.0, math.log1p(access) / math.log1p(10))

            # Relevance: TF-IDF cosine similarity
            relevance = relevance_scores.get(name, 0.0)

            # Weighted combination (α=0.2, β=0.2, γ=0.6 — relevance dominates)
            total = 0.2 * recency + 0.2 * importance + 0.6 * relevance
            if total > 0.01:
                scored.append((name, total))

        scored.sort(key=lambda x: x[1], reverse=True)
        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]

        for name, score in scored:
            node = nodes[name]
            node_tokens = node["lines"] * BUDGET["tokens_per_line"]
            if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                break
            branch_text = read_node(name)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens
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
            branch_text = read_node(name)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens

    # P19: Dedup branches — skip if >50% word overlap with already-loaded
    def _word_set(text):
        return set(re.findall(r'[a-zA-Z]{4,}', text.lower()))

    deduped = []
    loaded_words = []
    for name, text in loaded:
        if name == "root":
            deduped.append((name, text))
            loaded_words.append(_word_set(text))
            continue
        words = _word_set(text)
        is_dup = False
        for prev_words in loaded_words:
            if not words or not prev_words:
                continue
            overlap = len(words & prev_words) / min(len(words), len(prev_words))
            if overlap > 0.5:
                is_dup = True
                break
        if not is_dup:
            deduped.append((name, text))
            loaded_words.append(words)

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
                max_chars = remaining_budget * 4
                session_lines = session_text.split("\n")
                tail_lines = []
                char_count = 0
                for line in reversed(session_lines):
                    if char_count + len(line) + 1 > max_chars:
                        break
                    tail_lines.insert(0, line)
                    char_count += len(line) + 1
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

    return "\n".join(output)


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
                text = mn_file.read_text(encoding="utf-8")
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

    # 3. Search tree branches
    if TREE_DIR.exists():
        for mn_file in TREE_DIR.glob("*.mn"):
            if mn_file.name == "root.mn":
                continue
            try:
                text = mn_file.read_text(encoding="utf-8")
                for line in text.split("\n"):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    line_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
                    overlap = len(query_words & line_words)
                    if overlap >= 2:
                        results.append((overlap, mn_file.stem, stripped[:150]))
            except OSError:
                continue

    # 4. Check error/fix memory
    error_hints = _surface_known_errors(repo, query)
    if error_hints:
        for hint in error_hints.split("\n"):
            results.append((5, "errors", hint))

    if not results:
        return f"RECALL: nothing found for '{query}'"

    # Sort by relevance (overlap score), dedup, take top 10
    results.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    output = [f"RECALL: '{query}' — {len(results)} matches"]
    for score, source, text in results:
        if text in seen:
            continue
        seen.add(text)
        output.append(f"  [{source}] {text}")
        if len(output) >= 12:  # max 10 results + header
            break

    return "\n".join(output)


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


# ── PRUNE (R4) ───────────────────────────────────────────────────

def prune(dry_run: bool = True):
    """R4: promote hot, demote cold, kill dead. Uses temperature score."""
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

    branches = {n: d for n, d in nodes.items() if d["type"] == "branch"}
    if not branches:
        print("  No branches to prune.")
        return

    print(f"=== MUNINN PRUNE (R4) === {'[DRY RUN]' if dry_run else ''}")
    print(f"  Branches: {len(branches)}")
    print()

    hot, cold, dead = [], [], []

    for name, node in branches.items():
        temp = node.get("temperature", 0)
        acc = node.get("access_count", 0)
        last = node.get("last_access", "2026-01-01")
        try:
            days_ago = (datetime.now() - datetime.strptime(last, "%Y-%m-%d")).days
        except ValueError:
            days_ago = 90

        if temp >= 0.4:
            hot.append((name, temp))
            print(f"  HOT  {name}: t={temp:.2f} acc={acc}")
        elif temp == 0 and days_ago >= 90:
            dead.append((name, days_ago))
            print(f"  DEAD {name}: t={temp:.2f} cold {days_ago}d")
        elif temp < 0.1 and days_ago >= 30:
            cold.append((name, days_ago))
            print(f"  COLD {name}: t={temp:.2f} cold {days_ago}d")
        else:
            print(f"  OK   {name}: t={temp:.2f} acc={acc}")

    if not dry_run:
        for name, days in dead:
            node = nodes[name]
            filepath = TREE_DIR / node["file"]
            if filepath.exists():
                filepath.unlink()
            del nodes[name]
            if name in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(name)
            print(f"  DELETED {name}")

        save_tree(tree)

    print(f"\n  Summary: {len(hot)} hot, {len(cold)} cold, {len(dead)} dead")


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
        fill = node["lines"] / node["max_lines"] * 100
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

    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    conns = mycelium.data.get("connections", {})
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
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    recent.append(line.strip())
    except Exception:
        pass

    # Build root.mn
    fusions = len(mycelium.data.get("fusions", {}))
    lines = [
        f"P:{name}|{main_lang}|{total_lines}L|{file_count}files",
        f"E:{entry}",
        f"S:bootstrap|{time.strftime('%Y-%m-%d')}|mycelium:{len(conns)}conn,{fusions}fusions",
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


def install_hooks(repo_path: Path):
    """Install Claude Code hooks for automatic feed on PreCompact/SessionEnd."""
    repo_path = repo_path.resolve()
    muninn_engine = Path(__file__).resolve()
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    feed_cmd = f'python "{muninn_engine}" feed --repo "{repo_path}"'
    hooks_config = {
        "hooks": {
            "PreCompact": [{"type": "command", "command": feed_cmd}],
            "SessionEnd": [{"type": "command", "command": feed_cmd}],
        }
    }

    if settings_path.exists():
        try:
            existing = json.load(open(settings_path, encoding="utf-8"))
            if "hooks" in existing:
                print(f"  Hooks already configured, skipped")
                return
            existing["hooks"] = hooks_config["hooks"]
            hooks_config = existing
        except (json.JSONDecodeError, ValueError):
            pass

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(hooks_config, f, indent=2, ensure_ascii=False)
    print(f"  Hooks installed: PreCompact + SessionEnd")


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
    print(f"    {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}, -{(orig_tokens - comp_tokens) / orig_tokens * 100:.0f}%)")
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


def parse_transcript(jsonl_path: Path) -> list[str]:
    """Parse a Claude Code transcript JSONL and extract text messages.

    L0 FILTER: strips tool results (77% of transcript) down to 1-line summaries.
    Keeps: user messages, assistant text, tool call names + args (not results).
    """
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
                                if len(remainder) >= 25:
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
                            texts[old_idx] = None  # mark for removal
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
    """Feed the mycelium from a single transcript JSONL file."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mycelium import Mycelium

    m = Mycelium(repo_path)
    m.start_session()

    texts = parse_transcript(jsonl_path)
    if not texts:
        print(f"  No text messages found in {jsonl_path.name}")
        return 0

    for text in texts:
        m.observe_text(text)

    m.save()
    return len(texts)


def compress_transcript(jsonl_path: Path, repo_path: Path) -> Path:
    """Compress a transcript JSONL into a dense .mn session file.

    Extracts user+assistant messages, compresses each with the 7-layer
    pipeline, writes result to .muninn/sessions/<timestamp>.mn.
    Returns the path to the written .mn file.
    """
    texts = parse_transcript(jsonl_path)
    if not texts:
        return None

    # Strip secrets before compression
    secret_patterns = [
        r'ghp_[A-Za-z0-9]{36,}',       # GitHub tokens
        r'sk-[A-Za-z0-9]{20,}',         # API keys
        r'token[=:]\s*\S{20,}',         # Generic tokens
        r'password[=:]\s*\S+',          # Passwords
    ]
    for i, text in enumerate(texts):
        for pat in secret_patterns:
            texts[i] = re.sub(pat, '[REDACTED]', texts[i])

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
    output = ["# MUNINN|session_compressed"]
    for header, lines in sections:
        compressed = compress_section(header, lines)
        if compressed and len(compressed) > 5:
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
            continue
        if norm in seen_hashes:
            continue
        seen_hashes.add(norm)
        deduped_lines.append(dline)
    result = "\n".join(deduped_lines)

    # Layer 9: LLM self-compress (Claude summarizes via API, optional)
    # Only for large texts where the cost (~2K tokens) is worth the savings (>10K tokens)
    if len(result) > 4000:
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
            if api_key:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                llm_prompt = (
                    "Compress this session transcript into ultra-dense notes. Rules:\n"
                    "- Keep ALL facts: numbers, dates, names, file paths, commits, decisions\n"
                    "- Strip all filler, transitions, greetings, confirmations\n"
                    "- Use shorthand: -> for leads to, = for equals, | for separators\n"
                    "- One fact per line, no full sentences\n"
                    "- Preserve code snippets and error messages verbatim but minimal\n"
                    "- Target: 20% of original length, 100% of facts\n"
                    "- Output raw compressed text, no preamble\n\n"
                    f"TRANSCRIPT ({len(result)} chars):\n{result}"
                )
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max(1, token_count(result) // 4),  # target ~25% of input
                    messages=[{"role": "user", "content": llm_prompt}],
                )
                llm_compressed = response.content[0].text
                if len(llm_compressed) < len(result) * 0.8:  # only use if >20% savings
                    input_tokens = response.usage.input_tokens
                    output_tokens = response.usage.output_tokens
                    print(f"  Layer 9 (LLM): {len(result)//4} -> {len(llm_compressed)//4} tokens "
                          f"(API cost: {input_tokens}in+{output_tokens}out)")
                    result = llm_compressed
        except ImportError:
            pass  # anthropic not installed — skip Layer 9
        except Exception as e:
            print(f"  Layer 9 warning: {e}")

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
            line_tokens = max(1, len(pline) // 4)
            if running_tokens + line_tokens <= max_session_tokens:
                kept_indices.add(orig_idx)
                running_tokens += line_tokens
        # Rebuild in original order
        result = "\n".join(
            pline for i, (_, pline) in enumerate(lines_with_priority)
            if i in kept_indices
        )

    # Write to .muninn/sessions/
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    mn_path = sessions_dir / f"{timestamp}.mn"
    mn_path.write_text(result, encoding="utf-8")

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

    # P22: Update session index for future retrieval
    _update_session_index(repo_path, mn_path, result, ratio)

    return mn_path


def _update_session_index(repo_path: Path, mn_path: Path, compressed: str, ratio: float):
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

    entry = {
        "file": mn_path.name,
        "date": time.strftime("%Y-%m-%d"),
        "ratio": round(ratio, 1),
        "concepts": top_concepts,
        "tagged": tagged[:15],  # max 15 tagged lines per session
    }

    # Dedup by filename
    index = [e for e in index if e.get("file") != mn_path.name]
    index.append(entry)

    # Keep last 50 sessions in index (even if .mn files are pruned to 10)
    index = index[-50:]
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


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
        r_section = parts[1].split("\n\n", 1)  # R: entries end at blank line or EOF
        existing_lines = [l for l in r_section[0].split("\n") if l.strip()]
        existing_lines.append(log_line)
        existing_lines = existing_lines[-5:]  # keep last 5
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
        error_words = set(entry["error"].lower().split())
        query_words = set(query_lower.split())
        overlap = error_words & query_words
        if len(overlap) >= 2:  # at least 2 words match
            hints.append(f"KNOWN: {entry['error']} -> FIX: {entry['fix']}")
    return "\n".join(hints[:3])  # max 3 hints


def feed_from_hook(repo_path: Path):
    """Called by PreCompact/SessionEnd hook. Reads transcript_path from stdin JSON."""
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        print("ERROR: no valid JSON on stdin (expected hook event data)")
        sys.exit(1)

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        print("ERROR: no transcript_path in hook event data")
        sys.exit(1)

    jsonl_path = Path(transcript_path)
    if not jsonl_path.exists():
        print(f"ERROR: transcript not found: {jsonl_path}")
        sys.exit(1)

    # 1. Feed mycelium (co-occurrences)
    count = feed_from_transcript(jsonl_path, repo_path)
    print(f"MUNINN FEED: {count} messages -> mycelium ({repo_path.name})")

    # 2. Compress transcript into a .mn session file
    mn_path = compress_transcript(jsonl_path, repo_path)

    # 3. Auto-segment into tree branches (Brique 3)
    if mn_path:
        grow_branches_from_session(mn_path)

    # 4. Refresh tree temperatures
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)


def feed_history(repo_path: Path):
    """Feed mycelium from all past transcript JSONL files for this project.

    Scans ~/.claude/projects/<project>/ for .jsonl files and digests them.
    Tracks which files have been digested in .muninn/fed_transcripts.json.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
        if d.is_dir() and repo_name in d.name:
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

    m = Mycelium(repo_path)
    total_messages = 0
    new_files = 0

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

    print(f"=== MUNINN FEED HISTORY ===")
    print(f"  New transcripts: {new_files}")
    print(f"  Messages digested: {total_messages}")
    print(f"  Total fed transcripts: {len(fed)}")
    if total_messages > 0:
        print(f"\n{m.status()}")

    # Compress transcripts into .mn and auto-segment into branches
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    for project_dir in project_dirs:
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            mn_marker = sessions_dir / f"{jsonl_file.stem}.mn"
            if mn_marker.exists():
                continue
            mn_path = compress_transcript(jsonl_file, repo_path)
            if mn_path:
                created = grow_branches_from_session(mn_path)
                if created > 0:
                    print(f"  {jsonl_file.name}: {created} branches created")

    # Refresh tree
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)


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

        total_original += len(content)

        # Compress with full pipeline
        compressed = compress_file(f)
        total_compressed += len(compressed)

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

        ratio = len(content) / max(len(compressed), 1)
        print(f"  {f.name}: {len(content)} -> {len(compressed)} chars (x{ratio:.1f}), {created} branches")

    # Nourrit aussi le mycelium avec le contenu
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    print(f"\n  Total: {total_original} -> {total_compressed} chars (x{ratio:.1f})")
    print(f"  Branches created: {total_branches}")
    print(f"  Mycelium updated")


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.8 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap", "feed", "verify",
        "ingest", "recall",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
    parser.add_argument("--history", action="store_true", help="Feed from all past transcripts")
    args = parser.parse_args()

    # Set repo path for local codebook loading
    if args.repo:
        _REPO_PATH = Path(args.repo).resolve()
        _refresh_tree_paths()

    if args.command == "init":
        init_tree()
        return

    if args.command == "status":
        show_status()
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

    if args.command == "feed":
        repo = Path(args.repo or args.file or ".").resolve()
        _REPO_PATH = repo
        _refresh_tree_paths()
        if args.history:
            feed_history(repo)
        elif args.file and Path(args.file).suffix == ".jsonl":
            # Direct file mode: feed from a specific transcript
            count = feed_from_transcript(Path(args.file), repo)
            print(f"MUNINN FEED: {count} messages -> mycelium ({repo.name})")
            compress_transcript(Path(args.file), repo)
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
        force = args.file == "--force"
        prune(dry_run=not force)
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
