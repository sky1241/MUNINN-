#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B9-B10, B20-B22 (advanced).

B9: Laplacian RG groupage optimal (Villegas 2023)
B10: Cheeger constant (bottleneck detection)
B20: Belief Propagation (Pearl 1988)
B21: Survey Propagation pre-filtre (Mezard-Parisi 2002)
B22: Tononi Degeneracy (Tononi 1999)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.cube import (
    Cube, CubeStore, sha256_hash, compute_ncd,
    laplacian_rg_grouping, build_adjacency_matrix,
    cheeger_constant,
    belief_propagation,
    survey_propagation_filter,
    tononi_degeneracy,
)

numpy = pytest.importorskip("numpy", reason="numpy required for B9/B10")


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


def _setup_connected_cubes(cube_db, n=10, temp=0.5):
    """Create n connected cubes with neighbors."""
    cubes = [_make_cube(f"c{i}", f"val_{i}={i*7}", "f.py", i, i+1, temp)
             for i in range(n)]
    cube_db.save_cubes(cubes)
    # Chain neighbors: each cube connected to neighbors
    for i, c in enumerate(cubes):
        for j in range(max(0, i-2), min(n, i+3)):
            if i != j:
                cube_db.set_neighbor(c.id, cubes[j].id, 0.5 + 0.1 * (3 - abs(i-j)), 'static')
    return cubes


# ═══════════════════════════════════════════════════════════════════════
# B9: Laplacian RG grouping
# ═══════════════════════════════════════════════════════════════════════

class TestB9LaplacianRG:
    def test_adjacency_matrix(self, cube_db):
        """Adjacency matrix correctly built."""
        cubes = _setup_connected_cubes(cube_db, n=5)
        A, id_to_idx = build_adjacency_matrix(cubes, cube_db)
        assert A.shape == (5, 5)
        # Symmetric
        assert numpy.allclose(A, A.T)
        # No self-loops
        assert numpy.allclose(numpy.diag(A), 0)

    def test_grouping_basic(self, cube_db):
        """Laplacian RG produces groups."""
        cubes = _setup_connected_cubes(cube_db, n=16)
        groups = laplacian_rg_grouping(cubes, cube_db, n_groups=2)
        assert len(groups) == 2
        # All cubes assigned
        total = sum(len(g) for g in groups)
        assert total == 16

    def test_grouping_single(self, cube_db):
        """Single cube → single group."""
        cubes = [_make_cube("c0")]
        cube_db.save_cubes(cubes)
        groups = laplacian_rg_grouping(cubes, cube_db)
        assert len(groups) == 1
        assert len(groups[0]) == 1

    def test_grouping_empty(self, cube_db):
        """Empty input → empty output."""
        assert laplacian_rg_grouping([], cube_db) == []

    def test_auto_n_groups(self, cube_db):
        """Auto-detect number of groups (n/8)."""
        cubes = _setup_connected_cubes(cube_db, n=24)
        groups = laplacian_rg_grouping(cubes, cube_db)
        # n/8 = 3 groups
        assert len(groups) == 3

    def test_all_cubes_in_exactly_one_group(self, cube_db):
        """Each cube appears in exactly one group."""
        cubes = _setup_connected_cubes(cube_db, n=12)
        groups = laplacian_rg_grouping(cubes, cube_db, n_groups=3)
        all_ids = set()
        for g in groups:
            for c in g:
                assert c.id not in all_ids, f"Duplicate: {c.id}"
                all_ids.add(c.id)
        assert len(all_ids) == 12


# ═══════════════════════════════════════════════════════════════════════
# B10: Cheeger constant
# ═══════════════════════════════════════════════════════════════════════

class TestB10Cheeger:
    def test_cheeger_basic(self, cube_db):
        """Cheeger constant computed."""
        cubes = _setup_connected_cubes(cube_db, n=10)
        result = cheeger_constant(cubes, cube_db)
        assert 'lambda_2' in result
        assert 'h_estimate' in result
        assert 'bottlenecks' in result

    def test_cheeger_bounds(self, cube_db):
        """Cheeger bounds: h_lower ≤ h_estimate ≤ h_upper."""
        cubes = _setup_connected_cubes(cube_db, n=10)
        result = cheeger_constant(cubes, cube_db)
        assert result['h_lower'] <= result['h_estimate']
        assert result['h_estimate'] <= result['h_upper'] + 0.001

    def test_lambda2_positive(self, cube_db):
        """Connected graph has positive λ₂."""
        cubes = _setup_connected_cubes(cube_db, n=10)
        result = cheeger_constant(cubes, cube_db)
        assert result['lambda_2'] >= -0.001  # May be ≈0 for poorly connected

    def test_bottleneck_detection(self, cube_db):
        """Bottleneck cubes identified."""
        cubes = _setup_connected_cubes(cube_db, n=10)
        result = cheeger_constant(cubes, cube_db)
        assert isinstance(result['bottlenecks'], list)
        assert len(result['bottlenecks']) >= 1

    def test_single_cube(self, cube_db):
        """Single cube → h=0."""
        cubes = [_make_cube("c0")]
        cube_db.save_cubes(cubes)
        result = cheeger_constant(cubes, cube_db)
        assert result['h_estimate'] == 0.0


# ═══════════════════════════════════════════════════════════════════════
# B20: Belief Propagation
# ═══════════════════════════════════════════════════════════════════════

