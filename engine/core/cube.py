#!/usr/bin/env python3
"""
Cube Muninn — Code resilience through atomic destruction/reconstruction.

The cube is the mycelium subdividing and testing its own knowledge.
Scan → subdivide → destroy → reconstruct → validate → learn.

Briques B1-B8, B11-B19: Scanner, Tokenizer, Dataclass, Subdivision, SHA-256,
Storage, AST, Neighbors, LLM Providers, FIM, Reconstruction, Validation,
Scoring, NCD, Temperature, Kaplan-Meier, Danger Theory, God's Number,
Levels, Feed Mycelium, Hebbian, Git Blame, Scheduling, Security, Hooks, CLI,
Laplacian RG, Cheeger, BP, Survey Propagation, Tononi Degeneracy.
"""

import ast as ast_module
import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from engine.core.tokenizer import count_tokens, token_count

# ─── B1: Scanner de repo ──────────────────────────────────────────────

# Extensions considered binary (skip)
BINARY_EXTENSIONS = frozenset({
    '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.o', '.a', '.lib',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.flac', '.ogg',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.db', '.sqlite', '.sqlite3',
    '.class', '.jar', '.war',
    '.DS_Store', '.coverage',
})

# Directories to always skip
SKIP_DIRS = frozenset({
    '.git', '.svn', '.hg', '.bzr',
    'node_modules', 'vendor', 'vendors',
    '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    '.tox', '.nox', '.venv', 'venv', 'env',
    'dist', 'build', '.eggs', '*.egg-info',
    '.muninn', '.claude',
    'coverage', 'htmlcov',
})

# Extension → language mapping
LANG_MAP = {
    '.py': 'python', '.pyx': 'python', '.pyi': 'python',
    '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.c': 'c', '.h': 'c',
    '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp',
    '.cs': 'csharp',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin', '.kts': 'kotlin',
    '.scala': 'scala',
    '.r': 'r', '.R': 'r',
    '.lua': 'lua',
    '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell',
    '.sql': 'sql',
    '.html': 'html', '.htm': 'html',
    '.css': 'css', '.scss': 'css', '.sass': 'css', '.less': 'css',
    '.json': 'json',
    '.yaml': 'yaml', '.yml': 'yaml',
    '.toml': 'toml',
    '.xml': 'xml',
    '.md': 'markdown',
    '.tex': 'latex',
    '.el': 'elisp',
    '.clj': 'clojure', '.cljs': 'clojure',
    '.ex': 'elixir', '.exs': 'elixir',
    '.erl': 'erlang',
    '.hs': 'haskell',
    '.ml': 'ocaml', '.mli': 'ocaml',
    '.vue': 'vue',
    '.svelte': 'svelte',
    '.dart': 'dart',
    '.zig': 'zig',
    '.nim': 'nim',
    '.v': 'v',
    '.sol': 'solidity',
    '.proto': 'protobuf',
    '.graphql': 'graphql', '.gql': 'graphql',
    '.tf': 'terraform',
    '.dockerfile': 'dockerfile',
}

# Max file size to read (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@dataclass
class ScannedFile:
    """Result of scanning a single file."""
    path: str
    content: str
    language: str
    token_count: int = 0

    def __post_init__(self):
        if self.token_count == 0 and self.content:
            self.token_count = token_count(self.content)


def _should_skip_dir(name: str) -> bool:
    """Check if directory should be skipped."""
    if name in SKIP_DIRS:
        return True
    if name.endswith('.egg-info'):
        return True
    return False


def _detect_language(path: Path) -> Optional[str]:
    """Detect language from file extension."""
    ext = path.suffix.lower()
    if ext in LANG_MAP:
        return LANG_MAP[ext]
    # Special filenames
    name = path.name.lower()
    if name in ('dockerfile', 'containerfile'):
        return 'dockerfile'
    if name in ('makefile', 'gnumakefile'):
        return 'makefile'
    if name in ('cmakelists.txt',):
        return 'cmake'
    if name in ('gemfile', 'rakefile'):
        return 'ruby'
    return None


def _is_binary(path: Path) -> bool:
    """Check if file is binary by extension or content sniff."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    # Sniff first 8KB for null bytes
    try:
        with open(path, 'rb') as f:
            chunk = f.read(8192)
            if b'\x00' in chunk:
                return True
    except (OSError, PermissionError):
        return True
    return False


def scan_repo(repo_path: str, extensions: Optional[set] = None,
              max_file_size: int = MAX_FILE_SIZE) -> list[ScannedFile]:
    """
    B1: Scan a repository for source files.

    Args:
        repo_path: Path to the repository root.
        extensions: Optional set of extensions to include (e.g. {'.py', '.js'}).
                    None = all recognized source files.
        max_file_size: Maximum file size in bytes (default 10MB).

    Returns:
        List of ScannedFile(path, content, language, token_count).
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo_path}")

    results = []

    for root, dirs, files in os.walk(repo):
        # Filter directories in-place (prune early)
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

        for fname in sorted(files):
            fpath = Path(root) / fname

            # Skip binary files
            if _is_binary(fpath):
                continue

            # Extension filter
            if extensions and fpath.suffix.lower() not in extensions:
                continue

            # Language detection
            lang = _detect_language(fpath)
            if lang is None and extensions is None:
                continue  # Unknown file type, skip unless explicitly requested

            # Size check
            try:
                size = fpath.stat().st_size
                if size > max_file_size or size == 0:
                    continue
            except OSError:
                continue

            # Read content
            try:
                content = fpath.read_text(encoding='utf-8', errors='replace')
            except (OSError, PermissionError):
                continue

            rel_path = str(fpath.relative_to(repo)).replace('\\', '/')
            results.append(ScannedFile(
                path=rel_path,
                content=content,
                language=lang or 'unknown',
            ))

    return results


# ─── B3: Cube dataclass ───────────────────────────────────────────────

@dataclass
class Cube:
    """
    B3: Atomic unit of code for destruction/reconstruction testing.

    Each cube holds ~88 tokens of code and knows its neighbors.
    """
    id: str                          # Unique ID (e.g. "file.py:L10-L25:level1")
    content: str                     # The actual code
    sha256: str                      # SHA-256 of normalized content
    file_origin: str                 # Source file path (relative)
    line_start: int                  # First line in source
    line_end: int                    # Last line in source
    level: int = 0                   # 0=atomic(88tok), 1=704tok, 2=5632tok...
    neighbors: list[str] = field(default_factory=list)  # Neighbor cube IDs
    score: float = 0.0              # Hotness score (perplexity-based)
    temperature: float = 0.0        # Temperature (aggregated)
    token_count: int = 0            # Token count

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Cube':
        """Deserialize from dict."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> 'Cube':
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(s))


# ─── B5: SHA-256 normalisation + hashing ──────────────────────────────

def normalize_content(text: str) -> str:
    """
    B5: Normalize code content for consistent hashing.

    - Strip trailing whitespace per line
    - Normalize newlines to \n
    - Strip leading/trailing blank lines
    - Collapse multiple blank lines to single
    """
    # Normalize newlines
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    # Strip leading/trailing blank lines
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    # Collapse multiple blank lines to single
    result = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                result.append(line)
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    return '\n'.join(result)


def sha256_hash(text: str) -> str:
    """B5: SHA-256 hash of normalized content."""
    normalized = normalize_content(text)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


# ─── B4: Subdivision engine ───────────────────────────────────────────

TARGET_TOKENS = 88       # Atomic cube size
TOLERANCE_MIN = 72       # Accept cubes >= this (avoid tiny scraps)
TOLERANCE_MAX = 104      # Accept cubes <= this (avoid splitting mid-statement)


def _find_split_point(lines: list[str], target_line: int) -> int:
    """
    Find best split point near target_line respecting semantic boundaries.
    Prefers: blank lines > class/function defs > end of block.
    """
    search_range = max(3, len(lines) // 16)
    best = target_line
    best_score = 0

    for offset in range(-search_range, search_range + 1):
        idx = target_line + offset
        if idx <= 0 or idx >= len(lines):
            continue

        line = lines[idx].strip() if idx < len(lines) else ''
        prev_line = lines[idx - 1].strip() if idx > 0 else ''

        score = 0
        # Blank line = excellent split point
        if not prev_line:
            score = 10
        # After class/function def
        elif prev_line.startswith(('class ', 'def ', 'async def ')):
            score = 1  # Bad — don't split right after a def
        elif line.startswith(('class ', 'def ', 'async def ')):
            score = 9  # Good — split right before a new def
        # After closing brace/bracket
        elif prev_line in ('}', ']', ')'):
            score = 8
        # After return/break/continue
        elif prev_line.startswith(('return ', 'return', 'break', 'continue')):
            score = 7
        # Dedent (less indentation)
        elif idx > 0 and idx < len(lines):
            curr_indent = len(lines[idx]) - len(lines[idx].lstrip()) if lines[idx].strip() else 0
            prev_indent = len(lines[idx-1]) - len(lines[idx-1].lstrip()) if lines[idx-1].strip() else 0
            if curr_indent < prev_indent:
                score = 6

        # Penalize distance from target
        distance_penalty = abs(offset) * 0.5
        score -= distance_penalty

        if score > best_score:
            best_score = score
            best = idx

    return best


def subdivide_file(file_path: str, content: str, target_tokens: int = TARGET_TOKENS,
                   level: int = 0) -> list[Cube]:
    """
    B4: Subdivide a file's content into atomic cubes of ~target_tokens each.

    Respects semantic boundaries (function defs, blank lines, blocks).
    Returns list of Cube objects.
    """
    if not content.strip():
        return []
    lines = content.split('\n')

    total_tokens = token_count(content)
    if total_tokens <= TOLERANCE_MAX:
        # Small enough — single cube
        cube = Cube(
            id=f"{file_path}:L1-L{len(lines)}:lv{level}",
            content=content,
            sha256=sha256_hash(content),
            file_origin=file_path,
            line_start=1,
            line_end=len(lines),
            level=level,
            token_count=total_tokens,
        )
        return [cube]

    # Estimate number of cubes needed
    n_cubes = max(2, round(total_tokens / target_tokens))

    # Build line→token mapping for accurate splitting
    line_tokens = []
    for line in lines:
        lt = token_count(line + '\n')
        line_tokens.append(lt)

    total_line_tokens = sum(line_tokens)
    tokens_per_cube = total_line_tokens / n_cubes

    # Find split points
    cubes = []
    start_line = 0
    running_tokens = 0

    for i, lt in enumerate(line_tokens):
        running_tokens += lt

        is_last = (i == len(line_tokens) - 1)
        should_split = running_tokens >= tokens_per_cube and not is_last

        if should_split or is_last:
            end_line = i + 1 if is_last else _find_split_point(lines, i + 1)
            if end_line <= start_line:
                end_line = i + 1

            chunk_lines = lines[start_line:end_line]
            chunk_content = '\n'.join(chunk_lines)

            if chunk_content.strip():  # Skip empty chunks
                cube = Cube(
                    id=f"{file_path}:L{start_line+1}-L{end_line}:lv{level}",
                    content=chunk_content,
                    sha256=sha256_hash(chunk_content),
                    file_origin=file_path,
                    line_start=start_line + 1,
                    line_end=end_line,
                    level=level,
                    token_count=token_count(chunk_content),
                )
                cubes.append(cube)

            start_line = end_line
            running_tokens = 0

    return cubes


def subdivide_recursive(file_path: str, content: str,
                        target_tokens: int = TARGET_TOKENS,
                        max_levels: int = 5) -> list[Cube]:
    """
    B4: Recursive subdivision /8 until atomic cubes of ~88 tokens.

    Each level divides by ~8. Stops when cubes are within tolerance.
    """
    total = token_count(content)
    if total <= TOLERANCE_MAX:
        return subdivide_file(file_path, content, target_tokens, level=0)

    # Calculate appropriate level
    # level 0 = 88 tokens, level 1 = 704, level 2 = 5632, etc.
    level = 0
    size = total
    while size > TOLERANCE_MAX and level < max_levels:
        size = size // 8
        level += 1

    # Direct subdivision to atomic level
    return subdivide_file(file_path, content, target_tokens, level=0)


# ─── B6: Stockage index SQLite ────────────────────────────────────────

CUBE_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS cubes (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    content TEXT NOT NULL,
    file_origin TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    level INTEGER DEFAULT 0,
    score REAL DEFAULT 0.0,
    temperature REAL DEFAULT 0.0,
    token_count INTEGER DEFAULT 0
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS neighbors (
    cube_id TEXT NOT NULL,
    neighbor_id TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    type TEXT DEFAULT 'static',
    PRIMARY KEY (cube_id, neighbor_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cube_id TEXT NOT NULL,
    cycle_num INTEGER NOT NULL,
    success INTEGER NOT NULL,
    reconstruction TEXT,
    perplexity REAL,
    timestamp REAL
);

CREATE INDEX IF NOT EXISTS idx_cubes_file ON cubes(file_origin);
CREATE INDEX IF NOT EXISTS idx_cubes_level ON cubes(level);
CREATE INDEX IF NOT EXISTS idx_cubes_temp ON cubes(temperature);
CREATE INDEX IF NOT EXISTS idx_cycles_cube ON cycles(cube_id);
CREATE INDEX IF NOT EXISTS idx_neighbors_neighbor ON neighbors(neighbor_id);
"""


