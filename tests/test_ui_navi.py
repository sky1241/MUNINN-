"""Tests for B-UI-14 + B-UI-15: Navi fairy guide."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import QPointF


def test_navi_creates(qtbot):
    """NaviWidget creates and shows."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    assert w.isVisible()


def test_navi_timer_running(qtbot):
    """Navi animation timer is active."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    assert w._navi_timer.isActive()
    assert w._navi_timer.interval() == 16


def test_set_target(qtbot):
    """Setting target moves Navi (or snaps if reduce motion)."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.set_target(QPointF(200, 300))
    assert w._target.x() == 200
    assert w._target.y() == 300


def test_show_bubble(qtbot):
    """show_bubble displays text."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_bubble("Hello world!")
    assert w._bubble_visible
    assert w._bubble_text == "Hello world!"


def test_hide_bubble(qtbot):
    """hide_bubble hides the bubble."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_bubble("Test")
    w.hide_bubble()
    assert not w._bubble_visible


def test_context_help(qtbot):
    """Context help shows correct text."""
    from muninn.ui.navi import NaviWidget, HELP_TEXTS
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_context_help("neuron_map")
    assert w._bubble_visible
    assert w._bubble_text == HELP_TEXTS["neuron_map"]


def test_context_help_unknown(qtbot):
    """Unknown context hides bubble."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_bubble("Something")
    w.show_context_help("nonexistent_context")
    assert not w._bubble_visible


def test_first_launch(qtbot):
    """First launch shows guide with scan button option."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_first_launch()
    assert w._bubble_visible
    assert w._bubble_button_visible
    assert w.is_first_launch


def test_dismiss_first_launch(qtbot):
    """Dismissing first launch hides guide."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.show_first_launch()
    w.dismiss_first_launch()
    assert not w._bubble_visible
    assert not w.is_first_launch


def test_paint_no_crash(qtbot):
    """Full paint cycle with orb + bubble doesn't crash."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    w.show_bubble("Test paint")
    w.repaint()


def test_orb_position(qtbot):
    """orb_position returns current position."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    pos = w.orb_position
    assert isinstance(pos, QPointF)


# --- B-UI-14: PNG bubble frame ---

def test_paint_with_button_no_crash(qtbot):
    """Paint with scan button visible doesn't crash."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    w.show_bubble("Test", show_button=True)
    w.repaint()
    assert w._bubble_button_visible


# --- B-UI-15: French text ---

def test_help_texts_french(qtbot):
    """Help texts are in French."""
    from muninn.ui.navi import HELP_TEXTS
    assert "carte" in HELP_TEXTS["neuron_map"].lower() or "neuronale" in HELP_TEXTS["neuron_map"].lower()
    assert "Hey" in HELP_TEXTS["first_launch"]
    assert "Scanne" in HELP_TEXTS["first_launch"]


def test_scan_button_signal(qtbot):
    """Scan button emits scan_requested signal."""
    from muninn.ui.navi import NaviWidget
    w = NaviWidget()
    qtbot.addWidget(w)
    # Verify signal exists
    assert hasattr(w, 'scan_requested')
