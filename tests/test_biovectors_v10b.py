"""V10B — Russell circumplex affect mapping: strict validation bornes.

Paper: Russell 1980, J Personality and Social Psychology.
Formula: theta = atan2(a, v), r = sqrt(v^2 + a^2)

Tests:
  V10B.1  Positive valence, high arousal = Q1 (excited)
  V10B.2  Negative valence, high arousal = Q2 (tense)
  V10B.3  Negative valence, low arousal = Q3 (sad)
  V10B.4  Positive valence, low arousal = Q4 (calm)
  V10B.5  Origin (0,0) = zero intensity
  V10B.6  r is clamped to [0, 1]
  V10B.7  theta is in [-pi, +pi]
"""
import sys, os, math
from sentiment import circumplex_map

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


def test_v10b_1_q1():
    """Positive valence + high arousal = Q1"""
    r = circumplex_map(0.8, 0.7)
    check("V10B.1", r["quadrant"] == "Q1",
          f"quadrant={r['quadrant']}, label={r['label']}, r={r['r']}")


def test_v10b_2_q2():
    """Negative valence + high arousal = Q2"""
    r = circumplex_map(-0.8, 0.7)
    check("V10B.2", r["quadrant"] == "Q2",
          f"quadrant={r['quadrant']}, label={r['label']}")


def test_v10b_3_q3():
    """Negative valence + low arousal = Q3"""
    r = circumplex_map(-0.6, -0.5)
    check("V10B.3", r["quadrant"] == "Q3",
          f"quadrant={r['quadrant']}, label={r['label']}")


def test_v10b_4_q4():
    """Positive valence + low arousal = Q4"""
    r = circumplex_map(0.7, -0.4)
    check("V10B.4", r["quadrant"] == "Q4",
          f"quadrant={r['quadrant']}, label={r['label']}")


def test_v10b_5_origin():
    """(0,0) = zero intensity"""
    r = circumplex_map(0.0, 0.0)
    check("V10B.5", r["r"] == 0.0,
          f"r={r['r']}, theta={r['theta']}")


def test_v10b_6_clamped():
    """r is clamped to [0, 1]"""
    r = circumplex_map(1.0, 1.0)  # sqrt(2) > 1 -> clamped
    check("V10B.6", 0.0 <= r["r"] <= 1.0,
          f"r={r['r']} (clamped from sqrt(2))")


def test_v10b_7_theta_range():
    """theta in [-pi, +pi] for all inputs"""
    all_ok = True
    for v in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        for a in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            r = circumplex_map(v, a)
            if not (-math.pi - 0.001 <= r["theta"] <= math.pi + 0.001):
                all_ok = False
    check("V10B.7", all_ok, "all inputs -> theta in [-pi, +pi]")


if __name__ == "__main__":
    print("=== V10B Russell Circumplex — 7 bornes ===")
    test_v10b_1_q1()
    test_v10b_2_q2()
    test_v10b_3_q3()
    test_v10b_4_q4()
    test_v10b_5_origin()
    test_v10b_6_clamped()
    test_v10b_7_theta_range()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