class CubeStore:
    """B6: SQLite storage for cube index."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(CUBE_DB_SCHEMA)
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Cube CRUD ──

    def save_cube(self, cube: Cube):
        """Insert or replace a cube."""
        self.conn.execute(
            "INSERT OR REPLACE INTO cubes "
            "(id, sha256, content, file_origin, line_start, line_end, level, score, temperature, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cube.id, cube.sha256, cube.content, cube.file_origin,
             cube.line_start, cube.line_end, cube.level,
             cube.score, cube.temperature, cube.token_count)
        )
        self.conn.commit()

    def save_cubes(self, cubes: list[Cube]):
        """Batch insert cubes."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO cubes "
            "(id, sha256, content, file_origin, line_start, line_end, level, score, temperature, token_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(c.id, c.sha256, c.content, c.file_origin, c.line_start, c.line_end,
              c.level, c.score, c.temperature, c.token_count) for c in cubes]
        )
        self.conn.commit()

    def get_cube(self, cube_id: str) -> Optional[Cube]:
        """Get a cube by ID."""
        row = self.conn.execute(
            "SELECT id, sha256, content, file_origin, line_start, line_end, "
            "level, score, temperature, token_count FROM cubes WHERE id = ?",
            (cube_id,)
        ).fetchone()
        if not row:
            return None
        return Cube(
            id=row[0], sha256=row[1], content=row[2], file_origin=row[3],
            line_start=row[4], line_end=row[5], level=row[6],
            score=row[7], temperature=row[8], token_count=row[9],
        )

    def get_cubes_by_file(self, file_path: str) -> list[Cube]:
        """Get all cubes for a file."""
        rows = self.conn.execute(
            "SELECT id, sha256, content, file_origin, line_start, line_end, "
            "level, score, temperature, token_count FROM cubes WHERE file_origin = ? "
            "ORDER BY line_start",
            (file_path,)
        ).fetchall()
        return [Cube(id=r[0], sha256=r[1], content=r[2], file_origin=r[3],
                      line_start=r[4], line_end=r[5], level=r[6],
                      score=r[7], temperature=r[8], token_count=r[9]) for r in rows]

    def get_cubes_by_level(self, level: int) -> list[Cube]:
        """Get all cubes at a given level."""
        rows = self.conn.execute(
            "SELECT id, sha256, content, file_origin, line_start, line_end, "
            "level, score, temperature, token_count FROM cubes WHERE level = ?",
            (level,)
        ).fetchall()
        return [Cube(id=r[0], sha256=r[1], content=r[2], file_origin=r[3],
                      line_start=r[4], line_end=r[5], level=r[6],
                      score=r[7], temperature=r[8], token_count=r[9]) for r in rows]

    def get_hot_cubes(self, threshold: float = 0.5) -> list[Cube]:
        """Get cubes above temperature threshold."""
        rows = self.conn.execute(
            "SELECT id, sha256, content, file_origin, line_start, line_end, "
            "level, score, temperature, token_count FROM cubes WHERE temperature > ? "
            "ORDER BY temperature DESC",
            (threshold,)
        ).fetchall()
        return [Cube(id=r[0], sha256=r[1], content=r[2], file_origin=r[3],
                      line_start=r[4], line_end=r[5], level=r[6],
                      score=r[7], temperature=r[8], token_count=r[9]) for r in rows]

    def count_cubes(self, level: Optional[int] = None) -> int:
        """Count cubes, optionally filtered by level."""
        if level is not None:
            return self.conn.execute(
                "SELECT COUNT(*) FROM cubes WHERE level = ?", (level,)
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM cubes").fetchone()[0]

    def delete_cube(self, cube_id: str):
        """Delete a cube and its neighbors/cycles."""
        self.conn.execute("DELETE FROM cubes WHERE id = ?", (cube_id,))
        self.conn.execute("DELETE FROM neighbors WHERE cube_id = ? OR neighbor_id = ?",
                          (cube_id, cube_id))
        self.conn.execute("DELETE FROM cycles WHERE cube_id = ?", (cube_id,))
        self.conn.commit()

    # ── Neighbors ──

    def set_neighbor(self, cube_id: str, neighbor_id: str,
                     weight: float = 1.0, ntype: str = 'static'):
        """Set a neighbor relationship."""
        self.conn.execute(
            "INSERT OR REPLACE INTO neighbors (cube_id, neighbor_id, weight, type) "
            "VALUES (?, ?, ?, ?)",
            (cube_id, neighbor_id, weight, ntype)
        )
        self.conn.commit()

    def get_neighbors(self, cube_id: str) -> list[tuple[str, float, str]]:
        """Get neighbors of a cube. Returns [(neighbor_id, weight, type)]."""
        return self.conn.execute(
            "SELECT neighbor_id, weight, type FROM neighbors WHERE cube_id = ? "
            "ORDER BY weight DESC",
            (cube_id,)
        ).fetchall()

    # ── Cycles ──

    def record_cycle(self, cube_id: str, cycle_num: int, success: bool,
                     reconstruction: str = '', perplexity: float = 0.0):
        """Record a reconstruction cycle result."""
        import time
        self.conn.execute(
            "INSERT INTO cycles (cube_id, cycle_num, success, reconstruction, perplexity, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cube_id, cycle_num, int(success), reconstruction, perplexity, time.time())
        )
        self.conn.commit()

    def get_cycles(self, cube_id: str) -> list[dict]:
        """Get cycle history for a cube."""
        rows = self.conn.execute(
            "SELECT cycle_num, success, reconstruction, perplexity, timestamp "
            "FROM cycles WHERE cube_id = ? ORDER BY cycle_num",
            (cube_id,)
        ).fetchall()
        return [{'cycle': r[0], 'success': bool(r[1]), 'reconstruction': r[2],
                 'perplexity': r[3], 'timestamp': r[4]} for r in rows]

    def update_temperature(self, cube_id: str, temperature: float):
        """Update a cube's temperature."""
        self.conn.execute(
            "UPDATE cubes SET temperature = ? WHERE id = ?",
            (temperature, cube_id)
        )
        self.conn.commit()

    def update_score(self, cube_id: str, score: float):
        """Update a cube's hotness score."""
        self.conn.execute(
            "UPDATE cubes SET score = ? WHERE id = ?",
            (score, cube_id)
        )
        self.conn.commit()


# ─── B7: AST parser multi-langage ────────────────────────────────────

@dataclass
class Dependency:
    """A dependency between two files."""
    source: str      # File that depends
    target: str      # File it depends on
    dep_type: str    # 'import', 'call', 'ref'
    name: str        # The imported/called name


def _parse_python_deps(file_path: str, content: str,
                       all_files: set[str]) -> list[Dependency]:
    """Parse Python file for imports, function calls, class references."""
    deps = []
    try:
        tree = ast_module.parse(content, filename=file_path)
    except SyntaxError:
        return deps

    # Build module→file mapping from all_files
    module_to_file = {}
    for f in all_files:
        if f.endswith('.py'):
            # "src/utils.py" → "src.utils", "utils"
            mod = f[:-3].replace('/', '.').replace('\\', '.')
            module_to_file[mod] = f
            # Also map short name (last component)
            short = mod.split('.')[-1]
            if short not in module_to_file:
                module_to_file[short] = f

    for node in ast_module.walk(tree):
        if isinstance(node, ast_module.Import):
            for alias in node.names:
                mod_name = alias.name
                # Check direct match or prefix match
                target = module_to_file.get(mod_name)
                if not target:
                    # Try short name
                    short = mod_name.split('.')[-1]
                    target = module_to_file.get(short)
                if target and target != file_path:
                    deps.append(Dependency(file_path, target, 'import', mod_name))

        elif isinstance(node, ast_module.ImportFrom):
            if node.module:
                mod_name = node.module
                target = module_to_file.get(mod_name)
                if not target:
                    short = mod_name.split('.')[-1]
                    target = module_to_file.get(short)
                if target and target != file_path:
                    for alias in (node.names or []):
                        deps.append(Dependency(file_path, target, 'import',
                                               f"{mod_name}.{alias.name}"))

    return deps


# Regex patterns for JS/TS/Go/Java imports
_JS_IMPORT_RE = re.compile(
    r'''(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))''')
_GO_IMPORT_RE = re.compile(r'"([^"]+)"')
_JAVA_IMPORT_RE = re.compile(r'import\s+([\w.]+);')


def _parse_regex_deps(file_path: str, content: str, language: str,
                      all_files: set[str]) -> list[Dependency]:
    """Parse imports for JS/TS/Go/Java using regex."""
    deps = []

    if language in ('javascript', 'typescript', 'vue', 'svelte'):
        for m in _JS_IMPORT_RE.finditer(content):
            target_ref = m.group(1) or m.group(2)
            if target_ref.startswith('.'):
                # Relative import — try to resolve
                base_dir = os.path.dirname(file_path)
                candidate = os.path.normpath(os.path.join(base_dir, target_ref)).replace('\\', '/')
                # Try with extensions
                for ext in ('', '.js', '.ts', '.tsx', '.jsx', '/index.js', '/index.ts'):
                    full = candidate + ext
                    if full in all_files:
                        deps.append(Dependency(file_path, full, 'import', target_ref))
                        break

    elif language == 'go':
        for m in _GO_IMPORT_RE.finditer(content):
            pkg = m.group(1)
            # Go imports are package paths — match last component to dirs
            short = pkg.split('/')[-1]
            for f in all_files:
                if f.endswith('.go') and short in f:
                    if f != file_path:
                        deps.append(Dependency(file_path, f, 'import', pkg))

    elif language in ('java', 'kotlin', 'scala'):
        for m in _JAVA_IMPORT_RE.finditer(content):
            fqn = m.group(1)
            short = fqn.split('.')[-1]
            for f in all_files:
                if short in os.path.basename(f).split('.')[0]:
                    if f != file_path:
                        deps.append(Dependency(file_path, f, 'import', fqn))

    return deps


def parse_dependencies(files: list[ScannedFile]) -> list[Dependency]:
    """
    B7: Parse all files for dependencies (imports, calls, refs).

    Uses AST for Python, regex for other languages.
    Returns list of Dependency objects.
    """
    all_paths = {f.path for f in files}
    all_deps = []

    for f in files:
        if f.language == 'python':
            deps = _parse_python_deps(f.path, f.content, all_paths)
        else:
            deps = _parse_regex_deps(f.path, f.content, f.language, all_paths)
        all_deps.extend(deps)

    return all_deps


# ─── B8: Construction graphe de voisins ──────────────────────────────

MAX_NEIGHBORS = 9  # 9 neighbors per cube (like a Rubik's face)


def build_neighbor_graph(cubes: list[Cube], deps: list[Dependency],
                         max_neighbors: int = MAX_NEIGHBORS) -> dict[str, list[tuple[str, float]]]:
    """
    B8: Build neighbor graph for cubes.

    First pass: neighbors = static analysis (B7) + file proximity.
    Each cube gets up to max_neighbors closest neighbors.

    Returns: {cube_id: [(neighbor_id, weight), ...]}
    """
    if not cubes:
        return {}

    # Index cubes by file
    cubes_by_file: dict[str, list[Cube]] = defaultdict(list)
    cube_by_id: dict[str, Cube] = {}
    for c in cubes:
        cubes_by_file[c.file_origin].append(c)
        cube_by_id[c.id] = c

    # Sort cubes within each file by line_start
    for f in cubes_by_file:
        cubes_by_file[f].sort(key=lambda c: c.line_start)

    # Build file→file dependency graph
    file_deps: dict[str, set[str]] = defaultdict(set)
    for d in deps:
        file_deps[d.source].add(d.target)
        file_deps[d.target].add(d.source)  # Bidirectional

    graph: dict[str, list[tuple[str, float]]] = {}

    for cube in cubes:
        candidates: dict[str, float] = {}

        # 1. Same-file neighbors (proximity) — highest weight
        same_file = cubes_by_file.get(cube.file_origin, [])
        for other in same_file:
            if other.id == cube.id:
                continue
            # Weight inversely proportional to line distance
            line_dist = abs(cube.line_start - other.line_start)
            weight = 1.0 / (1.0 + line_dist * 0.01)
            candidates[other.id] = max(candidates.get(other.id, 0), weight)

        # 2. Cross-file neighbors (from dependencies) — medium weight
        dep_files = file_deps.get(cube.file_origin, set())
        for dep_file in dep_files:
            for other in cubes_by_file.get(dep_file, []):
                # Base weight 0.5 for dependency link
                weight = 0.5
                candidates[other.id] = max(candidates.get(other.id, 0), weight)

        # Sort by weight, take top max_neighbors
        sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1])
        graph[cube.id] = sorted_candidates[:max_neighbors]

    return graph


