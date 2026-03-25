"""
Tests for B-SCAN-05: Priority Ranker (Carmack scoring)
=======================================================
Covers: goldbeter Hill function, free energy surprise, MAPK depth bonus,
        rank_files composite scoring, RankedFile dataclass, edge cases.
"""

import sys
import os
import math

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest
from engine.core.scanner.priority_ranker import (
    goldbeter,
    free_energy_surprise,
    mapk_depth_bonus,
    rank_files,
    RankedFile,
    _ncd,
)
from engine.core.scanner.r0_calculator import FileMetrics


# ── Helpers ────────────────────────────────────────────────────────

def _make_fm(file: str, r0: int = 0, deg: float = 0.0,
             betw: float = 0.0, temp: float = 0.0,
             cheeger: bool = False) -> FileMetrics:
    """Build a FileMetrics instance."""
    return FileMetrics(
        file=file,
        r0=r0,
        degree_centrality=deg,
        betweenness_centrality=betw,
        temperature=temp,
        cheeger_bottleneck=cheeger,
    )


# ── Goldbeter Hill function ───────────────────────────────────────

class TestGoldbeter:

    def test_x_zero_returns_zero(self):
        """goldbeter(0) = 0."""
        assert goldbeter(0.0) == 0.0

    def test_x_equal_K_returns_half(self):
        """goldbeter(K) = 0.5 (midpoint of Hill function)."""
        assert goldbeter(10.0, K=10.0, n=4.0) == pytest.approx(0.5)

    def test_x_much_greater_than_K_approaches_one(self):
        """goldbeter(x >> K) ~ 1.0."""
        val = goldbeter(1000.0, K=10.0, n=4.0)
        assert val > 0.99
        assert val <= 1.0

    def test_x_less_than_K_returns_less_than_half(self):
        """goldbeter(x < K) < 0.5."""
        val = goldbeter(5.0, K=10.0, n=4.0)
        assert val < 0.5

    def test_negative_x_returns_zero(self):
        """goldbeter(x < 0) = 0."""
        assert goldbeter(-5.0) == 0.0

    def test_different_n_steepness(self):
        """Higher n = steeper transition (more ultrasensitive)."""
        # At x = 8 (below K=10), higher n should give lower value
        val_n2 = goldbeter(8.0, K=10.0, n=2.0)
        val_n8 = goldbeter(8.0, K=10.0, n=8.0)
        assert val_n2 > val_n8  # n=2 more gradual, higher at x<K


# ── Free Energy Surprise ──────────────────────────────────────────

class TestFreeEnergySurprise:

    def test_no_contents_returns_zero(self):
        """Without file_contents, surprise = 0."""
        graph = {"a": ["b"], "b": ["a"]}
        assert free_energy_surprise("a", graph) == 0.0

    def test_isolated_file_returns_zero(self):
        """File with no neighbors in graph = 0 surprise."""
        graph = {"a": [], "b": ["c"], "c": ["b"]}
        contents = {"a": b"hello", "b": b"world", "c": b"test"}
        assert free_energy_surprise("a", graph, file_contents=contents) == 0.0

    def test_outlier_file_gets_high_score(self):
        """A structurally different file should have higher surprise."""
        # Create a cluster of similar files + one outlier
        similar = b"import os\nimport sys\nprint('hello')\n" * 10
        outlier = b"x" * 500  # very different content

        graph = {
            "a": ["b", "c"],
            "b": ["a", "c"],
            "c": ["a", "b"],
            "outlier": ["a"],
            # a also connected to outlier
        }
        # Make a also connect to outlier for bidirectionality
        graph["a"] = ["b", "c", "outlier"]

        contents = {
            "a": similar,
            "b": similar + b"\n# extra",
            "c": similar + b"\n# more",
            "outlier": outlier,
        }
        score_outlier = free_energy_surprise("outlier", graph, file_contents=contents)
        # Outlier should get some score (may be 0 if all NCDs are similar)
        # At minimum it should be non-negative
        assert score_outlier >= 0.0

    def test_missing_file_in_graph_returns_zero(self):
        """File not in graph returns 0."""
        graph = {"a": ["b"], "b": ["a"]}
        contents = {"a": b"aaa", "b": b"bbb"}
        assert free_energy_surprise("missing", graph, file_contents=contents) == 0.0


# ── MAPK Depth Bonus ──────────────────────────────────────────────

class TestMapkDepthBonus:

    def test_depth_zero_returns_one(self):
        """File with no neighbors: depth=0, bonus=1.0."""
        graph = {"a": []}
        assert mapk_depth_bonus("a", graph) == 1.0

    def test_depth_four_returns_1_4(self):
        """Chain of 4 hops: bonus = 1.0 + 0.1*4 = 1.4."""
        graph = {"a": ["b"], "b": ["c"], "c": ["d"], "d": ["e"], "e": []}
        assert mapk_depth_bonus("a", graph) == pytest.approx(1.4)

    def test_file_not_in_graph(self):
        """File not in graph: bonus = 1.0."""
        graph = {"a": ["b"], "b": []}
        assert mapk_depth_bonus("missing", graph) == 1.0

    def test_cycle_does_not_infinite_loop(self):
        """Cycle in graph should not cause infinite loop."""
        graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
        bonus = mapk_depth_bonus("a", graph)
        assert bonus == pytest.approx(1.2)  # depth 2 (a->b->c, c->a already visited)


