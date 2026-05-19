"""CHUNK C5 (2026-05-19) — Forge file-level priority (F1).

Pre-fix: `files_to_scan` was iterated in disk/alphabetical order by
`_select_files`. High-risk files (per forge: high carmack/locate score)
processed last, low-risk first — wasteful for adaptive workflows that
should attack the dangerous code early.

Fix: after `_select_files` returns, sort `files_to_scan` by
`get_file_risk_map(repo).get(str(f), 0.0)` descending. Feature-flag
`MUNINN_FORGE_FILE_ORDERING=1` (default ON). Trace event
`pipeline.forge.file_ordering_applied`.

Locks the ordering invariant + flag dual ON/OFF behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE), str(ENGINE_CORE / "scanner")):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_forge_file_ordering_flag_default_enabled():
    """Default (no env) → _FORGE_FILE_ORDERING_ENABLED is True."""
    import importlib
    # Force reimport via fresh module from the orchestrator path
    sys.modules.pop("orchestrator", None)
    import orchestrator
    assert hasattr(orchestrator, "_FORGE_FILE_ORDERING_ENABLED")
    import os
    if os.environ.get("MUNINN_FORGE_FILE_ORDERING", "1") != "0":
        assert orchestrator._FORGE_FILE_ORDERING_ENABLED is True


def test_sort_files_by_forge_risk_helper_exists():
    """orchestrator exposes a helper `_sort_files_by_forge_risk(files, repo)`
    used in the scan pipeline. Direct unit access avoids running the
    full orchestrator for the test.
    """
    import orchestrator
    assert hasattr(orchestrator, "_sort_files_by_forge_risk")


def test_sort_files_by_forge_risk_orders_descending(tmp_path, monkeypatch):
    """Highest-risk files come first."""
    import orchestrator
    # Mock the forge risk map
    monkeypatch.setattr(
        orchestrator, "_get_file_risk_map_safe",
        lambda repo: {"a.py": 0.2, "b.py": 0.9, "c.py": 0.5},
    )
    files = ["a.py", "b.py", "c.py"]
    sorted_files = orchestrator._sort_files_by_forge_risk(files, tmp_path)
    assert sorted_files == ["b.py", "c.py", "a.py"], sorted_files


def test_sort_files_by_forge_risk_missing_files_get_zero(tmp_path, monkeypatch):
    """Files not in the risk map are ranked as 0.0 (no signal = bottom)."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_get_file_risk_map_safe",
        lambda repo: {"hot.py": 0.8},
    )
    files = ["cold.py", "hot.py", "unknown.py"]
    sorted_files = orchestrator._sort_files_by_forge_risk(files, tmp_path)
    # hot.py first; the rest in stable order (0.0 tied)
    assert sorted_files[0] == "hot.py"
    assert set(sorted_files[1:]) == {"cold.py", "unknown.py"}


def test_sort_files_by_forge_risk_empty_map_keeps_original_order(tmp_path, monkeypatch):
    """Forge unavailable / cache empty → returns files unchanged."""
    import orchestrator
    monkeypatch.setattr(orchestrator, "_get_file_risk_map_safe", lambda repo: {})
    files = ["x.py", "y.py", "z.py"]
    sorted_files = orchestrator._sort_files_by_forge_risk(files, tmp_path)
    assert sorted_files == files  # original order preserved


def test_sort_files_by_forge_risk_flag_off_returns_unchanged(tmp_path, monkeypatch):
    """When _FORGE_FILE_ORDERING_ENABLED is False, no sort applied
    (legacy behavior, §8.B feature flag dual test).
    """
    import orchestrator
    monkeypatch.setattr(orchestrator, "_FORGE_FILE_ORDERING_ENABLED", False)
    # Even with a risk map, flag OFF wins.
    monkeypatch.setattr(
        orchestrator, "_get_file_risk_map_safe",
        lambda repo: {"a.py": 0.1, "b.py": 0.9},
    )
    files = ["a.py", "b.py"]
    result = orchestrator._sort_files_by_forge_risk(files, tmp_path)
    assert result == files, "flag OFF must preserve original order"


def test_sort_emits_pipeline_trace_event(tmp_path, monkeypatch):
    """Per §8.F, emits `pipeline.forge.file_ordering_applied` with
    {repo, n_files, n_with_risk, top_3}."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_get_file_risk_map_safe",
        lambda repo: {"a.py": 0.7, "b.py": 0.4, "c.py": 0.9},
    )
    captured: list = []
    monkeypatch.setattr(
        orchestrator, "log_event",
        lambda name, data=None, level="info": captured.append((name, dict(data or {}))),
    )
    orchestrator._sort_files_by_forge_risk(["a.py", "b.py", "c.py"], tmp_path)
    events = [c for c in captured if c[0] == "pipeline.forge.file_ordering_applied"]
    assert len(events) == 1, f"expected 1 trace event, got: {captured}"
    data = events[0][1]
    assert data["n_files"] == 3
    assert data.get("top_3") == ["c.py", "a.py", "b.py"]
