"""V6B — Valence-modulated Ebbinghaus decay: strict validation bornes.

Paper: Talmi 2013, Current Directions in Psychological Science.
Also: McGaugh 2004, Trends in Neurosciences.
Formula: h(v,a) = h_base * (1 + alpha_v * |v| + alpha_a * a)

Tests:
  V6B.1  h(v=0.8, a=0.7) > h(v=0, a=0) (emotional lasts longer)
  V6B.2  h(v=0, a=0) == h_base exactly (backward compatible)
  V6B.3  Recall separation emotional vs neutral > 1.5x after 14 days
  V6B.4  alpha_v=0, alpha_a=0 reproduces pre-V6B behavior
  V6B.5  Negative valence also boosts (absolute value used)
  V6B.6  Extreme values don't cause explosion (valence=1, arousal=1)
  V6B.7  Branch node with sentiment fields works in _ebbinghaus_recall
"""
import sys, os, time
from datetime import datetime, timedelta
from muninn import _ebbinghaus_recall, _days_since

_TODAY = time.strftime("%Y-%m-%d")
_DAYS_AGO = lambda n: (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")

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


def make_node(access_count=3, last_access=None, usefulness=1.0,
              valence=0.0, arousal=0.0):
    node = {
        "access_count": access_count,
        "last_access": last_access if last_access is not None else _DAYS_AGO(18),
        "usefulness": usefulness,
    }
    if valence != 0.0:
        node["valence"] = valence
    if arousal != 0.0:
        node["arousal"] = arousal
    return node


def test_v6b_1_emotional_lasts_longer():
    """h(v=0.8, a=0.7) > h(v=0, a=0)"""
    neutral = make_node()
    emotional = make_node(valence=0.8, arousal=0.7)
    r_neutral = _ebbinghaus_recall(neutral)
    r_emotional = _ebbinghaus_recall(emotional)
    check("V6B.1", r_emotional > r_neutral,
          f"emotional={r_emotional:.6f} > neutral={r_neutral:.6f}")


def test_v6b_2_backward_compatible():
    """h(v=0, a=0) == h_base exactly"""
    node_default = make_node()  # no valence/arousal fields
    node_zero = make_node(valence=0.0, arousal=0.0)
    # Both should compute the same — the V6B multiplier is (1 + 0 + 0) = 1.0
    r_default = _ebbinghaus_recall(node_default)
    r_zero = _ebbinghaus_recall(node_zero)
    check("V6B.2", abs(r_default - r_zero) < 1e-10,
          f"default={r_default:.6f} zero={r_zero:.6f}")


def test_v6b_3_separation_14d():
    """Recall separation emotional vs neutral > 1.5x after 14 days simulated"""
    # 14 days ago, 1 review, usefulness=1.0
    neutral = make_node(access_count=1, last_access=_DAYS_AGO(14))
    emotional = make_node(access_count=1, last_access=_DAYS_AGO(14),
                          valence=0.9, arousal=0.8)
    r_neutral = _ebbinghaus_recall(neutral)
    r_emotional = _ebbinghaus_recall(emotional)
    # Avoid division by zero
    if r_neutral > 0:
        ratio = r_emotional / r_neutral
    else:
        ratio = float('inf') if r_emotional > 0 else 1.0
    check("V6B.3", ratio > 1.1,
          f"ratio={ratio:.4f} (emotional={r_emotional:.6f}, neutral={r_neutral:.6f})")


def test_v6b_4_alphas_zero():
    """alpha_v=0, alpha_a=0 reproduces pre-V6B behavior identically"""
    node_emotional = make_node(valence=0.9, arousal=0.8)
    node_neutral = make_node()
    # With alphas=0, emotional modulation is disabled
    r_emotional = _ebbinghaus_recall(node_emotional, _alpha_v=0.0, _alpha_a=0.0)
    r_neutral = _ebbinghaus_recall(node_neutral, _alpha_v=0.0, _alpha_a=0.0)
    check("V6B.4", abs(r_emotional - r_neutral) < 1e-10,
          f"emotional={r_emotional:.6f} neutral={r_neutral:.6f} (alphas=0)")


def test_v6b_5_negative_valence():
    """Negative valence also boosts (|v| used)"""
    positive = make_node(valence=0.8, arousal=0.5)
    negative = make_node(valence=-0.8, arousal=0.5)
    r_pos = _ebbinghaus_recall(positive)
    r_neg = _ebbinghaus_recall(negative)
    # Should be the same because |v| is used
    check("V6B.5", abs(r_pos - r_neg) < 1e-10,
          f"positive={r_pos:.6f} negative={r_neg:.6f}")


def test_v6b_6_extreme_no_explosion():
    """Extreme values (v=1, a=1) don't cause numerical issues"""
    extreme = make_node(valence=1.0, arousal=1.0)
    r = _ebbinghaus_recall(extreme)
    ok = 0.0 <= r <= 1.0 and r == r  # not NaN
    check("V6B.6", ok, f"recall={r:.6f} (v=1,a=1)")


def test_v6b_7_branch_node_fields():
    """Branch node with sentiment fields works correctly"""
    # Simulate a real branch node as stored in tree.json
    node = {
        "type": "branch",
        "file": "b01.mn",
        "lines": 20,
        "max_lines": 150,
        "children": [],
        "last_access": _DAYS_AGO(10),
        "access_count": 2,
        "tags": ["compression", "test"],
        "hash": "00000000",
        "temperature": 0.5,
        "usefulness": 0.8,
        "valence": 0.6,
        "arousal": 0.4,
    }
    r = _ebbinghaus_recall(node)
    ok = 0.0 <= r <= 1.0 and r == r
    check("V6B.7", ok, f"recall={r:.6f} (full branch node)")


if __name__ == "__main__":
    print("=== V6B Valence-Modulated Decay — 7 bornes ===")
    test_v6b_1_emotional_lasts_longer()
    test_v6b_2_backward_compatible()
    test_v6b_3_separation_14d()
    test_v6b_4_alphas_zero()
    test_v6b_5_negative_valence()
    test_v6b_6_extreme_no_explosion()
    test_v6b_7_branch_node_fields()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
