"""Muninn UI — Search bar for neuron map.

B-UI-25: Substring search with debounce 200ms.
Enter = zoom + center + select. Escape = clear.
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel

from muninn.ui.theme import (
    BG_1DP, ACCENT_CYAN_HEX, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY,
)


class SearchBar(QWidget):
    """Search bar with debounced substring matching (B-UI-25).

    Emits search_changed with matched neuron IDs on each keystroke (debounced).
    Emits search_confirmed when Enter is pressed.
    """

    search_changed = pyqtSignal(set)    # set of matching neuron IDs
    search_confirmed = pyqtSignal(str)  # confirmed search text
    search_cleared = pyqtSignal()       # Escape pressed

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        icon = QLabel("\U0001F50D")  # magnifying glass
        icon.setFont(QFont(FONT_BODY, 12))
        layout.addWidget(icon)

        self._input = QLineEdit()
        self._input.setFont(QFont(FONT_BODY, 11))
        self._input.setPlaceholderText("Search neurons...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; "
            f"padding: 4px 8px; }}"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_confirm)
        layout.addWidget(self._input, 1)

        self.setFixedHeight(36)

        # Debounce timer (200ms)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._emit_search)

        # Store neuron list reference for matching
        self._neurons = []

    def set_neurons(self, neurons):
        """Set neuron list for substring matching."""
        self._neurons = neurons

    def _on_text_changed(self, text: str):
        """Debounced text change."""
        self._debounce.start()

    def _emit_search(self):
        """Emit matched neuron IDs."""
        text = self._input.text().strip().lower()
        if not text:
            self.search_cleared.emit()
            return

        matched = set()
        for n in self._neurons:
            if text in n.label.lower() or text in n.id.lower():
                matched.add(n.id)
        self.search_changed.emit(matched)

    def _on_confirm(self):
        """Enter pressed — confirm search."""
        text = self._input.text().strip()
        if text:
            self.search_confirmed.emit(text)

    def keyPressEvent(self, event):
        """Escape clears search."""
        if event.key() == Qt.Key.Key_Escape:
            self._input.clear()
            self.search_cleared.emit()
            return
        super().keyPressEvent(event)

    def focus_input(self):
        """Focus the search input (Ctrl+F)."""
        self._input.setFocus()
        self._input.selectAll()
