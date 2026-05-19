"""CHUNK C11 (2026-05-19) — File line-by-line heatmap view.

Pre-fix : aucune vue line-by-line du fichier reconstruit avec
coloration des gaps. Le DetailPanel (C10) montre les compteurs mais
pas la géographie des lignes ancrées vs imaginées.

Fix :
  - muninn/ui/file_heatmap_view.py : nouveau widget FileHeatmapView
    (QPlainTextEdit read-only + custom gutter colorisé).
  - muninn/ui/cube_live.py : nouveau signal
    file_heatmap_ready(path: str, line_colors: dict).
  - main_window.py : ajout en bottom panel sous le cube 3D (left split).

Mapping couleurs par ligne :
  - "green"  : ligne ancrée (rel_idx PAS dans cube.gap_lines).
  - "red"    : gap (rel_idx dans cube.gap_lines) ET cube fail.
  - "orange" : gap (rel_idx dans cube.gap_lines) ET cube SHA match
               (le LLM a deviné juste sans anchor).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_file_heatmap_view_module_exists():
    """Module muninn.ui.file_heatmap_view importable."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import file_heatmap_view
    assert hasattr(file_heatmap_view, "FileHeatmapView")


def test_file_heatmap_view_is_widget(qtbot):
    """FileHeatmapView is a QWidget that can be instantiated."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.file_heatmap_view import FileHeatmapView
    w = FileHeatmapView()
    qtbot.addWidget(w)
    assert hasattr(w, "load_file")
    assert hasattr(w, "set_line_colors")
    assert hasattr(w, "line_clicked")


def test_set_line_colors_stores_mapping(qtbot):
    """set_line_colors(dict[int, str]) keeps the mapping accessible."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.file_heatmap_view import FileHeatmapView
    w = FileHeatmapView()
    qtbot.addWidget(w)
    w.set_line_colors({1: "green", 2: "red", 3: "orange"})
    assert w._line_colors == {1: "green", 2: "red", 3: "orange"}


def test_load_file_populates_text(qtbot, tmp_path):
    """load_file(path) reads the file and displays it."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    f = tmp_path / "sample.txt"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")
    from muninn.ui.file_heatmap_view import FileHeatmapView
    w = FileHeatmapView()
    qtbot.addWidget(w)
    w.load_file(str(f))
    assert "line1" in w._editor.toPlainText()
    assert "line3" in w._editor.toPlainText()


def test_compute_line_colors_helper_exists():
    """cube_live exposes _compute_line_colors_for_cube helper."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import cube_live
    assert hasattr(cube_live, "_compute_line_colors_for_cube")


def test_compute_line_colors_green_when_no_gap():
    """If gap_lines is empty, all cube lines are green."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.cube_live import _compute_line_colors_for_cube
    # cube spans absolute lines 1..3 (1-indexed)
    colors = _compute_line_colors_for_cube(
        line_start=1, line_end=3,
        gap_lines=[],
        sha_matched=False,
    )
    assert colors == {1: "green", 2: "green", 3: "green"}


def test_compute_line_colors_red_for_gap_fail():
    """Lines in gap_lines and cube fail → red."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.cube_live import _compute_line_colors_for_cube
    colors = _compute_line_colors_for_cube(
        line_start=10, line_end=12,
        gap_lines=[0, 2],          # rel idx 0 + 2 → abs lines 10 + 12
        sha_matched=False,
    )
    assert colors == {10: "red", 11: "green", 12: "red"}


def test_compute_line_colors_orange_for_gap_sha():
    """Lines in gap_lines but cube SHA matched → orange (lucky guess)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.cube_live import _compute_line_colors_for_cube
    colors = _compute_line_colors_for_cube(
        line_start=5, line_end=7,
        gap_lines=[1],             # rel idx 1 → abs line 6
        sha_matched=True,
    )
    assert colors == {5: "green", 6: "orange", 7: "green"}


def test_reconstruction_worker_has_file_heatmap_signal(qtbot):
    """ReconstructionWorker exposes file_heatmap_ready signal."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.cube_live import ReconstructionWorker
    assert hasattr(ReconstructionWorker, "file_heatmap_ready")


def test_terminal_widget_bubbles_file_heatmap_ready(qtbot):
    """TerminalWidget bubbles up the file_heatmap_ready signal."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.terminal import TerminalWidget
    assert hasattr(TerminalWidget, "file_heatmap_ready")


def test_main_window_has_file_heatmap_panel(qtbot):
    """MainWindow exposes _file_heatmap as a child widget."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.main_window import MainWindow
    from muninn.ui.file_heatmap_view import FileHeatmapView
    win = MainWindow()
    qtbot.addWidget(win)
    assert hasattr(win, "_file_heatmap")
    assert isinstance(win._file_heatmap, FileHeatmapView)


def test_line_click_emits_signal(qtbot):
    """Clicking on a line emits line_clicked(int) with 1-indexed line."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.file_heatmap_view import FileHeatmapView
    w = FileHeatmapView()
    qtbot.addWidget(w)
    received = []
    w.line_clicked.connect(received.append)
    # Direct API for testability — wraps the actual click handler
    w._emit_line_clicked(7)
    assert received == [7]
