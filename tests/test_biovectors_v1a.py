"""V1A — Coupled oscillator arm control: strict validation bornes.

Paper: Yekutieli et al. 2005, J Neurophysiology.
Formula: tau_i = J*theta_ddot + B*theta_dot + K*theta + sum_j C_ij*(theta_i - theta_j)

Tests:
  V1A.1  Coupling pulls connected nodes toward each other
  V1A.2  No coupling (C=0): nodes independent
  V1A.3  Strong coupling: convergence to mean
  V1A.4  Damping (B>0): oscillations decay
  V1A.5  Spring (K>0): restoring force toward equilibrium
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


def oscillator_step(theta, theta_dot, neighbors, C=0.1, K=0.5, B=0.3, dt=0.1):
    """One step of coupled oscillator dynamics.
    theta: dict of node -> position
    theta_dot: dict of node -> velocity
    neighbors: dict of node -> [neighbor_ids]
    Returns: new theta, theta_dot
    """
    new_theta = {}
    new_theta_dot = {}
    for i in theta:
        coupling = sum(C * (theta[j] - theta[i]) for j in neighbors.get(i, []) if j in theta)
        spring = -K * theta[i]
        damping = -B * theta_dot[i]
        accel = spring + damping + coupling  # J=1
        new_theta_dot[i] = theta_dot[i] + accel * dt
        new_theta[i] = theta[i] + new_theta_dot[i] * dt
    return new_theta, new_theta_dot


def test_v1a_1_coupling():
    """Coupling pulls connected nodes toward each other"""
    t = {"A": 1.0, "B": 0.0}
    td = {"A": 0.0, "B": 0.0}
    n = {"A": ["B"], "B": ["A"]}
    t2, _ = oscillator_step(t, td, n, C=0.5, K=0.0, B=0.0)
    # A should decrease, B should increase (pulled toward each other)
    check("V1A.1", t2["A"] < t["A"] and t2["B"] > t["B"],
          f"A: {t['A']:.2f}->{t2['A']:.3f}, B: {t['B']:.2f}->{t2['B']:.3f}")


def test_v1a_2_no_coupling():
    """C=0: nodes evolve independently"""
    t = {"A": 1.0, "B": -1.0}
    td = {"A": 0.0, "B": 0.0}
    n = {"A": ["B"], "B": ["A"]}
    t2, _ = oscillator_step(t, td, n, C=0.0, K=0.5, B=0.0)
    # Both should move toward 0 independently (spring only)
    check("V1A.2", abs(t2["A"]) < abs(t["A"]) and abs(t2["B"]) < abs(t["B"]),
          f"A: {t['A']:.2f}->{t2['A']:.3f}, B: {t['B']:.2f}->{t2['B']:.3f}")


def test_v1a_3_convergence():
    """Strong coupling: nodes converge to same value"""
    t = {"A": 1.0, "B": 0.0, "C": 0.5}
    td = {"A": 0.0, "B": 0.0, "C": 0.0}
    n = {"A": ["B", "C"], "B": ["A", "C"], "C": ["A", "B"]}
    for _ in range(100):
        t, td = oscillator_step(t, td, n, C=1.0, K=0.1, B=0.8)
    spread = max(t.values()) - min(t.values())
    check("V1A.3", spread < 0.1,
          f"spread={spread:.4f}, values=[{t['A']:.4f}, {t['B']:.4f}, {t['C']:.4f}]")


def test_v1a_4_damping():
    """B>0: oscillations decay"""
    t = {"A": 1.0}
    td = {"A": 0.5}
    n = {}
    # Run with damping
    for _ in range(200):
        t, td = oscillator_step(t, td, n, C=0.0, K=0.5, B=0.5)
    check("V1A.4", abs(t["A"]) < 0.5 and abs(td["A"]) < 0.5,
          f"theta={t['A']:.4f}, velocity={td['A']:.4f} (damped)")


def test_v1a_5_spring():
    """K>0: restoring force pulls toward 0"""
    t = {"A": 2.0}
    td = {"A": 0.0}
    n = {}
    t2, td2 = oscillator_step(t, td, n, C=0.0, K=1.0, B=0.0)
    # Spring should pull A toward 0
    check("V1A.5", abs(t2["A"]) < abs(t["A"]),
          f"A: {t['A']:.2f}->{t2['A']:.3f} (spring restoring)")


if __name__ == "__main__":
    print("=== V1A Coupled Oscillator — 5 bornes ===")
    test_v1a_1_coupling()
    test_v1a_2_no_coupling()
    test_v1a_3_convergence()
    test_v1a_4_damping()
    test_v1a_5_spring()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
