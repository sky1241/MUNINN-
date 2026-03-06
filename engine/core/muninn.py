#!/usr/bin/env python3
"""
Muninn v0.4 — Moteur de compression memoire LLM.
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
"""
import argparse
import io
import json
import re
import sys
import time
from collections import Counter
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
    if repo_path:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            mycelium_rules = m.get_compression_rules()
        except (ImportError, Exception):
            pass

    return {
        "text_rules": text_rules,
        "mycelium_rules": mycelium_rules,
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
    with open(TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


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
    """Compress a single line using universal rules + mycelium fusions."""
    cb = get_codebook()
    result = line

    # Apply text rules (longest first to avoid partial matches)
    for pattern in sorted(cb["text_rules"].keys(), key=len, reverse=True):
        result = result.replace(pattern, cb["text_rules"][pattern])

    # Mycelium-aware compression: strong fusions mean the concepts are
    # predictable given each other. Remove the shorter concept when both
    # appear in the same line AND fusion strength >= 10 (very strong link).
    # This is self-information filtering: predictable = low information = strip.
    strong_fusions = {k: v for k, v in cb["mycelium_rules"].items()
                      if v["strength"] >= 10}
    for key, rule in strong_fusions.items():
        a, b = rule["concepts"]
        result_lower = result.lower()
        if a in result_lower and b in result_lower:
            # Remove the shorter word (less information content)
            drop = b if len(b) <= len(a) else a
            result = re.sub(rf'\s+\b{re.escape(drop)}\b', '', result,
                          count=1, flags=re.IGNORECASE)

    # Strip markdown formatting
    result = re.sub(r"^##\s+", "", result)
    result = result.replace("**", "")
    result = re.sub(r"^-\s+", "", result)
    result = result.replace("`", "")

    # Compress large numbers
    def shorten_number(m):
        n = int(m.group(0).replace(",", ""))
        if n >= 1_000_000:
            return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K" if n % 1_000 == 0 else f"{n / 1_000:.1f}K"
        return str(n)

    result = re.sub(r"\d{1,3}(?:,\d{3})+", shorten_number, result)
    result = re.sub(r"\s{2,}", " ", result).strip()

    return result


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
            # Remove state from header (various formats)
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

    header = re.sub(r"^#+\s*", "", header).strip()

    # Apply text rules to header
    for pattern in sorted(text_rules.keys(), key=len, reverse=True):
        header = header.replace(pattern, text_rules[pattern])

    compressed_header = f"{state}{header}{session}"

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
            access_score = node.get("access_count", 0) * 0.1
            total = tag_score + access_score
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
            key=lambda x: x[1].get("access_count", 0),
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
    """R4: promote hot, demote cold, kill dead."""
    tree = load_tree()
    nodes = tree["nodes"]
    today = time.strftime("%Y-%m-%d")

    branches = {n: d for n, d in nodes.items() if d["type"] == "branch"}
    if not branches:
        print("  No branches to prune.")
        return

    counts = [d.get("access_count", 0) for d in branches.values()]
    median_access = sorted(counts)[len(counts) // 2] if counts else 0

    print(f"=== MUNINN PRUNE (R4) === {'[DRY RUN]' if dry_run else ''}")
    print(f"  Branches: {len(branches)}, Median access: {median_access}")
    print()

    hot, cold, dead = [], [], []

    for name, node in branches.items():
        acc = node.get("access_count", 0)
        last = node.get("last_access", "2026-01-01")

        try:
            from datetime import datetime
            days_cold = (datetime.strptime(today, "%Y-%m-%d") -
                        datetime.strptime(last, "%Y-%m-%d")).days
        except ValueError:
            days_cold = 0

        if acc > median_access and acc > 0:
            hot.append((name, acc))
            print(f"  HOT  {name}: acc={acc}")
        elif acc == 0 and days_cold >= 90:
            dead.append((name, days_cold))
            print(f"  DEAD {name}: cold {days_cold}d")
        elif acc == 0 and days_cold >= 30:
            cold.append((name, days_cold))
            print(f"  COLD {name}: cold {days_cold}d")
        else:
            print(f"  OK   {name}: acc={acc}, {days_cold}d")

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

    print("=== MUNINN TREE ===")
    print(f"  Version: {tree['version']}")
    print(f"  Codebook: {tree.get('codebook_version', '?')}")
    print(f"  Nodes: {len(nodes)}")
    print()

    total_lines = 0
    for name, node in nodes.items():
        ntype = node["type"]
        prefix = {"root": "R", "branch": "B", "leaf": "L"}.get(ntype, "?")
        fill = node["lines"] / node["max_lines"] * 100
        over = " OVER!" if node["lines"] > node["max_lines"] else ""
        total_lines += node["lines"]
        children = f" ch=[{','.join(node['children'])}]" if node.get("children") else ""
        tags = f" tags=[{','.join(node.get('tags', [])[:3])}]" if node.get("tags") else ""
        access = node.get("access_count", 0)
        print(f"  [{prefix}] {name}: {node['lines']}/{node['max_lines']} "
              f"({fill:.0f}%){over} acc={access}{children}{tags}")

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


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.3 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
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
