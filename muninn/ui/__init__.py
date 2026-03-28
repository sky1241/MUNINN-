"""Muninn UI — PyQt6 desktop interface for the Muninn memory engine."""

import os
import sys
import warnings
from pathlib import Path

_FONTS_DIR = Path(__file__).parent / "fonts"
_ASSETS_DIR = Path(__file__).parent / "assets"
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_SCANS_DIR = Path(__file__).parent / "scans"

# PyInstaller support
if hasattr(sys, "_MEIPASS"):
    _FONTS_DIR = Path(sys._MEIPASS) / "muninn" / "ui" / "fonts"
    _ASSETS_DIR = Path(sys._MEIPASS) / "muninn" / "ui" / "assets"
    _TEMPLATES_DIR = Path(sys._MEIPASS) / "muninn" / "ui" / "templates"
    _SCANS_DIR = Path(sys._MEIPASS) / "muninn" / "ui" / "scans"

_FONT_FILES = [
    "Orbitron-Variable.ttf",
    "Rajdhani-Regular.ttf",
    "Rajdhani-SemiBold.ttf",
    "JetBrainsMono-Regular.ttf",
]

_fonts_loaded = False


def load_fonts():
    """Load bundled fonts into QFontDatabase. Must be called AFTER QApplication creation."""
    global _fonts_loaded
    if _fonts_loaded:
        return True

    from PyQt6.QtGui import QFontDatabase

    all_ok = True
    for fname in _FONT_FILES:
        fpath = _FONTS_DIR / fname
        if not fpath.exists():
            warnings.warn(f"Muninn UI: font file missing: {fpath}")
            all_ok = False
            continue
        result = QFontDatabase.addApplicationFont(str(fpath))
        if result == -1:
            warnings.warn(f"Muninn UI: failed to load font: {fpath}")
            all_ok = False

    _fonts_loaded = True
    return all_ok


def get_font_families():
    """Return dict of loaded font family names for verification."""
    from PyQt6.QtGui import QFontDatabase
    families = QFontDatabase.families()
    return {
        "orbitron": any("Orbitron" in f for f in families),
        "rajdhani": any("Rajdhani" in f for f in families),
        "jetbrains_mono": any("JetBrains Mono" in f for f in families),
    }
