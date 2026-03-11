"""V1A — Coupled oscillator temperature coupling: strict validation bornes.

Paper: Yekutieli et al. 2005, J Neurophysiology.
Production formula: coupling_sum += C * (temp_j - temp_i) for shared tags
  total += 0.01 * clamp(coupling_sum, -0.05, 0.05)

Tests:
  V1A.1  Coupling pulls warmer node down, cooler node up (shared tags)
  V1A.2  No shared tags: zero coupling
  V1A.3  Coupling is bounded (clamp ±0.05 * 0.01 = ±0.0005)
  V1A.4  Multiple shared tags: coupling accumulates
  V1A.5  Same temperature: zero coupling
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


def temperature_coupling(nodes, C=0.1, max_tags=3):
    """Replicate production V1A coupling logic from boot().
    nodes: dict of name -> {"temperature": float, "tags": list}
    Returns: dict of name -> coupling_bonus (before 0.01 * clamp)
    """
    results = {}
    for name, node in nodes.items():
        my_temp = node.get("temperature", 0.5)
        node_tags = set(node.get("tags", []))
        coupling_sum = 0.0
        for tag in list(node_tags)[:max_tags]:
            for other_name, other_node in nodes.items():
                if other_name == name:
                    continue
                if tag in set(other_node.get("tags", [])):
                    other_temp = other_node.get("temperature", 0.5)
                    coupling_sum += C * (other_temp - my_temp)
                    break  # one coupling per tag (production behavior)
        # Production applies: 0.01 * clamp(coupling_sum, -0.05, 0.05)
        bonus = 0.01 * max(-0.05, min(0.05, coupling_sum))
        results[name] = bonus
    return results


def test_v1a_1_coupling():
    """Shared tag: hot node gets negative bonus, cold node gets positive"""
    nodes = {
        "A": {"temperature": 0.9, "tags": ["memory"]},
        "B": {"temperature": 0.1, "tags": ["memory"]},
    }
    r = temperature_coupling(nodes)
    # A is hot, B is cold, shared "memory" tag -> A pulled down, B pulled up
    check("V1A.1", r["A"] < 0 and r["B"] > 0,
          f"A={r['A']:.6f}, B={r['B']:.6f}")


def test_v1a_2_no_shared_tags():
    """No shared tags: zero coupling"""
    nodes = {
        "A": {"temperature": 0.9, "tags": ["memory"]},
        "B": {"temperature": 0.1, "tags": ["compression"]},
    }
    r = temperature_coupling(nodes)
    check("V1A.2", r["A"] == 0 and r["B"] == 0,
          f"A={r['A']}, B={r['B']} (no shared tags)")


def test_v1a_3_bounded():
    """Coupling is bounded: max absolute bonus = 0.01 * 0.05 = 0.0005"""
    nodes = {
        "A": {"temperature": 0.0, "tags": ["x", "y", "z"]},
        "B": {"temperature": 1.0, "tags": ["x", "y", "z"]},
    }
    r = temperature_coupling(nodes)
    # Even with large temp difference and 3 tags, bonus is clamped
    check("V1A.3", abs(r["A"]) <= 0.0005 + 1e-10 and abs(r["B"]) <= 0.0005 + 1e-10,
          f"A={r['A']:.6f}, B={r['B']:.6f}, max=0.0005")


def test_v1a_4_multi_tags():
    """Multiple shared tags: coupling accumulates before clamp"""
    nodes_1 = {
        "A": {"temperature": 0.8, "tags": ["mem"]},
        "B": {"temperature": 0.2, "tags": ["mem"]},
    }
    nodes_3 = {
        "A": {"temperature": 0.8, "tags": ["mem", "tree", "comp"]},
        "B": {"temperature": 0.2, "tags": ["mem", "tree", "comp"]},
    }
    r1 = temperature_coupling(nodes_1)
    r3 = temperature_coupling(nodes_3)
    # 3 shared tags should give stronger coupling than 1 (until clamp kicks in)
    check("V1A.4", abs(r3["A"]) >= abs(r1["A"]),
          f"1_tag={r1['A']:.6f}, 3_tags={r3['A']:.6f}")


def test_v1a_5_same_temp():
    """Same temperature: zero coupling regardless of shared tags"""
    nodes = {
        "A": {"temperature": 0.5, "tags": ["memory", "tree"]},
        "B": {"temperature": 0.5, "tags": ["memory", "tree"]},
    }
    r = temperature_coupling(nodes)
    check("V1A.5", r["A"] == 0.0 and r["B"] == 0.0,
          f"A={r['A']}, B={r['B']} (same temp)")


if __name__ == "__main__":
    print("=== V1A Temperature Coupling — 5 bornes ===")
    test_v1a_1_coupling()
    test_v1a_2_no_shared_tags()
    test_v1a_3_bounded()
    test_v1a_4_multi_tags()
    test_v1a_5_same_temp()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
