"""CHUNK C12 (2026-05-19) — Fractal x1/x2/x3 zoom visual.

Pre-fix: NeuronMapWidget always paints one neuron per cube. No way to
zoom out to a coarser fractal view (x2 = 2 cubes per molecule, x3 = 3).

Fix:
  - Add `self._zoom_level: int = 1` to NeuronMapWidget.
  - set_zoom_level(level: int) — accepts 1/2/3, invalid ignored,
    triggers repaint via _displayed_neurons() switch.
  - Module-level `_aggregate_neurons_to_level(neurons, level)` :
    pure function, groups consecutive neurons by `level` and produces
    a smaller list whose `temperature` is the token-weighted average
    NCD and `degree` is the max degree of the group.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_zoom_level_field_default_is_1(qtbot):
    """Fresh NeuronMapWidget defaults to zoom level 1."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    assert hasattr(w, "_zoom_level")
    assert w._zoom_level == 1


def test_set_zoom_level_accepts_2_and_3(qtbot):
    """set_zoom_level(2) and (3) are accepted."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.set_zoom_level(2)
    assert w._zoom_level == 2
    w.set_zoom_level(3)
    assert w._zoom_level == 3
    w.set_zoom_level(1)
    assert w._zoom_level == 1


def test_set_zoom_level_invalid_ignored(qtbot):
    """Levels outside {1, 2, 3} are silently ignored."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.set_zoom_level(4)
    assert w._zoom_level == 1
    w.set_zoom_level(0)
    assert w._zoom_level == 1
    w.set_zoom_level(-1)
    assert w._zoom_level == 1
    w.set_zoom_level("two")  # type: ignore[arg-type]
    assert w._zoom_level == 1


def test_aggregate_helper_exists():
    """neuron_map exposes module-level _aggregate_neurons_to_level."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import neuron_map
    assert hasattr(neuron_map, "_aggregate_neurons_to_level")


def test_aggregate_level_1_returns_input_unchanged():
    """level=1 is identity — same list, no aggregation."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level, Neuron
    src = [
        Neuron(id=f"cube_{i}", label=f"L{i}", level="cube",
               temperature=0.1 * i, degree=i)
        for i in range(5)
    ]
    out = _aggregate_neurons_to_level(src, 1)
    assert out == src


def test_aggregate_x2_halves_count():
    """level=2 → groups of 2 → ceil(N/2) molecules."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level, Neuron
    src = [
        Neuron(id=f"cube_{i}", label=f"L{i}", level="cube",
               temperature=0.0, degree=0)
        for i in range(6)
    ]
    out = _aggregate_neurons_to_level(src, 2)
    assert len(out) == 3
    # All molecules should keep level="cube"
    for m in out:
        assert m.level == "cube"


def test_aggregate_x3_ceils_count():
    """level=3 with N=7 → ceil(7/3) = 3 molecules."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level, Neuron
    src = [
        Neuron(id=f"cube_{i}", label=f"L{i}", level="cube",
               temperature=0.0, degree=0)
        for i in range(7)
    ]
    out = _aggregate_neurons_to_level(src, 3)
    assert len(out) == 3


def test_aggregate_x2_averages_ncd_weighted_by_tokens():
    """Molecule temperature = sum(tk_i * ncd_i) / sum(tk_i) over its members.

    Each Neuron carries `temperature` (NCD 0..1). For aggregation we
    use the cube's effective weight = `degree` or `1` if degree=0
    (legacy + safety for first paint when degree is still 0)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level, Neuron
    src = [
        Neuron(id="cube_0", label="L1", level="cube",
               temperature=0.2, degree=1),
        Neuron(id="cube_1", label="L2", level="cube",
               temperature=0.8, degree=3),
    ]
    out = _aggregate_neurons_to_level(src, 2)
    assert len(out) == 1
    expected = (0.2 * 1 + 0.8 * 3) / (1 + 3)  # = 0.65
    assert abs(out[0].temperature - expected) < 1e-9


def test_aggregate_x2_keeps_max_degree():
    """Molecule degree = max(degree_i) over its members (worst NCD wins)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level, Neuron
    src = [
        Neuron(id="cube_0", label="L1", level="cube",
               temperature=0.0, degree=2),
        Neuron(id="cube_1", label="L2", level="cube",
               temperature=0.0, degree=7),
    ]
    out = _aggregate_neurons_to_level(src, 2)
    assert out[0].degree == 7


