"""CHUNK C10 (2026-05-19) — DetailPanel enrichi (SHA / NCD / gaps / unknowns).

Pre-fix : ReconstructionResult exposait juste sha256/ncd/exact_match.
Aucune trace des lignes que la reco n'a pas pu ancrer ni des
identifiants qu'elle a inventés. Côté UI le DetailPanel n'avait
aucun champ reco-spécifique.

Fix :
  - cube_providers.ReconstructionResult gagne :
      gap_lines: list[int]
      unknown_identifiers: list[str]
  - reconstruct_cube les calcule depuis anchor_map + ast_hints.
  - Neuron gagne gap_lines, unknown_idents (UI state).
  - DetailPanel.show_neuron lit ces champs et les affiche quand
    le neuron est un cube de reco (level == 'cube').
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_reconstruction_result_has_gap_lines_field():
    """ReconstructionResult dataclass exposes gap_lines: list[int]."""
    from cube_providers import ReconstructionResult
    r = ReconstructionResult(
        cube_id="x", original_sha256="a", reconstruction="",
        reconstruction_sha256="b", exact_match=False,
        ncd_score=0.5, perplexity=0.0, success=False,
    )
    assert hasattr(r, "gap_lines")
    assert isinstance(r.gap_lines, list)
    assert r.gap_lines == []


def test_reconstruction_result_has_unknown_identifiers_field():
    """ReconstructionResult dataclass exposes unknown_identifiers: list[str]."""
    from cube_providers import ReconstructionResult
    r = ReconstructionResult(
        cube_id="x", original_sha256="a", reconstruction="",
        reconstruction_sha256="b", exact_match=False,
        ncd_score=0.5, perplexity=0.0, success=False,
    )
    assert hasattr(r, "unknown_identifiers")
    assert isinstance(r.unknown_identifiers, list)
    assert r.unknown_identifiers == []


def test_extract_gap_lines_helper_exists():
    """cube_providers exposes module-level _extract_gap_lines."""
    import cube_providers
    assert hasattr(cube_providers, "_extract_gap_lines")


def test_extract_gap_lines_inverse_of_anchors():
    """_extract_gap_lines returns lines NOT covered by the anchor map."""
    from cube_providers import _extract_gap_lines
    anchor_map = {0: "def foo():", 2: "    return 1"}
    n_lines = 5
    gaps = _extract_gap_lines(anchor_map, n_lines)
    assert sorted(gaps) == [1, 3, 4]


def test_extract_unknown_identifiers_helper_exists():
    """cube_providers exposes module-level _extract_unknown_identifiers."""
    import cube_providers
    assert hasattr(cube_providers, "_extract_unknown_identifiers")


def test_extract_unknown_identifiers_diff_against_hints():
    """Returns identifiers in reconstruction that are NOT in ast_hints['identifiers']."""
    from cube_providers import _extract_unknown_identifiers
    reconstruction = "def foo(x):\n    return helper(x) + magic_value"
    ast_hints = {"identifiers": ["foo", "x", "helper"]}
    unknowns = _extract_unknown_identifiers(reconstruction, ast_hints)
    # 'magic_value' is in the reco but not in hints → unknown
    assert "magic_value" in unknowns
    # 'foo', 'x', 'helper' are in hints → not unknown
    assert "foo" not in unknowns
    assert "helper" not in unknowns


def test_extract_unknown_identifiers_handles_no_hints():
    """When ast_hints is None or missing 'identifiers', returns []."""
    from cube_providers import _extract_unknown_identifiers
    assert _extract_unknown_identifiers("def foo(): pass", None) == []
    assert _extract_unknown_identifiers("def foo(): pass", {}) == []


def test_neuron_has_gap_lines_and_unknown_idents(qtbot):
    """Neuron dataclass carries reco-side fields (default empty)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import Neuron
    n = Neuron(id="cube_0", label="L1-5")
    assert hasattr(n, "gap_lines")
    assert hasattr(n, "unknown_idents")
    assert n.gap_lines == []
    assert n.unknown_idents == []


def test_detail_panel_shows_reco_fields_for_cube_neuron(qtbot):
    """DetailPanel.show_neuron renders sha/ncd/gaps/unknowns when level=='cube'."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.detail_panel import DetailPanel
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_neuron({
        "label": "L1-5",
        "id": "cube_0",
        "level": "cube",
        "status": "done",
        "sha_match": True,
        "ncd": 0.0,
        "gap_lines": [],
        "unknown_idents": [],
    })
    assert hasattr(panel, "_sha_label")
    assert hasattr(panel, "_ncd_label")
    assert hasattr(panel, "_gaps_label")
    assert hasattr(panel, "_unknowns_label")
    # Qt isVisible() is False until parent is shown — use isHidden() inverse
    assert not panel._sha_label.isHidden()
    assert not panel._ncd_label.isHidden()


def test_detail_panel_hides_reco_fields_for_non_cube(qtbot):
    """DetailPanel hides reco fields when neuron level != 'cube'."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.detail_panel import DetailPanel
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_neuron({
        "label": "module:foo",
        "id": "module:foo",
        "level": "F",          # not a cube
        "status": "done",
    })
    assert panel._sha_label.isHidden()
    assert panel._ncd_label.isHidden()
    assert panel._gaps_label.isHidden()
    assert panel._unknowns_label.isHidden()


