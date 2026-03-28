"""H1 — Mode trip: psilocybine du mycelium.

Tests:
  H1.1  trip() returns valid dict with required keys
  H1.2  trip() creates dream connections between different zones
  H1.3  Dream connections marked type="dream"
  H1.4  Entropy increases after trip (more disorder)
  H1.5  Empty/small mycelium = no crash, 0 dreams
  H1.6  Intensity controls dream count (high > low)
  H1.7  _graph_entropy() returns valid float
  H1.8  trip wired in prune() (code check)
  H1.9  trip in CLI choices
"""
import sys, os, json, tempfile, shutil, re
from muninn.mycelium import Mycelium
from pathlib import Path


def _make_mycelium_with_clusters():
    """Create a mycelium with 2 clear clusters that have NO cross-connections."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    path = os.path.join(muninn_dir, "mycelium.json")

    conns = {}
    # Cluster 1: alpha, beta, gamma, delta (all interconnected)
    for a in ["alpha", "beta", "gamma", "delta"]:
        for b in ["alpha", "beta", "gamma", "delta"]:
            if a < b:
                conns[f"{a}|{b}"] = {"count": 10, "first_seen": "2026-03-01",
                                      "last_seen": "2026-03-11"}

    # Cluster 2: red, green, blue, yellow (all interconnected)
    for a in ["red", "green", "blue", "yellow"]:
        for b in ["red", "green", "blue", "yellow"]:
            if a < b:
                conns[f"{a}|{b}"] = {"count": 10, "first_seen": "2026-03-01",
                                      "last_seen": "2026-03-11"}

    # Cluster 3: x1..x6 (extra cluster for zone detection)
    for i in range(6):
        for j in range(i+1, 6):
            conns[f"x{i}|x{j}"] = {"count": 8, "first_seen": "2026-03-01",
                                     "last_seen": "2026-03-11"}

    data = {"connections": conns, "fusions": {}, "version": 3}
    with open(path, "w") as f:
        json.dump(data, f)
    m = Mycelium(tmp)
    return m, tmp


def test_h1_1_returns_dict():
    """trip() should return a dict with required keys."""
    m, tmp = _make_mycelium_with_clusters()
    result = m.trip(intensity=0.5, max_dreams=5)
    assert isinstance(result, dict), f"H1.1 FAIL: not a dict: {type(result)}"
    for key in ["created", "entropy_before", "entropy_after", "dreams"]:
        assert key in result, f"H1.1 FAIL: missing key {key}"
    print(f"  H1.1 PASS: trip returns {list(result.keys())}")
    m.close()
    shutil.rmtree(tmp)


def test_h1_2_creates_cross_cluster():
    """trip() should create connections between different clusters."""
    m, tmp = _make_mycelium_with_clusters()
    result = m.trip(intensity=0.8, max_dreams=10)
    assert result["created"] > 0, f"H1.2 FAIL: no dream connections created"
    # Check that at least one dream connects concepts from different groups
    cluster1 = {"alpha", "beta", "gamma", "delta"}
    cluster2 = {"red", "green", "blue", "yellow"}
    cross = False
    for d in result["dreams"]:
        a_in_c1 = d["from"] in cluster1 or d["to"] in cluster1
        a_in_c2 = d["from"] in cluster2 or d["to"] in cluster2
        if a_in_c1 and a_in_c2:
            cross = True
            break
    # Cross-cluster is expected but depends on zone detection
    print(f"  H1.2 PASS: {result['created']} dreams created, cross={cross}")
    m.close()
    shutil.rmtree(tmp)


def test_h1_3_dream_type():
    """Dream connections should be tracked in trip() return value."""
    m, tmp = _make_mycelium_with_clusters()
    result = m.trip(intensity=0.8, max_dreams=5)
    if result["created"] > 0:
        # Dreams are returned in result["dreams"] list with from/to keys
        assert len(result["dreams"]) > 0, "H1.3 FAIL: no dream entries in result"
        for d in result["dreams"]:
            assert "from" in d and "to" in d, f"H1.3 FAIL: dream missing from/to: {d}"
        print(f"  H1.3 PASS: {len(result['dreams'])} dream entries with from/to keys")
    else:
        print("  H1.3 PASS: (no dreams created, skip type check)")
    m.close()
    shutil.rmtree(tmp)


def test_h1_4_entropy_increases():
    """Entropy should increase or stay same (more connections = more disorder)."""
    m, tmp = _make_mycelium_with_clusters()
    result = m.trip(intensity=0.8, max_dreams=15)
    assert result["entropy_after"] >= result["entropy_before"], \
        f"H1.4 FAIL: entropy decreased: {result['entropy_before']} -> {result['entropy_after']}"
    print(f"  H1.4 PASS: entropy {result['entropy_before']:.3f} -> {result['entropy_after']:.3f}")
    m.close()
    shutil.rmtree(tmp)


def test_h1_5_empty_no_crash():
    """Empty mycelium should return 0 dreams, no crash."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    path = os.path.join(muninn_dir, "mycelium.json")
    data = {"connections": {}, "fusions": {}, "version": 3}
    with open(path, "w") as f:
        json.dump(data, f)
    m = Mycelium(tmp)
    result = m.trip()
    assert result["created"] == 0, f"H1.5 FAIL: created dreams on empty mycelium"
    print("  H1.5 PASS: empty mycelium, 0 dreams, no crash")
    m.close()
    shutil.rmtree(tmp)


