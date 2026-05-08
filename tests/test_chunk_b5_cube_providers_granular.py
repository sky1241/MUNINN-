"""CHUNK B5 — cube_providers._query_mycelium granular except.

`_query_mycelium` wraps the entire mycelium query in
`try: ... except Exception: pass; return []`. Any error (DB corruption,
NoneType, schema mismatch) silently returns an empty hint list, which
the caller (cube reconstruction) interprets as "no related concepts" —
no signal that something is broken.

Fix: keep the empty-list fallback (callers expect a list) but log the
exception so the audit trail records it. Caller behavior unchanged.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B5
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_cube_providers():
    """Load engine/core/cube_providers.py under a unique name."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    spec = importlib.util.spec_from_file_location(
        "_chunk_b5_cube_providers", engine_core / "cube_providers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        pytest.skip(f"cube_providers not loadable here: {e}")
    return mod


def test_query_mycelium_returns_list_on_clean_call():
    """Sanity: with a working mycelium, returns a list of concepts."""
    cp = _load_cube_providers()
    fake_mycelium = MagicMock()
    fake_mycelium.spread_activation = MagicMock(
        return_value=[("alpha", 0.9), ("beta", 0.5)]
    )
    result = cp._query_mycelium(fake_mycelium, ["seed1", "seed2"])
    assert result == ["alpha", "beta"]


def test_query_mycelium_returns_empty_on_no_methods():
    """If mycelium has neither spread_activation nor get_related, returns []."""
    cp = _load_cube_providers()
    fake_mycelium = object()  # plain object — no methods
    result = cp._query_mycelium(fake_mycelium, ["seed"])
    assert result == []


def test_query_mycelium_logs_on_exception(capsys):
    """When mycelium raises, the failure must be logged (stderr OR
    rotating log) AND the function returns []."""
    cp = _load_cube_providers()
    fake_mycelium = MagicMock()

    # Unique sentinel to avoid false positives from cross-test log pollution
    SENTINEL = "B5-CUBE-PROVIDERS-UNIQUE-SENTINEL-c3f9a2"

    class _Boom(RuntimeError):
        pass

    fake_mycelium.spread_activation = MagicMock(
        side_effect=_Boom(SENTINEL)
    )

    # CHUNK E7 (2026-05-08): _query_mycelium now uses _hook_logger.swallow()
    # which routes to engine_events.log (DEFAULT_ENGINE_LOG_PATH) instead
    # of hook_errors.log. Check both paths for backwards compat.
    hook_log = Path.home() / ".muninn" / "hook_errors.log"
    engine_log = Path.home() / ".muninn" / "engine_events.log"
    hook_before = hook_log.read_text() if hook_log.exists() else ""
    engine_before = engine_log.read_text() if engine_log.exists() else ""

    result = cp._query_mycelium(fake_mycelium, ["seed1"])
    assert result == []  # Empty fallback preserved

    captured = capsys.readouterr()
    hook_added = (hook_log.read_text() if hook_log.exists() else "")[len(hook_before):]
    engine_added = (engine_log.read_text() if engine_log.exists() else "")[len(engine_before):]

    in_stderr = SENTINEL in captured.err
    in_hook = SENTINEL in hook_added
    in_engine = SENTINEL in engine_added
    assert in_stderr or in_hook or in_engine, (
        "Mycelium error was silently swallowed: neither stderr nor "
        "newly-appended log captured the audit trail. "
        f"stderr={captured.err!r} "
        f"hook_added={hook_added[:150]!r} engine_added={engine_added[:150]!r}"
    )


def test_query_mycelium_handles_none_input():
    """Sanity: None mycelium → return [] cleanly (defensive)."""
    cp = _load_cube_providers()
    result = cp._query_mycelium(None, ["seed"])
    assert result == []
