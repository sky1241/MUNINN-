"""CHUNK C7 (2026-05-19) — `subdivide_file` mycelium-aware.

THE archi fix Sky a demandé depuis le départ : le scan définit la
structure, la reco s'aligne dessus. Pre-fix, subdivide_file ignorait
totalement le mycelium et coupait en tranches de ~112 tokens uniformes
— peu importe que ça coupe au milieu d'une fonction.

Fix:
  - `concept_to_file_lines(content, mycelium)` (mycelium.py) :
    {line_idx: set[concept]} pour chaque ligne.
  - `find_concept_boundaries(content, mycelium, target_tokens)` (cube.py):
    retourne line numbers où la zone thématique change (Jaccard
    inter-lignes < threshold) OU où le cumul de tokens dépasse le
    plafond.
  - `subdivide_file(..., mycelium=None)`: si mycelium fourni ET
    `_SCAN_AWARE_SUBDIVIDE_ENABLED=1`, utilise zone-based découpage.
    Sinon fallback token-uniform legacy.

Décision Sky 2026-05-19: PURE zone-based. target_tokens devient un
plafond, pas une cible. Cubes hétérogènes acceptés.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_scan_aware_subdivide_flag_default_enabled():
    """Default (no env) → _SCAN_AWARE_SUBDIVIDE_ENABLED is True."""
    import cube
    assert hasattr(cube, "_SCAN_AWARE_SUBDIVIDE_ENABLED")
    import os
    if os.environ.get("MUNINN_SCAN_AWARE_SUBDIVIDE", "1") != "0":
        assert cube._SCAN_AWARE_SUBDIVIDE_ENABLED is True


def test_concept_to_file_lines_helper_exists():
    """Mycelium exposes `concept_to_file_lines(content, mycelium)`."""
    import mycelium
    assert hasattr(mycelium, "concept_to_file_lines")


def test_concept_to_file_lines_returns_per_line_set(tmp_path):
    """Returns dict[line_idx, set[concept]] — each line gets concepts."""
    import mycelium

    class FakeMycelium:
        def __init__(self, vocab):
            self._vocab = vocab
        def has_concept(self, c):
            return c.lower() in self._vocab

    mm = FakeMycelium({"foo", "bar", "baz"})
    content = "foo and bar\nbaz alone\nnothing here\n"
    result = mycelium.concept_to_file_lines(content, mm)
    assert isinstance(result, dict)
    assert result[0] == {"foo", "bar"}
    assert result[1] == {"baz"}
    assert result[2] == set()


def test_find_concept_boundaries_helper_exists():
    """cube.py exposes `find_concept_boundaries(content, mycelium, target)`."""
    import cube
    assert hasattr(cube, "find_concept_boundaries")


def test_find_concept_boundaries_empty_when_no_mycelium_signal(monkeypatch):
    """If mycelium signal is too weak (no concepts), return [] (fallback).

    CHUNK E7 (REMEDIATION-2) durcissement : pré-E7 le test acceptait
    `[] or [len(content.split("\\n"))]` — 2 valeurs très différentes,
    tautologie. Post-E7 : signal vide → contract est EXACTEMENT [].
    """
    import cube

    # Stub concept_to_file_lines pour signal vide (0 line_concepts).
    monkeypatch.setattr(
        cube, "concept_to_file_lines" if hasattr(cube, "concept_to_file_lines") else "_unused",
        lambda content, mycelium: {},
        raising=False,
    )

    class FakeMycelium:
        def has_concept(self, c):
            return False

    content = "line1\nline2\nline3\nline4\nline5\n"
    result = cube.find_concept_boundaries(content, FakeMycelium(), target_tokens=112)
    # Signal-strength gate : <30% lines with concepts → return []
    assert result == [], (
        f"empty mycelium signal must return [] (fallback), got: {result!r}"
    )


def test_find_concept_boundaries_detects_zone_transition(monkeypatch):
    """find_concept_boundaries doit retourner ≥1 boundary entre 2 zones
    sémantiques disjointes (E7 durcissement : remplace `if result:`
    tautologie par vraie assertion non-conditionnelle)."""
    import cube

    # Inject controlled line_concepts via monkeypatch sur
    # `concept_to_file_lines` (utilisé par find_concept_boundaries).
    # Lignes 0-5 zone "alpha" / lignes 6-11 zone "beta" — disjoint
    # → Jaccard(line_5_concepts, line_6_concepts) = 0.0 < 0.20 → boundary.
    line_concepts = {
        i: {"alpha", "shared_a"} for i in range(6)
    }
    line_concepts.update({
        i: {"beta", "shared_b"} for i in range(6, 12)
    })

    def stub_concept_to_file_lines(content, mycelium):
        return line_concepts

    # CHUNK F5 (REMEDIATION-3) — patch UNIQUEMENT `mycelium.concept_to_file_lines`.
    # `find_concept_boundaries` fait `from mycelium import concept_to_file_lines`
    # à l'intérieur de la fonction (cube.py:806-808), donc patcher `cube.*`
    # ne sert à rien (le nom n'existe pas au scope module de cube).
    # Pré-F5 le test avait un patch mort sur `cube.*` + un patch utile
    # sur `mycelium.*` ; on garde uniquement le second.
    import mycelium as _myc
    monkeypatch.setattr(_myc, "concept_to_file_lines",
                        stub_concept_to_file_lines, raising=False)

    class FakeMycelium:
        def has_concept(self, c):
            return c in {"alpha", "beta", "shared_a", "shared_b"}

    # Content avec 12 lignes (un par concept zone, identifiers triggables)
    content = "\n".join(f"line_{i}_token" for i in range(12)) + "\n"
    result = cube.find_concept_boundaries(content, FakeMycelium(), target_tokens=50)

    # Vraie post-condition : returns sorted list[int] non-vide
    assert isinstance(result, list)
    assert all(isinstance(x, int) for x in result)
    # PRINCIPALE : zone transition détectée
    assert len(result) >= 1, (
        f"expected ≥1 boundary at zone transition alpha→beta, got: {result!r}"
    )
    # Sorted strict
    assert result == sorted(result), f"boundaries must be sorted, got: {result!r}"
    # Chaque boundary doit être dans [1, n_lines]
    n_lines = len(content.split("\n"))
    assert all(0 < x <= n_lines for x in result), (
        f"boundaries out of range [1, {n_lines}] : {result!r}"
    )


def test_subdivide_file_accepts_mycelium_kwarg():
    """subdivide_file signature includes mycelium=None default."""
    import cube
    import inspect
    sig = inspect.signature(cube.subdivide_file)
    assert "mycelium" in sig.parameters
    assert sig.parameters["mycelium"].default is None


def test_subdivide_file_fallback_when_no_mycelium():
    """Without mycelium, behavior is identical to pre-C7 (token-uniform).

    Locks the §8.E backward-compat invariant: default mycelium=None
    preserves the legacy code path.
    """
    import cube
    content = "\n".join([f"line {i}" for i in range(200)])
    cubes_legacy = cube.subdivide_file("t.py", content, target_tokens=50)
    cubes_with_none = cube.subdivide_file(
        "t.py", content, target_tokens=50, mycelium=None,
    )
    # Same cube count and line ranges
    assert len(cubes_legacy) == len(cubes_with_none)
    for a, b in zip(cubes_legacy, cubes_with_none):
        assert a.line_start == b.line_start
        assert a.line_end == b.line_end


def test_subdivide_file_flag_off_keeps_legacy_even_with_mycelium(monkeypatch):
    """MUNINN_SCAN_AWARE_SUBDIVIDE=0 → mycelium arg ignored (§8.B)."""
    import cube
    monkeypatch.setattr(cube, "_SCAN_AWARE_SUBDIVIDE_ENABLED", False)

    class DummyMycelium:
        def has_concept(self, c):
            return True

    content = "\n".join([f"line {i}" for i in range(200)])
    cubes_with_flag_off = cube.subdivide_file(
        "t.py", content, target_tokens=50, mycelium=DummyMycelium(),
    )
    cubes_legacy = cube.subdivide_file("t.py", content, target_tokens=50)
    # Flag OFF → same as legacy
    assert len(cubes_with_flag_off) == len(cubes_legacy)