def assign_neighbors(cubes: list[Cube], deps: list[Dependency],
                     store: Optional['CubeStore'] = None,
                     max_neighbors: int = MAX_NEIGHBORS):
    """
    B8: Assign neighbors to cubes and optionally persist to CubeStore.

    Mutates cube.neighbors in-place.
    """
    graph = build_neighbor_graph(cubes, deps, max_neighbors)

    for cube in cubes:
        neighbors = graph.get(cube.id, [])
        cube.neighbors = [nid for nid, _ in neighbors]

        if store:
            for nid, weight in neighbors:
                store.set_neighbor(cube.id, nid, weight, 'static')


# ─── B11: Interface LLMProvider abstraite ─────────────────────────────

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    B11: Abstract LLM provider interface for cube reconstruction.

    Implementations: Ollama (B12), Claude (B13), OpenAI (B14).
    """

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        """Generate text completion."""
        ...

    @abstractmethod
    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Calculate perplexity of completion given prompt."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g. 'ollama', 'claude', 'openai')."""
        ...

    @property
    def supports_fim(self) -> bool:
        """Whether this provider supports Fill-in-the-Middle."""
        return False

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        """FIM: generate text to fill between prefix and suffix."""
        raise NotImplementedError(f"{self.name} does not support FIM")


# ─── B12: Backend Ollama ──────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """
    B12: LLM provider for Ollama (local models).

    Supports llama, mistral, phi, codellama, deepseek-coder.
    """

    def __init__(self, model: str = 'codellama', base_url: str = 'http://localhost:11434'):
        self.model = model
        self.base_url = base_url.rstrip('/')
        self._available = None

    @property
    def name(self) -> str:
        return 'ollama'

    @property
    def supports_fim(self) -> bool:
        return self.model in ('codellama', 'deepseek-coder', 'deepseek-coder-v2',
                              'starcoder2', 'codegemma', 'qwen2.5-coder')

    def _request(self, endpoint: str, payload: dict, timeout: int = 120) -> dict:
        """Make HTTP request to Ollama API."""
        import urllib.request
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}")

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        resp = self._request('/api/generate', {
            'model': self.model,
            'prompt': prompt,
            'options': {'num_predict': max_tokens, 'temperature': temperature},
            'stream': False,
        })
        return resp.get('response', '')

    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Estimate perplexity by tokenizing completion and measuring log probs."""
        # Ollama doesn't expose logprobs directly, estimate via generation
        # For now, return a rough estimate based on edit distance
        if not completion:
            return 0.0
        full_prompt = prompt + '\n# Expected:\n' + completion
        result = self.generate(full_prompt, max_tokens=len(completion) * 2)
        # Simple proxy: how different is the regeneration from the completion
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))  # 0 = perfect match, higher = more different

    def list_models(self) -> list[str]:
        if self._available is None:
            try:
                import urllib.request
                url = f"{self.base_url}/api/tags"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    self._available = [m['name'] for m in data.get('models', [])]
            except Exception:
                self._available = []
        return self._available

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        """FIM using Ollama's raw mode with FIM tokens."""
        if not self.supports_fim:
            raise NotImplementedError(f"{self.model} does not support FIM")
        # Use the standard FIM format (works with CodeLlama, DeepSeek-Coder)
        prompt = f"<PRE> {prefix} <SUF>{suffix} <MID>"
        return self.generate(prompt, max_tokens=max_tokens)


# ─── B13: Backend Claude API ─────────────────────────────────────────

