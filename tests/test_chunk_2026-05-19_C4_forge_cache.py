"""CHUNK C4 (2026-05-19) — Forge cache infrastructure (F0).

Pre-fix: `get_repo_risk(repo)` already exists and caches forge-shield
results in `.muninn/forge_cache.json` for 24h. But to feed C5
(file-level priority) and C6 (cube-level fuse_risks ordering), we
need a flat `dict[file_path, score]` accessor, not the full
ForgeRiskReport dataclass.

Fix: new `get_file_risk_map(repo, ttl_seconds)` that returns
`report.fused` as a plain dict, with a pipeline_trace event
`pipeline.forge.risk_map_cached` for the sandbox monitor.

Locks the public surface + the trace event shape.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_get_file_risk_map_exists():
    """forge_metrics exposes a public `get_file_risk_map` function."""
    import forge_metrics
    assert hasattr(forge_metrics, "get_file_risk_map")
    assert callable(forge_metrics.get_file_risk_map)


def test_get_file_risk_map_returns_flat_dict(tmp_path, monkeypatch):
    """Returns a plain `dict[str, float]` (not the dataclass)."""
    import forge_metrics
    # Mock get_repo_risk to avoid shelling out to forge-shield
    fake_report = forge_metrics.ForgeRiskReport(
        repo=tmp_path,
        fused={"file_a.py": 0.7, "file_b.py": 0.3},
        forge_available=True,
    )
    monkeypatch.setattr(forge_metrics, "get_repo_risk",
                        lambda repo, **kw: fake_report)
    result = forge_metrics.get_file_risk_map(tmp_path)
    assert isinstance(result, dict)
    assert result == {"file_a.py": 0.7, "file_b.py": 0.3}


def test_get_file_risk_map_returns_empty_when_forge_unavailable(
    tmp_path, monkeypatch
):
    """Forge not installed → ForgeRiskReport.forge_available=False.
    get_file_risk_map must return {} (graceful degradation)."""
    import forge_metrics
    fake_report = forge_metrics.ForgeRiskReport(
        repo=tmp_path, fused={}, forge_available=False,
        error="forge binary not found",
    )
    monkeypatch.setattr(forge_metrics, "get_repo_risk",
                        lambda repo, **kw: fake_report)
    result = forge_metrics.get_file_risk_map(tmp_path)
    assert result == {}


def test_get_file_risk_map_emits_pipeline_trace_event(tmp_path, monkeypatch):
    """The function emits `pipeline.forge.risk_map_cached` with
    {repo, n_files, available} so the sandbox monitor sees forge state.
    """
    import forge_metrics
    fake_report = forge_metrics.ForgeRiskReport(
        repo=tmp_path,
        fused={"x.py": 0.5, "y.py": 0.8, "z.py": 0.1},
        forge_available=True,
    )
    monkeypatch.setattr(forge_metrics, "get_repo_risk",
                        lambda repo, **kw: fake_report)

    captured: list = []

    def fake_log(name, data=None, level="info"):
        captured.append((name, dict(data or {})))

    monkeypatch.setattr(forge_metrics, "log_event", fake_log)
    forge_metrics.get_file_risk_map(tmp_path)

    events = [c for c in captured if c[0] == "pipeline.forge.risk_map_cached"]
    assert len(events) == 1, (
        f"expected 1 pipeline.forge.risk_map_cached event, got {captured}"
    )
    data = events[0][1]
    assert data["repo"] == str(tmp_path)
    assert data["n_files"] == 3
    assert data["available"] is True


def test_get_file_risk_map_passes_through_ttl(tmp_path, monkeypatch):
    """The ttl_seconds arg is forwarded to get_repo_risk's cache TTL."""
    import forge_metrics
    captured_kwargs: dict = {}

    def spy_get_repo_risk(repo, **kw):
        captured_kwargs.update(kw)
        return forge_metrics.ForgeRiskReport(repo=repo)

    monkeypatch.setattr(forge_metrics, "get_repo_risk", spy_get_repo_risk)
    forge_metrics.get_file_risk_map(tmp_path, ttl_seconds=42)
    assert captured_kwargs.get("ttl_seconds") == 42


def test_get_file_risk_map_cached_uses_default_ttl():
    """Default ttl matches the module constant (24h = 86400s)."""
    import forge_metrics
    import inspect
    sig = inspect.signature(forge_metrics.get_file_risk_map)
    default_ttl = sig.parameters["ttl_seconds"].default
    # Either the module constant or its int value
    assert default_ttl == forge_metrics._CACHE_TTL_SECONDS, (
        f"default ttl should be _CACHE_TTL_SECONDS "
        f"(={forge_metrics._CACHE_TTL_SECONDS}), got {default_ttl}"
    )
