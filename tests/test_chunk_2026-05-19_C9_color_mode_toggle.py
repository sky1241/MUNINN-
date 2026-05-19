"""CHUNK C9 (2026-05-19) — UI toggle Mycelium↔Reconstruction.

Pre-fix: NeuronMapWidget paints by `n.degree` only — pas de moyen de
basculer entre "couleur par mycelium degree" et "couleur par reco NCD".
ForestToggle existe mais n'est pas instancié; le `toggle_mode` action
du command palette est un no-op (`lambda: None`).

Fix:
  - NeuronMapWidget._color_mode = "mycelium" (default).
  - set_color_mode(mode: str) — accepte "mycelium"|"reconstruction".
  - toggle_color_mode() — bascule entre les deux.
  - Persistance via muninn.ui.ai_config (clé "neuron_color_mode").
  - main_window.py `toggle_mode` action → neuron_panel.toggle_color_mode().
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _isolate_ui_config(tmp_path, monkeypatch):
    """Redirect ~/.muninn/ui_config.json to a tmp_path so persistence
    doesn't leak between tests (and doesn't clobber Sky's real config)."""
    _pytest.importorskip("PyQt6")
    from muninn.ui import ai_config
    monkeypatch.setattr(ai_config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(ai_config, "_CONFIG_FILE", tmp_path / "ui_config.json")
    yield


def test_color_mode_default_is_mycelium(qtbot):
    """Fresh widget defaults to mycelium color mode."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    assert hasattr(w, "_color_mode")
    assert w._color_mode == "mycelium"


def test_set_color_mode_to_reconstruction(qtbot):
    """set_color_mode('reconstruction') is accepted."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.set_color_mode("reconstruction")
    assert w._color_mode == "reconstruction"


def test_set_color_mode_invalid_ignored(qtbot):
    """Invalid mode value is silently ignored (stays mycelium)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.set_color_mode("nonsense")
    assert w._color_mode == "mycelium"


def test_toggle_color_mode_flips(qtbot):
    """toggle_color_mode() switches between the two modes."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    assert w._color_mode == "mycelium"
    w.toggle_color_mode()
    assert w._color_mode == "reconstruction"
    w.toggle_color_mode()
    assert w._color_mode == "mycelium"


def test_color_mode_persists_via_ui_config(qtbot, tmp_path, monkeypatch):
    """Setting the mode writes 'neuron_color_mode' to ui_config.json."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    fake_config = tmp_path / "ui_config.json"
    from muninn.ui import ai_config
    monkeypatch.setattr(ai_config, "_CONFIG_FILE", fake_config)
    monkeypatch.setattr(ai_config, "_CONFIG_DIR", tmp_path)

    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    w.set_color_mode("reconstruction")

    assert fake_config.exists(), "ui_config.json should be created"
    data = json.loads(fake_config.read_text())
    assert data.get("neuron_color_mode") == "reconstruction"


def test_color_mode_loaded_at_init(qtbot, tmp_path, monkeypatch):
    """If ui_config.json already has a mode, widget loads it at init."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    fake_config = tmp_path / "ui_config.json"
    fake_config.write_text(json.dumps({"neuron_color_mode": "reconstruction"}))
    from muninn.ui import ai_config
    monkeypatch.setattr(ai_config, "_CONFIG_FILE", fake_config)
    monkeypatch.setattr(ai_config, "_CONFIG_DIR", tmp_path)

    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    assert w._color_mode == "reconstruction"


def test_color_mode_toggle_widget_exists(qtbot):
    """ColorModeToggle widget exists in muninn.ui.forest."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import forest
    assert hasattr(forest, "ColorModeToggle")
    w = forest.ColorModeToggle()
    qtbot.addWidget(w)
    assert hasattr(w, "mode_changed")
    assert hasattr(w, "toggle")
    assert hasattr(w, "mode")
    assert w.mode == "mycelium"


def test_color_mode_toggle_emits_signal(qtbot):
    """ColorModeToggle.toggle() emits mode_changed."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.forest import ColorModeToggle
    w = ColorModeToggle()
    qtbot.addWidget(w)
    received = []
    w.mode_changed.connect(received.append)
    w.toggle()
    assert received == ["reconstruction"]
    w.toggle()
    assert received == ["reconstruction", "mycelium"]


def test_palette_toggle_mode_calls_color_toggle(qtbot):
    """MainWindow `toggle_mode` palette action flips neuron color mode."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.neuron_panel._color_mode == "mycelium"
    win._on_palette_action("toggle_mode")
    assert win.neuron_panel._color_mode == "reconstruction"
    win._on_palette_action("toggle_mode")
    assert win.neuron_panel._color_mode == "mycelium"


def test_main_window_has_color_mode_toggle(qtbot):
    """MainWindow instantiates _color_mode_toggle as an overlay."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.main_window import MainWindow
    from muninn.ui.forest import ColorModeToggle
    win = MainWindow()
    qtbot.addWidget(win)
    assert hasattr(win, "_color_mode_toggle")
    assert isinstance(win._color_mode_toggle, ColorModeToggle)