class ClaudeProvider(LLMProvider):
    """
    B13: LLM provider for Claude API (Anthropic).

    Reuses the anthropic SDK.
    """

    def __init__(self, model: str = 'claude-sonnet-4-6',
                 api_key: Optional[str] = None):
        self.model = model
        self._api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        self._client = None

    @property
    def name(self) -> str:
        return 'claude'

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError("pip install anthropic required")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        client = self._get_client()
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.content[0].text if resp.content else ''

    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Claude doesn't expose logprobs; estimate via regeneration similarity."""
        if not completion:
            return 0.0
        result = self.generate(
            f"Complete this code exactly:\n{prompt}",
            max_tokens=len(completion) * 2,
        )
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))

    def list_models(self) -> list[str]:
        return ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001',
                'claude-opus-4-6']


# ─── B14: Backend OpenAI API ─────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """
    B14: LLM provider for OpenAI GPT models.
    """

    def __init__(self, model: str = 'gpt-4o-mini',
                 api_key: Optional[str] = None):
        self.model = model
        self._api_key = api_key or os.environ.get('OPENAI_API_KEY', '')
        self._client = None

    @property
    def name(self) -> str:
        return 'openai'

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise ValueError("OPENAI_API_KEY not set")
            try:
                import openai
                self._client = openai.OpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError("pip install openai required")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.choices[0].message.content or ''

    def get_perplexity(self, prompt: str, completion: str) -> float:
        if not completion:
            return 0.0
        result = self.generate(
            f"Complete this code exactly:\n{prompt}",
            max_tokens=len(completion) * 2,
        )
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))

    def list_models(self) -> list[str]:
        return ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo']


# ─── B15: Mode FIM (Fill-in-the-Middle) ──────────────────────────────

class FIMReconstructor:
    """
    B15: Fill-in-the-Middle reconstruction engine.

    Cube reconstruction IS code infilling — the cube is the span to fill.
    Uses FIM-capable models (DeepSeek-Coder, StarCoder2, CodeLlama) or
    falls back to standard prompt-based reconstruction.
    """

    # FIM token formats per model family
    FIM_FORMATS = {
        'codellama': {'pre': '<PRE> ', 'suf': ' <SUF>', 'mid': ' <MID>'},
        'deepseek-coder': {'pre': '<｜fim▁begin｜>', 'suf': '<｜fim▁hole｜>', 'mid': '<｜fim▁end｜>'},
        'starcoder2': {'pre': '<fim_prefix>', 'suf': '<fim_suffix>', 'mid': '<fim_middle>'},
        'codegemma': {'pre': '<|fim_prefix|>', 'suf': '<|fim_suffix|>', 'mid': '<|fim_middle|>'},
    }

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def reconstruct_fim(self, prefix: str, suffix: str,
                        max_tokens: int = 256) -> str:
        """Reconstruct missing code using FIM if available."""
        if self.provider.supports_fim:
            return self.provider.fim_generate(prefix, suffix, max_tokens)

        # Fallback: standard prompt-based infilling
        prompt = (
            "You are a code completion engine. Fill in the missing code between "
            "PREFIX and SUFFIX. Output ONLY the missing code, nothing else.\n\n"
            f"PREFIX:\n```\n{prefix}\n```\n\n"
            f"SUFFIX:\n```\n{suffix}\n```\n\n"
            "MISSING CODE:"
        )
        return self.provider.generate(prompt, max_tokens=max_tokens)

    def reconstruct_with_neighbors(self, cube: Cube, neighbors: list[Cube],
                                   max_tokens: int = 256) -> str:
        """
        Reconstruct a cube using its neighbors as context.

        This is the core reconstruction: neighbors provide the context,
        the cube content is what we're trying to reconstruct.
        """
        # Sort neighbors by line proximity
        sorted_neighbors = sorted(neighbors,
                                  key=lambda n: abs(n.line_start - cube.line_start))

        # Build context from neighbors
        context_parts = []
        for n in sorted_neighbors[:9]:
            context_parts.append(f"# From {n.file_origin} L{n.line_start}-{n.line_end}:\n{n.content}")

        context = "\n\n".join(context_parts)

        # Find prefix/suffix among same-file neighbors
        same_file = [n for n in sorted_neighbors if n.file_origin == cube.file_origin]
        prefix_cubes = [n for n in same_file if n.line_end <= cube.line_start]
        suffix_cubes = [n for n in same_file if n.line_start >= cube.line_end]

        prefix = prefix_cubes[-1].content if prefix_cubes else ""
        suffix = suffix_cubes[0].content if suffix_cubes else ""

        # Try FIM first if available
        if self.provider.supports_fim and prefix and suffix:
            return self.reconstruct_fim(prefix, suffix, max_tokens)

        # Standard prompt-based reconstruction
        prompt = (
            "Reconstruct the missing code. Context from neighboring code:\n\n"
            f"{context}\n\n"
            f"The missing code is from {cube.file_origin} "
            f"lines {cube.line_start}-{cube.line_end}.\n"
        )
        if prefix:
            prompt += f"\nCode immediately before:\n```\n{prefix}\n```\n"
        if suffix:
            prompt += f"\nCode immediately after:\n```\n{suffix}\n```\n"

        prompt += "\nOutput ONLY the missing code:"

        return self.provider.generate(prompt, max_tokens=max_tokens)


# ─── Mock provider for testing ────────────────────────────────────────

class MockLLMProvider(LLMProvider):
    """Test-only mock provider that returns predictable results."""

    def __init__(self, responses: Optional[dict[str, str]] = None):
        self._responses = responses or {}
        self._calls: list[dict] = []
        self._fim_enabled = False

    @property
    def name(self) -> str:
        return 'mock'

    @property
    def supports_fim(self) -> bool:
        return self._fim_enabled

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        self._calls.append({'method': 'generate', 'prompt': prompt,
                           'max_tokens': max_tokens, 'temperature': temperature})
        # Check if any response key is in the prompt
        for key, response in self._responses.items():
            if key in prompt:
                return response
        return "# mock generated code\npass"

    def get_perplexity(self, prompt: str, completion: str) -> float:
        self._calls.append({'method': 'perplexity', 'prompt': prompt,
                           'completion': completion})
        return 1.0

    def list_models(self) -> list[str]:
        return ['mock-model']

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        self._calls.append({'method': 'fim', 'prefix': prefix, 'suffix': suffix})
        return self._responses.get('fim', '# mock FIM result\npass')


# ─── B16: Moteur de reconstruction ───────────────────────────────────

@dataclass
class ReconstructionResult:
    """Result of a cube reconstruction attempt."""
    cube_id: str
    original_sha256: str
    reconstruction: str
    reconstruction_sha256: str
    exact_match: bool
    ncd_score: float      # 0.0 = identical, 1.0 = completely different
    perplexity: float
    success: bool         # exact_match OR ncd_score < threshold


def reconstruct_cube(cube: Cube, neighbors: list[Cube],
                     provider: LLMProvider,
                     ncd_threshold: float = 0.3) -> ReconstructionResult:
    """
    B16: Reconstruct a cube using its neighbors + LLM.

    1. Build prompt from neighbors context
    2. Call LLM to reconstruct
    3. Validate via SHA-256 (B17) and NCD fallback (B19)
    4. Score perplexity (B18)
    """
    fim = FIMReconstructor(provider)
    reconstruction = fim.reconstruct_with_neighbors(
        cube, neighbors, max_tokens=cube.token_count * 3
    )

    # B17: SHA-256 validation
    recon_sha256 = sha256_hash(reconstruction)
    exact_match = (recon_sha256 == cube.sha256)

    # B19: NCD fallback
    ncd = compute_ncd(cube.content, reconstruction)

    # B18: Perplexity scoring
    perplexity = provider.get_perplexity(
        "\n".join(n.content for n in neighbors[:3]),
        cube.content
    )

    success = exact_match or ncd < ncd_threshold

    return ReconstructionResult(
        cube_id=cube.id,
        original_sha256=cube.sha256,
        reconstruction=reconstruction,
        reconstruction_sha256=recon_sha256,
        exact_match=exact_match,
        ncd_score=ncd,
        perplexity=perplexity,
        success=success,
    )


# ─── B17: Validation SHA-256 ─────────────────────────────────────────

def validate_reconstruction(original: str, reconstruction: str) -> bool:
    """
    B17: Validate reconstruction via SHA-256 comparison.

    Both strings are normalized before hashing.
    """
    return sha256_hash(original) == sha256_hash(reconstruction)


# ─── B18: Scoring perplexite (hotness) ───────────────────────────────

def compute_hotness(cube: Cube, neighbors: list[Cube],
                    provider: LLMProvider) -> float:
    """
    B18: Compute hotness score for a cube.

    Hotness(cube) = -Σ log P_LLM(token_i | neighbors)
    ≈ perplexity of cube content given neighbor context.

    High hotness = irreconstructible = critical code.
    1 LLM call instead of 11 destructions.
    """
    context = "\n".join(n.content for n in neighbors[:9])
    return provider.get_perplexity(context, cube.content)


# ─── B19: NCD fallback ───────────────────────────────────────────────

def compute_ncd(a: str, b: str) -> float:
    """
    B19: Normalized Compression Distance.

    NCD(a,b) = (C(ab) - min(C(a),C(b))) / max(C(a),C(b))

    Returns 0.0 for identical strings, ~1.0 for completely different.
    Uses zlib as compressor.
    """
    import zlib

    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0

    a_bytes = a.encode('utf-8')
    b_bytes = b.encode('utf-8')

    ca = len(zlib.compress(a_bytes, 9))
    cb = len(zlib.compress(b_bytes, 9))
    cab = len(zlib.compress(a_bytes + b_bytes, 9))

    ncd = (cab - min(ca, cb)) / max(ca, cb)
    return max(0.0, min(1.0, ncd))  # Clamp to [0, 1]


def run_destruction_cycle(cubes: list[Cube], store: CubeStore,
                          provider: LLMProvider,
                          cycle_num: int = 1,
                          ncd_threshold: float = 0.3) -> list[ReconstructionResult]:
    """
    Run one cycle of destruction/reconstruction on all cubes.

    For each cube:
    1. Get its neighbors from store
    2. Reconstruct
    3. Record result
    4. Update temperature
    """
    results = []

    for cube in cubes:
        # Get neighbor cubes
        neighbor_entries = store.get_neighbors(cube.id)
        neighbor_cubes = []
        for nid, weight, ntype in neighbor_entries:
            n = store.get_cube(nid)
            if n:
                neighbor_cubes.append(n)

        # Reconstruct
        result = reconstruct_cube(cube, neighbor_cubes, provider, ncd_threshold)
        results.append(result)

        # Record in store
        store.record_cycle(cube.id, cycle_num, result.success,
                           result.reconstruction, result.perplexity)

        # Update temperature: hotter if reconstruction fails
        if result.success:
            new_temp = max(0.0, cube.temperature - 0.1)
        else:
            new_temp = min(1.0, cube.temperature + 0.2)
        store.update_temperature(cube.id, new_temp)
        store.update_score(cube.id, result.perplexity)
        cube.temperature = new_temp
        cube.score = result.perplexity

    return results


# ─── B23: Temperature par cube + stockage ─────────────────────────────

def compute_temperature(cube: Cube, store: CubeStore) -> float:
    """
    B23: Compute temperature for a cube based on cycle history.

    Temperature = f(perplexity, attempts, success_rate, survival)
    """
    cycles = store.get_cycles(cube.id)
    if not cycles:
        return cube.score  # Use raw perplexity if no history

    total = len(cycles)
    successes = sum(1 for c in cycles if c['success'])
    failures = total - successes
    success_rate = successes / total if total > 0 else 0.0

    avg_perplexity = sum(c.get('perplexity', 0) for c in cycles) / total if total else 0.0

    temperature = (
        0.4 * min(avg_perplexity / 5.0, 1.0) +
        0.4 * (1.0 - success_rate) +
        0.2 * min(failures / 10.0, 1.0)
    )
    return max(0.0, min(1.0, temperature))


def update_all_temperatures(cubes: list[Cube], store: CubeStore):
    """Update temperatures for all cubes based on their cycle history."""
    for cube in cubes:
        temp = compute_temperature(cube, store)
        store.update_temperature(cube.id, temp)
        cube.temperature = temp


# ─── B24: Kaplan-Meier survie par cube ────────────────────────────────

def kaplan_meier_survival(cube: Cube, store: CubeStore) -> float:
    """
    B24: Kaplan-Meier survival estimate. S(t) = Π(1 - d_i/n_i)
    High S(t) = cube stays hot. Low S(t) = cooling down.
    Scanniello 2011.
    """
    cycles = store.get_cycles(cube.id)
    if not cycles:
        return 1.0

    total = len(cycles)
    survival = 1.0

    for i, cycle in enumerate(cycles):
        n_i = total - i
        d_i = 0 if cycle['success'] else 1
        if n_i > 0:
            survival *= (1.0 - d_i / n_i)

    return max(0.0, min(1.0, survival))


# ─── B25: Danger Theory filtre ───────────────────────────────────────

def detect_dead_code(cube: Cube, all_cubes: list[Cube],
                     deps: list['Dependency']) -> bool:
    """
    B25: Detect dead code (Matzinger 2002).
    Dead = never imported, never called, never referenced.
    """
    is_target = any(d.target == cube.file_origin for d in deps)
    is_source = any(d.source == cube.file_origin for d in deps)

    if not is_target and not is_source:
        return True

    content = cube.content.strip()
    lines = content.split('\n')

    # Mostly comments
    comment_lines = sum(1 for l in lines if l.strip().startswith('#') or l.strip().startswith('//'))
    if len(lines) > 0 and comment_lines / len(lines) > 0.8:
        return True

    # Mostly TODO/FIXME
    todo_count = sum(1 for l in lines if any(tag in l.upper() for tag in ('TODO', 'FIXME', 'HACK', 'XXX')))
    if len(lines) > 2 and todo_count / len(lines) > 0.5:
        return True

    return False


def filter_dead_cubes(cubes: list[Cube], deps: list['Dependency']) -> tuple[list[Cube], list[Cube]]:
    """B25: Filter dead cubes. Returns (active, dead)."""
    active, dead = [], []
    for cube in cubes:
        if detect_dead_code(cube, cubes, deps):
            dead.append(cube)
        else:
            active.append(cube)
    return active, dead


# ─── B26: God's Number calcul ────────────────────────────────────────

@dataclass
class GodsNumberResult:
    """Result of God's Number computation."""
    gods_number: int
    total_cubes: int
    hot_cubes: list[Cube]
    dead_cubes: list[Cube]
    threshold: float
    bounds: dict


