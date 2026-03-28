"""Muninn UI — Command Palette.

B-UI-29: Ctrl+Shift+P overlay, fuzzy search on actions, shortcuts displayed.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
)

from muninn.ui.theme import BG_1DP, BG_2DP, ACCENT_CYAN_HEX, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY


# All available actions: (name, shortcut, callback_name)
ACTIONS = [
    ("Zoom to fit", "Ctrl+0", "zoom_to_fit"),
    ("Switch Solo/Forest", "Space", "toggle_mode"),
    ("Search neurons", "Ctrl+F", "focus_search"),
    ("Clear terminal", "Ctrl+L", "clear_terminal"),
    ("Export screenshot", "Ctrl+Shift+S", "export_screenshot"),
    ("Focus Neuron Map", "Ctrl+1", "focus_neuron"),
    ("Focus Terminal", "Ctrl+2", "focus_terminal"),
    ("Focus Tree View", "Ctrl+3", "focus_tree"),
    ("Focus Detail Panel", "Ctrl+4", "focus_detail"),
    ("Fullscreen panel", "F11", "fullscreen"),
    ("Deselect all", "Escape", "deselect"),
    ("Scan repo", "", "scan_repo"),
]


class CommandPalette(QDialog):
    """Overlay command palette with fuzzy search (B-UI-29)."""

    action_selected = pyqtSignal(str)  # callback_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(400, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._input = QLineEdit()
        self._input.setFont(QFont(FONT_BODY, 13))
        self._input.setPlaceholderText("Type a command...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {BG_1DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {ACCENT_CYAN_HEX}; border-radius: 8px; "
            f"padding: 8px 12px; }}"
        )
        self._input.textChanged.connect(self._filter)
        self._input.returnPressed.connect(self._confirm)
        layout.addWidget(self._input)

        self._list = QListWidget()
        self._list.setFont(QFont(FONT_BODY, 12))
        self._list.setStyleSheet(
            f"QListWidget {{ background: {BG_2DP}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; }} "
            f"QListWidget::item:selected {{ background: rgba(0,220,255,0.2); }}"
        )
        self._list.itemDoubleClicked.connect(lambda item: self._confirm())
        layout.addWidget(self._list)

        self.setStyleSheet(f"QDialog {{ background: {BG_1DP}; border-radius: 12px; }}")

        self._populate()

    def _populate(self):
        """Fill list with all actions."""
        self._list.clear()
        for name, shortcut, callback in ACTIONS:
            text = f"{name}  ({shortcut})" if shortcut else name
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, callback)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        """Fuzzy filter actions."""
        query = text.lower()
        self._list.clear()
        for name, shortcut, callback in ACTIONS:
            if query in name.lower() or query in callback.lower():
                display = f"{name}  ({shortcut})" if shortcut else name
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, callback)
                self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _confirm(self):
        """Execute selected action."""
        item = self._list.currentItem()
        if item:
            callback = item.data(Qt.ItemDataRole.UserRole)
            self.action_selected.emit(callback)
        self.hide()

    def focus_input(self):
        """Focus the input field."""
        self._input.clear()
        self._input.setFocus()
        self._populate()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._list.keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def show(self):
        """Center on parent and show."""
        if self.parent():
            parent = self.parent()
            x = parent.x() + (parent.width() - self.width()) // 2
            y = parent.y() + parent.height() // 4
            self.move(x, y)
        super().show()
        self.focus_input()
