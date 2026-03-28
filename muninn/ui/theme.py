"""Muninn UI Theme — cyberpunk QSS (Material dark elevation).

Design system values from reference_ux_rules.md:
- Spacing: multiples of 4px only
- Colors: 60-30-10 rule (neutral/surfaces/accent)
- Contrast: WCAG AA (4.5:1 text, 3:1 UI)
- Radius: 8px buttons/inputs, 12px cards/panels
- Borders: rgba(255,255,255,0.06-0.12), NO shadows in dark mode
"""

# --- Color tokens ---
BG_0DP = "#121212"       # Main background
BG_1DP = "#1E1E1E"       # Panels, cards
BG_2DP = "#222222"       # Menus, tooltips
BG_4DP = "#272727"       # Toolbars
BG_8DP = "#2E2E2E"       # Dialogs

TEXT_PRIMARY = "rgba(255, 255, 255, 0.87)"
TEXT_SECONDARY = "rgba(255, 255, 255, 0.60)"
TEXT_DISABLED = "rgba(255, 255, 255, 0.38)"

BORDER = "rgba(255, 255, 255, 0.06)"
BORDER_HOVER = "rgba(255, 255, 255, 0.12)"

ACCENT_CYAN = "rgba(0, 220, 255, 1.0)"
ACCENT_CYAN_HEX = "#00DCFF"
ACCENT_GREEN = "#35d99a"

SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
INFO = "#3B82F6"

# --- Font families ---
FONT_TITLE = "Orbitron"
FONT_BODY = "Rajdhani"
FONT_CODE = "JetBrains Mono"

# Cached QSS string (generated once)
_theme_cache = None


def load_theme() -> str:
    """Return the full QSS stylesheet string. Cached after first call."""
    global _theme_cache
    if _theme_cache is not None:
        return _theme_cache

    _theme_cache = _build_qss()
    return _theme_cache


def _build_qss() -> str:
    """Build the cyberpunk QSS — minimal selectors, no deep hierarchies (perf bug #19)."""
    return f"""
/* === GLOBAL === */
QWidget {{
    background-color: {BG_0DP};
    color: {TEXT_PRIMARY};
    font-family: "{FONT_BODY}";
    font-size: 16px;
}}

/* === MAIN WINDOW === */
QMainWindow {{
    background-color: {BG_0DP};
}}

/* === PANELS / FRAMES === */
QFrame, QGroupBox {{
    background-color: {BG_1DP};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 16px;
}}

QGroupBox::title {{
    font-family: "{FONT_TITLE}";
    font-size: 14px;
    color: {ACCENT_CYAN};
    padding: 4px 8px;
}}

/* === LABELS === */
QLabel {{
    background: transparent;
    border: none;
    padding: 0px;
}}

QLabel[heading="true"] {{
    font-family: "{FONT_TITLE}";
    font-size: 20px;
    font-weight: 600;
    color: {ACCENT_CYAN};
}}

/* === BUTTONS === */
QPushButton {{
    background-color: {BG_1DP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HOVER};
    border-radius: 8px;
    padding: 8px 16px;
    font-family: "{FONT_BODY}";
    font-size: 14px;
    min-height: 36px;
}}

QPushButton:hover {{
    background-color: {BG_2DP};
    border-color: {ACCENT_CYAN};
}}

QPushButton:pressed {{
    background-color: {BG_4DP};
}}

QPushButton:disabled {{
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

QPushButton[primary="true"] {{
    background-color: {ACCENT_CYAN_HEX};
    color: {BG_0DP};
    font-weight: 600;
}}

QPushButton[primary="true"]:hover {{
    background-color: #00c8e8;
}}

/* === INPUTS === */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {BG_1DP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HOVER};
    border-radius: 4px;
    padding: 8px;
    font-family: "{FONT_CODE}";
    font-size: 14px;
    min-height: 40px;
    selection-background-color: rgba(0, 220, 255, 0.3);
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT_CYAN};
}}

/* === SPLITTERS === */
QSplitter::handle {{
    background-color: {BG_4DP};
    border: 1px solid {BORDER};
}}

QSplitter::handle:horizontal {{
    width: 6px;
}}

QSplitter::handle:vertical {{
    height: 6px;
}}

QSplitter::handle:hover {{
    background-color: {ACCENT_CYAN_HEX};
}}

/* === SCROLLBARS === */
QScrollBar:vertical {{
    background: {BG_0DP};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {BG_4DP};
    border-radius: 4px;
    min-height: 24px;
    margin: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(255, 255, 255, 0.20);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {BG_0DP};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {BG_4DP};
    border-radius: 4px;
    min-width: 24px;
    margin: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: rgba(255, 255, 255, 0.20);
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* === TOOLTIPS === */
QToolTip {{
    background-color: {BG_2DP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HOVER};
    border-radius: 8px;
    padding: 8px 12px;
    font-family: "{FONT_BODY}";
    font-size: 14px;
}}

/* === STATUS BAR === */
QStatusBar {{
    background-color: {BG_1DP};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-family: "{FONT_CODE}";
    font-size: 12px;
    padding: 4px 8px;
}}

QStatusBar::item {{
    border: none;
}}

/* === MENUS === */
QMenuBar {{
    background-color: {BG_1DP};
    color: {TEXT_PRIMARY};
    border-bottom: 1px solid {BORDER};
    padding: 4px;
}}

QMenuBar::item:selected {{
    background-color: {BG_2DP};
}}

QMenu {{
    background-color: {BG_2DP};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_HOVER};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: rgba(0, 220, 255, 0.15);
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* === TAB WIDGET === */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background-color: {BG_1DP};
}}

QTabBar::tab {{
    background-color: {BG_0DP};
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}

QTabBar::tab:selected {{
    background-color: {BG_1DP};
    color: {ACCENT_CYAN};
    border-color: {BORDER_HOVER};
}}
"""


def get_palette():
    """Return a QPalette for dynamic color use (avoids GDI leak from QSS, bug #45)."""
    from PyQt6.QtGui import QPalette, QColor
    from PyQt6.QtCore import Qt

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(BG_0DP))
    p.setColor(QPalette.ColorRole.WindowText, QColor(222, 222, 222))
    p.setColor(QPalette.ColorRole.Base, QColor(BG_1DP))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_2DP))
    p.setColor(QPalette.ColorRole.Text, QColor(222, 222, 222))
    p.setColor(QPalette.ColorRole.Button, QColor(BG_1DP))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(222, 222, 222))
    p.setColor(QPalette.ColorRole.Highlight, QColor(0, 220, 255))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_0DP))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_2DP))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(222, 222, 222))
    return p