def compute_gods_number(cubes: list[Cube], store: CubeStore,
                        deps: list['Dependency'],
                        threshold: float = 0.5) -> GodsNumberResult:
    """
    B26: God's Number = |{cubes : Hotness > τ AND active}|

    Bounds: LRC ≥ n/10 (Gopalan 2012), MERA ~ O(log N) (Vidal 2007),
    Percolation fc = <k>/(<k²>-<k>) (Callaway 2000).
    """
    import math

    update_all_temperatures(cubes, store)
    active, dead = filter_dead_cubes(cubes, deps)
    hot = [c for c in active if c.temperature > threshold]

    n = len(active)
    lrc_lower = max(1, n // 10)
    mera_estimate = max(1, int(math.log2(max(n, 1))))

    degrees = []
    for c in active:
        neighbors = store.get_neighbors(c.id)
        degrees.append(len(neighbors))

    if degrees:
        k_mean = sum(degrees) / len(degrees)
        k2_mean = sum(d * d for d in degrees) / len(degrees)
        fc = k_mean / (k2_mean - k_mean) if (k2_mean - k_mean) > 0 else 1.0
    else:
        fc = 1.0

    return GodsNumberResult(
        gods_number=len(hot),
        total_cubes=len(cubes),
        hot_cubes=hot,
        dead_cubes=dead,
        threshold=threshold,
        bounds={
            'lrc_lower': lrc_lower,
            'mera_estimate': mera_estimate,
            'percolation_fc': fc,
            'n_active': n,
            'n_dead': len(dead),
        }
    )


# ─── B27: Remontee par niveaux ───────────────────────────────────────

def build_level_cubes(level0_cubes: list[Cube], level: int = 1,
                      group_size: int = 8) -> list[Cube]:
    """
    B27: Build higher-level cubes by grouping lower-level cubes.

    Level 0: ~88 tokens (atomic)
    Level 1: ~704 tokens (8×88)
    Level 2: ~5632 tokens (8×704)

    Groups cubes from the same file, adjacent by line order.
    """
    # Group by file
    by_file: dict[str, list[Cube]] = defaultdict(list)
    for c in level0_cubes:
        by_file[c.file_origin].append(c)

    upper_cubes = []

    for file_path, cubes in by_file.items():
        cubes.sort(key=lambda c: c.line_start)

        for i in range(0, len(cubes), group_size):
            group = cubes[i:i + group_size]
            if not group:
                continue

            content = "\n".join(c.content for c in group)
            line_start = group[0].line_start
            line_end = group[-1].line_end
            total_tokens = sum(c.token_count for c in group)

            cube = Cube(
                id=f"{file_path}:L{line_start}-L{line_end}:lv{level}",
                content=content,
                sha256=sha256_hash(content),
                file_origin=file_path,
                line_start=line_start,
                line_end=line_end,
                level=level,
                token_count=total_tokens,
            )
            upper_cubes.append(cube)

    return upper_cubes


# ─── B28: Agregation des scores entre niveaux ────────────────────────

def aggregate_scores(upper_cube: Cube, sub_cubes: list[Cube]) -> float:
    """
    B28: Aggregate scores from sub-cubes to upper cube.

    Score = max of sub-cube temperatures (hottest persists).
    A zone is only as resilient as its weakest part.
    """
    if not sub_cubes:
        return 0.0
    return max(c.temperature for c in sub_cubes)


def propagate_levels(level0_cubes: list[Cube], store: CubeStore,
                     max_level: int = 3) -> dict[int, list[Cube]]:
    """
    B27+B28: Build and score all levels.

    Returns {level: [cubes]} for levels 0 to max_level.
    Hot cubes persisting across levels = irreplaceable core.
    """
    levels: dict[int, list[Cube]] = {0: level0_cubes}

    current = level0_cubes
    for lvl in range(1, max_level + 1):
        upper = build_level_cubes(current, level=lvl)
        if not upper:
            break

        # Aggregate scores
        by_file: dict[str, list[Cube]] = defaultdict(list)
        for c in current:
            by_file[c.file_origin].append(c)

        for uc in upper:
            subs = [c for c in by_file.get(uc.file_origin, [])
                    if c.line_start >= uc.line_start and c.line_end <= uc.line_end]
            uc.temperature = aggregate_scores(uc, subs)
            uc.score = uc.temperature

        store.save_cubes(upper)
        levels[lvl] = upper
        current = upper

    return levels


# ─── B29: Feed resultats → mycelium ──────────────────────────────────

def feed_mycelium_from_results(results: list[ReconstructionResult],
                               cubes: list[Cube],
                               mycelium=None):
    """
    B29: Feed reconstruction results to mycelium.

    Creates mechanical (proven) connections:
    - Successful reconstruction = cube NEEDS its neighbors (proven dependency)
    - Failed reconstruction = neighbors are insufficient (weak link)

    Tags connections as 'mechanical' (distinct from statistical co-occurrence).
    """
    cube_by_id = {c.id: c for c in cubes}
    mechanical_pairs = []

    for result in results:
        cube = cube_by_id.get(result.cube_id)
        if not cube:
            continue

        for nid in cube.neighbors:
            neighbor = cube_by_id.get(nid)
            if not neighbor:
                continue

            # Extract concept names from cube content (simplified)
            cube_concepts = _extract_concepts(cube.content)
            neighbor_concepts = _extract_concepts(neighbor.content)

            pair = {
                'source': result.cube_id,
                'target': nid,
                'weight': 1.0 if result.success else -0.5,
                'type': 'mechanical',
                'cube_concepts': cube_concepts,
                'neighbor_concepts': neighbor_concepts,
            }
            mechanical_pairs.append(pair)

            # Feed to mycelium if available
            if hasattr(mycelium, 'observe'):
                combined = f"{cube.content}\n{neighbor.content}"
                try:
                    mycelium.observe(combined, zone=cube.file_origin)
                except Exception:
                    pass  # Graceful if mycelium not fully initialized

    return mechanical_pairs


def _extract_concepts(content: str) -> list[str]:
    """Extract concept names from code content (function/class names, imports)."""
    concepts = []
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('def '):
            name = line.split('(')[0].replace('def ', '')
            concepts.append(name)
        elif line.startswith('class '):
            name = line.split('(')[0].split(':')[0].replace('class ', '')
            concepts.append(name)
        elif line.startswith(('import ', 'from ')):
            parts = line.split()
            if len(parts) >= 2:
                concepts.append(parts[1].split('.')[0])
    return concepts


# ─── B30: Hebbian update ─────────────────────────────────────────────

def hebbian_update(store: CubeStore, results: list[ReconstructionResult],
                   learning_rate: float = 0.1):
    """
    B30: Hebbian learning on neighbor connections.

    Rule & O'Leary PNAS 2022: Self-Healing Neural Codes
    Δw = η × pre × post
    - Neighbors that reconstruct well → connection strengthened
    - Neighbors that fail → connection weakened
    - Homeostasis = SHA-256 validation (the ground truth)
    """
    for result in results:
        neighbors = store.get_neighbors(result.cube_id)
        for nid, weight, ntype in neighbors:
            if result.success:
                # Strengthen: successful reconstruction = neighbor was useful
                new_weight = min(2.0, weight + learning_rate)
            else:
                # Weaken: failed reconstruction = neighbor insufficient
                new_weight = max(0.1, weight - learning_rate * 0.5)

            store.set_neighbor(result.cube_id, nid, new_weight,
                             'mechanical' if ntype == 'static' else ntype)


# ─── B31: Git blame crossover ────────────────────────────────────────

def git_blame_cube(cube: Cube, repo_path: str) -> dict:
    """
    B31: Link hot cube to git history.

    Returns git blame info for the cube's lines.
    """
    import subprocess

    file_path = os.path.join(repo_path, cube.file_origin)
    if not os.path.exists(file_path):
        return {'error': f'File not found: {cube.file_origin}'}

    try:
        result = subprocess.run(
            ['git', 'blame', '-L', f'{cube.line_start},{cube.line_end}',
             '--porcelain', cube.file_origin],
            cwd=repo_path,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {'error': result.stderr.strip()}

        # Parse porcelain blame output
        commits = {}
        current_commit = None
        for line in result.stdout.split('\n'):
            if len(line) >= 40 and line[0] in '0123456789abcdef':
                parts = line.split()
                if len(parts) >= 3:
                    current_commit = parts[0]
                    if current_commit not in commits:
                        commits[current_commit] = {'lines': 0}
                    commits[current_commit]['lines'] += 1
            elif current_commit and line.startswith('author '):
                commits[current_commit]['author'] = line[7:]
            elif current_commit and line.startswith('summary '):
                commits[current_commit]['summary'] = line[8:]
            elif current_commit and line.startswith('author-time '):
                commits[current_commit]['time'] = int(line[12:])

        return {
            'cube_id': cube.id,
            'file': cube.file_origin,
            'lines': f'{cube.line_start}-{cube.line_end}',
            'commits': commits,
            'n_authors': len(set(c.get('author', '') for c in commits.values())),
        }

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {'error': 'git blame failed or git not available'}


def git_log_value(cube: Cube, repo_path: str) -> list[dict]:
    """
    B31: Check if a hot cube's content has changed recently.

    Returns recent commits that touched the cube's file+lines.
    """
    import subprocess

    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-5', '-L',
             f'{cube.line_start},{cube.line_end}:{cube.file_origin}'],
            cwd=repo_path,
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        entries = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    entries.append({'commit': parts[0], 'message': parts[1]})
        return entries

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ─── B32: Scheduling async ───────────────────────────────────────────

import time as _time


class CubeScheduler:
    """
    B32: Async scheduling — runs cube cycles in quiet periods.

    Detects repo activity via file timestamps and git status.
    Pauses when activity detected, resumes when quiet.
    """

    def __init__(self, repo_path: str, quiet_seconds: int = 300,
                 check_interval: int = 30):
        self.repo_path = repo_path
        self.quiet_seconds = quiet_seconds  # How long to wait for "quiet"
        self.check_interval = check_interval
        self._last_activity = _time.time()
        self._running = False

    def _check_activity(self) -> bool:
        """Check if repo has recent activity."""
        import subprocess
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True, text=True, timeout=5,
            )
            # Any uncommitted changes = active
            if result.stdout.strip():
                self._last_activity = _time.time()
                return True
        except Exception:
            pass

        # Check file modification times
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
            for f in files[:10]:  # Sample first 10 files per dir
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    if _time.time() - mtime < self.quiet_seconds:
                        self._last_activity = _time.time()
                        return True
                except OSError:
                    pass
            break  # Only check top-level

        return False

    def is_quiet(self) -> bool:
        """True if repo has been quiet for quiet_seconds."""
        return _time.time() - self._last_activity > self.quiet_seconds

    def should_run(self) -> bool:
        """Check if we should start/continue a cycle."""
        active = self._check_activity()
        return not active and self.is_quiet()


