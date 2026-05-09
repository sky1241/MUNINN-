"""CHUNK F6 — forge_metrics module (cube heatmap UX wiring).

Phase F6 of BATTLE_PLAN_FORGE_FINDINGS_2026-05-09.md.

The forge_metrics module fetches forge-shield risk scores (carmack +
locate + modularity) and caches them on disk for the cube heatmap UX
to consume. These tests pin the parsing + fusion + cache + colour
mapping behaviour without ever shelling out to a real `forge` binary.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _load_forge_metrics():
    """Standard import via sys.path injected by conftest. Cached in
    sys.modules so dataclass() can resolve cls.__module__ namespace."""
    import forge_metrics  # noqa: F401
    import importlib
    return importlib.reload(forge_metrics)


# ── Parsers ──────────────────────────────────────────────────────


def test_parse_carmack_extracts_score_and_path():
    fm = _load_forge_metrics()
    sample = """\
============================================================
  CARMACK PREDICT — Cross-domain defect prediction
============================================================
  0.558  engine/core/muninn.py
       Kalman=4.47  Wavelet=2499519.4  Crash=49%
  0.293  engine/core/mycelium.py
       Kalman=2.77  Wavelet=2456388.9  Crash=40%
============================================================
"""
    out = fm._parse_carmack(sample)
    assert out == {
        "engine/core/muninn.py": 0.558,
        "engine/core/mycelium.py": 0.293,
    }


def test_parse_locate_keeps_max_per_file():
    fm = _load_forge_metrics()
    sample = """\
  0.71  engine/core/cube.py:16  import hashlib
  0.71  engine/core/cube.py:17  import json
  0.85  engine/core/cube.py:42  some_thing
  0.40  engine/core/mycelium.py:5  import sqlite3
"""
    out = fm._parse_locate(sample)
    assert out["engine/core/cube.py"] == 0.85  # max of 3 entries
    assert out["engine/core/mycelium.py"] == 0.40


def test_parse_modularity_q_finds_global_value():
    fm = _load_forge_metrics()
    assert fm._parse_modularity_q("  Q = 0.677 (good — modules well isolated)") == 0.677
    assert fm._parse_modularity_q("no Q value here") is None


# ── Fusion ───────────────────────────────────────────────────────


def test_fuse_combines_carmack_and_locate_with_weights():
    fm = _load_forge_metrics()
    carmack = {"a.py": 0.8}
    locate = {"a.py": 0.5}
    fused = fm._fuse(carmack, locate, modularity_q=0.5)
    # 0.5 * 0.8 + 0.4 * 0.5 + 0.1 * 0 (Q=0.5 ≥ 0.30 → no penalty) = 0.6
    assert abs(fused["a.py"] - 0.6) < 1e-9


def test_fuse_applies_coupling_penalty_when_q_below_threshold():
    fm = _load_forge_metrics()
    carmack = {"a.py": 0.0}
    locate = {"a.py": 0.0}
    # Q = 0.15 → penalty = (0.30 - 0.15) / 0.30 = 0.5
    fused = fm._fuse(carmack, locate, modularity_q=0.15)
    assert abs(fused["a.py"] - 0.05) < 1e-9  # 0.1 * 0.5


def test_fuse_clamps_to_one():
    fm = _load_forge_metrics()
    carmack = {"a.py": 1.0}
    locate = {"a.py": 1.0}
    fused = fm._fuse(carmack, locate, modularity_q=0.0)
    assert fused["a.py"] == 1.0


# ── Colour mapping ───────────────────────────────────────────────


def test_color_for_score_thresholds():
    fm = _load_forge_metrics()
    assert fm.color_for_score(0.85) == "#d62728"  # red
    assert fm.color_for_score(0.70) == "#d62728"  # red boundary
    assert fm.color_for_score(0.55) == "#ff7f0e"  # orange
    assert fm.color_for_score(0.40) == "#ff7f0e"  # orange boundary
    assert fm.color_for_score(0.30) == "#bcbd22"  # yellow
    assert fm.color_for_score(0.20) == "#bcbd22"  # yellow boundary
    assert fm.color_for_score(0.05) == "#2ca02c"  # green


# ── Cache ────────────────────────────────────────────────────────


def test_cache_round_trip(tmp_path):
    fm = _load_forge_metrics()
    repo = tmp_path / "fake_repo"
    (repo / ".muninn").mkdir(parents=True)
    report = fm.ForgeRiskReport(
        repo=repo,
        carmack={"a.py": 0.5},
        locate={"a.py": 0.3},
        modularity_q=0.6,
        fused={"a.py": 0.37},
    )
    fm._save_cache(report)
    loaded = fm._load_cached(repo, ttl=10_000)
    assert loaded is not None
    assert loaded.carmack == {"a.py": 0.5}
    assert loaded.fused == {"a.py": 0.37}
    assert loaded.modularity_q == 0.6


def test_cache_expires_after_ttl(tmp_path):
    fm = _load_forge_metrics()
    repo = tmp_path / "fake_repo"
    (repo / ".muninn").mkdir(parents=True)
    report = fm.ForgeRiskReport(
        repo=repo, captured_at=time.time() - 100,  # 100s old
        carmack={"a.py": 0.5},
    )
    fm._save_cache(report)
    # ttl=50s → 100s old must be considered stale
    assert fm._load_cached(repo, ttl=50) is None
    # ttl=200s → still fresh
    assert fm._load_cached(repo, ttl=200) is not None


# ── Public entry point — graceful degradation ────────────────────


def test_get_repo_risk_returns_unavailable_when_forge_missing(tmp_path, monkeypatch):
    """If `forge` is not on PATH, get_repo_risk must return a sentinel
    report (forge_available=False) without raising."""
    fm = _load_forge_metrics()
    repo = tmp_path / "fake_repo"
    (repo / ".muninn").mkdir(parents=True)

    monkeypatch.setattr(fm, "_forge_binary_available", lambda: False)
    report = fm.get_repo_risk(repo)
    assert report.forge_available is False
    assert report.fused == {}
    assert "forge-shield" in (report.error or "")


def test_get_repo_risk_uses_cache_on_second_call(tmp_path, monkeypatch):
    """First call shells out (here mocked); second call reads cache."""
    fm = _load_forge_metrics()
    repo = tmp_path / "fake_repo"
    (repo / ".muninn").mkdir(parents=True)

    call_count = {"forge": 0}

    def fake_forge_binary_available():
        return True

    def fake_run_forge(repo, *args):
        call_count["forge"] += 1
        if "--carmack" in args:
            return ("  0.5  engine/core/foo.py\n", 0)
        if "--locate" in args:
            return ("  0.3  engine/core/foo.py:10  bar\n", 0)
        if "--modularity" in args:
            return ("  Q = 0.677\n", 0)
        return ("", 0)

    monkeypatch.setattr(fm, "_forge_binary_available", fake_forge_binary_available)
    monkeypatch.setattr(fm, "_run_forge", fake_run_forge)

    r1 = fm.get_repo_risk(repo)
    assert call_count["forge"] == 3  # carmack + locate + modularity
    assert "engine/core/foo.py" in r1.fused

    r2 = fm.get_repo_risk(repo)
    assert call_count["forge"] == 3  # cache hit, no extra shell-out
    assert r2.fused == r1.fused
