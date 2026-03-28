"""Tests for muninn.ui.command_palette — B-UI-29 Command palette."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


@pytest.fixture
def palette(qtbot):
    from muninn.ui.command_palette import CommandPalette
    w = CommandPalette()
    qtbot.addWidget(w)
    return w


class TestCommandPalette:
    """B-UI-29: Ctrl+Shift+P command palette."""

    def test_creates(self, palette):
        assert palette is not None

    def test_initial_list_populated(self, palette):
        from muninn.ui.command_palette import ACTIONS
        assert palette._list.count() == len(ACTIONS)

    def test_filter_narrows_results(self, palette):
        palette._filter("zoom")
        assert palette._list.count() >= 1
        assert palette._list.count() < 12

    def test_filter_empty_restores_all(self, palette):
        from muninn.ui.command_palette import ACTIONS
        palette._filter("zoom")
        palette._filter("")
        assert palette._list.count() == len(ACTIONS)

    def test_confirm_emits_signal(self, palette, qtbot):
        # Select first item
        palette._list.setCurrentRow(0)
        with qtbot.waitSignal(palette.action_selected, timeout=500):
            palette._confirm()

    def test_confirm_hides(self, palette):
        palette.show()
        palette._list.setCurrentRow(0)
        palette._confirm()
        assert not palette.isVisible()

    def test_escape_hides(self, palette):
        palette.show()
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        palette.keyPressEvent(event)
        assert not palette.isVisible()

    def test_focus_input_clears(self, palette):
        palette._input.setText("old query")
        palette.focus_input()
        assert palette._input.text() == ""

    def test_actions_have_callbacks(self):
        from muninn.ui.command_palette import ACTIONS
        for name, shortcut, callback in ACTIONS:
            assert callback  # non-empty string
            assert name  # non-empty string

    def test_fixed_size(self, palette):
        assert palette.width() == 400
        assert palette.height() == 300
