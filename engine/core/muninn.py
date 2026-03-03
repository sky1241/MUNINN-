#!/usr/bin/env python3
"""
Muninn — Moteur de compression mémoire LLM.

Winter tree pattern : lit, compresse, subdivise, écrit.
Auto-implémentation : se compresse lui-même.

Usage:
    python engine/core/muninn.py read <fichier>         # Lit et affiche les stats
    python engine/core/muninn.py compress <fichier>     # Compresse en format Muninn
    python engine/core/muninn.py tree <fichier>         # Construit l'arbre L-system
    python engine/core/muninn.py status                 # État de l'arbre
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# ── CODEBOOK ─────────────────────────────────────────────────────
# MA CLÉ — 25 règles de traduction

CODEBOOK = {
    # ÉTATS (7-8 chars → 1)
    "COMPLET": "✓",
    "VALIDÉ": "✓",
    "FIXÉ": "✓",
    "EN COURS": "⟳",
    "PRÊT": "◉",
    "ÉCHOUÉ": "✗",

    # IDENTITÉS (15-30 chars → 2-3)
    "Yggdrasil Engine": "YG",
    "OpenAlex": "OA",
    "arXiv": "AX",
    "PMC": "PM",

    # MODULES (20-40 chars → 2-3)
    "Winter Tree": "WT",
    "Glyph Laplacian": "GL",
    "Blind Test": "BT",
    "Predictions": "P4",
    "Frame Builder": "FR",
    "Archéologie": "AR",
    "Météorites": "MR",
    "Mapper": "MP",

    # MÉTRIQUES
    "papers": "#p",
    "concepts": "#c",
    "chunks": "ch",
    "session": "@s",
    "Cohen's d": "d",
    "Recall@": "R@",
}

# Inverse codebook for decompression
DECODE = {v: k for k, v in CODEBOOK.items()}

# ── BUDGET ────────────────────────────────────────────────────────

BUDGET = {
    "root_lines": 100,
    "branch_lines": 150,
    "leaf_lines": 200,
    "tokens_per_line": 16,  # mesuré sur MEMORY.md réel
    "max_loaded_tokens": 30_000,
    "compression_ratio": 4.6,  # mesuré sur codebook_v0
}

# ── TREE STRUCTURE ────────────────────────────────────────────────

TREE_DIR = ROOT / "memory"
TREE_META = TREE_DIR / "tree.json"


def init_tree():
    """Initialize the Muninn memory tree."""
    TREE_DIR.mkdir(parents=True, exist_ok=True)

    tree = {
        "version": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "budget": BUDGET,
        "codebook_version": "v0",
        "nodes": {
            "root": {
                "type": "root",
                "file": "root.mn",
                "lines": 0,
                "max_lines": BUDGET["root_lines"],
                "children": [],
                "last_access": time.strftime("%Y-%m-%d"),
                "access_count": 0,
            }
        },
    }

    with open(TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)

    # Create empty root
    (TREE_DIR / "root.mn").write_text(
        "# MUNINN ROOT\n# codebook=v0\n", encoding="utf-8"
    )

    print(f"  Tree initialized: {TREE_DIR}")
    print(f"  Root: {TREE_DIR / 'root.mn'}")
    return tree


def load_tree():
    """Load existing tree or init."""
    if not TREE_META.exists():
        return init_tree()
    with open(TREE_META, encoding="utf-8") as f:
        return json.load(f)


def save_tree(tree):
    """Save tree state."""
    with open(TREE_META, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)


# ── READ ──────────────────────────────────────────────────────────

def analyze_file(filepath: Path) -> dict:
    """Analyze a file for compression potential."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.count("\n")
    chars = len(text)
    words = len(text.split())

    # Count codebook hits
    hits = {}
    for pattern, code in CODEBOOK.items():
        count = text.count(pattern)
        if count > 0:
            saved_chars = count * (len(pattern) - len(code))
            hits[pattern] = {"count": count, "code": code, "saved": saved_chars}

    total_saved = sum(h["saved"] for h in hits.values())

    # Estimate tokens
    tokens_before = chars // 4  # rough estimate
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


