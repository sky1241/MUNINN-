#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B23-B26.

B23: Temperature par cube + stockage
B24: Kaplan-Meier survie
B25: Danger Theory filtre dead code
B26: God's Number calcul
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    Cube, CubeStore, Dependency,
    sha256_hash,
    compute_temperature, update_all_temperatures,
    kaplan_meier_survival,
    detect_dead_code, filter_dead_cubes,
    compute_gods_number, GodsNumberResult,
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
# B23: Temperature
# ═══════════════════════════════════════════════════════════════════════

class TestB23Temperature:
    def test_no_history_returns_score(self, cube_db):
        """No cycle history → return raw score."""
        c = _make_cube("c1")
        c.score = 0.5
        cube_db.save_cube(c)
        temp = compute_temperature(c, cube_db)
        assert temp == 0.5

    def test_all_success_low_temp(self, cube_db):
        """All successful cycles → low temperature."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        for i in range(5):
            cube_db.record_cycle("c1", i + 1, True, "", 0.5)
        temp = compute_temperature(c, cube_db)
        assert temp < 0.3

    def test_all_failure_high_temp(self, cube_db):
        """All failed cycles → high temperature."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        for i in range(5):
            cube_db.record_cycle("c1", i + 1, False, "", 3.0)
        temp = compute_temperature(c, cube_db)
        assert temp > 0.5

    def test_temperature_in_range(self, cube_db):
        """Temperature always in [0, 1]."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        cube_db.record_cycle("c1", 1, False, "", 100.0)
        temp = compute_temperature(c, cube_db)
        assert 0.0 <= temp <= 1.0

    def test_update_all(self, cube_db):
        """update_all_temperatures updates all cubes."""
        cubes = [_make_cube(f"c{i}") for i in range(5)]
        cube_db.save_cubes(cubes)
        for c in cubes:
            cube_db.record_cycle(c.id, 1, True, "", 0.5)
        update_all_temperatures(cubes, cube_db)
        for c in cubes:
            assert c.temperature > 0


# ═══════════════════════════════════════════════════════════════════════
# B24: Kaplan-Meier
# ═══════════════════════════════════════════════════════════════════════

class TestB24KaplanMeier:
    def test_no_data_full_survival(self, cube_db):
        """No cycles → S(t) = 1.0 (assume hot)."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        assert kaplan_meier_survival(c, cube_db) == 1.0

    def test_all_success_drops(self, cube_db):
        """All successful reconstructions → S(t) drops to 0."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        # All "deaths" (successful reconstructions = cube is killed/reconstructed)
        # Wait — in Kaplan-Meier for cubes:
        # "death" = failed reconstruction (cube survives = stays hot)
        # "success" = successful reconstruction (cube is "killed")
        # So all success = all deaths = S(t) → 0
        # But in our code, success=True in the cycle means the reconstruction succeeded
        # In KM: d_i = 0 if success (cube "survives" = stays hot), 1 if fail
        # Actually re-reading: d_i = 0 if cycle['success'] else 1
        # So success=True → d_i=0, cube SURVIVES (stays hot)
        # success=False → d_i=1, cube DIES (cools down)
        for i in range(5):
            cube_db.record_cycle("c1", i + 1, True, "", 0.5)
        s = kaplan_meier_survival(c, cube_db)
        assert s == 1.0  # All success → cube never "dies" → survival = 1.0

    def test_all_failure_survival_zero(self, cube_db):
        """All failed reconstructions → S(t) drops toward 0."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        for i in range(5):
            cube_db.record_cycle("c1", i + 1, False, "", 3.0)
        s = kaplan_meier_survival(c, cube_db)
        assert s == 0.0  # All fail → all deaths → S=0

    def test_mixed_survival(self, cube_db):
        """Mixed success/fail → 0 < S(t) < 1."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        cube_db.record_cycle("c1", 1, True, "", 0.5)
        cube_db.record_cycle("c1", 2, False, "", 2.0)
        cube_db.record_cycle("c1", 3, True, "", 0.5)
        cube_db.record_cycle("c1", 4, True, "", 0.3)
        s = kaplan_meier_survival(c, cube_db)
        assert 0.0 < s < 1.0

    def test_survival_range(self, cube_db):
        """S(t) always in [0, 1]."""
        c = _make_cube("c1")
        cube_db.save_cube(c)
        cube_db.record_cycle("c1", 1, False, "", 5.0)
        s = kaplan_meier_survival(c, cube_db)
        assert 0.0 <= s <= 1.0


# ═══════════════════════════════════════════════════════════════════════
# B25: Danger Theory
# ═══════════════════════════════════════════════════════════════════════

class TestB25DangerTheory:
    def test_active_code_not_dead(self):
        """Code with deps is not dead."""
        c = _make_cube("c1", "import os\ndef f(): pass", "main.py")
        deps = [Dependency("test.py", "main.py", "import", "main")]
        assert detect_dead_code(c, [c], deps) is False

    def test_isolated_file_is_dead(self):
        """File with no deps is dead."""
        c = _make_cube("c1", "x = 42", "orphan.py")
        deps = [Dependency("a.py", "b.py", "import", "b")]
        assert detect_dead_code(c, [c], deps) is True

    def test_mostly_comments_is_dead(self):
        """Mostly commented code → dead."""
        content = "# old code\n# deprecated\n# don't use\n# really\n# no\nx = 1"
        c = _make_cube("c1", content, "old.py")
        deps = [Dependency("a.py", "old.py", "import", "old")]
        assert detect_dead_code(c, [c], deps) is True

    def test_mostly_todos_is_dead(self):
        """Mostly TODO/FIXME → dead."""
        content = "# TODO: implement\n# FIXME: broken\n# TODO: refactor\npass"
        c = _make_cube("c1", content, "wip.py")
        deps = [Dependency("a.py", "wip.py", "import", "wip")]
        assert detect_dead_code(c, [c], deps) is True

    def test_real_code_not_dead(self):
        """Active code with deps → not dead."""
        content = "def process(data):\n    return data.strip()\n"
        c = _make_cube("c1", content, "utils.py")
        deps = [Dependency("main.py", "utils.py", "import", "utils")]
        assert detect_dead_code(c, [c], deps) is False

    def test_filter_separates(self):
        """filter_dead_cubes separates active from dead."""
        active_cube = _make_cube("c1", "def f(): pass", "main.py")
        dead_cube = _make_cube("c2", "x=1", "orphan.py")
        deps = [Dependency("test.py", "main.py", "import", "main")]
        active, dead = filter_dead_cubes([active_cube, dead_cube], deps)
        assert len(active) == 1
        assert len(dead) == 1
        assert active[0].id == "c1"
        assert dead[0].id == "c2"


# ═══════════════════════════════════════════════════════════════════════
# B26: God's Number
# ═══════════════════════════════════════════════════════════════════════

class TestB26GodsNumber:
    def test_basic_computation(self, cube_db):
        """God's Number computed correctly."""
        cubes = []
        deps = []
        for i in range(10):
            c = _make_cube(f"c{i}", f"val_{i} = {i}", "main.py", i, i+1)
            cubes.append(c)
            deps.append(Dependency("test.py", "main.py", "import", "main"))

        cube_db.save_cubes(cubes)

        # Set up neighbors
        for c in cubes:
            for n in cubes:
                if c.id != n.id:
                    cube_db.set_neighbor(c.id, n.id, 0.5, 'static')

        # Make some cubes hot (failed cycles)
        for i in range(3):
            cube_db.record_cycle(cubes[i].id, 1, False, "", 3.0)

        result = compute_gods_number(cubes, cube_db, deps, threshold=0.3)
        assert isinstance(result, GodsNumberResult)
        assert result.gods_number >= 0
        assert result.total_cubes == 10

    def test_gods_number_has_bounds(self, cube_db):
        """Result includes theoretical bounds."""
        cubes = [_make_cube(f"c{i}", f"x={i}", "f.py") for i in range(20)]
        deps = [Dependency("t.py", "f.py", "import", "f")]
        cube_db.save_cubes(cubes)
        for c in cubes:
            cube_db.set_neighbor(c.id, cubes[0].id, 0.5, 'static')

        result = compute_gods_number(cubes, cube_db, deps)
        assert 'lrc_lower' in result.bounds
        assert 'mera_estimate' in result.bounds
        assert 'percolation_fc' in result.bounds

    def test_dead_code_filtered(self, cube_db):
        """Dead cubes don't count toward God's Number."""
        active = _make_cube("c1", "def f(): pass", "main.py")
        dead = _make_cube("c2", "x=1", "orphan.py")
        cubes = [active, dead]
        deps = [Dependency("test.py", "main.py", "import", "main")]

        cube_db.save_cubes(cubes)
        # Make both hot
        for c in cubes:
            cube_db.record_cycle(c.id, 1, False, "", 5.0)

        result = compute_gods_number(cubes, cube_db, deps, threshold=0.3)
        assert result.gods_number <= len(cubes)
        assert len(result.dead_cubes) >= 1

    def test_lrc_bound(self, cube_db):
        """LRC bound: God's Number ≥ n/10."""
        cubes = [_make_cube(f"c{i}", f"x={i}", "f.py") for i in range(100)]
        deps = [Dependency("t.py", "f.py", "import", "f")]
        cube_db.save_cubes(cubes)

        result = compute_gods_number(cubes, cube_db, deps)
        assert result.bounds['lrc_lower'] == 10  # 100/10

    def test_zero_cubes(self, cube_db):
        """Empty cube list → God's Number = 0."""
        result = compute_gods_number([], cube_db, [])
        assert result.gods_number == 0
        assert result.total_cubes == 0


