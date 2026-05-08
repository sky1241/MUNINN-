"""Centralised hook error logger with rotation + stderr fallback.

CHUNK A8 (2026-05-08): both bridge_hook._log_hook_error and
muninn_feed._log_sync_error wrote to ~/.muninn/hook_errors.log with
no rotation and `except Exception: pass` on the logging path itself.
Result: 700 lines accumulated in 14 days with no signal to the user.

This module exposes `log_hook_event(source, context, exc, log_path=...,
max_bytes=..., backup_count=...)` which:
  1. Writes a timestamped line to the log path with rotation
     (RotatingFileHandler).
  2. If the file is unwritable (disk full, perms), falls back to
     stderr so the audit trail is never silently lost.

Both legacy hooks should call this helper instead of their own
`try: ... except: pass` boilerplate.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A8
"""
import logging
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_PATH = Path.home() / ".muninn" / "hook_errors.log"
DEFAULT_MAX_BYTES = 1_000_000  # 1 MB
DEFAULT_BACKUP_COUNT = 3

# Cache of (path_str -> logger) so we do not attach handlers repeatedly.
_LOGGERS: dict[str, logging.Logger] = {}


def _build_logger(
    log_path: Path,
    max_bytes: int,
    backup_count: int,
) -> logging.Logger | None:
    """Build a rotating logger for `log_path`. Returns None on failure."""
    key = str(log_path)
    cached = _LOGGERS.get(key)
    if cached is not None:
        return cached
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger(f"muninn.hooks.{abs(hash(key))}")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        _LOGGERS[key] = logger
        return logger
    except (OSError, ValueError):
        return None


def _format_event(source: str, context: str, exc: BaseException) -> str:
    """Format one log line. Includes ISO timestamp + traceback."""
    ts = datetime.now().isoformat()
    head = f"{ts} [{source}:{context}] {type(exc).__name__}: {exc}"
    tail = traceback.format_exc()
    return f"{head}\n{tail}---"


def log_hook_event(
    source: str,
    context: str,
    exc: BaseException,
    log_path: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    """Append a hook error to the rotating log; fall back to stderr.

    Args:
        source: producer name, e.g. "bridge_hook" or "muninn_feed".
        context: the logical step that failed, e.g. "stdin_parse".
        exc: the exception caught upstream.
        log_path: override target file (default: ~/.muninn/hook_errors.log).
        max_bytes: rotate when file size exceeds this (default 1 MB).
        backup_count: number of .1, .2, ... backups to keep.

    Never raises — failure to log is itself swallowed but routed to
    stderr so the user has a chance to notice.
    """
    target = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    line = _format_event(source, context, exc)

    logger = _build_logger(target, max_bytes, backup_count)
    if logger is not None:
        try:
            logger.warning(line)
            return
        except Exception:
            # Logger built but emit failed — fall through to stderr.
            pass

    # Stderr fallback: never silent.
    try:
        sys.stderr.write(f"[MUNINN HOOK LOG fallback] {line}\n")
        sys.stderr.flush()
    except Exception:
        # Truly nothing we can do without re-raising; hooks must exit 0.
        pass


__all__ = ["log_hook_event", "DEFAULT_LOG_PATH", "DEFAULT_MAX_BYTES", "DEFAULT_BACKUP_COUNT"]
