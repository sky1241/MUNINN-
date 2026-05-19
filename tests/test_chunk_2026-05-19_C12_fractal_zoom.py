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
