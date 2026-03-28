"""Muninn UI — Navi fairy guide widget.

B-UI-14: Sprite (orb + wings), lerp follow cursor, idle float, dialogue bubble.
B-UI-15: Contextual guide (hover explanations), first launch guide.

Rules: R1 (ownership — self.navi_timer), R5 (repaint throttle).
Respects Windows "reduce motion" setting.
"""

import math
import time
import ctypes
from typing import Optional

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QLinearGradient,
    QRadialGradient, QPainterPath, QPixmap,
)
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel

from muninn.ui.theme import (
    BG_2DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_BODY,
)
from muninn.ui import _ASSETS_DIR


# Contextual help texts (B-UI-15)
HELP_TEXTS = {
    "neuron_map": "This is the neuron map. Each point is a concept in your code. Connected points share dependencies.",
    "tree_view": "This is your project's botanical tree. The shape reveals your architecture pattern.",
    "detail_panel": "Click a neuron to see its details here: neighbors, files, temperature.",
    "terminal": "The terminal. Run Muninn commands or chat with the LLM.",
    "first_launch": "Hey! I'm Navi. Scan a repo to get started!",
    "no_data": "No data loaded yet. Try scanning a repo!",
    "scan_button": "Click here to scan a repo and populate the map.",
}


def _reduce_motion_enabled() -> bool:
    """Check if Windows 'reduce motion' / 'show animations' is disabled."""
    try:
        SPI_GETCLIENTAREAANIMATION = 0x1042
        result = ctypes.c_bool()
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(result), 0
        )
        return not result.value  # If animations OFF, reduce_motion = True
    except Exception:
        return False


