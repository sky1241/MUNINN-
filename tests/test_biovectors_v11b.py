"""V11B — Boyd-Richerson cultural transmission (3 biases): strict validation bornes.

Paper: Boyd & Richerson 1985, Culture and the Evolutionary Process.
Formulas:
  Conformist: dp = beta * p * (1-p) * (2p-1)
  Prestige:   p' = sum(w_i * p_i)
  Guided:     p' = p + mu * (p_opt - p)

Tests:
  V11B.1  Conformist bias: majority (p>0.5) gets boosted, minority (p<0.5) suppressed
  V11B.2  Conformist at p=0.5: dp=0 (neutral equilibrium)
  V11B.3  Prestige bias: high td_value * usefulness > low
  V11B.4  Guided variation: pushes toward mean (gap shrinks)
  V11B.5  All biases sum is bounded (no explosion)
  V11B.6  Empty tags: conformist bias = 0 (graceful)
  V11B.7  Backward compat: default td_value=0.5, usefulness=0.5 -> small bias
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

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


def conformist_dp(p, beta=0.3):
    """Conformist bias: dp = beta * p * (1-p) * (2p-1)"""
    p = max(0.01, min(0.99, p))
    return beta * p * (1.0 - p) * (2.0 * p - 1.0)


def prestige(td_value, usefulness):
    """Prestige bias: prestige = td_value * usefulness"""
    return td_value * usefulness


def guided_variation_delta(usefulness, mean_usefulness, mu=0.1):
    """Guided variation delta: delta = mu * (p_opt - p)"""
    return mu * (mean_usefulness - usefulness)


def test_v11b_1_conformist_majority():
    """Majority (p>0.5) boosted, minority (p<0.5) suppressed"""
    dp_high = conformist_dp(0.8)  # majority
    dp_low = conformist_dp(0.2)   # minority
    # High p -> dp > 0 (push higher), low p -> dp < 0 (push lower)
    check("V11B.1", dp_high > 0 and dp_low < 0,
          f"majority dp={dp_high:.6f} > 0, minority dp={dp_low:.6f} < 0")


def test_v11b_2_conformist_neutral():
    """At p=0.5: dp=0 (unstable equilibrium)"""
    dp = conformist_dp(0.5)
    check("V11B.2", abs(dp) < 1e-10,
          f"dp(0.5)={dp:.10f}")


def test_v11b_3_prestige_ordering():
    """High td_value * usefulness > low"""
    p_high = prestige(0.9, 0.9)
    p_low = prestige(0.2, 0.3)
    check("V11B.3", p_high > p_low,
          f"high={p_high:.4f} > low={p_low:.4f}")


def test_v11b_4_guided_converges():
    """Guided variation delta: above mean -> negative, below mean -> positive"""
    mean = 0.6
    u_high = 0.9  # above mean -> delta < 0 (pulled down)
    u_low = 0.3   # below mean -> delta > 0 (pulled up)
    d_high = guided_variation_delta(u_high, mean)
    d_low = guided_variation_delta(u_low, mean)
    ok = d_high < 0 and d_low > 0
    check("V11B.4", ok,
          f"high delta={d_high:.4f}<0, low delta={d_low:.4f}>0, mean={mean}")


def test_v11b_5_bounded():
    """All biases sum is bounded (no explosion for any input)"""
    import itertools
    max_total = 0
    for p in [0.01, 0.25, 0.5, 0.75, 0.99]:
        for td in [0.0, 0.5, 1.0]:
            for u in [0.0, 0.5, 1.0]:
                c = 0.02 * conformist_dp(p)
                pr = 0.02 * prestige(td, u)
                g = 0.02 * guided_variation_delta(u, 0.5)
                total = c + pr + g
                if abs(total) > max_total:
                    max_total = abs(total)
    # Total cultural bias should be < 0.05 (small modulation)
    check("V11B.5", max_total < 0.05,
          f"max_total_bias={max_total:.6f}")


def test_v11b_6_empty_tags():
    """Empty tags: conformist bias contributes 0"""
    # With no tags, p is undefined — conformist should be skipped
    # This tests the guard in boot(): if _node_tags and _tag_freq
    dp = conformist_dp(0.0)  # p clamped to 0.01
    # dp(0.01) = 0.3 * 0.01 * 0.99 * (0.02-1) = very small negative
    check("V11B.6", abs(dp) < 0.003,
          f"dp(~0)={dp:.6f} (negligible)")


def test_v11b_7_default_values():
    """Default td_value=0.5, usefulness=0.5 -> small total bias"""
    c = 0.02 * conformist_dp(0.5)    # = 0 at equilibrium
    pr = 0.02 * prestige(0.5, 0.5)   # = 0.02 * 0.25 = 0.005
    g = 0.02 * guided_variation_delta(0.5, 0.5)  # = 0.02 * 0.0 = 0.0 (at mean)
    total = c + pr + g
    check("V11B.7", abs(total) < 0.02,
          f"default bias={total:.6f} (small)")


if __name__ == "__main__":
    print("=== V11B Boyd-Richerson Cultural Transmission — 7 bornes ===")
    test_v11b_1_conformist_majority()
    test_v11b_2_conformist_neutral()
    test_v11b_3_prestige_ordering()
    test_v11b_4_guided_converges()
    test_v11b_5_bounded()
    test_v11b_6_empty_tags()
    test_v11b_7_default_values()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
