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
    QRadialGradient, QPainterPath, QPixmap, QImage,
)
from PyQt6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QLabel

from muninn.ui.theme import (
    BG_2DP, ACCENT_CYAN_HEX, ACCENT_GREEN, TEXT_PRIMARY,
    TEXT_SECONDARY, FONT_BODY,
)
from muninn.ui import _ASSETS_DIR


# Guided tutorial steps (B-UI-15) — French
TUTORIAL_STEPS = [
    {
        "key": "welcome",
        "text": "Hey! Je suis Navi, ton guide.\nOn va explorer ton code ensemble.",
        "button": None,
        "duration": 5.0,
    },
    {
        "key": "scan_prompt",
        "text": "D'abord, scanne un repo pour\nque je puisse cartographier ton code.",
        "button": "Scanner un repo",
        "duration": None,  # Wait for click
    },
    {
        "key": "scanning",
        "text": "Scan en cours...\nJe construis la carte neuronale.",
        "button": None,
        "duration": None,  # Until scan completes
    },
    {
        "key": "scan_done",
        "text": "Carte chargee! Chaque point est\nun concept de ton code.",
        "button": None,
        "duration": 5.0,
    },
    {
        "key": "explore_cube",
        "text": "Le cube 3D montre les connexions.\nClique un neurone pour l'explorer.",
        "button": None,
        "duration": 6.0,
    },
    {
        "key": "explore_tree",
        "text": "L'arbre en bas revele la structure.\nLes neurones du cube y correspondent.",
        "button": None,
        "duration": 6.0,
    },
    {
        "key": "explore_detail",
        "text": "Le panneau de droite montre les\ndetails: voisins, fichiers, temperature.",
        "button": None,
        "duration": 6.0,
    },
    {
        "key": "idle",
        "text": "",
        "button": None,
        "duration": None,
    },
]

