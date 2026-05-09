"""CHUNK P0bis-3 — RotatingFileHandler rotated-file permissions.

Pre-fix: yesterday's P0 commit chmod'd `hook_errors.log` ONCE at handler
creation time (see _hook_logger.py:50 pre-fix). When RotatingFileHandler
rolls over (`hook_errors.log` → `hook_errors.log.1`, then a fresh
`hook_errors.log` is opened), the new file inherits the process umask —
typically 0o644 on Linux. Hook logs contain user prompts + stack traces
(potential secrets). World-readable on multi-user hosts.

Post-fix: _SecureRotatingFileHandler subclass forces 0o600 on:
  - the active file (after every emit — defense in depth)
  - every rotated backup (.1, .2, ..., backupCount) after each rollover

Source: docs/BATTLE_PLAN_2026-05-09.md §P0bis-3
"""
import logging
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _mode(p: Path) -> int:
    return p.stat().st_mode & 0o777


def test_secure_rotating_file_handler_initial_emit_creates_0600(tmp_path):
    """First write through the handler must produce a 0o600 log file."""
    import _hook_logger

    log_path = tmp_path / "test.log"
    handler = _hook_logger._SecureRotatingFileHandler(
        str(log_path), maxBytes=10_000, backupCount=3, encoding="utf-8"
    )
    logger = logging.getLogger(f"_p0bis_test_{id(log_path)}")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    logger.warning("first message — should create file at 0o600")
    handler.close()

    assert log_path.exists(), "log file not created"
    assert _mode(log_path) == 0o600, (
        f"active log mode {oct(_mode(log_path))}; expected 0o600"
    )


def test_secure_rotating_file_handler_rollover_chmods_backups(tmp_path):
    """After 3 rollovers, .1 / .2 / .3 backups must all be 0o600.

    Pre-fix: rolled backups were created with the umask (usually 0o644)
    because RotatingFileHandler.doRollover does not chmod after the
    rename + reopen.
    """
    import _hook_logger

    log_path = tmp_path / "test.log"
    # Tiny maxBytes so every emit triggers a rollover.
    handler = _hook_logger._SecureRotatingFileHandler(
        str(log_path), maxBytes=10, backupCount=3, encoding="utf-8"
    )
    logger = logging.getLogger(f"_p0bis_rollover_{id(log_path)}")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False

    # 4 emits → rolls over 3 times (each emit > 10 bytes).
    for i in range(4):
        logger.warning(f"message-{i}-with-some-padding-to-exceed-10-bytes")
    handler.close()

    backups = [tmp_path / f"test.log.{i}" for i in (1, 2, 3)]
    found = [b for b in backups if b.exists()]
    assert found, "no rollover occurred — test setup wrong"

    for b in found:
        assert _mode(b) == 0o600, (
            f"rotated backup {b.name} mode {oct(_mode(b))}; "
            f"expected 0o600 (post-rollover chmod missing)"
        )

    # The active file (re-created after rollover) must also be 0o600.
    if log_path.exists():
        assert _mode(log_path) == 0o600, (
            f"active log post-rollover mode {oct(_mode(log_path))}; "
            f"expected 0o600"
        )


def test_build_logger_uses_secure_handler(tmp_path):
    """_build_logger() must wire a _SecureRotatingFileHandler, not the
    plain RotatingFileHandler. Static check on the handler type."""
    import _hook_logger

    log_path = tmp_path / "test.log"
    logger = _hook_logger._build_logger(
        log_path, max_bytes=1_000_000, backup_count=3
    )
    assert logger is not None, "logger build failed"

    # Verify the handler is the secure subclass
    assert any(
        isinstance(h, _hook_logger._SecureRotatingFileHandler)
        for h in logger.handlers
    ), "logger does not use _SecureRotatingFileHandler — rotated backups will leak"

    # Force a write to actually create the file
    logger.warning("test message")
    assert log_path.exists()
    assert _mode(log_path) == 0o600
