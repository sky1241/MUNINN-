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

# Secret patterns — applied in compress_file and compress_transcript
# Tested against 24+ real secret formats. Zero false positives on natural text.
_SECRET_PATTERNS = [
    # --- Git/CI ---
    r'ghp_[A-Za-z0-9]{20,}',       # GitHub PAT classic
    r'github_pat_[A-Za-z0-9_]{20,}',  # GitHub fine-grained PAT
    r'gho_[A-Za-z0-9]{20,}',       # GitHub OAuth
    r'ghu_[A-Za-z0-9]{20,}',       # GitHub user-to-server
    r'ghs_[A-Za-z0-9]{20,}',       # GitHub server-to-server
    r'glpat-[A-Za-z0-9\-_]{20,}',  # GitLab PAT
    # --- Cloud providers ---
    r'AKIA[A-Z0-9]{16}',           # AWS access keys
    r'AIzaSy[A-Za-z0-9\-_]{33}',   # Google Cloud API keys
    r'DefaultEndpointsProtocol=[^\s]+',  # Azure storage connection string
    # --- AI/SaaS API keys ---
    r'sk-[A-Za-z0-9\-._]{20,}',    # Anthropic/OpenAI (sk-ant-*, sk-proj-*)
    r'sk_live_[A-Za-z0-9]{20,}',   # Stripe secret key
    r'pk_live_[A-Za-z0-9]{20,}',   # Stripe publishable key
    r'SG\.[A-Za-z0-9\-_.]{20,}',   # SendGrid
    r'SK[a-f0-9]{32}',             # Twilio
    r'HRKU-[a-f0-9\-]{36}',        # Heroku
    # --- Package registries ---
    r'npm_[A-Za-z0-9]{20,}',       # NPM token
    r'pypi-[A-Za-z0-9]{20,}',      # PyPI token
    # --- Chat/Social ---
    r'xox[bpsar]-[A-Za-z0-9\-]{10,}',  # Slack tokens
    r'[A-Za-z0-9]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}',  # Discord bot token
    # --- Database URIs (password embedded) ---
    r'(?:mongodb(?:\+srv)?|postgresql|mysql|redis|amqp)://[^\s]*:[^\s@]+@[^\s]+',  # DB connection strings
    # --- Generic ---
    r'-----BEGIN\s+\w*\s*PRIVATE KEY-----[\s\S]*?-----END',  # PEM private keys
    r'Bearer\s+[A-Za-z0-9\-._~+/]{20,}=*',  # X12: OAuth Bearer tokens (min 20 chars to avoid false positive prose)
    r'token[=:]\s*\S{20,}',        # Generic token= or token:
    r'password[=:]\s*\S+',         # Generic password= or password:
    r'secret[=:]\s*\S{10,}',       # Generic secret= or secret:
    r'api[_-]?key[=:]\s*\S{10,}',  # Generic api_key= or apikey:
    r'(?:cl[eé]|mdp|mot\s+de\s+passe|passwd|passphrase)[=:\s]+\S+',  # FR: clé/mdp/mot de passe
]

# P10: Compile secret patterns once at module load (not per-call)
_COMPILED_SECRET_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SECRET_PATTERNS]


# Legacy globals — recomputed by _refresh_tree_paths()
TREE_DIR = MUNINN_ROOT / "memory"
TREE_META = TREE_DIR / "tree.json"

# Ensure sub-modules can find us as 'muninn' even when run as __main__
sys.modules.setdefault('muninn', sys.modules[__name__])

# ── SUB-MODULE RE-EXPORTS ─────────────────────────────────────
# Sub-modules access shared globals via `import muninn as _m`.
# Import order matters: layers first (no deps), tree second, feed third.
from muninn_layers import *  # noqa: F401,F403
from muninn_tree import *    # noqa: F401,F403
from muninn_feed import *    # noqa: F401,F403


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
                    m.observe_text(_redact_secrets_text(text))
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
    print(f"  Repo registered: {repo_key}")


