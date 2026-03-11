"""H2 — Synthese / reve: generate insights during sleep consolidation.

Tests:
  H2.1  dream() returns list of dicts with required keys
  H2.2  Detects strong pairs (high co-occurrence)
  H2.3  Detects absences (high-degree concepts not connected)
  H2.4  Health metric always present
  H2.5  Empty mycelium = no crash, empty list
  H2.6  Saves to insights.json
  H2.7  dream wired in prune() (code check)
"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from mycelium import Mycelium
from pathlib import Path


def _make_mycelium_rich():
    """Create a mycelium with strong pairs and absences."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    path = os.path.join(muninn_dir, "mycelium.json")

    conns = {}
    # Strong pair: alpha-beta with count=100 (way above average)
    conns["alpha|beta"] = {"count": 100, "first_seen": "2026-03-01",
                            "last_seen": "2026-03-11"}
    # Normal connections
    concepts = ["alpha", "beta", "gamma", "delta", "epsilon",
                "zeta", "eta", "theta", "iota", "kappa"]
    for i, a in enumerate(concepts):
        for b in concepts[i+1:]:
            key = f"{a}|{b}" if a < b else f"{b}|{a}"
            if key not in conns:
                conns[key] = {"count": 3, "first_seen": "2026-03-01",
                               "last_seen": "2026-03-11"}

    # High-degree concepts that are NOT connected (absence)
    for c in ["hub1", "hub2"]:
        for x in concepts[:8]:
            key = f"{c}|{x}" if c < x else f"{x}|{c}"
            conns[key] = {"count": 5, "first_seen": "2026-03-01",
                           "last_seen": "2026-03-11"}
    # hub1 and hub2 are NOT directly connected -> absence

    data = {"connections": conns, "fusions": {}, "version": 3}
    with open(path, "w") as f:
        json.dump(data, f)
    m = Mycelium(tmp)
    return m, tmp


def test_h2_1_returns_list():
    """dream() should return a list of dicts with required keys."""
    m, tmp = _make_mycelium_rich()
    result = m.dream()
    assert isinstance(result, list), f"H2.1 FAIL: not a list: {type(result)}"
    for ins in result:
        assert isinstance(ins, dict), f"H2.1 FAIL: insight not dict"
        for key in ["type", "concepts", "score", "text"]:
            assert key in ins, f"H2.1 FAIL: missing key {key} in {ins}"
    print(f"  H2.1 PASS: {len(result)} insights, all valid dicts")
    shutil.rmtree(tmp)


def test_h2_2_strong_pairs():
    """Should detect alpha-beta as a strong pair (count=100 vs avg~3)."""
    m, tmp = _make_mycelium_rich()
    result = m.dream()
    strong = [i for i in result if i["type"] == "strong_pair"]
    assert len(strong) > 0, f"H2.2 FAIL: no strong pairs found"
    # alpha-beta should be in there
    found = any("alpha" in i["concepts"] and "beta" in i["concepts"] for i in strong)
    assert found, f"H2.2 FAIL: alpha-beta not found in strong pairs"
    print(f"  H2.2 PASS: {len(strong)} strong pairs, alpha-beta found")
    shutil.rmtree(tmp)


def test_h2_3_absences():
    """Should detect hub1-hub2 absence (both high-degree, not connected)."""
    m, tmp = _make_mycelium_rich()
    result = m.dream()
    absences = [i for i in result if i["type"] == "absence"]
    assert len(absences) > 0, f"H2.3 FAIL: no absences found"
    found = any("hub1" in i["concepts"] and "hub2" in i["concepts"] for i in absences)
    assert found, f"H2.3 FAIL: hub1-hub2 absence not detected. Found: {[i['concepts'] for i in absences[:5]]}"
    print(f"  H2.3 PASS: {len(absences)} absences, hub1-hub2 found")
    shutil.rmtree(tmp)


def test_h2_4_health_metric():
    """Health metric should always be present."""
    m, tmp = _make_mycelium_rich()
    result = m.dream()
    health = [i for i in result if i["type"] == "health"]
    assert len(health) == 1, f"H2.4 FAIL: expected 1 health, got {len(health)}"
    assert 0 <= health[0]["score"] <= 1, f"H2.4 FAIL: health score out of range: {health[0]['score']}"
    print(f"  H2.4 PASS: health={health[0]['score']:.2%}")
    shutil.rmtree(tmp)


def test_h2_5_empty_no_crash():
    """Empty mycelium should return empty list, no crash."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    path = os.path.join(muninn_dir, "mycelium.json")
    data = {"connections": {}, "fusions": {}, "version": 3}
    with open(path, "w") as f:
        json.dump(data, f)
    m = Mycelium(tmp)
    result = m.dream()
    assert result == [], f"H2.5 FAIL: expected [], got {result}"
    print("  H2.5 PASS: empty mycelium, 0 insights, no crash")
    shutil.rmtree(tmp)


def test_h2_6_saves_insights():
    """dream() should save to .muninn/insights.json."""
    m, tmp = _make_mycelium_rich()
    m.dream()
    insights_path = os.path.join(tmp, ".muninn", "insights.json")
    assert os.path.exists(insights_path), "H2.6 FAIL: insights.json not created"
    data = json.loads(open(insights_path, encoding="utf-8").read())
    assert isinstance(data, list), f"H2.6 FAIL: not a list"
    assert len(data) > 0, "H2.6 FAIL: empty insights.json"
    assert "timestamp" in data[0], "H2.6 FAIL: no timestamp"
    print(f"  H2.6 PASS: insights.json with {len(data)} entries")
    shutil.rmtree(tmp)


def test_h2_7_wired_in_prune():
    """dream() should be called in prune()."""
    import muninn
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    prune_start = src.find("def prune(")
    prune_end = src.find("\ndef ", prune_start + 1)
    prune_body = src[prune_start:prune_end]
    assert "dream()" in prune_body, "H2.7 FAIL: dream not wired in prune()"
    assert "H2" in prune_body, "H2.7 FAIL: H2 comment not in prune()"
    print("  H2.7 PASS: dream wired in prune()")


if __name__ == "__main__":
    print("=== H2 — Synthese / reve ===")
    test_h2_1_returns_list()
    test_h2_2_strong_pairs()
    test_h2_3_absences()
    test_h2_4_health_metric()
    test_h2_5_empty_no_crash()
    test_h2_6_saves_insights()
    test_h2_7_wired_in_prune()
    print("\n  ALL H2 BORNES PASSED")
