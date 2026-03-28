"""Tests for muninn.ui.shortcuts — B-UI-26 Global keyboard shortcuts."""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")


@pytest.fixture
def window(qtbot):
    from PyQt6.QtWidgets import QMainWindow
    w = QMainWindow()
    # Mock panel attributes expected by install_shortcuts
    w.neuron_panel = MagicMock()
    w.terminal_panel = MagicMock()
    w.tree_panel = MagicMock()
    w.detail_panel = MagicMock()
    w._search_bar = MagicMock()
    w._forest_toggle = MagicMock()
    w._command_palette = MagicMock()
    w._fullscreen_panel = None
    w.main_splitter = MagicMock()
    w.focusWidget = MagicMock(return_value=w.neuron_panel)
    qtbot.addWidget(w)
    return w


class TestInstallShortcuts:
    """B-UI-26: Global keyboard shortcuts."""

    def test_installs_without_crash(self, window):
        from muninn.ui.shortcuts import install_shortcuts
        install_shortcuts(window)
        assert hasattr(window, '_shortcuts')

    def test_shortcuts_stored(self, window):
        from muninn.ui.shortcuts import install_shortcuts
        install_shortcuts(window)
        assert len(window._shortcuts) >= 6

    def test_shortcuts_not_gc(self, window):
        from muninn.ui.shortcuts import install_shortcuts
        install_shortcuts(window)
        # All shortcuts should still be alive (not garbage collected)
        for sc in window._shortcuts:
            assert sc is not None


class TestShortcutHelpers:
    """Test internal shortcut handler functions."""

    def test_focus_search(self):
        from muninn.ui.shortcuts import _focus_search
        window = MagicMock()
        window._search_bar = MagicMock()
        _focus_search(window)
        window._search_bar.focus_input.assert_called_once()

    def test_toggle_mode(self):
        from muninn.ui.shortcuts import _toggle_mode
        window = MagicMock()
        window._forest_toggle = MagicMock()
        _toggle_mode(window)
        window._forest_toggle.toggle.assert_called_once()

    def test_escape_deselect(self):
        from muninn.ui.shortcuts import _escape
        window = MagicMock()
        window.neuron_panel = MagicMock()
        window.neuron_panel._selected = set([1, 2])
        _escape(window)
        assert len(window.neuron_panel._selected) == 0

    def test_show_command_palette(self):
        from muninn.ui.shortcuts import _show_command_palette
        window = MagicMock()
        window._command_palette = MagicMock()
        _show_command_palette(window)
        window._command_palette.show.assert_called_once()
