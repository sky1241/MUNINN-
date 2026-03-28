"""B2 -- Graph anomaly detection: strict validation bornes.

Tests:
  B2.1  Isolated nodes detected (degree <= 1)
  B2.2  Hub monopoly detected (degree > mean + 2*std)
  B2.3  Empty graph: no crash, returns empty
  B2.4  Real mycelium: finds at least 1 anomaly
  B2.5  Output keys are exactly {isolated, hubs, weak_zones}
"""
import sys, os, tempfile
def test_b2_1_isolated():
    """Concept with degree=1 should be detected as isolated"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        # Create a mini graph: A-B (isolated), C-D-E (connected)
        m.data["connections"] = {
            "alpha|beta": {"count": 5, "last_seen": "2026-03-10"},
            "gamma|delta": {"count": 10, "last_seen": "2026-03-10"},
            "delta|epsilon": {"count": 8, "last_seen": "2026-03-10"},
            "gamma|epsilon": {"count": 6, "last_seen": "2026-03-10"},
        }
        result = m.detect_anomalies()
        # alpha and beta have degree=1, should be isolated
        assert "alpha" in result["isolated"], f"B2.1 FAIL: alpha not in isolated"
        assert "beta" in result["isolated"], f"B2.1 FAIL: beta not in isolated"
        # gamma has degree=2, should NOT be isolated
        assert "gamma" not in result["isolated"], f"B2.1 FAIL: gamma wrongly isolated"
    print(f"  B2.1 PASS: isolated nodes detected ({len(result['isolated'])} found)")

def test_b2_2_hubs():
    """Node with much higher degree than others should be detected as hub"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        # Create a star: hub connects to 20 nodes, each node has degree=1
        conns = {}
        for i in range(20):
            conns[f"hub|node{i:02d}"] = {"count": 5, "last_seen": "2026-03-10"}
        m.data["connections"] = conns
        result = m.detect_anomalies()
        hub_names = [h[0] for h in result["hubs"]]
        assert "hub" in hub_names, f"B2.2 FAIL: hub not detected, hubs={result['hubs']}"
        # The node0..node19 should be isolated (degree=1)
        assert len(result["isolated"]) == 20, f"B2.2 FAIL: expected 20 isolated, got {len(result['isolated'])}"
    print(f"  B2.2 PASS: hub monopoly detected (degree={result['hubs'][0][1]})")

def test_b2_3_empty():
    """Empty mycelium should return empty anomalies, no crash"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        result = m.detect_anomalies()
        assert result == {"isolated": [], "hubs": [], "weak_zones": []}, f"B2.3 FAIL: {result}"
    print(f"  B2.3 PASS: empty graph returns empty anomalies")

def test_b2_4_real():
    """Real mycelium should find at least 1 anomaly"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    repo = Path(os.path.dirname(__file__)).parent
    m = Mycelium(repo)
    if not m.data["connections"]:
        print(f"  B2.4 SKIP: no connections")
        return
    result = m.detect_anomalies()
    total = len(result["isolated"]) + len(result["hubs"]) + len(result["weak_zones"])
    assert total > 0, f"B2.4 FAIL: no anomalies found in {len(m.data['connections'])} connections"
    print(f"  B2.4 PASS: {len(result['isolated'])} isolated, {len(result['hubs'])} hubs, {len(result['weak_zones'])} weak_zones")

def test_b2_5_keys():
    """Output should have exactly the 3 expected keys"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        result = m.detect_anomalies()
        expected_keys = {"isolated", "hubs", "weak_zones"}
        assert set(result.keys()) == expected_keys, f"B2.5 FAIL: keys={set(result.keys())}"
    print(f"  B2.5 PASS: output keys = {{isolated, hubs, weak_zones}}")

if __name__ == "__main__":
    print("=== B2 -- Graph anomaly detection: validation bornes ===")
    test_b2_1_isolated()
    test_b2_2_hubs()
    test_b2_3_empty()
    test_b2_4_real()
    test_b2_5_keys()
    print("\n  ALL B2 BORNES PASSED")
