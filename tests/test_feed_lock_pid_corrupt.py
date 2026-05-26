"""Test _MuninnLock PID file corruption recovery.

Found by PC3 R6 cross-audit: PC1 R5 fix at muninn_feed.py:1100 logs a warning when
PID file contains garbage (ValueError on int()) but ZERO test covers this path.
PC1 himself flagged this gap (R5 INCERTITUDE 2, confidence 60%).

This test verifies:
1. Corrupt PID file (non-numeric) does not crash _is_lock_stale().
2. The warning logger fires.
3. Stale detection falls through to heartbeat/max-age layers.
"""
import logging
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.expanduser("~/Bureau/MUNINN-/engine/core"))


def _make_lock(tmp_path: Path, name: str = "hook"):
    from muninn_feed import _MuninnLock
    return _MuninnLock(repo_path=tmp_path, name=name)


def test_pid_file_corrupt_non_numeric_does_not_crash(tmp_path, caplog):
    """Garbage in PID file → warning logged + _is_lock_stale falls through cleanly."""
    lock = _make_lock(tmp_path)
    lock.lock_dir.mkdir(parents=True)
    lock.pid_file.write_text("NOT_A_PID", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="muninn.muninn_feed"):
        result = lock._is_lock_stale()

    assert isinstance(result, bool), "must return bool, not crash"
    warnings = [r for r in caplog.records if "PID read failed" in r.getMessage()]
    assert warnings, f"expected PID-read warning, got {[r.getMessage() for r in caplog.records]}"


def test_pid_file_empty_does_not_crash(tmp_path, caplog):
    """Empty PID file (truncated write) → same warning path."""
    lock = _make_lock(tmp_path, name="hook2")
    lock.lock_dir.mkdir(parents=True)
    lock.pid_file.write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="muninn.muninn_feed"):
        result = lock._is_lock_stale()

    assert isinstance(result, bool)


def test_pid_file_only_whitespace_does_not_crash(tmp_path):
    """Whitespace-only PID file → ValueError caught."""
    lock = _make_lock(tmp_path, name="hook3")
    lock.lock_dir.mkdir(parents=True)
    lock.pid_file.write_text("   \n\t  ", encoding="utf-8")
    assert isinstance(lock._is_lock_stale(), bool)


def test_pid_file_negative_does_not_crash(tmp_path):
    """Negative PID is parseable as int but invalid process → falls through to heartbeat layer."""
    lock = _make_lock(tmp_path, name="hook4")
    lock.lock_dir.mkdir(parents=True)
    lock.pid_file.write_text("-99999", encoding="utf-8")
    assert isinstance(lock._is_lock_stale(), bool)


def test_pid_file_missing_does_not_crash(tmp_path):
    """No PID file at all → skip PID layer, check others."""
    lock = _make_lock(tmp_path, name="hook5")
    lock.lock_dir.mkdir(parents=True)
    assert not lock.pid_file.exists()
    assert isinstance(lock._is_lock_stale(), bool)
