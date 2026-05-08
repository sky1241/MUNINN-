"""CHUNK D9 — extend _hook_logger into a centralised _muninn_logger.

A8 introduced log_hook_event() for hooks. D9 extends that module with
two more primitives so non-hook engine code can stop writing its own
`except Exception: pass` boilerplate:

  - log_engine_event(source, context, exc, ...): same as log_hook_event
    but writes to ~/.muninn/engine_events.log so engine errors don't
    pollute the hook audit trail.

  - swallow(source, context, log_path=None): context manager that
    catches any Exception inside its block, logs it via the rotating
    logger, and lets the program continue. Replaces the
    `try: ... except Exception as e: log_hook_event(...)` pattern
    that has accumulated in 5+ files since A8.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D9
"""
import importlib.util
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_hook_logger():
    src = REPO / "engine" / "core" / "_hook_logger.py"
    spec = importlib.util.spec_from_file_location("_chunk_d9_logger", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_log_engine_event_helper_exists():
    mod = _load_hook_logger()
    assert hasattr(mod, "log_engine_event"), (
        "log_engine_event() missing — see CHUNK D9"
    )


def test_swallow_context_manager_exists():
    mod = _load_hook_logger()
    assert hasattr(mod, "swallow"), "swallow() context manager missing"


def test_log_engine_event_uses_separate_log(tmp_path):
    """log_engine_event must default to a different file than
    log_hook_event so the audit trails stay split."""
    mod = _load_hook_logger()
    hook_log = tmp_path / "hook.log"
    engine_log = tmp_path / "engine.log"
    mod.log_hook_event("test", "h", Exception("h"), log_path=hook_log)
    mod.log_engine_event("test", "e", Exception("e"), log_path=engine_log)
    assert hook_log.exists()
    assert engine_log.exists()
    assert "h" in hook_log.read_text()
    assert "e" in engine_log.read_text()


def test_swallow_catches_and_logs(tmp_path):
    mod = _load_hook_logger()
    log = tmp_path / "swallow.log"
    SENTINEL = "D9-SWALLOW-CATCH-x9c2"

    def boom():
        raise RuntimeError(SENTINEL)

    # The context manager must not let the exception propagate
    with mod.swallow("test", "boom_check", log_path=log):
        boom()
        # If we reach here the exception was suppressed — but we may
        # not reach this line; what matters is no propagation OUT of
        # the with-block.

    assert log.exists()
    assert SENTINEL in log.read_text()


def test_swallow_does_not_swallow_keyboardinterrupt(tmp_path):
    """A user Ctrl-C must NOT be silenced."""
    mod = _load_hook_logger()
    log = tmp_path / "ki.log"
    with pytest.raises(KeyboardInterrupt):
        with mod.swallow("test", "ki_check", log_path=log):
            raise KeyboardInterrupt()


def test_swallow_does_not_swallow_systemexit(tmp_path):
    mod = _load_hook_logger()
    log = tmp_path / "se.log"
    with pytest.raises(SystemExit):
        with mod.swallow("test", "se_check", log_path=log):
            raise SystemExit(1)


def test_swallow_clean_block_no_log(tmp_path):
    """When no exception is raised, swallow must not write to the log.

    CHUNK H2 (2026-05-08): tightened from OR-faible
    `not log.exists() or log.read_text() == ""` to a strict invariant:
    after a clean block, the log file MUST NOT contain any entry. If
    the file exists at all, it must be empty (zero bytes). The handler
    constructor may have touched the file even without writing a
    record (RotatingFileHandler opens lazily) — both states accepted.
    """
    mod = _load_hook_logger()
    log = tmp_path / "clean.log"
    SENTINEL = "H2-CLEAN-BLOCK-MUST-NOT-LOG-7f4a"

    with mod.swallow("test", "clean", log_path=log):
        # Bind a variable using SENTINEL inside the block so the test
        # can prove no traceback containing SENTINEL leaked into the log.
        _local_marker = SENTINEL
        x = 1 + 1
        assert x == 2 and _local_marker == SENTINEL  # prove block ran

    # Strict invariant 1: no SENTINEL anywhere in the log path.
    if log.exists():
        content = log.read_text()
        assert SENTINEL not in content, (
            f"Clean block leaked the sentinel into the log: "
            f"{content!r}"
        )
        # Strict invariant 2: zero bytes (no record was emitted).
        assert log.stat().st_size == 0, (
            f"Log file is non-empty after clean block: "
            f"size={log.stat().st_size}, content={content!r}"
        )

    # Strict invariant 3: no .1/.2 backup file created either
    # (rotation should not trigger on a no-log run).
    backups = list(tmp_path.glob(f"{log.name}.*"))
    assert not backups, f"Unexpected rotation backups: {backups}"


def test_default_engine_log_path_constant():
    """A constant DEFAULT_ENGINE_LOG_PATH should be exposed for callers
    that want to log to the default file with `swallow(...)` (no
    log_path)."""
    mod = _load_hook_logger()
    assert hasattr(mod, "DEFAULT_ENGINE_LOG_PATH")
    p = mod.DEFAULT_ENGINE_LOG_PATH
    assert isinstance(p, Path)
    assert "engine" in str(p).lower()
