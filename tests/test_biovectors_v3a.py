"""V3A — Transitive inference value transfer: strict validation bornes.

Paper: Wynne 1995, J Exp Psych: Animal Behavior Processes.
Also: Paz-y-Mino, Bond, Kamil, Balda 2004, Nature.
Formula: V(A->C) = strength(A,B) * strength(B,C) * beta^hops

Tests:
  V3A.1  Direct neighbors returned with highest strength
  V3A.2  2-hop transitive inference works (A->B->C inferred)
  V3A.3  Strength decays with distance (hop 1 > hop 2 > hop 3)
  V3A.4  beta=0 disables transitive inference (only direct)
  V3A.5  Empty mycelium returns empty list
  V3A.6  Unknown concept returns empty list
  V3A.7  No cycles: visited nodes not revisited
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {name} PASS{': ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {name} FAIL{': ' + detail if detail else ''}")


def _make_mycelium(connections):
    """Create a Mycelium with given connections dict.
    connections: dict of "a|b" -> count
    """
    from mycelium import Mycelium
    m = Mycelium.__new__(Mycelium)
    m.data = {
        "connections": {k: {"count": v, "first": "2026-01-01", "last": "2026-03-11"}
                        for k, v in connections.items()},
        "fusions": {},
        "fillers": [],
        "stats": {}
    }
    m.repo_path = "."
    m.federated = False
    m.zone = "default"
    m.MIN_CONCEPT_LEN = 3
    m._db = None
    m._sigmoid_k = 0  # disable sigmoid for testing
    return m


def test_v3a_1_direct_neighbors():
    """Direct neighbors have highest strength"""
    m = _make_mycelium({
        "alpha|beta": 10.0,
        "alpha|gamma": 5.0,
        "beta|delta": 8.0,
    })
    results = m.transitive_inference("alpha", max_hops=1, beta=0.5)
    names = [c for c, _ in results]
    # beta should be strongest (10), gamma second (5)
    check("V3A.1", len(results) >= 2 and names[0] == "beta",
          f"top={names[:3]}, scores={[round(s,4) for _,s in results[:3]]}")


def test_v3a_2_two_hop():
    """2-hop transitive: alpha->beta->delta inferred"""
    m = _make_mycelium({
        "alpha|beta": 10.0,
        "beta|delta": 8.0,
    })
    results = m.transitive_inference("alpha", max_hops=2, beta=0.5)
    names = [c for c, _ in results]
    # delta should appear via alpha->beta->delta
    check("V3A.2", "delta" in names,
          f"found={names}, delta present via 2-hop chain")


def test_v3a_3_decay_with_distance():
    """Strength decays: hop 1 > hop 2 > hop 3"""
    m = _make_mycelium({
        "alpha|beta": 10.0,    # hop 1
        "beta|gamma": 10.0,    # hop 2 via beta
        "gamma|delta": 10.0,   # hop 3 via gamma
    })
    results = m.transitive_inference("alpha", max_hops=3, beta=0.5)
    scores = {c: s for c, s in results}
    # beta (hop 1) > gamma (hop 2) > delta (hop 3)
    ok = (scores.get("beta", 0) > scores.get("gamma", 0) >
          scores.get("delta", 0) > 0)
    check("V3A.3", ok,
          f"beta={scores.get('beta',0):.4f} > gamma={scores.get('gamma',0):.4f} > delta={scores.get('delta',0):.4f}")


def test_v3a_4_beta_zero():
    """beta=0 -> no transitive inference (only direct neighbors with zero strength)"""
    m = _make_mycelium({
        "alpha|beta": 10.0,
        "beta|gamma": 10.0,
    })
    results = m.transitive_inference("alpha", max_hops=3, beta=0.0)
    # With beta=0, all decay factors are 0, so min_strength filter kills everything
    check("V3A.4", len(results) == 0,
          f"results={results} (beta=0 disables)")


def test_v3a_5_empty_mycelium():
    """Empty mycelium returns empty list"""
    m = _make_mycelium({})
    results = m.transitive_inference("alpha", max_hops=3)
    check("V3A.5", results == [], f"results={results}")


def test_v3a_6_unknown_concept():
    """Unknown concept returns empty list"""
    m = _make_mycelium({"alpha|beta": 10.0})
    results = m.transitive_inference("unknown", max_hops=3)
    check("V3A.6", results == [], f"results={results}")


def test_v3a_7_no_cycles():
    """Visited nodes not revisited (no infinite loops)"""
    # Create a cycle: alpha -> beta -> gamma -> alpha
    m = _make_mycelium({
        "alpha|beta": 10.0,
        "beta|gamma": 10.0,
        "gamma|alpha": 10.0,
    })
    # Should not crash or loop infinitely
    results = m.transitive_inference("alpha", max_hops=5, beta=0.5)
    # alpha should NOT appear in results (it's the seed)
    names = [c for c, _ in results]
    check("V3A.7", "alpha" not in names and len(results) <= 10,
          f"results={names} (no cycle, alpha excluded)")


if __name__ == "__main__":
    print("=== V3A Transitive Inference — 7 bornes ===")
    test_v3a_1_direct_neighbors()
    test_v3a_2_two_hop()
    test_v3a_3_decay_with_distance()
    test_v3a_4_beta_zero()
    test_v3a_5_empty_mycelium()
    test_v3a_6_unknown_concept()
    test_v3a_7_no_cycles()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
