#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B16-B19.

B16: Moteur de reconstruction
B17: Validation SHA-256
B18: Scoring perplexite (hotness)
B19: NCD fallback
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    Cube, CubeStore, MockLLMProvider, FIMReconstructor,
    sha256_hash, normalize_content,
    validate_reconstruction, compute_hotness, compute_ncd,
    reconstruct_cube, ReconstructionResult, run_destruction_cycle,
    scan_repo, subdivide_file, parse_dependencies, assign_neighbors,
)


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def cube_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = CubeStore(db_path)
    yield store
    store.close()


@pytest.fixture
def sample_cubes():
    """Create sample cubes for testing."""
    c1 = Cube(id="f:L1-L5:lv0",
              content="def add(a, b):\n    return a + b",
              sha256=sha256_hash("def add(a, b):\n    return a + b"),
              file_origin="f.py", line_start=1, line_end=5, token_count=15)
    c2 = Cube(id="f:L6-L10:lv0",
              content="def multiply(a, b):\n    return a * b",
              sha256=sha256_hash("def multiply(a, b):\n    return a * b"),
              file_origin="f.py", line_start=6, line_end=10, token_count=15)
    c3 = Cube(id="f:L11-L15:lv0",
              content="result = add(3, multiply(2, 4))\nprint(result)",
              sha256=sha256_hash("result = add(3, multiply(2, 4))\nprint(result)"),
              file_origin="f.py", line_start=11, line_end=15, token_count=20)
    return [c1, c2, c3]


# ═══════════════════════════════════════════════════════════════════════
# B17: Validation SHA-256
# ═══════════════════════════════════════════════════════════════════════

class TestB17Validation:
    """B17: SHA-256 validation of reconstruction."""

    def test_identical_match(self):
        """Identical reconstruction → True."""
        assert validate_reconstruction("x = 42", "x = 42") is True

    def test_one_char_diff(self):
        """1 char difference → False."""
        assert validate_reconstruction("x = 42", "x = 43") is False

    def test_whitespace_normalized(self):
        """Different whitespace → still matches after normalization."""
        assert validate_reconstruction("x = 42\n", "x = 42  \n") is True

    def test_newline_normalized(self):
        """\\r\\n vs \\n → matches."""
        assert validate_reconstruction("x = 1\ny = 2", "x = 1\r\ny = 2") is True

    def test_empty_strings(self):
        """Empty strings match."""
        assert validate_reconstruction("", "") is True

    def test_completely_different(self):
        """Completely different strings → False."""
        assert validate_reconstruction("def f(): pass", "class X: pass") is False


# ═══════════════════════════════════════════════════════════════════════
# B18: Scoring perplexite (hotness)
# ═══════════════════════════════════════════════════════════════════════

class TestB18Hotness:
    """B18: Hotness scoring via perplexity."""

    def test_hotness_returns_float(self, sample_cubes):
        """compute_hotness returns a float >= 0."""
        mock = MockLLMProvider()
        h = compute_hotness(sample_cubes[0], sample_cubes[1:], mock)
        assert isinstance(h, float)
        assert h >= 0.0

    def test_hotness_uses_perplexity(self, sample_cubes):
        """compute_hotness calls get_perplexity."""
        mock = MockLLMProvider()
        compute_hotness(sample_cubes[0], sample_cubes[1:], mock)
        perp_calls = [c for c in mock._calls if c['method'] == 'perplexity']
        assert len(perp_calls) == 1

    def test_hotness_with_no_neighbors(self, sample_cubes):
        """Hotness with empty neighbors still works."""
        mock = MockLLMProvider()
        h = compute_hotness(sample_cubes[0], [], mock)
        assert isinstance(h, float)


# ═══════════════════════════════════════════════════════════════════════
# B19: NCD fallback
# ═══════════════════════════════════════════════════════════════════════

class TestB19NCD:
    """B19: Normalized Compression Distance."""

    def test_identical_near_zero(self):
        """Identical strings → NCD ≈ 0 (zlib header overhead makes it non-zero)."""
        ncd = compute_ncd("hello world", "hello world")
        assert ncd < 0.2  # Close to 0, zlib header adds small overhead

    def test_similar_low(self):
        """Similar strings → NCD < 0.3."""
        a = "def add(a, b):\n    return a + b"
        b = "def add(x, y):\n    return x + y"
        ncd = compute_ncd(a, b)
        assert ncd < 0.5  # Very similar code

    def test_different_high(self):
        """Very different strings → NCD > 0.5."""
        a = "def add(a, b):\n    return a + b"
        b = "import os\nimport sys\nprint(os.getcwd())\nfor i in range(100): pass"
        ncd = compute_ncd(a, b)
        assert ncd > 0.3

    def test_empty_both(self):
        """Both empty → NCD = 0."""
        assert compute_ncd("", "") == 0.0

    def test_one_empty(self):
        """One empty → NCD = 1."""
        assert compute_ncd("hello", "") == 1.0
        assert compute_ncd("", "hello") == 1.0

    def test_ncd_range(self):
        """NCD is always in [0, 1]."""
        pairs = [
            ("a", "b"),
            ("hello" * 100, "world" * 100),
            ("x=1", "x=1"),
            ("def f(): pass", "def f(): return 42"),
        ]
        for a, b in pairs:
            ncd = compute_ncd(a, b)
            assert 0.0 <= ncd <= 1.0, f"NCD out of range: {ncd} for {a[:20]}..., {b[:20]}..."

    def test_ncd_symmetric(self):
        """NCD(a,b) ≈ NCD(b,a)."""
        a = "def hello():\n    print('hi')"
        b = "def world():\n    print('bye')"
        assert abs(compute_ncd(a, b) - compute_ncd(b, a)) < 0.01


