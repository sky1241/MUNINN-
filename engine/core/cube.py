#!/usr/bin/env python3
"""
Cube Muninn — Code resilience through atomic destruction/reconstruction.

The cube is the mycelium subdividing and testing its own knowledge.
Scan → subdivide → destroy → reconstruct → validate → learn.

Briques B1-B8, B11-B19: Scanner, Tokenizer, Dataclass, Subdivision, SHA-256,
Storage, AST, Neighbors, LLM Providers, FIM, Reconstruction, Validation,
Scoring, NCD, Temperature, Kaplan-Meier, Danger Theory, God's Number.
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
