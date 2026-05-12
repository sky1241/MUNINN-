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
# CHUNK C8 (2026-05-08): single source of truth = pyproject.toml.
# Dynamically resolved via importlib.metadata; fallback only if the
# package is run from a checkout without `pip install -e .`.
try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError
    try:
        __version__ = _pkg_version("muninn")
    except PackageNotFoundError:
        __version__ = "1.0.0"  # checkout fallback (sync with pyproject.toml)
except Exception:
    __version__ = "1.0.0"

import argparse
import io
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MUNINN_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(MUNINN_ROOT / "engine" / "core"))
from tokenizer import count_tokens, token_count
from _secrets import redact_secrets_text as _redact_secrets_text
from _secrets import secure_perms  # P0bis (2026-05-09): chmod sensitive writes
try:
    from sentiment import score_sentiment, score_session
    _HAS_SENTIMENT = True
except ImportError:
    _HAS_SENTIMENT = False

# Lazy-loaded global
_CB = None
_CB_REPO = None
_REPO_PATH = None
_SKIP_L9 = False
_CORE_DIR = str(Path(__file__).resolve().parent)

# M5 fix: single source of truth for secret patterns — import from _secrets.py
# instead of duplicating the 24+ patterns list here. Prevents silent drift.
try:
    from _secrets import _SECRET_PATTERNS, _COMPILED_PATTERNS as _COMPILED_SECRET_PATTERNS
except ImportError:
    from engine.core._secrets import _SECRET_PATTERNS, _COMPILED_PATTERNS as _COMPILED_SECRET_PATTERNS


# Legacy globals — recomputed by _refresh_tree_paths() once _REPO_PATH is set.
# BUG-091 follow-up (2026-05-08): default to MUNINN_ROOT/.muninn/tree (runtime,
# gitignored) instead of MUNINN_ROOT/memory (tracked). Callers that forget to
# set _REPO_PATH no longer pollute the tracked tree.json with stale data.
TREE_DIR = MUNINN_ROOT / ".muninn" / "tree"
TREE_META = TREE_DIR / "tree.json"

# Ensure sub-modules can find us as 'muninn' even when run as __main__
sys.modules.setdefault('muninn', sys.modules[__name__])

# ── SUB-MODULE RE-EXPORTS ─────────────────────────────────────
# Sub-modules access shared globals via `import muninn as _m`.
# Import order matters: layers first (no deps), tree second, feed third.
from muninn_layers import *  # noqa: F401,F403
from muninn_tree import *    # noqa: F401,F403
from muninn_feed import *    # noqa: F401,F403

# Chunk C.1 split (2026-05-11 nuit): install/hooks/cron + scrub moved to
# sibling modules. Re-import here so `from muninn import install_hooks` etc.
# keep working unchanged for downstream callers.
from muninn_install import (  # noqa: F401
    install_hooks, install_cron, _detect_init_system,
    _repos_registry_path, _load_repos_registry, _register_repo,
    _generate_bridge_hook, _generate_post_tool_failure_hook,
    _generate_subagent_start_hook, _generate_session_start_hook,
    _install_pre_tool_use_hooks, _install_scaling_hooks,
    _copy_hooks_from_source,
)
from muninn_secrets import (  # noqa: F401
    scrub_secrets, purge_secrets_db,
    _SCRUB_EXTENSIONS, _TRIGGER_VALUE_PATTERNS,
    _handle_scrub_command, _handle_purge_secrets_command,
)


# ── SCAN — auto-generate local codebook (R5) ────────────────────

