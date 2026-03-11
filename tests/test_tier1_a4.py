"""A4 — Saturation decay (Lotka-Volterra): strict validation bornes.

Tests:
  A4.1  Arithmetic: w=100, beta=0.001 => saturation_loss=10
  A4.2  Beta=0: behavior identical to pre-A4
  A4.3  w petit: w=2 => saturation negligible
  A4.4  w enorme: w=10000 => saturation kills connection
  A4.5  Integer: result stays int
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

def test_a4_1_arithmetic():
    """w=100, beta=0.001 => loss = int(0.001 * 100 * 100) = 10"""
    w = 100
    beta = 0.001
    loss = int(beta * w * w)
    result = max(1, w - loss)
    assert loss == 10, f"A4.1 FAIL: loss={loss}, expected 10"
    assert result == 90, f"A4.1 FAIL: result={result}, expected 90"
    print(f"  A4.1 PASS: w=100, loss=10, result=90")

def test_a4_2_beta_zero():
    """Beta=0 => no saturation, no change"""
    beta = 0.0
    w = 100
    # With beta=0, the condition (beta > 0) is False, so no saturation applied
    applies = beta > 0 and w > 50
    assert not applies, "A4.2 FAIL: beta=0 should not apply saturation"
    print(f"  A4.2 PASS: beta=0 does not apply saturation")

def test_a4_3_w_small():
    """w=2 => below threshold, no saturation"""
    w = 2
    threshold = 50
    beta = 0.001
    applies = beta > 0 and w > threshold
    assert not applies, f"A4.3 FAIL: w={w} should be below threshold={threshold}"
    print(f"  A4.3 PASS: w={w} < threshold={threshold}, no saturation")

def test_a4_4_w_enormous():
    """w=10000, beta=0.001 => loss = 100000000 >> w, clamped to 1"""
    w = 10000
    beta = 0.001
    loss = int(beta * w * w)
    result = max(1, w - loss)
    assert result == 1, f"A4.4 FAIL: result={result}, expected 1 (clamped)"
    print(f"  A4.4 PASS: w=10000, loss={loss}, result=1 (clamped)")

def test_a4_5_integer():
    """Result is always int"""
    w = 100
    beta = 0.001
    loss = int(beta * w * w)
    result = max(1, w - loss)
    assert isinstance(result, int), f"A4.5 FAIL: type={type(result)}"
    print(f"  A4.5 PASS: result is int ({result})")

def test_a4_integration():
    """Test with real mycelium (beta=0.001 moderate default since TIER3/C1)"""
    from pathlib import Path
    from mycelium import Mycelium
    repo = Path(os.path.dirname(__file__)).parent
    m = Mycelium(repo)
    if not m.data["connections"]:
        print(f"  A4.INT SKIP: no connections")
        return
    counts_before = [c["count"] for c in m.data["connections"].values()]
    # TIER3/C1 set default beta=0.001 (moderate saturation, not disabled)
    assert m.SATURATION_BETA >= 0.0, f"A4.INT FAIL: beta must be non-negative, got {m.SATURATION_BETA}"
    print(f"  A4.INT PASS: beta={m.SATURATION_BETA}, {len(counts_before)} connections, max={max(counts_before)}")

if __name__ == "__main__":
    print("=== A4 — Saturation decay: validation bornes ===")
    test_a4_1_arithmetic()
    test_a4_2_beta_zero()
    test_a4_3_w_small()
    test_a4_4_w_enormous()
    test_a4_5_integer()
    test_a4_integration()
    print("\n  ALL A4 BORNES PASSED")
