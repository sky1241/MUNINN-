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
