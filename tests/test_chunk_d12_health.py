"""CHUNK D12 — muninn_layers.health() exposes optional-module status.

Pre-fix: muninn_layers.py imports lexicons / dedup / budget_select
inside try/except so a missing or broken optional module is degraded
silently. The user has no way to ask "are my optional features
loaded?" except by reading the import stack manually.

Fix: a `health()` function returns a dict of per-module status. Wired
later into `muninn doctor` (or callable directly).

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D12
"""
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_layers():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_layers" in sys.modules:
        return sys.modules["muninn_layers"]
    import muninn_layers
    return muninn_layers


def test_health_exists():
    ml = _load_muninn_layers()
    assert hasattr(ml, "health"), "muninn_layers.health() missing — see CHUNK D12"


def test_health_returns_dict():
    ml = _load_muninn_layers()
    result = ml.health()
    assert isinstance(result, dict)


def test_health_reports_lexicons():
    ml = _load_muninn_layers()
    h = ml.health()
    assert "lexicons_tier1" in h, "health must report lexicons tier1 status"
    assert isinstance(h["lexicons_tier1"], bool)


def test_health_reports_dedup():
    ml = _load_muninn_layers()
    h = ml.health()
    assert "dedup" in h
    assert isinstance(h["dedup"], bool)


def test_health_reports_budget_select():
    ml = _load_muninn_layers()
    h = ml.health()
    assert "budget_select" in h
    assert isinstance(h["budget_select"], bool)


def test_health_matches_actual_module_state():
    """If dedup was loaded successfully, health()['dedup'] must be True."""
    ml = _load_muninn_layers()
    h = ml.health()
    # The internal flag tracks the same state
    expected_dedup = ml._DEDUP_AVAILABLE
    expected_budget = ml._BUDGET_SELECT_AVAILABLE
    assert h["dedup"] == expected_dedup
    assert h["budget_select"] == expected_budget


def test_health_includes_pipeline_summary():
    """health() should also indicate L9 status (anthropic + API key)."""
    ml = _load_muninn_layers()
    h = ml.health()
    # L9 reports the SKIP flag and whether anthropic is importable
    assert "l9_active" in h or "l9" in h, (
        "health must report L9 (LLM) availability"
    )