def scan_repo(repo_path: Path, output_path: str = None):
    """Scan a repo to auto-generate its local codebook.
    Finds frequent words, entities, paths, numbers and assigns short codes.
    This is R5: codebook local per node.
    CHUNK 9: If output_path given, writes neuron map JSON for UI."""
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
    import tempfile as _tmpmod
    _fd, _tmp = _tmpmod.mkstemp(dir=str(local_path.parent), suffix=".tmp")
    try:
        with open(_fd, "w", encoding="utf-8") as f:
            json.dump(local, f, ensure_ascii=False, indent=2)
        os.replace(_tmp, str(local_path))
    except Exception:
        if os.path.exists(_tmp):
            os.unlink(_tmp)
        raise

    print(f"  Generated: {len(encode)} local codes")
    print(f"  Saved: {_safe_path(local_path)}")

    # Show top 15
    print(f"\n  Top codes:")
    shown = [(p, c) for p, c in encode.items() if p not in ("## ", "**", "- ")]
    for pattern, code in shown[:15]:
        orig = next((c[1] for c in candidates if c[0] == pattern), 0)
        print(f"    '{pattern}' -> '{code}' ({orig}x)")

    # CHUNK 9: Generate neuron map JSON for UI if output requested
    if output_path:
        nodes = []
        connections = []
        node_ids = set()
        level_map = {"word": "F", "entity": "R", "path": "I", "number": "B"}
        zone_map = {"word": "Concepts", "entity": "Entites",
                    "path": "Structure", "number": "Metriques"}
        max_count = candidates[0][1] if candidates else 1
        for i, (pattern, count, savings, ptype) in enumerate(candidates[:80]):
            nid = re.sub(r'[^a-zA-Z0-9_]', '_', pattern.lower())
            if nid in node_ids:
                nid = f"{nid}_{i}"
            node_ids.add(nid)
            confidence = min(100, int(100 * count / max_count))
            temperature = count / max_count if max_count > 0 else 0.0
            nodes.append({
                "id": nid, "label": pattern,
                "level": level_map.get(ptype, "F"),
                "status": "done" if pattern in encode else "todo",
                "entry": "", "depth": 0 if ptype == "entity" else 1,
                "confidence": confidence,
                "temperature": round(temperature, 3),
                "zone": zone_map.get(ptype, ""),
            })
        # Co-occurrence connections
        file_concepts = {}
        for f in repo_path.rglob("*"):
            if f.is_file() and f.suffix in {".py", ".md", ".txt", ".rs", ".ts", ".js"}:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")[:10000]
                    present = [n["id"] for n in nodes if n["label"].lower() in text.lower()]
                    for a in present:
                        for b in present:
                            if a < b:
                                connections.append({"from": a, "to": b})
                except (PermissionError, OSError):
                    pass
        # Dedup connections
        seen = set()
        deduped = []
        for c in connections:
            key = (c["from"], c["to"])
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        scan_data = {"nodes": nodes, "connections": deduped[:500]}
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(scan_data, f, ensure_ascii=False, indent=2)
        print(f"\n  Neuron map: {len(nodes)} nodes, {len(deduped)} connections -> {output_path}")


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