# Contextual help texts (B-UI-15) — French
HELP_TEXTS = {
    "neuron_map": "La carte neuronale. Chaque point\nest un concept de ton code.",
    "tree_view": "L'arbre botanique de ton projet.\nSa forme revele l'architecture.",
    "detail_panel": "Clique un neurone pour voir\nses details ici.",
    "terminal": "Le terminal. Lance des commandes\nMuninn ou discute avec le LLM.",
    "first_launch": "Hey! Scanne un repo\npour commencer!",
    "no_data": "Pas de donnees chargees.\nScanne un repo!",
    "neuron_loaded": "Repo charge! Clique un neurone\npour explorer. Ctrl+F pour chercher.",
    "no_forest": "Pas de meta-mycelium.\nLance 'muninn feed' sur plusieurs repos.",
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
        # NOT transparent for mouse — we handle clicks on button, forward the rest
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        # Fill parent size
        if parent:
            self.setGeometry(parent.rect())

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

        # Tutorial state (B-UI-15)
        self._tutorial_step = 0
        self._tutorial_timer = 0.0  # seconds elapsed in current step
        self._tutorial_active = True

        # Flight patterns
        self._flight_mode = 0  # 0=patrol-H, 1=patrol-V, 2=figure-8, 3=circle, 4=diagonal
        self._flight_timer = 0.0
        self._flight_switch_interval = 12.0  # seconds per pattern
        self._flight_time = 0.0

        # R1: Timer stored as self attribute
        self._navi_timer = QTimer(self)
        self._navi_timer.setInterval(16)  # ~60fps
        self._navi_timer.timeout.connect(self._tick)
        self._navi_timer.start()

        # Orb size
        self._orb_radius = 12

        # B-UI-15: Scan button rect (set during paint)
        self._scan_btn_rect: Optional[QRectF] = None

    def _tick(self):
        """Main animation tick (16ms) with flight patterns + tutorial."""
        self._phase += 0.05
        if self._phase > math.pi * 200:
            self._phase = 0

        dt = 0.016  # ~16ms
        self._flight_time += dt

        # Tutorial auto-advance (timed steps only)
        if self._tutorial_active and self._tutorial_step < len(TUTORIAL_STEPS):
            step = TUTORIAL_STEPS[self._tutorial_step]
            if step["duration"] is not None:
                self._tutorial_timer += dt
                if self._tutorial_timer >= step["duration"]:
                    self._advance_tutorial()

        # Switch flight pattern periodically (only when NOT talking)
        if not self._bubble_visible:
            if self._flight_time > self._flight_switch_interval:
                self._flight_time = 0.0
                self._flight_mode = (self._flight_mode + 1) % 5

        if not self._reduce_motion:
            w = max(self.width(), 200)
            h = max(self.height(), 200)
            margin = 60

            if self._bubble_visible:
                # GEOSTATIONARY — hover gently in place when talking
                lerp_speed = 0.02
                # Gentle breathing only
                self._pos = QPointF(
                    self._pos.x() + math.sin(self._phase * 0.3) * 0.2,
                    self._pos.y() + math.cos(self._phase * 0.4) * 0.3,
                )
            else:
                # Flight patterns
                t = self._flight_time / self._flight_switch_interval  # 0..1

                if self._flight_mode == 0:
                    tx = margin + t * (w - 2 * margin)
                    ty = h * 0.25 + math.sin(t * math.pi * 4) * 30
                elif self._flight_mode == 1:
                    tx = w * 0.3 + math.cos(t * math.pi * 3) * 40
                    ty = margin + t * (h - 2 * margin)
                elif self._flight_mode == 2:
                    tx = w * 0.5 + math.sin(t * math.pi * 2) * (w * 0.3)
                    ty = h * 0.4 + math.sin(t * math.pi * 4) * (h * 0.2)
                elif self._flight_mode == 3:
                    tx = w * 0.5 + math.cos(t * math.pi * 2) * (w * 0.25)
                    ty = h * 0.4 + math.sin(t * math.pi * 2) * (h * 0.25)
                else:
                    seg = int(t * 4) % 4
                    st = (t * 4) % 1.0
                    corners = [
                        (margin, margin), (w - margin, h * 0.4),
                        (margin, h * 0.6), (w - margin, margin),
                    ]
                    x0, y0 = corners[seg]
                    x1, y1 = corners[(seg + 1) % 4]
                    tx = x0 + st * (x1 - x0)
                    ty = y0 + st * (y1 - y0)

                self._target = QPointF(tx, ty)

                lerp_speed = 0.06
                dx = self._target.x() - self._pos.x()
                dy = self._target.y() - self._pos.y()
                self._pos = QPointF(
                    self._pos.x() + dx * lerp_speed,
                    self._pos.y() + dy * lerp_speed,
                )

                # Micro float
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
        if self._tutorial_active:
            return  # Don't interrupt tutorial
        if context == self._current_context:
            return
        self._current_context = context
        text = HELP_TEXTS.get(context, "")
        if text:
            self.show_bubble(text, show_button=False)
        else:
            self.hide_bubble()

    def show_first_launch(self):
        """Start guided tutorial (B-UI-15)."""
        self._first_launch = True
        self._tutorial_active = True
        self._tutorial_step = 0
        self._tutorial_timer = 0.0
        self._show_tutorial_step()

    def _show_tutorial_step(self):
        """Display current tutorial step."""
        if self._tutorial_step >= len(TUTORIAL_STEPS):
            self._tutorial_active = False
            self.hide_bubble()
            return
        step = TUTORIAL_STEPS[self._tutorial_step]
        if step["key"] == "idle":
            self._tutorial_active = False
            self.hide_bubble()
            return
        self.show_bubble(step["text"], show_button=(step["button"] is not None))
        self._bubble_button_text = step.get("button", "")

    def _advance_tutorial(self):
        """Move to next tutorial step."""
        self._tutorial_step += 1
        self._tutorial_timer = 0.0
        self._show_tutorial_step()

    def on_scan_complete(self):
        """Called when scan finishes — advance tutorial past scanning step."""
        if self._tutorial_active:
            # Jump to scan_done step
            for i, step in enumerate(TUTORIAL_STEPS):
                if step["key"] == "scan_done":
                    self._tutorial_step = i
                    self._tutorial_timer = 0.0
                    self._show_tutorial_step()
                    return

    def dismiss_first_launch(self):
        """Dismiss first launch guide (after scan)."""
        self._first_launch = False
        self._tutorial_active = False
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
        """Draw the Navi orb — 3 glow layers + 6 dragonfly wings + iridescent core.

        Ported from proto_navi.html (sky1241/tree).
        6 wings in fan pattern: 3 left (grande/moyenne/petite), 3 right (mirrored).
        Each pair has different flap speed and angle range.
        """
        cx, cy = self._pos.x(), self._pos.y()
        r = self._orb_radius
        pulse = 0.7 + 0.3 * math.sin(self._phase * 2)

        # === 3 GLOW LAYERS (breathe animation, staggered) ===
        for i, (size_mult, base_alpha) in enumerate([(5.5, 0.06), (3.5, 0.15), (2.0, 0.5)]):
            breathe = 1.0 + 0.2 * math.sin(self._phase * 2 + i * 0.6)
            gr = r * size_mult * breathe
            glow = QRadialGradient(cx, cy, gr)
            a = int(base_alpha * 255 * pulse)
            glow.setColorAt(0.0, QColor(0, 255, 210, a))
            glow.setColorAt(0.4, QColor(0, 150, 255, int(a * 0.5)))
            glow.setColorAt(0.65, QColor(0, 100, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(cx, cy), gr, gr)

        # === 6 WINGS — scythe/crescent shape, top-mounted downbeat ===
        # Grandes: long curved crescents on top, powerful downbeat
        # Moyennes: shorter crescents, offset phase
        # Petites: tiny fast stabilizers behind

        p.save()
        p.translate(cx, cy)

        t = self._phase

        def _draw_crescent_wing(side_m, length, thickness, angle_deg, alpha_base):
            """Draw a curved crescent/scythe wing shape."""
            grad = QLinearGradient(0, -length, 0, length * 0.2)
            grad.setColorAt(0.0, QColor(0, 255, 230, int(alpha_base * 0.3)))
            grad.setColorAt(0.3, QColor(60, 240, 255, int(alpha_base * 0.9)))
            grad.setColorAt(0.6, QColor(140, 250, 255, alpha_base))
            grad.setColorAt(1.0, QColor(0, 200, 255, int(alpha_base * 0.2)))

            p.save()
            p.rotate(angle_deg)

            p.setPen(QPen(QColor(130, 235, 255, int(alpha_base * 0.7)), 0.6))
            p.setBrush(QBrush(grad))

            # Crescent: curves up from root, sweeps outward, tapers to point
            path = QPainterPath()
            # Root at body
            path.moveTo(0, 0)
            # Leading edge — sweeps up and out in a long arc
            path.cubicTo(
                -thickness * 0.8 * side_m, -length * 0.35,   # pull inward first
                -thickness * 1.5 * side_m, -length * 0.7,    # wide arc outward
                -thickness * 0.3 * side_m, -length,           # tip (nearly straight up)
            )
            # Trailing edge — tighter curve back to root
            path.cubicTo(
                thickness * 0.5 * side_m, -length * 0.65,
                thickness * 0.3 * side_m, -length * 0.3,
                0, 0,
            )
            path.closeSubpath()
            p.drawPath(path)

            # Single central nervure
            p.setPen(QPen(QColor(120, 230, 255, int(alpha_base * 0.35)), 0.3))
            p.drawLine(
                QPointF(0, 0),
                QPointF(-thickness * 0.4 * side_m, -length * 0.85),
            )

            p.restore()

        # === GRANDES — long crescents, slow powerful downbeat ===
        for side_m in [-1, 1]:
            ph = 0.0 if side_m == -1 else 0.2
            raw = math.sin(t * 3.0 + ph)
            # Asymmetric: slow down, fast up
            flap = raw ** 0.5 if raw > 0 else -((-raw) ** 1.8)
            # Angle: UP = tight to body (small angle), DOWN = spread wide
            angle = 25 * side_m + flap * 55 * side_m
            spread = (flap + 1) / 2
            length = r * (5.0 + 1.5 * spread)
            thickness = r * (0.8 + 0.4 * spread)
            alpha = int(40 + 30 * spread)
            _draw_crescent_wing(side_m, length, thickness, angle, alpha)

        # === MOYENNES — shorter, delayed, slightly back ===
        for side_m in [-1, 1]:
            ph = 0.6 if side_m == -1 else 0.9
            raw = math.sin(t * 3.0 + ph)
            flap = raw ** 0.6 if raw > 0 else -((-raw) ** 1.5)
            angle = 35 * side_m + flap * 45 * side_m
            spread = (flap + 1) / 2
            length = r * (3.5 + 1.0 * spread)
            thickness = r * (0.6 + 0.3 * spread)
            alpha = int(30 + 20 * spread)

            p.save()
            p.translate(0, r * 0.3)  # Slightly lower attach point
            _draw_crescent_wing(side_m, length, thickness, angle, alpha)
            p.restore()

        # === PETITES — fast stabilizers, ellipses, behind ===
        for side_m in [-1, 1]:
            ph = 1.5 if side_m == -1 else 1.8
            flap = math.sin(t * 8.0 + ph) * 0.5 + 0.5
            angle = 50 * side_m + 15 * (flap - 0.5) * side_m
            wl = r * 1.8
            ww = r * 0.25
            alpha = 25

            grad = QLinearGradient(0, 0, wl * side_m * 0.5, -wl * 0.5)
            grad.setColorAt(0.0, QColor(0, 255, 230, alpha))
            grad.setColorAt(1.0, QColor(0, 200, 255, int(alpha * 0.2)))

            p.save()
            p.translate(0, r * 0.7)
            p.rotate(angle)
            p.setPen(QPen(QColor(130, 230, 255, int(alpha * 0.5)), 0.3))
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(wl * 0.3 * side_m, -wl * 0.2), wl * 0.4, ww)
            p.restore()

        p.restore()

        # === CORE ORB — iridescent (white -> cyan -> blue) ===
        core = QRadialGradient(cx - r * 0.2, cy - r * 0.2, r)
        core.setColorAt(0.0, QColor(255, 255, 255))
        core.setColorAt(0.25, QColor(176, 255, 238))
        core.setColorAt(0.5, QColor(0, 232, 192))
        core.setColorAt(0.8, QColor(0, 136, 255))
        core.setColorAt(1.0, QColor(0, 136, 255, 0))
        p.setBrush(QBrush(core))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

    def _load_bubble_frame(self):
        """Lazy-load PNG bubble frame (B-UI-14) with black made transparent."""
        if self._bubble_frame is None:
            frame_path = _ASSETS_DIR / "node_tooltip_frame_blue.png"
            if frame_path.exists():
                img = QImage(str(frame_path))
                img = img.convertToFormat(QImage.Format.Format_ARGB32)
                # Make dark pixels transparent (threshold: brightness < 40)
                for y in range(img.height()):
                    for x in range(img.width()):
                        c = QColor(img.pixel(x, y))
                        brightness = c.red() + c.green() + c.blue()
                        if brightness < 120:  # Near-black -> transparent
                            # Scale alpha by brightness (smooth fade)
                            alpha = int((brightness / 120) * c.alpha())
                            img.setPixelColor(x, y, QColor(c.red(), c.green(), c.blue(), alpha))
                self._bubble_frame = QPixmap.fromImage(img)

    def _paint_bubble(self, p: QPainter):
        """Draw the dialogue bubble to the right of Navi (B-UI-14: PNG frame x2.5)."""
        cx, cy = self._pos.x(), self._pos.y()

        # Bubble size (x2.5 bigger)
        bubble_w = 600
        bubble_h = 220 if self._bubble_button_visible else 180

        # Position: to the RIGHT of Navi orb
        bx = cx + self._orb_radius * 4
        by = cy - bubble_h / 2

        # Clamp to widget bounds
        bx = max(8, min(self.width() - bubble_w - 8, bx))
        by = max(8, min(self.height() - bubble_h - 8, by))

        rect = QRectF(bx, by, bubble_w, bubble_h)

        # B-UI-14: Use PNG frame if available, else fallback to rounded rect
        self._load_bubble_frame()
        if self._bubble_frame and not self._bubble_frame.isNull():
            scaled_frame = self._bubble_frame.scaled(
                int(bubble_w), int(bubble_h),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(bx), int(by), scaled_frame)
        else:
            p.setPen(QPen(QColor(0, 220, 255, 100), 1))
            p.setBrush(QBrush(QColor(2, 8, 22, 0)))  # Transparent background
            p.drawRoundedRect(rect, 12, 12)

        # Text — cyan color like Navi, CENTERED
        p.setPen(QColor(0, 220, 255))
        font = QFont(FONT_BODY, 16)
        p.setFont(font)
        text_rect = QRectF(bx + 24, by + 20, bubble_w - 48, bubble_h - (70 if self._bubble_button_visible else 40))
        p.drawText(text_rect,
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   self._bubble_text)

        # B-UI-15: Action button in bubble
        if self._bubble_button_visible:
            btn_label = getattr(self, '_bubble_button_text', '') or "Scanner un repo"
            btn_w, btn_h = 200, 36
            btn_x = bx + (bubble_w - btn_w) / 2
            btn_y = by + bubble_h - btn_h - 16
            # Button background
            p.setPen(QPen(QColor(0, 220, 255), 1))
            p.setBrush(QBrush(QColor(0, 220, 255, 40)))
            p.drawRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 6, 6)
            # Button text
            p.setPen(QColor(0, 220, 255))
            p.setFont(QFont(FONT_BODY, 14))
            p.drawText(QRectF(btn_x, btn_y, btn_w, btn_h),
                       Qt.AlignmentFlag.AlignCenter, btn_label)
            # Store button rect for click detection
            self._scan_btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)

    def resizeEvent(self, event):
        """Keep Navi the same size as parent overlay."""
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        """Handle click on button — forward everything else to parent."""
        if (event.button() == Qt.MouseButton.LeftButton
                and self._bubble_button_visible
                and self._scan_btn_rect is not None
                and self._scan_btn_rect.contains(event.position())):
            self.scan_requested.emit()
            # Advance tutorial past scan_prompt
            if self._tutorial_active:
                self._advance_tutorial()
            return  # Consumed
        # Forward click to parent (neuron map underneath)
        event.ignore()

    # --- Public ---

    @property
    def is_first_launch(self) -> bool:
        return self._first_launch

    @property
    def orb_position(self) -> QPointF:
        return QPointF(self._pos)
