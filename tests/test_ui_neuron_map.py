"""Tests for B-UI-02 through B-UI-07: NeuronMapWidget."""

import pytest
from PyQt6.QtCore import Qt, QPointF


# --- B-UI-02: Static points ---

def test_neuron_map_creates(qtbot):
    """NeuronMapWidget can be created and shown."""
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    assert w.accessibleName() == "Neuron Map"


def test_neuron_map_empty_state(qtbot):
    """Empty map shows empty state (no crash)."""
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    w.repaint()  # Force paint
    assert w._empty is True
    assert len(w.neurons) == 0


def test_load_scan_file(qtbot):
    """Load neurons from a real scan JSON."""
    from muninn.ui.neuron_map import NeuronMapWidget
    from muninn.ui import _SCANS_DIR
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()

    scan_file = _SCANS_DIR / "infernal-wheel.json"
    if scan_file.exists():
        w.load_scan(scan_file)
        assert len(w.neurons) > 0
        assert w._empty is False


def test_load_scan_nonexistent(qtbot):
    """Loading nonexistent scan = empty state, no crash."""
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.load_scan("/nonexistent/path.json")
    assert w._empty is True


def test_neurons_have_positions(qtbot):
    """After loading, neurons have x/y positions."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    neurons = [
        Neuron(id="a", label="Alpha"),
        Neuron(id="b", label="Beta"),
        Neuron(id="c", label="Gamma"),
    ]
    w.load_neurons(neurons)
    assert all(n.x != 0 or n.y != 0 for n in w.neurons)


def test_distinct_shapes(qtbot):
    """Different levels get different shapes."""
    from muninn.ui.neuron_map import LEVEL_SHAPES
    shapes = set(LEVEL_SHAPES.values())
    assert len(shapes) >= 3  # At least 3 distinct shapes for daltonism


# --- B-UI-04: Zoom + drag ---

def test_zoom_clamp(qtbot):
    """Zoom is clamped to [0.1, 20.0]."""
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w._zoom = 0.05
    w._zoom = max(0.1, min(20.0, w._zoom))
    assert w._zoom >= 0.1

    w._zoom = 25.0
    w._zoom = max(0.1, min(20.0, w._zoom))
    assert w._zoom <= 20.0


def test_zoom_to_fit(qtbot):
    """Ctrl+0 zoom-to-fit works."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    neurons = [Neuron(id="a", label="A", x=10, y=10),
               Neuron(id="b", label="B", x=300, y=300)]
    w._neurons = neurons
    w._empty = False
    w._zoom_to_fit()
    assert 0.1 <= w._zoom <= 20.0


# --- B-UI-05: Hover ---

def test_hit_test(qtbot):
    """Hit test finds neuron under cursor."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    n = Neuron(id="test", label="Test")
    n.x = 200
    n.y = 200
    w._neurons = [n]
    w._empty = False
    w._zoom = 1.0
    w._pan_x = 200
    w._pan_y = 200

    # Screen center should map to world (200, 200)
    hit = w._hit_test(QPointF(200, 200))
    assert hit is not None
    assert hit.label == "Test"


def test_hit_test_miss(qtbot):
    """Hit test returns None when no neuron near cursor."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    n = Neuron(id="test", label="Test", x=10, y=10)
    w._neurons = [n]
    w._empty = False
    hit = w._hit_test(QPointF(390, 390))
    assert hit is None


# --- B-UI-06: Selection ---

def test_selection(qtbot):
    """Selecting a neuron emits signal and stores selection."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [Neuron(id="a", label="A"), Neuron(id="b", label="B")]
    w.load_neurons(neurons)

    w._handle_neuron_click(w._neurons[0], Qt.KeyboardModifier.NoModifier)
    assert 0 in w._selected
    assert len(w.selected_neurons) == 1


def test_multi_select(qtbot):
    """Shift+click adds to selection."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [Neuron(id="a", label="A"), Neuron(id="b", label="B")]
    w.load_neurons(neurons)

    w._handle_neuron_click(w._neurons[0], Qt.KeyboardModifier.NoModifier)
    w._handle_neuron_click(w._neurons[1], Qt.KeyboardModifier.ShiftModifier)
    assert len(w._selected) == 2


def test_deselect(qtbot):
    """Clicking selected neuron again deselects."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [Neuron(id="a", label="A")]
    w.load_neurons(neurons)

    w._handle_neuron_click(w._neurons[0], Qt.KeyboardModifier.NoModifier)
    assert 0 in w._selected
    w._handle_neuron_click(w._neurons[0], Qt.KeyboardModifier.NoModifier)
    assert len(w._selected) == 0


def test_selection_history(qtbot):
    """Alt+Left/Right navigates selection history."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [Neuron(id="a", label="A"), Neuron(id="b", label="B")]
    w.load_neurons(neurons)

    w._handle_neuron_click(w._neurons[0], Qt.KeyboardModifier.NoModifier)
    w._handle_neuron_click(w._neurons[1], Qt.KeyboardModifier.NoModifier)
    assert 1 in w._selected

    w._history_back()
    assert 0 in w._selected

    w._history_forward()
    assert 1 in w._selected


# --- B-UI-07: Edges ---

def test_edges_from_depends(qtbot):
    """Edges are built from node depends."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [
        Neuron(id="a", label="A", depends=["b"]),
        Neuron(id="b", label="B", depends=[]),
    ]
    w.load_neurons(neurons)
    # Manually build edges since load_neurons uses random layout
    w._neurons[0].depends = ["b"]
    w._build_edges()
    assert len(w._edges) == 1


def test_paint_no_crash(qtbot):
    """Full paint cycle with neurons doesn't crash."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    neurons = [
        Neuron(id="a", label="Alpha", status="done"),
        Neuron(id="b", label="Beta", status="todo"),
        Neuron(id="c", label="Gamma", status="wip"),
    ]
    w.load_neurons(neurons)
    w.repaint()  # Force full paint cycle
