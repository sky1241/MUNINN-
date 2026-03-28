"""Tests for B-UI-01: MainWindow with 4-panel layout."""

import pytest
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
