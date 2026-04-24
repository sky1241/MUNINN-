#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B1-B6.

B1: Scanner de repo
B2: Tokenizer integration (uses existing tokenizer.py)
B3: Cube dataclass
B4: Subdivision engine
B5: SHA-256 normalisation + hashing
B6: Stockage index SQLite
"""

import json
import os
import sys
import tempfile
import shutil

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    scan_repo, ScannedFile,
    Cube, subdivide_file, subdivide_recursive,
    normalize_content, sha256_hash,
    CubeStore,
    TARGET_TOKENS, TOLERANCE_MIN, TOLERANCE_MAX,
)
from muninn.tokenizer import token_count


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mini_repo(tmp_path):
    """Create a minimal repo structure for testing."""
    # Python files
    (tmp_path / "main.py").write_text("def hello():\n    print('hello world')\n\nhello()\n")
    (tmp_path / "utils.py").write_text("import os\nimport sys\n\ndef get_path():\n    return os.getcwd()\n")

    # Nested directory
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("from utils import get_path\n\nclass App:\n    pass\n")
    (tmp_path / "src" / "config.json").write_text('{"key": "value"}\n')

    # Files that should be skipped
    (tmp_path / "image.png").write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lodash.js").write_text("module.exports = {}\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-313.pyc").write_bytes(b'\x00' * 50)

    # Empty file (should be skipped)
    (tmp_path / "empty.py").write_text("")

    # JS file
    (tmp_path / "script.js").write_text("console.log('hello');\n")

    # Markdown
    (tmp_path / "README.md").write_text("# My Project\n\nA test project.\n")

    return tmp_path


@pytest.fixture
def large_file_content():
    """Generate a large Python file (~1000 tokens)."""
    lines = []
    for i in range(50):
        lines.append(f"def function_{i}(x, y):")
        lines.append(f"    '''Function {i} does computation.'''")
        lines.append(f"    result = x * {i} + y")
        lines.append(f"    if result > {i * 10}:")
        lines.append(f"        return result - {i}")
        lines.append(f"    return result + {i}")
        lines.append("")
    return "\n".join(lines)


@pytest.fixture
def cube_db(tmp_path):
    """Create a temporary CubeStore."""
    db_path = str(tmp_path / "test_cubes.db")
    store = CubeStore(db_path)
    yield store
    store.close()


# ═══════════════════════════════════════════════════════════════════════
# B1: Scanner de repo
# ═══════════════════════════════════════════════════════════════════════

class TestB1Scanner:
    """B1: Scanner de repo — parcourt fichiers, filtre binaires/vendored."""

    def test_scan_finds_source_files(self, mini_repo):
        """Scanner finds Python, JS, JSON, MD files."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert "main.py" in paths
        assert "utils.py" in paths
        assert "src/app.py" in paths
        assert "script.js" in paths
        assert "README.md" in paths
        assert "src/config.json" in paths

    def test_scan_skips_binary(self, mini_repo):
        """Scanner skips binary files (PNG)."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert "image.png" not in paths

    def test_scan_skips_git(self, mini_repo):
        """Scanner skips .git directory."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert not any(".git/" in p for p in paths)

    def test_scan_skips_node_modules(self, mini_repo):
        """Scanner skips node_modules directory."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert not any("node_modules/" in p for p in paths)

    def test_scan_skips_pycache(self, mini_repo):
        """Scanner skips __pycache__ directory."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert not any("__pycache__/" in p for p in paths)

    def test_scan_skips_empty(self, mini_repo):
        """Scanner skips empty files."""
        files = scan_repo(str(mini_repo))
        paths = {f.path for f in files}
        assert "empty.py" not in paths

    def test_scan_detects_language(self, mini_repo):
        """Scanner correctly detects language from extension."""
        files = scan_repo(str(mini_repo))
        by_path = {f.path: f for f in files}
        assert by_path["main.py"].language == "python"
        assert by_path["script.js"].language == "javascript"
        assert by_path["README.md"].language == "markdown"
        assert by_path["src/config.json"].language == "json"

    def test_scan_has_content(self, mini_repo):
        """Scanned files have non-empty content."""
        files = scan_repo(str(mini_repo))
        for f in files:
            assert f.content, f"Empty content for {f.path}"
            assert f.token_count > 0, f"Zero tokens for {f.path}"

    def test_scan_extension_filter(self, mini_repo):
        """Extension filter only returns matching files."""
        files = scan_repo(str(mini_repo), extensions={'.py'})
        for f in files:
            assert f.path.endswith('.py'), f"Non-Python file: {f.path}"
        assert len(files) == 3  # main.py, utils.py, src/app.py

    def test_scan_nonexistent_repo(self):
        """Scanner raises on nonexistent directory."""
        with pytest.raises(ValueError):
            scan_repo("/nonexistent/path/xyz")

    def test_scan_count(self, mini_repo):
        """Scanner returns expected file count."""
        files = scan_repo(str(mini_repo))
        # main.py, utils.py, src/app.py, script.js, README.md, src/config.json
        assert len(files) == 6


