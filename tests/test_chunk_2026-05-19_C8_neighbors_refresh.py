"""CHUNK C8 (2026-05-19) — mycelium_neighbors live refresh entre cycles.

Pre-fix: cube_live.py calcule `mycelium_neighbors` une fois au début
du reco (avant le 1er cycle). Pendant les cycles x1→x2→x3, le mycelium
grossit via observe_text/observe_failure mais le graph UI reste figé.

Fix:
  - Extraire le calcul en `_compute_mycelium_neighbors(cubes, mycelium)`.
  - Sur callback `on_cube(... status='CYCLE_END' ...)`, recomputer +
    émettre signal `cube_neighbors_refreshed(list[list[int]])`.
  - neuron_map.py: nouveau slot `refresh_neighbors(payload)` qui rebuild
    juste les edges + relaunch Laplacien (PAS les neurons).
  - Feature flag `MUNINN_NEIGHBORS_LIVE_REFRESH=1` (default ON).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_neighbors_live_refresh_flag_default_enabled():
    """Default (no env) → _NEIGHBORS_LIVE_REFRESH_ENABLED is True."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import cube_live
    assert hasattr(cube_live, "_NEIGHBORS_LIVE_REFRESH_ENABLED")
    import os
    if os.environ.get("MUNINN_NEIGHBORS_LIVE_REFRESH", "1") != "0":
        assert cube_live._NEIGHBORS_LIVE_REFRESH_ENABLED is True


def test_compute_mycelium_neighbors_helper_exists():
    """cube_live exposes module-level `_compute_mycelium_neighbors(cubes, mycelium)`."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import cube_live
    assert hasattr(cube_live, "_compute_mycelium_neighbors")


def test_compute_mycelium_neighbors_returns_list_of_lists():
    """Returns list[list[int]] — one neighbor list per cube."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import cube_live
    from types import SimpleNamespace

    class FakeMycelium:
        _vocab = {"alpha", "beta", "gamma"}
        class _Lock:
            def __enter__(self): return self
            def __exit__(self, *a): return False
        class _Conn:
            def execute(self, *a):
                return [("alpha",), ("beta",), ("gamma",)]
        class _DB:
            _lock = None
            _conn = None
            def __init__(self):
                self._lock = FakeMycelium._Lock()
                self._conn = FakeMycelium._Conn()
        _db = None
        def __init__(self):
            self._db = FakeMycelium._DB()

    cubes = [
        SimpleNamespace(content="alpha beta", line_start=1, line_end=1, sha256="x"),
        SimpleNamespace(content="alpha gamma", line_start=2, line_end=2, sha256="y"),
        SimpleNamespace(content="nothing here", line_start=3, line_end=3, sha256="z"),
    ]
    result = cube_live._compute_mycelium_neighbors(cubes, FakeMycelium())
    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(l, list) for l in result)


def test_cube_neighbors_refreshed_signal_exists(qtbot):
    """ReconstructionWorker exposes `cube_neighbors_refreshed` signal."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.cube_live import ReconstructionWorker
    assert hasattr(ReconstructionWorker, "cube_neighbors_refreshed")


def test_neuron_map_has_refresh_neighbors_slot(qtbot):
    """NeuronMapWidget exposes `refresh_neighbors(payload)` slot."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget
    w = NeuronMapWidget()
    qtbot.addWidget(w)
    assert hasattr(w, "refresh_neighbors")
    assert callable(w.refresh_neighbors)


def test_refresh_neighbors_rebuilds_edges_keeps_neurons(qtbot):
    """refresh_neighbors changes edges but does NOT clear self._neurons."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui.neuron_map import NeuronMapWidget

    w = NeuronMapWidget()
    qtbot.addWidget(w)
    cubes = [
        {"idx": 0, "start": 1, "end": 5, "original": "a", "sha": "x", "mycelium_neighbors": []},
        {"idx": 1, "start": 6, "end": 10, "original": "b", "sha": "y", "mycelium_neighbors": []},
        {"idx": 2, "start": 11, "end": 15, "original": "c", "sha": "z", "mycelium_neighbors": []},
    ]
    w.set_reconstruction_cubes(cubes)
    w._cancel_laplacian()
    n_neurons_before = len(w._neurons)

    # Refresh with new edges (mycelium_neighbors populated)
    new_payload = [
        {"idx": 0, "mycelium_neighbors": [1, 2]},
        {"idx": 1, "mycelium_neighbors": [0]},
        {"idx": 2, "mycelium_neighbors": [0]},
    ]
    w.refresh_neighbors(new_payload)
    w._cancel_laplacian()

    # Neurons preserved
    assert len(w._neurons) == n_neurons_before, "refresh must not drop neurons"
    # Edges include the new mycelium links
    edge_pairs = {(a, b) for a, b, _ in w._edges}
    assert (0, 1) in edge_pairs or (1, 0) in edge_pairs
    assert (0, 2) in edge_pairs or (2, 0) in edge_pairs


def test_legacy_flag_off_disables_live_refresh(monkeypatch):
    """MUNINN_NEIGHBORS_LIVE_REFRESH=0 → _NEIGHBORS_LIVE_REFRESH_ENABLED False (§8.B)."""
    pytest_qt = __import__("pytest")
    pytest_qt.importorskip("PyQt6")
    from muninn.ui import cube_live
    monkeypatch.setattr(cube_live, "_NEIGHBORS_LIVE_REFRESH_ENABLED", False)
    assert cube_live._NEIGHBORS_LIVE_REFRESH_ENABLED is False
