#!/usr/bin/env python3
"""
Muninn v0.7 — Moteur de compression memoire LLM.
UNIVERSEL — zero hardcode projet. Fonctionne sur n'importe quel repo.

Deux couches de compression:
  1. Universelle (UNIVERSAL_RULES) — BPE-native English compact
  2. Mycelium (<repo>/.muninn/mycelium.json) — codebook vivant par co-occurrences

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
_REPO_PATH = None


def get_codebook():
    global _CB
    if _CB is None:
        _CB = load_codebook(_REPO_PATH)
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

TREE_DIR = MUNINN_ROOT / "memory"
TREE_META = TREE_DIR / "tree.json"


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
    with open(TREE_META, encoding="utf-8") as f:
        return json.load(f)


def save_tree(tree):
    tree["updated"] = time.strftime("%Y-%m-%d")
    with open(TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


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
        r"\bcorresponds to\b", r"\binstead of\b", r"\bbecause of\b",
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
    # Remove shorter concept when both appear (self-information filtering).
    strong_fusions = {k: v for k, v in cb["mycelium_rules"].items()
                      if v["strength"] >= 10}
    for key, rule in strong_fusions.items():
        a, b = rule["concepts"]
        result_lower = result.lower()
        if a in result_lower and b in result_lower:
            drop = b if len(b) <= len(a) else a
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

    return "\n".join(output)


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
            while len(root_lines) > BUDGET["root_lines"]:
                overflow = root_lines.pop()
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                (TREE_DIR / branch_file).write_text(overflow, encoding="utf-8")
                root_lines.append(f"\u2192{branch_name}:{overflow[:50]}")
                tree["nodes"][branch_name] = {
                    "type": "branch", "file": branch_file,
                    "lines": 1, "max_lines": BUDGET["branch_lines"],
                    "children": [], "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0, "tags": [],
                }
                branch_id += 1

        root_path = TREE_DIR / "root.mn"
        root_path.write_text("\n".join(root_lines), encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(root_lines)
        tree["nodes"]["root"]["children"] = [n for n in tree["nodes"] if n != "root"]
        save_tree(tree)
        print(f"\n  Root: {len(root_lines)} lines, {branch_id} branches")


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
    """R7: load root + relevant branches based on query."""
    tree = load_tree()
    nodes = tree["nodes"]

    root_text = read_node("root")
    loaded = [("root", root_text)]

    if query:
        query_lower = query.lower()
        scored = []
        for name, node in nodes.items():
            if name == "root":
                continue
            tags = node.get("tags", [])
            tag_score = sum(1 for t in tags if any(
                q in t.lower() for q in query_lower.split()
            ))
            temp_score = node.get("temperature", 0) * 0.5
            total = tag_score + temp_score
            if total > 0:
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

    output = []
    for name, text in loaded:
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
            session_tokens = len(session_text) // 4

            if session_tokens <= remaining_budget:
                output.append(f"=== last_session ({latest.stem}) ===")
                output.append(session_text)
            elif remaining_budget > 200:
                # Take tail (most recent context) that fits budget
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
    tokens_before = chars // 4
    tokens_after = (chars - total_saved) // 4

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

    # Token estimates
    orig_tokens = len(original) // 4
    comp_tokens = len(compressed) // 4
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
    print(f"\n  Compression:")
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

def parse_transcript(jsonl_path: Path) -> list[str]:
    """Parse a Claude Code transcript JSONL and extract text messages.

    Returns a list of text strings (user + assistant messages).
    Skips thinking blocks, tool calls, and system messages.
    """
    texts = []
    with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only process user and assistant messages
            if entry.get("type") not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            content = message.get("content", [])

            if isinstance(content, str):
                texts.append(content)
                continue

            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if len(text) >= 20:  # skip tiny messages
                        texts.append(text)

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

    # Compress each section
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

    # Layer 8: LLMLingua-2 (BERT-based token scoring, optional)
    try:
        from llmlingua import PromptCompressor
        compressor = PromptCompressor(
            model_name="microsoft/llmlingua-2-xlm-roberta-large-meetingbank",
            use_llmlingua2=True,
            device_map="cpu",
        )
        lingua_result = compressor.compress_prompt([result], rate=0.5)
        lingua_compressed = lingua_result["compressed_prompt"]
        if len(lingua_compressed) < len(result):
            result = lingua_compressed
    except ImportError:
        pass  # LLMLingua not installed — skip Layer 8
    except Exception as e:
        print(f"  LLMLingua warning: {e}")

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

    orig_tokens = len(all_text) // 4
    comp_tokens = len(result) // 4
    ratio = orig_tokens / max(comp_tokens, 1)
    print(f"MUNINN SESSION: {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}) -> {mn_path.name}")

    return mn_path


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
    compress_transcript(jsonl_path, repo_path)

    # 3. Refresh tree temperatures
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
        with open(fed_path, encoding="utf-8") as f:
            fed = set(json.load(f))

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

        # Subagent transcripts
        subagents_dir = project_dir / "subagents" if (project_dir / "subagents").exists() else None
        if subagents_dir:
            # Also check inside session subdirectories
            for sub_dir in project_dir.iterdir():
                if sub_dir.is_dir():
                    sa_dir = sub_dir / "subagents"
                    if sa_dir.exists():
                        for jsonl_file in sorted(sa_dir.glob("*.jsonl")):
                            file_key = str(jsonl_file)
                            if file_key in fed:
                                continue
                            texts = parse_transcript(jsonl_file)
                            if texts:
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

    # Refresh tree
    tree = load_tree()
    refresh_tree_metadata(tree)
    save_tree(tree)


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.6 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap", "feed", "verify",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
    parser.add_argument("--history", action="store_true", help="Feed from all past transcripts")
    args = parser.parse_args()

    # Set repo path for local codebook loading
    if args.repo:
        _REPO_PATH = Path(args.repo).resolve()

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
        bootstrap_mycelium(Path(args.file))
        return

    if args.command == "feed":
        repo = Path(args.repo or args.file or ".").resolve()
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

    if args.command == "boot":
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
        verify_compression(Path(args.file))
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