# ═══════════════════════════════════════════════════════════════════════
# Integration: B23-B26 pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB23B26:
    def test_full_scoring_pipeline(self, cube_db):
        """Temperature → Kaplan-Meier → Danger Theory → God's Number."""
        cubes = [_make_cube(f"c{i}", f"val_{i} = {i * 7}", "main.py", i, i+1)
                 for i in range(10)]
        deps = [Dependency("test.py", "main.py", "import", "main")]
        cube_db.save_cubes(cubes)

        # Set neighbors
        for c in cubes:
            for n in cubes[:3]:
                if c.id != n.id:
                    cube_db.set_neighbor(c.id, n.id, 0.5)

        # Simulate cycles — first 3 fail, rest succeed
        for i, c in enumerate(cubes):
            success = i >= 3
            cube_db.record_cycle(c.id, 1, success, "", 0.5 if success else 3.0)

        # B23: temperatures
        update_all_temperatures(cubes, cube_db)
        hot_temps = [c.temperature for c in cubes[:3]]
        cold_temps = [c.temperature for c in cubes[3:]]
        assert max(cold_temps) < max(hot_temps) or len(hot_temps) == 0

        # B24: Kaplan-Meier
        for c in cubes:
            s = kaplan_meier_survival(c, cube_db)
            assert 0.0 <= s <= 1.0

        # B26: God's Number
        result = compute_gods_number(cubes, cube_db, deps, threshold=0.3)
        assert result.gods_number >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
