"""CHUNK A8 — hook log rotation + audit trail.

`bridge_hook._log_hook_error` and `muninn_feed._log_sync_error` both
swallow their own errors (`except Exception: pass`) and write to a
file with no rotation. Result: ~/.muninn/hook_errors.log accumulated
700 lines (50+ stdin_parse entries) with no signal to the user.

Fix: shared rotating logger in engine/core/_hook_logger.py used by
both hooks. RotatingFileHandler with 1 MB max + 3 backups; falls
back to stderr when the file is unwritable so the audit trail is
never truly silent.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A8
"""
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_hook_logger():
    repo = Path(__file__).resolve().parent.parent
    src = repo / "engine" / "core" / "_hook_logger.py"
    if not src.exists():
        return None
    spec = importlib.util.spec_from_file_location("_chunk_a8_hook_logger", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_module_exists():
    """engine/core/_hook_logger.py must exist."""
    repo = Path(__file__).resolve().parent.parent
    src = repo / "engine" / "core" / "_hook_logger.py"
    assert src.exists(), f"Missing module: {src}"


def test_log_to_custom_path(tmp_path):
    """Logger writes to the path given via env var override."""
    mod = _load_hook_logger()
    assert mod is not None, "engine/core/_hook_logger.py missing — A8 was wired in chunk a8"
    log_path = tmp_path / "test.log"
    mod.log_hook_event("test", "stdin_parse", ValueError("boom"),
                       log_path=log_path)
    assert log_path.exists()
    text = log_path.read_text()
    assert "stdin_parse" in text
    assert "ValueError" in text
    assert "boom" in text


def test_rotation_at_max_bytes(tmp_path):
    """When the log file reaches max_bytes, it must rotate to .1 backup."""
    mod = _load_hook_logger()
    assert mod is not None, "engine/core/_hook_logger.py missing — A8 was wired in chunk a8"
    log_path = tmp_path / "rot.log"
    # Use a tiny max_bytes to trigger rotation quickly
    for i in range(50):
        mod.log_hook_event("test", f"event_{i}",
                           Exception("x" * 200),
                           log_path=log_path,
                           max_bytes=2000,
                           backup_count=2)
    # After 50 events of ~200 bytes, must have rotated at least once
    backup = log_path.with_suffix(log_path.suffix + ".1")
    assert backup.exists(), f"No rotation backup at {backup}"
    # And the live file must be smaller than max_bytes (bounded growth)
    assert log_path.stat().st_size <= 4000, (
        f"Log file too large: {log_path.stat().st_size} bytes"
    )


def test_falls_back_to_stderr_when_unwritable(tmp_path, capsys, monkeypatch):
    """When the log path can't be written, error must go to stderr."""
    mod = _load_hook_logger()
    assert mod is not None, "engine/core/_hook_logger.py missing — A8 was wired in chunk a8"
    # Path that cannot be created (parent is a file, not dir)
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file not a directory")
    impossible = blocker / "deeper" / "log.txt"

    mod.log_hook_event("test", "fallback_check",
                       RuntimeError("audit"),
                       log_path=impossible)

    captured = capsys.readouterr()
    # Either stderr or stdout — fallback channel must surface the audit
    combined = captured.out + captured.err
    assert "fallback_check" in combined or "RuntimeError" in combined, (
        f"audit trail vanished — captured: stdout={captured.out!r} "
        f"stderr={captured.err!r}"
    )


def test_log_format_includes_timestamp(tmp_path):
    """Each log entry must start with an ISO-8601-ish timestamp."""
    mod = _load_hook_logger()
    assert mod is not None, "engine/core/_hook_logger.py missing — A8 was wired in chunk a8"
    log_path = tmp_path / "ts.log"
    mod.log_hook_event("test", "ts_check", Exception("x"), log_path=log_path)
    line = log_path.read_text().splitlines()[0]
    # Expect something like "2026-05-08T..."
    assert line[:4].isdigit() and line[4] == "-", (
        f"line does not start with a year: {line!r}"
    )


def test_two_calls_append_not_overwrite(tmp_path):
    """Logger must append, never truncate."""
    mod = _load_hook_logger()
    assert mod is not None, "engine/core/_hook_logger.py missing — A8 was wired in chunk a8"
    log_path = tmp_path / "append.log"
    mod.log_hook_event("test", "first", Exception("a"), log_path=log_path)
    mod.log_hook_event("test", "second", Exception("b"), log_path=log_path)
    text = log_path.read_text()
    assert "first" in text and "second" in text, (
        f"second event lost — log content: {text!r}"
    )