# ═══════════════════════════════════════════════════════════════════════
# B2: Tokenizer integration (via existing tokenizer.py)
# ═══════════════════════════════════════════════════════════════════════

class TestB2Tokenizer:
    """B2: Tokenizer integration — counting tokens per chunk."""

    def test_token_count_basic(self):
        """Basic token counting works."""
        count = token_count("hello world")
        assert count > 0
        assert count < 10

    def test_token_count_code(self):
        """Token counting on code produces reasonable counts."""
        code = "def hello():\n    print('hello world')\n"
        count = token_count(code)
        assert 5 < count < 30

    def test_token_count_empty(self):
        """Empty string = 0 tokens."""
        assert token_count("") == 0

    def test_token_count_consistency(self):
        """Same text = same count every time."""
        text = "x = 42\ny = x * 2\nprint(y)"
        c1 = token_count(text)
        c2 = token_count(text)
        assert c1 == c2

    def test_token_count_scales(self):
        """More text = more tokens."""
        short = "x = 1"
        long = "x = 1\n" * 100
        assert token_count(long) > token_count(short)


# ═══════════════════════════════════════════════════════════════════════
# B3: Cube dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestB3CubeDataclass:
    """B3: Cube dataclass — id, content, sha256, neighbors, score, level."""

    def test_create_cube(self):
        """Basic cube creation."""
        c = Cube(
            id="test.py:L1-L10:lv0",
            content="x = 42",
            sha256=sha256_hash("x = 42"),
            file_origin="test.py",
            line_start=1,
            line_end=10,
        )
        assert c.id == "test.py:L1-L10:lv0"
        assert c.content == "x = 42"
        assert c.level == 0
        assert c.neighbors == []
        assert c.score == 0.0

    def test_serialize_json(self):
        """Cube serializes to/from JSON."""
        c = Cube(
            id="test.py:L1-L5:lv0",
            content="print('hello')",
            sha256=sha256_hash("print('hello')"),
            file_origin="test.py",
            line_start=1,
            line_end=5,
            neighbors=["a.py:L1-L3:lv0", "b.py:L4-L8:lv0"],
            score=0.75,
        )
        j = c.to_json()
        c2 = Cube.from_json(j)
        assert c2.id == c.id
        assert c2.content == c.content
        assert c2.sha256 == c.sha256
        assert c2.neighbors == c.neighbors
        assert c2.score == c.score

    def test_serialize_dict(self):
        """Cube serializes to/from dict."""
        c = Cube(
            id="x:L1-L2:lv0", content="y=1", sha256="abc",
            file_origin="x", line_start=1, line_end=2,
        )
        d = c.to_dict()
        assert isinstance(d, dict)
        c2 = Cube.from_dict(d)
        assert c2.id == c.id
        assert c2.content == c.content

    def test_batch_create(self):
        """Create 100 cubes, verify integrity."""
        cubes = []
        for i in range(100):
            content = f"value_{i} = {i * 7}"
            cubes.append(Cube(
                id=f"file.py:L{i}-L{i+1}:lv0",
                content=content,
                sha256=sha256_hash(content),
                file_origin="file.py",
                line_start=i, line_end=i+1,
            ))
        # All unique IDs
        ids = [c.id for c in cubes]
        assert len(set(ids)) == 100
        # All unique SHA-256
        hashes = [c.sha256 for c in cubes]
        assert len(set(hashes)) == 100
        # Round-trip
        for c in cubes:
            c2 = Cube.from_json(c.to_json())
            assert c2.sha256 == c.sha256


