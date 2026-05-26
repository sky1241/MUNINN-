#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B27-B31.

B27: Remontee par niveaux (88→704→5632)
B28: Agregation des scores entre niveaux
B29: Feed resultats → mycelium
B30: Hebbian update
B31: Git blame crossover
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    Cube, CubeStore, Dependency, ReconstructionResult,
    sha256_hash, subdivide_file,
    build_level_cubes, aggregate_scores, propagate_levels,
    feed_mycelium_from_results, _extract_concepts,
    hebbian_update,
    git_blame_cube, git_log_value,
)


@pytest.fixture
def cube_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = CubeStore(db_path)
    yield store
    store.close()


def _make_cube(cid, content="x=1", file_origin="f.py", line_start=1, line_end=2, temp=0.0):
    return Cube(id=cid, content=content, sha256=sha256_hash(content),
                file_origin=file_origin, line_start=line_start, line_end=line_end,
                temperature=temp, token_count=5)


# ═══════════════════════════════════════════════════════════════════════
# B27: Remontee par niveaux
# ═══════════════════════════════════════════════════════════════════════

class TestB27Levels:
    def test_build_level1(self):
        """8 level-0 cubes → 1 level-1 cube."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(8)]
        upper = build_level_cubes(cubes, level=1, group_size=8)
        assert len(upper) == 1
        assert upper[0].level == 1

    def test_build_level1_partial(self):
        """5 level-0 cubes → 1 level-1 cube (partial group)."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(5)]
        upper = build_level_cubes(cubes, level=1, group_size=8)
        assert len(upper) == 1

    def test_build_level1_multiple_groups(self):
        """16 cubes → 2 level-1 cubes."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(16)]
        upper = build_level_cubes(cubes, level=1, group_size=8)
        assert len(upper) == 2

    def test_multi_file(self):
        """Cubes from different files grouped separately."""
        cubes = (
            [_make_cube(f"a:L{i}:lv0", f"a{i}", "a.py", i, i+1) for i in range(8)] +
            [_make_cube(f"b:L{i}:lv0", f"b{i}", "b.py", i, i+1) for i in range(4)]
        )
        upper = build_level_cubes(cubes, level=1, group_size=8)
        assert len(upper) == 2  # 1 from a.py, 1 from b.py

    def test_level_id_correct(self):
        """Upper cubes have correct level in their ID."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(8)]
        upper = build_level_cubes(cubes, level=2, group_size=8)
        assert all(':lv2' in c.id for c in upper)

    def test_sha256_set(self):
        """Upper cubes have valid SHA-256."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(8)]
        upper = build_level_cubes(cubes, level=1)
        for c in upper:
            assert len(c.sha256) == 64

    def test_empty_input(self):
        """Empty input → empty output."""
        assert build_level_cubes([], level=1) == []


# ═══════════════════════════════════════════════════════════════════════
# B28: Agregation des scores
# ═══════════════════════════════════════════════════════════════════════

class TestB28Aggregation:
    def test_max_propagates(self):
        """Hottest sub-cube determines upper cube score."""
        sub = [_make_cube(f"c{i}", temp=i * 0.1) for i in range(5)]
        upper = _make_cube("u1")
        score = aggregate_scores(upper, sub)
        assert score == 0.4  # Max of [0.0, 0.1, 0.2, 0.3, 0.4]

    def test_empty_sub(self):
        """Empty sub-cubes → 0 score."""
        assert aggregate_scores(_make_cube("u1"), []) == 0.0

    def test_all_cold(self):
        """All cold sub-cubes → 0 score."""
        sub = [_make_cube(f"c{i}", temp=0.0) for i in range(8)]
        assert aggregate_scores(_make_cube("u1"), sub) == 0.0

    def test_one_hot(self):
        """One hot sub-cube makes upper hot."""
        sub = [_make_cube(f"c{i}", temp=0.0) for i in range(7)]
        sub.append(_make_cube("hot", temp=0.9))
        score = aggregate_scores(_make_cube("u1"), sub)
        assert score == 0.9

    def test_propagate_levels(self, cube_db):
        """propagate_levels builds multi-level hierarchy."""
        cubes = [_make_cube(f"f:L{i}:lv0", f"x={i}", "f.py", i, i+1) for i in range(24)]
        for c in cubes:
            c.temperature = 0.3
        cubes[0].temperature = 0.9  # One hot cube
        cube_db.save_cubes(cubes)

        levels = propagate_levels(cubes, cube_db, max_level=2)
        assert 0 in levels
        assert 1 in levels
        assert len(levels[0]) == 24
        assert len(levels[1]) > 0
        # Hot cube should propagate
        assert any(c.temperature >= 0.9 for c in levels[1])


# ═══════════════════════════════════════════════════════════════════════
# B29: Feed mycelium
# ═══════════════════════════════════════════════════════════════════════

class TestB29FeedMycelium:
    def test_extract_concepts(self):
        """Extract function/class names from code."""
        code = "def add(a, b):\n    return a + b\nclass User:\n    pass"
        concepts = _extract_concepts(code)
        assert 'add' in concepts
        assert 'User' in concepts

    def test_extract_imports(self):
        """Extract import names."""
        code = "import os\nfrom collections import defaultdict"
        concepts = _extract_concepts(code)
        assert 'os' in concepts
        assert 'collections' in concepts

    def test_feed_returns_pairs(self):
        """feed_mycelium_from_results returns mechanical pairs."""
        cubes = [
            Cube(id="a", content="def f(): pass", sha256="h1", file_origin="f.py",
                 line_start=1, line_end=1, neighbors=["b"]),
            Cube(id="b", content="def g(): pass", sha256="h2", file_origin="f.py",
                 line_start=2, line_end=2, neighbors=["a"]),
        ]
        results = [
            ReconstructionResult(cube_id="a", original_sha256="h1",
                                reconstruction="def f(): pass", reconstruction_sha256="h1",
                                exact_match=True, ncd_score=0.0, perplexity=0.5,
                                success=True)
        ]
        pairs = feed_mycelium_from_results(results, cubes, mycelium=None)
        assert len(pairs) == 1
        assert pairs[0]['type'] == 'mechanical'
        assert pairs[0]['weight'] == 1.0

    def test_failed_gets_negative_weight(self):
        """Failed reconstruction → negative weight."""
        cubes = [
            Cube(id="a", content="x=1", sha256="h1", file_origin="f.py",
                 line_start=1, line_end=1, neighbors=["b"]),
            Cube(id="b", content="y=2", sha256="h2", file_origin="f.py",
                 line_start=2, line_end=2),
        ]
        results = [
            ReconstructionResult(cube_id="a", original_sha256="h1",
                                reconstruction="wrong", reconstruction_sha256="bad",
                                exact_match=False, ncd_score=0.8, perplexity=3.0,
                                success=False)
        ]
        pairs = feed_mycelium_from_results(results, cubes)
        assert pairs[0]['weight'] == -0.5

    def test_no_mycelium_graceful(self):
        """Works without mycelium (returns pairs but doesn't crash)."""
        cubes = [_make_cube("a")]
        cubes[0].neighbors = []
        results = [ReconstructionResult("a", "h", "", "h2", False, 0.5, 1.0, False)]
        pairs = feed_mycelium_from_results(results, cubes, mycelium=None)
        assert isinstance(pairs, list)


# ═══════════════════════════════════════════════════════════════════════
# B30: Hebbian update
# ═══════════════════════════════════════════════════════════════════════

class TestB30Hebbian:
    def test_success_strengthens(self, cube_db):
        """Successful reconstruction strengthens neighbor weights."""
        cube_db.save_cube(_make_cube("a"))
        cube_db.save_cube(_make_cube("b"))
        cube_db.set_neighbor("a", "b", 0.5, "static")

        results = [ReconstructionResult("a", "h", "", "h", True, 0.0, 0.5, True)]
        hebbian_update(cube_db, results, learning_rate=0.1)

        neighbors = cube_db.get_neighbors("a")
        assert neighbors[0][1] == pytest.approx(0.6, abs=0.01)

    def test_failure_weakens(self, cube_db):
        """Failed reconstruction weakens neighbor weights."""
        cube_db.save_cube(_make_cube("a"))
        cube_db.save_cube(_make_cube("b"))
        cube_db.set_neighbor("a", "b", 0.5, "static")

        results = [ReconstructionResult("a", "h", "", "h2", False, 0.8, 3.0, False)]
        hebbian_update(cube_db, results, learning_rate=0.1)

        neighbors = cube_db.get_neighbors("a")
        assert neighbors[0][1] == pytest.approx(0.45, abs=0.01)

    def test_weight_bounds(self, cube_db):
        """Weights stay in [0.1, 2.0]."""
        cube_db.save_cube(_make_cube("a"))
        cube_db.save_cube(_make_cube("b"))
        cube_db.set_neighbor("a", "b", 1.9, "static")

        # Many successes
        for _ in range(20):
            results = [ReconstructionResult("a", "h", "", "h", True, 0.0, 0.5, True)]
            hebbian_update(cube_db, results, learning_rate=0.1)

        neighbors = cube_db.get_neighbors("a")
        assert neighbors[0][1] <= 2.0

    def test_type_changes_to_mechanical(self, cube_db):
        """Static neighbors become mechanical after Hebbian update."""
        cube_db.save_cube(_make_cube("a"))
        cube_db.save_cube(_make_cube("b"))
        cube_db.set_neighbor("a", "b", 0.5, "static")

        results = [ReconstructionResult("a", "h", "", "h", True, 0.0, 0.5, True)]
        hebbian_update(cube_db, results)

        neighbors = cube_db.get_neighbors("a")
        assert neighbors[0][2] == "mechanical"


# ═══════════════════════════════════════════════════════════════════════
# B31: Git blame
# ═══════════════════════════════════════════════════════════════════════

class TestB31GitBlame:
    def test_blame_on_real_file(self):
        """Git blame on actual repo file."""
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cube = _make_cube("c1", "x=1", "engine/core/tokenizer.py", 1, 5)
        result = git_blame_cube(cube, repo_path)
        if 'error' not in result:
            assert 'commits' in result
            assert result['cube_id'] == "c1"
        # May fail in CI where git is not available — that's OK

    def test_blame_nonexistent_file(self):
        """Git blame on missing file returns error."""
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cube = _make_cube("c1", "x=1", "nonexistent_file.py", 1, 5)
        result = git_blame_cube(cube, repo_path)
        assert 'error' in result

    def test_log_value(self):
        """Git log for a file returns entries or empty list."""
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cube = _make_cube("c1", "x=1", "engine/core/tokenizer.py", 1, 5)
        entries = git_log_value(cube, repo_path)
        assert isinstance(entries, list)


# ═══════════════════════════════════════════════════════════════════════
# Integration B27-B31
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB27B31:
    def test_levels_plus_hebbian(self, cube_db):
        """Build levels → run cycle → Hebbian update → levels propagate."""
        # Create cubes
        cubes = [_make_cube(f"f:L{i}:lv0", f"val_{i}={i*7}", "f.py", i, i+1)
                 for i in range(16)]
        cube_db.save_cubes(cubes)

        # Set neighbors (both in store and on cube objects)
        for i, c in enumerate(cubes):
            c.neighbors = []
            for j in range(max(0, i-2), min(len(cubes), i+3)):
                if i != j:
                    cube_db.set_neighbor(c.id, cubes[j].id, 0.5, 'static')
                    c.neighbors.append(cubes[j].id)

        # Simulate results
        results = []
        for i, c in enumerate(cubes):
            success = i % 3 != 0  # Every 3rd cube fails
            results.append(ReconstructionResult(
                cube_id=c.id, original_sha256=c.sha256,
                reconstruction=c.content if success else "wrong",
                reconstruction_sha256=c.sha256 if success else "bad",
                exact_match=success, ncd_score=0.0 if success else 0.8,
                perplexity=0.5 if success else 3.0, success=success,
            ))
            if not success:
                c.temperature = 0.8
            else:
                c.temperature = 0.1

        # B30: Hebbian
        hebbian_update(cube_db, results)

        # B29: Feed
        pairs = feed_mycelium_from_results(results, cubes)
        assert len(pairs) > 0

        # B27+B28: Levels
        levels = propagate_levels(cubes, cube_db, max_level=2)
        assert len(levels[1]) > 0
        # Hot cubes should propagate
        assert any(c.temperature > 0.5 for c in levels[1])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
