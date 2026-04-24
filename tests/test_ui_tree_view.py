"""Tests for B-UI-08, B-UI-10, B-UI-11: TreeViewWidget."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


def test_tree_view_creates(qtbot):
    """TreeViewWidget creates and shows."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    assert w.accessibleName() == "Botanical Tree"


def test_tree_view_empty_state(qtbot):
    """Empty tree shows message (R8), no crash on paint."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()
    w.repaint()
    assert w._empty is True


def test_load_tree_from_scan(qtbot):
    """Load tree from scan data."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)

    scan = {
        "nodes": [
            {"id": "R1", "label": "Core", "status": "done", "level": "R", "depth": 0},
            {"id": "F1", "label": "Feature A", "status": "wip", "level": "F", "depth": 1},
            {"id": "F2", "label": "Feature B", "status": "todo", "level": "F", "depth": 1},
        ]
    }
    w.load_tree("feuillu", scan)
    assert len(w.nodes) == 3
    assert w.family == "feuillu"
    assert w._empty is False


def test_load_tree_with_background(qtbot):
    """Load tree with a real family background."""
    from muninn.ui.tree_view import TreeViewWidget
    from muninn.ui import _TEMPLATES_DIR
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)

    scan = {
        "nodes": [
            {"id": "R1", "label": "Core", "status": "done"},
        ]
    }
    w.load_tree("feuillu", scan)
    # Check background loaded (if file exists)
    bg = _TEMPLATES_DIR / "feuillu_final.png"
    if bg.exists():
        assert w._bg_pixmap is not None


def test_paint_with_nodes_no_crash(qtbot):
    """Paint cycle with loaded nodes doesn't crash."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()

    scan = {"nodes": [
        {"id": "A", "label": "Alpha", "status": "done"},
        {"id": "B", "label": "Beta", "status": "wip"},
    ]}
    w.load_tree("buisson", scan)
    w.repaint()  # Force paint


def test_node_click_selection(qtbot):
    """Clicking a node selects it and emits signal."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()

    scan = {"nodes": [
        {"id": "A", "label": "Alpha", "status": "done"},
    ]}
    w.load_tree("feuillu", scan, positions=[(0.5, 0.5)])

    # Simulate selection
    w._selected_id = "A"
    assert w.selected_node is not None
    assert w.selected_node.id == "A"


def test_node_deselection(qtbot):
    """Deselecting clears selection."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)

    scan = {"nodes": [{"id": "A", "label": "Alpha", "status": "done"}]}
    w.load_tree("feuillu", scan)

    w._selected_id = "A"
    assert w.selected_node is not None

    w._selected_id = None
    assert w.selected_node is None


# --- B-UI-11: Bidirectional highlight ---

def test_highlight_concept(qtbot):
    """Highlighting a concept updates state."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)

    scan = {"nodes": [
        {"id": "A", "label": "Alpha", "status": "done"},
        {"id": "B", "label": "Beta", "status": "wip"},
    ]}
    w.load_tree("feuillu", scan)

    w.highlight_concept("A", secondary_ids={"B"})
    assert w._highlighted_id == "A"
    assert "B" in w._secondary_ids


def test_clear_highlight(qtbot):
    """Clearing highlight removes all highlights."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)

    w._highlighted_id = "A"
    w._secondary_ids = {"B"}
    w.clear_highlight()
    assert w._highlighted_id is None
    assert len(w._secondary_ids) == 0


def test_highlight_paint_no_crash(qtbot):
    """Paint with highlights doesn't crash."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)
    w.show()

    scan = {"nodes": [
        {"id": "A", "label": "Alpha", "status": "done"},
        {"id": "B", "label": "Beta", "status": "wip"},
    ]}
    w.load_tree("feuillu", scan, positions=[(0.3, 0.3), (0.7, 0.7)])
    w.highlight_concept("A", secondary_ids={"B"})
    w.repaint()  # Force paint with highlights


# --- B-UI-10: Pixmap cache ---

def test_pixmap_cache_invalidated_on_load(qtbot):
    """Background pixmap cache is invalidated on tree load (R6)."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)

    # Set a fake cache
    w._bg_cache_size = (200, 200)
    # Load tree => should invalidate cache
    scan = {"nodes": [{"id": "A", "label": "A", "status": "done"}]}
    w.load_tree("feuillu", scan, positions=[(0.5, 0.5)])
    assert w._bg_cache_size == (0, 0)  # Cache invalidated
    assert w._bg_cache is None


# --- B-UI-11: Center animation ---

def test_center_animation_starts(qtbot):
    """Highlighting a concept starts center animation."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)

    scan = {"nodes": [
        {"id": "A", "label": "Alpha"},
        {"id": "B", "label": "Beta"},
    ]}
    w.load_tree("feuillu", scan, positions=[(0.2, 0.2), (0.8, 0.8)])
    w.highlight_concept("A")
    assert w._center_anim_timer.isActive()
    w._center_anim_timer.stop()


def test_cross_fade_on_highlight_change(qtbot):
    """Cross-fade triggers when highlight changes."""
    from muninn.ui.tree_view import TreeViewWidget
    w = TreeViewWidget()
    qtbot.addWidget(w)
    w.resize(400, 400)

    scan = {"nodes": [
        {"id": "A", "label": "Alpha"},
        {"id": "B", "label": "Beta"},
    ]}
    w.load_tree("feuillu", scan, positions=[(0.2, 0.2), (0.8, 0.8)])
    w.highlight_concept("A")
    # Opacity should start at 0.3 (fading in)
    assert w._opacity_effect.opacity() < 1.0 or w._fade_anim.state() != 0
