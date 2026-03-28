"""Muninn UI — About dialog.

B-UI-32: Version info, credits, links.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
)

from muninn.ui.theme import BG_1DP, ACCENT_CYAN_HEX, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY


class AboutDialog(QDialog):
    """About dialog showing version, credits, links (B-UI-32)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About Muninn")
        self.setFixedSize(360, 280)
        self.setStyleSheet(f"QDialog {{ background: {BG_1DP}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Title
        title = QLabel("Muninn")
        title.setFont(QFont(FONT_BODY, 24, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT_CYAN_HEX};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        sub = QLabel("Memory Compression Engine for LLMs")
        sub.setFont(QFont(FONT_BODY, 11))
        sub.setStyleSheet(f"color: {TEXT_PRIMARY};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # Version
        try:
            from muninn import __version__
            version_text = f"v{__version__}"
        except (ImportError, AttributeError):
            version_text = "dev"
        ver = QLabel(version_text)
        ver.setFont(QFont(FONT_BODY, 10))
        ver.setStyleSheet(f"color: {TEXT_SECONDARY};")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        # Credits
        credits = QLabel("Created by Sky")
        credits.setFont(QFont(FONT_BODY, 10))
        credits.setStyleSheet(f"color: {TEXT_SECONDARY};")
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(credits)

        layout.addStretch()

        # Close button
        btn = QPushButton("OK")
        btn.setFixedWidth(80)
        btn.setStyleSheet(
            f"QPushButton {{ background: rgba(0,220,255,0.15); color: {ACCENT_CYAN_HEX}; "
            f"border: 1px solid {ACCENT_CYAN_HEX}; border-radius: 8px; padding: 6px; }}"
        )
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