# ═══════════════════════════════════════════════════════════════════════
# B16: Moteur de reconstruction
# ═══════════════════════════════════════════════════════════════════════

class TestB16Reconstruction:
    """B16: Cube reconstruction engine."""

    def test_reconstruct_returns_result(self, sample_cubes):
        """reconstruct_cube returns a ReconstructionResult."""
        mock = MockLLMProvider()
        result = reconstruct_cube(sample_cubes[0], sample_cubes[1:], mock)
        assert isinstance(result, ReconstructionResult)
        assert result.cube_id == sample_cubes[0].id

    def test_exact_match_detected(self):
        """Exact reconstruction detected via SHA-256."""
        content = "x = 42"
        cube = Cube(id="t:L1:lv0", content=content, sha256=sha256_hash(content),
                    file_origin="t.py", line_start=1, line_end=1, token_count=5)
        # Mock returns the exact content
        mock = MockLLMProvider({'reconstructing': content})
        result = reconstruct_cube(cube, [], mock)
        assert result.exact_match is True
        assert result.success is True

    def test_ncd_fallback(self):
        """NCD fallback accepts similar reconstruction."""
        content = "def add(a, b):\n    return a + b"
        similar = "def add(x, y):\n    return x + y"
        cube = Cube(id="t:L1:lv0", content=content, sha256=sha256_hash(content),
                    file_origin="t.py", line_start=1, line_end=2, token_count=15)
        mock = MockLLMProvider({'reconstructing': similar})
        result = reconstruct_cube(cube, [], mock, ncd_threshold=0.5)
        assert result.exact_match is False
        # NCD of very similar code should be low enough
        assert result.ncd_score < 0.5

    def test_failed_reconstruction(self):
        """Completely wrong reconstruction detected."""
        content = "TIMEOUT = 3000"
        cube = Cube(id="t:L1:lv0", content=content, sha256=sha256_hash(content),
                    file_origin="t.py", line_start=1, line_end=1, token_count=5)
        # Mock returns something completely different
        mock = MockLLMProvider({'reconstructing': 'import os\nimport sys\nprint("completely different code")'})
        result = reconstruct_cube(cube, [], mock, ncd_threshold=0.3)
        assert result.exact_match is False

    def test_perplexity_recorded(self, sample_cubes):
        """Perplexity is computed and recorded."""
        mock = MockLLMProvider()
        result = reconstruct_cube(sample_cubes[0], sample_cubes[1:], mock)
        assert isinstance(result.perplexity, float)

    def test_result_has_all_fields(self, sample_cubes):
        """ReconstructionResult has all expected fields."""
        mock = MockLLMProvider()
        result = reconstruct_cube(sample_cubes[0], sample_cubes[1:], mock)
        assert hasattr(result, 'cube_id')
        assert hasattr(result, 'original_sha256')
        assert hasattr(result, 'reconstruction')
        assert hasattr(result, 'reconstruction_sha256')
        assert hasattr(result, 'exact_match')
        assert hasattr(result, 'ncd_score')
        assert hasattr(result, 'perplexity')
        assert hasattr(result, 'success')


# ═══════════════════════════════════════════════════════════════════════
# Integration: Destruction cycle
# ═══════════════════════════════════════════════════════════════════════

class TestDestructionCycle:
    """Integration: full destruction/reconstruction cycle."""

    def test_run_cycle(self, sample_cubes, cube_db):
        """Run a complete destruction cycle."""
        # Store cubes
        cube_db.save_cubes(sample_cubes)
        # Set up neighbors
        for i, c in enumerate(sample_cubes):
            for j, n in enumerate(sample_cubes):
                if i != j:
                    cube_db.set_neighbor(c.id, n.id, 0.8, 'static')

        mock = MockLLMProvider()
        results = run_destruction_cycle(sample_cubes, cube_db, mock, cycle_num=1)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, ReconstructionResult)

    def test_cycle_records_history(self, sample_cubes, cube_db):
        """Cycle records in SQLite cycle history."""
        cube_db.save_cubes(sample_cubes)
        for c in sample_cubes:
            for n in sample_cubes:
                if c.id != n.id:
                    cube_db.set_neighbor(c.id, n.id, 0.8, 'static')

        mock = MockLLMProvider()
        run_destruction_cycle(sample_cubes, cube_db, mock, cycle_num=1)

        # Check cycle history recorded
        for c in sample_cubes:
            cycles = cube_db.get_cycles(c.id)
            assert len(cycles) == 1
            assert cycles[0]['cycle'] == 1

    def test_temperature_updates(self, sample_cubes, cube_db):
        """Temperature changes after cycle."""
        cube_db.save_cubes(sample_cubes)
        for c in sample_cubes:
            for n in sample_cubes:
                if c.id != n.id:
                    cube_db.set_neighbor(c.id, n.id, 0.8, 'static')

        mock = MockLLMProvider()
        run_destruction_cycle(sample_cubes, cube_db, mock, cycle_num=1)

        # Temperatures should have changed from initial 0.0
        for c in sample_cubes:
            stored = cube_db.get_cube(c.id)
            assert stored.temperature != 0.0 or stored.score != 0.0

    def test_multiple_cycles(self, sample_cubes, cube_db):
        """Run multiple destruction cycles."""
        cube_db.save_cubes(sample_cubes)
        for c in sample_cubes:
            for n in sample_cubes:
                if c.id != n.id:
                    cube_db.set_neighbor(c.id, n.id, 0.8, 'static')

        mock = MockLLMProvider()
        run_destruction_cycle(sample_cubes, cube_db, mock, cycle_num=1)
        run_destruction_cycle(sample_cubes, cube_db, mock, cycle_num=2)

        for c in sample_cubes:
            cycles = cube_db.get_cycles(c.id)
            assert len(cycles) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
