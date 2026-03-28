"""Tests for B-UI-19 + B-UI-20: Terminal widget."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


def test_terminal_creates(qtbot):
    """TerminalWidget creates and shows."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    assert w.accessibleName() == "Terminal"


def test_terminal_empty_state(qtbot):
    """Terminal starts with empty output."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._output.toPlainText() == ""


def test_command_history(qtbot):
    """Command history stores entries."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._input.setText("hello")
    w._on_enter()
    w._stop_llm()  # Cancel LLM thread
    assert len(w._history) == 1
    assert w._history[0] == "hello"


def test_clear_command(qtbot):
    """Ctrl+L or /clear clears output."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._append_text("some text")
    assert w._output.toPlainText().strip() != ""
    w._handle_command("/clear")
    assert w._output.toPlainText() == ""


def test_help_command(qtbot):
    """/help shows commands."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._handle_command("/help")
    text = w._output.toPlainText()
    assert "/clear" in text
    assert "/help" in text


def test_unknown_command(qtbot):
    """Unknown command shows error."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._handle_command("/foobar")
    assert "Unknown command" in w._output.toPlainText()


def test_max_block_count(qtbot):
    """Output is limited to 5000 blocks (bug #61)."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._output.document().maximumBlockCount() == 5000


def test_breathing_hidden_by_default(qtbot):
    """Breathing indicator is hidden by default."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert not w._breathing.isVisible()
    assert not w._stop_btn.isVisible()


def test_stop_button_hides_after_stop(qtbot):
    """Stop cancels LLM and hides indicator."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._stop_llm()
    assert not w._breathing.isVisible()
    assert not w._stop_btn.isVisible()


def test_set_context(qtbot):
    """set_context stores LLM context."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w.set_context("You are helping with compression")
    assert w._context == "You are helping with compression"


def test_flash_timer(qtbot):
    """Flash timer exists and is single-shot."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._flash_timer.isSingleShot()
    assert w._flash_timer.interval() == 150


def test_command_signal(qtbot):
    """command_entered signal emits on Enter."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    received = []
    w.command_entered.connect(lambda t: received.append(t))
    w._input.setText("test command")
    w._on_enter()
    w._stop_llm()
    assert len(received) == 1
    assert received[0] == "test command"
