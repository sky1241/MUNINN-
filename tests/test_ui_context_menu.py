"""Tests for muninn.ui.context_menu — B-UI-27 Right-click menus."""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QMenu


@pytest.fixture
def widget(qtbot):
    w = QWidget()
    qtbot.addWidget(w)
    return w


class TestInstallContextMenu:
    """B-UI-27: Context menu installation."""

    def test_installs_neuron_menu(self, widget):
        from muninn.ui.context_menu import install_context_menu
        install_context_menu(widget, "neuron")
        assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    def test_installs_tree_menu(self, widget):
        from muninn.ui.context_menu import install_context_menu
        install_context_menu(widget, "tree")
        assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    def test_installs_terminal_menu(self, widget):
        from muninn.ui.context_menu import install_context_menu
        install_context_menu(widget, "terminal")
        assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    def test_installs_detail_menu(self, widget):
        from muninn.ui.context_menu import install_context_menu
        install_context_menu(widget, "detail")
        assert widget.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu


class TestBuildMenus:
    """Test menu builders don't crash."""

    def test_neuron_menu_empty_selection(self, widget):
        from muninn.ui.context_menu import _build_neuron_menu
        menu = QMenu(widget)
        _build_neuron_menu(menu, widget, None)
        # Should have at least zoom-to-fit
        assert menu.actions()

    def test_neuron_menu_with_selection(self, widget):
        from muninn.ui.context_menu import _build_neuron_menu
        neuron = MagicMock(label="TestNeuron", id="t1", entry=None)
        widget.selected_neurons = [neuron]
        menu = QMenu(widget)
        _build_neuron_menu(menu, widget, None)
        action_texts = [a.text() for a in menu.actions()]
        assert any("TestNeuron" in t for t in action_texts)

    def test_tree_menu_no_node(self, widget):
        from muninn.ui.context_menu import _build_tree_menu
        widget.selected_node = None
        menu = QMenu(widget)
        _build_tree_menu(menu, widget, None)
        assert len(menu.actions()) == 0

    def test_tree_menu_with_node(self, widget):
        from muninn.ui.context_menu import _build_tree_menu
        widget.selected_node = MagicMock(label="Branch A", entry="/some/file.py")
        menu = QMenu(widget)
        _build_tree_menu(menu, widget, None)
        assert len(menu.actions()) >= 2  # copy + open + path

    def test_terminal_menu(self, widget):
        from muninn.ui.context_menu import _build_terminal_menu
        widget._output = MagicMock()
        widget._output.textCursor.return_value.selectedText.return_value = "sel"
        menu = QMenu(widget)
        _build_terminal_menu(menu, widget)
        assert len(menu.actions()) == 2  # copy + clear

    def test_detail_menu_empty(self, widget):
        from muninn.ui.context_menu import _build_detail_menu
        widget._title = MagicMock()
        widget._title.text.return_value = ""
        menu = QMenu(widget)
        _build_detail_menu(menu, widget)
        assert len(menu.actions()) == 0

    def test_detail_menu_with_title(self, widget):
        from muninn.ui.context_menu import _build_detail_menu
        widget._title = MagicMock()
        widget._title.text.return_value = "Some Concept"
        menu = QMenu(widget)
        _build_detail_menu(menu, widget)
        assert len(menu.actions()) == 1


class TestCopyText:
    """R9: Clipboard copy with retry."""

    def test_copy_text_no_crash(self):
        from muninn.ui.context_menu import _copy_text
        # Should not crash even if clipboard is unavailable
        _copy_text("test text")
