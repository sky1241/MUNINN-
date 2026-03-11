"""V3B — Bayesian Theory of Mind (BToM): strict validation bornes.

Paper: Baker, Saxe, Tenenbaum 2009, Cognition.
Formula: P(goal|actions,state) ~ P(actions|goal,state) * P(goal)
         P(actions|goal,state) ~ exp(-C(actions,goal,state))

Tests:
  V3B.1  Higher alignment -> higher posterior
  V3B.2  Higher prior (usefulness) -> higher posterior
  V3B.3  Zero alignment -> zero posterior
  V3B.4  Posterior in [0, 1] for all inputs
  V3B.5  Multiple overlapping concepts boost more than single
  V3B.6  Empty actions -> no goal inference
"""
import sys, os, math
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


def btom_posterior(alignment, prior=0.5):
    """Compute BToM posterior as in boot().
    alignment = sum of action probabilities for overlapping concepts.
    prior = usefulness (Bayesian prior).
    """
    if alignment <= 0:
        return 0.0
    return min(1.0, math.exp(-1.0 / max(0.01, alignment)) * prior)


def test_v3b_1_higher_alignment():
    """Higher alignment -> higher posterior"""
    low = btom_posterior(0.2, prior=0.5)
    high = btom_posterior(0.8, prior=0.5)
    check("V3B.1", high > low,
          f"high_align={high:.6f} > low_align={low:.6f}")


def test_v3b_2_higher_prior():
    """Higher prior (usefulness) -> higher posterior"""
    low_prior = btom_posterior(0.5, prior=0.2)
    high_prior = btom_posterior(0.5, prior=0.9)
    check("V3B.2", high_prior > low_prior,
          f"high_prior={high_prior:.6f} > low_prior={low_prior:.6f}")


def test_v3b_3_zero_alignment():
    """Zero alignment -> zero posterior"""
    p = btom_posterior(0.0, prior=0.5)
    check("V3B.3", p == 0.0, f"posterior={p}")


def test_v3b_4_bounded():
    """Posterior in [0, 1] for all inputs"""
    all_ok = True
    for a in [0.0, 0.01, 0.1, 0.5, 1.0, 5.0, 100.0]:
        for pr in [0.0, 0.1, 0.5, 1.0, 2.0]:
            p = btom_posterior(a, pr)
            if not (0.0 <= p <= 1.0):
                all_ok = False
                break
    check("V3B.4", all_ok, "all inputs -> [0,1]")


def test_v3b_5_multiple_concepts():
    """Multiple overlapping concepts boost more than single"""
    # Simulate: 3 concepts each with prob 0.2 -> alignment = 0.6
    # vs 1 concept with prob 0.2 -> alignment = 0.2
    single = btom_posterior(0.2, prior=0.5)
    multi = btom_posterior(0.6, prior=0.5)
    check("V3B.5", multi > single,
          f"multi={multi:.6f} > single={single:.6f}")


def test_v3b_6_empty_actions():
    """No actions -> no goal inference (alignment=0)"""
    p = btom_posterior(0.0, prior=0.9)
    check("V3B.6", p == 0.0,
          f"posterior={p} (no actions, even with high prior)")


if __name__ == "__main__":
    print("=== V3B Bayesian Theory of Mind — 6 bornes ===")
    test_v3b_1_higher_alignment()
    test_v3b_2_higher_prior()
    test_v3b_3_zero_alignment()
    test_v3b_4_bounded()
    test_v3b_5_multiple_concepts()
    test_v3b_6_empty_actions()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
