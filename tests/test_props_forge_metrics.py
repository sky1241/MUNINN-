#!/usr/bin/env python3
"""Property-based tests for forge_metrics.py — CURATED post-E3 remediation.

CHUNK E3 (REMEDIATION-2) — pré-E3 ce fichier contenait 5 tests
auto-générés par forge --gen-props, tous suivant le pattern
`test_X_no_crash` avec `try: f(...) except Exception: pass`. 4 d'entre
eux prenaient des `Path` real-filesystem comme paramètres : passer
`st.text(max_size=50)` génère des strings random qui font crash le
filesystem lookup → AttributeError/OSError swallowed → test passe sans
rien tester.

Hypothesis avait laissé 4 patches non triés dans `.hypothesis/patches/`
(2026-05-19 : `031be5e6`, `dadd3197`, `d07a90f1`, `1dbfd94b`) — bugs
réels jamais regardés. D6 a oublié ce fichier, l'audit 4-agents 24h a
flag.

Post-E3 : on garde UNIQUEMENT `color_for_score` (pure function,
float in → hex string out, vraies post-conditions). Les 4 autres
sont supprimés (path-based, fuzz `st.text()` = no-op).

Voir `docs/FORGE_REGEN_HANDBOOK.md` pour la procédure obligatoire
après chaque `forge --gen-props engine/core/forge_metrics.py`.

Tests gardés : 4 (color_for_score format + thresholds).
Tests supprimés : 4 (get_repo_risk, get_file_risk_map,
                    forge_score_for_path, forge_color_for_path
                    — toutes path-based).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings
from engine.core.forge_metrics import color_for_score


@pytest.fixture(autouse=True)
def _forge_isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@given(score=st.floats(allow_nan=False, allow_infinity=False))
@settings(max_examples=50, deadline=None)
def test_color_for_score_returns_hex_string(score: float):
    """color_for_score always returns a 7-char hex string '#RRGGBB'."""
    result = color_for_score(score)
    assert isinstance(result, str)
    assert len(result) == 7
    assert result.startswith("#")
    # All 6 trailing chars must be valid hex
    assert all(c in "0123456789abcdefABCDEF" for c in result[1:]), (
        f"non-hex in {result!r}"
    )


def test_color_for_score_red_threshold():
    """score >= 0.70 → bright red (#d62728)."""
    assert color_for_score(0.70) == "#d62728"
    assert color_for_score(0.85) == "#d62728"
    assert color_for_score(1.0) == "#d62728"


def test_color_for_score_orange_threshold():
    """0.40 ≤ score < 0.70 → orange (#ff7f0e)."""
    assert color_for_score(0.40) == "#ff7f0e"
    assert color_for_score(0.55) == "#ff7f0e"
    assert color_for_score(0.69) == "#ff7f0e"


def test_color_for_score_yellow_and_green():
    """0.20 ≤ score < 0.40 → yellow ; score < 0.20 → green."""
    assert color_for_score(0.20) == "#bcbd22"
    assert color_for_score(0.39) == "#bcbd22"
    assert color_for_score(0.19) == "#2ca02c"
    assert color_for_score(0.0) == "#2ca02c"
    assert color_for_score(-1.0) == "#2ca02c"
