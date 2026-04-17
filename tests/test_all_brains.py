"""Test ALL brains / intelligence systems in Muninn — real function calls.

Not inspect.getsource checks — actual execution with real or mock data.
Each test calls the function, checks the return type and basic invariants.
"""
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


# ── MYCELIUM BRAINS ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def mycelium():
    from mycelium import Mycelium
    td = tempfile.mkdtemp()
    m = Mycelium(Path(td))
    texts = [
        "compression memory tokens mycelium tree branch",
        "spreading activation collins loftus semantic network",
        "decay ebbinghaus forgetting curve spaced repetition",
        "sleep consolidation wilson mcnaughton replay",
        "cube destruction reconstruction kaplan meier survival",
    ]
    for t in texts:
        m.observe(t)
    m.save()
    yield m
    m.close()


class TestMyceliumBrains:
    def test_spreading_activation(self, mycelium):
        r = mycelium.spread_activation(["compression"], hops=2, decay=0.5)
        assert isinstance(r, list)

    def test_transitive_inference(self, mycelium):
        r = mycelium.transitive_inference("compression")
        assert isinstance(r, list)

    def test_get_related(self, mycelium):
        r = mycelium.get_related("compression", top_n=5)
        assert isinstance(r, list)

    def test_get_related_no_stopwords(self, mycelium):
        r = mycelium.get_related("compression", top_n=10)
        stopwords = {"est", "pas", "que", "les", "des", "sur"}
        names = {n for n, _ in r}
        assert len(names & stopwords) == 0

    def test_detect_anomalies(self, mycelium):
        r = mycelium.detect_anomalies()
        assert isinstance(r, dict)
        assert "isolated" in r
        assert "hubs" in r

    def test_detect_blind_spots(self, mycelium):
        r = mycelium.detect_blind_spots(top_n=5)
        assert isinstance(r, list)

    def test_dream(self, mycelium):
        r = mycelium.dream()
        assert isinstance(r, list)

    def test_trip(self, mycelium):
        r = mycelium.trip(intensity=0.3, max_dreams=2)
        assert isinstance(r, dict)
        assert "created" in r
        assert "entropy_before" in r

    def test_decay(self, mycelium):
        r = mycelium.decay()
        assert isinstance(r, int)

    def test_compression_rules(self, mycelium):
        r = mycelium.get_compression_rules()
        assert isinstance(r, dict)

    def test_get_fusions(self, mycelium):
        r = mycelium.get_fusions()
        assert isinstance(r, dict)

    def test_growth_stats(self, mycelium):
        r = mycelium.growth_stats()
        assert isinstance(r, dict)
        assert "connections" in r
        assert "concepts" in r


# ── TREE BRAINS ──────────────────────────────────────────────────

class TestTreeBrains:
    def test_ebbinghaus_recall(self):
        from muninn_tree import _ebbinghaus_recall
        node = {"name": "test", "created": "2026-04-01",
                "last_read": "2026-04-15", "read_count": 3,
                "usefulness": 0.5, "tags": ["compression"]}
        r = _ebbinghaus_recall(node)
        assert isinstance(r, float)
        assert 0.0 <= r <= 1.0

    def test_actr_activation(self):
        from muninn_tree import _actr_activation
        node = {"name": "test", "created": "2026-04-01",
                "last_read": "2026-04-15", "read_count": 3}
        r = _actr_activation(node)
        assert isinstance(r, float)

    def test_danger_score(self):
        # _danger_score is an internal helper — access via module attribute
        import muninn_tree as mt
        fn = getattr(mt, '_danger_score', None)
        if fn is None:
            pytest.skip("_danger_score not exported")
        node = {"name": "test", "danger_score": 0.3}
        r = fn(node)
        assert isinstance(r, float)
        assert 0.0 <= r <= 1.0

    def test_session_mode_detection(self):
        from muninn_tree import detect_session_mode
        r = detect_session_mode(concepts=["compression", "compression", "memory", "tree"])
        assert isinstance(r, dict)
        assert r["mode"] in ("convergent", "divergent", "balanced")
        assert "diversity" in r
        assert "suggested_k" in r

    def test_extract_tags(self):
        from muninn_tree import extract_tags
        r = extract_tags("compression memory tokens mycelium tree branch boot session "
                         "compression compression compression memory memory")
        assert isinstance(r, list)

    def test_ncd(self):
        import muninn as _m
        r = _m._ncd("hello world", "hello world test")
        assert isinstance(r, float)
        assert 0.0 <= r <= 1.0


