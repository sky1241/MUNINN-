"""V9A — Bioelectric gap junction regeneration: strict validation bornes.

Paper: Shomrat & Levin 2013, J Exp Biol.
Also: Levin 2012, BioEssays.
Formula: dV_i/dt = -g_leak*(V_i - E_leak) + sum_j g_gap*(V_j - V_i) + I_ion

Tests:
  V9A.1  Diffusion formula: neighbors converge toward dead node's value
  V9A.2  Leak: isolated node decays to E_leak
  V9A.3  Gap junction: connected nodes share state
  V9A.4  Multiple iterations -> convergence
  V9A.5  Regeneration preserves total information (conservation)
  V9A.6  Empty neighbors: no diffusion, no crash
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


def gap_junction_step(V, neighbors, g_leak=0.1, E_leak=0.0, g_gap=0.3):
    """One step of bioelectric gap junction diffusion.
    V: dict of node_id -> voltage (state value)
    neighbors: dict of node_id -> [neighbor_ids]
    Returns new V dict.
    """
    V_new = {}
    for i in V:
        leak = -g_leak * (V[i] - E_leak)
        gap = sum(g_gap * (V[j] - V[i]) for j in neighbors.get(i, []) if j in V)
        V_new[i] = V[i] + leak + gap
    return V_new


def test_v9a_1_diffusion():
    """Neighbors converge toward dead node's value via gap junctions"""
    # Node A=1.0 (dead), B=0.0, C=0.0. B and C connected to A.
    V = {"A": 1.0, "B": 0.0, "C": 0.0}
    neighbors = {"A": ["B", "C"], "B": ["A"], "C": ["A"]}
    V2 = gap_junction_step(V, neighbors, g_gap=0.3, g_leak=0.0)
    # B and C should increase toward A's value
    check("V9A.1", V2["B"] > 0 and V2["C"] > 0,
          f"B: {V['B']:.2f}->{V2['B']:.3f}, C: {V['C']:.2f}->{V2['C']:.3f}")


def test_v9a_2_leak():
    """Isolated node decays to E_leak"""
    V = {"A": 1.0}
    neighbors = {"A": []}
    for _ in range(20):
        V = gap_junction_step(V, neighbors, g_leak=0.1, E_leak=0.0)
    check("V9A.2", abs(V["A"]) < 0.15,
          f"after 20 steps: V={V['A']:.4f} (decayed toward 0)")


def test_v9a_3_gap_sharing():
    """Connected nodes share state via gap junctions"""
    V = {"A": 1.0, "B": 0.0}
    neighbors = {"A": ["B"], "B": ["A"]}
    V2 = gap_junction_step(V, neighbors, g_gap=0.3, g_leak=0.0)
    # A should decrease, B should increase
    check("V9A.3", V2["A"] < V["A"] and V2["B"] > V["B"],
          f"A: {V['A']:.2f}->{V2['A']:.3f}, B: {V['B']:.2f}->{V2['B']:.3f}")


def test_v9a_4_convergence():
    """Multiple iterations -> nodes converge to same value"""
    V = {"A": 1.0, "B": 0.0, "C": 0.5}
    neighbors = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    for _ in range(50):
        V = gap_junction_step(V, neighbors, g_gap=0.2, g_leak=0.01, E_leak=0.0)
    values = list(V.values())
    spread = max(values) - min(values)
    check("V9A.4", spread < 0.05,
          f"after 50 steps: spread={spread:.4f}, values={[round(v,4) for v in values]}")


def test_v9a_5_conservation():
    """Regeneration preserves total information when g_leak=0"""
    V = {"A": 1.0, "B": 0.0, "C": 0.0}
    neighbors = {"A": ["B", "C"], "B": ["A"], "C": ["A"]}
    total_before = sum(V.values())
    V = gap_junction_step(V, neighbors, g_gap=0.3, g_leak=0.0)
    total_after = sum(V.values())
    check("V9A.5", abs(total_before - total_after) < 1e-10,
          f"before={total_before:.4f}, after={total_after:.4f}")


def test_v9a_6_empty_neighbors():
    """No neighbors: no diffusion, no crash"""
    V = {"A": 0.8}
    neighbors = {}
    V2 = gap_junction_step(V, neighbors, g_gap=0.3, g_leak=0.1, E_leak=0.0)
    ok = "A" in V2 and V2["A"] == V2["A"]  # not NaN
    check("V9A.6", ok, f"A={V2['A']:.4f} (leak only, no crash)")


if __name__ == "__main__":
    print("=== V9A Bioelectric Gap Junction Regeneration — 6 bornes ===")
    test_v9a_1_diffusion()
    test_v9a_2_leak()
    test_v9a_3_gap_sharing()
    test_v9a_4_convergence()
    test_v9a_5_conservation()
    test_v9a_6_empty_neighbors()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
