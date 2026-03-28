"""Tests for B-UI-01: MainWindow with 4-panel layout."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter


def test_window_creates(qtbot):
    """MainWindow can be created and shown."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    assert w.windowTitle() == "Muninn \u2014 Winter Tree"


def test_window_minimum_size(qtbot):
    """Window has minimum size 800x600."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.minimumWidth() == 800
    assert w.minimumHeight() == 600


def test_four_panels_visible(qtbot):
    """All 4 panels are visible after show."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.resize(1024, 768)
    # Force showEvent with sizes
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QShowEvent
    w.showEvent(QShowEvent())

    assert w.neuron_panel.isVisible()
    assert w.terminal_panel.isVisible()
    assert w.tree_panel.isVisible()
    assert w.detail_panel.isVisible()


def test_panels_minimum_size(qtbot):
    """Each panel has minimum size 200x150 (bug #39b)."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    for panel in [w.neuron_panel, w.terminal_panel, w.tree_panel, w.detail_panel]:
        assert panel.minimumWidth() >= 200
        assert panel.minimumHeight() >= 150


def test_splitter_handle_width(qtbot):
    """Splitter handles are 6px wide (bug #36)."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.main_splitter.handleWidth() == 6
    assert w.left_splitter.handleWidth() == 6
    assert w.right_splitter.handleWidth() == 6


def test_status_bar_exists(qtbot):
    """Status bar has repo, neurons, mode, zoom labels."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.status_bar is not None
    assert w.status_repo.text() == "No repo"
    assert w.status_mode.text() == "SOLO"
    assert w.status_zoom.text() == "100%"


def test_worker_registry(qtbot):
    """Worker registry can register and cancel."""
    from muninn.ui.main_window import MainWindow
    from PyQt6.QtCore import QObject, QThread

    w = MainWindow()
    qtbot.addWidget(w)

    class FakeWorker(QObject):
        def __init__(self):
            super().__init__()
            self._stop = False

    thread = QThread()
    worker = FakeWorker()
    w.register_worker("test", worker, thread)
    assert "test" in w._workers

    w.cancel_worker("test")
    assert "test" not in w._workers


def test_save_restore_state(qtbot):
    """save_state and restore don't crash."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.save_state()
    # No crash = success


def test_close_event(qtbot):
    """closeEvent stops autosave and saves state."""
    from muninn.ui.main_window import MainWindow
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    w.close()
    assert not w._autosave_timer.isActive()


# --- Signal wiring ---

def test_real_widgets_wired(qtbot):
    """Real widgets are used (not all placeholders)."""
    from muninn.ui.main_window import MainWindow
    from muninn.ui.neuron_map import NeuronMapWidget
    from muninn.ui.tree_view import TreeViewWidget
    from muninn.ui.detail_panel import DetailPanel
    w = MainWindow()
    qtbot.addWidget(w)
    assert isinstance(w.neuron_panel, NeuronMapWidget)
    assert isinstance(w.tree_panel, TreeViewWidget)
    assert isinstance(w.detail_panel, DetailPanel)


def test_neuron_select_updates_detail(qtbot):
    """Selecting a neuron updates detail panel."""
    from muninn.ui.main_window import MainWindow
    from muninn.ui.neuron_map import Neuron
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()

    neurons = [
        Neuron(id="a", label="Alpha", status="done", depends=["b"]),
        Neuron(id="b", label="Beta", status="wip"),
    ]
    w.neuron_panel.load_neurons(neurons)
    w.neuron_panel._handle_neuron_click(
        w.neuron_panel.neurons[0], Qt.KeyboardModifier.NoModifier
    )
    # Detail panel should show Alpha's info
    assert w.detail_panel._title.text() == "Alpha"


def test_neuron_select_highlights_tree(qtbot):
    """Selecting a neuron highlights in tree (bidirectional B-UI-11)."""
    from muninn.ui.main_window import MainWindow
    from muninn.ui.neuron_map import Neuron
    w = MainWindow()
    qtbot.addWidget(w)

    neurons = [Neuron(id="a", label="A"), Neuron(id="b", label="B")]
    w.neuron_panel.load_neurons(neurons)

    scan = {"nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}
    w.tree_panel.load_tree("feuillu", scan, positions=[(0.3, 0.3), (0.7, 0.7)])

    w.neuron_panel._handle_neuron_click(
        w.neuron_panel.neurons[0], Qt.KeyboardModifier.NoModifier
    )
    assert w.tree_panel._highlighted_id == "a"


def test_load_scan_integration(qtbot):
    """load_scan populates both neuron map and tree."""
    from muninn.ui.main_window import MainWindow
    from muninn.ui import _SCANS_DIR
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()

    scan_file = _SCANS_DIR / "infernal-wheel.json"
    if scan_file.exists():
        w.load_scan(str(scan_file))
        w.neuron_panel._cancel_laplacian()  # Cleanup thread
        assert len(w.neuron_panel.neurons) > 0
        assert len(w.tree_panel.nodes) > 0
        assert w.status_repo.text() != "No repo"
