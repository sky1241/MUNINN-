"""Muninn UI — MainWindow with 4-panel layout.

B-UI-01: QMainWindow, nested QSplitters, status bar, geometry save/restore.
Rules applied: R1 (ownership), R4 (closeEvent), R7 (main entry), R13 (worker registry),
R14 (geometry restore safe), bug #36 (handleWidth 6), bug #39b (min panel size),
bug #54 (setSizes in showEvent), bug #57 (screen detach).
"""

import sys
import os
import time

from PyQt6.QtCore import Qt, QTimer, QSettings, QByteArray
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QStatusBar, QLabel,
    QApplication, QVBoxLayout,
)


class PlaceholderPanel(QWidget):
    """Temporary placeholder for panels not yet implemented."""

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)  # bug #39b: prevent collapse to 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        self._label = QLabel(label_text)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setProperty("heading", True)
        layout.addWidget(self._label)


class MainWindow(QMainWindow):
    """Main 4-panel window: neuron map (TL), terminal (TR), tree (BL), detail (BR)."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Muninn \u2014 Winter Tree")
        self.setMinimumSize(800, 600)

        # R13: Worker registry
        self._workers = {}

        # Auto-save timer (60s)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(60_000)
        self._autosave_timer.timeout.connect(self.save_state)
        self._autosave_timer.start()

        self._build_ui()
        self._build_status_bar()
        self._restore_state()

    def _build_ui(self):
        """Create 4-panel layout with nested splitters."""
        # Main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setHandleWidth(6)  # bug #36: visible handles

        # Left vertical splitter (neuron map top, tree bottom)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setHandleWidth(6)

        # Right vertical splitter (terminal top, detail bottom)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(6)

        # 4 placeholder panels (replaced by real widgets in later briques)
        self.neuron_panel = PlaceholderPanel("Neuron Map")
        self.terminal_panel = PlaceholderPanel("Terminal LLM")
        self.tree_panel = PlaceholderPanel("Botanical Tree")
        self.detail_panel = PlaceholderPanel("Details")

        self.left_splitter.addWidget(self.neuron_panel)
        self.left_splitter.addWidget(self.tree_panel)

        self.right_splitter.addWidget(self.terminal_panel)
        self.right_splitter.addWidget(self.detail_panel)

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)

        self.setCentralWidget(self.main_splitter)

    def _build_status_bar(self):
        """Status bar: repo name, neuron count, mode, zoom %."""
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.status_repo = QLabel("No repo")
        self.status_neurons = QLabel("0 neurons")
        self.status_mode = QLabel("SOLO")
        self.status_zoom = QLabel("100%")

        self.status_bar.addWidget(self.status_repo, 1)
        self.status_bar.addWidget(self.status_neurons)
        self.status_bar.addWidget(self.status_mode)
        self.status_bar.addPermanentWidget(self.status_zoom)

    def showEvent(self, event):
        """Set initial splitter sizes AFTER show (bug #54)."""
        super().showEvent(event)
        if not hasattr(self, "_sizes_set"):
            w = self.width()
            h = self.height()
            self.main_splitter.setSizes([w * 6 // 10, w * 4 // 10])
            self.left_splitter.setSizes([h * 6 // 10, h * 4 // 10])
            self.right_splitter.setSizes([h * 6 // 10, h * 4 // 10])
            self._sizes_set = True

    # --- Worker registry (R13) ---

    def register_worker(self, name, worker, thread):
        """Register a worker+thread pair. Cancels existing worker with same name."""
        self.cancel_worker(name)
        self._workers[name] = (worker, thread)

    def cancel_worker(self, name):
        """Cancel a running worker by name."""
        if name in self._workers:
            w, t = self._workers.pop(name)
            w._stop = True
            t.quit()
            t.wait(2000)

    # --- State persistence ---

    def save_state(self):
        """Save window geometry and splitter sizes to QSettings."""
        settings = QSettings("Muninn", "WinterTree")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("main_splitter", self.main_splitter.saveState())
        settings.setValue("left_splitter", self.left_splitter.saveState())
        settings.setValue("right_splitter", self.right_splitter.saveState())

    def _restore_state(self):
        """Restore geometry + splitter sizes from QSettings."""
        settings = QSettings("Muninn", "WinterTree")
        geom = settings.value("geometry")
        if geom and isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
            self._restore_geometry_safe()

        for key, splitter in [
            ("main_splitter", self.main_splitter),
            ("left_splitter", self.left_splitter),
            ("right_splitter", self.right_splitter),
        ]:
            state = settings.value(key)
            if state and isinstance(state, QByteArray):
                splitter.restoreState(state)

    def _restore_geometry_safe(self):
        """Verify window is on an existing screen (R14, bug #57)."""
        screen = QApplication.screenAt(self.geometry().center())
        if screen is None:
            primary = QApplication.primaryScreen()
            if primary:
                center = primary.availableGeometry().center()
                self.move(
                    center.x() - self.width() // 2,
                    center.y() - self.height() // 2,
                )

    # --- Close (R4) ---

    def closeEvent(self, event):
        """Clean shutdown: cancel all workers, save state."""
        for name in list(self._workers):
            self.cancel_worker(name)
        self._autosave_timer.stop()
        self.save_state()
        event.accept()


def main():
    """Entry point for Muninn UI (R7)."""
    # HiDPI BEFORE anything
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # OpenGL format BEFORE QApplication
    from PyQt6.QtGui import QSurfaceFormat
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    QSurfaceFormat.setDefaultFormat(fmt)

    # ANGLE fallback for bad GPUs
    if os.environ.get("MUNINN_GL_SOFTWARE"):
        os.environ["QT_OPENGL"] = "angle"

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Mandatory for dark mode on Win11

    # Exception hook (Qt swallows exceptions in nested event loops)
    def exception_hook(exc_type, exc_value, exc_tb):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = exception_hook

    from muninn.ui.theme import load_theme
    from muninn.ui import load_fonts
    from PyQt6.QtGui import QPixmapCache

    app.setStyleSheet(load_theme())
    QPixmapCache.clear()  # bug #44
    load_fonts()

    window = MainWindow()
    window.show()
    ret = app.exec()
    del window  # explicit destruction order (R7)
    del app
    sys.exit(ret)


if __name__ == "__main__":
    main()
