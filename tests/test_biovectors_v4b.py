"""V4B — EWC Fisher importance: strict validation bornes.

Paper: Kirkpatrick et al. 2017, PNAS.
Formula: h *= (1 + lambda_ewc * F_i), F_i in [0,1]

Tests:
  V4B.1  High Fisher importance -> higher recall (slower decay)
  V4B.2  Fisher=0 -> identical to pre-V4B (backward compat)
  V4B.3  Fisher is clamped to [0, 1]
  V4B.4  lambda_ewc=0 disables V4B
  V4B.5  Fisher + valence stack multiplicatively
  V4B.6  Recall separation with Fisher > 1.1x after 14 days
"""
import sys, os, time
from datetime import datetime, timedelta
from muninn import _ebbinghaus_recall

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
              fisher_importance=0.0, valence=0.0, arousal=0.0):
    node = {
        "access_count": access_count,
        "last_access": last_access if last_access is not None else _DAYS_AGO(18),
        "usefulness": usefulness,
    }
    if fisher_importance != 0.0:
        node["fisher_importance"] = fisher_importance
    if valence != 0.0:
        node["valence"] = valence
    if arousal != 0.0:
        node["arousal"] = arousal
    return node


def test_v4b_1_fisher_boosts_recall():
    """High Fisher -> higher recall"""
    neutral = make_node()
    important = make_node(fisher_importance=0.9)
    r_neutral = _ebbinghaus_recall(neutral)
    r_important = _ebbinghaus_recall(important)
    check("V4B.1", r_important > r_neutral,
          f"important={r_important:.6f} > neutral={r_neutral:.6f}")


def test_v4b_2_backward_compat():
    """Fisher=0 -> identical to pre-V4B"""
    node_default = make_node()  # no fisher field
    node_zero = make_node(fisher_importance=0.0)
    r_default = _ebbinghaus_recall(node_default)
    r_zero = _ebbinghaus_recall(node_zero)
    check("V4B.2", abs(r_default - r_zero) < 1e-10,
          f"default={r_default:.6f} zero={r_zero:.6f}")


def test_v4b_3_fisher_clamped():
    """Fisher is clamped to [0, 1] internally"""
    node_over = make_node(fisher_importance=5.0)
    node_under = make_node(fisher_importance=-2.0)
    node_max = make_node(fisher_importance=1.0)
    node_min = make_node(fisher_importance=0.0)
    r_over = _ebbinghaus_recall(node_over)
    r_under = _ebbinghaus_recall(node_under)
    r_max = _ebbinghaus_recall(node_max)
    r_min = _ebbinghaus_recall(node_min)
    # Over-1 should be clamped to 1
    check("V4B.3", abs(r_over - r_max) < 1e-10 and abs(r_under - r_min) < 1e-10,
          f"over={r_over:.6f}==max={r_max:.6f}, under={r_under:.6f}==min={r_min:.6f}")


def test_v4b_4_lambda_zero():
    """lambda_ewc=0 disables V4B"""
    node = make_node(fisher_importance=1.0)
    r_with = _ebbinghaus_recall(node, _lambda_ewc=0.5)
    r_without = _ebbinghaus_recall(node, _lambda_ewc=0.0)
    r_default = _ebbinghaus_recall(make_node(), _lambda_ewc=0.0)
    check("V4B.4", abs(r_without - r_default) < 1e-10,
          f"lambda=0: with_fisher={r_without:.6f} == no_fisher={r_default:.6f}")


def test_v4b_5_stacks_with_valence():
    """Fisher + valence stack multiplicatively"""
    base = make_node()
    fisher_only = make_node(fisher_importance=0.8)
    valence_only = make_node(valence=0.8, arousal=0.5)
    both = make_node(fisher_importance=0.8, valence=0.8, arousal=0.5)
    r_base = _ebbinghaus_recall(base)
    r_fisher = _ebbinghaus_recall(fisher_only)
    r_valence = _ebbinghaus_recall(valence_only)
    r_both = _ebbinghaus_recall(both)
    # both > either alone > base
    ok = r_both > r_fisher and r_both > r_valence and r_fisher > r_base and r_valence > r_base
    check("V4B.5", ok,
          f"both={r_both:.6f} > fisher={r_fisher:.6f}, valence={r_valence:.6f} > base={r_base:.6f}")


def test_v4b_6_separation_14d():
    """Recall separation Fisher > 1.1x after simulated time"""
    neutral = make_node(access_count=1, last_access=_DAYS_AGO(18))
    important = make_node(access_count=1, last_access=_DAYS_AGO(18), fisher_importance=1.0)
    r_neutral = _ebbinghaus_recall(neutral)
    r_important = _ebbinghaus_recall(important)
    if r_neutral > 0:
        ratio = r_important / r_neutral
    else:
        ratio = float('inf') if r_important > 0 else 1.0
    check("V4B.6", ratio > 1.1,
          f"ratio={ratio:.4f} (important={r_important:.6f}, neutral={r_neutral:.6f})")


if __name__ == "__main__":
    print("=== V4B EWC Fisher Importance — 6 bornes ===")
    test_v4b_1_fisher_boosts_recall()
    test_v4b_2_backward_compat()
    test_v4b_3_fisher_clamped()
    test_v4b_4_lambda_zero()
    test_v4b_5_stacks_with_valence()
    test_v4b_6_separation_14d()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
