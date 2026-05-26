#!/usr/bin/env python3
"""
Tests for Cube wiring — validate that ALL 39 bricks are properly connected.

Tests the 3 orchestration points added in the wiring pass:
  1. prepare_cubes()      — B25 dead filter + B21 survey propagation
  2. run_destruction_cycle() post-cycle — B30+B29+B23+B24+B22+B38
  3. post_cycle_analysis() — B27+B28+B9+B10+B26+B35+B31+B37+B38
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    Cube, CubeStore, MockLLMProvider, Dependency,
    sha256_hash, prepare_cubes, post_cycle_analysis,
    run_destruction_cycle, ReconstructionResult,
    scan_repo, subdivide_file, parse_dependencies, assign_neighbors,
)


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "wiring_test.db")
    s = CubeStore(db_path)
    yield s
    s.close()


def _make_cube(id_, content, file_origin="test.py", line_start=1, line_end=5):
    return Cube(
        id=id_, content=content,
        sha256=sha256_hash(content),
        file_origin=file_origin,
        line_start=line_start, line_end=line_end,
        token_count=max(10, len(content.split())),
    )


@pytest.fixture
def cubes_with_neighbors(store):
    """5 cubes with neighbors wired — enough for meaningful tests."""
    c1 = _make_cube("a:L1-L5:lv0", "def add(a, b):\n    return a + b\n")
    c2 = _make_cube("a:L6-L10:lv0", "def sub(a, b):\n    return a - b\n")
    c3 = _make_cube("a:L11-L15:lv0", "result = add(1, sub(3, 2))\nprint(result)\n")
    c4 = _make_cube("b:L1-L5:lv0", "import math\ndef sqrt(x):\n    return math.sqrt(x)\n",
                     file_origin="math_utils.py")
    c5 = _make_cube("b:L6-L10:lv0", "PI = 3.14159\ndef circle_area(r):\n    return PI * r * r\n",
                     file_origin="math_utils.py")
    cubes = [c1, c2, c3, c4, c5]
    store.save_cubes(cubes)
    # Wire neighbors
    for i, c in enumerate(cubes):
        for j, n in enumerate(cubes):
            if i != j:
                store.set_neighbor(c.id, n.id, 0.7, 'static')
    return cubes


@pytest.fixture
def dead_cubes():
    """Cubes that should be detected as dead (comments/TODOs)."""
    return [
        _make_cube("dead:L1:lv0",
                    "# TODO: implement this\n# TODO: fix that\n# FIXME: broken\npass\n",
                    file_origin="dead.py"),
        _make_cube("dead:L5:lv0",
                    "# This is just a comment block\n# explaining nothing useful\n# end\n",
                    file_origin="dead.py"),
    ]


# ═══════════════════════════════════════════════════════════════════════
# 1. prepare_cubes() — B25 + B21 pre-filter
# ═══════════════════════════════════════════════════════════════════════

class TestPrepareCubes:
    """Unit tests for prepare_cubes() orchestration."""

    def test_returns_tuple(self, cubes_with_neighbors, store):
        """Returns (cubes_list, stats_dict)."""
        result = prepare_cubes(cubes_with_neighbors, store)
        assert isinstance(result, tuple)
        assert len(result) == 2
        filtered, stats = result
        assert isinstance(filtered, list)
        assert isinstance(stats, dict)

    def test_stats_keys(self, cubes_with_neighbors, store):
        """Stats dict has all required keys."""
        _, stats = prepare_cubes(cubes_with_neighbors, store)
        for key in ('total', 'dead', 'trivial', 'active'):
            assert key in stats, f"Missing key: {key}"

    def test_no_deps_keeps_all(self, cubes_with_neighbors, store):
        """Without deps, no dead filtering — all cubes kept."""
        filtered, stats = prepare_cubes(cubes_with_neighbors, store, deps=None)
        assert stats['dead'] == 0
        assert stats['total'] == 5
        assert stats['active'] <= 5

    def test_with_deps_filters_dead(self, cubes_with_neighbors, dead_cubes, store):
        """With deps, dead cubes are filtered out."""
        all_cubes = cubes_with_neighbors + dead_cubes
        store.save_cubes(dead_cubes)
        # No deps referencing dead cubes → they should be detected as dead
        deps = [Dependency(source="a:L11-L15:lv0", target="a:L1-L5:lv0",
                          dep_type="call", name="add")]
        filtered, stats = prepare_cubes(all_cubes, store, deps=deps, use_survey=False)
        assert stats['dead'] >= 1  # At least some dead detected
        assert stats['total'] == 7

    def test_empty_list(self, store):
        """Empty cube list doesn't crash."""
        filtered, stats = prepare_cubes([], store)
        assert filtered == []
        assert stats['total'] == 0
        assert stats['active'] == 0

    def test_survey_disabled(self, cubes_with_neighbors, store):
        """use_survey=False skips survey propagation."""
        filtered, stats = prepare_cubes(cubes_with_neighbors, store, use_survey=False)
        assert stats['trivial'] == 0  # Survey not run
        assert stats['active'] == 5

    def test_survey_needs_10_cubes(self, cubes_with_neighbors, store):
        """Survey propagation only runs with >10 cubes."""
        # 5 cubes < 10 threshold
        filtered, stats = prepare_cubes(cubes_with_neighbors, store, use_survey=True)
        assert stats['trivial'] == 0  # Not enough cubes for survey

    def test_active_leq_total(self, cubes_with_neighbors, store):
        """Active count is always <= total."""
        _, stats = prepare_cubes(cubes_with_neighbors, store)
        assert stats['active'] <= stats['total']


