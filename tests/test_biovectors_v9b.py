"""V9B — Reed-Solomon error correction redundancy: strict validation bornes.

Paper: Reed & Solomon 1960, J SIAM.
Formula: t = floor((n-k)/2) corrections possible with n symbols for k data.
         d_min >= n-k+1 (minimum distance).

Tests:
  V9B.1  Redundancy k=1: single carrier = fragile (no correction)
  V9B.2  Redundancy k>=2: concept survives loss of 1 branch
  V9B.3  d_min formula: d_min >= n-k+1
  V9B.4  Correction capacity: t = floor((n-k)/2) errors
  V9B.5  Full redundancy: all concepts in all branches -> max protection
  V9B.6  Empty branches: no concepts, no fragility
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


def compute_redundancy(branches_tags):
    """Compute concept redundancy across branches.
    branches_tags: dict of branch_name -> list of tags
    Returns: dict of concept -> set of carriers
    """
    carriers = {}
    for bname, tags in branches_tags.items():
        for tag in tags:
            carriers.setdefault(tag, set()).add(bname)
    return carriers


def correction_capacity(n, k):
    """Reed-Solomon: t = floor((n-k)/2) symbol errors correctable."""
    return (n - k) // 2


def min_distance(n, k):
    """Minimum distance: d_min >= n-k+1."""
    return n - k + 1


def test_v9b_1_fragile():
    """Single carrier = fragile (redundancy=1, t=0)"""
    branches = {
        "b1": ["compression", "memory"],
        "b2": ["tokens", "context"],
    }
    carriers = compute_redundancy(branches)
    # "compression" only in b1 -> fragile
    fragile = {c for c, s in carriers.items() if len(s) == 1}
    check("V9B.1", "compression" in fragile and "tokens" in fragile,
          f"fragile={fragile}")


def test_v9b_2_redundant():
    """Redundancy k>=2: concept survives loss of 1 branch"""
    branches = {
        "b1": ["compression", "memory"],
        "b2": ["compression", "tokens"],
        "b3": ["memory", "tokens"],
    }
    carriers = compute_redundancy(branches)
    # "compression" in b1 AND b2 -> redundancy=2, survives loss of 1
    redundancy = len(carriers["compression"])
    # With n=2 carriers and k=1 data: survives loss of 1 (redundancy > 1)
    # Not fragile = not sole carrier
    fragile = {c for c, s in carriers.items() if len(s) == 1}
    check("V9B.2", redundancy >= 2 and "compression" not in fragile,
          f"compression redundancy={redundancy}, not fragile")


def test_v9b_3_dmin():
    """d_min >= n-k+1"""
    # n=5 symbols, k=3 data -> d_min >= 3
    d = min_distance(5, 3)
    check("V9B.3", d >= 3, f"d_min(5,3)={d}")


def test_v9b_4_correction():
    """t = floor((n-k)/2) errors correctable"""
    # n=10, k=6 -> t=2
    t = correction_capacity(10, 6)
    check("V9B.4", t == 2, f"t(10,6)={t}")
    # n=15, k=10 -> t=2
    t2 = correction_capacity(15, 10)
    check("V9B.4b", t2 == 2, f"t(15,10)={t2}")


def test_v9b_5_full_redundancy():
    """All concepts in all branches -> maximum protection"""
    branches = {
        "b1": ["alpha", "beta", "gamma"],
        "b2": ["alpha", "beta", "gamma"],
        "b3": ["alpha", "beta", "gamma"],
    }
    carriers = compute_redundancy(branches)
    all_max = all(len(s) == 3 for s in carriers.values())
    fragile = {c for c, s in carriers.items() if len(s) == 1}
    check("V9B.5", all_max and len(fragile) == 0,
          f"all redundancy=3, fragile={fragile}")


def test_v9b_6_empty():
    """Empty branches: no fragility"""
    branches = {"b1": [], "b2": []}
    carriers = compute_redundancy(branches)
    check("V9B.6", len(carriers) == 0, "no concepts = no fragility")


if __name__ == "__main__":
    print("=== V9B Reed-Solomon Redundancy — 7 bornes ===")
    test_v9b_1_fragile()
    test_v9b_2_redundant()
    test_v9b_3_dmin()
    test_v9b_4_correction()
    test_v9b_5_full_redundancy()
    test_v9b_6_empty()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
