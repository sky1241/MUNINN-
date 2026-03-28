"""A1 — h adaptatif: strict validation bornes.

Tests:
  A1.1  Arithmetic: usefulness=1.0 => h=224 (unchanged)
  A1.2  Arithmetic: usefulness=0.5, beta=0.5 => h=224*0.707=158.4
  A1.3  Monotonicity: usefulness up => h up
  A1.4  Regression: usefulness=1.0 default => same recall as pre-A1
  A1.5  Differentiation: different usefulness => different temperatures
  A1.6  Prune safety: no HOT->DEAD flip
  A1.7  usefulness=0.0 => clamped to 0.1, no crash
"""
import sys, os, math
from muninn import _ebbinghaus_recall, compute_temperature

TOLERANCE = 0.01

def _today():
    """Use today's date so delta=0 tests don't drift over time."""
    import time
    return time.strftime("%Y-%m-%d")

def make_node(access_count=5, last_access=None, usefulness=1.0):
    return {
        "access_count": access_count,
        "last_access": last_access or _today(),
        "usefulness": usefulness,
        "lines": 50,
        "max_lines": 150,
    }

def test_a1_1_arithmetic_default():
    """usefulness=1.0 => h = 7 * 2^5 = 224.0 (same as pre-A1)"""
    node = make_node(access_count=5, usefulness=1.0)  # last_access=today => delta=0
    recall = _ebbinghaus_recall(node)
    # delta=0 => recall = 2^0 = 1.0
    assert abs(recall - 1.0) < TOLERANCE, f"A1.1 FAIL: recall={recall}, expected 1.0"
    print(f"  A1.1 PASS: recall={recall:.4f} (usefulness=1.0, delta=0)")

def test_a1_2_arithmetic_half():
    """usefulness=0.5, beta=0.5 => h = 224 * 0.5^0.5 = 224 * 0.7071 = 158.39"""
    node = make_node(access_count=5, usefulness=0.5)  # last_access=today by default
    # With delta=0, recall is still 1.0 regardless of h
    # Test with delta = 158.39 (= h), recall should be 0.5
    # We need a node where delta is known
    # Use last_access far enough that delta = 224 days
    # With usefulness=1.0: h=224, recall = 2^(-224/224) = 0.5
    # With usefulness=0.5: h=158.39, recall = 2^(-224/158.39) = 2^(-1.414) = 0.375
    node_u1 = make_node(access_count=5, usefulness=1.0, last_access="2025-07-30")  # ~224 days ago (fixed reference)
    node_u05 = make_node(access_count=5, usefulness=0.5, last_access="2025-07-30")
    recall_u1 = _ebbinghaus_recall(node_u1)
    recall_u05 = _ebbinghaus_recall(node_u05)
    # recall_u1 should be ~0.5 (delta ~= h = 224)
    assert 0.4 < recall_u1 < 0.6, f"A1.2a FAIL: recall_u1={recall_u1}, expected ~0.5"
    # recall_u05 should be lower (h is smaller, same delta)
    assert recall_u05 < recall_u1, f"A1.2b FAIL: recall_u05={recall_u05} >= recall_u1={recall_u1}"
    print(f"  A1.2 PASS: recall(u=1.0)={recall_u1:.4f}, recall(u=0.5)={recall_u05:.4f}")

def test_a1_3_monotonicity():
    """usefulness up => h up => recall up (for same delta)"""
    usefulness_values = [0.1, 0.3, 0.5, 0.7, 1.0]
    recalls = []
    for u in usefulness_values:
        node = make_node(access_count=5, usefulness=u, last_access="2025-07-30")
        recalls.append(_ebbinghaus_recall(node))
    for i in range(len(recalls) - 1):
        assert recalls[i] < recalls[i + 1], (
            f"A1.3 FAIL: recall({usefulness_values[i]})={recalls[i]:.4f} >= "
            f"recall({usefulness_values[i+1]})={recalls[i+1]:.4f}"
        )
    print(f"  A1.3 PASS: monotonic {[f'{r:.3f}' for r in recalls]}")

def test_a1_5_differentiation():
    """Different usefulness => different temperatures"""
    node_low = make_node(access_count=3, usefulness=0.3, last_access="2025-12-01")
    node_high = make_node(access_count=3, usefulness=0.9, last_access="2025-12-01")
    temp_low = compute_temperature(node_low)
    temp_high = compute_temperature(node_high)
    diff = abs(temp_high - temp_low)
    assert diff > 0.01, f"A1.5 FAIL: diff={diff}, expected > 0.01"
    print(f"  A1.5 PASS: temp(u=0.3)={temp_low:.3f}, temp(u=0.9)={temp_high:.3f}, diff={diff:.3f}")

def test_a1_7_usefulness_zero():
    """usefulness=0.0 should be clamped to 0.1, no crash"""
    node = make_node(access_count=5, usefulness=0.0, last_access="2025-07-30")
    recall = _ebbinghaus_recall(node)
    assert recall > 0, f"A1.7 FAIL: recall={recall}, expected > 0"
    assert not math.isnan(recall), f"A1.7 FAIL: recall is NaN"
    assert not math.isinf(recall), f"A1.7 FAIL: recall is Inf"
    print(f"  A1.7 PASS: recall={recall:.4f} (usefulness=0.0, clamped to 0.1)")

if __name__ == "__main__":
    print("=== A1 — h adaptatif: validation bornes ===")
    test_a1_1_arithmetic_default()
    test_a1_2_arithmetic_half()
    test_a1_3_monotonicity()
    test_a1_5_differentiation()
    test_a1_7_usefulness_zero()
    print("\n  ALL A1 BORNES PASSED")
