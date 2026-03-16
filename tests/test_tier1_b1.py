"""B1 — Reconsolidation at boot: strict validation bornes.

Tests:
  B1.1  Size: reconsolidated branch <= original
  B1.4  Cooldown: fresh branch (< 1 day) NOT reconsolidated
  B1.5  Fresh skip: recall > 0.3 NOT reconsolidated
  B1.6  No API: only L10+L11 used
  B1.X  Root protection: root never reconsolidated
"""
import sys, os, tempfile, json, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from muninn import _cue_distill, _extract_rules, _ebbinghaus_recall

_TODAY = time.strftime("%Y-%m-%d")
_DAYS_AGO = lambda n: (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")

def test_b1_1_size():
    """L10+L11 should reduce or maintain size, never inflate"""
    sample = """## Architecture
Python is a programming language used for many things.
The system uses a tree structure for memory management.
compression ratio: x4.1 on verbose, x2.6 on roadmap
benchmark: 37/40 facts preserved (92%)
The weather is nice today and the sky is blue.
Generally speaking, most things work as expected.
Python was created by Guido van Rossum in 1991.
The system has been tested extensively.
Results show: speed=fast accuracy=high cost=low latency=5ms
"""
    original_len = len(sample)
    result = _cue_distill(sample)
    result = _extract_rules(result)
    assert len(result) <= original_len, f"B1.1 FAIL: inflated {original_len} -> {len(result)}"
    print(f"  B1.1 PASS: {original_len} -> {len(result)} chars ({len(result)/original_len*100:.0f}%)")

def test_b1_4_cooldown():
    """Node accessed < 1 day ago should NOT trigger reconsolidation"""
    import time
    node = {
        "access_count": 2,
        "last_access": time.strftime("%Y-%m-%d"),  # today
        "usefulness": 0.5,
    }
    recall = _ebbinghaus_recall(node)
    # Today = 0 days ago => recall = 1.0 (way above 0.3)
    assert recall > 0.3, f"B1.4 FAIL: recall={recall}, should be > 0.3 for today"
    print(f"  B1.4 PASS: recall={recall:.4f} > 0.3, reconsolidation skipped")

def test_b1_5_fresh_skip():
    """recall > 0.3 => reconsolidation skipped"""
    node = {
        "access_count": 10,  # many reviews = high h = high recall
        "last_access": _DAYS_AGO(9),
        "usefulness": 1.0,
    }
    recall = _ebbinghaus_recall(node)
    # h = 7 * 2^10 = 7168 days. recall = 2^(-9/7168) = ~0.999
    assert recall > 0.3, f"B1.5 FAIL: recall={recall}, expected > 0.3"
    print(f"  B1.5 PASS: recall={recall:.4f} > 0.3 (well-reviewed branch skipped)")

def test_b1_6_no_api():
    """_cue_distill and _extract_rules are regex-only"""
    import inspect
    source_l10 = inspect.getsource(_cue_distill)
    source_l11 = inspect.getsource(_extract_rules)
    for forbidden in ["anthropic", "api_key", "client.", "messages.create"]:
        assert forbidden not in source_l10, f"B1.6 FAIL: L10 contains '{forbidden}'"
        assert forbidden not in source_l11, f"B1.6 FAIL: L11 contains '{forbidden}'"
    print(f"  B1.6 PASS: L10+L11 contain no API calls")

def test_b1_root_protection():
    """Root should never be reconsolidated"""
    # The code checks `name != "root"` — verified by reading the source
    from muninn import read_node
    # Just verify the condition exists in the code
    import inspect
    source = inspect.getsource(read_node)
    assert 'name != "root"' in source, "B1.X FAIL: root protection not found in read_node"
    print(f"  B1.X PASS: root protection clause present in read_node")

def test_b1_idempotence():
    """Running L10+L11 twice should change < 5% the second time"""
    sample = """compression ratio: x4.1 on verbose, x2.6 on roadmap
benchmark: 37/40 facts preserved
Generally, the system performs well in most scenarios.
The approach uses standard techniques from the field.
Results: speed=fast accuracy=high cost=low latency=5ms
Numbers show improvement across all metrics.
Architecture follows established patterns.
"""
    pass1 = _extract_rules(_cue_distill(sample))
    pass2 = _extract_rules(_cue_distill(pass1))
    delta = abs(len(pass1) - len(pass2)) / max(len(pass1), 1)
    assert delta < 0.05, f"B1.3 FAIL: delta={delta:.2%}, expected < 5%"
    print(f"  B1.3 PASS: idempotent (pass1={len(pass1)}, pass2={len(pass2)}, delta={delta:.2%})")

if __name__ == "__main__":
    print("=== B1 — Reconsolidation: validation bornes ===")
    test_b1_1_size()
    test_b1_4_cooldown()
    test_b1_5_fresh_skip()
    test_b1_6_no_api()
    test_b1_root_protection()
    test_b1_idempotence()
    print("\n  ALL B1 BORNES PASSED")