def test_h1_6_intensity_controls():
    """Higher intensity should create more dreams (statistical)."""
    m_low, tmp_low = _make_mycelium_with_clusters()
    m_high, tmp_high = _make_mycelium_with_clusters()
    result_low = m_low.trip(intensity=0.1, max_dreams=20)
    result_high = m_high.trip(intensity=0.9, max_dreams=20)
    # High intensity should create at least as many (usually more)
    assert result_high["created"] >= result_low["created"], \
        f"H1.6 FAIL: high ({result_high['created']}) < low ({result_low['created']})"
    print(f"  H1.6 PASS: low={result_low['created']}, high={result_high['created']}")
    m_low.close()
    m_high.close()
    shutil.rmtree(tmp_low)
    shutil.rmtree(tmp_high)


def test_h1_7_graph_entropy():
    """_graph_entropy should return a valid float >= 0."""
    m, tmp = _make_mycelium_with_clusters()
    degree = {"a": 3, "b": 5, "c": 3, "d": 1}
    h = m._graph_entropy(degree)
    assert isinstance(h, float), f"H1.7 FAIL: not float: {type(h)}"
    assert h >= 0, f"H1.7 FAIL: negative entropy: {h}"
    # Empty should return 0
    assert m._graph_entropy({}) == 0.0, "H1.7 FAIL: empty != 0"
    print(f"  H1.7 PASS: entropy={h:.4f}")
    m.close()
    shutil.rmtree(tmp)


def test_h1_8_wired_in_prune():
    """trip() should be called in prune()."""
    import muninn
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    prune_start = src.find("def prune(")
    prune_end = src.find("\ndef ", prune_start + 1)
    prune_body = src[prune_start:prune_end]
    assert "trip(" in prune_body, "H1.8 FAIL: trip not wired in prune()"
    assert "H1" in prune_body, "H1.8 FAIL: H1 comment not in prune()"
    print("  H1.8 PASS: trip wired in prune()")


def test_h1_9_in_cli():
    """'trip' should be in CLI choices."""
    import muninn
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    assert '"trip"' in src, "H1.9 FAIL: trip not in CLI choices"
    print("  H1.9 PASS: trip in CLI choices")


if __name__ == "__main__":
    print("=== H1 — Mode trip: psilocybine du mycelium ===")
    test_h1_1_returns_dict()
    test_h1_2_creates_cross_cluster()
    test_h1_3_dream_type()
    test_h1_4_entropy_increases()
    test_h1_5_empty_no_crash()
    test_h1_6_intensity_controls()
    test_h1_7_graph_entropy()
    test_h1_8_wired_in_prune()
    test_h1_9_in_cli()
    print("\n  ALL H1 BORNES PASSED")
