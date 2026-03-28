"""Muninn UI — Botanical Tree View Widget.

B-UI-08: Placeholder image (QPixmap lazy loaded).
B-UI-10: QPainter native rendering with clickable nodes.
B-UI-11: Bidirectional highlight (neuron map <-> tree).

Rules: R1 (ownership), R5 (repaint throttle), R6 (cache QPixmap, HiDPI),
R8 (empty state), bug #5 (lazy QPixmap), bug #39e (elided text).
"""

import json
import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontMetrics,
    QPixmap, QPainterPath,
)
from PyQt6.QtWidgets import QWidget

from muninn.ui.theme import (
    BG_0DP, BG_1DP, ACCENT_CYAN_HEX, ACCENT_GREEN, SUCCESS, WARNING, ERROR,
    TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_TITLE,
)
from muninn.ui import _TEMPLATES_DIR


# Node status -> glow ring color
GLOW_COLORS = {
    "done": QColor(SUCCESS),
    "wip": QColor(WARNING),
    "todo": QColor(ERROR),
}


class TreeNode:
    """A node on the botanical tree."""
    __slots__ = ("id", "label", "status", "x", "y", "radius", "level", "depth", "entry")

    def __init__(self, id="", label="", status="", x=0.0, y=0.0,
                 radius=8.0, level="", depth=0, entry=""):
        self.id = id
        self.label = label
        self.status = status
        self.x = x
        self.y = y
        self.radius = radius
        self.level = level
        self.depth = depth
        self.entry = entry