# ── CUBE BRAINS ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def cube_store():
    from cube import CubeStore, Cube, sha256_hash
    td = tempfile.mkdtemp()
    store = CubeStore(os.path.join(td, "test_cube.db"))
    cubes = []
    for i in range(5):
        content = f"def func{i}():\n    return {i}"
        c = Cube(id=f"cube{i}", content=content, sha256=sha256_hash(content),
                 file_origin=f"test{i}.py", line_start=1, line_end=2,
                 token_count=10, level=0)
        cubes.append(c)
    store.save_cubes(cubes)
    # Add some neighbors
    for i in range(4):
        store.set_neighbor(f"cube{i}", f"cube{i+1}", weight=1.0)
    yield store
    store.close()


class TestCubeBrains:
    def test_temperature(self, cube_store):
        from cube_analysis import compute_temperature
        cubes = cube_store.get_cubes_by_level(0)
        c = cubes[0] if cubes else None
        if not c:
            pytest.skip("no cubes")
        r = compute_temperature(c, cube_store)
        assert isinstance(r, float)

    def test_tononi_degeneracy(self, cube_store):
        from cube_analysis import tononi_degeneracy
        cubes = cube_store.get_cubes_by_level(0)
        if len(cubes) >= 2:
            r = tononi_degeneracy(cubes[0], cube_store, cubes)
            assert isinstance(r, float)
            assert r >= 0.0

    def test_kaplan_meier(self, cube_store):
        from cube_analysis import kaplan_meier_survival
        cubes = cube_store.get_cubes_by_level(0)
        if cubes:
            r = kaplan_meier_survival(cubes[0], cube_store)
            assert isinstance(r, float)
            assert 0.0 <= r <= 1.0

    def test_detect_dead_code(self, cube_store):
        from cube_analysis import detect_dead_code
        cubes = cube_store.get_cubes_by_level(0)
        if cubes:
            r = detect_dead_code(cubes[0], cubes, deps=[])
            assert isinstance(r, bool)

    def test_gods_number(self, cube_store):
        from cube_analysis import compute_gods_number
        cubes = cube_store.get_cubes_by_level(0)
        if len(cubes) >= 2:
            r = compute_gods_number(cubes, cube_store, deps=[])
            assert hasattr(r, "gods_number")
            assert isinstance(r.gods_number, int)

    def test_hebbian_update(self, cube_store):
        from cube_analysis import hebbian_update
        from dataclasses import dataclass
        @dataclass
        class FR:
            cube_id: str = "cube0"
            success: bool = True
            exact_match: bool = False
            ncd_score: float = 0.1
            reconstructed: str = ""
        hebbian_update(cube_store, [FR()])  # Should not crash

    def test_belief_propagation(self, cube_store):
        from cube_analysis import belief_propagation
        cubes = cube_store.get_cubes_by_level(0)
        if len(cubes) >= 3:
            r = belief_propagation(cubes, cube_store)
            assert isinstance(r, dict)

    def test_compute_ncd(self):
        from cube_providers import compute_ncd
        r = compute_ncd("def hello(): pass", "def hello(): return 42")
        assert isinstance(r, float)
        assert 0.0 <= r <= 1.0

    def test_cube_heatmap(self, cube_store):
        from cube_analysis import cube_heatmap
        r = cube_heatmap(cube_store)
        assert isinstance(r, dict)

    def test_extract_concepts(self):
        from cube_analysis import _extract_concepts
        r = _extract_concepts("def compress():\n    import re")
        assert isinstance(r, list)

    def test_provider_selection(self):
        from cube_analysis import CubeConfig
        config = CubeConfig()
        p = config.get_provider()
        assert hasattr(p, "name")
        assert p.name in ("mock", "ollama", "claude", "openai")

    def test_feed_mycelium_from_results(self):
        from cube_analysis import feed_mycelium_from_results
        from cube import Cube
        from dataclasses import dataclass
        @dataclass
        class FR:
            cube_id: str = "c1"
            success: bool = True
            exact_match: bool = False
            ncd_score: float = 0.1
            reconstructed: str = ""
        from cube import sha256_hash
        c1 = Cube(id="c1", content="def a(): pass", sha256=sha256_hash("def a(): pass"),
                  file_origin="a.py", line_start=1, line_end=1, token_count=5, level=0)
        c1.neighbors = ["c2"]
        c2 = Cube(id="c2", content="def b(): pass", sha256=sha256_hash("def b(): pass"),
                  file_origin="b.py", line_start=1, line_end=1, token_count=5, level=0)
        pairs = feed_mycelium_from_results([FR()], [c1, c2])
        assert isinstance(pairs, list)
        if pairs:
            assert pairs[0]["weight"] == 1.0
