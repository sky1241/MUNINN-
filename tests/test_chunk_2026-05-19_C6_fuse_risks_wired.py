"""CHUNK C6 (2026-05-19) — fuse_risks wiré dans reconstruct_adaptive (F2).

Pre-fix: `_run_level_pass` itère `to_test` dans l'ordre naturel
(line_start ascending). Sky's design demanded that cubes be ordered
low-risk → high-risk so the stable ones become reliable context for the
fragile ones. `fuse_risks(store, forge_root)` exists since 2026-04 but
zero call site at runtime.

Fix:
  - `reconstruct_adaptive(..., forge_root=None)` signature étendue.
  - Si forge_root + flag MUNINN_FUSE_RISKS_ORDERING=1 (default):
    helper `_sort_to_test_by_risk` réordonne `to_test` (low-risk first).
  - Feature flag `MUNINN_FUSE_RISKS_ORDERING=0` → ordre legacy.
  - Pipeline_trace event `pipeline.engine.reco.cube_ordering_applied`.

Locks the wiring + flag dual ON/OFF + ordering semantics.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_fuse_risks_ordering_flag_default_enabled():
    """Default (no env) → _FUSE_RISKS_ORDERING_ENABLED is True."""
    import cube_providers
    assert hasattr(cube_providers, "_FUSE_RISKS_ORDERING_ENABLED")
    import os
    if os.environ.get("MUNINN_FUSE_RISKS_ORDERING", "1") != "0":
        assert cube_providers._FUSE_RISKS_ORDERING_ENABLED is True


def test_sort_helper_exists():
    """cube_providers exposes _sort_to_test_by_risk(to_test, cubes, store, forge_root)."""
    import cube_providers
    assert hasattr(cube_providers, "_sort_to_test_by_risk")


def test_sort_no_forge_root_returns_unchanged():
    """Without forge_root, to_test is returned untouched (legacy)."""
    import cube_providers
    to_test = [3, 1, 5, 0, 2]
    result = cube_providers._sort_to_test_by_risk(to_test, [], None, None)
    assert result == to_test


def test_sort_flag_off_returns_unchanged(monkeypatch):
    """MUNINN_FUSE_RISKS_ORDERING=0 → no sort (§8.B feature flag OFF)."""
    import cube_providers
    monkeypatch.setattr(cube_providers, "_FUSE_RISKS_ORDERING_ENABLED", False)
    to_test = [4, 2, 0]
    result = cube_providers._sort_to_test_by_risk(to_test, [], None, Path("/fake"))
    assert result == to_test


def test_sort_low_risk_first_when_forge_root_given(tmp_path, monkeypatch):
    """When forge_root + fuse_risks data present, to_test sorted by
    combined risk ASCENDING (low first → contexte stable)."""
    import cube_providers
    from cube import Cube, sha256_hash

    # 3 cubes; mock fuse_risks to return per-file risk by file_origin.
    cubes = []
    for i, fo in enumerate(["a.py", "b.py", "c.py"]):
        c = Cube(id=f"c{i}", sha256=sha256_hash(f"x{i}"),
                 content=f"x{i}", file_origin=fo,
                 line_start=i, line_end=i, level=1,
                 score=0.0, temperature=0.5, token_count=5)
        cubes.append(c)

    fake_store = object()

    def fake_fuse_risks(store, forge_root, **kw):
        return [
            {"file": "a.py", "combined": 0.7, "forge_risk": 0.5, "cube_temp": 0.5, "hot_cubes": []},
            {"file": "b.py", "combined": 0.2, "forge_risk": 0.1, "cube_temp": 0.3, "hot_cubes": []},
            {"file": "c.py", "combined": 0.9, "forge_risk": 0.8, "cube_temp": 0.5, "hot_cubes": []},
        ]

    # _sort_to_test_by_risk imports fuse_risks lazily from cube_analysis,
    # so monkeypatch the source module.
    import cube_analysis
    monkeypatch.setattr(cube_analysis, "fuse_risks", fake_fuse_risks)
    result = cube_providers._sort_to_test_by_risk(
        [0, 1, 2], cubes, fake_store, tmp_path,
    )
    # b.py risk=0.2 (lowest), a.py=0.7, c.py=0.9 → indices 1, 0, 2
    assert result == [1, 0, 2], (
        f"expected low-risk first [1, 0, 2], got {result}"
    )


def test_sort_emits_pipeline_trace_event(tmp_path, monkeypatch):
    """Emits `pipeline.engine.reco.cube_ordering_applied` with
    {n_cubes, n_with_risk}."""
    import cube_providers
    from cube import Cube, sha256_hash

    cubes = [Cube(id=f"c{i}", sha256=sha256_hash(f"x{i}"),
                  content=f"x{i}", file_origin=f"f{i}.py",
                  line_start=i, line_end=i, level=1,
                  score=0.0, temperature=0.5, token_count=5)
             for i in range(2)]
    import cube_analysis
    monkeypatch.setattr(
        cube_analysis, "fuse_risks",
        lambda store, fr, **kw: [
            {"file": "f0.py", "combined": 0.3, "forge_risk": 0.2, "cube_temp": 0.4, "hot_cubes": []},
            {"file": "f1.py", "combined": 0.7, "forge_risk": 0.6, "cube_temp": 0.8, "hot_cubes": []},
        ],
    )
    captured: list = []
    monkeypatch.setattr(
        cube_providers, "log_event",
        lambda name, data=None, level="info": captured.append((name, dict(data or {}))),
    )
    cube_providers._sort_to_test_by_risk([0, 1], cubes, object(), tmp_path)
    events = [c for c in captured if c[0] == "pipeline.engine.reco.cube_ordering_applied"]
    assert len(events) == 1, f"expected 1 trace event, got: {captured}"
    data = events[0][1]
    assert data["n_cubes"] == 2
    assert data["n_with_risk"] == 2


def test_reconstruct_adaptive_accepts_forge_root_kwarg():
    """reconstruct_adaptive signature includes optional forge_root."""
    import cube_providers
    import inspect
    sig = inspect.signature(cube_providers.reconstruct_adaptive)
    assert "forge_root" in sig.parameters, (
        f"reconstruct_adaptive must accept forge_root kwarg, got: "
        f"{list(sig.parameters)}"
    )
    # Default = None for backward compat
    assert sig.parameters["forge_root"].default is None