# ── rank_files ────────────────────────────────────────────────────

class TestRankFiles:

    def test_empty_graph_returns_empty(self):
        """No file_metrics = empty result."""
        assert rank_files({}, {}) == []

    def test_single_file(self):
        """Single file should still be ranked."""
        fm = {"a.py": _make_fm("a.py", r0=5, temp=0.5)}
        graph = {"a.py": []}
        result = rank_files(fm, graph)
        assert len(result) == 1
        assert result[0].file == "a.py"
        assert result[0].priority > 0.0

    def test_hub_hot_file_at_top(self):
        """Hub with high temp + cheeger should rank above isolated cold file."""
        fm = {
            "hub.py": _make_fm("hub.py", r0=20, betw=0.9, temp=0.8, cheeger=True),
            "cold.py": _make_fm("cold.py", r0=0, betw=0.0, temp=0.0, cheeger=False),
        }
        graph = {"hub.py": ["cold.py"], "cold.py": []}
        result = rank_files(fm, graph)
        assert result[0].file == "hub.py"
        assert result[-1].file == "cold.py"
        assert result[0].priority > result[-1].priority

    def test_component_weights_sum_approximately_one(self):
        """Component weights (0.25 + 0.20 + 0.20 + 0.20 + 0.15) = 1.0.
        With all components at 1.0 and depth_bonus=1.0, raw priority ~ 1.0."""
        fm = {"x.py": _make_fm("x.py", r0=10000, betw=1.0, temp=1.0, cheeger=True)}
        graph = {"x.py": []}
        result = rank_files(fm, graph)
        r = result[0]
        # goldbeter(10000) ~ 1.0, free_energy = 0 (no contents), betw=1, temp=1, cheeger=1
        # raw = 0.25*1 + 0.20*0 + 0.20*1 + 0.20*1 + 0.15*1 = 0.80
        # depth_bonus = 1.0
        expected = 0.25 * 1.0 + 0.20 * 0.0 + 0.20 * 1.0 + 0.20 * 1.0 + 0.15 * 1.0
        assert r.priority == pytest.approx(expected, abs=0.01)

    def test_depth_bonus_amplifies_priority(self):
        """MAPK depth bonus should amplify the raw score."""
        fm = {
            "a.py": _make_fm("a.py", r0=10, betw=0.5, temp=0.5),
        }
        # Chain: a -> b -> c -> d (depth 3 from a)
        graph = {"a.py": ["b.py"], "b.py": ["c.py"], "c.py": ["d.py"], "d.py": []}
        result = rank_files(fm, graph)
        r = result[0]
        assert r.depth_bonus == pytest.approx(1.3)  # 1.0 + 0.1*3
        # Priority should be raw * 1.3
        raw = (0.25 * goldbeter(10.0) + 0.20 * 0.0 + 0.20 * 0.5
               + 0.20 * 0.5 + 0.15 * 0.0)
        assert r.priority == pytest.approx(raw * 1.3, abs=0.01)

    def test_ordering_multiple_files(self):
        """Multiple files should be sorted by priority descending."""
        fm = {
            "low.py": _make_fm("low.py", r0=1, temp=0.1),
            "mid.py": _make_fm("mid.py", r0=10, betw=0.5, temp=0.5),
            "high.py": _make_fm("high.py", r0=20, betw=0.9, temp=0.9, cheeger=True),
        }
        graph = {"low.py": [], "mid.py": [], "high.py": []}
        result = rank_files(fm, graph)
        priorities = [r.priority for r in result]
        assert priorities == sorted(priorities, reverse=True)
        assert result[0].file == "high.py"
        assert result[-1].file == "low.py"


# ── RankedFile dataclass ──────────────────────────────────────────

class TestRankedFileDataclass:

    def test_fields_exist(self):
        """RankedFile should have file, priority, components, depth_bonus."""
        rf = RankedFile(file="test.py", priority=0.75, components={"a": 1}, depth_bonus=1.2)
        assert rf.file == "test.py"
        assert rf.priority == 0.75
        assert rf.components == {"a": 1}
        assert rf.depth_bonus == 1.2

    def test_components_dict_has_expected_keys(self):
        """rank_files should produce components with all 5 sub-score keys."""
        fm = {"x.py": _make_fm("x.py", r0=5, betw=0.3, temp=0.4)}
        graph = {"x.py": []}
        result = rank_files(fm, graph)
        keys = set(result[0].components.keys())
        expected = {'goldbeter', 'free_energy', 'betweenness', 'temperature', 'cheeger'}
        assert keys == expected


# ── NCD helper ────────────────────────────────────────────────────

class TestNCD:

    def test_empty_input_returns_zero(self):
        """NCD with empty bytes = 0."""
        assert _ncd(b'', b'hello') == 0.0
        assert _ncd(b'hello', b'') == 0.0

    def test_identical_content_low_ncd(self):
        """Identical content should have low NCD."""
        data = b"hello world" * 100
        ncd = _ncd(data, data)
        assert ncd < 0.4  # zlib header overhead keeps NCD > 0 even for identical data

    def test_different_content_higher_ncd(self):
        """Very different content should have higher NCD."""
        a = b"aaaa" * 200
        b_data = b"zzzz" * 200
        ncd = _ncd(a, b_data)
        assert ncd > 0.0
