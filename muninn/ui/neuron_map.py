"""Muninn UI — Neuron Map Widget.

B-UI-02: Static points from scan JSON.
B-UI-03: Laplacian spectral layout (QThread).
B-UI-04: Zoom + drag.
B-UI-05: Hover + tooltip + dimming.
B-UI-06: Selection.
B-UI-07: Edges.

Rules: R1 (ownership), R5 (repaint throttle), R6 (paint perf), R11 (AA),
R15 (mouse throttle), bug #39b (min size), bug #39d (pan bounds),
bug #39e (elided text).
"""

import json
import math
import time
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontMetrics,
    QPolygonF, QPainterPath,
)
from PyQt6.QtWidgets import QWidget, QToolTip

from muninn.ui.theme import (
    BG_0DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_DISABLED, FONT_BODY, FONT_CODE,
)


@dataclass
class Neuron:
    """A single neuron (concept/node) on the map."""
    id: str
    label: str
    level: str = ""
    status: str = ""
    entry: str = ""
    confidence: int = 0
    depth: int = 0
    depends: list = field(default_factory=list)
    # Layout position (set by Laplacian or random)
    x: float = 0.0
    y: float = 0.0
    # Computed
    degree: int = 0
    category: str = ""  # for shape: R=circle, F=diamond, I=triangle, B=square


# Shape constants for daltonism support (bug #38 in UX rules)
SHAPE_CIRCLE = "circle"
SHAPE_DIAMOND = "diamond"
SHAPE_TRIANGLE = "triangle"
SHAPE_SQUARE = "square"

LEVEL_SHAPES = {
    "R": SHAPE_CIRCLE,    # Root/runtime
    "F": SHAPE_DIAMOND,   # Feature
    "I": SHAPE_TRIANGLE,  # Infrastructure
    "B": SHAPE_SQUARE,    # Build
}

STATUS_COLORS = {
    "done": QColor(ACCENT_GREEN),
    "wip": QColor("#F59E0B"),
    "todo": QColor("#EF4444"),
    "skip": QColor(128, 128, 128),
}


