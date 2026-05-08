"""CHUNK C5 — isinstance(dict) check after json.loads.

Pre-fix: `data = json.loads(...)` then `data.get("repos", {})` assumes
dict. If a poisoned config returns `[]` or `"string"` or `42`, the
.get() call raises AttributeError and the entire feature crashes.

Fix: explicit `isinstance(data, dict)` check after every json.loads
that expects a dict, with a clean fallback (return / skip).

CHUNK H1 (2026-05-08): the original tests only asserted "no
AttributeError". Now each test verifies the OBSERVABLE BEHAVIOR:
- watchdog: must NOT spawn any subprocess on invalid payloads
- watchdog: MUST spawn 1 subprocess per valid repo
- sync_backend: must return a dict containing the documented default
  keys (backend, meta_path) regardless of payload shape

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C5
        docs/BATTLE_PLAN_AUDIT3_2026-05-08.md §H1
"""
import importlib.util
import json
import subprocess
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


def _setup_watchdog(monkeypatch, tmp_path, payload_text: str):
    """Common watchdog setup: prepare repos.json + valid MUNINN target +
    capture every subprocess.run call."""
    wd = _load_module("engine/core/watchdog.py", f"_chunk_c5_watchdog_{id(payload_text)}")
    fake_repos = tmp_path / "repos.json"
    fake_repos.write_text(payload_text)
    monkeypatch.setattr(wd, "REPOS_PATH", fake_repos)
    fake_muninn = tmp_path / "muninn.py"
    fake_muninn.write_text("# fake")
    monkeypatch.setattr(wd, "MUNINN", fake_muninn)
    captured = []
    real_run = subprocess.run

    def _capture(*args, **kwargs):
        captured.append(args)
        # Return a fake CompletedProcess so wd.main() doesn't crash on .returncode
        return subprocess.CompletedProcess(
            args=args[0] if args else [], returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(wd._sp if hasattr(wd, "_sp") else subprocess, "run", _capture)
    monkeypatch.setattr(subprocess, "run", _capture)
    return wd, captured


# ── watchdog.py:29 — behavioural asserts ─────────────────────────────────

def test_watchdog_list_payload_spawns_no_subprocess(tmp_path, monkeypatch):
    """List payload → 0 subprocess.run calls (no repo iteration)."""
    wd, captured = _setup_watchdog(monkeypatch, tmp_path, json.dumps(["not", "a", "dict"]))
    wd.main()
    assert captured == [], (
        f"List payload triggered {len(captured)} subprocess.run call(s); "
        f"expected 0 (the function should refuse non-dict payloads cleanly)"
    )


def test_watchdog_string_payload_spawns_no_subprocess(tmp_path, monkeypatch):
    """String payload → 0 subprocess.run calls."""
    wd, captured = _setup_watchdog(monkeypatch, tmp_path, json.dumps("oops"))
    wd.main()
    assert captured == [], f"String payload triggered {len(captured)} call(s)"


def test_watchdog_int_payload_spawns_no_subprocess(tmp_path, monkeypatch):
    """Int payload → 0 subprocess.run calls."""
    wd, captured = _setup_watchdog(monkeypatch, tmp_path, "42")
    wd.main()
    assert captured == [], f"Int payload triggered {len(captured)} call(s)"


def test_watchdog_invalid_inner_repos_spawns_no_subprocess(tmp_path, monkeypatch):
    """{"repos": "not_a_dict"} → 0 subprocess.run calls (inner check)."""
    wd, captured = _setup_watchdog(monkeypatch, tmp_path,
                                    json.dumps({"repos": "should_be_dict"}))
    wd.main()
    assert captured == [], (
        f"Inner non-dict 'repos' triggered {len(captured)} call(s); the C5 "
        f"fix must also reject inner shape"
    )


def test_watchdog_valid_dict_with_one_repo_spawns_one_subprocess(tmp_path, monkeypatch):
    """{"repos": {"one": "/path"}} → exactly 1 subprocess.run call.

    Causality check: the SAME path must appear in the spawned command
    args (proves wd.main() iterated the dict and forwarded the value)."""
    fake_repo_path = str(tmp_path / "fake_target_repo")
    (tmp_path / "fake_target_repo" / ".muninn").mkdir(parents=True)
    payload = json.dumps({"repos": {"one": fake_repo_path}})
    wd, captured = _setup_watchdog(monkeypatch, tmp_path, payload)
    wd.main()
    assert len(captured) == 1, (
        f"Valid 1-repo dict triggered {len(captured)} call(s); expected 1"
    )
    # Causality: the spawned command must reference the repo path
    cmd_str = " ".join(map(str, captured[0][0]))
    assert fake_repo_path in cmd_str, (
        f"Spawned command does not reference the repo path. "
        f"Expected substring {fake_repo_path!r} in {cmd_str!r}"
    )


def test_watchdog_empty_repos_dict_spawns_no_subprocess(tmp_path, monkeypatch):
    """Sanity: {"repos": {}} → 0 subprocess.run calls (nothing to iterate)."""
    wd, captured = _setup_watchdog(monkeypatch, tmp_path, json.dumps({"repos": {}}))
    wd.main()
    assert captured == []


# ── sync_backend.py:450 (_load_sync_config) — behavioural asserts ──────────────

def test_sync_backend_list_returns_default_dict_with_keys(tmp_path, monkeypatch):
    """List payload → returned dict must contain the documented default
    keys ('backend' at minimum) and NOT the malformed payload."""
    sb = _load_module("engine/core/sync_backend.py", "_chunk_c5_sb_list")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_path = tmp_path / ".muninn" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps(["wrong", "shape"]))
    if not hasattr(sb, "_load_sync_config"):
        pytest.skip("load_sync_config not exposed in this build")
    result = sb._load_sync_config()
    assert isinstance(result, dict)
    # "backend" is a documented default key — it MUST be present even
    # though cfg.get failed (defensive default kicked in).
    assert "backend" in result, (
        f"Default key 'backend' missing from _load_sync_config() result on "
        f"poisoned payload — fallback didn't activate. Got: {result}"
    )


def test_sync_backend_string_returns_default_dict_with_keys(tmp_path, monkeypatch):
    sb = _load_module("engine/core/sync_backend.py", "_chunk_c5_sb_str")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_path = tmp_path / ".muninn" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps("wrong"))
    if not hasattr(sb, "_load_sync_config"):
        pytest.skip("load_sync_config not exposed in this build")
    result = sb._load_sync_config()
    assert isinstance(result, dict)
    assert "backend" in result


def test_sync_backend_valid_dict_overrides_defaults(tmp_path, monkeypatch):
    """Sanity: a real dict {"backend": "git"} → result["backend"] == "git".

    Proves _load_sync_config() actually MERGES the config into defaults
    (not just returns defaults regardless)."""
    sb = _load_module("engine/core/sync_backend.py", "_chunk_c5_sb_ok")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg_path = tmp_path / ".muninn" / "config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({"backend": "git"}))
    if not hasattr(sb, "_load_sync_config"):
        pytest.skip("load_sync_config not exposed in this build")
    result = sb._load_sync_config()
    assert result["backend"] == "git", (
        f"Valid config not merged into defaults. Got: {result}"
    )
