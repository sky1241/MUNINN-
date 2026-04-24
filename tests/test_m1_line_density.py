"""Test M1: _line_density max vs min for long narrative lines.

Bug: `max(score, 0.1)` at L677 should be `min(score, 0.1)`.
Long narrative lines (>120 chars, no digits) with incidental patterns
(key=value, file paths) keep inflated scores instead of being capped.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m1_long_narrative_with_pattern_capped():
    """Long narrative with incidental key=value should be capped at 0.1."""
    from muninn import _line_density

    # Long narrative (>120 chars, no digits) WITH incidental patterns
    # key=value gives +0.1, file path gives +0.1 -> score 0.2
    # Before fix: max(0.2, 0.1) = 0.2 (NOT capped)
    # After fix:  min(0.2, 0.1) = 0.1 (capped correctly)
    narrative_kv = ("The implementation follows a specific pattern where we configure "
                    "the system settings mode=verbose and the overall approach is based "
                    "on principles from module.py that we discussed earlier in the meeting")
    assert len(narrative_kv) > 120, f"Test line too short: {len(narrative_kv)}"

    density = _line_density(narrative_kv)
    print(f"  Long narrative+kv ({len(narrative_kv)} chars): density={density:.3f}")
    print(f"  density <= 0.1: {density <= 0.1}")
    assert density <= 0.1, (
        f"Long narrative with incidental kv/path should be capped at 0.1, got {density}. "
        f"Bug: max(score, 0.1) should be min(score, 0.1)"
    )

    # Factual tagged line — should still be HIGH density
    factual = "B> latency=42ms throughput=1500rps error_rate=0.01"
    density_fact = _line_density(factual)
    print(f"  Factual tagged line: density={density_fact:.3f}")
    assert density_fact > 0.5, f"Factual should be high density, got {density_fact}"

    # Pure narrative (no patterns) — should be 0.0 after fix
    pure_narrative = ("This is a very long and meandering description about the general state "
                      "of affairs and how everything relates to everything else in a completely "
                      "generic way that carries absolutely no specific information at all")
    assert len(pure_narrative) > 120
    density_pure = _line_density(pure_narrative)
    print(f"  Pure narrative ({len(pure_narrative)} chars): density={density_pure:.3f}")
    # After fix: min(0.0, 0.1) = 0.0 (not boosted)
    assert density_pure <= 0.1, f"Pure narrative should be <= 0.1, got {density_pure}"

    # KIComp ordering: factual >> narrative (regardless of accidental patterns)
    print(f"  Ordering: factual({density_fact:.2f}) > narrative_kv({density:.2f}): {density_fact > density}")
    assert density_fact > density, "Factual must always outrank narrative"

    print("  PASS")


if __name__ == "__main__":
    print("## M1 — _line_density max vs min")
    test_m1_long_narrative_with_pattern_capped()
