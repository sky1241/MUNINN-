#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B35-B38 (Forge integration).

B35: Cube heatmap
B36: Forge link (fuse risks)
B37: Auto-repair
B38: Feedback loop (anomalies → mycelium)
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    Cube, CubeStore, sha256_hash,
    cube_heatmap,
    fuse_risks, _get_forge_risks,
    auto_repair,
    record_anomaly, feedback_loop_check, feed_anomalies_to_mycelium,
)


def _make_cube(cid, content="x=1", file_origin="f.py", line_start=1, line_end=2, temp=0.0):
    return Cube(id=cid, content=content, sha256=sha256_hash(content),
                file_origin=file_origin, line_start=line_start, line_end=line_end,
                temperature=temp, token_count=5)


@pytest.fixture
def cube_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = CubeStore(db_path)
    yield store
    store.close()


def _setup_multi_file_cubes(cube_db, temps_a=None, temps_b=None):
    """Create cubes across two files with given temperatures."""
    if temps_a is None:
        temps_a = [0.1, 0.3, 0.7, 0.9]
    if temps_b is None:
        temps_b = [0.0, 0.1, 0.2]
    cubes = []
    for i, t in enumerate(temps_a):
        c = _make_cube(f"a.py:L{i}:lv0", f"code_a_{i}", "a.py", i, i+1, temp=t)
        cubes.append(c)
    for i, t in enumerate(temps_b):
        c = _make_cube(f"b.py:L{i}:lv0", f"code_b_{i}", "b.py", i, i+1, temp=t)
        cubes.append(c)
    cube_db.save_cubes(cubes)
    # Set some neighbors
    for i in range(len(temps_a) - 1):
        cube_db.set_neighbor(f"a.py:L{i}:lv0", f"a.py:L{i+1}:lv0", 0.8, "static")
    return cubes


# ═══════════════════════════════════════════════════════════════════════
# B35: Cube Heatmap
# ═══════════════════════════════════════════════════════════════════════

