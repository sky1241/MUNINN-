"""B5 -- Session mode detection (convergent/divergent): strict validation bornes.

Tests:
  B5.1  Divergent: many unique concepts -> mode=divergent, k=5
  B5.2  Convergent: repeated concepts -> mode=convergent, k=20
  B5.3  Balanced: mixed -> mode=balanced, k=10
  B5.4  Empty: returns balanced default
  B5.5  Output keys: mode, diversity, suggested_k, concept_count
"""
import sys, os
def test_b5_1_divergent():
    """Many unique concepts = divergent mode"""
    import muninn
    # 20 unique concepts, 20 total = diversity=1.0
    concepts = [f"concept_{i}" for i in range(20)]
    result = muninn.detect_session_mode(concepts)
    assert result["mode"] == "divergent", f"B5.1 FAIL: mode={result['mode']}"
    assert result["suggested_k"] == 5, f"B5.1 FAIL: k={result['suggested_k']}"
    assert result["diversity"] > 0.6, f"B5.1 FAIL: diversity={result['diversity']}"
    print(f"  B5.1 PASS: divergent mode (diversity={result['diversity']}, k={result['suggested_k']})")

def test_b5_2_convergent():
    """Repeated concepts = convergent mode"""
    import muninn
    # 3 unique concepts repeated 10 times each = diversity=3/30=0.1
    concepts = ["debug", "error", "fix"] * 10
    result = muninn.detect_session_mode(concepts)
    assert result["mode"] == "convergent", f"B5.2 FAIL: mode={result['mode']}"
    assert result["suggested_k"] == 20, f"B5.2 FAIL: k={result['suggested_k']}"
    assert result["diversity"] < 0.4, f"B5.2 FAIL: diversity={result['diversity']}"
    print(f"  B5.2 PASS: convergent mode (diversity={result['diversity']}, k={result['suggested_k']})")

def test_b5_3_balanced():
    """Mixed concepts = balanced mode"""
    import muninn
    # 5 unique in 10 total = diversity=0.5
    concepts = ["alpha", "beta", "gamma", "delta", "epsilon",
                "alpha", "beta", "gamma", "delta", "epsilon"]
    result = muninn.detect_session_mode(concepts)
    assert result["mode"] == "balanced", f"B5.3 FAIL: mode={result['mode']}"
    assert result["suggested_k"] == 10, f"B5.3 FAIL: k={result['suggested_k']}"
    print(f"  B5.3 PASS: balanced mode (diversity={result['diversity']}, k={result['suggested_k']})")

def test_b5_4_empty():
    """Empty concepts with no session index = balanced default"""
    import muninn, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / ".muninn").mkdir()
        old_repo = muninn._REPO_PATH
        muninn._REPO_PATH = repo
        result = muninn.detect_session_mode([])
        muninn._REPO_PATH = old_repo
    assert result["mode"] == "balanced", f"B5.4 FAIL: mode={result['mode']}"
    assert result["concept_count"] == 0, f"B5.4 FAIL: count={result['concept_count']}"
    print(f"  B5.4 PASS: empty concepts returns balanced default")

def test_b5_5_keys():
    """Output should have exactly the expected keys"""
    import muninn
    result = muninn.detect_session_mode(["test"])
    expected_keys = {"mode", "diversity", "suggested_k", "concept_count"}
    assert set(result.keys()) == expected_keys, f"B5.5 FAIL: keys={set(result.keys())}"
    print(f"  B5.5 PASS: output keys = {{mode, diversity, suggested_k, concept_count}}")

if __name__ == "__main__":
    print("=== B5 -- Session mode detection: validation bornes ===")
    test_b5_1_divergent()
    test_b5_2_convergent()
    test_b5_3_balanced()
    test_b5_4_empty()
    test_b5_5_keys()
    print("\n  ALL B5 BORNES PASSED")
