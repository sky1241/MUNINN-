"""Muninn UI — System tray icon.

B-UI-30: Tray icon with minimize-to-tray, notifications for scan complete.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication


class MuninnTray(QSystemTrayIcon):
    """System tray icon with context menu (B-UI-30)."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self._window = window

        # Use app icon or fallback
        icon = QApplication.windowIcon()
        if icon.isNull():
            from PyQt6.QtGui import QPixmap, QPainter, QColor
            pm = QPixmap(32, 32)
            pm.fill(QColor(0, 0, 0, 0))
            p = QPainter(pm)
            p.setBrush(QColor(0, 220, 255))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(4, 4, 24, 24)
            p.end()
            icon = QIcon(pm)

        self.setIcon(icon)
        self.setToolTip("Muninn — Winter Tree")

        # Context menu
        menu = QMenu()
        act_show = QAction("Show", menu)
        act_show.triggered.connect(self._show_window)
        menu.addAction(act_show)

        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _show_window(self):
        self._window.showNormal()
        self._window.activateWindow()
        self._window.raise_()

    def notify(self, title: str, message: str, duration_ms: int = 3000):
        """Show a tray notification (B-UI-30)."""
        if self.supportsMessages():
            self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms)
