"""Muninn UI — Drag and drop support.

B-UI-28: Drop folder onto neuron map -> auto scan.
"""

from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget


def install_drag_drop(widget: QWidget, window=None):
    """Enable drag-and-drop on a widget (B-UI-28).

    Drop a folder -> triggers scan on that folder.
    """
    widget.setAcceptDrops(True)
    widget._dd_window = window

    # Store originals
    widget._orig_dragEnterEvent = widget.dragEnterEvent
    widget._orig_dropEvent = widget.dropEvent

    def drag_enter(event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def drop(event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    event.acceptProposedAction()
                    if widget._dd_window and hasattr(widget._dd_window, '_scan_folder'):
                        widget._dd_window._scan_folder(str(path))
                    return
        event.ignore()

    widget.dragEnterEvent = drag_enter
    widget.dropEvent = drop
