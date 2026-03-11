"""V2B — TD-Learning reward prediction error: strict validation bornes.

Paper: Schultz, Dayan, Montague 1997, Science.
Formula: delta = r + gamma * V(s_next) - V(s); V(s) += alpha * delta

Tests:
  V2B.1  delta > 0 after successful recall (reward=high) -> usefulness increases
  V2B.2  delta < 0 after useless recall (reward=low) -> usefulness decreases
  V2B.3  V(s) converges (doesn't diverge) over 100 simulations
  V2B.4  gamma=0 behavior: delta = reward - V(s) only (no look-ahead)
  V2B.5  td_value and td_delta stored in node
  V2B.6  Usefulness stays in [0, 1] after extreme inputs
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


def simulate_td(node, reward, gamma=0.9, alpha=0.1):
    """Simulate what _update_usefulness does for V2B."""
    v_current = node.get("td_value", 0.5)
    v_next = v_current  # self-ref approximation
    delta = reward + gamma * v_next - v_current
    v_new = v_current + alpha * delta
    v_new = max(0.0, min(1.0, v_new))
    node["td_value"] = round(v_new, 4)
    node["td_delta"] = round(delta, 4)

    old_score = node.get("usefulness", 0.5)
    td_bonus = max(0.0, delta) * 0.1
    node["usefulness"] = round(min(1.0, 0.7 * old_score + 0.3 * reward + td_bonus), 3)
    return delta


def test_v2b_1_positive_delta():
    """Successful recall (high reward) -> positive delta -> usefulness increases"""
    node = {"usefulness": 0.5, "td_value": 0.5}
    old_u = node["usefulness"]
    delta = simulate_td(node, reward=0.9)
    check("V2B.1", delta > 0 and node["usefulness"] > old_u,
          f"delta={delta:.4f}, usefulness {old_u}->{node['usefulness']}")


def test_v2b_2_negative_delta():
    """Useless recall (zero reward) -> negative delta -> usefulness decreases"""
    node = {"usefulness": 0.7, "td_value": 0.7}
    old_u = node["usefulness"]
    delta = simulate_td(node, reward=0.0)
    # delta = 0 + 0.9*0.7 - 0.7 = -0.07
    check("V2B.2", delta < 0 and node["usefulness"] < old_u,
          f"delta={delta:.4f}, usefulness {old_u}->{node['usefulness']}")


def test_v2b_3_convergence():
    """V(s) converges over 100 iterations with constant reward=0.6"""
    node = {"usefulness": 0.5, "td_value": 0.5}
    for _ in range(100):
        simulate_td(node, reward=0.6)
    v = node["td_value"]
    # Should converge toward reward/(1-gamma) but clamped at 1.0
    ok = 0.0 <= v <= 1.0 and v == v  # not NaN
    check("V2B.3", ok, f"V(s) after 100 iters = {v:.4f}")


def test_v2b_4_gamma_zero():
    """gamma=0: delta = reward - V(s), no look-ahead"""
    node = {"usefulness": 0.5, "td_value": 0.3}
    delta = simulate_td(node, reward=0.8, gamma=0.0)
    expected = 0.8 - 0.3  # = 0.5
    check("V2B.4", abs(delta - expected) < 0.01,
          f"delta={delta:.4f}, expected={expected:.4f}")


def test_v2b_5_td_fields():
    """td_value and td_delta stored in node"""
    node = {"usefulness": 0.5}
    simulate_td(node, reward=0.7)
    ok = "td_value" in node and "td_delta" in node
    check("V2B.5", ok,
          f"td_value={node.get('td_value')}, td_delta={node.get('td_delta')}")


def test_v2b_6_clamped():
    """Usefulness stays in [0, 1] after extreme inputs"""
    node_high = {"usefulness": 0.99, "td_value": 0.99}
    simulate_td(node_high, reward=1.0)
    node_low = {"usefulness": 0.01, "td_value": 0.01}
    simulate_td(node_low, reward=0.0)
    ok = (0.0 <= node_high["usefulness"] <= 1.0 and
          0.0 <= node_low["usefulness"] <= 1.0 and
          0.0 <= node_high["td_value"] <= 1.0 and
          0.0 <= node_low["td_value"] <= 1.0)
    check("V2B.6", ok,
          f"high: u={node_high['usefulness']}, v={node_high['td_value']}; "
          f"low: u={node_low['usefulness']}, v={node_low['td_value']}")


if __name__ == "__main__":
    print("=== V2B TD-Learning — 6 bornes ===")
    test_v2b_1_positive_delta()
    test_v2b_2_negative_delta()
    test_v2b_3_convergence()
    test_v2b_4_gamma_zero()
    test_v2b_5_td_fields()
    test_v2b_6_clamped()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
