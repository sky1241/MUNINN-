"""X2 — UTC epoch: date.today() -> datetime.now(timezone.utc).date() partout.

Tests:
  X2.1  today_days() uses UTC
  X2.2  date_to_days fallback uses UTC
  X2.3  No date.today() calls remain in engine/core/
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from mycelium_db import today_days, date_to_days, days_to_date
from datetime import datetime, date, timedelta, timezone


def test_x2_1_today_days_utc():
    """today_days() should return UTC-based epoch days."""
    result = today_days()
    # Compare with UTC
    utc_today = datetime.now(timezone.utc).date()
    epoch_ref = date(2020, 1, 1)
    expected = (utc_today - epoch_ref).days
    assert result == expected, f"X2.1 FAIL: today_days()={result}, expected UTC={expected}"
    print(f"  X2.1 PASS: today_days()={result} matches UTC epoch")


def test_x2_2_date_to_days_fallback_utc():
    """date_to_days() fallback on invalid input uses UTC."""
    result = date_to_days("not-a-date")
    utc_today = datetime.now(timezone.utc).date()
    epoch_ref = date(2020, 1, 1)
    expected = (utc_today - epoch_ref).days
    assert result == expected, f"X2.2 FAIL: fallback={result}, expected UTC={expected}"
    print(f"  X2.2 PASS: fallback={result} matches UTC epoch")


def test_x2_3_no_date_today_in_codebase():
    """No date.today() calls remain in engine/core/ Python files."""
    import re
    core_dir = os.path.join(os.path.dirname(__file__), "..", "engine", "core")
    violations = []
    for fname in os.listdir(core_dir):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(core_dir, fname)
        with open(fpath, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if "date.today()" in line and not line.strip().startswith("#"):
                    violations.append(f"{fname}:{i}: {line.strip()}")
    assert len(violations) == 0, f"X2.3 FAIL: found date.today() in:\n" + "\n".join(violations)
    print(f"  X2.3 PASS: no date.today() found in engine/core/")


if __name__ == "__main__":
    test_x2_1_today_days_utc()
    test_x2_2_date_to_days_fallback_utc()
    test_x2_3_no_date_today_in_codebase()
    print("\nAll X2 tests PASS")