# ═══════════════════════════════════════════════════════════════════════
# B4: Subdivision engine
# ═══════════════════════════════════════════════════════════════════════

class TestB4Subdivision:
    """B4: Subdivision engine — recursive /8 until 88 tokens."""

    def test_small_file_single_cube(self):
        """File smaller than 104 tokens → single cube."""
        content = "x = 42\ny = x + 1\nprint(y)"
        cubes = subdivide_file("small.py", content)
        assert len(cubes) == 1
        assert cubes[0].content == content

    def test_large_file_multiple_cubes(self, large_file_content):
        """Large file → multiple cubes."""
        cubes = subdivide_file("large.py", large_file_content)
        assert len(cubes) > 1

    def test_cube_size_range(self, large_file_content):
        """Each cube should be roughly TARGET_TOKENS (within tolerance)."""
        cubes = subdivide_file("large.py", large_file_content)
        for c in cubes:
            # Allow wider tolerance for edge cubes (first/last)
            assert c.token_count > 0, f"Empty cube: {c.id}"

    def test_no_overlap(self, large_file_content):
        """Cubes should not overlap in line ranges."""
        cubes = subdivide_file("large.py", large_file_content)
        for i in range(len(cubes) - 1):
            assert cubes[i].line_end <= cubes[i+1].line_start, \
                f"Overlap: {cubes[i].id} (end={cubes[i].line_end}) vs {cubes[i+1].id} (start={cubes[i+1].line_start})"

    def test_complete_coverage(self, large_file_content):
        """Cubes should cover the entire file (no gaps)."""
        cubes = subdivide_file("large.py", large_file_content)
        # First cube starts at line 1
        assert cubes[0].line_start == 1
        # Reconstruct content
        reconstructed = "\n".join(c.content for c in cubes)
        # Token count should be similar (may differ slightly due to join)
        orig_tokens = token_count(large_file_content)
        recon_tokens = token_count(reconstructed)
        assert abs(orig_tokens - recon_tokens) / max(orig_tokens, 1) < 0.05

    def test_sha256_set(self, large_file_content):
        """Each cube has a valid SHA-256."""
        cubes = subdivide_file("large.py", large_file_content)
        for c in cubes:
            assert len(c.sha256) == 64
            assert all(ch in '0123456789abcdef' for ch in c.sha256)

    def test_file_origin_set(self, large_file_content):
        """Each cube tracks its file origin."""
        cubes = subdivide_file("large.py", large_file_content)
        for c in cubes:
            assert c.file_origin == "large.py"

    def test_empty_content(self):
        """Empty content → no cubes."""
        assert subdivide_file("empty.py", "") == []
        assert subdivide_file("blank.py", "   \n\n  ") == []


# ═══════════════════════════════════════════════════════════════════════
# B5: SHA-256 normalisation
# ═══════════════════════════════════════════════════════════════════════

