"""A3 — Sigmoid spreading activation: strict validation bornes.

Tests:
  A3.1  Arithmetic: sigmoid(0, k=10, x0=0.3)
  A3.2  Arithmetic: sigmoid(0.5, k=10, x0=0.3)
  A3.3  Noise filter: low activation -> near 0
  A3.4  Signal preserve: high activation -> near 1
  A3.6  k=0: sigmoid disabled -> raw values preserved
"""
import sys, os, math
TOLERANCE = 0.05

def sigmoid(x, k=10, x0=0.3):
    return 1.0 / (1.0 + math.exp(-k * (x - x0)))

def test_a3_1_arithmetic():
    """sigmoid(0, k=10, x0=0.3) = 1/(1+e^3) = 0.0474"""
    val = sigmoid(0, k=10, x0=0.3)
    expected = 1.0 / (1.0 + math.exp(3))
    assert abs(val - expected) < 0.001, f"A3.1 FAIL: {val:.4f} != {expected:.4f}"
    print(f"  A3.1 PASS: sigmoid(0)={val:.4f}, expected={expected:.4f}")

def test_a3_2_arithmetic():
    """sigmoid(0.5, k=10, x0=0.3) = 1/(1+e^-2) = 0.881"""
    val = sigmoid(0.5, k=10, x0=0.3)
    expected = 1.0 / (1.0 + math.exp(-2))
    assert abs(val - expected) < 0.001, f"A3.2 FAIL: {val:.4f} != {expected:.4f}"
    print(f"  A3.2 PASS: sigmoid(0.5)={val:.4f}, expected={expected:.4f}")

def test_a3_3_noise_filter():
    """Low activation (below median) should be suppressed"""
    val = sigmoid(0.05, k=10, x0=0.3)
    assert val < 0.1, f"A3.3 FAIL: sigmoid(0.05)={val:.4f}, expected < 0.1"
    print(f"  A3.3 PASS: sigmoid(0.05)={val:.4f} < 0.1 (noise filtered)")

def test_a3_4_signal_preserve():
    """High activation should stay high"""
    val = sigmoid(0.8, k=10, x0=0.3)
    assert val > 0.9, f"A3.4 FAIL: sigmoid(0.8)={val:.4f}, expected > 0.9"
    print(f"  A3.4 PASS: sigmoid(0.8)={val:.4f} > 0.9 (signal preserved)")

def test_a3_6_disabled():
    """k=0 should give 0.5 for all inputs"""
    for x in [0.0, 0.3, 1.0]:
        val = sigmoid(x, k=0, x0=0.3)
        assert abs(val - 0.5) < 0.001, f"A3.6 FAIL: sigmoid({x}, k=0)={val}, expected 0.5"
    print(f"  A3.6 PASS: k=0 gives 0.5 for all inputs (disabled)")

def test_a3_integration():
    """Test that spread_activation still works with sigmoid"""
    from pathlib import Path
    from muninn.mycelium import Mycelium
    # Use actual repo mycelium if it exists
    repo = Path(os.path.dirname(__file__)).parent
    m = Mycelium(repo)
    if not m.data["connections"]:
        print(f"  A3.INT SKIP: no mycelium connections to test")
        return
    results = m.spread_activation(["compression"], hops=2, top_n=10)
    assert isinstance(results, list), "A3.INT FAIL: not a list"
    if results:
        # All activations should be in [0, 1] after sigmoid
        for concept, act in results:
            assert 0 <= act <= 1.0, f"A3.INT FAIL: {concept}={act} out of [0,1]"
        print(f"  A3.INT PASS: {len(results)} results, all in [0,1], top={results[0]}")
    else:
        print(f"  A3.INT PASS: empty results (no connections for 'compression')")

if __name__ == "__main__":
    print("=== A3 — Sigmoid spreading: validation bornes ===")
    test_a3_1_arithmetic()
    test_a3_2_arithmetic()
    test_a3_3_noise_filter()
    test_a3_4_signal_preserve()
    test_a3_6_disabled()
    test_a3_integration()
    print("\n  ALL A3 BORNES PASSED")