def test_aggregate_empty_list():
    """Empty input → empty output for all levels."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import _aggregate_neurons_to_level
    assert _aggregate_neurons_to_level([], 1) == []
    assert _aggregate_neurons_to_level([], 2) == []
    assert _aggregate_neurons_to_level([], 3) == []


def test_displayed_neurons_switches_on_zoom(qtbot):
    """NeuronMapWidget._displayed_neurons() returns aggregated list when
    zoom > 1, original when zoom == 1."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [
        Neuron(id=f"cube_{i}", label=f"L{i}", level="cube",
               temperature=0.0, degree=0)
        for i in range(6)
    ]
    assert hasattr(w, "_displayed_neurons")
    assert len(w._displayed_neurons()) == 6  # x1 = identity
    w.set_zoom_level(2)
    assert len(w._displayed_neurons()) == 3
    w.set_zoom_level(3)
    assert len(w._displayed_neurons()) == 2


# CHUNK D5 (2026-05-19 remediation, Q1 B acté) — hover/click at zoom>1
# must operate on molecules, not silently land on whichever original is
# nearest to the centroid. Click on a molecule selects ALL its
# constituent cubes (group selection).

def test_d5_aggregate_with_groups_returns_mapping():
    """D5 : new helper _aggregate_neurons_with_groups returns (molecules, groups)
    where groups[i] = list of orig_idx aggregated in molecule i."""
    from muninn.ui.neuron_map import _aggregate_neurons_with_groups, Neuron
    src = [Neuron(id=f"c{i}", label=f"L{i}", level="cube") for i in range(5)]
    molecules, groups = _aggregate_neurons_with_groups(src, 2)
    assert len(molecules) == 3  # ceil(5/2)
    assert groups == [[0, 1], [2, 3], [4]]


def test_d5_aggregate_with_groups_level_1_identity():
    """level=1 returns groups = [[0], [1], ...]."""
    from muninn.ui.neuron_map import _aggregate_neurons_with_groups, Neuron
    src = [Neuron(id=f"c{i}", label=f"L{i}", level="cube") for i in range(3)]
    molecules, groups = _aggregate_neurons_with_groups(src, 1)
    assert molecules == src
    assert groups == [[0], [1], [2]]


def test_d5_aggregate_with_groups_empty():
    """Empty input → empty molecules + empty groups."""
    from muninn.ui.neuron_map import _aggregate_neurons_with_groups
    molecules, groups = _aggregate_neurons_with_groups([], 2)
    assert molecules == []
    assert groups == []


def test_d5_displayed_groups_filled_after_set_zoom_level(qtbot):
    """`_displayed_groups` mirrors `_displayed_neurons` mapping."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f"c{i}", label=f"L{i}", level="cube")
                  for i in range(6)]
    # zoom=1
    _ = w._displayed_neurons()
    assert w._displayed_groups == [[0], [1], [2], [3], [4], [5]]
    # zoom=2
    w.set_zoom_level(2)
    _ = w._displayed_neurons()
    assert w._displayed_groups == [[0, 1], [2, 3], [4, 5]]
    # zoom=3
    w.set_zoom_level(3)
    _ = w._displayed_neurons()
    assert w._displayed_groups == [[0, 1, 2], [3, 4, 5]]


def test_d5_click_at_zoom_2_selects_whole_group(qtbot):
    """Q1 B regression : click on a molecule at zoom=2 selects all
    originals of that group (not just one)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    from PyQt6.QtCore import Qt
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f"c{i}", label=f"L{i}", level="cube", x=i, y=0, z=0)
                  for i in range(6)]
    w.set_zoom_level(2)
    displayed = w._displayed_neurons()
    # Click on molecule idx 1 (group = [2, 3])
    molecule_1 = displayed[1]
    w._handle_neuron_click(molecule_1, Qt.KeyboardModifier.NoModifier)
    assert w._selected == {2, 3}, f"expected {{2, 3}}, got {w._selected}"


def test_d5_click_at_zoom_1_unchanged(qtbot):
    """D5 must NOT regress zoom=1 click behavior (single-cube selection)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    from PyQt6.QtCore import Qt
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f"c{i}", label=f"L{i}", level="cube")
                  for i in range(4)]
    # zoom=1 default, click on cube 2
    _ = w._displayed_neurons()  # ensure _displayed_groups populated
    w._handle_neuron_click(w._neurons[2], Qt.KeyboardModifier.NoModifier)
    assert w._selected == {2}


def test_d5_resolve_clicked_originals_molecule(qtbot):
    """D5 helper : _resolve_clicked_originals(molecule) returns its group."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._neurons = [Neuron(id=f"c{i}", label=f"L{i}", level="cube")
                  for i in range(5)]
    w.set_zoom_level(2)
    displayed = w._displayed_neurons()
    # displayed[0] is molecule aggregating originals [0, 1]
    result = w._resolve_clicked_originals(displayed[0])
    assert result == [0, 1]
    # displayed[2] is molecule with single original [4]
    result = w._resolve_clicked_originals(displayed[2])
    assert result == [4]