# ─── B33: Config securite ────────────────────────────────────────────

@dataclass
class CubeConfig:
    """
    B33: Security configuration for cube operations.

    local_only=True: ONLY local models (Ollama), code never leaves network.
    """
    local_only: bool = True
    max_cycles: int = 100
    ncd_threshold: float = 0.3
    temperature_threshold: float = 0.5
    target_tokens: int = 88
    max_neighbors: int = 9
    db_path: str = '.muninn/cube.db'
    allowed_providers: list[str] = field(default_factory=lambda: ['ollama', 'mock'])

    @classmethod
    def load(cls, config_path: str = '.muninn/config.json') -> 'CubeConfig':
        """Load config from JSON file."""
        if not os.path.exists(config_path):
            return cls()
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            cube_data = data.get('cube', {})
            return cls(
                local_only=cube_data.get('local_only', True),
                max_cycles=cube_data.get('max_cycles', 100),
                ncd_threshold=cube_data.get('ncd_threshold', 0.3),
                temperature_threshold=cube_data.get('temperature_threshold', 0.5),
                target_tokens=cube_data.get('target_tokens', 88),
                max_neighbors=cube_data.get('max_neighbors', 9),
                db_path=cube_data.get('db_path', '.muninn/cube.db'),
                allowed_providers=cube_data.get('allowed_providers', ['ollama', 'mock']),
            )
        except (json.JSONDecodeError, OSError):
            return cls()

    def save(self, config_path: str = '.muninn/config.json'):
        """Save config to JSON file."""
        os.makedirs(os.path.dirname(config_path) or '.', exist_ok=True)
        data = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        data['cube'] = {
            'local_only': self.local_only,
            'max_cycles': self.max_cycles,
            'ncd_threshold': self.ncd_threshold,
            'temperature_threshold': self.temperature_threshold,
            'target_tokens': self.target_tokens,
            'max_neighbors': self.max_neighbors,
            'db_path': self.db_path,
            'allowed_providers': self.allowed_providers,
        }
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)

    def get_provider(self) -> LLMProvider:
        """Get an LLM provider based on config."""
        if self.local_only:
            if 'mock' in self.allowed_providers:
                return MockLLMProvider()
            if 'ollama' not in self.allowed_providers:
                raise ValueError("local_only=True but 'ollama' not in allowed_providers")
            return OllamaProvider()

        # Try providers in order of preference
        if 'claude' in self.allowed_providers:
            if os.environ.get('ANTHROPIC_API_KEY'):
                return ClaudeProvider()
        if 'openai' in self.allowed_providers:
            if os.environ.get('OPENAI_API_KEY'):
                return OpenAIProvider()
        if 'ollama' in self.allowed_providers:
            return OllamaProvider()

        return MockLLMProvider()

    def validate_provider(self, provider: LLMProvider) -> bool:
        """Check if a provider is allowed by config."""
        if self.local_only and provider.name not in ('ollama', 'mock'):
            return False
        return provider.name in self.allowed_providers


# ─── B34: Multi-LLM hooks ────────────────────────────────────────────
# (Already covered by B11-B14 providers + B33 config)
# The hook system is the provider selection in CubeConfig.get_provider()


# ─── B39: CLI commands ───────────────────────────────────────────────

def cli_scan(repo_path: str, config: Optional[CubeConfig] = None) -> dict:
    """
    `cube scan <repo>` — Scan repo, subdivide, build index.

    Returns summary dict.
    """
    config = config or CubeConfig()
    store = CubeStore(config.db_path)

    try:
        # B1: scan
        files = scan_repo(repo_path)

        # B4: subdivide
        all_cubes = []
        for f in files:
            cubes = subdivide_file(f.path, f.content, config.target_tokens)
            all_cubes.extend(cubes)

        # B7+B8: deps + neighbors
        deps = parse_dependencies(files)
        assign_neighbors(all_cubes, deps, store=store,
                        max_neighbors=config.max_neighbors)

        # B6: store
        store.save_cubes(all_cubes)

        return {
            'files': len(files),
            'cubes': len(all_cubes),
            'dependencies': len(deps),
            'db_path': config.db_path,
        }
    finally:
        store.close()