# ── COMPRESS ──────────────────────────────────────────────────────

def compress_line(line: str) -> str:
    """Compress a single line using the codebook."""
    result = line

    # Apply codebook replacements (longest first to avoid partial matches)
    for pattern in sorted(CODEBOOK.keys(), key=len, reverse=True):
        result = result.replace(pattern, CODEBOOK[pattern])

    # Compress markdown headers
    result = re.sub(r"^##\s+", "", result)

    # Compress bold markers
    result = result.replace("**", "")

    # Compress bullet points
    result = re.sub(r"^-\s+", "", result)

    # Compress backtick paths (keep path, remove backticks)
    result = result.replace("`", "")

    # Compress common words in context
    result = result.replace("session ", "@s")
    result = result.replace(" papers", "#p")
    result = result.replace(" concepts", "#c")
    result = result.replace(" chunks", "ch")

    # Compress numbers with K/M
    def shorten_number(m):
        n = int(m.group(0).replace(",", ""))
        if n >= 1_000_000:
            return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K" if n % 1_000 == 0 else f"{n / 1_000:.1f}K"
        return str(n)

    result = re.sub(r"\d{1,3}(?:,\d{3})+", shorten_number, result)

    # Collapse multiple spaces
    result = re.sub(r"\s{2,}", " ", result).strip()

    return result


def compress_section(header: str, lines: list[str]) -> str:
    """Compress a full section into Muninn format."""
    # Extract state from header
    state = "?"
    for pattern, code in [
        ("COMPLET", "✓"), ("VALIDÉ", "✓"), ("FIXÉ", "✓"),
        ("EN COURS", "⟳"), ("PRÊT", "◉"),
    ]:
        if pattern in header:
            state = code
            header = header.replace(f" — {pattern}", "").replace(f"— {pattern}", "")
            break

    # Extract session from header
    session = ""
    m = re.search(r"\(session\s+(\d+)", header)
    if m:
        session = f"@s{m.group(1)}"
        header = re.sub(r"\s*\(session\s+\d+.*?\)", "", header)

    # Clean header
    header = header.replace("## ", "").strip()

    # Compress ID
    for pattern, code in CODEBOOK.items():
        header = header.replace(pattern, code)

    # Build compressed line
    compressed_header = f"{state}{header}{session}"

    # Compress body lines
    body = []
    for line in lines:
        if not line.strip():
            continue
        cl = compress_line(line)
        if cl:
            body.append(cl)

    # Join with | if short enough, newlines otherwise
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
            continue  # skip top-level header
        else:
            current_lines.append(line)

    if current_header:
        sections.append((current_header, current_lines))

    # Compress each section
    output = ["# MUNINN|codebook=v0"]
    for header, slines in sections:
        compressed = compress_section(header, slines)
        output.append(compressed)

    return "\n".join(output)


# ── TREE BUILD ────────────────────────────────────────────────────