def bootstrap_mycelium(repo_path: Path):
    """Cold start: scan repo files and feed the mycelium.

    Reads all human-written files (code, docs, config) and feeds them
    to the mycelium as co-occurrence observations. This bootstraps the
    living codebook from scratch on a new repo.
    """
    repo_path = repo_path.resolve()
    # CRITICAL (2026-05-11 PM hotfix): propagate _REPO_PATH to the package
    # namespace AND the local module global, then refresh TREE_DIR/TREE_META,
    # BEFORE any tree write. Without this, the module-level TREE_DIR global
    # (hardcoded to MUNINN_ROOT at import) wins, and bootstrap_mycelium called
    # from a test with a tmp_path leaks into the source repo. Caught by
    # tests/test_wire_observe_latex.py::test_bootstrap_picks_up_tex_files.
    try:
        import muninn as _pkg
        _pkg._REPO_PATH = repo_path
    except Exception:
        pass
    global _REPO_PATH
    _REPO_PATH = repo_path
    _refresh_tree_paths()
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
                    "**/*.mn", "**/*.tex"]:
        for f in repo_path.glob(pattern):
            parts = f.relative_to(repo_path).parts
            if any(p.startswith(".") or p in skip_dirs for p in parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if len(text) < 50_000:
                    clean = _redact_secrets_text(text)
                    if f.suffix == ".tex":
                        m.observe_latex(clean)
                    else:
                        m.observe_text(clean)
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
            secure_perms(mn_temp)
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

    # Write to tree. CRITICAL (2026-05-11 PM hotfix): compute target paths
    # from the `repo_path` argument directly — the legacy module global
    # TREE_DIR is hardcoded to MUNINN_ROOT at import time and leaks the
    # source repo when bootstrap_mycelium is called from a test with a
    # tmp_path target. Propagate _REPO_PATH to the package namespace so
    # downstream code (load_tree, save_tree) targets the same repo.
    try:
        import muninn as _pkg
        _pkg._REPO_PATH = repo_path
    except Exception:
        pass
    global _REPO_PATH
    _REPO_PATH = repo_path
    _refresh_tree_paths()
    target_tree_dir = repo_path / ".muninn" / "tree"
    target_tree_dir.mkdir(parents=True, exist_ok=True)
    tree = load_tree()
    root_path = target_tree_dir / "root.mn"
    import tempfile as _tmpmod
    _fd, _tmp = _tmpmod.mkstemp(dir=str(root_path.parent), suffix=".tmp")
    try:
        with open(_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(_tmp, str(root_path))
    except Exception:
        if os.path.exists(_tmp):
            os.unlink(_tmp)
        raise
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
        secure_perms(wt_path)
        print(f"  WINTER_TREE.md generated for human")
    else:
        print(f"  WINTER_TREE.md exists, skipped (not overwriting)")




def _handle_vault_command(args):
    """Dispatch lock / unlock / rekey to the Vault module.
    Auto-detects repo via _REPO_PATH or `.muninn/` in cwd."""
    global _REPO_PATH
    if not _REPO_PATH:
        cwd = Path(".").resolve()
        if (cwd / ".muninn").exists():
            _REPO_PATH = cwd
            _refresh_tree_paths()
    repo = _REPO_PATH or Path(".").resolve()
    try:
        from vault import Vault
    except ImportError:
        print("ERROR: vault module not found")
        sys.exit(1)

    v = Vault(repo)
    pw = args.password  # --password for scripts/CI, getpass for interactive
    if not pw:
        import getpass
        pw = getpass.getpass("Vault password: ")

    try:
        if args.command == "lock":
            if not v.is_initialized():
                v.init(pw)
                print("VAULT: initialized (salt + backup saved)")
            else:
                v.load_key(pw)
            result = v.lock()
            print(f"VAULT LOCKED: {result['encrypted']} files encrypted ({result['total_bytes']:,} bytes)")
        elif args.command == "unlock":
            if not v.is_initialized():
                print("ERROR: vault not initialized. Run: muninn lock --password <pw>")
                sys.exit(1)
            v.load_key(pw)
            result = v.unlock()
            print(f"VAULT UNLOCKED: {result['decrypted']} files decrypted ({result['total_bytes']:,} bytes)")
        elif args.command == "rekey":
            if not v.is_initialized():
                print("ERROR: vault not initialized.")
                sys.exit(1)
            v.load_key(pw)
            import getpass as _gp
            new_pw = args.file  # Can pass new password as positional arg
            if not new_pw:
                new_pw = _gp.getpass("New vault password: ")
            result = v.rekey(new_pw)
            print(f"VAULT REKEYED: {result['rekeyed']} files re-encrypted ({result['total_bytes']:,} bytes)")
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


# ── F1b (2026-05-09): huginn + quarantine command handlers ────

def _ensure_repo_from_cwd() -> None:
    """If _REPO_PATH is not set, auto-detect from cwd `.muninn/`.
    No-op if no `.muninn/` is found — caller falls back to Path(".")."""
    global _REPO_PATH
    if not _REPO_PATH:
        cwd = Path(".").resolve()
        if (cwd / ".muninn").exists():
            _REPO_PATH = cwd
            _refresh_tree_paths()


def _handle_huginn_trip(args) -> None:
    """Mycelium dream-pass: generates `max_dreams` semantic connections,
    measures entropy delta, persists if new connections were made."""
    _ensure_repo_from_cwd()
    repo = _REPO_PATH or Path(".")
    if _CORE_DIR not in sys.path:
        sys.path.insert(0, _CORE_DIR)
    from mycelium import Mycelium
    m = Mycelium(repo)
    intensity = 0.7 if args.force else 0.5
    result = m.trip(intensity=intensity, max_dreams=20)
    if result["created"] > 0:
        m.save()
    print("=== HUGINN TRIP (H1) ===")
    print(f"  Intensity: {intensity}")
    print(f"  Dream connections: {result['created']}")
    print(f"  Entropy: {result['entropy_before']:.4f} -> {result['entropy_after']:.4f} "
          f"(delta: {result.get('entropy_delta', 0):+.4f})")
    if result.get("reason"):
        print(f"  Note: {result['reason']}")
    for d in result["dreams"][:10]:
        zones = d.get('zones', [])
        if len(zones) >= 2:
            print(f"    {d['from']} <-> {d['to']} (zones: {zones[0][:20]}|{zones[1][:20]})")
        else:
            print(f"    {d['from']} <-> {d['to']}")
    if result["created"] > 10:
        print(f"    ... and {result['created'] - 10} more")


def _handle_huginn_think(args) -> None:
    """Surface stored insights ranked by mycelium relevance to `args.file`
    (used as the query). Empty result hint nudges to `prune` to seed dreams."""
    _ensure_repo_from_cwd()
    query = args.file or ""
    insights = huginn_think(query=query, top_n=10)
    print("=== HUGINN THINK (H3) ===")
    if not insights:
        print("  No insights yet. Run `muninn.py prune` to generate (dream runs during sleep).")
        return
    for ins in insights:
        print(f"  {ins['formatted']}")
    print(f"\n  {len(insights)} insight(s) total")



def _handle_quarantine_command() -> None:
    """Pretty-print ~/.muninn/quarantine.jsonl entries (cube SHA mismatches)."""
    quarantine_path = os.path.join(os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
    if not os.path.exists(quarantine_path):
        print("No quarantine entries found.")
        return
    import json as _json
    with open(quarantine_path, 'r', encoding='utf-8') as f:
        entries = [_json.loads(line) for line in f if line.strip()]
    if not entries:
        print("Quarantine file exists but is empty.")
        return
    print(f"=== Quarantine — {len(entries)} entries ===\n")
    for i, e in enumerate(entries, 1):
        date = e.get('date', '?')
        cube_id = e.get('cube_id', '?')
        forigin = e.get('file_origin', '?')
        ncd = e.get('ncd_score', '?')
        expected = e.get('expected_sha256', '?')[:12]
        found = e.get('found_sha256', '?')[:12]
        print(f"  [{i}] {date} | {forigin} | NCD={ncd}")
        print(f"      cube: {cube_id}")
        print(f"      hash: {expected}... -> {found}...")
        corrupted = e.get('corrupted_content', '')
        if corrupted:
            preview = corrupted[:120].replace('\n', '\\n')
            print(f"      corrupted: {preview}")
        print()


def _handle_zones_command(args) -> None:
    """H3.2 (2026-05-09): detect + label thematic zones in the mycelium
    (spectral Laplacian clustering, Newman-Girvan). Wires
    Mycelium.detect_zones + auto_label_zones + get_zones into a
    CLI-visible production path.
    """
    _ensure_repo_from_cwd()
    repo = _REPO_PATH or Path(".").resolve()
    if _CORE_DIR not in sys.path:
        sys.path.insert(0, _CORE_DIR)
    try:
        from mycelium import Mycelium
    except ImportError:
        from engine.core.mycelium import Mycelium
    m = Mycelium(repo)
    zones = m.detect_zones()
    if not zones:
        print("=== MYCELIUM ZONES ===")
        print("  No zones detected (need >= 10 connections + numpy/scipy/sklearn).")
        return
    # Side-effect: tag edges with their zone (auto_label_zones runs detect_zones
    # internally too but is idempotent on a populated mycelium).
    m.auto_label_zones()
    print(f"=== MYCELIUM ZONES — {len(zones)} detected ===\n")
    sorted_zones = sorted(zones.items(), key=lambda kv: -len(kv[1]))[:10]
    for i, (zone_name, members) in enumerate(sorted_zones, 1):
        print(f"  [{i}] {zone_name} ({len(members)} concepts)")
        for concept in list(members)[:5]:
            print(f"      - {concept}")


# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.9 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap", "feed", "verify",
        "ingest", "recall", "bridge", "upgrade-hooks", "install-cron", "inject", "diagnose", "doctor",
        "lock", "unlock", "rekey", "trip", "think", "quarantine", "scrub", "purge-secrets",
        "sync", "zones",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
    parser.add_argument("--history", action="store_true", help="Feed from all past transcripts")
    parser.add_argument("--watch", action="store_true", help="Poll-based feed: only process transcripts that grew since last check")
    parser.add_argument("--no-l9", action="store_true", help="Skip L9 (LLM API) — use only free layers")
    parser.add_argument("--trigger", choices=["hook", "stop"], default="hook",
                        help="Hook trigger type (hook=PreCompact/SessionEnd, stop=Stop)")
    parser.add_argument("--force", action="store_true", help="Force operation (e.g., prune without dry-run)")
    parser.add_argument("--output", help="Output path for scan neuron map JSON (CHUNK 9)")
    parser.add_argument("--password", help="Password for vault lock/unlock (AES-256)")
    parser.add_argument("--uninstall", action="store_true",
                        help="For install-cron: remove the systemd timer instead of installing")

    args = parser.parse_args()

    # Global flag to skip L9
    global _SKIP_L9
    _SKIP_L9 = getattr(args, 'no_l9', False)

    # Set repo path for local codebook loading
    if args.repo:
        _REPO_PATH = Path(args.repo).resolve()
        _refresh_tree_paths()

    # CHUNK E6 (2026-05-08): wire A3 check_integrity() at boot.
    # Pre-fix: A3 helper existed but was only called via `muninn doctor`.
    # If Sky never ran doctor, mycelium.db corruption stayed silent
    # until queries returned wrong data. Now every CLI command (except
    # init/doctor — see exemptions) runs a quick integrity check at
    # boot and warns stderr on failure.
    # Override with MUNINN_SKIP_INTEGRITY=1 if needed (e.g. tests on
    # garbage DBs).
    if (args.command not in ("init", "doctor")
            and os.environ.get("MUNINN_SKIP_INTEGRITY") != "1"):
        db_path = (_REPO_PATH or Path.cwd()) / ".muninn" / "mycelium.db"
        if db_path.exists():
            try:
                from mycelium_db import MyceliumDB
                _db = MyceliumDB(db_path)
                ok, msg = _db.check_integrity()
                if not ok:
                    print(f"WARNING: mycelium.db integrity_check failed: {msg}",
                          file=sys.stderr)
                    print("  Run `muninn doctor` for full diagnostic, or set "
                          "MUNINN_SKIP_INTEGRITY=1 to bypass.",
                          file=sys.stderr)
            except Exception as _ic_exc:
                # MyceliumDB() itself can crash on garbage DB
                # (sqlite3.DatabaseError "file is not a database").
                # That's still a corruption signal — surface it
                # instead of swallowing.
                print(f"WARNING: mycelium.db integrity_check failed: "
                      f"{type(_ic_exc).__name__}: {_ic_exc}",
                      file=sys.stderr)
                print("  Run `muninn doctor` for full diagnostic, or set "
                      "MUNINN_SKIP_INTEGRITY=1 to bypass.",
                      file=sys.stderr)

    if args.command == "init":
        # Full one-shot setup: tree + hooks + register
        # Works on any repo: cd /path/to/repo && muninn init
        # Or: muninn init --repo /path/to/repo
        repo = Path(args.repo or args.file or ".").resolve()
        if not repo.exists():
            print(f"ERROR: path does not exist: {repo}", file=sys.stderr)
            sys.exit(1)
        if not _REPO_PATH:
            _REPO_PATH = repo
            _refresh_tree_paths()
        # CRITICAL (2026-05-11 PM hotfix): propagate _REPO_PATH to the package
        # namespace so _m._REPO_PATH (used by _get_tree_dir/meta inside
        # muninn_tree.py and init_tree's guard) sees the same value. In pip-
        # install-e mode the package and the _engine module diverge — the
        # E2E test test_e2e_pip_install_from_scratch leaked into the source
        # repo because of this exact divergence. Belt-and-suspenders here:
        # set the local global, mirror to the package, refresh paths, and
        # compute tree_meta directly from `repo` (no globals at all).
        try:
            import muninn as _pkg
            _pkg._REPO_PATH = repo
        except Exception:
            pass
        _refresh_tree_paths()
        muninn_dir = repo / ".muninn"
        muninn_dir.mkdir(parents=True, exist_ok=True)
        tree_meta = repo / ".muninn" / "tree" / "tree.json"
        tree_dir = repo / ".muninn" / "tree"
        if not tree_meta.exists():
            init_tree()
        else:
            print(f"  Tree already exists: {tree_dir} (skipped)")
        install_hooks(repo)
        print(f"  Muninn ready: {repo}")
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

    if args.command == "doctor":
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        doctor()
        # --fix: auto-install missing formatters
        if getattr(args, 'fix', False) or (
                hasattr(args, 'file') and args.file == '--fix'):
            try:
                from cube import install_formatters
            except ImportError:
                from engine.core.cube import install_formatters
            repo = _REPO_PATH or Path(".").resolve()
            results = install_formatters(repo_path=str(repo), auto=True)
            for name, status in results.items():
                if status == 'installed':
                    print(f"  [INSTALLED] {name}")
                elif status == 'failed':
                    print(f"  [FAILED] {name}")
        return

    if args.command in ("lock", "unlock", "rekey"):
        _handle_vault_command(args)
        return

    if args.command == "trip":
        _handle_huginn_trip(args)
        return

    if args.command == "think":
        _handle_huginn_think(args)
        return

    if args.command == "scan":
        if not args.file:
            print("ERROR: repo path required. Usage: muninn.py scan <repo-path>")
            sys.exit(1)
        scan_repo(Path(args.file), output_path=getattr(args, 'output', None))
        return

    if args.command == "bootstrap":
        if not args.file:
            print("ERROR: repo path required. Usage: muninn.py bootstrap <repo-path>")
            sys.exit(1)
        _REPO_PATH = Path(args.file).resolve()
        if not _REPO_PATH.exists():
            print(f"ERROR: path does not exist: {_safe_path(_REPO_PATH)}", file=sys.stderr)
            sys.exit(1)
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

    if args.command == "install-cron":
        # Chunk MCP A.3: weekly systemd-user timer for `muninn prune`.
        repo = Path(args.repo or args.file or ".").resolve()
        if not (repo / ".muninn").exists():
            print(f"ERROR: {repo} is not a Muninn repo (no .muninn/ directory)")
            sys.exit(1)
        result = install_cron(repo, uninstall=args.uninstall)
        print(f"install-cron: {result['status']}")
        if result["status"] == "skipped_no_systemd":
            print("  systemctl not found on PATH. Cron fallback is not yet implemented.")
            print("  See docs/BATTLE_PLAN_MASTER_MCP.md for the planned A.3.bis chunk.")
        elif result["status"] == "installed":
            print(f"  service: {result['service_path']}")
            print(f"  timer:   {result['timer_path']}")
            print(f"  next:    {result.get('next_action', '')}")
        elif result["status"] == "uninstalled":
            print("  service + timer files removed.")
            print("  next: systemctl --user daemon-reload (then verify with `systemctl --user list-timers`)")
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
            # Chunk MCP A.2: guarded sync (timeout + opt-out + doctor marker)
            sync_result = _sync_to_meta_guarded(repo, hook_event="direct_file")
            if sync_result["status"] == "ok":
                print(f"MUNINN SYNC: {sync_result['pushed']} connections -> meta-mycelium")
            elif sync_result["status"] == "timeout":
                print(f"MUNINN SYNC: timeout after {sync_result['elapsed_s']}s",
                      file=sys.stderr)
            elif sync_result["status"] == "error":
                print(f"MUNINN SYNC warning: {sync_result['error']}", file=sys.stderr)
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
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        prune(dry_run=not args.force)
        return

    if args.command == "decode":
        if args.file:
            fpath = Path(args.file)
            if not fpath.exists():
                print(f"ERROR: file not found: {_safe_path(args.file)}", file=sys.stderr)
                sys.exit(1)
            text = fpath.read_text(encoding="utf-8")
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
            print(f"ERROR: {_safe_path(fp)} not found")
            sys.exit(1)
        verify_compression(fp)
        return

    if args.command == "scrub":
        _handle_scrub_command(args)
        return

    if args.command == "purge-secrets":
        _handle_purge_secrets_command(args)
        return

    if args.command == "sync":
        # I1: CLI sync commands — --status/--backend/--migrate/--export/--import
        if not _REPO_PATH:
            cwd = Path(".").resolve()
            if (cwd / ".muninn").exists():
                _REPO_PATH = cwd
                _refresh_tree_paths()
        if _CORE_DIR not in sys.path:
            sys.path.insert(0, _CORE_DIR)
        from sync_backend import get_sync_backend, save_sync_config, _load_sync_config
        sub = args.file or "status"  # Default sub-action

        if sub == "status":
            # I1: Show backend status
            try:
                backend = get_sync_backend()
                st = backend.status()
                print("=== MUNINN SYNC STATUS ===")
                for k, v in st.items():
                    print(f"  {k}: {v}")
            except Exception as e:
                print(f"Sync status error: {e}")
        elif sub.startswith("backend="):
            # I1: Switch backend — sync backend=git|shared_file|tls
            new_backend = sub.split("=", 1)[1]
            if new_backend not in ("shared_file", "git", "tls"):
                print(f"ERROR: unknown backend '{new_backend}'. Use: shared_file, git, tls")
                sys.exit(1)
            config = _load_sync_config()
            config["backend"] = new_backend
            save_sync_config(config)
            print(f"Backend switched to: {new_backend}")
        elif sub == "migrate":
            # I2: Migration — backend-to-backend
            from sync_backend import migrate_backend
            config = _load_sync_config()
            src_type = config.get("backend", "shared_file")
            # Migrate to the "other" backend
            target = "git" if src_type == "shared_file" else "shared_file"
            print(f"=== MUNINN SYNC MIGRATE: {src_type} -> {target} ===")
            result = migrate_backend(src_type, target, config)
            print(f"  Migrated: {result['edges']} edges, {result['fusions']} fusions")
            if result.get("verified"):
                print(f"  Verification: PASS")
            else:
                print(f"  Verification: SKIP (no verification possible)")
        elif sub == "export":
            # I5: Export meta to JSON
            from sync_backend import export_meta_json
            out_path = Path(args.repo) if args.repo else Path("muninn_export.json")
            result = export_meta_json(out_path)
            print(f"Exported: {result['edges']} edges, {result['fusions']} fusions -> {out_path}")
        elif sub == "import":
            # I5: Import meta from JSON
            if not args.repo:
                print("ERROR: usage: muninn sync import --repo <json-file>")
                sys.exit(1)
            from sync_backend import import_meta_json
            result = import_meta_json(Path(args.repo))
            print(f"Imported: {result['edges']} edges, {result['fusions']} fusions")
        elif sub == "verify-hooks":
            # I3: Verify hook integration
            from sync_backend import verify_hooks
            result = verify_hooks()
            print("=== MUNINN SYNC HOOK VERIFY ===")
            for site, status in result.items():
                mark = "[OK]" if status else "[FAIL]"
                print(f"  {mark} {site}")
        elif sub == "doctor":
            # I4: Sync health check
            from sync_backend import sync_doctor
            result = sync_doctor()
            print("=== MUNINN SYNC DOCTOR ===")
            for check, info in result.items():
                mark = "[OK]" if info.get("ok") else "[FAIL]"
                print(f"  {mark} {check}: {info.get('detail', '')}")
        else:
            print(f"ERROR: unknown sync subcommand '{sub}'")
            print("  Usage: muninn sync [status|backend=TYPE|migrate|export|import|verify-hooks|doctor]")
            sys.exit(1)
        return

    if args.command == "quarantine":
        _handle_quarantine_command()
        return

    if args.command == "zones":
        _handle_zones_command(args)
        return

    if not args.file:
        print("ERROR: file argument required")
        sys.exit(1)

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"ERROR: {_safe_path(filepath)} not found")
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
