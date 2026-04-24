"""Muninn UI — Neuron Map Widget.

B-UI-02: Static points from scan JSON.
B-UI-03: Laplacian spectral layout (QThread worker).
B-UI-04: Zoom + drag + animated zoom-to-fit (300ms).
B-UI-05: Hover + tooltip + dimming + KD-tree O(log n).
B-UI-06: Selection.
B-UI-07: Edges (bezier, batch, LOD, edge click).

Rules: R1 (ownership), R3 (worker pattern), R5 (repaint throttle),
R6 (paint perf), R11 (AA), R12 (cancel old worker),
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
    Qt, QPointF, QRectF, QLineF, QTimer, QThread, pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QFontMetrics,
    QPolygonF, QPainterPath,
)
from PyQt6.QtWidgets import QWidget, QToolTip

from muninn.ui.theme import (
    BG_0DP, BG_1DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
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
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    degree: int = 0
    category: str = ""
    temperature: float = 0.0  # CHUNK 3: from scan frequency ratio
    zone: str = ""  # CHUNK 3: from pattern type


# Shape constants for daltonism support
SHAPE_CIRCLE = "circle"
SHAPE_DIAMOND = "diamond"
SHAPE_TRIANGLE = "triangle"
SHAPE_SQUARE = "square"

LEVEL_SHAPES = {
    "R": SHAPE_CIRCLE,
    "F": SHAPE_DIAMOND,
    "I": SHAPE_TRIANGLE,
    "B": SHAPE_SQUARE,
    "cube": SHAPE_SQUARE,  # reconstruction-mode cubes render as squares
}

STATUS_COLORS = {
    "done": QColor(ACCENT_GREEN),
    "wip": QColor("#F59E0B"),
    "todo": QColor("#EF4444"),
    "skip": QColor(128, 128, 128),
}

# B-UI-03: Degree-based color gradient (green -> yellow -> red, 10 steps)
DEGREE_GRADIENT = [
    (0.0,   QColor(0, 180, 0)),       # green
    (0.11,  QColor(40, 200, 0)),      # green-lime
    (0.22,  QColor(100, 210, 0)),     # lime
    (0.33,  QColor(160, 220, 0)),     # lime-yellow
    (0.44,  QColor(210, 220, 0)),     # yellow-green
    (0.55,  QColor(240, 200, 0)),     # yellow
    (0.66,  QColor(250, 170, 0)),     # yellow-orange
    (0.77,  QColor(250, 120, 0)),     # orange
    (0.88,  QColor(240, 60, 0)),      # orange-red
    (1.0,   QColor(220, 0, 0)),       # red
]


def _degree_color(degree: int, max_degree: int) -> QColor:
    """Interpolate color from degree gradient."""
    if max_degree <= 0:
        return DEGREE_GRADIENT[0][1]
    t = min(degree / max(max_degree, 1), 1.0)
    # Find segment
    for i in range(len(DEGREE_GRADIENT) - 1):
        t0, c0 = DEGREE_GRADIENT[i]
        t1, c1 = DEGREE_GRADIENT[i + 1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return QColor(
                int(c0.red() + f * (c1.red() - c0.red())),
                int(c0.green() + f * (c1.green() - c0.green())),
                int(c0.blue() + f * (c1.blue() - c0.blue())),
            )
    return DEGREE_GRADIENT[-1][1]


class NeuronMapWidget(QWidget):
    """Custom QPainter widget displaying neurons as colored points."""

    neuron_hovered = pyqtSignal(object)
    neuron_selected = pyqtSignal(object)
    neuron_deselected = pyqtSignal()
    layout_started = pyqtSignal()
    layout_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 150)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Neuron Map")
        self.setAccessibleDescription("Interactive map of code concepts and their connections")

        # Data
        self._neurons: list[Neuron] = []
        self._edges: list[tuple[int, int, float]] = []
        self._neighbor_cache: dict[int, set[int]] = {}  # idx -> set of neighbor idx

        # View transform
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0

        # B-UI-04: Animated zoom-to-fit state
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_start_zoom = 1.0
        self._anim_target_zoom = 1.0
        self._anim_start_pan_x = 0.0
        self._anim_start_pan_y = 0.0
        self._anim_target_pan_x = 0.0
        self._anim_target_pan_y = 0.0
        self._anim_progress = 0.0
        self._anim_duration = 0.3  # 300ms

        # Search matches (B-UI-25)
        self._search_matches: set[str] = set()  # neuron IDs matching search

        # Interaction state
        self._hovered: Optional[Neuron] = None
        self._selected: set[int] = set()
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
        self._repaint_timer.setInterval(16)
        self._repaint_timer.timeout.connect(self.update)

        # R15: mouse throttle
        self._last_hover_time = 0.0

        # R6: cache
        self._cache_dirty = True

        # R11: AA toggle during pan
        self._aa_enabled = True

        # 3D cube rotation
        self._cube_angle = 0.0
        self._cube_timer = QTimer(self)
        self._cube_timer.setInterval(33)  # ~30fps
        self._cube_timer.timeout.connect(self._cube_tick)
        self._cube_timer.start()

        # B-UI-05: KD-tree (scipy.spatial.cKDTree)
        self._kdtree = None
        self._kdtree_screen_coords = None  # array of screen coords for KD-tree

        # B-UI-03: Laplacian worker (R3, R12)
        self._lap_thread: Optional[QThread] = None
        self._lap_worker = None
        self._layout_computing = False

        # B-UI-07: edge rendering
        self._max_visible_edges = 5000
        self._edge_lod_threshold = 0.3  # hide edges below this zoom

        # Empty state
        self._empty = True

        # Max degree (for color gradient)
        self._max_degree = 1

    def closeEvent(self, event):  # R4: cleanup
        self._cancel_laplacian()
        self._anim_timer.stop()
        self._cube_timer.stop()
        super().closeEvent(event)

    # --- 3D Cube ---

    def _cube_tick(self):
        """Rotate the 3D cube slowly. Skip when hidden to save CPU."""
        if not self.isVisible():
            return
        self._cube_angle += 0.006
        if self._cube_angle > math.tau:
            self._cube_angle -= math.tau
        self._invalidate_kdtree()
        self.update()

    def _project_3d(self, x, y, z):
        """Rotate + perspective project a 3D point. Returns (sx, sy, depth)."""
        a = self._cube_angle
        ax = a * 0.3  # slight X tilt

        # Rotate around Y axis
        cos_a, sin_a = math.cos(a), math.sin(a)
        x1 = x * cos_a - z * sin_a
        z1 = x * sin_a + z * cos_a

        # Rotate around X axis (slight)
        cos_ax, sin_ax = math.cos(ax), math.sin(ax)
        y1 = y * cos_ax - z1 * sin_ax
        z2 = y * sin_ax + z1 * cos_ax

        # Perspective projection
        fov = 3.5
        scale = fov / (fov + z2)
        return x1 * scale, y1 * scale, z2

    def _paint_cube_wireframe(self, p: QPainter):
        """Draw rotating wireframe cube."""
        corners_3d = [
            (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1),
        ]
        wire_edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # front face
            (4, 5), (5, 6), (6, 7), (7, 4),  # back face
            (0, 4), (1, 5), (2, 6), (3, 7),  # connectors
        ]
        s = 0.85  # cube edge slightly larger than neuron space
        projected = []
        for cx, cy, cz in corners_3d:
            sp = self._world_to_screen(cx * s, cy * s, cz * s)
            projected.append(sp)

        pen = QPen(QColor(0, 220, 255, 35), 1)
        p.setPen(pen)
        for i, j in wire_edges:
            p.drawLine(projected[i], projected[j])

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
                temperature=n.get("temperature", 0.0),
                zone=n.get("zone", ""),
            )
            neuron.category = LEVEL_SHAPES.get(neuron.level, SHAPE_CIRCLE)
            self._neurons.append(neuron)

        # Also load connections from scan data if present
        self._scan_connections = data.get("connections", [])
        self._build_edges()
        self._compute_degrees()

        # Random layout first (instant), then launch Laplacian in background
        self._layout_random()

        self._empty = False
        self._cache_dirty = True
        self._kdtree = None
        self._selected.clear()
        self._selection_history.clear()
        self._history_pos = -1
        self.update()

        # B-UI-03: launch Laplacian layout in QThread
        self._start_laplacian()

    def load_neurons(self, neurons: list[Neuron]):
        """Load neurons directly (for testing or programmatic use)."""
        self._neurons = neurons
        self._empty = len(neurons) == 0
        if not self._empty:
            self._build_edges()
            self._compute_degrees()
            self._layout_random()
        self._cache_dirty = True
        self._kdtree = None
        self._selected.clear()
        self.update()

    def _build_edges(self):
        """Build edge list from node depends + scan connections."""
        id_to_idx = {n.id: i for i, n in enumerate(self._neurons)}
        self._edges = []
        seen = set()

        # From node.depends
        for i, n in enumerate(self._neurons):
            for dep_id in n.depends:
                j = id_to_idx.get(dep_id)
                if j is not None:
                    key = (min(i, j), max(i, j))
                    if key not in seen:
                        seen.add(key)
                        self._edges.append((key[0], key[1], 1.0))

        # From scan connections (from/to or source/target format)
        for conn in getattr(self, '_scan_connections', []):
            src = conn.get("from") or conn.get("source", "")
            tgt = conn.get("to") or conn.get("target", "")
            i = id_to_idx.get(src)
            j = id_to_idx.get(tgt)
            if i is not None and j is not None:
                key = (min(i, j), max(i, j))
                if key not in seen:
                    seen.add(key)
                    w = conn.get("weight", 1.0)
                    self._edges.append((key[0], key[1], w))
        # Build neighbor cache for fast lookup
        self._neighbor_cache.clear()
        for ia, ib, _ in self._edges:
            self._neighbor_cache.setdefault(ia, set()).add(ib)
            self._neighbor_cache.setdefault(ib, set()).add(ia)

    def _compute_degrees(self):
        """Compute degree for each neuron."""
        for n in self._neurons:
            n.degree = 0
        for ia, ib, w in self._edges:
            self._neurons[ia].degree += 1
            self._neurons[ib].degree += 1
        self._max_degree = max((n.degree for n in self._neurons), default=1)

    def _layout_random(self):
        """Assign random 3D positions in [-0.8, 0.8] cube space."""
        rng = random.Random(42)
        for n in self._neurons:
            n.x = (rng.random() - 0.5) * 1.6
            n.y = (rng.random() - 0.5) * 1.6
            n.z = (rng.random() - 0.5) * 1.6

    # --- B-UI-03: Laplacian spectral layout (QThread) ---

    def _start_laplacian(self):
        """Launch Laplacian layout in background thread (R3, R12)."""
        if len(self._neurons) < 3:
            return  # Guard < 3 nodes

        # R12: cancel old worker before launching new one
        self._cancel_laplacian()

        try:
            from muninn.ui.workers import LaplacianWorker
        except ImportError:
            return  # scipy not available

        self._lap_thread = QThread()
        self._lap_worker = LaplacianWorker(
            self._neurons, self._edges, top_n=1000
        )
        # R3: moveToThread BEFORE connect
        self._lap_worker.moveToThread(self._lap_thread)
        self._lap_thread.started.connect(self._lap_worker.run)
        self._lap_worker.finished.connect(self._on_laplacian_done)
        self._lap_worker.error.connect(self._on_laplacian_error)
        self._lap_worker.finished.connect(self._lap_thread.quit)

        self._layout_computing = True
        self.layout_started.emit()
        self._lap_thread.start()

    def _cancel_laplacian(self):
        """Cancel running Laplacian worker (R12)."""
        if self._lap_worker is not None:
            self._lap_worker._stop = True
        if self._lap_thread is not None and self._lap_thread.isRunning():
            self._lap_thread.quit()
            self._lap_thread.wait(1000)
        self._lap_worker = None
        self._lap_thread = None
        self._layout_computing = False

    def _on_laplacian_done(self, positions):
        """Apply Laplacian layout positions (mapped to 3D cube space)."""
        self._layout_computing = False
        for i, (px, py) in enumerate(positions):
            if i < len(self._neurons):
                self._neurons[i].x = (px - 0.5) * 1.6  # map [0,1] -> [-0.8, 0.8]
                self._neurons[i].y = (py - 0.5) * 1.6
                # Keep z from random layout
        self._cache_dirty = True
        self._kdtree = None
        self.layout_finished.emit()
        self.update()

    def _on_laplacian_error(self, msg):
        """Laplacian failed, keep random layout."""
        self._layout_computing = False
        self.layout_finished.emit()

    # --- B-UI-05: KD-tree ---

    def _build_kdtree(self):
        """Build KD-tree from current screen positions."""
        if not self._neurons:
            self._kdtree = None
            return
        try:
            from scipy.spatial import cKDTree
            import numpy as np
            coords = []
            for n in self._neurons:
                sp = self._world_to_screen(n.x, n.y, n.z)
                coords.append([sp.x(), sp.y()])
            self._kdtree_screen_coords = np.array(coords)
            self._kdtree = cKDTree(self._kdtree_screen_coords)
        except ImportError:
            self._kdtree = None  # scipy not available, fallback to O(n)

    def _invalidate_kdtree(self):
        """Mark KD-tree as stale (needs rebuild on next hover)."""
        self._kdtree = None

    # --- Coordinate transforms ---

    def _world_to_screen(self, wx: float, wy: float, wz: float = 0.0) -> QPointF:
        px, py, _ = self._project_3d(wx, wy, wz)
        half_w = self.width() / 2
        half_h = self.height() / 2
        cube_scale = min(half_w, half_h) * 0.7
        sx = half_w + (px * cube_scale - self._pan_x) * self._zoom
        sy = half_h + (py * cube_scale - self._pan_y) * self._zoom
        return QPointF(sx, sy)

    def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        half_w = self.width() / 2
        half_h = self.height() / 2
        cube_scale = min(half_w, half_h) * 0.7
        if cube_scale == 0:
            return 0.0, 0.0
        wx = (sx - half_w) / (self._zoom * cube_scale) + self._pan_x / cube_scale
        wy = (sy - half_h) / (self._zoom * cube_scale) + self._pan_y / cube_scale
        return wx, wy

    # --- Paint ---

    def paintEvent(self, event):
        p = QPainter(self)
        if self._aa_enabled:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.fillRect(self.rect(), QColor(BG_0DP))

        if self._empty:
            self._paint_empty(p)
            p.end()
            return

        self._paint_cube_wireframe(p)
        self._paint_edges(p)
        self._paint_neurons(p)
        self._paint_legend(p)

        if self._rect_selecting:
            p.setPen(QPen(QColor(ACCENT_CYAN_HEX), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(0, 220, 255, 30))
            r = QRectF(self._rect_start, self._rect_end).normalized()
            p.drawRect(r)

        if self._layout_computing:
            p.setPen(QColor(ACCENT_CYAN_HEX))
            p.setFont(QFont(FONT_BODY, 12))
            p.drawText(QRectF(self.width() - 160, 8, 150, 24),
                       Qt.AlignmentFlag.AlignRight, "Computing layout...")

        p.end()

    def _paint_empty(self, p: QPainter):
        p.setPen(QColor(TEXT_SECONDARY))
        p.setFont(QFont(FONT_BODY, 16))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                   "No data loaded.\nScan a repo first!")

    def _paint_neurons(self, p: QPainter):
        """Draw neurons with degree-based colors, 3D depth, and category shapes."""
        font = QFont(FONT_BODY, max(8, int(10 * self._zoom)))
        fm = QFontMetrics(font)
        p.setFont(font)

        # Precompute hovered neuron index for fast neighbor lookup
        hovered_idx = None
        if self._hovered:
            for i, n in enumerate(self._neurons):
                if n is self._hovered:
                    hovered_idx = i
                    break

        viewport = self.rect()

        # Depth-sort: paint far neurons first (painter's algorithm)
        indexed = list(enumerate(self._neurons))
        indexed.sort(key=lambda x: self._project_3d(x[1].x, x[1].y, x[1].z)[2])

        for i, n in indexed:
            sp = self._world_to_screen(n.x, n.y, n.z)

            # Frustum culling: skip off-screen neurons
            if not viewport.contains(sp.toPoint()):
                continue

            # Depth-based sizing and alpha
            _, _, depth = self._project_3d(n.x, n.y, n.z)
            depth_scale = 3.5 / (3.5 + depth)
            radius = max(3, 6 * self._zoom * depth_scale)
            depth_alpha = int(130 + 125 * min(max(depth_scale, 0), 1))

            # Dimming: if something is hovered, dim non-neighbors
            alpha = depth_alpha
            if hovered_idx is not None and i != hovered_idx:
                neighbors = self._neighbor_cache.get(hovered_idx, set())
                if i not in neighbors:
                    alpha = int(depth_alpha * 0.2)

            # B-UI-03: Color by degree (not status)
            color = _degree_color(n.degree, self._max_degree)
            color.setAlpha(alpha)

            # Search match: orange ring (B-UI-25)
            if self._search_matches and n.id in self._search_matches:
                match_color = QColor(255, 165, 0, min(alpha, 180))
                p.setPen(QPen(match_color, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(sp, radius * 2.2, radius * 2.2)

            # Selected: halo
            if i in self._selected:
                halo_color = QColor(ACCENT_CYAN_HEX)
                halo_color.setAlpha(alpha)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(halo_color))
                p.drawEllipse(sp, radius * 2, radius * 2)

            # Hovered: glow
            if i == hovered_idx:
                glow = QColor(ACCENT_CYAN_HEX)
                glow.setAlpha(100)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(glow))
                p.drawEllipse(sp, radius * 1.8, radius * 1.8)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            self._draw_shape(p, sp, radius, n.category)

            # Label: only for hovered/selected neurons (3D cube is too dense for all labels)
            if (i == hovered_idx or i in self._selected) and self._zoom > 0.3:
                label_color = QColor(TEXT_PRIMARY)
                label_color.setAlpha(min(alpha, 220))
                p.setPen(label_color)
                max_w = int(100 * self._zoom)
                elided = fm.elidedText(n.label, Qt.TextElideMode.ElideRight, max_w)
                p.drawText(QPointF(sp.x() + radius + 4, sp.y() + 4), elided)

    def _draw_shape(self, p: QPainter, center: QPointF, r: float, shape: str):
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
        else:
            p.drawEllipse(center, r, r)

    def _paint_edges(self, p: QPainter):
        """Draw edges with bezier curves, LOD, batch, frustum culling."""
        if not self._edges:
            return

        # B-UI-07: LOD — hide edges at very low zoom
        if self._zoom < self._edge_lod_threshold:
            return

        viewport = QRectF(self.rect())
        n_neurons = len(self._neurons)

        # Sort by weight, take top edges (max 5000)
        visible_edges = []
        for ia, ib, w in self._edges:
            if ia >= n_neurons or ib >= n_neurons:
                continue
            na, nb = self._neurons[ia], self._neurons[ib]
            sa = self._world_to_screen(na.x, na.y, na.z)
            sb = self._world_to_screen(nb.x, nb.y, nb.z)
            # Frustum culling: skip if both endpoints off-screen
            if not viewport.contains(sa) and not viewport.contains(sb):
                continue
            visible_edges.append((sa, sb, w, ia, ib))
            if len(visible_edges) >= self._max_visible_edges:
                break

        if not visible_edges:
            return

        # B-UI-07: Batch bezier curves
        for sa, sb, w, ia, ib in visible_edges:
            # Alpha proportional to weight
            alpha = min(int(20 + w * 18), 80)
            # Thickness = log(weight + 1)
            thickness = max(0.5, math.log(w + 1) * self._zoom)
            pen = QPen(QColor(255, 255, 255, alpha), thickness)
            p.setPen(pen)

            # Bezier curve (control point offset perpendicular to midpoint)
            mx = (sa.x() + sb.x()) / 2
            my = (sa.y() + sb.y()) / 2
            dx = sb.x() - sa.x()
            dy = sb.y() - sa.y()
            dist = math.hypot(dx, dy)
            # Offset proportional to distance (curved feel)
            offset = min(dist * 0.15, 30)
            if dist > 1:
                nx, ny = -dy / dist, dx / dist
            else:
                nx, ny = 0, 0
            cx_pt = mx + nx * offset
            cy_pt = my + ny * offset

            path = QPainterPath()
            path.moveTo(sa)
            path.quadTo(QPointF(cx_pt, cy_pt), sb)
            p.drawPath(path)

    def _paint_legend(self, p: QPainter):
        """B-UI-03: Color legend (bottom-left, small, discreet)."""
        if not self._neurons or self._max_degree <= 0:
            return

        x0, y0 = 12, self.height() - 60
        bar_w, bar_h = 100, 8

        p.setPen(Qt.PenStyle.NoPen)
        # Draw gradient bar
        for i in range(bar_w):
            t = i / bar_w
            c = _degree_color(int(t * self._max_degree), self._max_degree)
            p.setBrush(QBrush(c))
            p.drawRect(QRectF(x0 + i, y0, 1, bar_h))

        # Labels
        p.setPen(QColor(TEXT_SECONDARY))
        font = QFont(FONT_CODE, 9)
        p.setFont(font)
        p.drawText(QPointF(x0, y0 + bar_h + 14), "0")
        p.drawText(QPointF(x0 + bar_w - 20, y0 + bar_h + 14), str(self._max_degree))
        p.drawText(QPointF(x0, y0 - 4), "Degree")

    # --- Zoom + Drag (B-UI-04) ---

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._zoom = max(0.1, min(20.0, self._zoom * factor))
        self._cache_dirty = True
        self._invalidate_kdtree()
        self._schedule_repaint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.position())
            if hit is not None:
                self._handle_neuron_click(hit, event.modifiers())
            else:
                # Check edge click (B-UI-07)
                edge_hit = self._hit_test_edge(event.position())
                if edge_hit is not None:
                    ia, ib = edge_hit
                    self._selected = {ia, ib}
                    self._push_history()
                    self.neuron_selected.emit(self._neurons[ia])
                    self._cache_dirty = True
                    self.update()
                elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._rect_selecting = True
                    self._rect_start = event.position()
                    self._rect_end = event.position()
                else:
                    # Deselect on empty click
                    if self._selected:
                        self._selected.clear()
                        self.neuron_deselected.emit()
                        self._cache_dirty = True
                        self.update()
                    self._dragging = True
                    self._drag_start = event.position()
                    self._pan_start_x = self._pan_x
                    self._pan_start_y = self._pan_y
                    self._aa_enabled = False

    def mouseMoveEvent(self, event):
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
            self._invalidate_kdtree()
            self._schedule_repaint()
        elif self._rect_selecting:
            self._rect_end = event.position()
            self._schedule_repaint()
        else:
            hit = self._hit_test(event.position())
            if hit != self._hovered:
                self._hovered = hit
                self.neuron_hovered.emit(hit)
                self._schedule_repaint()

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
                self._aa_enabled = True
                self._cache_dirty = True
                self.update()
            elif self._rect_selecting:
                self._rect_selecting = False
                self._select_in_rect()
                self.update()

    def mouseDoubleClickEvent(self, event):
        hit = self._hit_test(event.position())
        if hit and hit.entry:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(hit.entry))
        elif hit is None:
            self._zoom_to_fit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_to_fit_animated()
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._copy_selection()
        elif event.key() == Qt.Key.Key_Left and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._history_back()
        elif event.key() == Qt.Key.Key_Right and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._history_forward()

    # --- Hit testing ---

    def _hit_test(self, screen_pos: QPointF) -> Optional[Neuron]:
        """Find neuron under screen position. Uses KD-tree if available."""
        if not self._neurons:
            return None
        hit_radius = max(8, 10 * self._zoom)

        # Try KD-tree first (B-UI-05)
        if self._kdtree is None:
            self._build_kdtree()

        if self._kdtree is not None:
            dist, idx = self._kdtree.query([screen_pos.x(), screen_pos.y()])
            if dist < hit_radius and idx < len(self._neurons):
                return self._neurons[idx]
            return None

        # Fallback O(n)
        best = None
        best_dist = float("inf")
        for n in self._neurons:
            sp = self._world_to_screen(n.x, n.y, n.z)
            dx = screen_pos.x() - sp.x()
            dy = screen_pos.y() - sp.y()
            dist = math.hypot(dx, dy)
            if dist < hit_radius and dist < best_dist:
                best = n
                best_dist = dist
        return best

    def _hit_test_edge(self, screen_pos: QPointF) -> Optional[tuple[int, int]]:
        """B-UI-07: Find edge near screen position."""
        if not self._edges:
            return None
        hit_radius = max(6, 8 * self._zoom)
        sx, sy = screen_pos.x(), screen_pos.y()
        n_neurons = len(self._neurons)

        for ia, ib, w in self._edges:
            if ia >= n_neurons or ib >= n_neurons:
                continue
            sa = self._world_to_screen(self._neurons[ia].x, self._neurons[ia].y, self._neurons[ia].z)
            sb = self._world_to_screen(self._neurons[ib].x, self._neurons[ib].y, self._neurons[ib].z)
            # Point-to-segment distance
            dist = self._point_to_segment_dist(sx, sy, sa.x(), sa.y(), sb.x(), sb.y())
            if dist < hit_radius:
                return (ia, ib)
        return None

    @staticmethod
    def _point_to_segment_dist(px, py, ax, ay, bx, by) -> float:
        """Distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def _get_neighbor_labels(self, neuron: Neuron, max_n: int = 3) -> list[str]:
        idx = None
        for i, n in enumerate(self._neurons):
            if n is neuron:
                idx = i
                break
        if idx is None:
            return []
        neighbor_indices = self._neighbor_cache.get(idx, set())
        labels = [self._neurons[j].label for j in neighbor_indices if j < len(self._neurons)]
        return labels[:max_n]

    # --- Selection (B-UI-06) ---

    def _handle_neuron_click(self, neuron: Neuron, modifiers):
        idx = self._neurons.index(neuron)
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)
        else:
            if idx in self._selected and len(self._selected) == 1:
                self._selected.clear()
                self.neuron_deselected.emit()
            else:
                self._selected = {idx}
                self.neuron_selected.emit(neuron)

        self._push_history()
        self._cache_dirty = True
        self.update()

    def _select_in_rect(self):
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
        """Instant zoom to fit (reset to default 3D view)."""
        if not self._neurons:
            return
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._cache_dirty = True
        self._invalidate_kdtree()
        self.update()

    def _zoom_to_fit_animated(self):
        """B-UI-04: Animated zoom-to-fit (300ms ease-out, reset to default 3D view)."""
        if not self._neurons:
            return
        self._anim_start_zoom = self._zoom
        self._anim_start_pan_x = self._pan_x
        self._anim_start_pan_y = self._pan_y
        self._anim_target_pan_x = 0.0
        self._anim_target_pan_y = 0.0
        self._anim_target_zoom = 1.0
        self._anim_progress = 0.0
        self._anim_timer.start()

    def _anim_tick(self):
        """Tick for zoom-to-fit animation."""
        self._anim_progress += 16.0 / (self._anim_duration * 1000)
        if self._anim_progress >= 1.0:
            self._anim_progress = 1.0
            self._anim_timer.stop()

        # Ease-out: t' = 1 - (1-t)^2
        t = 1 - (1 - self._anim_progress) ** 2

        self._zoom = self._anim_start_zoom + t * (self._anim_target_zoom - self._anim_start_zoom)
        self._pan_x = self._anim_start_pan_x + t * (self._anim_target_pan_x - self._anim_start_pan_x)
        self._pan_y = self._anim_start_pan_y + t * (self._anim_target_pan_y - self._anim_start_pan_y)
        self._cache_dirty = True
        self._invalidate_kdtree()
        self.update()

    def _clamp_pan(self):
        half = min(self.width(), self.height()) * 0.5 + 50
        self._pan_x = max(-half, min(half, self._pan_x))
        self._pan_y = max(-half, min(half, self._pan_y))

    def _schedule_repaint(self):
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

    @property
    def is_computing_layout(self) -> bool:
        return self._layout_computing

    # --- Reconstruction mode (cube heatmap) ---
    #
    # Companion to docs/CUBE_UX_HEATMAP_PLAN.md Phase 1: brancher le NCD
    # d'une reconstruction Cube sur la carte, en live. Each cube becomes a
    # Neuron laid out in a grid, coloured by NCD (green = perfect match,
    # yellow/orange = partial, red = fail).

    def set_reconstruction_cubes(self, cubes: list):
        """Populate the map with cubes from a reconstruction run.

        Each cube is a dict with keys: idx, start, end, original, sha.
        Layout: simple grid (sqrt(n) columns), one neuron per cube.
        """
        import math
        self._neurons = []
        self._edges = []
        self._neighbor_cache = {}
        self._selected = set()

        # Stop the idle cube rotation and pin to a clean isometric angle.
        # In reconstruction mode the user is reading code positions — a
        # spinning cube fights that. ~pi/5 around Y gives a nice 3D feel
        # without distorting the grid.
        if hasattr(self, "_cube_timer") and self._cube_timer.isActive():
            self._cube_timer.stop()
        self._cube_angle = math.pi / 5  # ~36° — isometric-ish, fixed

        n = len(cubes)
        if n == 0:
            self._empty = True
            self.update()
            return

        # Normalise the degree gradient to [0..10] so NCD maps cleanly onto
        # the 10-step DEGREE_GRADIENT. Pending cubes start at 5 = mid-grey
        # so the user can distinguish "not yet processed" from "processed and red".
        self._max_degree = 10
        self._empty = False  # trigger the neuron painter instead of the empty-state banner

        # Starting positions: small grid inside the cube wireframe
        # (world coords in [-1, +1], wireframe at +/-0.85). The Laplacian
        # worker will then relax the layout using the chain edges below.
        cols = max(1, int(math.ceil(math.sqrt(n))))
        rows = max(1, int(math.ceil(n / cols)))
        extent = 1.2
        dx = extent / cols if cols > 1 else 0.0
        dy = extent / rows if rows > 1 else 0.0
        for cube in cubes:
            idx = cube["idx"]
            row = idx // cols
            col = idx % cols
            x = -extent / 2 + (col + 0.5) * (dx if cols > 1 else 0.0)
            y = -extent / 2 + (row + 0.5) * (dy if rows > 1 else 0.0)
            self._neurons.append(Neuron(
                id=f"cube_{idx}",
                label=f"L{cube['start']}-{cube['end']}",
                level="cube",
                status="todo",      # pending reconstruction
                temperature=0.5,    # neutral until reconstructed
                zone="reconstruction",
                x=x, y=y, z=0.0,
                degree=5,           # mid-yellow until the cube is processed
                category=SHAPE_SQUARE,  # render as squares (cubes of code)
            ))

        # Chain-graph edges: each cube is connected to the next. This feeds
        # the Laplacian spectral layout so the positions reflect the
        # sequential structure of the file.
        self._edges = [(i, i + 1, 1.0) for i in range(n - 1)]
        self._neighbor_cache = {
            i: {i - 1 for _ in [0] if i > 0} | {i + 1 for _ in [0] if i < n - 1}
            for i in range(n)
        }

        # Relax with the Laplacian worker if the graph is big enough
        # (the worker needs >=3 nodes). Fallback: keep the grid.
        if n >= 3 and hasattr(self, "_start_laplacian"):
            try:
                self._start_laplacian()
            except Exception:
                pass
        self.update()

    def update_cube_ncd(self, idx: int, ncd: float, sha_match: bool):
        """Update the colour of cube `idx` after reconstruction completes.

        Painting uses `n.degree` mapped onto DEGREE_GRADIENT (green->red),
        so we store NCD*10 into degree. SHA match forces degree=0 (greenest).
        """
        if idx < 0 or idx >= len(self._neurons):
            return
        n = self._neurons[idx]
        clamped = max(0.0, min(1.0, float(ncd)))
        n.temperature = clamped
        n.degree = 0 if sha_match else int(round(clamped * 10))
        n.status = "done" if sha_match else ("wip" if clamped < 0.3 else "todo")
        self.update()
