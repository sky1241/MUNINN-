"""Muninn UI — Detail Panel Widget.

B-UI-12: Basic info (name, type, LOC, status) + empty state.
B-UI-13: Extended info (temperature, neighbors, files, click navigation).

Rules: R1 (ownership), R8 (empty state), bug #39e (elided text).
"""

from typing import Optional

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QGraphicsOpacityEffect,
)

from muninn.ui.theme import (
    BG_1DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_DISABLED, SUCCESS, WARNING, ERROR, FONT_TITLE, FONT_BODY, FONT_CODE,
)


class ClickableLabel(QLabel):
    """QLabel that emits clicked signal."""
    clicked = pyqtSignal(str)

    def __init__(self, text="", data="", parent=None):
        super().__init__(text, parent)
        self._data = data
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"color: {ACCENT_CYAN_HEX}; text-decoration: underline;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._data)


class DetailPanel(QWidget):
    """Panel showing detailed info about a selected neuron/tree node.

    B-UI-12: name, type, LOC, status + empty state with cross-fade.
    B-UI-13: temperature, neighbors (clickable), files (clickable).
    """

    # Signals
    neighbor_clicked = pyqtSignal(str)    # Navigate to this concept
    file_clicked = pyqtSignal(str)        # Open this file

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)

        # Opacity effect for cross-fade (B-UI-12)
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(200)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self._build_ui()
        self.show_empty()

    def _build_ui(self):
        """Build the detail panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        self._title = QLabel()
        self._title.setProperty("heading", True)
        self._title.setFont(QFont(FONT_TITLE, 16))
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        # Status badge
        self._status_label = QLabel()
        self._status_label.setFont(QFont(FONT_BODY, 14))
        layout.addWidget(self._status_label)

        # Basic info section (B-UI-12)
        self._info_frame = QFrame()
        info_layout = QVBoxLayout(self._info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        self._level_label = QLabel()
        self._loc_label = QLabel()  # B-UI-12: LOC field
        self._depth_label = QLabel()
        self._confidence_label = QLabel()
        self._entry_label = QLabel()
        self._entry_label.setFont(QFont(FONT_CODE, 11))

        for lbl in [self._level_label, self._loc_label, self._depth_label,
                     self._confidence_label, self._entry_label]:
            lbl.setFont(QFont(FONT_BODY, 13))
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
            info_layout.addWidget(lbl)

        layout.addWidget(self._info_frame)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: rgba(255,255,255,0.06);")
        layout.addWidget(sep)

        # Extended info section (B-UI-13)
        self._extended_frame = QFrame()
        ext_layout = QVBoxLayout(self._extended_frame)
        ext_layout.setContentsMargins(0, 0, 0, 0)
        ext_layout.setSpacing(8)

        # Temperature
        self._temp_label = QLabel()
        self._temp_label.setFont(QFont(FONT_BODY, 13))
        self._temp_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        ext_layout.addWidget(self._temp_label)

        # B-UI-13: Last modified
        self._last_modified_label = QLabel()
        self._last_modified_label.setFont(QFont(FONT_BODY, 13))
        self._last_modified_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        ext_layout.addWidget(self._last_modified_label)

        # B-UI-13: Zone
        self._zone_label = QLabel()
        self._zone_label.setFont(QFont(FONT_BODY, 13))
        self._zone_label.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        ext_layout.addWidget(self._zone_label)

        # Neighbors section
        neighbors_header = QLabel("Neighbors")
        neighbors_header.setFont(QFont(FONT_BODY, 14))
        neighbors_header.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600; background: transparent; border: none;")
        ext_layout.addWidget(neighbors_header)

        self._neighbors_container = QWidget()
        self._neighbors_layout = QVBoxLayout(self._neighbors_container)
        self._neighbors_layout.setContentsMargins(0, 0, 0, 0)
        self._neighbors_layout.setSpacing(4)
        ext_layout.addWidget(self._neighbors_container)

        # Files section
        files_header = QLabel("Files")
        files_header.setFont(QFont(FONT_BODY, 14))
        files_header.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600; background: transparent; border: none;")
        ext_layout.addWidget(files_header)

        self._files_container = QWidget()
        self._files_layout = QVBoxLayout(self._files_container)
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(4)
        ext_layout.addWidget(self._files_container)

        layout.addWidget(self._extended_frame)

        # Scroll support
        layout.addStretch()

        # Empty state overlay
        self._empty_label = QLabel("Click a neuron to see details")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {TEXT_DISABLED}; background: transparent; border: none;")
        self._empty_label.setFont(QFont(FONT_BODY, 14))
        layout.addWidget(self._empty_label)

    def show_empty(self):
        """Show empty state (R8)."""
        self._title.hide()
        self._status_label.hide()
        self._info_frame.hide()
        self._extended_frame.hide()
        self._empty_label.show()

    def show_neuron(self, neuron_data: dict):
        """Display info for a selected neuron.

        Args:
            neuron_data: dict with keys: label, id, level, status, depth,
                confidence, entry, degree, temperature, neighbors, files
        """
        # Cross-fade animation
        self._fade_anim.setStartValue(0.3)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

        self._empty_label.hide()
        self._title.show()
        self._status_label.show()
        self._info_frame.show()
        self._extended_frame.show()

        # B-UI-12: Basic info
        self._title.setText(neuron_data.get("label", "Unknown"))

        status = neuron_data.get("status", "")
        status_colors = {"done": SUCCESS, "wip": WARNING, "todo": ERROR}
        color = status_colors.get(status, TEXT_DISABLED)
        self._status_label.setText(f"Status: {status.upper() or 'N/A'}")
        self._status_label.setStyleSheet(
            f"color: {color}; font-weight: 600; background: transparent; border: none;"
        )

        self._level_label.setText(f"Level: {neuron_data.get('level', 'N/A')}")

        # B-UI-12: LOC field
        loc = neuron_data.get("loc")
        if loc is not None:
            self._loc_label.setText(f"LOC: {loc}")
            self._loc_label.show()
        else:
            self._loc_label.hide()

        self._depth_label.setText(f"Depth: {neuron_data.get('depth', 'N/A')}")
        self._confidence_label.setText(
            f"Confidence: {neuron_data.get('confidence', 'N/A')}%"
        )
        entry = neuron_data.get("entry", "")
        self._entry_label.setText(f"Entry: {entry or 'N/A'}")

        # B-UI-13: Extended info
        temp = neuron_data.get("temperature")
        if temp is not None:
            self._temp_label.setText(f"Temperature: {temp:.2f}")
            self._temp_label.show()
        else:
            self._temp_label.hide()

        # B-UI-13: Last modified
        last_mod = neuron_data.get("last_modified")
        if last_mod:
            self._last_modified_label.setText(f"Last modified: {last_mod}")
            self._last_modified_label.show()
        else:
            self._last_modified_label.hide()

        # B-UI-13: Zone
        zone = neuron_data.get("zone")
        if zone:
            self._zone_label.setText(f"Zone: {zone}")
            self._zone_label.show()
        else:
            self._zone_label.hide()

        # Clear and rebuild neighbors
        self._clear_layout(self._neighbors_layout)
        neighbors = neuron_data.get("neighbors", [])
        if neighbors:
            for name, count in neighbors[:5]:
                lbl = ClickableLabel(f"  {name} ({count})", data=name, parent=self)
                lbl.clicked.connect(self._on_neighbor_clicked)
                self._neighbors_layout.addWidget(lbl)
        else:
            no_neighbors = QLabel("  (none)")
            no_neighbors.setStyleSheet(f"color: {TEXT_DISABLED}; background: transparent; border: none;")
            self._neighbors_layout.addWidget(no_neighbors)

        # Clear and rebuild files
        self._clear_layout(self._files_layout)
        files = neuron_data.get("files", [])
        if files:
            for fpath in files:
                lbl = ClickableLabel(f"  {fpath}", data=fpath, parent=self)
                lbl.clicked.connect(self._on_file_clicked)
                self._files_layout.addWidget(lbl)
        else:
            no_files = QLabel("  (none)")
            no_files.setStyleSheet(f"color: {TEXT_DISABLED}; background: transparent; border: none;")
            self._files_layout.addWidget(no_files)

    def _on_neighbor_clicked(self, name: str):
        self.neighbor_clicked.emit(name)

    def _on_file_clicked(self, path: str):
        self.file_clicked.emit(path)
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _clear_layout(self, layout):
        """Remove all widgets from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
