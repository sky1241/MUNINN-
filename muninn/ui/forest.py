"""Muninn UI — Forest mode (meta-mycelium multi-repo view).

B-UI-16: Solo/forest toggle button.
B-UI-17: Meta-mycelium loading (QThread, zone-colored, top 200/zone).
B-UI-18: Drill-down from forest to solo.

Rules: R3 (worker pattern), R8 (empty state), R12 (cancel old worker).
"""

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel,
)

from muninn.ui.theme import (
    ACCENT_CYAN_HEX, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY,
)


# Zone colors for forest mode (up to 13 zones)
ZONE_COLORS = [
    QColor(0, 220, 255),     # cyan
    QColor(50, 205, 50),     # green
    QColor(255, 165, 0),     # orange
    QColor(255, 80, 80),     # red
    QColor(180, 100, 255),   # purple
    QColor(255, 215, 0),     # gold
    QColor(0, 206, 209),     # teal
    QColor(255, 105, 180),   # pink
    QColor(100, 149, 237),   # cornflower
    QColor(144, 238, 144),   # light green
    QColor(255, 140, 0),     # dark orange
    QColor(147, 112, 219),   # medium purple
    QColor(72, 209, 204),    # turquoise
]


class MetaMyceliumWorker(QObject):
    """Load meta-mycelium in background (B-UI-17).

    Top 200 concepts per zone, max 2600 nodes total.
    Separate SQLite connection per thread.
    """

    finished = pyqtSignal(object)  # list of (concept, zone, degree) tuples
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, meta_db_path: str, max_per_zone: int = 200):
        super().__init__()
        self._stop = False
        self._meta_db_path = meta_db_path
        self._max_per_zone = max_per_zone

    def run(self):
        """Load top concepts per zone from meta-mycelium."""
        try:
            import sqlite3
            path = Path(self._meta_db_path)
            if not path.exists():
                self.error.emit(f"Meta-mycelium not found: {path}")
                return

            self.progress.emit(10)

            conn = sqlite3.connect(str(path), timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")

            # Get all zones
            try:
                zones = [r[0] for r in conn.execute(
                    "SELECT DISTINCT zone FROM connections WHERE zone IS NOT NULL"
                ).fetchall()]
            except sqlite3.OperationalError:
                # Table might not have zone column
                zones = ["default"]

            if self._stop:
                conn.close()
                return

            self.progress.emit(30)

            results = []
            for i, zone in enumerate(zones):
                if self._stop:
                    conn.close()
                    return

                try:
                    # Get top concepts by degree in this zone
                    rows = conn.execute("""
                        SELECT c.name, COUNT(*) as degree
                        FROM edges e
                        JOIN edge_zones ez ON ez.a = e.a AND ez.b = e.b
                        JOIN concepts c ON c.id = e.a OR c.id = e.b
                        WHERE ez.zone = ?
                        GROUP BY c.name
                        ORDER BY degree DESC
                        LIMIT ?
                    """, (zone, self._max_per_zone)).fetchall()

                    for name, degree in rows:
                        results.append((name, zone, degree))
                except sqlite3.OperationalError:
                    # Schema mismatch — skip zone
                    continue

                self.progress.emit(30 + int(60 * (i + 1) / max(len(zones), 1)))

            conn.close()
            self.progress.emit(100)
            self.finished.emit(results)

        except Exception as e:
            self.error.emit(str(e))


class ForestToggle(QWidget):
    """Solo/Forest toggle button (B-UI-16).

    Positioned top-left of neuron panel.
    """

    mode_changed = pyqtSignal(str)  # "solo" or "forest"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "solo"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._btn = QPushButton("SOLO")
        self._btn.setFixedSize(80, 28)
        self._btn.setFont(QFont(FONT_BODY, 10))
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self.toggle)
        self._update_style()
        layout.addWidget(self._btn)

        self.setFixedHeight(36)

    def toggle(self):
        """Toggle between solo and forest mode."""
        self._mode = "forest" if self._mode == "solo" else "solo"
        self._btn.setText(self._mode.upper())
        self._update_style()
        self.mode_changed.emit(self._mode)

    def _update_style(self):
        if self._mode == "solo":
            self._btn.setStyleSheet(
                f"QPushButton {{ background: rgba(0,220,255,0.15); color: {ACCENT_CYAN_HEX}; "
                f"border: 1px solid {ACCENT_CYAN_HEX}; border-radius: 8px; font-weight: 600; }}"
            )
        else:
            self._btn.setStyleSheet(
                f"QPushButton {{ background: rgba(50,205,50,0.15); color: #32CD32; "
                f"border: 1px solid #32CD32; border-radius: 8px; font-weight: 600; }}"
            )

    @property
    def mode(self) -> str:
        return self._mode
