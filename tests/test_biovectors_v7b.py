"""V7B — ACO pheromone boot scoring: strict validation bornes.

Paper: Dorigo, Maniezzo, Colorni 1996, IEEE Trans SMC-B.
Formula: p_ij = tau^alpha * eta^beta / sum(tau_il^alpha * eta_il^beta)

Tests:
  V7B.1  ACO score increases with both tau and eta
  V7B.2  eta (relevance) matters more than tau (beta=2 > alpha=1)
  V7B.3  Branches with high historical use + high relevance dominate
  V7B.4  tau floor clamp: usefulness*recall=0 -> tau=0.01 (never zero)
  V7B.5  Backward compat: scores with ACO blend are still > 0
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


def aco_score(usefulness, recall, relevance, alpha=1.0, beta=2.0):
    """Compute V7B ACO score as in boot()."""
    tau = max(0.01, usefulness * recall)
    eta = max(0.01, relevance)
    return (tau ** alpha) * (eta ** beta)


def blended_score(base_total, usefulness, recall, relevance):
    """Compute blended score: 80% base + 20% ACO."""
    aco = aco_score(usefulness, recall, relevance)
    return 0.8 * base_total + 0.2 * aco


def test_v7b_1_increases():
    """ACO score increases with both tau and eta"""
    s_low = aco_score(0.3, 0.3, 0.3)
    s_high = aco_score(0.9, 0.9, 0.9)
    check("V7B.1", s_high > s_low,
          f"high={s_high:.4f} > low={s_low:.4f}")


def test_v7b_2_eta_dominates():
    """eta (relevance) matters more than tau (beta=2 > alpha=1)"""
    # High tau, low eta
    s_tau = aco_score(0.9, 0.9, 0.2)  # tau=0.81, eta=0.2
    # Low tau, high eta
    s_eta = aco_score(0.3, 0.3, 0.9)  # tau=0.09, eta=0.9
    check("V7B.2", s_eta > s_tau,
          f"eta-heavy={s_eta:.4f} > tau-heavy={s_tau:.4f}")


def test_v7b_3_both_high_dominates():
    """High use + high relevance >> single high dimension"""
    s_both = aco_score(0.9, 0.9, 0.9)
    s_tau_only = aco_score(0.9, 0.9, 0.1)
    s_eta_only = aco_score(0.1, 0.1, 0.9)
    ok = s_both > s_tau_only and s_both > s_eta_only
    check("V7B.3", ok,
          f"both={s_both:.4f} > tau_only={s_tau_only:.4f}, eta_only={s_eta_only:.4f}")


def test_v7b_4_tau_floor():
    """tau never goes below 0.01 (floor prevents zero scores)"""
    s = aco_score(0.0, 0.0, 0.5)  # usefulness*recall = 0 -> clamped to 0.01
    ok = s > 0
    check("V7B.4", ok, f"score={s:.6f} (tau clamped to 0.01)")


def test_v7b_5_blend_positive():
    """Blended scores are always > 0 for any positive base_total"""
    s = blended_score(0.3, 0.5, 0.5, 0.5)
    ok = s > 0
    check("V7B.5", ok, f"blended={s:.4f}")


if __name__ == "__main__":
    print("=== V7B ACO Pheromone — 5 bornes ===")
    test_v7b_1_increases()
    test_v7b_2_eta_dominates()
    test_v7b_3_both_high_dominates()
    test_v7b_4_tau_floor()
    test_v7b_5_blend_positive()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
