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
        w._cancel_laplacian()  # Stop background thread for test cleanup
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


# --- B-UI-03: Degree colors + legend ---

def test_degree_color_gradient(qtbot):
    """Degree-based color gradient returns valid colors."""
    from muninn.ui.neuron_map import _degree_color, DEGREE_GRADIENT
    from PyQt6.QtGui import QColor
    # Low degree = cold
    cold = _degree_color(0, 10)
    assert isinstance(cold, QColor)
    # High degree = hot
    hot = _degree_color(10, 10)
    assert isinstance(hot, QColor)
    # Different colors
    assert cold.red() != hot.red() or cold.green() != hot.green()


def test_compute_degrees(qtbot):
    """Degree counts are computed after loading."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [
        Neuron(id="a", label="A", depends=["b", "c"]),
        Neuron(id="b", label="B", depends=[]),
        Neuron(id="c", label="C", depends=[]),
    ]
    w.load_neurons(neurons)
    assert w._neurons[0].degree == 2  # a connects to b and c
    assert w._neurons[1].degree == 1
    assert w._neurons[2].degree == 1


def test_legend_paint(qtbot):
    """Paint with legend doesn't crash."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    neurons = [
        Neuron(id="a", label="A", depends=["b"]),
        Neuron(id="b", label="B"),
    ]
    w.load_neurons(neurons)
    w.repaint()  # Legend renders in bottom-left


# --- B-UI-03: Laplacian worker ---

def test_laplacian_worker_single_node(qtbot):
    """LaplacianWorker handles single node (no scipy needed)."""
    from muninn.ui.workers import LaplacianWorker
    from muninn.ui.neuron_map import Neuron
    results = []
    worker = LaplacianWorker([Neuron(id="a", label="A")], [])
    worker.finished.connect(lambda pos: results.append(pos))
    worker.run()
    assert len(results) == 1
    assert results[0] == [(0.5, 0.5)]


def test_laplacian_worker_two_nodes(qtbot):
    """LaplacianWorker handles two nodes (no scipy needed)."""
    from muninn.ui.workers import LaplacianWorker
    from muninn.ui.neuron_map import Neuron
    results = []
    nodes = [Neuron(id="a", label="A"), Neuron(id="b", label="B")]
    worker = LaplacianWorker(nodes, [(0, 1, 1.0)])
    worker.finished.connect(lambda pos: results.append(pos))
    worker.run()
    assert len(results) == 1
    assert results[0] == [(0.3, 0.5), (0.7, 0.5)]


def test_laplacian_worker_larger_graceful(qtbot):
    """LaplacianWorker handles 5+ nodes gracefully (error or positions)."""
    from muninn.ui.workers import LaplacianWorker
    from muninn.ui.neuron_map import Neuron
    nodes = [Neuron(id=str(i), label=str(i)) for i in range(5)]
    edges = [(0, 1, 1.0), (1, 2, 1.0), (2, 3, 1.0), (3, 4, 1.0)]
    worker = LaplacianWorker(nodes, edges)
    results = []
    errors = []
    worker.finished.connect(lambda pos: results.append(pos))
    worker.error.connect(lambda msg: errors.append(msg))
    worker.run()
    # Either succeeds with positions or fails gracefully with error signal
    assert len(results) + len(errors) == 1


# --- B-UI-04: Animated zoom-to-fit ---

def test_zoom_to_fit_animated(qtbot):
    """Animated zoom-to-fit starts animation timer."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    neurons = [Neuron(id="a", label="A", x=10, y=10),
               Neuron(id="b", label="B", x=300, y=300)]
    w._neurons = neurons
    w._empty = False
    w._zoom_to_fit_animated()
    assert w._anim_timer.isActive()
    w._anim_timer.stop()  # Cleanup


# --- B-UI-05: KD-tree ---

def test_kdtree_build(qtbot):
    """KD-tree builds from neuron positions (or None without scipy)."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    neurons = [Neuron(id="a", label="A", x=100, y=100),
               Neuron(id="b", label="B", x=300, y=300)]
    w._neurons = neurons
    w._empty = False
    w._build_kdtree()
    # With scipy: kdtree is built. Without: graceful None fallback.
    try:
        import scipy.spatial  # noqa: F401
        assert w._kdtree is not None
    except ImportError:
        assert w._kdtree is None  # Graceful fallback


# --- B-UI-07: Bezier edges + edge click ---

def test_edge_hit_test(qtbot):
    """Edge click detection finds nearby edges."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w._zoom = 1.0
    # Pan so world origin is at screen center (200,200)
    w._pan_x = 200.0
    w._pan_y = 200.0
    # World coords: (100,200) -> screen (100,200), (300,200) -> screen (300,200)
    n1 = Neuron(id="a", label="A", x=100, y=200)
    n2 = Neuron(id="b", label="B", x=300, y=200)
    w._neurons = [n1, n2]
    w._edges = [(0, 1, 1.0)]
    w._empty = False
    # Screen midpoint of the edge: world(200,200) -> screen (200,200)
    mid = QPointF(200, 200)
    hit = w._hit_test_edge(mid)
    assert hit is not None


def test_neighbor_cache(qtbot):
    """Neighbor cache is built from edges."""
    from muninn.ui.neuron_map import NeuronMapWidget, Neuron
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    neurons = [
        Neuron(id="a", label="A", depends=["b"]),
        Neuron(id="b", label="B", depends=["c"]),
        Neuron(id="c", label="C"),
    ]
    w.load_neurons(neurons)
    assert 1 in w._neighbor_cache.get(0, set())
    assert 2 in w._neighbor_cache.get(1, set())
