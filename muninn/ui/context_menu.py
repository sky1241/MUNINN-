"""Muninn UI — Context menus.

B-UI-27: Right-click menus for neuron map, tree view, terminal.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget, QApplication


def install_context_menu(widget: QWidget, menu_type: str, window=None):
    """Install a context menu on a widget.

    Args:
        widget: target widget
        menu_type: "neuron", "tree", "terminal", "detail"
        window: MainWindow reference for cross-panel actions
    """
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    widget.customContextMenuRequested.connect(
        lambda pos: _show_menu(widget, pos, menu_type, window)
    )


def _show_menu(widget, pos, menu_type, window):
    """Build and show the context menu."""
    menu = QMenu(widget)
    menu.setStyleSheet(
        "QMenu { background: #1E1E1E; color: #E0E0E0; border: 1px solid rgba(255,255,255,0.1); "
        "border-radius: 8px; padding: 4px; } "
        "QMenu::item:selected { background: rgba(0,220,255,0.2); }"
    )

    if menu_type == "neuron":
        _build_neuron_menu(menu, widget, window)
    elif menu_type == "tree":
        _build_tree_menu(menu, widget, window)
    elif menu_type == "terminal":
        _build_terminal_menu(menu, widget)
    elif menu_type == "detail":
        _build_detail_menu(menu, widget)

    if menu.actions():
        menu.exec(widget.mapToGlobal(pos))


def _build_neuron_menu(menu, widget, window):
    """Context menu for neuron map."""
    if hasattr(widget, 'selected_neurons') and widget.selected_neurons:
        neurons = widget.selected_neurons
        name = neurons[0].label if len(neurons) == 1 else f"{len(neurons)} neurons"

        act_copy = QAction(f"Copy '{name}'", menu)
        act_copy.triggered.connect(lambda: _copy_text(
            ", ".join(n.label for n in neurons)
        ))
        menu.addAction(act_copy)

        if len(neurons) == 1 and window:
            act_tree = QAction("View in tree", menu)
            act_tree.triggered.connect(
                lambda: window.tree_panel.highlight_concept(neurons[0].id)
            )
            menu.addAction(act_tree)

            if neurons[0].entry:
                act_open = QAction("Open source file", menu)
                act_open.triggered.connect(
                    lambda: _open_file(neurons[0].entry)
                )
                menu.addAction(act_open)

    act_fit = QAction("Zoom to fit (Ctrl+0)", menu)
    act_fit.triggered.connect(lambda: widget._zoom_to_fit_animated())
    menu.addAction(act_fit)


def _build_tree_menu(menu, widget, window):
    """Context menu for tree view."""
    node = widget.selected_node
    if node:
        act_copy = QAction(f"Copy '{node.label}'", menu)
        act_copy.triggered.connect(lambda: _copy_text(node.label))
        menu.addAction(act_copy)

        if node.entry:
            act_open = QAction("Open file", menu)
            act_open.triggered.connect(lambda: _open_file(node.entry))
            menu.addAction(act_open)

            act_path = QAction("Copy path", menu)
            act_path.triggered.connect(lambda: _copy_text(node.entry))
            menu.addAction(act_path)


def _build_terminal_menu(menu, widget):
    """Context menu for terminal."""
    act_copy = QAction("Copy", menu)
    act_copy.triggered.connect(lambda: _copy_text(widget._output.textCursor().selectedText()))
    menu.addAction(act_copy)

    act_clear = QAction("Clear", menu)
    act_clear.triggered.connect(lambda: widget._output.clear())
    menu.addAction(act_clear)


def _build_detail_menu(menu, widget):
    """Context menu for detail panel."""
    title = widget._title.text()
    if title:
        act_copy = QAction(f"Copy '{title}'", menu)
        act_copy.triggered.connect(lambda: _copy_text(title))
        menu.addAction(act_copy)


def _copy_text(text: str):
    """Copy text to clipboard (R9 retry)."""
    cb = QApplication.clipboard()
    for _ in range(5):
        try:
            cb.setText(text)
            if cb.text() == text:
                return
        except Exception:
            pass
        import time
        time.sleep(0.05)


def _open_file(path: str):
    """Open file in default editor."""
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtCore import QUrl
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
