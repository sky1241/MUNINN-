"""Tests for B-UI-00b: Theme QSS cyberpunk."""

import pytest


def test_load_theme_returns_string():
    """load_theme() returns a non-empty QSS string."""
    from muninn.ui.theme import load_theme
    qss = load_theme()
    assert isinstance(qss, str)
    assert len(qss) > 500


def test_load_theme_cached():
    """Second call returns same object (cached)."""
    from muninn.ui import theme
    theme._theme_cache = None
    qss1 = theme.load_theme()
    qss2 = theme.load_theme()
    assert qss1 is qss2


def test_theme_contains_key_values():
    """QSS contains required color and font tokens."""
    from muninn.ui.theme import load_theme
    qss = load_theme()
    assert "#121212" in qss
    assert "#1E1E1E" in qss
    assert "rgba(0, 220, 255" in qss
    assert "Orbitron" in qss
    assert "Rajdhani" in qss
    assert "JetBrains Mono" in qss


def test_theme_spacing_multiples_of_4():
    """Padding/margin/width/height values are multiples of 4 (except 0, 1 for borders)."""
    import re
    from muninn.ui.theme import load_theme
    qss = load_theme()
    # Only check spacing properties, not font-size/min-height
    spacing_props = re.findall(
        r'(?:padding|margin|width|height|border-radius):\s*([^;]+)',
        qss,
    )
    for prop_val in spacing_props:
        matches = re.findall(r'(\d+)px', prop_val)
        for m in matches:
            val = int(m)
            if val <= 1 or val == 6:
                continue  # 0px, 1px borders, 6px splitter handle OK
            assert val % 4 == 0, f"Found {val}px in spacing — not a multiple of 4"


def test_theme_no_border_image():
    """No border-image in QSS (fuite memoire bug #46)."""
    from muninn.ui.theme import load_theme
    qss = load_theme()
    assert "border-image" not in qss


def test_apply_theme(qapp):
    """Theme can be applied to QApplication without error."""
    from muninn.ui.theme import load_theme
    from PyQt6.QtGui import QPixmapCache
    qapp.setStyleSheet(load_theme())
    QPixmapCache.clear()  # R44: clear after bulk style change


def test_get_palette(qapp):
    """get_palette() returns valid QPalette with correct window color."""
    from muninn.ui.theme import get_palette
    from PyQt6.QtGui import QPalette
    p = get_palette()
    assert isinstance(p, QPalette)
    window_color = p.color(QPalette.ColorRole.Window)
    assert window_color.red() == 0x12
    assert window_color.green() == 0x12
    assert window_color.blue() == 0x12


def test_color_tokens_exported():
    """Key color constants are accessible from module."""
    from muninn.ui import theme
    assert theme.BG_0DP == "#121212"
    assert theme.ACCENT_CYAN_HEX == "#00DCFF"
    assert theme.SUCCESS == "#22C55E"
    assert theme.ERROR == "#EF4444"
    assert theme.FONT_TITLE == "Orbitron"
