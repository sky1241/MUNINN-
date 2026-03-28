"""Tests for drag_drop, system_tray, about_dialog — B-UI-28/30/32."""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


class TestDragDrop:
    """B-UI-28: Drag and drop folder onto neuron map."""

    def test_install_sets_accept_drops(self, qtbot):
        from muninn.ui.drag_drop import install_drag_drop
        w = QWidget()
        qtbot.addWidget(w)
        install_drag_drop(w)
        assert w.acceptDrops()

    def test_install_with_window(self, qtbot):
        from muninn.ui.drag_drop import install_drag_drop
        w = QWidget()
        qtbot.addWidget(w)
        window = MagicMock()
        install_drag_drop(w, window)
        assert w._dd_window is window

    def test_drag_enter_rejects_non_url(self, qtbot):
        from muninn.ui.drag_drop import install_drag_drop
        w = QWidget()
        qtbot.addWidget(w)
        install_drag_drop(w)
        event = MagicMock()
        event.mimeData.return_value.hasUrls.return_value = False
        w.dragEnterEvent(event)
        event.ignore.assert_called()


class TestAboutDialog:
    """B-UI-32: About dialog."""

    def test_creates(self, qtbot):
        from muninn.ui.about_dialog import AboutDialog
        d = AboutDialog()
        qtbot.addWidget(d)
        assert d.windowTitle() == "About Muninn"

    def test_fixed_size(self, qtbot):
        from muninn.ui.about_dialog import AboutDialog
        d = AboutDialog()
        qtbot.addWidget(d)
        assert d.width() == 360
        assert d.height() == 280

    def test_has_title_label(self, qtbot):
        from muninn.ui.about_dialog import AboutDialog
        d = AboutDialog()
        qtbot.addWidget(d)
        # Find a label with "Muninn" text
        from PyQt6.QtWidgets import QLabel
        labels = d.findChildren(QLabel)
        texts = [l.text() for l in labels]
        assert any("Muninn" in t for t in texts)

    def test_ok_button_closes(self, qtbot):
        from muninn.ui.about_dialog import AboutDialog
        from PyQt6.QtWidgets import QPushButton
        d = AboutDialog()
        qtbot.addWidget(d)
        btns = d.findChildren(QPushButton)
        assert len(btns) == 1
        assert btns[0].text() == "OK"


class TestSystemTray:
    """B-UI-30: System tray icon."""

    def test_creates(self, qtbot):
        from muninn.ui.system_tray import MuninnTray
        from PyQt6.QtWidgets import QMainWindow
        w = QMainWindow()
        qtbot.addWidget(w)
        tray = MuninnTray(w)
        assert tray is not None

    def test_has_context_menu(self, qtbot):
        from muninn.ui.system_tray import MuninnTray
        from PyQt6.QtWidgets import QMainWindow
        w = QMainWindow()
        qtbot.addWidget(w)
        tray = MuninnTray(w)
        assert tray.contextMenu() is not None
        assert len(tray.contextMenu().actions()) == 2  # Show + Quit

    def test_tooltip(self, qtbot):
        from muninn.ui.system_tray import MuninnTray
        from PyQt6.QtWidgets import QMainWindow
        w = QMainWindow()
        qtbot.addWidget(w)
        tray = MuninnTray(w)
        assert "Muninn" in tray.toolTip()