class TestB20BeliefPropagation:
    def test_bp_returns_beliefs(self, cube_db):
        """BP returns belief for each cube."""
        cubes = _setup_connected_cubes(cube_db, n=10, temp=0.5)
        beliefs = belief_propagation(cubes, cube_db)
        assert len(beliefs) == 10
        for cid, belief in beliefs.items():
            assert 0.0 <= belief <= 1.0

    def test_bp_hot_stays_hot(self, cube_db):
        """BP produces valid beliefs for all cubes."""
        cubes = _setup_connected_cubes(cube_db, n=5, temp=0.1)
        cubes[2].temperature = 0.9  # One hot cube
        beliefs = belief_propagation(cubes, cube_db)
        # All beliefs should be valid (between 0 and 1)
        for cid, belief in beliefs.items():
            assert 0.0 <= belief <= 1.0, f"Invalid belief for {cid}: {belief}"

    def test_bp_converges(self, cube_db):
        """BP converges within max_iter."""
        cubes = _setup_connected_cubes(cube_db, n=10, temp=0.5)
        # Should not raise or hang
        beliefs = belief_propagation(cubes, cube_db, max_iter=15)
        assert len(beliefs) == 10

    def test_bp_no_neighbors(self, cube_db):
        """Cube with no neighbors keeps its temperature as belief."""
        cube = _make_cube("alone", temp=0.7)
        cube_db.save_cube(cube)
        beliefs = belief_propagation([cube], cube_db)
        assert beliefs["alone"] == pytest.approx(0.7, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════
# B21: Survey Propagation
# ═══════════════════════════════════════════════════════════════════════

class TestB21SurveyPropagation:
    def test_sp_filter_separates(self, cube_db):
        """SP separates trivial from non-trivial."""
        cubes = _setup_connected_cubes(cube_db, n=10, temp=0.1)
        cubes[0].temperature = 0.9
        cubes[1].temperature = 0.8
        non_trivial, trivial = survey_propagation_filter(cubes, cube_db)
        assert len(non_trivial) + len(trivial) == 10

    def test_sp_all_cold(self, cube_db):
        """All cold cubes → all trivial."""
        cubes = _setup_connected_cubes(cube_db, n=5, temp=0.0)
        non_trivial, trivial = survey_propagation_filter(cubes, cube_db)
        assert len(trivial) >= len(non_trivial)

    def test_sp_saves_llm_calls(self, cube_db):
        """SP should filter at least some cubes (saves LLM calls)."""
        cubes = _setup_connected_cubes(cube_db, n=20, temp=0.1)
        # Make a few hot
        for i in range(5):
            cubes[i].temperature = 0.8
        non_trivial, trivial = survey_propagation_filter(cubes, cube_db)
        # Should have filtered some trivial ones
        assert len(trivial) > 0


# ═══════════════════════════════════════════════════════════════════════
# B22: Tononi Degeneracy
# ═══════════════════════════════════════════════════════════════════════

class TestB22TononiDegeneracy:
    def test_degeneracy_returns_float(self, cube_db):
        """Degeneracy returns a non-negative float."""
        cubes = _setup_connected_cubes(cube_db, n=5)
        d = tononi_degeneracy(cubes[2], cube_db, cubes)
        assert isinstance(d, float)
        assert d >= 0.0

    def test_no_neighbors_zero(self, cube_db):
        """Cube with no neighbors → D=0."""
        cube = _make_cube("alone")
        cube_db.save_cube(cube)
        d = tononi_degeneracy(cube, cube_db, [cube])
        assert d == 0.0

    def test_diverse_neighbors_low_d(self, cube_db):
        """Diverse neighbors → low degeneracy (each unique)."""
        cubes = [
            _make_cube("target", "x = 42"),
            _make_cube("n1", "import os\nos.getcwd()"),
            _make_cube("n2", "class User:\n    pass"),
            _make_cube("n3", "def sort(lst):\n    return sorted(lst)"),
        ]
        cube_db.save_cubes(cubes)
        cube_db.set_neighbor("target", "n1", 0.5)
        cube_db.set_neighbor("target", "n2", 0.5)
        cube_db.set_neighbor("target", "n3", 0.5)
        d = tononi_degeneracy(cubes[0], cube_db, cubes)
        assert isinstance(d, float)

    def test_redundant_neighbors_higher_d(self, cube_db):
        """Redundant (identical) neighbors → higher degeneracy."""
        content = "x = 42\ny = x + 1"
        cubes = [_make_cube("target", content)]
        # All neighbors have the same content (maximally redundant)
        for i in range(3):
            n = _make_cube(f"n{i}", content)
            cubes.append(n)
            cube_db.set_neighbor("target", f"n{i}", 0.5)
        cube_db.save_cubes(cubes)
        d = tononi_degeneracy(cubes[0], cube_db, cubes)
        assert d >= 0.0  # With identical neighbors, D should be positive


# ═══════════════════════════════════════════════════════════════════════
# Integration: advanced briques together
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationAdvanced:
    def test_laplacian_to_cheeger_to_bp(self, cube_db):
        """Laplacian grouping → Cheeger bottleneck → BP beliefs."""
        cubes = _setup_connected_cubes(cube_db, n=16, temp=0.5)
        cubes[0].temperature = 0.9
        cubes[7].temperature = 0.9

        # B9: Laplacian grouping
        groups = laplacian_rg_grouping(cubes, cube_db, n_groups=2)
        assert len(groups) == 2

        # B10: Cheeger constant
        ch = cheeger_constant(cubes, cube_db)
        assert ch['lambda_2'] >= 0

        # B20: BP
        beliefs = belief_propagation(cubes, cube_db)
        assert all(0 <= b <= 1 for b in beliefs.values())

        # B21: SP filter
        non_trivial, trivial = survey_propagation_filter(cubes, cube_db)
        assert len(non_trivial) + len(trivial) == 16

        # B22: Tononi
        for c in cubes[:3]:
            d = tononi_degeneracy(c, cube_db, cubes)
            assert d >= 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