class NaviWidget(QWidget):
    """Navi fairy guide — animated orb that follows cursor and shows contextual help.

    Features:
    - Orb with pulsing glow (cyan) + dragonfly wings
    - Lerp follow cursor (smooth, 16ms timer)
    - Idle: floats near active panel
    - Dialogue bubble with tooltip frame
    - Contextual help on hover
    - First launch guide (B-UI-15)
    """

    scan_requested = pyqtSignal()  # When user clicks "Scan" in the bubble

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        # Position (screen coords within parent)
        self._pos = QPointF(100, 100)
        self._target = QPointF(100, 100)

        # Animation state
        self._phase = 0.0  # For pulsing/wing animation
        self._reduce_motion = _reduce_motion_enabled()

        # Dialogue bubble
        self._bubble_text: str = ""
        self._bubble_visible = False
        self._bubble_button_visible = False

        # Tooltip frame (lazy loaded)
        self._bubble_frame: Optional[QPixmap] = None

        # State
        self._first_launch = True
        self._current_context = ""

        # R1: Timer stored as self attribute
        self._navi_timer = QTimer(self)
        self._navi_timer.setInterval(16)  # ~60fps
        self._navi_timer.timeout.connect(self._tick)
        self._navi_timer.start()

        # Orb size
        self._orb_radius = 12

    def _tick(self):
        """Main animation tick (16ms)."""
        self._phase += 0.05
        if self._phase > math.pi * 200:
            self._phase = 0

        if not self._reduce_motion:
            # Lerp toward target
            lerp_speed = 0.08
            dx = self._target.x() - self._pos.x()
            dy = self._target.y() - self._pos.y()
            self._pos = QPointF(
                self._pos.x() + dx * lerp_speed,
                self._pos.y() + dy * lerp_speed,
            )

            # Idle float (small oscillation)
            if abs(dx) < 5 and abs(dy) < 5:
                self._pos = QPointF(
                    self._pos.x() + math.sin(self._phase * 0.5) * 0.3,
                    self._pos.y() + math.cos(self._phase * 0.7) * 0.5,
                )

        self.update()

    def set_target(self, pos: QPointF):
        """Set the target position Navi floats toward."""
        self._target = pos
        if self._reduce_motion:
            self._pos = pos

    def show_bubble(self, text: str, show_button: bool = False):
        """Show a dialogue bubble with text."""
        self._bubble_text = text
        self._bubble_visible = True
        self._bubble_button_visible = show_button
        self.update()

    def hide_bubble(self):
        """Hide the dialogue bubble."""
        self._bubble_visible = False
        self.update()

    def show_context_help(self, context: str):
        """Show contextual help for a given context (B-UI-15)."""
        if context == self._current_context:
            return
        self._current_context = context
        text = HELP_TEXTS.get(context, "")
        if text:
            self.show_bubble(text, show_button=(context in ("first_launch", "no_data")))
        else:
            self.hide_bubble()

    def show_first_launch(self):
        """Show first launch guide (B-UI-15)."""
        self._first_launch = True
        self.show_context_help("first_launch")

    def dismiss_first_launch(self):
        """Dismiss first launch guide (after scan)."""
        self._first_launch = False
        self.hide_bubble()

    # --- Paint ---

    def paintEvent(self, event):
        if not self.isVisible():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw bubble first (behind orb)
        if self._bubble_visible and self._bubble_text:
            self._paint_bubble(p)

        # Draw Navi orb
        self._paint_orb(p)

        p.end()

    def _paint_orb(self, p: QPainter):
        """Draw the Navi orb with pulsing glow + dragonfly wings."""
        cx, cy = self._pos.x(), self._pos.y()
        r = self._orb_radius

        # Pulsing glow
        pulse = 0.7 + 0.3 * math.sin(self._phase * 2)
        glow_r = r * (2.0 + pulse * 0.5)

        # Outer glow (radial gradient)
        glow = QRadialGradient(cx, cy, glow_r)
        glow.setColorAt(0.0, QColor(0, 220, 255, int(120 * pulse)))
        glow.setColorAt(0.5, QColor(0, 220, 255, int(40 * pulse)))
        glow.setColorAt(1.0, QColor(0, 220, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Wings (two ellipses, oscillating)
        wing_angle = math.sin(self._phase * 4) * 0.3  # Flutter
        p.save()
        p.translate(cx, cy)

        wing_color = QColor(0, 220, 255, 60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(wing_color))

        # Left wing
        p.save()
        p.rotate(-30 + math.degrees(wing_angle))
        p.drawEllipse(QPointF(-r * 1.5, -r * 0.3), r * 1.2, r * 0.4)
        p.restore()

        # Right wing
        p.save()
        p.rotate(30 - math.degrees(wing_angle))
        p.drawEllipse(QPointF(r * 1.5, -r * 0.3), r * 1.2, r * 0.4)
        p.restore()

        p.restore()

        # Core orb
        core = QRadialGradient(cx - r * 0.2, cy - r * 0.2, r)
        core.setColorAt(0.0, QColor(200, 255, 255))
        core.setColorAt(0.4, QColor(0, 220, 255))
        core.setColorAt(1.0, QColor(0, 150, 200))
        p.setBrush(QBrush(core))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _paint_bubble(self, p: QPainter):
        """Draw the dialogue bubble near the orb."""
        cx, cy = self._pos.x(), self._pos.y()

        # Bubble position (above the orb)
        bubble_w = 220
        bubble_h = 80
        bx = cx - bubble_w / 2
        by = cy - self._orb_radius * 3 - bubble_h

        # Clamp to widget bounds
        bx = max(8, min(self.width() - bubble_w - 8, bx))
        by = max(8, by)

        # Background
        p.setPen(QPen(QColor(0, 220, 255, 100), 1))
        p.setBrush(QBrush(QColor(BG_2DP)))
        rect = QRectF(bx, by, bubble_w, bubble_h)
        p.drawRoundedRect(rect, 12, 12)

        # Text
        p.setPen(QColor(TEXT_PRIMARY))
        font = QFont(FONT_BODY, 11)
        p.setFont(font)
        text_rect = QRectF(bx + 12, by + 8, bubble_w - 24, bubble_h - 16)
        p.drawText(text_rect,
                   Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                   self._bubble_text)

    # --- Public ---

    @property
    def is_first_launch(self) -> bool:
        return self._first_launch

    @property
    def orb_position(self) -> QPointF:
        return QPointF(self._pos)
