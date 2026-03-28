"""Tests for muninn.ui.search — B-UI-25 Search bar."""

import pytest
from unittest.mock import MagicMock

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


@pytest.fixture
def bar(qtbot):
    from muninn.ui.search import SearchBar
    w = SearchBar()
    qtbot.addWidget(w)
    return w


class TestSearchBar:
    """B-UI-25: Substring search with debounce."""

    def test_creates(self, bar):
        assert bar is not None

    def test_fixed_height(self, bar):
        assert bar.maximumHeight() == 36

    def test_placeholder_text(self, bar):
        assert "earch" in bar._input.placeholderText().lower()

    def test_set_neurons(self, bar):
        neurons = [MagicMock(label="Alpha", id="a1"), MagicMock(label="Beta", id="b2")]
        bar.set_neurons(neurons)
        assert len(bar._neurons) == 2

    def test_debounce_interval(self, bar):
        assert bar._debounce.interval() == 200

    def test_emit_search_with_match(self, bar, qtbot):
        neurons = [MagicMock(label="Alpha", id="a1"), MagicMock(label="Beta", id="b2")]
        bar.set_neurons(neurons)
        bar._input.setText("alp")
        with qtbot.waitSignal(bar.search_changed, timeout=500) as blocker:
            bar._emit_search()
        assert "a1" in blocker.args[0]

    def test_emit_search_no_match(self, bar, qtbot):
        neurons = [MagicMock(label="Alpha", id="a1")]
        bar.set_neurons(neurons)
        bar._input.setText("zzz")
        with qtbot.waitSignal(bar.search_changed, timeout=500) as blocker:
            bar._emit_search()
        assert len(blocker.args[0]) == 0

    def test_empty_text_emits_cleared(self, bar, qtbot):
        bar._input.setText("")
        with qtbot.waitSignal(bar.search_cleared, timeout=500):
            bar._emit_search()

    def test_confirm_emits_signal(self, bar, qtbot):
        bar._input.setText("test query")
        with qtbot.waitSignal(bar.search_confirmed, timeout=500) as blocker:
            bar._on_confirm()
        assert blocker.args == ["test query"]

    def test_focus_input(self, bar):
        bar.focus_input()
        # Should not crash

    def test_escape_clears(self, bar, qtbot):
        bar._input.setText("something")
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        bar.keyPressEvent(event)
        assert bar._input.text() == ""
