"""Muninn UI — Terminal Widget.

B-UI-19: Terminal basique (QTextEdit + QLineEdit, history, Ctrl+L, flash).
B-UI-20: LLM connection (QThread, streaming, breathing indicator, stop).

Rules: R1 (ownership), R3 (worker pattern), R5 (repaint throttle),
R8 (empty state), bug #61 (maxBlockCount 5000), bug #20 (no QMessageBox in slot).
"""

import time
from typing import Optional

from PyQt6.QtCore import (
    Qt, QTimer, QThread, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QFont, QColor, QTextCursor, QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QPushButton, QLabel, QGraphicsOpacityEffect,
)

from muninn.ui.theme import (
    BG_1DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_CODE, FONT_BODY,
)


class LLMWorker(QObject):
    """Background worker for LLM API calls (R3, B-UI-20).

    Streams response chunks via signal. Supports cancellation.
    """

    chunk_ready = pyqtSignal(str)   # One chunk of text
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, prompt: str, context: str = ""):
        super().__init__()
        self._stop = False
        self._prompt = prompt
        self._context = context

    def run(self):
        """Execute LLM call. Override for actual API integration."""
        try:
            # Try Anthropic API if available
            try:
                import anthropic
                client = anthropic.Anthropic()
                system = self._context or "You are Muninn, a memory compression assistant."
                with client.messages.stream(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    system=system,
                    messages=[{"role": "user", "content": self._prompt}],
                ) as stream:
                    for text in stream.text_stream:
                        if self._stop:
                            return
                        self.chunk_ready.emit(text)
            except ImportError:
                # No anthropic package — echo mode
                self.chunk_ready.emit(f"[echo] {self._prompt}\n")
                self.chunk_ready.emit("(Install 'anthropic' package for LLM features)")
            except Exception as e:
                self.error.emit(str(e))
                return

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class TerminalWidget(QWidget):
    """Terminal panel with command input, history, and LLM integration.

    B-UI-19: basic terminal (history, Ctrl+L, flash, maxBlockCount).
    B-UI-20: LLM streaming with breathing indicator and stop button.
    """

    command_entered = pyqtSignal(str)  # Raw command text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setAccessibleName("Terminal")

        # History
        self._history: list[str] = []
        self._history_pos = -1

        # LLM state
        self._llm_thread: Optional[QThread] = None
        self._llm_worker: Optional[LLMWorker] = None
        self._context: str = ""

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Output area
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont(FONT_CODE, 12))
        self._output.setStyleSheet(
            f"QTextEdit {{ background: {BG_1DP}; color: {ACCENT_GREEN}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._output.document().setMaximumBlockCount(5000)  # bug #61
        layout.addWidget(self._output, 1)

        # Breathing indicator (B-UI-20)
        self._breathing = QLabel("\u2022")  # dot
        self._breathing.setFont(QFont(FONT_BODY, 20))
        self._breathing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._breathing.setStyleSheet(f"color: {ACCENT_CYAN_HEX};")
        self._breathing.setFixedHeight(24)
        self._breathing.hide()

        self._breath_effect = QGraphicsOpacityEffect(self._breathing)
        self._breath_effect.setOpacity(1.0)
        self._breathing.setGraphicsEffect(self._breath_effect)

        self._breath_anim = QPropertyAnimation(self._breath_effect, b"opacity", self)
        self._breath_anim.setDuration(2000)
        self._breath_anim.setStartValue(0.4)
        self._breath_anim.setEndValue(1.0)
        self._breath_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._breath_anim.setLoopCount(-1)  # Infinite loop

        layout.addWidget(self._breathing)

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(4)

        self._prompt_label = QLabel(">")
        self._prompt_label.setFont(QFont(FONT_CODE, 12))
        self._prompt_label.setStyleSheet(f"color: {ACCENT_CYAN_HEX};")
        input_layout.addWidget(self._prompt_label)

        self._input = QLineEdit()
        self._input.setFont(QFont(FONT_CODE, 12))
        self._input.setPlaceholderText("Type a command or ask a question...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._input.returnPressed.connect(self._on_enter)
        input_layout.addWidget(self._input, 1)

        # Stop button (B-UI-20)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(239,68,68,0.2); color: #EF4444; "
            f"border: 1px solid #EF4444; border-radius: 8px; padding: 4px 12px; }}"
        )
        self._stop_btn.clicked.connect(self._stop_llm)
        self._stop_btn.hide()
        input_layout.addWidget(self._stop_btn)

        layout.addLayout(input_layout)

        # Flash timer for input line
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(150)
        self._flash_timer.timeout.connect(self._flash_reset)

    def _on_enter(self):
        """Handle Enter key: process command."""
        text = self._input.text().strip()
        if not text:
            return

        # Add to history
        self._history.append(text)
        self._history_pos = len(self._history)

        # Flash input line yellow
        self._input.setStyleSheet(
            f"QLineEdit {{ background: rgba(245,158,11,0.3); color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )
        self._flash_timer.start()

        self._input.clear()

        # Display command
        self._append_text(f"> {text}", color=ACCENT_CYAN_HEX)

        # Emit signal
        self.command_entered.emit(text)

        # Check if it's a local command or LLM query
        if text.startswith("/"):
            self._handle_command(text)
        else:
            self._start_llm(text)

    def _handle_command(self, cmd: str):
        """Handle local commands."""
        if cmd == "/clear":
            self._output.clear()
        elif cmd == "/help":
            self._append_text(
                "Commands:\n"
                "  /clear   — Clear terminal\n"
                "  /help    — Show this help\n"
                "  /scan    — Scan current repo\n"
                "  /status  — Show Muninn status\n"
                "  (text)   — Ask the LLM",
                color=TEXT_SECONDARY,
            )
        else:
            self._append_text(f"Unknown command: {cmd}", color="#EF4444")

    def _start_llm(self, prompt: str):
        """Launch LLM query in background thread (R3, B-UI-20)."""
        self._stop_llm()  # Cancel previous

        self._llm_thread = QThread()
        self._llm_worker = LLMWorker(prompt, self._context)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.chunk_ready.connect(self._on_chunk)
        self._llm_worker.finished.connect(self._on_llm_done)
        self._llm_worker.error.connect(self._on_llm_error)
        self._llm_worker.finished.connect(self._llm_thread.quit)
        self._llm_worker.error.connect(self._llm_thread.quit)

        # Show breathing + stop button
        self._breathing.show()
        self._breath_anim.start()
        self._stop_btn.show()

        self._llm_thread.start()

    def _stop_llm(self):
        """Cancel running LLM query (R12)."""
        if self._llm_worker is not None:
            self._llm_worker._stop = True
        if self._llm_thread is not None and self._llm_thread.isRunning():
            self._llm_thread.quit()
            self._llm_thread.wait(2000)
        self._llm_worker = None
        self._llm_thread = None
        self._breathing.hide()
        self._breath_anim.stop()
        self._stop_btn.hide()

    def _on_chunk(self, text: str):
        """Append streaming LLM chunk."""
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TEXT_PRIMARY))
        cursor.insertText(text, fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _on_llm_done(self):
        """LLM finished."""
        self._append_text("")  # New line
        self._stop_llm()

    def _on_llm_error(self, msg: str):
        """LLM error (bug #20: no QMessageBox here)."""
        self._append_text(f"Error: {msg}", color="#EF4444")
        self._stop_llm()

    def _append_text(self, text: str, color: str = ACCENT_GREEN):
        """Append colored text to output."""
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.insertText(text + "\n", fmt)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def _flash_reset(self):
        """Reset input style after flash."""
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 8px; }}"
        )

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_L:
                self._output.clear()
                return
        # History navigation
        if event.key() == Qt.Key.Key_Up and self._input.hasFocus():
            if self._history and self._history_pos > 0:
                self._history_pos -= 1
                self._input.setText(self._history[self._history_pos])
            return
        if event.key() == Qt.Key.Key_Down and self._input.hasFocus():
            if self._history_pos < len(self._history) - 1:
                self._history_pos += 1
                self._input.setText(self._history[self._history_pos])
            else:
                self._history_pos = len(self._history)
                self._input.clear()
            return
        super().keyPressEvent(event)

    def set_context(self, context: str):
        """Set LLM system context (selected neuron info, etc.)."""
        self._context = context

    def closeEvent(self, event):
        self._stop_llm()
        super().closeEvent(event)