class NeuronMapWidget(QWidget):
    """Custom QPainter widget displaying neurons as colored points.

    Supports: static points (B-UI-02), zoom/drag (B-UI-04), hover (B-UI-05),
    selection (B-UI-06), edges (B-UI-07).
    """

    # Signals
    neuron_hovered = pyqtSignal(object)   # Neuron or None
    neuron_selected = pyqtSignal(object)  # Neuron or None
    neuron_deselected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Neuron Map")
        self.setAccessibleDescription("Interactive map of code concepts and their connections")

        # Data
        self._neurons: list[Neuron] = []
        self._edges: list[tuple[int, int, float]] = []  # (idx_a, idx_b, weight)

        # View transform
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

        # Interaction state
        self._hovered: Optional[Neuron] = None
        self._selected: set[int] = set()  # indices into _neurons
        self._dragging = False
        self._drag_start = QPointF()
        self._pan_start_x = 0.0
        self._pan_start_y = 0.0

        # Rectangle selection
        self._rect_selecting = False
        self._rect_start = QPointF()
        self._rect_end = QPointF()

        # Selection history (B-UI-06)
        self._selection_history: list[set[int]] = []
        self._history_pos = -1

        # R5: repaint throttle
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(16)  # 60fps max
        self._repaint_timer.timeout.connect(self.update)

        # R15: mouse throttle
        self._last_hover_time = 0.0

        # R6: cache
        self._cache_dirty = True

        # R11: AA toggle during pan
        self._aa_enabled = True

        # KD-tree (built on demand, B-UI-05)
        self._kdtree = None

        # Empty state
        self._empty = True

    # --- Data loading ---

    def load_scan(self, scan_path: str | Path):
        """Load neurons from a scan JSON file."""
        path = Path(scan_path)
        if not path.exists():
            self._neurons = []
            self._empty = True
            self._cache_dirty = True
            self.update()
            return

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        nodes = data.get("nodes", [])
        if not nodes:
            self._neurons = []
            self._empty = True
            self._cache_dirty = True
            self.update()
            return

        self._neurons = []
        for n in nodes:
            neuron = Neuron(
                id=n.get("id", ""),
                label=n.get("label", n.get("id", "")),
                level=n.get("level", ""),
                status=n.get("status", ""),
                entry=n.get("entry", ""),
                confidence=n.get("confidence", 0),
                depth=n.get("depth", 0),
                depends=n.get("depends", []),
            )
            neuron.category = LEVEL_SHAPES.get(neuron.level, SHAPE_CIRCLE)
            self._neurons.append(neuron)

        # Build edges from depends
        self._build_edges()

        # Compute degrees
        for n in self._neurons:
            n.degree = 0
        for ia, ib, w in self._edges:
            self._neurons[ia].degree += 1
            self._neurons[ib].degree += 1

        # Initial layout: random positions (replaced by Laplacian in B-UI-03)
        self._layout_random()

        self._empty = False
        self._cache_dirty = True
        self._kdtree = None
        self._selected.clear()
        self._selection_history.clear()
        self._history_pos = -1
        self.update()

    def load_neurons(self, neurons: list[Neuron]):
        """Load neurons directly (for testing or programmatic use)."""
        self._neurons = neurons
        self._empty = len(neurons) == 0
        if not self._empty:
            self._layout_random()
        self._cache_dirty = True
        self._kdtree = None
        self._selected.clear()
        self.update()

    def _build_edges(self):
        """Build edge list from node depends."""
        id_to_idx = {n.id: i for i, n in enumerate(self._neurons)}
        self._edges = []
        seen = set()
        for i, n in enumerate(self._neurons):
            for dep_id in n.depends:
                j = id_to_idx.get(dep_id)
                if j is not None:
                    key = (min(i, j), max(i, j))
                    if key not in seen:
                        seen.add(key)
                        self._edges.append((key[0], key[1], 1.0))

    def _layout_random(self):
        """Assign random positions in [0.1, 0.9] normalized space."""
        rng = random.Random(42)  # deterministic
        w, h = self.width() or 400, self.height() or 400
        margin = 0.1
        for n in self._neurons:
            n.x = (margin + rng.random() * (1 - 2 * margin)) * w
            n.y = (margin + rng.random() * (1 - 2 * margin)) * h

    # --- Coordinate transforms ---

    def _world_to_screen(self, wx: float, wy: float) -> QPointF:
        """Convert world coords to screen coords."""
        sx = (wx - self._pan_x) * self._zoom + self.width() / 2
        sy = (wy - self._pan_y) * self._zoom + self.height() / 2
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen coords to world coords."""
        wx = (sx - self.width() / 2) / self._zoom + self._pan_x
        wy = (sy - self.height() / 2) / self._zoom + self._pan_y
        return wx, wy

    # --- Paint ---

    def paintEvent(self, event):
        p = QPainter(self)
        if self._aa_enabled:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), QColor(BG_0DP))

        if self._empty:
            self._paint_empty(p)
            p.end()
            return

        # Draw edges (B-UI-07, simplified here)
        self._paint_edges(p)

        # Draw neurons
        self._paint_neurons(p)

        # Rectangle selection overlay
        if self._rect_selecting:
            p.setPen(QPen(QColor(ACCENT_CYAN_HEX), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(0, 220, 255, 30))
            r = QRectF(self._rect_start, self._rect_end).normalized()
            p.drawRect(r)

        p.end()

    def _paint_empty(self, p: QPainter):
        """Draw empty state message."""
        p.setPen(QColor(TEXT_SECONDARY))
        font = QFont(FONT_BODY, 16)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "No data loaded.\nScan a repo first!")

    def _paint_neurons(self, p: QPainter):
        """Draw all neuron points with shapes based on category."""
        radius = max(4, 6 * self._zoom)
        font = QFont(FONT_BODY, max(8, int(10 * self._zoom)))
        fm = QFontMetrics(font)
        p.setFont(font)

        for i, n in enumerate(self._neurons):
            sp = self._world_to_screen(n.x, n.y)

            # Dimming: if something is hovered, dim non-neighbors
            alpha = 255
            if self._hovered and n is not self._hovered:
                if not self._is_neighbor(n, self._hovered):
                    alpha = 51  # 20%

            color = STATUS_COLORS.get(n.status, QColor(ACCENT_GREEN))
            color = QColor(color)
            color.setAlpha(alpha)

            # Selected: halo
            if i in self._selected:
                halo_color = QColor(ACCENT_CYAN_HEX)
                halo_color.setAlpha(alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(halo_color))
                p.drawEllipse(sp, radius * 2, radius * 2)

            # Draw shape based on category
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            self._draw_shape(p, sp, radius, n.category)

            # Label (only if zoom > 0.5 and not too many neurons)
            if self._zoom > 0.5 and len(self._neurons) < 200:
                label_color = QColor(TEXT_PRIMARY)
                label_color.setAlpha(alpha)
                p.setPen(label_color)
                max_w = int(80 * self._zoom)
                elided = fm.elidedText(n.label, Qt.TextElideMode.ElideRight, max_w)
                p.drawText(QPointF(sp.x() + radius + 4, sp.y() + 4), elided)

    def _draw_shape(self, p: QPainter, center: QPointF, r: float, shape: str):
        """Draw a neuron shape at center with radius r."""
        cx, cy = center.x(), center.y()
        if shape == SHAPE_DIAMOND:
            path = QPainterPath()
            path.moveTo(cx, cy - r)
            path.lineTo(cx + r, cy)
            path.lineTo(cx, cy + r)
            path.lineTo(cx - r, cy)
            path.closeSubpath()
            p.drawPath(path)
        elif shape == SHAPE_TRIANGLE:
            path = QPainterPath()
            path.moveTo(cx, cy - r)
            path.lineTo(cx + r, cy + r * 0.7)
            path.lineTo(cx - r, cy + r * 0.7)
            path.closeSubpath()
            p.drawPath(path)
        elif shape == SHAPE_SQUARE:
            p.drawRect(QRectF(cx - r * 0.7, cy - r * 0.7, r * 1.4, r * 1.4))
        else:  # circle (default)
            p.drawEllipse(center, r, r)

    def _paint_edges(self, p: QPainter):
        """Draw edges between connected neurons."""
        if not self._edges:
            return
        pen = QPen(QColor(255, 255, 255, 38), max(1, self._zoom))
        p.setPen(pen)

        for ia, ib, w in self._edges:
            if ia >= len(self._neurons) or ib >= len(self._neurons):
                continue
            na, nb = self._neurons[ia], self._neurons[ib]
            sa = self._world_to_screen(na.x, na.y)
            sb = self._world_to_screen(nb.x, nb.y)
            p.drawLine(sa, sb)

    def _is_neighbor(self, a: Neuron, b: Neuron) -> bool:
        """Check if two neurons are connected."""
        ia = self._neurons.index(a) if a in self._neurons else -1
        ib = self._neurons.index(b) if b in self._neurons else -1
        if ia < 0 or ib < 0:
            return False
        key = (min(ia, ib), max(ia, ib))
        return any((ea, eb) == key for ea, eb, _ in self._edges)

    # --- Zoom + Drag (B-UI-04) ---

    def wheelEvent(self, event):
        """Zoom centered on cursor position."""
        pos = event.position()
        old_wx, old_wy = self._screen_to_world(pos.x(), pos.y())

        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        new_zoom = self._zoom * factor
        new_zoom = max(0.1, min(20.0, new_zoom))  # Clamp
        self._zoom = new_zoom

        # Adjust pan so cursor stays on same world point
        new_wx, new_wy = self._screen_to_world(pos.x(), pos.y())
        self._pan_x -= (new_wx - old_wx)
        self._pan_y -= (new_wy - old_wy)

        self._clamp_pan()
        self._cache_dirty = True
        self._schedule_repaint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicking on a neuron
            hit = self._hit_test(event.position())
            if hit is not None:
                self._handle_neuron_click(hit, event.modifiers())
            else:
                # Start drag or rect select
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._rect_selecting = True
                    self._rect_start = event.position()
                    self._rect_end = event.position()
                else:
                    self._dragging = True
                    self._drag_start = event.position()
                    self._pan_start_x = self._pan_x
                    self._pan_start_y = self._pan_y
                    self._aa_enabled = False  # R11

    def mouseMoveEvent(self, event):
        # R15: throttle
        now = time.monotonic()
        if now - self._last_hover_time < 0.008:
            return
        self._last_hover_time = now

        if self._dragging:
            dx = (event.position().x() - self._drag_start.x()) / self._zoom
            dy = (event.position().y() - self._drag_start.y()) / self._zoom
            self._pan_x = self._pan_start_x - dx
            self._pan_y = self._pan_start_y - dy
            self._clamp_pan()
            self._cache_dirty = True
            self._schedule_repaint()
        elif self._rect_selecting:
            self._rect_end = event.position()
            self._schedule_repaint()
        else:
            # Hover detection
            hit = self._hit_test(event.position())
            if hit != self._hovered:
                self._hovered = hit
                self.neuron_hovered.emit(hit)
                self._schedule_repaint()

                # Tooltip
                if hit:
                    neighbors = self._get_neighbor_labels(hit, 3)
                    tip = f"<b>{hit.label}</b><br>Degree: {hit.degree}"
                    if neighbors:
                        tip += "<br>Neighbors: " + ", ".join(neighbors)
                    QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                else:
                    QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                self._aa_enabled = True  # R11
                self._cache_dirty = True
                self.update()
            elif self._rect_selecting:
                self._rect_selecting = False
                self._select_in_rect()
                self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click: reset view or open file."""
        hit = self._hit_test(event.position())
        if hit and hit.entry:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(hit.entry))
        elif hit is None:
            # Reset zoom/pan
            self._zoom = 1.0
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._cache_dirty = True
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_to_fit()
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._copy_selection()
        elif event.key() == Qt.Key.Key_Left and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._history_back()
        elif event.key() == Qt.Key.Key_Right and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._history_forward()

    # --- Hit testing ---

    def _hit_test(self, screen_pos: QPointF) -> Optional[Neuron]:
        """Find neuron under screen position. O(n) for now, KD-tree in B-UI-05."""
        if not self._neurons:
            return None
        hit_radius = max(8, 10 * self._zoom)
        best = None
        best_dist = float("inf")
        for n in self._neurons:
            sp = self._world_to_screen(n.x, n.y)
            dx = screen_pos.x() - sp.x()
            dy = screen_pos.y() - sp.y()
            dist = math.hypot(dx, dy)
            if dist < hit_radius and dist < best_dist:
                best = n
                best_dist = dist
        return best

    def _get_neighbor_labels(self, neuron: Neuron, max_n: int = 3) -> list[str]:
        """Get labels of neighbors of a neuron."""
        idx = self._neurons.index(neuron) if neuron in self._neurons else -1
        if idx < 0:
            return []
        neighbors = []
        for ia, ib, _ in self._edges:
            if ia == idx and ib < len(self._neurons):
                neighbors.append(self._neurons[ib].label)
            elif ib == idx and ia < len(self._neurons):
                neighbors.append(self._neurons[ia].label)
        return neighbors[:max_n]

    # --- Selection (B-UI-06) ---

    def _handle_neuron_click(self, neuron: Neuron, modifiers):
        """Handle click on a neuron."""
        idx = self._neurons.index(neuron)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Multi-select
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)
        else:
            if idx in self._selected and len(self._selected) == 1:
                # Deselect
                self._selected.clear()
                self.neuron_deselected.emit()
            else:
                self._selected = {idx}
                self.neuron_selected.emit(neuron)

        self._push_history()
        self._cache_dirty = True
        self.update()

    def _select_in_rect(self):
        """Select all neurons inside the selection rectangle."""
        r = QRectF(self._rect_start, self._rect_end).normalized()
        self._selected.clear()
        for i, n in enumerate(self._neurons):
            sp = self._world_to_screen(n.x, n.y)
            if r.contains(sp):
                self._selected.add(i)
        if self._selected:
            self._push_history()
            first = self._neurons[next(iter(self._selected))]
            self.neuron_selected.emit(first)
        else:
            self.neuron_deselected.emit()

    def _push_history(self):
        """Push current selection to history stack."""
        # Truncate forward history
        self._selection_history = self._selection_history[:self._history_pos + 1]
        self._selection_history.append(set(self._selected))
        self._history_pos = len(self._selection_history) - 1

    def _history_back(self):
        if self._history_pos > 0:
            self._history_pos -= 1
            self._selected = set(self._selection_history[self._history_pos])
            self._cache_dirty = True
            self.update()

    def _history_forward(self):
        if self._history_pos < len(self._selection_history) - 1:
            self._history_pos += 1
            self._selected = set(self._selection_history[self._history_pos])
            self._cache_dirty = True
            self.update()

    # --- Clipboard (R9) ---

    def _copy_selection(self):
        """Copy selected neuron names to clipboard (R9 retry loop)."""
        if not self._selected:
            return
        names = [self._neurons[i].label for i in sorted(self._selected)]
        text = "\n".join(names)
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QThread
        cb = QApplication.clipboard()
        for _ in range(5):
            cb.setText(text)
            if cb.text() == text:
                return
            QThread.msleep(50)

    # --- View helpers ---

    def _zoom_to_fit(self):
        """Zoom to show all neurons (Ctrl+0)."""
        if not self._neurons:
            return
        xs = [n.x for n in self._neurons]
        ys = [n.y for n in self._neurons]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        dx = max_x - min_x or 1
        dy = max_y - min_y or 1
        self._pan_x = (min_x + max_x) / 2
        self._pan_y = (min_y + max_y) / 2
        self._zoom = min(self.width() / (dx * 1.2), self.height() / (dy * 1.2))
        self._zoom = max(0.1, min(20.0, self._zoom))
        self._cache_dirty = True
        self.update()

    def _clamp_pan(self):
        """Clamp pan to bounding box + 20% margin (bug #39d)."""
        if not self._neurons:
            return
        xs = [n.x for n in self._neurons]
        ys = [n.y for n in self._neurons]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        margin_x = (max_x - min_x) * 0.2 + 100
        margin_y = (max_y - min_y) * 0.2 + 100
        self._pan_x = max(min_x - margin_x, min(max_x + margin_x, self._pan_x))
        self._pan_y = max(min_y - margin_y, min(max_y + margin_y, self._pan_y))

    def _schedule_repaint(self):
        """R5: throttled repaint."""
        if not self._repaint_timer.isActive():
            self._repaint_timer.start()

    # --- Public accessors ---

    @property
    def neurons(self) -> list[Neuron]:
        return self._neurons

    @property
    def selected_neurons(self) -> list[Neuron]:
        return [self._neurons[i] for i in sorted(self._selected) if i < len(self._neurons)]

    @property
    def zoom_level(self) -> float:
        return self._zoom
