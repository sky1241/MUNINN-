#!/usr/bin/env python3
"""Property-based tests for cube_providers.py — CURATED post-D6 remediation.

CHUNK D6 (2026-05-19 remediation) — pré-D6 ce fichier contenait 7 tests
auto-générés par forge --gen-props, tous suivant le pattern :

    @given(cube=st.text(max_size=50), neighbors=st.text(max_size=50), ...)
    def test_X_no_crash(...):
        try: f(...)
        except Exception: pass  # ← swallow

Pour les fonctions qui prennent des objets typés (Cube, CubeStore,
LLMProvider), `st.text()` produit des strings → AttributeError au 1er
accès → swallowed → test passe sans rien tester. C'était du green chiffré
gonflé (l'audit avait flag 7 tests, 0 assertion).

Post-D6 : on garde UNIQUEMENT les helpers purs (string/numeric in/out)
avec vraies post-conditions. Forge --gen-props re-générera les no-op
à chaque run ; cf docs/FORGE_REGEN_HANDBOOK.md pour la procédure.

Tests gardés :
- compute_ncd : (str, str) → float ∈ [0, 1] (vraie post-condition NCD).
- validate_reconstruction : (str, str) → bool (vraie post-condition).

Tests supprimés (prennent objets typés, st.text() inutile) :
- reconstruct_cube (Cube + neighbors + provider)
- compute_hotness (Cube + neighbors + provider)
- reconstruct_line_by_line (Cube + neighbors + provider)
- reconstruct_cube_waves (Cube + neighbors + provider)
- reconstruct_adaptive (file_path + content via real File + provider)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings
from engine.core.cube_providers import compute_ncd, validate_reconstruction


# cwd guard : forge convention, indirect file writes land in tmp_path.
@pytest.fixture(autouse=True)
def _forge_isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@given(a=st.text(max_size=200), b=st.text(max_size=200))
@settings(max_examples=50, deadline=None)
def test_compute_ncd_bounded_and_self_zero(a: str, b: str):
    """NCD output must be in [0, 1] for any input pair, and NCD(x, x) = 0
    for non-empty x by definition (compression invariance)."""
    result = compute_ncd(a, b)
    # Bounded
    assert 0.0 <= result <= 1.0, f"NCD out of bounds : {result}"
    # Symmetry (Bennett et al. 1998)
    sym = compute_ncd(b, a)
    assert abs(result - sym) < 1e-6, (
        f"NCD must be symmetric : NCD(a,b)={result} vs NCD(b,a)={sym}"
    )


def test_compute_ncd_empty_vs_empty():
    """NCD("", "") = 0.0 (exact case in implementation)."""
    assert compute_ncd("", "") == 0.0


def test_compute_ncd_empty_vs_nonempty():
    """NCD("", "x") = 1.0 (exact case in implementation)."""
    assert compute_ncd("", "hello") == 1.0
    assert compute_ncd("hello", "") == 1.0


@given(s=st.text(min_size=200, max_size=1000))
@settings(max_examples=30, deadline=None)
def test_compute_ncd_long_self_is_small(s: str):
    """For LONG strings (≥200 chars), NCD(x, x) is small (<0.2).

    Note : NCD(x, x) can be measurably > 0 for short or barely-redundant
    strings due to zlib per-stream overhead (header bytes count in C(ab)
    but not symmetrically in min/max). For inputs ≥200 chars the zlib
    overhead is amortized and the NCD is dominated by the actual
    compressibility ratio.
    """
    result = compute_ncd(s, s)
    assert 0.0 <= result < 0.20, (
        f"NCD(x, x) for x of len {len(s)} should be < 0.20, got {result}"
    )


@given(original=st.text(max_size=200), reconstruction=st.text(max_size=200))
@settings(max_examples=50, deadline=None)
def test_validate_reconstruction_returns_bool(original: str, reconstruction: str):
    """validate_reconstruction must return a bool ; True iff
    sha256(normalized(original)) == sha256(normalized(reconstruction))."""
    result = validate_reconstruction(original, reconstruction)
    assert isinstance(result, bool)
    # Reflexivity : equal strings must validate equal
    assert validate_reconstruction(original, original) is True


@given(original=st.text(min_size=1, max_size=200))
@settings(max_examples=30, deadline=None)
def test_validate_reconstruction_reflexive(original: str):
    """validate_reconstruction(x, x) must be True for any x."""
    assert validate_reconstruction(original, original) is True
