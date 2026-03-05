#!/usr/bin/env python3
"""
Muninn v0.2 — Moteur de compression memoire LLM.

Charge le codebook dynamiquement depuis CODEBOOK.json.
Deux couches de compression:
  1. Sinogrammes (CODEBOOK.json) — identifiants semantiques universels
  2. Texte (patterns frequents) — compression structurelle

Usage:
    python engine/core/muninn.py read <fichier>
    python engine/core/muninn.py compress <fichier>
    python engine/core/muninn.py tree <fichier>
    python engine/core/muninn.py status
    python engine/core/muninn.py boot [query]
"""
import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent

# ── CODEBOOK LOADER ──────────────────────────────────────────────

CODEBOOK_PATH = ROOT / "CODEBOOK.json"


def load_codebook() -> dict:
    """Load CODEBOOK.json and build compression tables."""
    with open(CODEBOOK_PATH, encoding="utf-8") as f:
        cb = json.load(f)

    # Build symbol -> concept and concept -> symbol maps
    sym_to_concept = {}
    concept_to_sym = {}
    text_to_sym = {}  # for text compression: desc/concept keywords -> symbol

    for sym, data in cb["symbols"].items():
        if not isinstance(data, dict) or "concept" not in data:
            continue
        concept = data["concept"]
        sym_to_concept[sym] = data
        concept_to_sym[concept] = sym

    # Build text compression rules from codebook
    # Map common text patterns to their sinogram equivalents
    text_rules = {}
    for sym, data in sym_to_concept.items():
        concept = data["concept"]
        desc = data.get("desc", "")

        # State symbols: map French state words
        if concept == "COMPLETE":
            for w in ("COMPLET", "COMPLETE", "complet"):
                text_rules[w] = sym
        elif concept == "RUNNING":
            for w in ("EN COURS", "en cours"):
                text_rules[w] = sym
        elif concept == "FAILED":
            for w in ("ECHOUE", "ECHOUÉ", "FAILED", "CASSÉ"):
                text_rules[w] = sym
        elif concept == "PENDING":
            for w in ("EN ATTENTE", "PENDING"):
                text_rules[w] = sym

        # Strata
        elif concept.startswith("S") and concept[1:2].isdigit():
            strate = concept.split("_")[0]  # S0, S1, etc.
            text_rules[strate] = sym

        # Patterns
        elif concept.startswith("P") and concept[1:2].isdigit():
            pass  # keep sinogram IDs for pattern types

        # Metrics
        elif concept == "P_VALUE":
            text_rules["p-value"] = sym
            text_rules["p="] = f"{sym}="
        elif concept == "EFFECT_SIZE":
            text_rules["Cohen's d"] = sym
            text_rules["d="] = f"{sym}="
        elif concept == "MIRROR_PAIRS":
            text_rules["mirror pairs"] = sym
        elif concept == "DISRUPTION":
            text_rules["D-index"] = sym

        # Repos
        elif concept == "REPO_YGG":
            for w in ("Yggdrasil", "yggdrasil"):
                text_rules[w] = sym
        elif concept == "REPO_MUNINN":
            for w in ("MUNINN", "Muninn", "muninn"):
                text_rules[w] = sym

    # Additional text compression (not in sinograms — structural)
    text_rules.update({
        "VALIDÉ": "✓", "FIXÉ": "✓",
        "PRÊT": "◉",
        # Short codes for common project terms
        "OpenAlex": "OA", "arXiv": "AX", "PMC": "PM",
        "Winter Tree": "WT", "Glyph Laplacian": "GL",
        "Blind Test": "BT", "Predictions": "P4",
        "Frame Builder": "FR", "Archéologie": "AR",
        "papers": "#p", "concepts": "#c", "chunks": "ch",
        "session": "@s", "Recall@": "R@",
    })

    return {
        "raw": cb,
        "sym_to_concept": sym_to_concept,
        "concept_to_sym": concept_to_sym,
        "text_rules": text_rules,
        "domains": cb.get("domains", {}),
    }


# Lazy-loaded global
_CB = None


def get_codebook():
    global _CB
    if _CB is None:
        _CB = load_codebook()
    return _CB


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

TREE_DIR = ROOT / "memory"
TREE_META = TREE_DIR / "tree.json"


def init_tree():
    """Initialize the Muninn memory tree."""
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
    """Read a node file and increment access counter."""
    tree = load_tree()
    node = tree["nodes"].get(name)
    if not node:
        return f"ERROR: node '{name}' not found"

    filepath = TREE_DIR / node["file"]
    if not filepath.exists():
        return f"ERROR: file '{filepath}' not found"

    # Track access (R4 prerequisite)
    node["access_count"] = node.get("access_count", 0) + 1
    node["last_access"] = time.strftime("%Y-%m-%d")
    save_tree(tree)

    return filepath.read_text(encoding="utf-8")


# ── COMPRESS ──────────────────────────────────────────────────────

