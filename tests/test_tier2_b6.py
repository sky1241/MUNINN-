"""B6 -- Klein RPD session-type classification: strict validation bornes.

Tests:
  B6.1  Debug session: E> tags dominant
  B6.2  Feature session: D> tags + high diversity
  B6.3  Review session: B> and F> tags dominant
  B6.4  Empty input: returns unknown
  B6.5  Output keys: type, confidence, tag_profile
  B6.6  Confidence in [0, 1]
"""
import sys, os
def test_b6_1_debug():
    """Session with many E> tags = debug"""
    import muninn
    concepts = ["error", "fix", "bug", "error", "fix"]
    tagged = ["E> TypeError in line 42", "E> IndexError on boot", "E> fix: add None check",
              "D> decision: use try/except"]
    result = muninn.classify_session(concepts, tagged)
    assert result["type"] == "debug", f"B6.1 FAIL: type={result['type']}"
    assert result["tag_profile"]["E"] == 3, f"B6.1 FAIL: E count={result['tag_profile']['E']}"
    print(f"  B6.1 PASS: debug session (confidence={result['confidence']:.2f})")

def test_b6_2_feature():
    """Session with D> tags + high diversity = feature"""
    import muninn
    concepts = [f"new_concept_{i}" for i in range(15)]
    tagged = ["D> new API endpoint for inject", "D> use branch b0000 for live",
              "F> inject_memory() returns branch name"]
    result = muninn.classify_session(concepts, tagged)
    # With 15 unique concepts and D> tags, should be feature or explore
    assert result["type"] in ("feature", "explore"), f"B6.2 FAIL: type={result['type']}"
    print(f"  B6.2 PASS: {result['type']} session (confidence={result['confidence']:.2f})")

def test_b6_3_review():
    """Session with B> and F> tags = review"""
    import muninn
    concepts = ["benchmark", "test", "result", "benchmark", "test"]
    tagged = ["B> 37/40 facts preserved (92%)", "B> compression x4.5",
              "F> tiktoken measures real tokens", "F> L9 useless on compressed",
              "B> TIER 1: 36 PASS"]
    result = muninn.classify_session(concepts, tagged)
    assert result["type"] == "review", f"B6.3 FAIL: type={result['type']}"
    print(f"  B6.3 PASS: review session (confidence={result['confidence']:.2f})")

def test_b6_4_empty():
    """Empty input with no session index = unknown"""
    import muninn, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / ".muninn").mkdir()
        old_repo = muninn._REPO_PATH
        muninn._REPO_PATH = repo
        result = muninn.classify_session([], [])
        muninn._REPO_PATH = old_repo
    assert result["type"] == "unknown", f"B6.4 FAIL: type={result['type']}"
    assert result["confidence"] == 0.0, f"B6.4 FAIL: confidence={result['confidence']}"
    print(f"  B6.4 PASS: empty input returns unknown")

def test_b6_5_keys():
    """Output should have the expected keys"""
    import muninn
    result = muninn.classify_session(["test"], [])
    expected_keys = {"type", "confidence", "tag_profile"}
    assert set(result.keys()) == expected_keys, f"B6.5 FAIL: keys={set(result.keys())}"
    print(f"  B6.5 PASS: output keys = {{type, confidence, tag_profile}}")

def test_b6_6_confidence_range():
    """Confidence should be in [0, 1]"""
    import muninn
    for concepts, tagged in [
        (["x"], []),
        (["error"] * 10, ["E> bug"] * 5),
        ([f"c{i}" for i in range(20)], ["D> decision"]),
    ]:
        result = muninn.classify_session(concepts, tagged)
        assert 0 <= result["confidence"] <= 1.0, \
            f"B6.6 FAIL: confidence={result['confidence']} out of [0,1]"
    print(f"  B6.6 PASS: confidence always in [0, 1]")

if __name__ == "__main__":
    print("=== B6 -- Klein RPD session-type: validation bornes ===")
    test_b6_1_debug()
    test_b6_2_feature()
    test_b6_3_review()
    test_b6_4_empty()
    test_b6_5_keys()
    test_b6_6_confidence_range()
    print("\n  ALL B6 BORNES PASSED")
