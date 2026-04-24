"""Muninn UI — Global keyboard shortcuts.

B-UI-26: Tab cycle panels, Escape, Ctrl+F search, Ctrl+1..4 focus panel,
Space toggle mode, F11 fullscreen panel, Ctrl+Shift+S export.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow


def install_shortcuts(window: QMainWindow):
    """Install all global shortcuts on the main window (B-UI-26)."""

    # Ctrl+F: focus search
    sc_search = QShortcut(QKeySequence("Ctrl+F"), window)
    sc_search.activated.connect(lambda: _focus_search(window))

    # Ctrl+1..4: focus panel
    for i, attr in enumerate(["neuron_panel", "terminal_panel", "tree_panel", "detail_panel"], 1):
        sc = QShortcut(QKeySequence(f"Ctrl+{i}"), window)
        panel = getattr(window, attr, None)
        if panel:
            sc.activated.connect(panel.setFocus)

    # Space: toggle solo/forest
    sc_space = QShortcut(QKeySequence(Qt.Key.Key_Space), window)
    sc_space.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    sc_space.activated.connect(lambda: _toggle_mode(window))

    # Escape: deselect / clear
    sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), window)
    sc_esc.activated.connect(lambda: _escape(window))

    # F11: fullscreen active panel
    sc_f11 = QShortcut(QKeySequence(Qt.Key.Key_F11), window)
    sc_f11.activated.connect(lambda: _toggle_fullscreen_panel(window))

    # Ctrl+Shift+S: export screenshot
    sc_export = QShortcut(QKeySequence("Ctrl+Shift+S"), window)
    sc_export.activated.connect(lambda: _export_screenshot(window))

    # Ctrl+Shift+P: command palette
    sc_palette = QShortcut(QKeySequence("Ctrl+Shift+P"), window)
    sc_palette.activated.connect(lambda: _show_command_palette(window))

    # Store shortcuts to prevent GC (R1)
    window._shortcuts = [sc_search, sc_space, sc_esc, sc_f11, sc_export, sc_palette]


def _focus_search(window):
    if hasattr(window, '_search_bar'):
        window._search_bar.focus_input()


def _toggle_mode(window):
    if hasattr(window, '_forest_toggle'):
        window._forest_toggle.toggle()


def _escape(window):
    if hasattr(window, 'neuron_panel'):
        window.neuron_panel._selected.clear()
        window.neuron_panel.neuron_deselected.emit()
        window.neuron_panel.update()


def _toggle_fullscreen_panel(window):
    """Toggle fullscreen on the focused panel."""
    if hasattr(window, '_fullscreen_panel') and window._fullscreen_panel:
        # Restore
        window._fullscreen_panel = None
        window.main_splitter.show()
        return

    focused = window.focusWidget()
    # Find which panel contains the focused widget
    for panel in [window.neuron_panel, window.terminal_panel,
                  window.tree_panel, window.detail_panel]:
        if panel is focused or panel.isAncestorOf(focused):
            window._fullscreen_panel = panel
            # TODO: maximize panel (requires layout gymnastics)
            break


def _export_screenshot(window):
    """Export active panel as PNG (B-UI-31)."""
    from PyQt6.QtWidgets import QFileDialog
    focused = window.focusWidget()
    if focused is None:
        focused = window.neuron_panel

    # Find parent panel
    for panel in [window.neuron_panel, window.terminal_panel,
                  window.tree_panel, window.detail_panel]:
        if panel is focused or panel.isAncestorOf(focused):
            pixmap = panel.grab()
            path, _ = QFileDialog.getSaveFileName(
                window, "Export Screenshot", "", "PNG (*.png);;All Files (*)"
            )
            if path:
                pixmap.save(path)
            return


def _show_command_palette(window):
    """Show command palette (B-UI-29)."""
    if hasattr(window, '_command_palette'):
        window._command_palette.show()
        window._command_palette.focus_input()
