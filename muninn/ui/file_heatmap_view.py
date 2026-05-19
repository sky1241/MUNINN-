"""CHUNK C11 (2026-05-19) — File line-by-line heatmap view.

QPlainTextEdit read-only + custom left gutter that paints a colored
band per line so the user can see the geography of the reconstruction
at a glance:

- green   : line covered by an anchor (ast_hints) — LLM had a constraint.
- red     : gap line in a cube that did NOT SHA match.
- orange  : gap line in a cube that DID SHA match (lucky guess —
            the LLM produced the right line without any anchor).

Designed to sit in the bottom of the left split (under the cube 3D),
side-by-side with the heatmap so the user can correlate cube neurons
with file positions.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QFont, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPlainTextEdit, QHBoxLayout,
)


# Hex colors aligned with NeuronMapWidget gradient.
_COLOR_GREEN = QColor("#32CD32")
_COLOR_RED = QColor("#EF4444")
_COLOR_ORANGE = QColor("#F59E0B")
_COLOR_NEUTRAL = QColor(60, 60, 60)

_STATUS_TO_QCOLOR = {
    "green": _COLOR_GREEN,
    "red": _COLOR_RED,
    "orange": _COLOR_ORANGE,
}

# Gutter width in pixels.
_GUTTER_WIDTH = 14


class _LineGutter(QWidget):
    """Left gutter widget that paints the per-line color band."""

    def __init__(self, editor: QPlainTextEdit, view: "FileHeatmapView"):
        super().__init__(editor)
        self._editor = editor
        self._view = view
        self.setFixedWidth(_GUTTER_WIDTH)

    def sizeHint(self) -> QSize:
        return QSize(_GUTTER_WIDTH, 0)

    def paintEvent(self, event):  # noqa: N802 — Qt API
        painter = QPainter(self)
        try:
            painter.fillRect(event.rect(), QColor(20, 20, 20))
            block = self._editor.firstVisibleBlock()
            top = int(self._editor.blockBoundingGeometry(block).translated(
                self._editor.contentOffset()).top())
            height = int(self._editor.blockBoundingRect(block).height())
            colors = self._view._line_colors
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and (top + height) >= event.rect().top():
                    # blockNumber is 0-indexed; line_colors keys are 1-indexed
                    line_no = block.blockNumber() + 1
                    status = colors.get(line_no)
                    color = _STATUS_TO_QCOLOR.get(status, _COLOR_NEUTRAL)
                    painter.fillRect(
                        QRect(0, top, _GUTTER_WIDTH - 2, height), color
                    )
                block = block.next()
                top += height
                height = int(self._editor.blockBoundingRect(block).height())
        finally:
            painter.end()


class FileHeatmapView(QWidget):
    """Read-only file viewer with per-line color gutter.

    Signals:
      - line_clicked(int): emitted when the user clicks on a line
        (1-indexed file line number).
    """

    line_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_colors: dict = {}
        self._current_path: str = ""
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._editor = QPlainTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setFont(QFont("monospace", 10))
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setStyleSheet(
            "QPlainTextEdit { background:#0c0c0c; color:#e8e8e8; border:0; }"
        )

        self._gutter = _LineGutter(self._editor, self)

        layout.addWidget(self._gutter)
        layout.addWidget(self._editor, 1)

        # Repaint gutter when editor scrolls.
        self._editor.updateRequest.connect(lambda _r, _dy: self._gutter.update())
        self._editor.verticalScrollBar().valueChanged.connect(
            lambda _v: self._gutter.update()
        )

        # Track mouse clicks for line_clicked emit.
        self._editor.cursorPositionChanged.connect(self._on_cursor_changed)

    def load_file(self, path: str) -> None:
        """Load a file's full content into the read-only viewer."""
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = f"[unable to read {path}]"
        self._editor.setPlainText(text)
        self._current_path = str(path)
        self._gutter.update()

    def set_line_colors(self, line_colors: dict) -> None:
        """Set the per-line color mapping. Keys are 1-indexed line numbers,
        values are 'green' | 'red' | 'orange' (unknown values render as
        neutral grey)."""
        self._line_colors = dict(line_colors or {})
        self._gutter.update()

    def _on_cursor_changed(self):
        cursor = self._editor.textCursor()
        # blockNumber is 0-indexed; emit 1-indexed line number
        self._emit_line_clicked(cursor.blockNumber() + 1)

    def _emit_line_clicked(self, line_no: int) -> None:
        """Direct API entry point for tests and programmatic triggers."""
        try:
            self.line_clicked.emit(int(line_no))
        except Exception:
            pass
