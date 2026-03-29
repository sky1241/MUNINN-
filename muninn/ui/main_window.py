"""Muninn UI — MainWindow with 4-panel layout.

B-UI-01: QMainWindow, nested QSplitters, status bar, geometry save/restore.
Real widgets wired: NeuronMapWidget, TreeViewWidget, DetailPanel, TerminalWidget.
Signal wiring: neuron_selected -> tree highlight + detail panel + status bar.

Rules applied: R1 (ownership), R4 (closeEvent), R7 (main entry), R13 (worker registry),
R14 (geometry restore safe), bug #36 (handleWidth 6), bug #39b (min panel size),
bug #54 (setSizes in showEvent), bug #57 (screen detach).
"""

import sys
import os

from PyQt6.QtCore import Qt, QTimer, QSettings, QByteArray
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QStatusBar, QLabel,
    QApplication, QVBoxLayout, QHBoxLayout,
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

        self._fullscreen_panel = None  # F11 state

        self._build_ui()
        self._build_status_bar()
        self._wire_signals()
        self._install_extras()
        self._restore_state()

    def _build_ui(self):
        """Create 4-panel layout with real widgets."""
        # Main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setHandleWidth(6)  # bug #36: visible handles

        # Left vertical splitter (neuron map top, tree bottom)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setHandleWidth(6)

        # Right vertical splitter (terminal top, detail bottom)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(6)

        # Real widgets (lazy import to avoid circular deps)
        from muninn.ui.neuron_map import NeuronMapWidget
        from muninn.ui.tree_view import TreeViewWidget
        from muninn.ui.detail_panel import DetailPanel
        from muninn.ui.terminal import TerminalWidget

        self.neuron_panel = NeuronMapWidget()
        self.tree_panel = TreeViewWidget()
        self.detail_panel = DetailPanel()
        self.terminal_panel = TerminalWidget()

        # Search bar + forest toggle overlay above neuron map
        from muninn.ui.search import SearchBar
        from muninn.ui.forest import ForestToggle

        self._search_bar = SearchBar()
        self._forest_toggle = ForestToggle()

        neuron_container = QWidget()
        neuron_layout = QVBoxLayout(neuron_container)
        neuron_layout.setContentsMargins(0, 0, 0, 0)
        neuron_layout.setSpacing(0)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 2, 4, 2)
        toolbar_layout.setSpacing(4)
        toolbar_layout.addWidget(self._forest_toggle)
        toolbar_layout.addWidget(self._search_bar, 1)
        neuron_layout.addWidget(toolbar)
        neuron_layout.addWidget(self.neuron_panel, 1)

        self.left_splitter.addWidget(neuron_container)
        self.left_splitter.addWidget(self.tree_panel)

        self.right_splitter.addWidget(self.terminal_panel)
        self.right_splitter.addWidget(self.detail_panel)

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)

        self.setCentralWidget(self.main_splitter)

        # Navi fairy guide (B-UI-14/15) — overlay on neuron panel
        from muninn.ui.navi import NaviWidget
        self._navi = NaviWidget(self.neuron_panel)
        self._navi.scan_requested.connect(self._scan_folder_dialog)
        self._navi.raise_()  # Above neuron panel content
        self._navi.show()
        self._navi.show_first_launch()

        # Keep Navi sized to neuron panel
        self.neuron_panel.installEventFilter(self)

        # Command palette (overlay, initially hidden)
        from muninn.ui.command_palette import CommandPalette
        self._command_palette = CommandPalette(self)
        self._command_palette.hide()

        # About dialog (lazy)
        self._about_dialog = None

    def eventFilter(self, obj, event):
        """Resize Navi overlay when neuron panel resizes."""
        from PyQt6.QtCore import QEvent
        if obj is self.neuron_panel and event.type() == QEvent.Type.Resize:
            if hasattr(self, '_navi'):
                self._navi.setGeometry(self.neuron_panel.rect())
        return super().eventFilter(obj, event)

    def _wire_signals(self):
        """Cable signals between panels."""
        # Neuron selected -> update tree highlight + detail panel + status bar
        self.neuron_panel.neuron_selected.connect(self._on_neuron_selected)
        self.neuron_panel.neuron_deselected.connect(self._on_neuron_deselected)

        # Tree node selected -> select neuron in map (bidirectional B-UI-11)
        self.tree_panel.node_selected.connect(self._on_tree_node_selected)
        self.tree_panel.node_deselected.connect(self._on_neuron_deselected)

        # Detail panel neighbor click -> navigate to that neuron
        self.detail_panel.neighbor_clicked.connect(self._on_neighbor_navigate)

        # Layout events -> status bar
        self.neuron_panel.layout_started.connect(
            lambda: self.status_bar.showMessage("Computing layout...", 5000)
        )
        self.neuron_panel.layout_finished.connect(self._update_status)

    def _install_extras(self):
        """Install shortcuts, context menus, drag-drop, system tray (Phase 6-9)."""
        from muninn.ui.shortcuts import install_shortcuts
        from muninn.ui.context_menu import install_context_menu
        from muninn.ui.drag_drop import install_drag_drop

        install_shortcuts(self)
        install_context_menu(self.neuron_panel, "neuron", self)
        install_context_menu(self.tree_panel, "tree", self)
        install_context_menu(self.terminal_panel, "terminal")
        install_context_menu(self.detail_panel, "detail")
        install_drag_drop(self.neuron_panel, self)

        # Search bar wiring
        self._search_bar.search_changed.connect(self._on_search_changed)
        self._search_bar.search_confirmed.connect(self._on_search_confirmed)
        self._search_bar.search_cleared.connect(self._on_search_cleared)

        # Forest toggle wiring
        self._forest_toggle.mode_changed.connect(self._on_mode_changed)

        # Command palette wiring
        self._command_palette.action_selected.connect(self._on_palette_action)

        # System tray
        try:
            from muninn.ui.system_tray import MuninnTray
            self._tray = MuninnTray(self)
            self._tray.show()
        except Exception:
            self._tray = None

    def _on_search_changed(self, matched_ids):
        """Highlight matched neurons from search."""
        self.neuron_panel._search_matches = matched_ids
        self.neuron_panel.update()

    def _on_search_confirmed(self, text):
        """Zoom to first matched neuron."""
        for n in self.neuron_panel.neurons:
            if text.lower() in n.label.lower() or text.lower() in n.id.lower():
                self.neuron_panel._handle_neuron_click(n, Qt.KeyboardModifier.NoModifier)
                break

    def _on_search_cleared(self):
        """Clear search highlights."""
        self.neuron_panel._search_matches = set()
        self.neuron_panel.update()

    def _on_mode_changed(self, mode):
        """Handle solo/forest toggle."""
        self.status_mode.setText(mode.upper())
        if mode == "forest":
            self._load_forest()
        else:
            # Back to solo: reload current scan
            pass

    def _load_forest(self):
        """Load meta-mycelium into neuron map (B-UI-17)."""
        from pathlib import Path
        meta_path = Path.home() / ".muninn" / "meta_mycelium.db"
        if not meta_path.exists():
            if hasattr(self, '_navi'):
                self._navi.show_context_help("no_forest")
            return

        from muninn.ui.forest import MetaMyceliumWorker
        from PyQt6.QtCore import QThread

        self._forest_thread = QThread()
        self._forest_worker = MetaMyceliumWorker(str(meta_path))
        self._forest_worker.moveToThread(self._forest_thread)
        self._forest_thread.started.connect(self._forest_worker.run)
        self._forest_worker.finished.connect(self._on_forest_loaded)
        self._forest_worker.error.connect(
            lambda msg: self.status_bar.showMessage(f"Forest: {msg}", 5000)
        )
        self.register_worker("forest", self._forest_worker, self._forest_thread)
        self._forest_thread.start()

    def _on_forest_loaded(self, results):
        """Handle forest data loaded from meta-mycelium."""
        if not results:
            self.status_bar.showMessage("Forest: no data found", 3000)
            return
        self.status_bar.showMessage(f"Forest: {len(results)} concepts loaded", 3000)
        # Notify tray if available
        if self._tray:
            self._tray.notify("Muninn", f"Forest loaded: {len(results)} concepts")

    def _on_palette_action(self, callback_name):
        """Execute command palette action."""
        actions = {
            "zoom_to_fit": lambda: self.neuron_panel._zoom_to_fit_animated(),
            "toggle_mode": lambda: self._forest_toggle.toggle(),
            "focus_search": lambda: self._search_bar.focus_input(),
            "clear_terminal": lambda: self.terminal_panel._output.clear(),
            "export_screenshot": lambda: self._export_panel_screenshot(),
            "focus_neuron": lambda: self.neuron_panel.setFocus(),
            "focus_terminal": lambda: self.terminal_panel.setFocus(),
            "focus_tree": lambda: self.tree_panel.setFocus(),
            "focus_detail": lambda: self.detail_panel.setFocus(),
            "fullscreen": lambda: self._toggle_fullscreen(),
            "deselect": lambda: self._deselect_all(),
            "scan_repo": lambda: self._scan_folder_dialog(),
        }
        fn = actions.get(callback_name)
        if fn:
            fn()

    def _export_panel_screenshot(self):
        """Export focused panel as PNG."""
        from PyQt6.QtWidgets import QFileDialog
        focused = self.focusWidget()
        for panel in [self.neuron_panel, self.terminal_panel, self.tree_panel, self.detail_panel]:
            if panel is focused or panel.isAncestorOf(focused):
                pixmap = panel.grab()
                path, _ = QFileDialog.getSaveFileName(self, "Export", "", "PNG (*.png)")
                if path:
                    pixmap.save(path)
                return

    def _toggle_fullscreen(self):
        """Toggle fullscreen on focused panel."""
        pass  # Requires layout gymnastics — placeholder

    def _deselect_all(self):
        """Deselect all neurons."""
        if hasattr(self.neuron_panel, '_selected'):
            self.neuron_panel._selected.clear()
            self.neuron_panel.update()

    def _scan_folder_dialog(self):
        """Open folder dialog to scan a repo."""
        from PyQt6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select repo folder")
        if folder:
            self._scan_folder(folder)

    def _scan_folder(self, path: str):
        """Scan a folder and load results (B-UI-22)."""
        import subprocess
        import sys
        import tempfile
        import json

        self.status_bar.showMessage(f"Scanning {path}...", 10000)
        try:
            # Run muninn scan and capture JSON output
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                [sys.executable, "-m", "muninn", "scan", path, "--output", tmp_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                from pathlib import Path
                if Path(tmp_path).exists():
                    self.load_scan(tmp_path)
                    self.status_bar.showMessage(f"Loaded: {path}", 3000)
                    if self._tray:
                        self._tray.notify("Muninn", f"Scan complete: {path}")
            else:
                self.status_bar.showMessage(f"Scan failed: {result.stderr[:80]}", 5000)
        except Exception as e:
            self.status_bar.showMessage(f"Scan error: {e}", 5000)

    def _on_neuron_selected(self, neuron):
        """Handle neuron selection from map."""
        # Update tree highlight (B-UI-11)
        neighbors = self.neuron_panel._neighbor_cache.get(
            self._neuron_index(neuron), set()
        )
        secondary_ids = set()
        for idx in neighbors:
            if idx < len(self.neuron_panel.neurons):
                secondary_ids.add(self.neuron_panel.neurons[idx].id)
        self.tree_panel.highlight_concept(neuron.id, secondary_ids)

        # Update detail panel (B-UI-12/13)
        self.detail_panel.show_neuron({
            "label": neuron.label,
            "id": neuron.id,
            "level": neuron.level,
            "status": neuron.status,
            "depth": neuron.depth,
            "confidence": neuron.confidence,
            "entry": neuron.entry,
            "degree": neuron.degree,
            "neighbors": self._get_neighbor_pairs(neuron),
            "files": [neuron.entry] if neuron.entry else [],
        })

        # Status bar
        self.status_neurons.setText(f"{len(self.neuron_panel.neurons)} neurons")

    def _on_neuron_deselected(self):
        """Handle deselection."""
        self.tree_panel.clear_highlight()
        self.detail_panel.show_empty()

    def _on_tree_node_selected(self, tree_node):
        """Handle tree node click -> select in neuron map (bidirectional)."""
        for i, n in enumerate(self.neuron_panel.neurons):
            if n.id == tree_node.id:
                self.neuron_panel._handle_neuron_click(
                    n, Qt.KeyboardModifier.NoModifier
                )
                break

    def _on_neighbor_navigate(self, concept_name: str):
        """Navigate to a neighbor concept."""
        for i, n in enumerate(self.neuron_panel.neurons):
            if n.label == concept_name or n.id == concept_name:
                self.neuron_panel._handle_neuron_click(
                    n, Qt.KeyboardModifier.NoModifier
                )
                break

    def _neuron_index(self, neuron):
        """Find index of neuron in list."""
        for i, n in enumerate(self.neuron_panel.neurons):
            if n is neuron:
                return i
        return -1

    def _get_neighbor_pairs(self, neuron):
        """Get top 5 neighbor (name, degree) pairs."""
        idx = self._neuron_index(neuron)
        if idx < 0:
            return []
        neighbor_indices = self.neuron_panel._neighbor_cache.get(idx, set())
        pairs = []
        for j in sorted(neighbor_indices):
            if j < len(self.neuron_panel.neurons):
                nb = self.neuron_panel.neurons[j]
                pairs.append((nb.label, nb.degree))
        return sorted(pairs, key=lambda p: p[1], reverse=True)[:5]

    def _update_status(self):
        """Update status bar info."""
        n = len(self.neuron_panel.neurons)
        self.status_neurons.setText(f"{n} neurons")
        self.status_zoom.setText(f"{int(self.neuron_panel.zoom_level * 100)}%")

    # --- Data loading ---

    def load_scan(self, scan_path):
        """Load a scan file into the neuron map + tree view."""
        from pathlib import Path
        import json

        path = Path(scan_path)
        if not path.exists():
            return

        self.neuron_panel.load_scan(path)

        # Load tree from same scan data
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        family = data.get("family", "feuillu")
        from muninn.ui.classifier import classify_repo
        if not family or family == "unknown":
            family = classify_repo(data).get("family", "feuillu")

        self.tree_panel.load_tree(family, data)
        self.status_repo.setText(data.get("name", path.stem))
        self._update_status()

        # Feed search bar with neuron list (B-UI-25)
        self._search_bar.set_neurons(self.neuron_panel.neurons)

        # Navi: scan complete -> advance tutorial
        if hasattr(self, '_navi'):
            self._navi.on_scan_complete()

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
        # Cancel neuron map Laplacian if running
        self.neuron_panel._cancel_laplacian()
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

    # Load scan from CLI arg if provided
    if len(sys.argv) > 1:
        scan_path = sys.argv[1]
        QTimer.singleShot(100, lambda: window.load_scan(scan_path))

    ret = app.exec()
    del window  # explicit destruction order (R7)
    del app
    sys.exit(ret)


if __name__ == "__main__":
    main()