class TreeViewWidget(QWidget):
    """Botanical tree rendered with QPainter.

    Shows a background template image with interactive nodes drawn on top.
    Supports click-to-select and bidirectional highlighting with neuron map.
    """

    # Signals
    node_selected = pyqtSignal(object)    # TreeNode
    node_deselected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Botanical Tree")
        self.setAccessibleDescription("Visual tree representation of project structure")

        # Data
        self._nodes: list[TreeNode] = []
        self._family: str = ""
        self._bg_pixmap: Optional[QPixmap] = None  # Lazy loaded (bug #5)

        # Highlight state (B-UI-11)
        self._highlighted_id: Optional[str] = None
        self._secondary_ids: set[str] = set()
        self._selected_id: Optional[str] = None

        # R5: repaint throttle
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(16)
        self._repaint_timer.timeout.connect(self.update)

        # State
        self._empty = True

    # --- Data loading ---

    def load_tree(self, family: str, scan_data: dict, positions: Optional[list] = None):
        """Load tree nodes from scan data with optional position file.

        Args:
            family: botanical family name (feuillu, conifere, etc.)
            scan_data: scan JSON dict with 'nodes'
            positions: optional list of (x, y) tuples for node placement
        """
        self._family = family
        nodes_data = scan_data.get("nodes", [])

        if not nodes_data:
            self._nodes = []
            self._empty = True
            self._bg_pixmap = None
            self.update()
            return

        # Load background template
        self._load_background(family)

        # Load positions from template file if not provided
        if positions is None:
            positions = self._load_positions(family, len(nodes_data))

        self._nodes = []
        for i, nd in enumerate(nodes_data):
            x, y = positions[i] if i < len(positions) else (0.5, 0.5)
            node = TreeNode(
                id=nd.get("id", ""),
                label=nd.get("label", nd.get("id", "")),
                status=nd.get("status", ""),
                x=x,
                y=y,
                level=nd.get("level", ""),
                depth=nd.get("depth", 0),
                entry=nd.get("entry", ""),
            )
            self._nodes.append(node)

        self._empty = False
        self._selected_id = None
        self._highlighted_id = None
        self._secondary_ids.clear()
        self.update()

    def _load_background(self, family: str):
        """Lazy load background QPixmap (bug #5)."""
        bg_path = _TEMPLATES_DIR / f"{family}_final.png"
        if bg_path.exists():
            self._bg_pixmap = QPixmap(str(bg_path))
        else:
            self._bg_pixmap = None

    def _load_positions(self, family: str, count: int) -> list[tuple[float, float]]:
        """Load node positions from template positions file."""
        pos_path = _TEMPLATES_DIR / f"{family}_positions_1024.txt"
        positions = []
        if pos_path.exists():
            with open(pos_path, encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            x = float(parts[0]) / 1024.0  # Normalize to [0, 1]
                            y = float(parts[1]) / 1024.0
                            positions.append((x, y))
                        except ValueError:
                            continue

        # Pad with defaults if not enough positions
        import random
        rng = random.Random(42)
        while len(positions) < count:
            positions.append((0.2 + rng.random() * 0.6, 0.2 + rng.random() * 0.6))

        return positions

    # --- Paint ---

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), QColor(BG_0DP))

        if self._empty:
            self._paint_empty(p)
            p.end()
            return

        # Background image
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)

        # Draw nodes
        self._paint_nodes(p)

        p.end()

    def _paint_empty(self, p: QPainter):
        """Empty state (R8)."""
        p.setPen(QColor(TEXT_SECONDARY))
        font = QFont(FONT_BODY, 16)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "No tree loaded.\nClassify a repo first!")

    def _paint_nodes(self, p: QPainter):
        """Draw tree nodes with glow rings based on status."""
        w, h = self.width(), self.height()
        font = QFont(FONT_BODY, 10)
        fm = QFontMetrics(font)
        p.setFont(font)

        for node in self._nodes:
            cx = node.x * w
            cy = node.y * h
            r = node.radius

            # Glow ring (status color)
            glow_color = GLOW_COLORS.get(node.status, QColor(128, 128, 128))

            # Highlight: primary = full halo, secondary = outline
            is_primary = (node.id == self._highlighted_id)
            is_secondary = (node.id in self._secondary_ids)
            is_selected = (node.id == self._selected_id)

            if is_primary or is_selected:
                # Full cyan halo
                halo = QColor(ACCENT_CYAN_HEX)
                halo.setAlpha(180)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(halo))
                p.drawEllipse(QPointF(cx, cy), r * 2.5, r * 2.5)

            if is_secondary:
                # Outline only
                p.setPen(QPen(QColor(ACCENT_CYAN_HEX), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r * 1.8, r * 1.8)

            # Glow ring
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow_color))
            p.drawEllipse(QPointF(cx, cy), r * 1.3, r * 1.3)

            # Inner node
            p.setBrush(QBrush(QColor(BG_1DP)))
            p.drawEllipse(QPointF(cx, cy), r, r)

            # Label
            p.setPen(QColor(TEXT_PRIMARY))
            max_w = int(min(80, w * 0.15))
            elided = fm.elidedText(node.label, Qt.TextElideMode.ElideRight, max_w)
            p.drawText(QPointF(cx + r + 4, cy + 4), elided)

    # --- Interaction ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.position())
            if hit:
                self._selected_id = hit.id
                self.node_selected.emit(hit)
            else:
                self._selected_id = None
                self.node_deselected.emit()
            self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click opens the source file."""
        hit = self._hit_test(event.position())
        if hit and hit.entry:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(hit.entry))

    def _hit_test(self, pos: QPointF) -> Optional[TreeNode]:
        """Find node at screen position."""
        w, h = self.width(), self.height()
        for node in self._nodes:
            cx = node.x * w
            cy = node.y * h
            dx = pos.x() - cx
            dy = pos.y() - cy
            if math.hypot(dx, dy) < node.radius * 2:
                return node
        return None

    # --- Bidirectional highlight (B-UI-11) ---

    def highlight_concept(self, concept_id: str, secondary_ids: Optional[set[str]] = None):
        """Highlight a concept (from neuron map selection).

        Args:
            concept_id: primary concept to highlight (full halo)
            secondary_ids: secondary concepts (outline only)
        """
        self._highlighted_id = concept_id
        self._secondary_ids = secondary_ids or set()
        self.update()

    def clear_highlight(self):
        """Remove all highlights."""
        self._highlighted_id = None
        self._secondary_ids.clear()
        self.update()

    # --- Public ---

    @property
    def nodes(self) -> list[TreeNode]:
        return self._nodes

    @property
    def family(self) -> str:
        return self._family

    @property
    def selected_node(self) -> Optional[TreeNode]:
        if self._selected_id:
            for n in self._nodes:
                if n.id == self._selected_id:
                    return n
        return None
