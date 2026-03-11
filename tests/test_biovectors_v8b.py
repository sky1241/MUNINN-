"""V8B — Active sensing info-theoretic: strict validation bornes.

Paper: Yang, Wolpert, Lengyel 2016, eLife.
Formula: a* = argmax_a I(X;Y|a) = argmax_a [H(X) - E[H(X|Y,a)]]

Tests:
  V8B.1  Best concept splits candidates most evenly (max entropy)
  V8B.2  Concept in all branches: zero entropy (no discrimination)
  V8B.3  Concept in exactly 1 branch: high entropy (good discriminator)
  V8B.4  Binary entropy maximum at p=0.5
  V8B.5  No concepts: no disambiguation possible
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


def binary_entropy(p):
    """H(p) = -p*log2(p) - (1-p)*log2(1-p)"""
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def best_disambiguator(branches_tags, n_candidates=3):
    """Find the concept that best disambiguates top candidates.
    Returns (concept, entropy) or ("", 0).
    """
    # Compute concept distribution across branches
    concept_dist = {}
    for bname, tags in branches_tags.items():
        for tag in tags:
            concept_dist.setdefault(tag, set()).add(bname)

    best_c, best_h = "", 0.0
    n = len(branches_tags)
    for c, branches_with in concept_dist.items():
        p = len(branches_with) / n
        h = binary_entropy(p)
        if h > best_h:
            best_h = h
            best_c = c
    return best_c, best_h


def test_v8b_1_best_split():
    """Best concept splits candidates most evenly"""
    branches = {
        "b1": ["alpha", "beta"],
        "b2": ["alpha", "gamma"],
        "b3": ["beta", "delta"],
    }
    concept, entropy = best_disambiguator(branches)
    # "alpha" in 2/3, "beta" in 2/3, "gamma" in 1/3, "delta" in 1/3
    # H(2/3) = H(1/3) = 0.918 (same by symmetry)
    # All are equally good discriminators
    check("V8B.1", entropy > 0.5,
          f"best={concept}, entropy={entropy:.4f}")


def test_v8b_2_all_branches():
    """Concept in all branches: zero entropy"""
    h = binary_entropy(1.0)
    check("V8B.2", h == 0.0, f"H(1.0)={h}")


def test_v8b_3_one_branch():
    """Concept in 1/3 branches: high entropy"""
    h = binary_entropy(1/3)
    check("V8B.3", h > 0.9, f"H(1/3)={h:.4f}")


def test_v8b_4_max_at_half():
    """Binary entropy maximum at p=0.5"""
    h_half = binary_entropy(0.5)
    h_quarter = binary_entropy(0.25)
    h_three_quarter = binary_entropy(0.75)
    check("V8B.4", h_half > h_quarter and h_half > h_three_quarter,
          f"H(0.5)={h_half:.4f} > H(0.25)={h_quarter:.4f}")


def test_v8b_5_no_concepts():
    """No concepts: no disambiguation"""
    branches = {"b1": [], "b2": [], "b3": []}
    concept, entropy = best_disambiguator(branches)
    check("V8B.5", concept == "" and entropy == 0.0,
          f"concept='{concept}', entropy={entropy}")


if __name__ == "__main__":
    print("=== V8B Active Sensing Info-Theoretic — 5 bornes ===")
    test_v8b_1_best_split()
    test_v8b_2_all_branches()
    test_v8b_3_one_branch()
    test_v8b_4_max_at_half()
    test_v8b_5_no_concepts()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
