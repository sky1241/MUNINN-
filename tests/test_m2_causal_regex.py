"""Test M2: Causal protection regex trailing space.

Bug: `car |donc ` in the P24 alternation has trailing spaces.
Then `\\s+\\S+` requires ANOTHER space. So "car raison" (single space,
normal French) is NOT protected by P24.
"""
import sys, re
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m2_causal_french():
    """French causal connectors with single space must match P24 regex."""

    # The ACTUAL buggy pattern from muninn.py L882
    buggy_pattern = r'(?:because|since|therefore|so that|due to|parce que?|car |donc |puisque)\s+\S+'

    # The FIXED pattern (no trailing spaces on car/donc)
    fixed_pattern = r'(?:because|since|therefore|so that|due to|parce que?|car|donc|puisque)\s+\S+'

    test_cases = [
        ("car raison", "French 'car' + single space"),
        ("donc voila", "French 'donc' + single space"),
        ("parce que oui", "French 'parce que'"),
        ("because reason", "English 'because'"),
    ]

    print("  --- Buggy pattern (car /donc  with trailing space) ---")
    buggy_fails = 0
    for text, desc in test_cases:
        match = re.search(buggy_pattern, text, re.IGNORECASE)
        status = "match" if match else "NO MATCH"
        print(f"    '{text}' -> {status} — {desc}")
        if not match and "car" in text.lower()[:4] or "donc" in text.lower()[:5]:
            buggy_fails += 1

    print(f"\n  --- Fixed pattern (car/donc without trailing space) ---")
    fixed_fails = 0
    for text, desc in test_cases:
        match = re.search(fixed_pattern, text, re.IGNORECASE)
        matched = match is not None
        status = "match" if matched else "NO MATCH"
        print(f"    '{text}' -> {status} — {desc}")
        if not matched:
            fixed_fails += 1

    # Now test what the actual code does by reading compress_line source
    # Read the actual regex from the code
    import muninn, inspect
    source = inspect.getsource(muninn.compress_line)

    # Check that the regex in source no longer has trailing space on car/donc
    has_trailing_car = "car |" in source or "car )" in source
    has_trailing_donc = "donc |" in source or "donc )" in source
    print(f"\n  Code still has 'car ': {has_trailing_car}")
    print(f"  Code still has 'donc ': {has_trailing_donc}")

    assert not has_trailing_car, "Fix not applied: 'car ' still has trailing space in regex"
    assert not has_trailing_donc, "Fix not applied: 'donc ' still has trailing space in regex"
    assert fixed_fails == 0, f"Fixed pattern should match all test cases, {fixed_fails} failed"

    print("  PASS")


if __name__ == "__main__":
    print("## M2 — Causal regex trailing space")
    test_m2_causal_french()
