"""CHUNK B2 — bridge_fast granular except (no silent empty).

`bridge_fast` had `except Exception: return ""` around the mycelium
load + iteration. ANY error (DB corruption, ImportError, missing
file) returned an empty bridge silently. Sky never sees that the
mycelium is broken.

Fix: classify the failure modes:
  - ImportError       -> warn once on stderr, return ""
  - FileNotFoundError -> first run / no DB yet -> info, return ""
  - any other         -> log via _hook_logger (audit trail), return ""

This way silent paths are limited to "expected, no signal needed",
while real errors get a stderr warning + persistent log entry.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B2
"""
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_tree():
    """Reuse the muninn_tree module loaded by other chunks if present;
    else load fresh under the bare name."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_tree" in sys.modules:
        return sys.modules["muninn_tree"]
    import muninn_tree
    return muninn_tree


def test_bridge_fast_returns_empty_on_clean_repo(tmp_path, monkeypatch):
    """No mycelium DB present (first run) → empty bridge, no exception."""
    mt = _load_muninn_tree()
    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    # No .muninn/mycelium.db → Mycelium will lazy-create one.
    # We just assert no crash on a clean repo.
    result = mt.bridge_fast("test mycelium tree compression")
    assert isinstance(result, str)


def test_bridge_fast_logs_on_unexpected_error(tmp_path, monkeypatch, capsys):
    """If Mycelium init raises an unexpected exception, the failure
    must be logged (stderr OR _hook_logger), not silenced."""
    mt = _load_muninn_tree()
    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()

    # Force a non-import, non-FileNotFound failure
    class _Boom(RuntimeError):
        pass

    # Ensure mycelium is loaded so we can patch its Mycelium class
    if "mycelium" not in sys.modules:
        try:
            import mycelium  # noqa: F401
        except Exception:
            pytest.skip("cannot load mycelium module here")
    if "mycelium" in sys.modules and hasattr(sys.modules["mycelium"], "Mycelium"):
        original = sys.modules["mycelium"].Mycelium

        def _broken_init(*args, **kwargs):
            raise _Boom("simulated backend failure")

        try:
            sys.modules["mycelium"].Mycelium = _broken_init
            result = mt.bridge_fast("test alpha beta gamma delta")
            assert result == "", f"expected silent fallback, got {result!r}"
            # The failure must surface SOMEWHERE — capture stderr OR the
            # rotating log. We accept either signal so the test isn't
            # over-coupled to one channel.
            captured = capsys.readouterr()
            log_path = Path.home() / ".muninn" / "hook_errors.log"
            log_text = log_path.read_text() if log_path.exists() else ""
            in_stderr = "simulated" in captured.err or "_Boom" in captured.err
            in_log = "simulated" in log_text or "_Boom" in log_text
            assert in_stderr or in_log, (
                "Unexpected error was silently swallowed — neither "
                "stderr nor the rotating log captured the audit trail"
            )
        finally:
            sys.modules["mycelium"].Mycelium = original
    else:
        pytest.skip("mycelium module not preloaded; skipping monkey-patch test")


def test_bridge_fast_no_concepts_returns_empty(tmp_path, monkeypatch):
    """Sanity: input with no qualifying concepts returns "" cleanly."""
    mt = _load_muninn_tree()
    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    # 3-letter-only words pass the regex but get filtered by len >= 4
    result = mt.bridge_fast("ok no go ya hi")
    assert result == ""


def test_bridge_fast_does_not_raise_on_garbage_input(tmp_path, monkeypatch):
    """Sanity: weird / empty / large input must not raise."""
    mt = _load_muninn_tree()
    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    for prompt in ["", "   ", "a" * 10000, "\x00\x01", "🔥🔥🔥"]:
        try:
            result = mt.bridge_fast(prompt)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"bridge_fast raised on input {prompt!r}: {e}")
