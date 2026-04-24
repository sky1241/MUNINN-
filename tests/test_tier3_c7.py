"""C7 — Contradiction resolution in B1 reconsolidation.

Tests:
  C7.1  _resolve_contradictions removes stale numeric facts
  C7.2  Last-writer-wins: later value preserved
  C7.3  Non-contradicting lines preserved
  C7.4  Headers and ?FACTS never removed
  C7.5  Wired in B1 reconsolidation (read_node)
"""
import sys, os, re
import muninn
from pathlib import Path


def test_c7_1_removes_stale():
    """Lines with same structure but different numbers should lose the older one."""
    text = "D> ratio x7.4 on verbose\nD> other fact\nD> ratio x4.1 on verbose"
    result = muninn._resolve_contradictions(text)
    assert "x4.1" in result, f"C7.1 FAIL: latest value not preserved: {result}"
    assert "x7.4" not in result, f"C7.1 FAIL: stale value still present: {result}"
    print("  C7.1 PASS: stale numeric line removed")


def test_c7_2_last_wins():
    """The last occurrence should always win."""
    text = "F> score 85%\nD> decision made\nF> score 92%\nA> arch note\nF> score 88%"
    result = muninn._resolve_contradictions(text)
    assert "88%" in result, f"C7.2 FAIL: last value not preserved"
    assert "85%" not in result, f"C7.2 FAIL: first value still present"
    assert "92%" not in result, f"C7.2 FAIL: middle value still present"
    print("  C7.2 PASS: last-writer-wins")


def test_c7_3_non_contradicting_preserved():
    """Lines without numeric contradictions should be untouched."""
    text = "D> chose Python over Rust\nF> 37 tests pass\nA> L-system architecture"
    result = muninn._resolve_contradictions(text)
    assert result == text, f"C7.3 FAIL: non-contradicting lines modified"
    print("  C7.3 PASS: non-contradicting lines preserved")


def test_c7_4_headers_protected():
    """Headers and ?FACTS should never be removed."""
    text = "## Section 1\n?FACTS: 5 items\nD> ratio x7.4\n## Section 1\n?FACTS: 3 items\nD> ratio x4.1"
    result = muninn._resolve_contradictions(text)
    # Headers should survive
    assert result.count("## Section 1") == 2, "C7.4 FAIL: header removed"
    assert result.count("?FACTS") == 2, "C7.4 FAIL: ?FACTS removed"
    print("  C7.4 PASS: headers and ?FACTS protected")


def test_c7_5_wired_in_reconsolidation():
    """_resolve_contradictions should be called in B1 reconsolidation."""
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    # Find reconsolidation section in read_node
    reconsolidation_start = src.find("B1: Reconsolidation")
    assert reconsolidation_start != -1, "C7.5 FAIL: B1 reconsolidation not found in source"
    reconsolidation_section = src[reconsolidation_start:reconsolidation_start+1500]
    assert "_resolve_contradictions" in reconsolidation_section, \
        "C7.5 FAIL: contradiction resolution not wired in B1"
    assert "C7" in reconsolidation_section, \
        "C7.5 FAIL: C7 comment not found in reconsolidation"
    print("  C7.5 PASS: wired in B1 reconsolidation")


if __name__ == "__main__":
    print("=== C7 — Contradiction resolution in reconsolidation ===")
    test_c7_1_removes_stale()
    test_c7_2_last_wins()
    test_c7_3_non_contradicting_preserved()
    test_c7_4_headers_protected()
    test_c7_5_wired_in_reconsolidation()
    print("\n  ALL C7 BORNES PASSED")
