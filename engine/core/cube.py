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
import sys
import os
import re
import sqlite3
import threading
import time as _time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# M3 fix: _quarantine_lock and _anomaly_lock moved to cube_analysis.py
# (only used there). Removed dead definitions here.

from engine.core.tokenizer import token_count
try:
    from engine.core.wal_monitor import WALMonitor
except ImportError:
    try:
        from .wal_monitor import WALMonitor
    except ImportError:
        from wal_monitor import WALMonitor

try:
    from engine.core.lang_lexicons import get_lexicon, format_lexicon_prompt
except ImportError:
    try:
        from .lang_lexicons import get_lexicon, format_lexicon_prompt
    except ImportError:
        from lang_lexicons import get_lexicon, format_lexicon_prompt

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
    '.cob': 'cobol', '.cbl': 'cobol', '.cpy': 'cobol',
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
    extension: str = ''
    size: int = 0
    lines: int = 0

    def __post_init__(self):
        if self.token_count == 0 and self.content:
            self.token_count = token_count(self.content)
        if self.size == 0 and self.content:
            self.size = len(self.content)
        if self.lines == 0 and self.content:
            self.lines = self.content.count('\n') + 1
        if not self.extension and self.path:
            self.extension = os.path.splitext(self.path)[1]


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

    Each cube holds ~112 tokens of code and knows its neighbors.
    """
    id: str                          # Unique ID (e.g. "file.py:L10-L25:level1")
    content: str                     # The actual code
    sha256: str                      # SHA-256 of normalized content
    file_origin: str                 # Source file path (relative)
    line_start: int                  # First line in source
    line_end: int                    # Last line in source
    level: int = 0                   # 0=atomic(112tok), 1=896tok, 2=7168tok...
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
    if text is None:
        text = ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    if not isinstance(text, str):
        text = str(text)
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

TARGET_TOKENS = 112      # Atomic cube size (QTM: 14 tokens × 8 faces)
TOLERANCE_MIN = 92       # Accept cubes >= this (avoid tiny scraps)
TOLERANCE_MAX = 132      # Accept cubes <= this (avoid splitting mid-statement)


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
    B4: Recursive subdivision /8 until atomic cubes of ~112 tokens.

    Each level divides by ~8. Stops when cubes are within tolerance.
    """
    total = token_count(content)
    if total <= TOLERANCE_MAX:
        return subdivide_file(file_path, content, target_tokens, level=0)

    # Calculate appropriate level
    # level 0 = 112 tokens, level 1 = 896, level 2 = 7168, etc.
    level = 0
    size = total
    while size > TOLERANCE_MAX and level < max_levels:
        size = size // 8
        level += 1

    # Direct subdivision to calculated level
    return subdivide_file(file_path, content, target_tokens, level=level)


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
CREATE INDEX IF NOT EXISTS idx_neighbors_cube ON neighbors(cube_id);
"""


class CubeStore:
    """B6: SQLite storage for cube index."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()  # Protects all DB writes when check_same_thread=False
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(CUBE_DB_SCHEMA)
        self.conn.commit()
        self._wal_monitor = WALMonitor(self.conn)

    def close(self):
        if self.conn:
            with self._lock:
                try:
                    self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except sqlite3.OperationalError:
                    pass
                self.conn.close()
                self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Cube CRUD ──

    def save_cube(self, cube: Cube):
        """Insert or replace a cube."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO cubes "
                "(id, sha256, content, file_origin, line_start, line_end, level, score, temperature, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cube.id, cube.sha256, cube.content, cube.file_origin,
                 cube.line_start, cube.line_end, cube.level,
                 cube.score, cube.temperature, cube.token_count)
            )
            self.conn.commit()
            self._wal_monitor.on_write()

    def save_cubes(self, cubes: list[Cube]):
        """Batch insert cubes."""
        with self._lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO cubes "
                "(id, sha256, content, file_origin, line_start, line_end, level, score, temperature, token_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(c.id, c.sha256, c.content, c.file_origin, c.line_start, c.line_end,
                  c.level, c.score, c.temperature, c.token_count) for c in cubes]
            )
            self.conn.commit()
            self._wal_monitor.on_write()

    def get_cube(self, cube_id: str) -> Optional[Cube]:
        """Get a cube by ID."""
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            if level is not None:
                return self.conn.execute(
                    "SELECT COUNT(*) FROM cubes WHERE level = ?", (level,)
                ).fetchone()[0]
            return self.conn.execute("SELECT COUNT(*) FROM cubes").fetchone()[0]

    def delete_cube(self, cube_id: str):
        """Delete a cube and its neighbors/cycles."""
        with self._lock:
            self.conn.execute("DELETE FROM cubes WHERE id = ?", (cube_id,))
            self.conn.execute("DELETE FROM neighbors WHERE cube_id = ? OR neighbor_id = ?",
                              (cube_id, cube_id))
            self.conn.execute("DELETE FROM cycles WHERE cube_id = ?", (cube_id,))
            self.conn.commit()
            self._wal_monitor.on_write()

    # ── Neighbors ──

    def set_neighbor(self, cube_id: str, neighbor_id: str,
                     weight: float = 1.0, ntype: str = 'static'):
        """Set a neighbor relationship."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO neighbors (cube_id, neighbor_id, weight, type) "
                "VALUES (?, ?, ?, ?)",
                (cube_id, neighbor_id, weight, ntype)
            )
            self.conn.commit()
            self._wal_monitor.on_write()

    def get_neighbors(self, cube_id: str) -> list[tuple[str, float, str]]:
        """Get neighbors of a cube. Returns [(neighbor_id, weight, type)]."""
        with self._lock:
            return self.conn.execute(
                "SELECT neighbor_id, weight, type FROM neighbors WHERE cube_id = ? "
                "ORDER BY weight DESC",
                (cube_id,)
            ).fetchall()

    # ── Cycles ──

    def record_cycle(self, cube_id: str, cycle_num: int, success: bool,
                     reconstruction: str = '', perplexity: float = 0.0):
        """Record a reconstruction cycle result."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO cycles (cube_id, cycle_num, success, reconstruction, perplexity, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (cube_id, cycle_num, int(success), reconstruction, perplexity, _time.time())
            )
            self.conn.commit()
            self._wal_monitor.on_write()

    def get_cycles(self, cube_id: str) -> list[dict]:
        """Get cycle history for a cube."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT cycle_num, success, reconstruction, perplexity, timestamp "
                "FROM cycles WHERE cube_id = ? ORDER BY cycle_num",
                (cube_id,)
            ).fetchall()
        return [{'cycle': r[0], 'success': bool(r[1]), 'reconstruction': r[2],
                 'perplexity': r[3], 'timestamp': r[4]} for r in rows]

    def update_temperature(self, cube_id: str, temperature: float):
        """Update a cube's temperature."""
        with self._lock:
            self.conn.execute(
                "UPDATE cubes SET temperature = ? WHERE id = ?",
                (temperature, cube_id)
            )
            self.conn.commit()
            self._wal_monitor.on_write()

    def update_score(self, cube_id: str, score: float):
        """Update a cube's hotness score."""
        with self._lock:
            self.conn.execute(
                "UPDATE cubes SET score = ? WHERE id = ?",
                (score, cube_id)
            )
            self.conn.commit()
            self._wal_monitor.on_write()


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


