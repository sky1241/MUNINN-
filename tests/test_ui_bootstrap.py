"""Tests for B-UI-00: Bootstrap — package, fonts, assets."""

import pytest
from pathlib import Path


def test_import_ui_package():
    """muninn.ui is importable."""
    import muninn.ui
    assert hasattr(muninn.ui, "load_fonts")
    assert hasattr(muninn.ui, "get_font_families")


def test_font_files_exist():
    """All 4 font files are bundled."""
    from muninn.ui import _FONTS_DIR, _FONT_FILES
    for fname in _FONT_FILES:
        fpath = _FONTS_DIR / fname
        assert fpath.exists(), f"Missing font: {fpath}"
        assert fpath.stat().st_size > 1000, f"Font too small: {fpath}"


def test_asset_files_exist():
    """Key asset files are present."""
    from muninn.ui import _ASSETS_DIR
    expected = [
        "node_info_panel.png",
        "node_tooltip_frame_blue.png",
    ]
    for fname in expected:
        fpath = _ASSETS_DIR / fname
        assert fpath.exists(), f"Missing asset: {fpath}"


def test_template_files_exist():
    """Skeleton and position files are present for all 6 families."""
    from muninn.ui import _TEMPLATES_DIR
    families = ["baobab", "buisson", "conifere", "feuillu", "liane", "palmier"]
    for fam in families:
        skel = _TEMPLATES_DIR / f"{fam}_skeleton_sky.json"
        pos = _TEMPLATES_DIR / f"{fam}_positions_1024.txt"
        assert skel.exists(), f"Missing skeleton: {skel}"
        assert pos.exists(), f"Missing positions: {pos}"


def test_scan_files_exist():
    """At least one scan JSON is present."""
    from muninn.ui import _SCANS_DIR
    scans = list(_SCANS_DIR.glob("*.json"))
    assert len(scans) >= 1, "No scan files found"


def test_load_fonts(qapp):
    """Fonts load successfully into QFontDatabase."""
    from muninn.ui import load_fonts, get_font_families
    # Reset state for test
    import muninn.ui
    muninn.ui._fonts_loaded = False

    ok = load_fonts()
    assert ok, "load_fonts() returned False — some fonts failed"

    families = get_font_families()
    assert families["orbitron"], "Orbitron not found in QFontDatabase"
    assert families["rajdhani"], "Rajdhani not found in QFontDatabase"
    assert families["jetbrains_mono"], "JetBrains Mono not found in QFontDatabase"