class TestB35Heatmap:
    def test_heatmap_returns_files(self, cube_db):
        """Heatmap groups cubes by file."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        assert 'a.py' in hm
        assert 'b.py' in hm

    def test_heatmap_counts(self, cube_db):
        """Heatmap has correct cube counts."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        assert hm['a.py']['count'] == 4
        assert hm['b.py']['count'] == 3

    def test_heatmap_hot_count(self, cube_db):
        """Heatmap counts hot cubes (temp > 0.5)."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        assert hm['a.py']['hot_count'] == 2  # 0.7 and 0.9
        assert hm['b.py']['hot_count'] == 0

    def test_heatmap_avg_temp(self, cube_db):
        """Heatmap computes average temperature."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        assert hm['a.py']['avg_temp'] == pytest.approx(0.5, abs=0.01)

    def test_heatmap_max_temp(self, cube_db):
        """Heatmap tracks max temperature."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        assert hm['a.py']['max_temp'] == 0.9

    def test_heatmap_cube_details(self, cube_db):
        """Heatmap includes per-cube details."""
        _setup_multi_file_cubes(cube_db)
        hm = cube_heatmap(cube_db)
        cubes_list = hm['a.py']['cubes']
        assert len(cubes_list) == 4
        assert all('id' in c and 'temp' in c and 'lines' in c for c in cubes_list)

    def test_heatmap_empty_db(self, cube_db):
        """Empty database returns empty heatmap."""
        hm = cube_heatmap(cube_db)
        assert hm == {}


# ═══════════════════════════════════════════════════════════════════════
# B36: Forge Link
# ═══════════════════════════════════════════════════════════════════════

class TestB36ForgeLink:
    def test_fuse_returns_list(self, cube_db, tmp_path):
        """fuse_risks returns sorted list of dicts."""
        _setup_multi_file_cubes(cube_db)
        results = fuse_risks(cube_db, str(tmp_path))
        assert isinstance(results, list)
        assert len(results) >= 2

    def test_fuse_has_fields(self, cube_db, tmp_path):
        """Each result has required fields."""
        _setup_multi_file_cubes(cube_db)
        results = fuse_risks(cube_db, str(tmp_path))
        for r in results:
            assert 'file' in r
            assert 'forge_risk' in r
            assert 'cube_temp' in r
            assert 'combined' in r
            assert 'hot_cubes' in r

    def test_fuse_sorted_desc(self, cube_db, tmp_path):
        """Results sorted by combined risk descending."""
        _setup_multi_file_cubes(cube_db)
        results = fuse_risks(cube_db, str(tmp_path))
        for i in range(len(results) - 1):
            assert results[i]['combined'] >= results[i+1]['combined']

    def test_fuse_cube_only(self, cube_db, tmp_path):
        """Without Forge data, risk = cube temperature * cube_weight."""
        _setup_multi_file_cubes(cube_db)
        results = fuse_risks(cube_db, str(tmp_path), forge_weight=0.0, cube_weight=1.0)
        a_result = [r for r in results if r['file'] == 'a.py'][0]
        assert a_result['combined'] == pytest.approx(0.5, abs=0.01)

    def test_get_forge_risks_nonexistent(self):
        """_get_forge_risks with bad path returns empty dict."""
        risks = _get_forge_risks("/nonexistent/path")
        assert risks == {}


# ═══════════════════════════════════════════════════════════════════════
# B37: Auto-repair
# ═══════════════════════════════════════════════════════════════════════

class TestB37AutoRepair:
    def test_repair_returns_patches(self, cube_db):
        """auto_repair returns patch list."""
        _setup_multi_file_cubes(cube_db)
        patches = auto_repair(cube_db, ['a.py'])
        assert isinstance(patches, list)
        assert len(patches) > 0

    def test_repair_hottest_first(self, cube_db):
        """Patches are for hottest cubes first."""
        _setup_multi_file_cubes(cube_db)
        patches = auto_repair(cube_db, ['a.py'], max_patches=2)
        if len(patches) >= 2:
            assert patches[0]['temperature'] >= patches[1]['temperature']

    def test_repair_has_fields(self, cube_db):
        """Each patch has required fields."""
        _setup_multi_file_cubes(cube_db)
        patches = auto_repair(cube_db, ['a.py'])
        for p in patches:
            assert 'cube_id' in p
            assert 'file' in p
            assert 'original' in p
            assert 'temperature' in p
            assert 'neighbor_count' in p

    def test_repair_no_reconstructor(self, cube_db):
        """Without reconstructor, patch is None (dry-run)."""
        _setup_multi_file_cubes(cube_db)
        patches = auto_repair(cube_db, ['a.py'])
        for p in patches:
            assert p['patch'] is None

    def test_repair_max_patches(self, cube_db):
        """Respects max_patches limit."""
        _setup_multi_file_cubes(cube_db)
        patches = auto_repair(cube_db, ['a.py'], max_patches=1)
        assert len(patches) <= 1

    def test_repair_nonexistent_file(self, cube_db):
        """Non-existent file returns empty list."""
        patches = auto_repair(cube_db, ['nonexistent.py'])
        assert patches == []

    def test_repair_no_neighbors(self, cube_db):
        """Cubes without neighbors are skipped."""
        cube_db.save_cube(_make_cube("lone:L0:lv0", "x=1", "lone.py", 1, 2, 0.9))
        patches = auto_repair(cube_db, ['lone.py'])
        assert patches == []


# ═══════════════════════════════════════════════════════════════════════
# B38: Feedback Loop
# ═══════════════════════════════════════════════════════════════════════

class TestB38FeedbackLoop:
    def test_record_anomaly(self, tmp_path):
        """record_anomaly writes JSONL entry."""
        path = str(tmp_path / "anomalies.jsonl")
        entry = record_anomaly(path, "engine/core/muninn.py",
                               {'risk': 0.8, 'churn': 42},
                               ['c1', 'c2'], 'predicted_risky')
        assert entry['file'] == "engine/core/muninn.py"
        assert entry['validated'] is False
        assert os.path.exists(path)

    def test_record_multiple(self, tmp_path):
        """Multiple anomalies appended to same file."""
        path = str(tmp_path / "anomalies.jsonl")
        record_anomaly(path, "a.py", {}, ['c1'])
        record_anomaly(path, "b.py", {}, ['c2'])
        with open(path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 2

    def test_feedback_no_file(self, tmp_path):
        """feedback_loop_check with no file returns zeros."""
        result = feedback_loop_check(str(tmp_path / "nope.jsonl"), ".")
        assert result['total'] == 0
        assert result['accuracy'] == 0.0

    def test_feedback_structure(self, tmp_path):
        """feedback_loop_check returns correct structure."""
        path = str(tmp_path / "anomalies.jsonl")
        # Write an old anomaly (timestamp in the past)
        entry = {
            'timestamp': time.time() - 200 * 86400,  # 200 days ago
            'date': '2025-09-01',
            'file': 'engine/core/muninn.py',
            'metrics': {'risk': 0.8},
            'cube_ids': ['c1'],
            'label': 'predicted_risky',
            'validated': False,
        }
        with open(path, 'w') as f:
            f.write(json.dumps(entry) + '\n')

        result = feedback_loop_check(path, ".", lookback_days=180)
        assert 'total' in result
        assert 'correct' in result
        assert 'accuracy' in result
        assert 'details' in result

    def test_feed_anomalies_empty(self, tmp_path):
        """feed_anomalies_to_mycelium with no file returns empty."""
        pairs = feed_anomalies_to_mycelium(str(tmp_path / "nope.jsonl"))
        assert pairs == []

    def test_feed_anomalies_validated(self, tmp_path):
        """Only validated anomalies are fed to mycelium."""
        path = str(tmp_path / "anomalies.jsonl")
        entries = [
            {'file': 'a.py', 'validated': True, 'was_buggy': True},
            {'file': 'b.py', 'validated': False, 'was_buggy': False},
            {'file': 'c.py', 'validated': True, 'was_buggy': False},
        ]
        with open(path, 'w') as f:
            for e in entries:
                f.write(json.dumps(e) + '\n')

        pairs = feed_anomalies_to_mycelium(path)
        assert len(pairs) == 2  # Only validated ones
        assert pairs[0]['weight'] == 1.0   # True positive
        assert pairs[1]['weight'] == -0.5  # False positive


# ═══════════════════════════════════════════════════════════════════════
# Integration: B35-B38 together
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB35B38:
    def test_heatmap_to_repair(self, cube_db, tmp_path):
        """Heatmap → identify hot files → auto-repair candidates."""
        _setup_multi_file_cubes(cube_db)

        # B35: Heatmap
        hm = cube_heatmap(cube_db)
        assert 'a.py' in hm
        assert hm['a.py']['hot_count'] == 2

        # B36: Fuse risks
        results = fuse_risks(cube_db, str(tmp_path))
        assert len(results) >= 2
        # a.py should be ranked higher (has hot cubes)
        a_rank = next(i for i, r in enumerate(results) if r['file'] == 'a.py')
        b_rank = next(i for i, r in enumerate(results) if r['file'] == 'b.py')
        assert a_rank < b_rank  # a.py more risky

        # B37: Auto-repair on hottest file
        hot_files = [results[0]['file']]
        patches = auto_repair(cube_db, hot_files, max_patches=2)
        assert len(patches) > 0

        # B38: Record anomaly
        anomaly_path = str(tmp_path / "anomalies.jsonl")
        for r in results[:2]:
            record_anomaly(anomaly_path, r['file'],
                           {'combined': r['combined']},
                           [p['cube_id'] for p in patches if p['file'] == r['file']])

        # Verify anomaly recorded
        with open(anomaly_path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
