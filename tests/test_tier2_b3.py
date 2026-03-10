"""B3 -- Angles morts (blind spots): strict validation bornes.

Tests:
  B3.1  Zone gap: two high-degree concepts in same zone without connection
  B3.2  Transitive gap: A-B, B-C exist, A-C missing
  B3.3  Empty graph: no crash
  B3.4  Real mycelium: finds at least 1 blind spot
  B3.5  Output format: list of (str, str, str) tuples
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

def test_b3_1_zone_gap():
    """Two well-connected concepts in same cluster but no direct link"""
    from pathlib import Path
    from mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        # Create a dense graph where alpha and beta share high-degree bridge nodes
        # but are NOT directly connected to each other
        conns = {}
        bridges = ["hub01", "hub02", "hub03", "hub04", "hub05"]
        # alpha connects to all bridges
        for h in bridges:
            conns[f"alpha|{h}"] = {"count": 10, "last_seen": "2026-03-10"}
        # beta connects to all bridges
        for h in bridges:
            conns[f"beta|{h}"] = {"count": 10, "last_seen": "2026-03-10"}
        # Each bridge connects to 5 extra nodes (degree >= 7 each)
        for h in bridges:
            for i in range(5):
                conns[f"{h}|extra_{h}_{i}"] = {"count": 5, "last_seen": "2026-03-10"}
        m.data["connections"] = conns
        result = m.detect_blind_spots(top_n=50)
        # alpha and beta should appear as transitive blind spot through bridges
        pairs = [(a, b) for a, b, _ in result]
        found = ("alpha", "beta") in pairs or ("beta", "alpha") in pairs
        assert found, f"B3.1 FAIL: alpha-beta not found in blind spots, got {pairs[:5]}"
    print(f"  B3.1 PASS: zone gap detected (alpha-beta, {len(result)} total spots)")

def test_b3_2_transitive():
    """A-B connected, B-C connected, A-C missing with high degree"""
    from pathlib import Path
    from mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        conns = {}
        # Give A, B, C high degree by connecting to many nodes
        for prefix in ["aaa", "bbb", "ccc"]:
            for i in range(10):
                conns[f"{prefix}|x{prefix}{i:02d}"] = {"count": 5, "last_seen": "2026-03-10"}
        # Connect A-B and B-C but NOT A-C
        conns["aaa|bbb"] = {"count": 20, "last_seen": "2026-03-10"}
        conns["bbb|ccc"] = {"count": 20, "last_seen": "2026-03-10"}
        m.data["connections"] = conns
        result = m.detect_blind_spots(top_n=50)
        pairs = [(a, b) for a, b, _ in result]
        found = ("aaa", "ccc") in pairs or ("ccc", "aaa") in pairs
        assert found, f"B3.2 FAIL: transitive gap aaa-ccc not found"
        # Check reason mentions either transitive or zone_gap (both valid)
        for a, b, reason in result:
            if sorted([a, b]) == ["aaa", "ccc"]:
                valid = "transitive" in reason or "zone_gap" in reason
                assert valid, f"B3.2 FAIL: reason should mention transitive or zone_gap, got {reason}"
                break
    print(f"  B3.2 PASS: transitive gap detected (aaa-ccc)")

def test_b3_3_empty():
    """Empty mycelium should return empty list, no crash"""
    from pathlib import Path
    from mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        result = m.detect_blind_spots()
        assert result == [], f"B3.3 FAIL: expected [], got {result}"
    print(f"  B3.3 PASS: empty graph returns empty blind spots")

def test_b3_4_real():
    """Real mycelium should find at least 1 blind spot"""
    from pathlib import Path
    from mycelium import Mycelium
    repo = Path(os.path.dirname(__file__)).parent
    m = Mycelium(repo)
    if len(m.data["connections"]) < 10:
        print(f"  B3.4 SKIP: too few connections")
        return
    result = m.detect_blind_spots(top_n=10)
    assert len(result) > 0, f"B3.4 FAIL: no blind spots in {len(m.data['connections'])} connections"
    print(f"  B3.4 PASS: {len(result)} blind spots found, top: {result[0][:2]}")

def test_b3_5_format():
    """Output should be list of (str, str, str) tuples"""
    from pathlib import Path
    from mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        m = Mycelium(Path(tmpdir))
        conns = {}
        for prefix in ["aaa", "bbb", "ccc"]:
            for i in range(10):
                conns[f"{prefix}|x{prefix}{i:02d}"] = {"count": 5, "last_seen": "2026-03-10"}
        conns["aaa|bbb"] = {"count": 20, "last_seen": "2026-03-10"}
        conns["bbb|ccc"] = {"count": 20, "last_seen": "2026-03-10"}
        m.data["connections"] = conns
        result = m.detect_blind_spots()
        assert isinstance(result, list), f"B3.5 FAIL: not a list"
        if result:
            item = result[0]
            assert len(item) == 3, f"B3.5 FAIL: tuple len={len(item)}"
            assert all(isinstance(x, str) for x in item), f"B3.5 FAIL: not all strings"
    print(f"  B3.5 PASS: output format = list of (str, str, str)")

if __name__ == "__main__":
    print("=== B3 -- Angles morts (blind spots): validation bornes ===")
    test_b3_1_zone_gap()
    test_b3_2_transitive()
    test_b3_3_empty()
    test_b3_4_real()
    test_b3_5_format()
    print("\n  ALL B3 BORNES PASSED")