def _generate_bridge_hook(repo_path: Path, engine_core_dir: Path) -> Path:
    """Generate a bridge_hook.py in the target repo's .claude/hooks/ directory.

    The generated hook points to the correct engine/core path regardless of
    where the repo lives. Returns the path to the generated file.
    """
    hooks_dir = repo_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    bridge_path = hooks_dir / "bridge_hook.py"

    # Use forward slashes — Python handles them on all platforms
    engine_core_str = str(engine_core_dir).replace("\\", "/")

    bridge_code = f'''#!/usr/bin/env python3
"""P42 UserPromptSubmit hook — Live Mycelium Bridge + Secret Sentinel.

Reads user prompt from stdin (JSON), checks for accidental secrets,
then runs bridge_fast() for activated concepts.

Auto-generated by muninn install_hooks(). Do not edit manually.
Target: <0.5s total execution time.
"""
import json
import math
import re
import sys
import os
from pathlib import Path

def _shannon_entropy(s):
    """Shannon entropy of a string. High entropy = likely a secret."""
    if not s:
        return 0.0
    freq = {{}}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum((n / length) * math.log2(n / length) for n in freq.values())

def _has_char_diversity(s):
    """Check if string has mixed character classes (upper+lower+digit+special)."""
    classes = 0
    if re.search(r'[a-z]', s): classes += 1
    if re.search(r'[A-Z]', s): classes += 1
    if re.search(r'[0-9]', s): classes += 1
    if re.search(r'[^a-zA-Z0-9\\s]', s): classes += 1
    return classes >= 3

_SECRET_TRIGGERS = re.compile(
    r'(?:cl[eé]|key|password|mdp|mot de passe|passwd|secret|token|passphrase'
    r'|api.?key|credentials?|auth)',
    re.IGNORECASE
)

def _check_secrets(prompt):
    """Detect if user accidentally typed a password/key in their prompt.
    Returns warning string or None."""
    # 1. Check known API key patterns (structural)
    _API_PATTERNS = [
        r'ghp_[A-Za-z0-9]{{20,}}', r'sk-[A-Za-z0-9\\-._]{{20,}}',
        r'AKIA[A-Z0-9]{{16}}', r'Bearer\\s+[A-Za-z0-9\\-._~+/]+=*',
    ]
    for pat in _API_PATTERNS:
        if re.search(pat, prompt):
            return "[MUNINN SENTINEL] API key/token detected in your message. It will be stored in the Claude transcript. Consider rotating it."

    # 2. Check for password-like strings near trigger words
    if _SECRET_TRIGGERS.search(prompt):
        words = prompt.split()
        for word in words:
            clean = word.strip('.,;:!?\\'\\"/()[]{{}}')
            if len(clean) >= 6 and _has_char_diversity(clean) and _shannon_entropy(clean) > 2.8:
                return "[MUNINN SENTINEL] You may have typed a password or secret in your message. It will be recorded in the Claude transcript (.jsonl). Consider changing it. Muninn will redact it from .mn files but CANNOT erase it from the raw transcript."

    # 3. Standalone high-entropy check (no trigger needed) for very suspicious strings
    for word in prompt.split():
        clean = word.strip('.,;:!?\\'\\"/()[]{{}}')
        if len(clean) >= 10 and _has_char_diversity(clean) and _shannon_entropy(clean) > 3.5:
            return "[MUNINN SENTINEL] High-entropy string detected — possible password or key. It will be stored in the raw transcript."

    return None

def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError):
        sys.exit(0)

    prompt = hook_input.get("prompt", "")
    if not prompt or len(prompt) < 10:
        sys.exit(0)

    # Secret detection — runs FIRST, before anything else
    warning = _check_secrets(prompt)
    if warning:
        print(warning)
        sys.stdout.flush()

    repo_path = hook_input.get("cwd", os.getcwd())

    engine_core = "{engine_core_str}"
    if engine_core not in sys.path:
        sys.path.insert(0, engine_core)

    try:
        import muninn
        muninn._REPO_PATH = Path(repo_path).resolve()
        muninn._refresh_tree_paths()
        result = muninn.bridge_fast(prompt)
        if result:
            print(result)
    except Exception as e:
        print(f"[MUNINN BRIDGE ERROR] {{type(e).__name__}}: {{e}}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
'''
    bridge_path.write_text(bridge_code, encoding="utf-8")
    return bridge_path


