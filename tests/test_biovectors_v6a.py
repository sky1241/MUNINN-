"""V6A — Emotional tagging E(a): strict validation bornes.

Paper: Richter-Levin & Akirav 2003, Brain Research Reviews.
Also: Frey & Morris 1997, Nature (synaptic tagging).
Formula: E(a) = 1 + kappa * a^n / (a^n + theta^n)

Tests:
  V6A.1  E(a=0) == 1.0 (no boost without arousal)
  V6A.2  E(a=1) > 1.5 (significant boost at max arousal)
  V6A.3  Mycelium weight with arousal > weight without arousal
  V6A.4  No numerical explosion (arousal=100)
  V6A.5  observe_text with arousal=0 works same as before
  V6A.6  Hill switch is sharp around theta=0.5
"""
import sys, os, tempfile, json
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


def _hill(a, kappa=1.0, n=3, theta=0.5):
    """Reproduce the V6A Hill function."""
    a = max(0.0, float(a))
    if a > 0:
        return 1.0 + kappa * (a ** n) / (a ** n + theta ** n)
    return 1.0


def test_v6a_1_no_boost():
    """E(a=0) == 1.0"""
    e = _hill(0.0)
    check("V6A.1", abs(e - 1.0) < 1e-10, f"E(0)={e}")


def test_v6a_2_max_boost():
    """E(a=1) > 1.5"""
    e = _hill(1.0)
    check("V6A.2", e > 1.5, f"E(1)={e:.4f}")


def test_v6a_3_mycelium_weight():
    """Mycelium connection with arousal > without arousal"""
    from mycelium import Mycelium
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = type('P', (), {'__truediv__': lambda s, k: type('P2', (), {'__truediv__': lambda s2, k2: os.path.join(tmpdir, k, k2), 'exists': lambda s2: os.path.exists(os.path.join(tmpdir, k, k2)), 'mkdir': lambda s2, **kw: os.makedirs(os.path.join(tmpdir, k, k2), exist_ok=True), 'read_text': lambda s2, **kw: open(os.path.join(tmpdir, k, k2)).read(), 'write_text': lambda s2, t, **kw: open(os.path.join(tmpdir, k, k2), 'w').write(t)})()})()
        # Use simpler approach: create two Mycelium instances, observe same concepts
        # One with arousal=0, one with arousal=0.9
        m1 = Mycelium.__new__(Mycelium)
        m1.data = {"connections": {}, "fusions": {}, "fillers": [], "stats": {}}
        m1.repo_path = tmpdir
        m1.federated = False
        m1.zone = "default"
        m1.MIN_CONCEPT_LEN = 3
        m1._db = None
        m1._high_degree_cache = None
        m1._adj_cache = None
        m1._adj_cache_max_weight = 0.0
        m1.FUSION_THRESHOLD = 5
        m1.MAX_CONNECTIONS = 0

        m2 = Mycelium.__new__(Mycelium)
        m2.data = {"connections": {}, "fusions": {}, "fillers": [], "stats": {}}
        m2.repo_path = tmpdir
        m2.federated = False
        m2.zone = "default"
        m2.MIN_CONCEPT_LEN = 3
        m2._db = None
        m2._high_degree_cache = None
        m2._adj_cache = None
        m2._adj_cache_max_weight = 0.0
        m2.FUSION_THRESHOLD = 5
        m2.MAX_CONNECTIONS = 0

        concepts = ["compression", "memory", "tokens"]

        m1.observe(concepts, arousal=0.0)
        m2.observe(concepts, arousal=0.9)

        # Get connection counts
        c1 = list(m1.data["connections"].values())
        c2 = list(m2.data["connections"].values())

        if c1 and c2:
            count_neutral = sum(c["count"] for c in c1)
            count_emotional = sum(c["count"] for c in c2)
            check("V6A.3", count_emotional > count_neutral,
                  f"emotional={count_emotional:.2f} > neutral={count_neutral:.2f}")
        else:
            check("V6A.3", False, "no connections created")


def test_v6a_4_no_explosion():
    """No numerical explosion with extreme arousal"""
    e = _hill(100.0)
    ok = 1.0 < e <= 2.001  # should cap near 2.0 (kappa=1.0)
    check("V6A.4", ok, f"E(100)={e:.6f}")


def test_v6a_5_backward_compat():
    """observe_text with arousal=0 works same as before (count=1 per pair)"""
    from mycelium import Mycelium
    m = Mycelium.__new__(Mycelium)
    m.data = {"connections": {}, "fusions": {}, "fillers": [], "stats": {}}
    m.repo_path = "."
    m.federated = False
    m.zone = "default"
    m.MIN_CONCEPT_LEN = 3
    m._db = None
    m._high_degree_cache = None
    m._adj_cache = None
    m._adj_cache_max_weight = 0.0
    m.FUSION_THRESHOLD = 5
    m.MAX_CONNECTIONS = 0

    m.observe(["alpha", "beta", "gamma"], arousal=0.0)
    counts = [c["count"] for c in m.data["connections"].values()]
    all_one = all(abs(c - 1.0) < 1e-10 for c in counts)
    check("V6A.5", all_one, f"counts={counts}")


def test_v6a_6_hill_switch():
    """Hill switch is sharp around theta=0.5"""
    e_low = _hill(0.2)   # below theta
    e_mid = _hill(0.5)   # at theta
    e_high = _hill(0.8)  # above theta
    # At theta, Hill = 0.5 -> E = 1.5
    # Below theta, much less; above theta, much more
    ok = (e_low < 1.1 and abs(e_mid - 1.5) < 0.01 and e_high > 1.8)
    check("V6A.6", ok,
          f"E(0.2)={e_low:.4f} E(0.5)={e_mid:.4f} E(0.8)={e_high:.4f}")


if __name__ == "__main__":
    print("=== V6A Emotional Tagging — 6 bornes ===")
    test_v6a_1_no_boost()
    test_v6a_2_max_boost()
    test_v6a_3_mycelium_weight()
    test_v6a_4_no_explosion()
    test_v6a_5_backward_compat()
    test_v6a_6_hill_switch()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