# ═══════════════════════════════════════════════════════════════════════
# 2. run_destruction_cycle() — post-cycle wiring
# ═══════════════════════════════════════════════════════════════════════

class TestCyclePostWiring:
    """Test that post-cycle bricks actually run inside run_destruction_cycle()."""

    def test_results_returned(self, cubes_with_neighbors, store):
        """Cycle returns ReconstructionResult for each cube."""
        mock = MockLLMProvider()
        results = run_destruction_cycle(
            cubes_with_neighbors, store, mock, cycle_num=1)
        assert len(results) == 5
        for r in results:
            assert isinstance(r, ReconstructionResult)

    def test_b24_km_survival_set(self, cubes_with_neighbors, store):
        """B24: Kaplan-Meier survival computed for hot cubes."""
        mock = MockLLMProvider()
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        # After cycle, hottest cubes should have _km_survival
        hot = sorted(cubes_with_neighbors,
                     key=lambda c: c.temperature, reverse=True)[:10]
        for hc in hot:
            assert hasattr(hc, '_km_survival'), f"Cube {hc.id} missing _km_survival"
            assert isinstance(hc._km_survival, float)
            assert 0.0 <= hc._km_survival <= 1.0

    def test_b22_degeneracy_set_on_failed(self, cubes_with_neighbors, store):
        """B22: Tononi degeneracy computed for failed cubes."""
        # Force failures by making mock return garbage
        mock = MockLLMProvider({'reconstructing': 'GARBAGE_CONTENT_NOTHING_MATCHES'})
        results = run_destruction_cycle(
            cubes_with_neighbors, store, mock, cycle_num=1)
        failed_ids = {r.cube_id for r in results if not r.success}
        cube_map = {c.id: c for c in cubes_with_neighbors}
        for fid in failed_ids:
            fc = cube_map.get(fid)
            if fc:
                assert hasattr(fc, '_degeneracy'), f"Failed cube {fid} missing _degeneracy"

    def test_b30_hebbian_runs(self, cubes_with_neighbors, store):
        """B30: Hebbian update doesn't crash (weights may change)."""
        mock = MockLLMProvider()
        # Run 2 cycles — weights should update
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=2)
        # No crash = Hebbian ran. Check that neighbor data still exists.
        neighbors = store.get_neighbors(cubes_with_neighbors[0].id)
        assert len(neighbors) > 0

    def test_b23_temperature_updated(self, cubes_with_neighbors, store):
        """B23: Temperatures update after cycle."""
        mock = MockLLMProvider()
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        # At least one cube should have non-zero temperature
        any_changed = False
        for c in cubes_with_neighbors:
            stored = store.get_cube(c.id)
            if stored and (stored.temperature != 0.0 or stored.score != 0.0):
                any_changed = True
                break
        assert any_changed, "No temperature changed after cycle"

    def test_cycle_records_history(self, cubes_with_neighbors, store):
        """Cycle history recorded in SQLite."""
        mock = MockLLMProvider()
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        for c in cubes_with_neighbors:
            cycles = store.get_cycles(c.id)
            assert len(cycles) >= 1
            assert cycles[0]['cycle'] == 1

    def test_two_cycles_accumulate(self, cubes_with_neighbors, store):
        """Two cycles produce 2 history entries per cube."""
        mock = MockLLMProvider()
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=2)
        for c in cubes_with_neighbors:
            cycles = store.get_cycles(c.id)
            assert len(cycles) == 2


# ═══════════════════════════════════════════════════════════════════════
# 3. post_cycle_analysis() — full diagnostics
# ═══════════════════════════════════════════════════════════════════════

