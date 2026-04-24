"""C4 — Real-time sigmoid k adaptation.

Tests:
  C4.1  adapt_k() returns valid dict
  C4.2  adapt_k() adjusts k for divergent concepts
  C4.3  adapt_k() adjusts k for convergent concepts
  C4.4  adapt_k() wired in recall()
  C4.5  adapt_k() wired in inject_memory()
"""
import sys, os, re
import muninn
from pathlib import Path


def test_c4_1_adapt_k_returns_dict():
    """adapt_k() should return a dict with old_k, new_k, mode, diversity."""
    result = muninn.adapt_k(["test", "concept", "alpha", "beta"])
    assert isinstance(result, dict), f"C4.1 FAIL: not a dict: {type(result)}"
    for key in ["old_k", "new_k", "mode", "diversity"]:
        assert key in result, f"C4.1 FAIL: missing key {key}"
    print(f"  C4.1 PASS: adapt_k returns {result}")


def test_c4_2_divergent():
    """Many unique concepts should give low k (divergent)."""
    # All unique = diversity 1.0 = divergent
    concepts = [f"concept_{i}" for i in range(20)]
    result = muninn.adapt_k(concepts)
    assert result["new_k"] <= 10, f"C4.2 FAIL: divergent should have low k, got {result['new_k']}"
    print(f"  C4.2 PASS: divergent k={result['new_k']}, mode={result['mode']}")


def test_c4_3_convergent():
    """Repeated concepts should give high k (convergent)."""
    # Same concept repeated = diversity 0.05 = convergent
    concepts = ["debug"] * 20
    result = muninn.adapt_k(concepts)
    assert result["new_k"] >= 10, f"C4.3 FAIL: convergent should have high k, got {result['new_k']}"
    print(f"  C4.3 PASS: convergent k={result['new_k']}, mode={result['mode']}")


def test_c4_4_wired_in_recall():
    """adapt_k() should be called in recall()."""
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    recall_start = src.find("def recall(")
    recall_end = src.find("\ndef ", recall_start + 1)
    recall_body = src[recall_start:recall_end]
    assert "adapt_k" in recall_body, "C4.4 FAIL: adapt_k not wired in recall()"
    print("  C4.4 PASS: adapt_k wired in recall()")


def test_c4_5_wired_in_inject():
    """adapt_k() should be called in inject_memory()."""
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    inject_start = src.find("def inject_memory(")
    inject_end = src.find("\ndef ", inject_start + 1)
    inject_body = src[inject_start:inject_end]
    assert "adapt_k" in inject_body, "C4.5 FAIL: adapt_k not wired in inject_memory()"
    print("  C4.5 PASS: adapt_k wired in inject_memory()")


if __name__ == "__main__":
    print("=== C4 — Real-time k adaptation ===")
    test_c4_1_adapt_k_returns_dict()
    test_c4_2_divergent()
    test_c4_3_convergent()
    test_c4_4_wired_in_recall()
    test_c4_5_wired_in_inject()
    print("\n  ALL C4 BORNES PASSED")
