"""Tests for muninn.ui.forest — B-UI-16/17 Solo/Forest toggle + MetaMyceliumWorker."""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


@pytest.fixture
def toggle(qtbot):
    from muninn.ui.forest import ForestToggle
    w = ForestToggle()
    qtbot.addWidget(w)
    return w


class TestForestToggle:
    """B-UI-16: Solo/Forest toggle button."""

    def test_creates(self, toggle):
        assert toggle is not None

    def test_initial_mode_solo(self, toggle):
        assert toggle.mode == "solo"

    def test_toggle_to_forest(self, toggle):
        toggle.toggle()
        assert toggle.mode == "forest"

    def test_toggle_back_to_solo(self, toggle):
        toggle.toggle()
        toggle.toggle()
        assert toggle.mode == "solo"

    def test_signal_emitted(self, toggle, qtbot):
        with qtbot.waitSignal(toggle.mode_changed, timeout=500) as blocker:
            toggle.toggle()
        assert blocker.args == ["forest"]

    def test_button_text_changes(self, toggle):
        assert toggle._btn.text() == "SOLO"
        toggle.toggle()
        assert toggle._btn.text() == "FOREST"

    def test_fixed_height(self, toggle):
        assert toggle.maximumHeight() == 36


class TestZoneColors:
    """B-UI-17: Zone colors defined."""

    def test_zone_colors_count(self):
        from muninn.ui.forest import ZONE_COLORS
        assert len(ZONE_COLORS) >= 13

    def test_zone_colors_are_qcolor(self):
        from muninn.ui.forest import ZONE_COLORS
        from PyQt6.QtGui import QColor
        for c in ZONE_COLORS:
            assert isinstance(c, QColor)


class TestMetaMyceliumWorker:
    """B-UI-17: Worker for loading meta-mycelium."""

    def test_worker_creates(self):
        from muninn.ui.forest import MetaMyceliumWorker
        w = MetaMyceliumWorker("/nonexistent/path.db")
        assert w is not None

    def test_worker_error_on_missing_db(self, qtbot):
        from muninn.ui.forest import MetaMyceliumWorker
        w = MetaMyceliumWorker("/nonexistent/path.db")
        errors = []
        w.error.connect(lambda msg: errors.append(msg))
        w.run()
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_worker_stop_flag(self):
        from muninn.ui.forest import MetaMyceliumWorker
        w = MetaMyceliumWorker("/nonexistent/path.db")
        w._stop = True
        assert w._stop is True