class TestPostCycleAnalysis:
    """Unit tests for post_cycle_analysis() wiring all diagnostic bricks."""

    def test_returns_dict(self, cubes_with_neighbors, store):
        """Returns a dict."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert isinstance(analysis, dict)

    def test_b27_b28_levels(self, cubes_with_neighbors, store):
        """B27+B28: Level pyramid present in analysis."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert 'levels' in analysis
        # levels is either a dict of level->count or has 'error'
        if 'error' not in analysis['levels']:
            assert isinstance(analysis['levels'], dict)

    def test_b9_rg_groups(self, cubes_with_neighbors, store):
        """B9: Laplacian RG grouping present."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert 'rg_groups' in analysis

    def test_b10_cheeger(self, cubes_with_neighbors, store):
        """B10: Cheeger constant present."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert 'cheeger' in analysis

    def test_b26_gods_number(self, cubes_with_neighbors, store):
        """B26: God's Number present with expected structure."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert 'gods_number' in analysis
        gn = analysis['gods_number']
        if 'error' not in gn:
            assert 'value' in gn
            assert 'total' in gn
            assert 'bounds' in gn
            assert gn['value'] >= 0

    def test_b35_heatmap(self, cubes_with_neighbors, store):
        """B35: Heatmap present."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        assert 'heatmap' in analysis
        if 'error' not in analysis['heatmap']:
            assert isinstance(analysis['heatmap'], dict)

    def test_no_git_blame_without_repo(self, cubes_with_neighbors, store):
        """B31: Git blame not present when no repo_path."""
        analysis = post_cycle_analysis(cubes_with_neighbors, store, repo_path=None)
        assert 'git_blame' not in analysis

    def test_analysis_after_cycle(self, cubes_with_neighbors, store):
        """Full analysis after a destruction cycle."""
        mock = MockLLMProvider()
        run_destruction_cycle(cubes_with_neighbors, store, mock, cycle_num=1)
        analysis = post_cycle_analysis(cubes_with_neighbors, store)
        # All main keys should be present
        for key in ('levels', 'rg_groups', 'cheeger', 'gods_number', 'heatmap'):
            assert key in analysis, f"Missing analysis key: {key}"

    def test_analysis_empty_cubes(self, store):
        """Analysis with empty cube list doesn't crash."""
        analysis = post_cycle_analysis([], store)
        assert isinstance(analysis, dict)

    def test_analysis_with_deps(self, cubes_with_neighbors, store):
        """Analysis with deps gives God's Number with dead count."""
        deps = [Dependency(source="a:L11-L15:lv0", target="a:L1-L5:lv0",
                          dep_type="call", name="add")]
        analysis = post_cycle_analysis(cubes_with_neighbors, store, deps=deps)
        gn = analysis.get('gods_number', {})
        if 'error' not in gn:
            assert gn['bounds']['n_dead'] >= 0


# ═══════════════════════════════════════════════════════════════════════
# 4. Integration: prepare → cycle → analysis (full pipeline)
# ═══════════════════════════════════════════════════════════════════════

class TestFullWiringIntegration:
    """End-to-end: prepare_cubes → run_destruction_cycle → post_cycle_analysis."""

    def test_mini_pipeline(self, cubes_with_neighbors, store):
        """Complete mini pipeline: prepare → cycle → analysis."""
        mock = MockLLMProvider()

        # Phase 1: Prepare
        active, stats = prepare_cubes(cubes_with_neighbors, store, use_survey=False)
        assert stats['active'] == 5
        assert len(active) == 5

        # Phase 2: Cycle
        results = run_destruction_cycle(active, store, mock, cycle_num=1)
        assert len(results) == 5

        # Phase 3: Analysis
        analysis = post_cycle_analysis(active, store)
        assert 'levels' in analysis
        assert 'gods_number' in analysis

    def test_pipeline_two_cycles_convergence(self, cubes_with_neighbors, store):
        """Two cycles — check that state evolves."""
        mock = MockLLMProvider()
        active, _ = prepare_cubes(cubes_with_neighbors, store, use_survey=False)

        r1 = run_destruction_cycle(active, store, mock, cycle_num=1)
        r2 = run_destruction_cycle(active, store, mock, cycle_num=2)

        # History should show 2 cycles per cube
        for c in active:
            cycles = store.get_cycles(c.id)
            assert len(cycles) == 2

        # Analysis should work on post-2-cycle state
        analysis = post_cycle_analysis(active, store)
        assert isinstance(analysis, dict)

    def test_pipeline_from_scan(self, tmp_path, store):
        """Scan real files → subdivide → wire → cycle → analysis."""
        # Create minimal Python files
        (tmp_path / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\n"
            "def sub(a, b):\n    return a - b\n\n"
            "def mul(a, b):\n    return a * b\n\n"
            "result = add(1, mul(2, sub(5, 3)))\nprint(result)\n"
        )
        (tmp_path / "utils.py").write_text(
            "import math\n\ndef sqrt(x):\n    return math.sqrt(x)\n\n"
            "def square(x):\n    return x * x\n"
        )

        # Scan
        scanned = scan_repo(str(tmp_path), extensions=['.py'])
        assert len(scanned) >= 2

        # Subdivide
        all_cubes = []
        for sf in scanned:
            cubes = subdivide_file(sf.path, sf.content)
            all_cubes.extend(cubes)
        assert len(all_cubes) >= 2

        # Store + wire neighbors
        store.save_cubes(all_cubes)
        deps = parse_dependencies(scanned)
        assign_neighbors(all_cubes, deps, store)

        # Prepare
        active, stats = prepare_cubes(all_cubes, store, deps=deps, use_survey=False)
        assert stats['total'] >= 2

        # Cycle
        mock = MockLLMProvider()
        results = run_destruction_cycle(active, store, mock, cycle_num=1)
        assert len(results) == len(active)

        # Analysis
        analysis = post_cycle_analysis(active, store, deps=deps)
        assert 'gods_number' in analysis
        assert 'heatmap' in analysis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