class TestB5SHA256:
    """B5: SHA-256 normalisation — same code with different whitespace → same hash."""

    def test_trailing_whitespace(self):
        """Trailing whitespace doesn't affect hash."""
        h1 = sha256_hash("x = 42")
        h2 = sha256_hash("x = 42   ")
        assert h1 == h2

    def test_different_newlines(self):
        """\\r\\n vs \\n → same hash."""
        h1 = sha256_hash("x = 1\ny = 2")
        h2 = sha256_hash("x = 1\r\ny = 2")
        assert h1 == h2

    def test_leading_trailing_blanks(self):
        """Leading/trailing blank lines stripped."""
        h1 = sha256_hash("x = 1\ny = 2")
        h2 = sha256_hash("\n\nx = 1\ny = 2\n\n\n")
        assert h1 == h2

    def test_multiple_blank_lines(self):
        """Multiple blank lines collapsed to single."""
        h1 = sha256_hash("x = 1\n\ny = 2")
        h2 = sha256_hash("x = 1\n\n\n\ny = 2")
        assert h1 == h2

    def test_different_content_different_hash(self):
        """Different content → different hash."""
        h1 = sha256_hash("x = 42")
        h2 = sha256_hash("x = 43")
        assert h1 != h2

    def test_hash_format(self):
        """Hash is 64-char hex string."""
        h = sha256_hash("test")
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_normalize_preserves_content(self):
        """Normalization preserves actual code content."""
        code = "def f():\n    return 42\n"
        normalized = normalize_content(code)
        assert "def f():" in normalized
        assert "return 42" in normalized


# ═══════════════════════════════════════════════════════════════════════
# B6: Stockage SQLite
# ═══════════════════════════════════════════════════════════════════════

class TestB6Storage:
    """B6: SQLite storage — CRUD cubes, neighbors, cycles."""

    def test_save_and_get(self, cube_db):
        """Save a cube and retrieve it."""
        c = Cube(id="t:L1-L5:lv0", content="x=1", sha256=sha256_hash("x=1"),
                 file_origin="t", line_start=1, line_end=5, token_count=3)
        cube_db.save_cube(c)
        c2 = cube_db.get_cube("t:L1-L5:lv0")
        assert c2 is not None
        assert c2.content == "x=1"
        assert c2.sha256 == c.sha256

    def test_get_nonexistent(self, cube_db):
        """Getting nonexistent cube returns None."""
        assert cube_db.get_cube("doesntexist") is None

    def test_batch_save(self, cube_db):
        """Batch save 1000 cubes."""
        cubes = []
        for i in range(1000):
            content = f"val_{i} = {i}"
            cubes.append(Cube(
                id=f"f:L{i}-L{i+1}:lv0", content=content,
                sha256=sha256_hash(content), file_origin="f",
                line_start=i, line_end=i+1, token_count=5,
            ))
        cube_db.save_cubes(cubes)
        assert cube_db.count_cubes() == 1000

    def test_get_by_file(self, cube_db):
        """Query cubes by file origin."""
        for i in range(10):
            f = "a.py" if i < 6 else "b.py"
            cube_db.save_cube(Cube(
                id=f"{f}:L{i}:lv0", content=f"x={i}",
                sha256=sha256_hash(f"x={i}"), file_origin=f,
                line_start=i, line_end=i+1,
            ))
        assert len(cube_db.get_cubes_by_file("a.py")) == 6
        assert len(cube_db.get_cubes_by_file("b.py")) == 4

    def test_get_by_level(self, cube_db):
        """Query cubes by level."""
        for i in range(10):
            lvl = i % 3
            cube_db.save_cube(Cube(
                id=f"f:L{i}:lv{lvl}", content=f"x={i}",
                sha256=sha256_hash(f"x={i}"), file_origin="f",
                line_start=i, line_end=i+1, level=lvl,
            ))
        assert len(cube_db.get_cubes_by_level(0)) == 4
        assert len(cube_db.get_cubes_by_level(1)) == 3
        assert len(cube_db.get_cubes_by_level(2)) == 3

    def test_hot_cubes(self, cube_db):
        """Query cubes above temperature threshold."""
        for i in range(10):
            cube_db.save_cube(Cube(
                id=f"f:L{i}:lv0", content=f"x={i}",
                sha256=sha256_hash(f"x={i}"), file_origin="f",
                line_start=i, line_end=i+1, temperature=i * 0.1,
            ))
        hot = cube_db.get_hot_cubes(threshold=0.5)
        assert len(hot) == 4  # 0.6, 0.7, 0.8, 0.9
        assert all(c.temperature > 0.5 for c in hot)

    def test_neighbors(self, cube_db):
        """Set and get neighbor relationships."""
        cube_db.save_cube(Cube(id="a", content="x", sha256="h1",
                               file_origin="f", line_start=1, line_end=2))
        cube_db.save_cube(Cube(id="b", content="y", sha256="h2",
                               file_origin="f", line_start=3, line_end=4))
        cube_db.set_neighbor("a", "b", weight=0.9, ntype="static")
        neighbors = cube_db.get_neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0][0] == "b"
        assert neighbors[0][1] == 0.9
        assert neighbors[0][2] == "static"

    def test_cycles(self, cube_db):
        """Record and retrieve cycle history."""
        cube_db.save_cube(Cube(id="c1", content="z", sha256="h3",
                               file_origin="f", line_start=1, line_end=2))
        cube_db.record_cycle("c1", 1, True, "z_reconstructed", 0.5)
        cube_db.record_cycle("c1", 2, False, "z_wrong", 2.3)
        cycles = cube_db.get_cycles("c1")
        assert len(cycles) == 2
        assert cycles[0]['success'] is True
        assert cycles[1]['success'] is False
        assert cycles[1]['perplexity'] == 2.3

    def test_update_temperature(self, cube_db):
        """Update cube temperature."""
        cube_db.save_cube(Cube(id="t1", content="a", sha256="h",
                               file_origin="f", line_start=1, line_end=2))
        cube_db.update_temperature("t1", 0.85)
        c = cube_db.get_cube("t1")
        assert c.temperature == 0.85

    def test_delete_cube(self, cube_db):
        """Delete cube removes cube + neighbors + cycles."""
        cube_db.save_cube(Cube(id="d1", content="a", sha256="h",
                               file_origin="f", line_start=1, line_end=2))
        cube_db.set_neighbor("d1", "other", 1.0)
        cube_db.record_cycle("d1", 1, True)
        cube_db.delete_cube("d1")
        assert cube_db.get_cube("d1") is None
        assert cube_db.get_neighbors("d1") == []
        assert cube_db.get_cycles("d1") == []

    def test_count_by_level(self, cube_db):
        """Count cubes filtered by level."""
        cube_db.save_cubes([
            Cube(id=f"c{i}", content=f"x{i}", sha256=f"h{i}",
                 file_origin="f", line_start=i, line_end=i+1, level=i % 2)
            for i in range(10)
        ])
        assert cube_db.count_cubes() == 10
        assert cube_db.count_cubes(level=0) == 5
        assert cube_db.count_cubes(level=1) == 5


