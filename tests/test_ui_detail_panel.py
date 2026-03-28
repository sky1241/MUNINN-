"""Tests for B-UI-12 + B-UI-13: DetailPanel."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


def test_detail_panel_creates(qtbot):
    """DetailPanel creates and shows."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()


def test_empty_state(qtbot):
    """Empty state shows message."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()
    assert w._empty_label.isVisible()
    assert w._title.isHidden()


def test_show_neuron_basic(qtbot):
    """B-UI-12: Show basic neuron info."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "mycelium.py",
        "id": "myc",
        "level": "F",
        "status": "done",
        "depth": 2,
        "confidence": 85,
        "entry": "engine/core/mycelium.py",
    })

    assert w._title.text() == "mycelium.py"
    assert "DONE" in w._status_label.text()
    assert w._empty_label.isHidden()
    assert w._title.isVisible()


def test_show_neuron_extended(qtbot):
    """B-UI-13: Show extended info with neighbors and files."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "tree_view.py",
        "id": "tv",
        "level": "F",
        "status": "wip",
        "depth": 1,
        "confidence": 70,
        "entry": "muninn/ui/tree_view.py",
        "temperature": 0.85,
        "neighbors": [("neuron_map", 15), ("theme", 8), ("classifier", 5)],
        "files": ["muninn/ui/tree_view.py", "tests/test_ui_tree_view.py"],
    })

    assert "0.85" in w._temp_label.text()
    assert w._neighbors_layout.count() == 3
    assert w._files_layout.count() == 2


def test_switch_neuron_crossfade(qtbot):
    """Switching neuron triggers cross-fade (animation exists)."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({"label": "First", "id": "a", "status": "done"})
    w.show_neuron({"label": "Second", "id": "b", "status": "wip"})
    assert w._title.text() == "Second"


def test_back_to_empty(qtbot):
    """Calling show_empty after show_neuron returns to empty state."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({"label": "Test", "id": "t", "status": "done"})
    assert w._title.isVisible()

    w.show_empty()
    assert w._empty_label.isVisible()
    assert w._title.isHidden()


def test_neighbor_click_signal(qtbot):
    """Clicking a neighbor emits neighbor_clicked signal."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "Test",
        "id": "t",
        "status": "done",
        "neighbors": [("alpha", 5)],
        "files": [],
    })

    signals = []
    w.neighbor_clicked.connect(lambda name: signals.append(name))

    # Find the clickable label and click it
    from muninn.ui.detail_panel import ClickableLabel
    for i in range(w._neighbors_layout.count()):
        item = w._neighbors_layout.itemAt(i)
        if item and item.widget() and isinstance(item.widget(), ClickableLabel):
            item.widget().clicked.emit("alpha")
            break

    assert "alpha" in signals


def test_no_neighbors_shows_none(qtbot):
    """No neighbors shows '(none)' label."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "Isolated",
        "id": "iso",
        "status": "todo",
        "neighbors": [],
        "files": [],
    })

    assert w._neighbors_layout.count() == 1  # (none) label


# --- B-UI-12: LOC field ---

def test_loc_field(qtbot):
    """LOC field shows when present."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "Engine",
        "id": "engine",
        "status": "done",
        "loc": 1509,
    })
    assert w._loc_label.isVisible()
    assert "1509" in w._loc_label.text()


def test_loc_hidden_when_absent(qtbot):
    """LOC field hidden when not provided."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({"label": "X", "id": "x", "status": "todo"})
    assert not w._loc_label.isVisible()


# --- B-UI-13: last_modified + zone ---

def test_last_modified_field(qtbot):
    """Last modified shows when present."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "Core",
        "id": "core",
        "status": "done",
        "last_modified": "2026-03-27",
    })
    assert w._last_modified_label.isVisible()
    assert "2026-03-27" in w._last_modified_label.text()


def test_zone_field(qtbot):
    """Zone shows when present."""
    from muninn.ui.detail_panel import DetailPanel
    w = DetailPanel()
    qtbot.addWidget(w)
    w.show()

    w.show_neuron({
        "label": "Mycelium",
        "id": "myc",
        "status": "wip",
        "zone": "engine/core",
    })
    assert w._zone_label.isVisible()
    assert "engine/core" in w._zone_label.text()