def build_tree(filepath: Path):
    """Build a Muninn L-system tree from a source file."""
    tree = load_tree()

    compressed = compress_file(filepath)
    comp_lines = compressed.split("\n")

    print(f"\n  Source: {filepath}")
    print(f"  Original: {filepath.stat().st_size} chars")
    print(f"  Compressed: {len(compressed)} chars")
    print(f"  Lines: {len(comp_lines)}")

    # Does it fit in root?
    if len(comp_lines) <= BUDGET["root_lines"]:
        # Write directly to root
        root_path = TREE_DIR / "root.mn"
        root_path.write_text(compressed, encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(comp_lines)
        tree["nodes"]["root"]["last_access"] = time.strftime("%Y-%m-%d")
        save_tree(tree)
        print(f"  → Fits in root ({len(comp_lines)}/{BUDGET['root_lines']} lines)")
        print(f"  Written: {root_path}")
    else:
        # SPLIT — R2 rule
        print(f"  → Exceeds root budget, splitting...")
        # Keep first N sections in root, overflow to branches
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

        # Root gets pointers, branches get content
        root_lines = [header]
        branch_id = 0
        for section in sections:
            sec_lines = section.split("\n")
            first_line = sec_lines[0][:60]

            if len(root_lines) + len(sec_lines) <= BUDGET["root_lines"]:
                root_lines.extend(sec_lines)
            else:
                # Create branch
                branch_name = f"b{branch_id:02d}"
                branch_file = f"{branch_name}.mn"
                branch_path = TREE_DIR / branch_file

                branch_path.write_text(section, encoding="utf-8")

                root_lines.append(f"→{branch_name}:{first_line}")

                tree["nodes"][branch_name] = {
                    "type": "branch",
                    "file": branch_file,
                    "lines": len(sec_lines),
                    "max_lines": BUDGET["branch_lines"],
                    "children": [],
                    "last_access": time.strftime("%Y-%m-%d"),
                    "access_count": 0,
                }
                tree["nodes"]["root"]["children"].append(branch_name)

                branch_id += 1
                print(f"    Branch {branch_name}: {len(sec_lines)} lines ← {first_line}")

        # Write root
        root_path = TREE_DIR / "root.mn"
        root_path.write_text("\n".join(root_lines), encoding="utf-8")
        tree["nodes"]["root"]["lines"] = len(root_lines)
        save_tree(tree)

        print(f"\n  Root: {len(root_lines)} lines, {branch_id} branches")
        print(f"  Written: {root_path}")


# ── STATUS ────────────────────────────────────────────────────────

def show_status():
    """Show tree status."""
    tree = load_tree()
    nodes = tree["nodes"]

    print("=== MUNINN TREE ===")
    print(f"  Version: {tree['version']}")
    print(f"  Codebook: {tree['codebook_version']}")
    print(f"  Nodes: {len(nodes)}")
    print()

    total_lines = 0
    for name, node in nodes.items():
        prefix = "🌳" if node["type"] == "root" else "🌿" if node["type"] == "branch" else "🍃"
        fill = node["lines"] / node["max_lines"] * 100
        total_lines += node["lines"]
        children = f" →{','.join(node['children'])}" if node.get("children") else ""
        print(f"  {prefix} {name}: {node['lines']}/{node['max_lines']} "
              f"({fill:.0f}%){children}")

    est_tokens = total_lines * BUDGET["tokens_per_line"]
    est_compressed = est_tokens / BUDGET["compression_ratio"]
    print(f"\n  Total: {total_lines} lines ≈ {est_tokens} tok brut ≈ {est_compressed:.0f} tok compressé")
    print(f"  Budget: {est_compressed:.0f}/{BUDGET['max_loaded_tokens']} tokens ({est_compressed/BUDGET['max_loaded_tokens']*100:.1f}%)")


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Muninn — Memory compression engine")
    parser.add_argument("command", choices=["read", "compress", "tree", "status", "init"])
    parser.add_argument("file", nargs="?", help="Input file")
    args = parser.parse_args()

    if args.command == "init":
        init_tree()
        return

    if args.command == "status":
        show_status()
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
        print(f"  Chars: {stats['chars']}")
        print(f"  Words: {stats['words']}")
        print(f"  Tokens (est): {stats['tokens_est']}")
        print(f"\n  Codebook hits:")
        for pattern, info in sorted(stats["codebook_hits"].items(),
                                     key=lambda x: x[1]["saved"], reverse=True):
            print(f"    {info['count']:3d}× '{pattern}' → '{info['code']}' "
                  f"(saves {info['saved']} chars)")
        print(f"\n  Total chars saved: {stats['chars_saved']}")
        print(f"  Tokens: {stats['tokens_est']} → {stats['tokens_after']} "
              f"(ratio ×{stats['ratio']})")

    elif args.command == "compress":
        compressed = compress_file(filepath)
        print(compressed)
        orig_chars = filepath.stat().st_size
        comp_chars = len(compressed)
        print(f"\n# {orig_chars} → {comp_chars} chars "
              f"(×{orig_chars/max(comp_chars,1):.1f})")

    elif args.command == "tree":
        build_tree(filepath)


if __name__ == "__main__":
    main()