def test_detail_panel_renders_gap_lines_count(qtbot):
    """When gap_lines is non-empty, the label shows the count."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.detail_panel import DetailPanel
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show_neuron({
        "label": "L1-5", "id": "cube_0", "level": "cube",
        "status": "wip", "sha_match": False, "ncd": 0.42,
        "gap_lines": [1, 3, 7],
        "unknown_idents": ["magic", "foobar"],
    })
    txt = panel._gaps_label.text()
    assert "3" in txt
    txt_u = panel._unknowns_label.text()
    assert "2" in txt_u or "magic" in txt_u


# CHUNK D1 (2026-05-19 remediation) — regression tests for the
# `_build_full_anchor_map` 3-arg-call bug (TypeError swallowed by
# broad except → gap_lines always []). Pre-fix : these tests FAIL
# because reconstruct_cube returns gap_lines = [] regardless of input.

def test_d1_gap_lines_populated_when_ast_hints_provided():
    """D1 regression : gap_lines must NOT be silently empty when the
    cube has a real ast_hints dict + non-trivial unanchored lines.

    Pre-fix : `_build_full_anchor_map(ast_hints, lines, n_lines)` was
    called with 3 args instead of 4 → TypeError swallowed by broad
    except → gap_lines = [] always. This test forces the fix to wire
    the 4-arg call so unanchored unique code lines appear in gaps.
    """
    from cube_providers import reconstruct_cube, MockLLMProvider
    from cube import Cube
    # Use 5 lines of UNIQUE non-trivial code (no blanks, no '}', no defer,
    # no struct tags) so full_anchor_map's heuristics CAN'T anchor them
    # — only the explicit first_line hint will.
    c = Cube(
        id='t',
        content='alpha = compute_unique_x()\n'
                'beta = compute_unique_y()\n'
                'gamma = combine(alpha, beta)\n'
                'delta = transform(gamma)\n'
                'epsilon = finalize(delta)',
        sha256='x', file_origin='t.py', line_start=1, line_end=5,
    )
    r = reconstruct_cube(
        c, [], MockLLMProvider(),
        ast_hints={'first_line': 'alpha = compute_unique_x()',
                   'identifiers': ['alpha', 'beta']},
    )
    # first_line anchors idx 0 → must NOT be in gaps.
    assert 0 not in r.gap_lines, (
        f"line 0 was anchored by first_line, must not be a gap. "
        f"Got gap_lines={r.gap_lines}."
    )
    # For 4 remaining UNIQUE code lines, AT LEAST 2 must appear as gaps
    # — the full_anchor_map heuristics catch blanks/braces/defer, not
    # arbitrary code lines. If gap_lines is empty here, the TypeError
    # swallow is still active.
    assert len(r.gap_lines) >= 2, (
        f"expected ≥2 gap_lines for 4 unanchored unique code lines, "
        f"got {r.gap_lines}. The _build_full_anchor_map call is "
        f"probably still failing silently (D1 not applied)."
    )


def test_d1_gap_lines_full_anchor_map_catches_closing_brace():
    """Bonus B regression : full anchor map (4-arg with ext) must mark
    closing braces as anchored AND keep arbitrary code lines unanchored.

    Pre-fix : gap_lines = [] always → '}' is trivially "not in []" so a
    weaker test would pass. We require both that '}' is anchored AND
    that a unique non-trivial code line IS in gaps, proving the full
    anchor map ran (not the silent empty fallback).
    """
    from cube_providers import reconstruct_cube, MockLLMProvider
    from cube import Cube
    c = Cube(
        id='t',
        content='func F() {\n'                       # idx 0 : anchored (first_line)
                '    x := unique_value_123\n'         # idx 1 : unique code line, should be gap
                '    y := another_unique_456\n'       # idx 2 : unique code line, should be gap
                '}',                                  # idx 3 : '}', anchored by Fix 6
        sha256='x', file_origin='t.go', line_start=1, line_end=4,
    )
    r = reconstruct_cube(
        c, [], MockLLMProvider(),
        ast_hints={'first_line': 'func F() {'},
    )
    # Line idx 3 = '}' — full_anchor_map Fix 6 must anchor it.
    assert 3 not in r.gap_lines, (
        f"closing brace '}}' at line idx 3 must be anchored. "
        f"Got gap_lines={r.gap_lines}."
    )
    # Lines idx 1 and 2 are unique code — must be gaps. If gap_lines
    # is empty, the full_anchor_map ran but produced no anchor distinction
    # (i.e. it's silently failing).
    assert 1 in r.gap_lines or 2 in r.gap_lines, (
        f"expected at least one of [1, 2] in gaps (unique code lines), "
        f"got {r.gap_lines}. Full anchor map not running properly."
    )


def test_d1_gap_lines_no_typeerror_on_missing_file_origin():
    """D1 edge case : Cube with empty file_origin must not crash the
    extraction. Earlier hotfix would also have raised TypeError if
    cube.file_origin was missing."""
    from cube_providers import reconstruct_cube, MockLLMProvider
    from cube import Cube
    c = Cube(
        id='t', content='line1\nline2',
        sha256='x', file_origin='', line_start=1, line_end=2,
    )
    # Must not crash, must not raise
    r = reconstruct_cube(c, [], MockLLMProvider(), ast_hints={})
    assert isinstance(r.gap_lines, list)
    assert isinstance(r.unknown_identifiers, list)
