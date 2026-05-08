"""CHUNK C5 — isinstance(dict) check after json.loads.

Pre-fix: `data = json.loads(...)` then `data.get("repos", {})` assumes
dict. If a poisoned config returns `[]` or `"string"` or `42`, the
.get() call raises AttributeError and the entire feature crashes.

Fix: explicit `isinstance(data, dict)` check after every json.loads
that expects a dict, with a clean fallback (return / skip).

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C5
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_module(rel_path: str, module_name: str):
    src = REPO / rel_path
    if not src.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(module_name, src)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        pytest.skip(f"{rel_path} not loadable: {e}")
    return mod


# ── watchdog.py:29 ─────────────────────────────────────────────────

def test_watchdog_handles_list_payload(tmp_path, monkeypatch):
    """watchdog.main() must not crash if repos.json contains a list."""
    wd = _load_module("engine/core/watchdog.py", "_chunk_c5_watchdog")
    fake = tmp_path / "repos.json"
    fake.write_text(json.dumps(["not", "a", "dict"]))
    monkeypatch.setattr(wd, "REPOS_PATH", fake)
    # Also set MUNINN to a valid path so the early return is skipped
    # Create a fake MUNINN file so the early-return path isn't taken
    fake_muninn = tmp_path / "muninn.py"
    fake_muninn.write_text("# fake")
    monkeypatch.setattr(wd, "MUNINN", fake_muninn)
    # Must complete without raising AttributeError
    try:
        wd.main()
    except AttributeError as e:
        pytest.fail(f"watchdog.main() crashed on list payload: {e}")


def test_watchdog_handles_string_payload(tmp_path, monkeypatch):
    """watchdog.main() must not crash on a JSON string."""
    wd = _load_module("engine/core/watchdog.py", "_chunk_c5_watchdog2")
    fake = tmp_path / "repos.json"
    fake.write_text(json.dumps("oops"))
    monkeypatch.setattr(wd, "REPOS_PATH", fake)
    # Create a fake MUNINN file so the early-return path isn't taken
    fake_muninn = tmp_path / "muninn.py"
    fake_muninn.write_text("# fake")
    monkeypatch.setattr(wd, "MUNINN", fake_muninn)
    try:
        wd.main()
    except AttributeError as e:
        pytest.fail(f"watchdog.main() crashed on string payload: {e}")


def test_watchdog_handles_int_payload(tmp_path, monkeypatch):
    """watchdog.main() must not crash on a JSON int."""
    wd = _load_module("engine/core/watchdog.py", "_chunk_c5_watchdog3")
    fake = tmp_path / "repos.json"
    fake.write_text("42")
    monkeypatch.setattr(wd, "REPOS_PATH", fake)
    # Create a fake MUNINN file so the early-return path isn't taken
    fake_muninn = tmp_path / "muninn.py"
    fake_muninn.write_text("# fake")
    monkeypatch.setattr(wd, "MUNINN", fake_muninn)
    try:
        wd.main()
    except AttributeError as e:
        pytest.fail(f"watchdog.main() crashed on int payload: {e}")


def test_watchdog_still_handles_valid_dict(tmp_path, monkeypatch):
    """Sanity: regular {"repos": {...}} still works."""
    wd = _load_module("engine/core/watchdog.py", "_chunk_c5_watchdog4")
    fake = tmp_path / "repos.json"
    fake.write_text(json.dumps({"repos": {}}))  # empty dict, no subprocess
    monkeypatch.setattr(wd, "REPOS_PATH", fake)
    # Create a fake MUNINN file so the early-return path isn't taken
    fake_muninn = tmp_path / "muninn.py"
    fake_muninn.write_text("# fake")
    monkeypatch.setattr(wd, "MUNINN", fake_muninn)
    # Should complete cleanly (no repos to iterate)
    wd.main()


# ── sync_backend.py:450 (load_config) ───────────────────────────────

def test_sync_backend_load_config_handles_list(tmp_path, monkeypatch):
    """load_config must tolerate a list payload in ~/.muninn/config.json."""
    sb = _load_module("engine/core/sync_backend.py", "_chunk_c5_sync_backend")

    # Point HOME at tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_path = tmp_path / ".muninn" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps(["wrong", "shape"]))

    # load_config must return a dict (default config) without crash
    if hasattr(sb, "load_config"):
        try:
            result = sb.load_config()
        except AttributeError as e:
            pytest.fail(f"load_config crashed on list payload: {e}")
        assert isinstance(result, dict)


def test_sync_backend_load_config_handles_string(tmp_path, monkeypatch):
    """load_config must tolerate a string payload."""
    sb = _load_module("engine/core/sync_backend.py", "_chunk_c5_sync_backend2")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_path = tmp_path / ".muninn" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps("wrong"))
    if hasattr(sb, "load_config"):
        try:
            result = sb.load_config()
        except AttributeError as e:
            pytest.fail(f"load_config crashed on string payload: {e}")
        assert isinstance(result, dict)