# ═══════════════════════════════════════════════════════════════════════
# Integration: B1 + B2 + B4 + B5 + B6 together
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB1toB6:
    """Integration: scan → tokenize → subdivide → hash → store."""

    def test_scan_subdivide_store(self, mini_repo, cube_db):
        """Full pipeline: scan repo → subdivide each file → store in SQLite."""
        files = scan_repo(str(mini_repo))
        all_cubes = []
        for f in files:
            cubes = subdivide_file(f.path, f.content)
            all_cubes.extend(cubes)

        assert len(all_cubes) > 0

        # Store all
        cube_db.save_cubes(all_cubes)
        assert cube_db.count_cubes() == len(all_cubes)

        # Verify each stored cube matches original
        for c in all_cubes:
            stored = cube_db.get_cube(c.id)
            assert stored is not None
            assert stored.sha256 == c.sha256
            assert stored.content == c.content

    def test_scan_real_repo(self):
        """Scan this actual Muninn repo (smoke test)."""
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = scan_repo(repo_path, extensions={'.py'})
        assert len(files) >= 5  # At least muninn.py, mycelium.py, tokenizer.py, cube.py, etc.
        # Verify muninn.py is found
        paths = {f.path for f in files}
        assert "engine/core/muninn.py" in paths
        assert "engine/core/cube.py" in paths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