def install_hooks(repo_path: Path):
    """Install Claude Code hooks for automatic feed on PreCompact/SessionEnd/Stop/UserPromptSubmit.

    P32: Merges hook-by-hook instead of skipping when hooks key exists.
    P43: Also installs UserPromptSubmit bridge hook (generates bridge_hook.py).
    Also registers repo in ~/.muninn/repos.json for P20c cross-repo discovery.
    """
    repo_path = repo_path.resolve()
    muninn_engine = Path(__file__).resolve()
    engine_core_dir = muninn_engine.parent
    claude_dir = repo_path / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    # Generate bridge_hook.py in target repo with correct engine path
    bridge_path = _generate_bridge_hook(repo_path, engine_core_dir)

    feed_cmd = f'python "{muninn_engine}" feed --repo "{repo_path}"'
    stop_cmd = f'python "{muninn_engine}" feed --repo "{repo_path}" --trigger stop'
    bridge_cmd = f'python "{bridge_path}"'
    required_hooks = {
        "UserPromptSubmit": [{"type": "command", "command": bridge_cmd, "timeout": 5}],
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
            # Check if existing hook points to a stale muninn.py or bridge path
            existing_cmds = [e.get("command", "") for e in existing_hooks[hook_name]]
            new_cmd = hook_entries[0]["command"]
            if any("muninn" in c.lower() for c in existing_cmds) and new_cmd not in existing_cmds:
                existing_hooks[hook_name] = hook_entries
                installed.append(f"{hook_name}(updated)")

    if not installed:
        print(f"  Hooks already up-to-date (UserPromptSubmit + PreCompact + SessionEnd + Stop)")
    else:
        existing["hooks"] = existing_hooks
        # X15: Atomic write — tempfile + replace to prevent corruption
        import tempfile as _tmpmod
        tmp_fd, tmp_path = _tmpmod.mkstemp(dir=str(settings_path.parent), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(settings_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        print(f"  Hooks installed: {' + '.join(installed)}")

    # Register repo in ~/.muninn/repos.json for P20c cross-repo discovery
    _register_repo(repo_path)


# ── SCRUB — universal secret redaction ────────────────────────────

_SCRUB_EXTENSIONS = {
    ".jsonl", ".json", ".md", ".mn", ".txt", ".log", ".csv",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".conf",
    ".py", ".js", ".ts", ".sh", ".bash", ".zsh", ".ps1",
}

# Trigger-word patterns: "clé xxx", "password xxx", etc. — redact the VALUE not the keyword
_TRIGGER_VALUE_PATTERNS = [
    re.compile(
        r'((?:cl[eé]|key|password|mdp|mot\s+de\s+passe|passwd|secret|token|passphrase'
        r'|api[_\-]?key|credentials?)\s*[=:\s]\s*)(\S+)',
        re.IGNORECASE
    ),
]


def scrub_secrets(target_path: Path, dry_run: bool = False) -> dict:
    """Scan files under target_path and redact secrets in-place.

    Works on any text file — JSONL, JSON, Markdown, logs, code, etc.
    Returns stats: {files_scanned, files_modified, secrets_found, errors}.
    """
    target = Path(target_path).resolve()
    stats = {"files_scanned": 0, "files_modified": 0, "secrets_found": 0, "errors": []}

    # Files that MUST NOT be scrubbed (auth, config, lock files)
    _SKIP_FILES = {
        ".credentials.json", "credentials.json", "settings.json",
        "settings.local.json", "config.json", ".env",
    }

    if target.is_file():
        if target.name in _SKIP_FILES:
            print(f"  SKIPPED (protected): {_safe_path(target)}")
            return stats
        files = [target]
    elif target.is_dir():
        files = []
        for root, _dirs, fnames in os.walk(target):
            # Skip .git, node_modules, __pycache__, .venv
            rp = Path(root)
            if any(p in rp.parts for p in (".git", "node_modules", "__pycache__", ".venv", "venv")):
                continue
            for fn in fnames:
                if fn in _SKIP_FILES:
                    continue
                fp = rp / fn
                if fp.suffix.lower() in _SCRUB_EXTENSIONS:
                    files.append(fp)
    else:
        stats["errors"].append(f"Path not found: {target}")
        return stats

    for fp in files:
        stats["files_scanned"] += 1
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            stats["errors"].append(f"{_safe_path(fp)}: {e}")
            continue

        modified = text
        file_hits = 0

        # 1. P10: Structural patterns (compiled) — redact entire match
        for cpat in _COMPILED_SECRET_PATTERNS:
            new, count = cpat.subn("[REDACTED]", modified)
            file_hits += count
            modified = new

        # 2. Trigger-word patterns — redact only the VALUE after the keyword
        for pat in _TRIGGER_VALUE_PATTERNS:
            def _redact_value(m):
                return m.group(1) + "[REDACTED]"
            new, count = pat.subn(_redact_value, modified)
            file_hits += count
            modified = new

        if file_hits > 0:
            stats["secrets_found"] += file_hits
            stats["files_modified"] += 1
            if not dry_run:
                fp.write_text(modified, encoding="utf-8")
            print(f"  {'[DRY-RUN] ' if dry_run else ''}SCRUBBED {_safe_path(fp)}: {file_hits} secret(s) redacted")

    return stats


# ── X1b: Purge secrets from mycelium databases ──────────────────

def purge_secrets_db(repo_path: Path = None):
    """X1b: Scan mycelium.db + meta_mycelium.db for secret concepts and delete them.

    Removes any concept whose name matches a secret pattern, along with
    all its edges, fusions, and edge_zones.
    """
    from mycelium_db import MyceliumDB

    total = 0

    # 1. Local mycelium.db
    local_db = (repo_path or Path(".")) / ".muninn" / "mycelium.db"
    if local_db.exists():
        db = MyceliumDB(local_db)
        n = db.purge_secret_concepts()
        total += n
        db.close()
        if n:
            print(f"  Purged {n} secret concept(s) from {local_db}")
        else:
            print(f"  No secrets found in {local_db}")

    # 2. Meta mycelium (cross-repo)
    meta_db = Path.home() / ".muninn" / "meta_mycelium.db"
    # Check config for custom meta_path
    config_path = Path.home() / ".muninn" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            mp = cfg.get("meta_path")
            if mp:
                meta_db = Path(mp) / "meta_mycelium.db"
        except Exception:
            pass

    if meta_db.exists():
        db = MyceliumDB(meta_db)
        n = db.purge_secret_concepts()
        total += n
        db.close()
        if n:
            print(f"  Purged {n} secret concept(s) from {meta_db}")
        else:
            print(f"  No secrets found in {meta_db}")

    print(f"\n  Total purged: {total} concept(s)")
    return total
# ── MAIN ──────────────────────────────────────────────────────────

def main():
    global _REPO_PATH

    parser = argparse.ArgumentParser(description="Muninn v0.9 — Universal memory compression")
    parser.add_argument("command", choices=[
        "read", "compress", "tree", "status", "init",
        "boot", "decode", "prune", "scan", "bootstrap", "feed", "verify",
        "ingest", "recall", "bridge", "upgrade-hooks", "inject", "diagnose", "doctor",
        "lock", "unlock", "rekey", "trip", "think", "quarantine", "scrub", "purge-secrets",
        "sync",
    ])
    parser.add_argument("file", nargs="?", help="Input file, repo path, or query")
    parser.add_argument("--repo", help="Target repo path (for local codebook)")
    parser.add_argument("--history", action="store_true", help="Feed from all past transcripts")
    parser.add_argument("--watch", action="store_true", help="Poll-based feed: only process transcripts that grew since last check")
    parser.add_argument("--no-l9", action="store_true", help="Skip L9 (LLM API) — use only free layers")
    parser.add_argument("--trigger", choices=["hook", "stop"], default="hook",
                        help="Hook trigger type (hook=PreCompact/SessionEnd, stop=Stop)")
    parser.add_argument("--force", action="store_true", help="Force operation (e.g., prune without dry-run)")
    parser.add_argument("--password", help="Password for vault lock/unlock (AES-256)")

    args = parser.parse_args()

    # Global flag to skip L9
    global _SKIP_L9
    _SKIP_L9 = getattr(args, 'no_l9', False)

    # Set repo path for local codebook loading
    if args.repo:
        _REPO_PATH = Path(args.repo).resolve()
        _refresh_tree_paths()

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
        muninn_dir = repo / ".muninn"
        muninn_dir.mkdir(parents=True, exist_ok=True)
        # Only init tree if it doesn't exist yet (protect existing branches)
        if not TREE_META.exists():
            init_tree()
        else:
            print(f"  Tree already exists: {TREE_DIR} (skipped)")
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
        return

    if args.command in ("lock", "unlock", "rekey"):
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
                    print(f"VAULT: initialized (salt + backup saved)")
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
            zones = d.get('zones', [])
            if len(zones) >= 2:
                print(f"    {d['from']} <-> {d['to']} (zones: {zones[0][:20]}|{zones[1][:20]})")
            else:
                print(f"    {d['from']} <-> {d['to']}")
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
        target = Path(args.file or ".").resolve()
        if not target.exists():
            print(f"ERROR: path not found: {target}", file=sys.stderr)
            sys.exit(1)
        dry = not args.force
        if dry:
            print("=== MUNINN SCRUB (dry-run) — use --force to apply ===")
        else:
            print("=== MUNINN SCRUB ===")
        stats = scrub_secrets(target, dry_run=dry)
        print(f"\n  Scanned: {stats['files_scanned']} files")
        print(f"  Modified: {stats['files_modified']} files")
        print(f"  Secrets found: {stats['secrets_found']}")
        if stats["errors"]:
            print(f"  Errors: {len(stats['errors'])}")
            for e in stats["errors"][:5]:
                print(f"    {e}")
        if dry and stats["secrets_found"] > 0:
            print(f"\n  Run with --force to redact {stats['secrets_found']} secret(s)")
        return

    if args.command == "purge-secrets":
        repo = Path(args.file or ".").resolve()
        print("=== MUNINN PURGE-SECRETS — cleaning mycelium databases ===")
        purge_secrets_db(repo)
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
        quarantine_path = os.path.join(os.path.expanduser('~'), '.muninn', 'quarantine.jsonl')
        if not os.path.exists(quarantine_path):
            print("No quarantine entries found.")
        else:
            import json as _json
            with open(quarantine_path, 'r', encoding='utf-8') as f:
                entries = [_json.loads(line) for line in f if line.strip()]
            if not entries:
                print("Quarantine file exists but is empty.")
            else:
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