def cli_run(repo_path: str, cycles: int = 1, level: int = 0,
            config: Optional[CubeConfig] = None) -> dict:
    """
    `cube run [--cycles N] [--level L]` — Run destruction/reconstruction cycles.
    """
    config = config or CubeConfig()
    store = CubeStore(config.db_path)

    try:
        provider = config.get_provider()
        cubes = store.get_cubes_by_level(level)
        deps = []  # Already stored; not needed for run

        all_results = []
        for cycle_num in range(1, cycles + 1):
            results = run_destruction_cycle(
                cubes, store, provider,
                cycle_num=cycle_num,
                ncd_threshold=config.ncd_threshold,
            )
            all_results.extend(results)

            # B30: Hebbian update
            hebbian_update(store, results)

            # B29: Feed mycelium (if available)
            feed_mycelium_from_results(results, cubes)

        successes = sum(1 for r in all_results if r.success)
        return {
            'cycles': cycles,
            'cubes_tested': len(cubes),
            'total_tests': len(all_results),
            'successes': successes,
            'failures': len(all_results) - successes,
            'success_rate': successes / len(all_results) if all_results else 0.0,
        }
    finally:
        store.close()


def cli_status(config: Optional[CubeConfig] = None) -> dict:
    """
    `cube status` — Show God's Number, hot cubes, temperature stats.
    """
    config = config or CubeConfig()
    if not os.path.exists(config.db_path):
        return {'error': 'No cube database found. Run `cube scan` first.'}

    store = CubeStore(config.db_path)
    try:
        total = store.count_cubes()
        hot = store.get_hot_cubes(config.temperature_threshold)

        # Temperature stats
        all_cubes = store.get_cubes_by_level(0)
        temps = [c.temperature for c in all_cubes]
        avg_temp = sum(temps) / len(temps) if temps else 0.0

        return {
            'total_cubes': total,
            'hot_cubes': len(hot),
            'gods_number_estimate': len(hot),
            'avg_temperature': round(avg_temp, 3),
            'max_temperature': round(max(temps), 3) if temps else 0.0,
            'levels': {
                lvl: store.count_cubes(level=lvl)
                for lvl in range(4)
                if store.count_cubes(level=lvl) > 0
            },
        }
    finally:
        store.close()


def cli_god(config: Optional[CubeConfig] = None) -> dict:
    """
    `cube god` — Compute and display God's Number with bounds.
    """
    config = config or CubeConfig()
    if not os.path.exists(config.db_path):
        return {'error': 'No cube database found. Run `cube scan` first.'}

    store = CubeStore(config.db_path)
    try:
        cubes = store.get_cubes_by_level(0)
        result = compute_gods_number(cubes, store, [],
                                     threshold=config.temperature_threshold)
        return {
            'gods_number': result.gods_number,
            'total_cubes': result.total_cubes,
            'dead_cubes': len(result.dead_cubes),
            'threshold': result.threshold,
            'bounds': result.bounds,
            'hot_cube_ids': [c.id for c in result.hot_cubes[:20]],
        }
    finally:
        store.close()


# ─── B9: Laplacian RG groupage optimal ──────────────────────────────

def build_adjacency_matrix(cubes: list[Cube], store: CubeStore):
    """Build adjacency matrix from cube neighbor graph."""
    import numpy as np

    n = len(cubes)
    id_to_idx = {c.id: i for i, c in enumerate(cubes)}
    A = np.zeros((n, n))

    for cube in cubes:
        i = id_to_idx[cube.id]
        neighbors = store.get_neighbors(cube.id)
        for nid, weight, _ in neighbors:
            j = id_to_idx.get(nid)
            if j is not None:
                A[i, j] = weight
                A[j, i] = weight

    return A, id_to_idx