def compress_line(line: str) -> str:
    """Compress a single line using the loaded codebook."""
    cb = get_codebook()
    result = line

    # Apply text rules (longest first)
    for pattern in sorted(cb["text_rules"].keys(), key=len, reverse=True):
        result = result.replace(pattern, cb["text_rules"][pattern])

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
    """Compress a full section into Muninn format."""
    cb = get_codebook()
    text_rules = cb["text_rules"]

    # Extract state
    state = "?"
    for pattern, code in [
        ("COMPLET", "✓"), ("VALIDÉ", "✓"), ("FIXÉ", "✓"),
        ("EN COURS", "⟳"), ("PRÊT", "◉"),
    ]:
        if pattern in header:
            state = code
            header = header.replace(f" — {pattern}", "").replace(f"— {pattern}", "")
            break

    # Extract session
    session = ""
    m = re.search(r"\(session\s+(\d+)", header)
    if m:
        session = f"@s{m.group(1)}"
        header = re.sub(r"\s*\(session\s+\d+.*?\)", "", header)

    header = header.replace("## ", "").strip()

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
    """Compress a full markdown file into Muninn format."""
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
    """Build a Muninn L-system tree from a source file.
    R3: compress BEFORE split. R2: split if over budget."""
    tree = load_tree()

    # R3: compress first
    compressed = compress_file(filepath)
    comp_lines = compressed.split("\n")

    print(f"\n  Source: {filepath}")
    print(f"  Original: {filepath.stat().st_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Lines: {len(comp_lines)}")

    # Does it fit in root? (R1 check)
    if len(comp_lines) <= BUDGET["root_lines"]:
        root_path = TREE_DIR / "root.mn"
        root_path.write_text(compressed, encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(comp_lines)
        tree["nodes"]["root"]["last_access"] = time.strftime("%Y-%m-%d")
        save_tree(tree)
        print(f"  Fits in root ({len(comp_lines)}/{BUDGET['root_lines']} lines)")
    else:
        # R2: split
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

        # Extract tags from section content for boot intelligence
        for section in sections:
            sec_lines = section.split("\n")
            first_line = sec_lines[0][:60]
            tags = extract_tags(section)

            if len(root_lines) + len(sec_lines) <= BUDGET["root_lines"]:
                root_lines.extend(sec_lines)
            else:
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                branch_path = TREE_DIR / branch_file

                branch_path.write_text(section, encoding="utf-8")
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

        # Enforce R1: root MUST fit budget
        if len(root_lines) > BUDGET["root_lines"]:
            print(f"  WARNING: root still {len(root_lines)} > {BUDGET['root_lines']}, force-splitting last entries")
            while len(root_lines) > BUDGET["root_lines"]:
                overflow = root_lines.pop()
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                (TREE_DIR / branch_file).write_text(overflow, encoding="utf-8")
                root_lines.append(f"\u2192{branch_name}:{overflow[:50]}")
                tree["nodes"][branch_name] = {
                    "type": "branch",
                    "file": branch_file,
                    "lines": 1,
                    "max_lines": BUDGET["branch_lines"],
                    "children": [],
                    "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0,
                    "tags": [],
                }
                branch_id += 1

        root_path = TREE_DIR / "root.mn"
        root_path.write_text("\n".join(root_lines), encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(root_lines)
        tree["nodes"]["root"]["children"] = [
            n for n in tree["nodes"] if n != "root"
        ]
        save_tree(tree)

        print(f"\n  Root: {len(root_lines)} lines, {branch_id} branches")


# ── BOOT INTELLIGENCE (R7) ──────────────────────────────────────

def extract_tags(text: str) -> list[str]:
    """Extract semantic tags from text for branch matching."""
    tags = set()
    cb = get_codebook()

    # Check for known concepts
    for concept, sym in cb["concept_to_sym"].items():
        # Match concept name parts in text
        for part in concept.lower().split("_"):
            if len(part) > 2 and part in text.lower():
                tags.add(concept)
                break

    # Check for common keywords
    keywords = [
        "bug", "fix", "pipeline", "scan", "glyph", "spectral",
        "blind test", "prediction", "film", "convention", "architecture",
        "memory", "compression", "tree", "codebook",
    ]
    for kw in keywords:
        if kw in text.lower():
            tags.add(kw)

    return sorted(tags)[:10]  # cap at 10 tags per node


def boot(query: str = "") -> str:
    """Boot sequence: load root + relevant branches based on query.
    R7: navigate by descent — load only what's needed."""
    tree = load_tree()
    nodes = tree["nodes"]

    # Always load root
    root_text = read_node("root")
    loaded = [("root", root_text)]

    if query:
        query_lower = query.lower()
        scored = []
        for name, node in nodes.items():
            if name == "root":
                continue
            tags = node.get("tags", [])
            # Score by tag match + access frequency
            tag_score = sum(1 for t in tags if any(
                q in t.lower() for q in query_lower.split()
            ))
            access_score = node.get("access_count", 0) * 0.1
            total = tag_score + access_score
            if total > 0:
                scored.append((name, total))

        # Load top matching branches (budget-aware)
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
        # No query: load root + most accessed branches
        ranked = sorted(
            [(n, d) for n, d in nodes.items() if n != "root"],
            key=lambda x: x[1].get("access_count", 0),
            reverse=True,
        )
        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]
        for name, node in ranked[:3]:  # top 3 by default
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
    """Decode a compressed line back to readable text."""
    cb = get_codebook()
    result = line

    # Reverse sinograms to concepts
    for sym, data in cb["sym_to_concept"].items():
        if sym in result:
            result = result.replace(sym, f"[{data['concept']}]")

    # Reverse text codes
    reverse_rules = {v: k for k, v in cb["text_rules"].items()
                     if len(v) > 0 and v != k}
    for code in sorted(reverse_rules.keys(), key=len, reverse=True):
        if code in result:
            result = result.replace(code, reverse_rules[code])

    return result


# ── PRUNE (R4) ───────────────────────────────────────────────────

def prune(dry_run: bool = True):
    """R4: promote hot nodes, demote cold nodes, kill dead ones.
    - Hot = access_count > median → content summary gets promoted to root pointers
    - Cold = access_count == 0 AND last_access > 30 days → candidate for pruning
    - Dead = cold for 90+ days → deleted
    """
    tree = load_tree()
    nodes = tree["nodes"]
    today = time.strftime("%Y-%m-%d")

    branches = {n: d for n, d in nodes.items() if d["type"] == "branch"}
    if not branches:
        print("  No branches to prune.")
        return

    # Calculate access stats
    counts = [d.get("access_count", 0) for d in branches.values()]
    median_access = sorted(counts)[len(counts) // 2] if counts else 0

    print(f"=== MUNINN PRUNE (R4) === {'[DRY RUN]' if dry_run else ''}")
    print(f"  Branches: {len(branches)}")
    print(f"  Median access: {median_access}")
    print()

    hot, cold, dead = [], [], []

    for name, node in branches.items():
        acc = node.get("access_count", 0)
        last = node.get("last_access", "2026-01-01")

        # Days since last access
        try:
            from datetime import datetime
            days_cold = (datetime.strptime(today, "%Y-%m-%d") -
                        datetime.strptime(last, "%Y-%m-%d")).days
        except ValueError:
            days_cold = 0

        if acc > median_access and acc > 0:
            hot.append((name, acc))
            print(f"  HOT  {name}: acc={acc} (above median {median_access})")
        elif acc == 0 and days_cold >= 90:
            dead.append((name, days_cold))
            print(f"  DEAD {name}: acc=0, cold for {days_cold} days")
        elif acc == 0 and days_cold >= 30:
            cold.append((name, days_cold))
            print(f"  COLD {name}: acc=0, cold for {days_cold} days")
        else:
            print(f"  OK   {name}: acc={acc}, {days_cold}d since last access")

    if not dry_run:
        # Delete dead branches
        for name, days in dead:
            node = nodes[name]
            filepath = TREE_DIR / node["file"]
            if filepath.exists():
                filepath.unlink()
            del nodes[name]
            if name in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(name)
            print(f"  DELETED {name} (dead {days} days)")

        save_tree(tree)

    print(f"\n  Summary: {len(hot)} hot, {len(cold)} cold, {len(dead)} dead")
    if dry_run and dead:
        print("  Run with --force to actually delete dead nodes.")


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
    words = len(text.split())

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
        "file": str(filepath),
        "lines": lines,
        "chars": chars,
        "words": words,
        "tokens_est": tokens_before,
        "codebook_hits": hits,
        "chars_saved": total_saved,
        "tokens_after": tokens_after,
        "ratio": round(tokens_before / max(tokens_after, 1), 2),
    }


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Muninn v0.2 — Memory compression engine")
    parser.add_argument("command", choices=["read", "compress", "tree", "status", "init", "boot", "decode", "prune"])
    parser.add_argument("file", nargs="?", help="Input file or query")
    args = parser.parse_args()

    if args.command == "init":
        init_tree()
        return

    if args.command == "status":
        show_status()
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
        print(f"  Lines: {stats['lines']}")
        print(f"  Tokens (est): {stats['tokens_est']}")
        print(f"\n  Top codebook hits:")
        for pattern, info in sorted(stats["codebook_hits"].items(),
                                     key=lambda x: x[1]["saved"], reverse=True)[:15]:
            print(f"    {info['count']:3d}x '{pattern}' -> '{info['code']}' "
                  f"(saves {info['saved']} chars)")
        print(f"\n  Tokens: {stats['tokens_est']} -> {stats['tokens_after']} "
              f"(x{stats['ratio']})")

    elif args.command == "compress":
        compressed = compress_file(filepath)
        print(compressed)
        orig_chars = filepath.stat().st_size
        comp_chars = len(compressed)
        print(f"\n# {orig_chars} -> {comp_chars} chars "
              f"(x{orig_chars / max(comp_chars, 1):.1f})")

    elif args.command == "tree":
        build_tree(filepath)


if __name__ == "__main__":
    main()
