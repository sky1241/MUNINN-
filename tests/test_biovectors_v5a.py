"""V5A — Quorum sensing Hill switch: strict validation bornes.

Paper: Waters & Bassler 2005, Annual Review of Cell and Developmental Biology.
Formula: f(A) = A^n / (K^n + A^n)

Tests:
  V5A.1  Below threshold (A < K): output < 0.5
  V5A.2  At threshold (A = K): output = 0.5
  V5A.3  Above threshold (A > K): output > 0.5
  V5A.4  n=1 (Michaelis-Menten): gentle sigmoid
  V5A.5  n=10 (ultra-sensitive): near-step function
  V5A.6  A=0: output = 0 (no quorum)
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


def hill_gate(A, K=2.0, n=3):
    """Hill function quorum gate: f(A) = A^n / (K^n + A^n)"""
    if A <= 0:
        return 0.0
    return (A ** n) / (K ** n + A ** n)


def test_v5a_1_below_threshold():
    """A < K -> output < 0.5"""
    f = hill_gate(1.0, K=2.0, n=3)
    check("V5A.1", f < 0.5, f"f(1)={f:.4f} < 0.5")


def test_v5a_2_at_threshold():
    """A = K -> output = 0.5"""
    f = hill_gate(2.0, K=2.0, n=3)
    check("V5A.2", abs(f - 0.5) < 1e-10, f"f(K)={f:.10f}")


def test_v5a_3_above_threshold():
    """A > K -> output > 0.5"""
    f = hill_gate(4.0, K=2.0, n=3)
    check("V5A.3", f > 0.5, f"f(4)={f:.4f} > 0.5")


def test_v5a_4_gentle():
    """n=1: gentle Michaelis-Menten curve"""
    f_low = hill_gate(0.5, K=2.0, n=1)
    f_high = hill_gate(4.0, K=2.0, n=1)
    # n=1 is gentle: f(0.5) = 0.2, f(4) = 0.667
    check("V5A.4", f_low > 0.1 and f_high < 0.8,
          f"f(0.5)={f_low:.4f}, f(4)={f_high:.4f} (gentle)")


def test_v5a_5_ultrasensitive():
    """n=10: near-step function"""
    f_low = hill_gate(1.5, K=2.0, n=10)
    f_high = hill_gate(2.5, K=2.0, n=10)
    # n=10 is sharp: f(1.5) very small, f(2.5) very high
    check("V5A.5", f_low < 0.1 and f_high > 0.9,
          f"f(1.5)={f_low:.4f} < 0.1, f(2.5)={f_high:.4f} > 0.9")


def test_v5a_6_zero():
    """A=0: output = 0"""
    f = hill_gate(0.0, K=2.0, n=3)
    check("V5A.6", f == 0.0, f"f(0)={f}")


if __name__ == "__main__":
    print("=== V5A Quorum Sensing Hill Switch — 6 bornes ===")
    test_v5a_1_below_threshold()
    test_v5a_2_at_threshold()
    test_v5a_3_above_threshold()
    test_v5a_4_gentle()
    test_v5a_5_ultrasensitive()
    test_v5a_6_zero()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