def laplacian_rg_grouping(cubes: list[Cube], store: CubeStore,
                          n_groups: Optional[int] = None) -> list[list[Cube]]:
    """
    B9: Laplacian RG grouping (Villegas 2023).
    L = D - A, spectral decimation groups cubes by eigenvector similarity.
    Falls back to sequential grouping if numpy not available.
    """
    try:
        import numpy as np
        from numpy.linalg import eigh
    except ImportError:
        groups = []
        by_file = defaultdict(list)
        for c in cubes:
            by_file[c.file_origin].append(c)
        for f, fcubes in by_file.items():
            fcubes.sort(key=lambda c: c.line_start)
            for i in range(0, len(fcubes), 8):
                groups.append(fcubes[i:i+8])
        return groups

    n = len(cubes)
    if n <= 1:
        return [cubes] if cubes else []

    if n_groups is None:
        n_groups = max(1, n // 8)

    A, id_to_idx = build_adjacency_matrix(cubes, store)
    D = np.diag(A.sum(axis=1))
    L = D - A

    k = min(n_groups, n - 1)
    try:
        eigenvalues, eigenvectors = eigh(L)
        features = eigenvectors[:, 1:k+1]
    except Exception:
        features = np.random.randn(n, k)

    labels = _simple_kmeans(features, n_groups)

    groups_dict: dict[int, list[Cube]] = defaultdict(list)
    for i, label in enumerate(labels):
        groups_dict[label].append(cubes[i])

    return list(groups_dict.values())


def _simple_kmeans(X, k, max_iter: int = 20):
    """Simple k-means using numpy only."""
    import numpy as np

    n = X.shape[0]
    if k >= n:
        return list(range(n))

    rng = np.random.RandomState(42)
    indices = rng.choice(n, k, replace=False)
    centroids = X[indices].copy()
    labels = np.zeros(n, dtype=int)

    for _ in range(max_iter):
        for i in range(n):
            dists = np.sum((centroids - X[i]) ** 2, axis=1)
            labels[i] = np.argmin(dists)

        new_centroids = np.zeros_like(centroids)
        for j in range(k):
            members = X[labels == j]
            if len(members) > 0:
                new_centroids[j] = members.mean(axis=0)
            else:
                new_centroids[j] = centroids[j]

        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids

    return labels.tolist()


# ─── B10: Cheeger constant ──────────────────────────────────────────

def cheeger_constant(cubes: list[Cube], store: CubeStore) -> dict:
    """
    B10: Cheeger constant. λ₂/2 ≤ h ≤ √(2λ₂).
    Identifies bottleneck cubes via Fiedler vector sign change.
    """
    try:
        import numpy as np
        from numpy.linalg import eigh
    except ImportError:
        return {'h_estimate': 0.0, 'lambda_2': 0.0, 'bottlenecks': [],
                'error': 'numpy not available'}

    n = len(cubes)
    if n < 2:
        return {'h_estimate': 0.0, 'lambda_2': 0.0, 'bottlenecks': []}

    A, id_to_idx = build_adjacency_matrix(cubes, store)
    D = np.diag(A.sum(axis=1))
    L = D - A

    eigenvalues, eigenvectors = eigh(L)
    lambda_2 = float(eigenvalues[1]) if len(eigenvalues) > 1 else 0.0

    import math
    h_lower = lambda_2 / 2.0
    h_upper = math.sqrt(2.0 * max(lambda_2, 0.0))

    if len(eigenvectors) > 1:
        fiedler = eigenvectors[:, 1]
        abs_fiedler = np.abs(fiedler)
        bottleneck_indices = np.argsort(abs_fiedler)[:max(1, n // 10)]
        bottleneck_ids = [cubes[i].id for i in bottleneck_indices]
    else:
        bottleneck_ids = []

    return {
        'h_lower': h_lower,
        'h_upper': h_upper,
        'h_estimate': (h_lower + h_upper) / 2,
        'lambda_2': lambda_2,
        'bottlenecks': bottleneck_ids,
    }


# ─── B20: Belief Propagation ─────────────────────────────────────────

def belief_propagation(cubes: list[Cube], store: CubeStore,
                       max_iter: int = 15, tolerance: float = 1e-4) -> dict[str, float]:
    """
    B20: Belief Propagation (Pearl 1988). Neighbors exchange beliefs.
    Returns {cube_id: belief} where belief = probability of being hot.
    """
    beliefs: dict[str, float] = {c.id: c.temperature for c in cubes}
    messages: dict[tuple[str, str], float] = {}

    for cube in cubes:
        neighbors = store.get_neighbors(cube.id)
        for nid, weight, _ in neighbors:
            messages[(cube.id, nid)] = 0.5

    for iteration in range(max_iter):
        max_change = 0.0
        new_messages = {}

        for cube in cubes:
            neighbors = store.get_neighbors(cube.id)
            for nid, weight, _ in neighbors:
                incoming_product = 1.0
                for nid2, w2, _ in neighbors:
                    if nid2 != nid:
                        msg = messages.get((nid2, cube.id), 0.5)
                        incoming_product *= (msg * w2 + (1 - msg) * (1 - w2))

                compat = weight * cube.temperature
                new_msg = compat * incoming_product
                new_msg = max(0.001, min(0.999, new_msg))

                old_msg = messages.get((cube.id, nid), 0.5)
                max_change = max(max_change, abs(new_msg - old_msg))
                new_messages[(cube.id, nid)] = new_msg

        messages.update(new_messages)
        if max_change < tolerance:
            break

    for cube in cubes:
        neighbors = store.get_neighbors(cube.id)
        belief = cube.temperature
        for nid, weight, _ in neighbors:
            msg = messages.get((nid, cube.id), 0.5)
            belief *= msg
        beliefs[cube.id] = max(0.0, min(1.0, belief))

    return beliefs


# ─── B21: Survey Propagation pre-filtre ──────────────────────────────

def survey_propagation_filter(cubes: list[Cube], store: CubeStore,
                              neutral_threshold: float = 0.2) -> tuple[list[Cube], list[Cube]]:
    """
    B21: Survey Propagation pre-filter (Mezard-Parisi 2002).
    Skips trivial cubes (~30% neutral, Schulte 2014).
    Returns (non_trivial, trivial).
    """
    beliefs = belief_propagation(cubes, store, max_iter=5)
    trivial, non_trivial = [], []

    for cube in cubes:
        belief = beliefs.get(cube.id, 0.5)
        if belief < neutral_threshold:
            trivial.append(cube)
        else:
            non_trivial.append(cube)

    return non_trivial, trivial


# ─── B22: Tononi Degeneracy ──────────────────────────────────────────

def tononi_degeneracy(cube: Cube, store: CubeStore,
                      all_cubes: list[Cube]) -> float:
    """
    B22: Tononi Degeneracy (Tononi 1999).
    D = Σ MI(v_i, cube) - MI(all_v, cube).
    High D = fragile (redundant neighbors). Low D = critical.
    Uses NCD as MI proxy.
    """
    neighbors = store.get_neighbors(cube.id)
    if not neighbors:
        return 0.0

    cube_by_id = {c.id: c for c in all_cubes}

    individual_mi = 0.0
    neighbor_contents = []
    for nid, weight, _ in neighbors:
        n = cube_by_id.get(nid)
        if n:
            ncd = compute_ncd(cube.content, n.content)
            individual_mi += (1.0 - ncd)
            neighbor_contents.append(n.content)

    if not neighbor_contents:
        return 0.0

    combined = "\n".join(neighbor_contents)
    combined_ncd = compute_ncd(cube.content, combined)
    joint_mi = 1.0 - combined_ncd

    return max(0.0, individual_mi - joint_mi)


# ─── B35: Cube Heatmap ────────────────────────────────────────────────

def cube_heatmap(store: CubeStore) -> dict:
    """
    B35: Generate heatmap of cube temperatures grouped by file.
    Returns {file: {count, hot_count, avg_temp, max_temp, cubes: [{id, temp, lines}]}}.
    """
    rows = store.conn.execute(
        "SELECT file_origin, id, temperature, line_start, line_end "
        "FROM cubes WHERE level = 0 ORDER BY file_origin, line_start"
    ).fetchall()

    heatmap = {}
    for file_origin, cid, temp, ls, le in rows:
        if file_origin not in heatmap:
            heatmap[file_origin] = {
                'count': 0, 'hot_count': 0, 'temps': [],
                'cubes': [],
            }
        entry = heatmap[file_origin]
        entry['count'] += 1
        entry['temps'].append(temp)
        if temp > 0.5:
            entry['hot_count'] += 1
        entry['cubes'].append({'id': cid, 'temp': temp, 'lines': f"L{ls}-{le}"})

    # Compute aggregates
    for f, entry in heatmap.items():
        temps = entry.pop('temps')
        entry['avg_temp'] = sum(temps) / len(temps) if temps else 0.0
        entry['max_temp'] = max(temps) if temps else 0.0

    return heatmap


# ─── B36: Forge Link — fuse Cube + Forge risks ────────────────────────

def fuse_risks(store: CubeStore, forge_root: str,
               forge_weight: float = 0.4,
               cube_weight: float = 0.6) -> list[dict]:
    """
    B36: Combine Forge defect prediction risk with Cube temperature.
    combined_risk = forge_weight * forge_risk + cube_weight * cube_avg_temp.
    Returns sorted list of {file, forge_risk, cube_temp, combined, hot_cubes}.
    """
    # Get cube temperatures per file
    cube_temps = {}
    rows = store.conn.execute(
        "SELECT file_origin, AVG(temperature), MAX(temperature), COUNT(*), "
        "SUM(CASE WHEN temperature > 0.5 THEN 1 ELSE 0 END) "
        "FROM cubes WHERE level = 0 GROUP BY file_origin"
    ).fetchall()
    for file_origin, avg_t, max_t, count, hot in rows:
        cube_temps[file_origin] = {
            'avg_temp': avg_t, 'max_temp': max_t,
            'count': count, 'hot_cubes': hot,
        }

    # Get Forge risks (capture printed output, parse risk scores)
    forge_risks = _get_forge_risks(forge_root)

    # Fuse
    all_files = set(cube_temps.keys()) | set(forge_risks.keys())
    results = []
    for f in all_files:
        fr = forge_risks.get(f, 0.0)
        ct = cube_temps.get(f, {}).get('avg_temp', 0.0)
        combined = forge_weight * fr + cube_weight * ct
        results.append({
            'file': f,
            'forge_risk': fr,
            'cube_temp': ct,
            'combined': combined,
            'hot_cubes': cube_temps.get(f, {}).get('hot_cubes', 0),
        })

    results.sort(key=lambda x: x['combined'], reverse=True)
    return results


def _get_forge_risks(forge_root: str) -> dict:
    """Extract risk scores from Forge predict_defects (parse output)."""
    import io
    import contextlib
    try:
        from engine.core.forge import predict_defects
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            predict_defects(Path(forge_root))
        output = buf.getvalue()
        # Parse "  0.73  engine/core/muninn.py" lines
        risks = {}
        for line in output.split('\n'):
            line = line.strip()
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    risk = float(parts[0])
                    fname = parts[1].strip()
                    if fname.endswith('.py'):
                        risks[fname] = risk
                except ValueError:
                    continue
        return risks
    except Exception:
        return {}


# ─── B37: Auto-repair — generate patches for failing tests ────────────

def auto_repair(store: CubeStore, failed_files: list[str],
                reconstructor=None, max_patches: int = 3) -> list[dict]:
    """
    B37: For failing test files, find hot cubes and generate repair patches.
    1. Find cubes in failed files sorted by temperature (hottest first)
    2. Generate up to max_patches reconstructions via FIM
    3. Return patches with metadata

    Args:
        store: CubeStore with scanned cubes
        failed_files: list of file paths that have test failures
        reconstructor: FIMReconstructor instance (or None for dry-run)
        max_patches: max patches to generate

    Returns list of {cube_id, file, original, patch, temperature}.
    """
    patches = []

    for fpath in failed_files:
        cubes = store.get_cubes_by_file(fpath)
        # Sort by temperature descending — hottest cubes first
        cubes.sort(key=lambda c: c.temperature, reverse=True)

        for cube in cubes[:max_patches]:
            neighbors = store.get_neighbors(cube.id)
            if not neighbors:
                continue

            # Build context from neighbors
            context_parts = []
            for nid, weight, _ in neighbors:
                ncube = store.get_cube(nid)
                if ncube:
                    context_parts.append(ncube.content)

            prefix = "\n".join(context_parts[:len(context_parts)//2])
            suffix = "\n".join(context_parts[len(context_parts)//2:])

            patch_content = None
            if reconstructor:
                try:
                    patch_content = reconstructor.reconstruct(
                        prefix=prefix, suffix=suffix,
                        hint=f"# Reconstruct {cube.file_origin} L{cube.line_start}-{cube.line_end}"
                    )
                except Exception:
                    patch_content = None

            patches.append({
                'cube_id': cube.id,
                'file': cube.file_origin,
                'line_start': cube.line_start,
                'line_end': cube.line_end,
                'original': cube.content,
                'patch': patch_content,
                'temperature': cube.temperature,
                'neighbor_count': len(neighbors),
            })

            if len(patches) >= max_patches:
                break
        if len(patches) >= max_patches:
            break

    return patches


# ─── B38: Feedback loop — anomalies → mycelium ────────────────────────

def record_anomaly(anomaly_path: str, file: str, metrics: dict,
                   cube_ids: list[str], label: str = "predicted_risky"):
    """
    B38: Record a file anomaly for future feedback validation.
    Stored as JSONL in .muninn/anomalies.jsonl.
    """
    import time as time_mod
    os.makedirs(os.path.dirname(anomaly_path) or '.', exist_ok=True)
    entry = {
        'timestamp': time_mod.time(),
        'date': time_mod.strftime('%Y-%m-%d'),
        'file': file,
        'metrics': metrics,
        'cube_ids': cube_ids,
        'label': label,
        'validated': False,
    }
    with open(anomaly_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')
    return entry


def feedback_loop_check(anomaly_path: str, repo_root: str,
                        lookback_days: int = 180) -> dict:
    """
    B38: Check old anomalies — were they actually buggy?
    Looks at git log for bugfix commits in predicted files.
    Returns {total, correct, accuracy, details}.
    """
    import subprocess
    import time as time_mod

    if not os.path.exists(anomaly_path):
        return {'total': 0, 'correct': 0, 'accuracy': 0.0, 'details': []}

    cutoff = time_mod.time() - (lookback_days * 86400)
    anomalies = []
    with open(anomaly_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get('timestamp', 0) < cutoff:
                    anomalies.append(entry)
            except json.JSONDecodeError:
                continue

    if not anomalies:
        return {'total': 0, 'correct': 0, 'accuracy': 0.0, 'details': []}

    details = []
    correct = 0
    for a in anomalies:
        # Check if file had bugfix commits since the anomaly was recorded
        since_date = a.get('date', '2020-01-01')
        try:
            result = subprocess.run(
                ['git', 'log', '--oneline', f'--since={since_date}',
                 '--grep=fix\\|bug\\|patch\\|repair', '--', a['file']],
                capture_output=True, text=True, cwd=repo_root, timeout=10
            )
            bugfixes = [l for l in result.stdout.strip().split('\n') if l.strip()]
        except Exception:
            bugfixes = []

        was_buggy = len(bugfixes) > 0
        if was_buggy:
            correct += 1

        details.append({
            'file': a['file'],
            'predicted': a['label'],
            'was_buggy': was_buggy,
            'bugfix_count': len(bugfixes),
            'date': a.get('date'),
        })

    total = len(anomalies)
    return {
        'total': total,
        'correct': correct,
        'accuracy': correct / total if total > 0 else 0.0,
        'details': details,
    }


def feed_anomalies_to_mycelium(anomaly_path: str, mycelium=None) -> list[dict]:
    """
    B38: Feed validated anomaly patterns to mycelium for future prediction.
    Creates concept pairs: (file_concept, 'bug_prone') with positive weight
    for correct predictions, negative for false positives.
    """
    if not os.path.exists(anomaly_path):
        return []

    pairs = []
    with open(anomaly_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if not entry.get('validated'):
                    continue
                # Extract file concept (stem without extension)
                file_concept = Path(entry['file']).stem
                weight = 1.0 if entry.get('was_buggy') else -0.5
                pairs.append({
                    'source': file_concept,
                    'target': 'bug_prone',
                    'weight': weight,
                    'type': 'feedback',
                })
            except (json.JSONDecodeError, KeyError):
                continue

    if mycelium and pairs:
        for p in pairs:
            try:
                mycelium.observe_pair(p['source'], p['target'], weight=p['weight'])
            except Exception:
                pass

    return pairs