# ─── B7b: Extract AST hints per cube (pre-destruction) ──────────────

def extract_ast_hints(cube: Cube) -> dict:
    """
    Extract structural constraints from a cube's content before destruction.
    These hints constrain the LLM during reconstruction.

    Language-agnostic approach: extract ALL identifiers from the code,
    plus first/last lines as anchors. Works for any language without
    hardcoded patterns per language.
    """
    content = cube.content
    lines = content.split('\n')
    non_empty = [l for l in lines if l.strip()]
    hints = {
        'functions': [],
        'classes': [],
        'imports': [],
        'variables': [],
        'identifiers': [],     # ALL unique identifiers in the cube
        'strings': [],         # string literals ("closed", "error: %v", etc.)
        'type_sigs': [],       # type signatures (field Type `tag`)
        'first_line': '',      # anchor: first non-empty line
        'last_line': '',       # anchor: last non-empty line
        'indent_char': None,
        'indent_level': 0,
        'n_lines': len(lines),
        'n_tokens': cube.token_count,
    }

    # Line anchors: first, last, + every 5th line as checkpoints
    if non_empty:
        hints['first_line'] = non_empty[0]
        hints['last_line'] = non_empty[-1]
    # Intermediate anchors — use REAL line numbers (counting blanks)
    # Not non_empty index — actual position in the full content
    anchors = []
    for idx, line in enumerate(lines):
        if idx == 0 or idx == len(lines) - 1:
            continue  # first/last already covered
        if (idx + 1) % 5 == 0:  # every 5th line (real position)
            anchors.append((idx + 1, line))
    hints['anchors'] = anchors

    # Detect indentation from first indented line
    for line in lines:
        stripped = line.lstrip()
        if stripped and line != stripped:
            indent = line[:len(line) - len(stripped)]
            if '\t' in indent:
                hints['indent_char'] = 'tabs'
            else:
                n_spaces = len(indent)
                hints['indent_char'] = f'{n_spaces} spaces'
            hints['indent_level'] = len(indent)
            break

    # Extract ALL identifiers — language-agnostic
    # Matches any word that looks like a code identifier (not a keyword, not a number)
    all_ids = set()
    for line in lines:
        # Find all identifier-like tokens: starts with letter or _, at least 2 chars
        ids = re.findall(r'\b([a-zA-Z_]\w{1,})\b', line)
        all_ids.update(ids)

    # Remove common keywords (universal across languages)
    _KEYWORDS = {
        'if', 'else', 'for', 'while', 'return', 'break', 'continue',
        'switch', 'case', 'default', 'try', 'catch', 'finally', 'throw',
        'new', 'delete', 'this', 'self', 'true', 'false', 'null', 'nil',
        'none', 'void', 'int', 'float', 'double', 'string', 'bool',
        'import', 'from', 'package', 'module', 'include', 'require',
        'class', 'struct', 'enum', 'interface', 'trait', 'type',
        'def', 'func', 'function', 'fn', 'fun', 'sub', 'proc',
        'public', 'private', 'protected', 'internal', 'static',
        'const', 'let', 'var', 'val', 'mut', 'final', 'readonly',
        'async', 'await', 'yield', 'defer', 'go', 'chan', 'select',
        'pub', 'crate', 'mod', 'use', 'impl', 'where', 'match',
        'elif', 'elsif', 'unless', 'until', 'begin', 'end', 'do',
        'and', 'or', 'not', 'in', 'is', 'as', 'with', 'pass', 'raise',
        'extends', 'implements', 'override', 'abstract', 'sealed',
        'export', 'declare', 'namespace', 'typeof', 'instanceof',
    }
    identifiers = sorted(all_ids - _KEYWORDS)
    hints['identifiers'] = identifiers[:50]  # cap at 50 to not bloat prompt

    # Extract string literals — the values inside quotes
    # These are critical: "closed", "open", "session not found" etc.
    # Without them the model guesses synonyms ("inactive" vs "closed")
    all_strings = set()
    for line in lines:
        # Double-quoted strings (Go, Java, JS, Python, etc.)
        all_strings.update(re.findall(r'"([^"]{1,60})"', line))
        # Single-quoted strings (Python, Ruby, etc.)
        all_strings.update(re.findall(r"'([^']{1,60})'", line))
    # Remove empty strings and pure whitespace
    hints['strings'] = sorted(s for s in all_strings if s.strip())[:20]

    # Extract type signatures — "Name Type `tag`" patterns
    # Catches struct field types: Items interface{}, Total int64, etc.
    # Language-agnostic: looks for "word type" or "word []type" or "word *type"
    type_sigs = []
    for line in lines:
        stripped = line.strip()
        # Struct field pattern: FieldName Type (with optional pointer/slice/map)
        m = re.match(
            r'([A-Z]\w+)\s+'
            r'((?:\[\]|\*|map\[[\w.]+\])?[\w.*\[\]{}]+)'
            r'(?:\s+`.*`)?$', stripped)
        if m:
            type_sigs.append(f"{m.group(1)} {m.group(2)}")
    hints['type_sigs'] = type_sigs[:20]

    # Still extract structured hints for backward compatibility
    for line in lines:
        stripped = line.strip()

        # Functions (universal patterns)
        m = re.match(
            r'(?:pub\s+)?(?:async\s+)?(?:static\s+)?'
            r'(?:def|func|fn|function|fun|sub|proc)\s+'
            r'([a-zA-Z_]\w*)', stripped)
        if m:
            hints['functions'].append(m.group(1))
            continue

        # Methods with receiver (Go: func (x *T) Name())
        m = re.match(r'func\s*\([^)]+\)\s+([a-zA-Z_]\w*)', stripped)
        if m and m.group(1) not in hints['functions']:
            hints['functions'].append(m.group(1))
            continue

        # Classes/structs/types (starts with uppercase)
        m = re.match(
            r'(?:pub\s+)?(?:data\s+|sealed\s+|abstract\s+)?'
            r'(?:class|struct|enum|interface|trait|type)\s+'
            r'([A-Z]\w*)', stripped)
        if m:
            hints['classes'].append(m.group(1))
            continue

        # Imports
        if stripped.startswith(('import ', 'from ', '#include', 'use ', 'require')):
            hints['imports'].append(stripped[:80])
            continue

        # Variable assignments (universal: let/const/var/val/mut + Go := )
        m = re.match(
            r'(?:let|const|var|val|mut)\s+([a-zA-Z_]\w*)', stripped)
        if m:
            hints['variables'].append(m.group(1))
        else:
            # Go short assignment: name :=
            m = re.match(r'([a-zA-Z_]\w*)\s*:=', stripped)
            if m:
                hints['variables'].append(m.group(1))

    return hints


def extract_all_ast_hints(cubes: list[Cube]) -> dict[str, dict]:
    """Extract AST hints for all cubes. Returns {cube_id: hints}."""
    return {cube.id: extract_ast_hints(cube) for cube in cubes}


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



# Ensure sub-modules can find us and our siblings
_CUBE_DIR = os.path.dirname(os.path.abspath(__file__))
if _CUBE_DIR not in sys.path:
    sys.path.insert(0, _CUBE_DIR)
sys.modules.setdefault('cube', sys.modules[__name__])

# ─── Re-export from sub-modules ─────────────────────────────────────
from cube_providers import *  # noqa: F401,F403
from cube_analysis import *   # noqa: F401,F403
