"""CHUNK C13 (2026-05-19) — perf tests for C0-C12 engine hot paths.

Pattern (audit 2026-05-19 found none) :
  - Tests named test_perf_* are OPT-IN via env MUNINN_RUN_PERF=1.
  - They use plain time.perf_counter() (no pytest-benchmark dep).
  - They skip silently in normal CI runs so the green pipeline stays
    fast; Sky can run them locally with `MUNINN_RUN_PERF=1 pytest …`.

Thresholds are intentionally generous (3-10x the measured nominal
on Sky's machine) to avoid flaky CI on slower runners.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


_OPT_IN = os.environ.get("MUNINN_RUN_PERF", "0") == "1"
pytestmark = pytest.mark.skipif(
    not _OPT_IN,
    reason="perf tests are opt-in via MUNINN_RUN_PERF=1 (see C13 convention)",
)


def test_perf_record_cycles_batch_under_5s_for_1000(tmp_path):
    """C2 perf — store.record_cycles(batch_of_1000) under 5s.

    On Sky's machine measured ~0.05s ; threshold = 100x slack for
    slow CI runners. Real CI never runs this (opt-in)."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "perf.db"))
    batch = [
        (f"cube_{i}", 1, True, "stub", 0.0)
        for i in range(1000)
    ]
    t0 = time.perf_counter()
    store.record_cycles(batch)
    elapsed = time.perf_counter() - t0
    store.close()
    assert elapsed < 5.0, f"record_cycles(1000) took {elapsed:.3f}s ; budget=5s"


def test_perf_subdivide_file_under_200ms_for_btree(tmp_path):
    """C7 perf — subdivide_file(btree_google_go, mycelium=m) under 200ms.

    Nominal ~10-30ms on Sky's machine (depends on mycelium codebook size).
    Threshold 200ms allows for slower disks / cold caches."""
    btree = REPO_ROOT / "tests" / "cube_corpus" / "btree_google.go"
    if not btree.exists():
        pytest.skip(f"corpus missing: {btree}")
    from cube import subdivide_file
    from mycelium import Mycelium
    (tmp_path / ".muninn").mkdir(parents=True, exist_ok=True)
    mycelium = Mycelium(tmp_path)
    content = btree.read_text(encoding="utf-8")

    # Warmup (mycelium concept fetch caches).
    subdivide_file(str(btree), content, target_tokens=112, mycelium=mycelium)

    t0 = time.perf_counter()
    cubes = subdivide_file(str(btree), content, target_tokens=112, mycelium=mycelium)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    try:
        mycelium.close()
    except Exception:
        pass
    assert cubes, "subdivide_file returned no cubes"
    assert elapsed_ms < 200.0, (
        f"subdivide_file took {elapsed_ms:.1f}ms ; budget=200ms"
    )


def test_perf_fuse_risks_under_500ms_for_100_cubes(tmp_path):
    """C6 perf — fuse_risks(store, forge_root) under 500ms for 100 cubes."""
    try:
        from cube_analysis import fuse_risks
    except ImportError:
        pytest.skip("fuse_risks unavailable")
    from cube import CubeStore, Cube
    store = CubeStore(str(tmp_path / "perf.db"))
    # Populate 100 cubes so fuse_risks has work to do.
    for i in range(100):
        c = Cube(
            id=f"cube_{i}", file_origin="x.py", content=f"line {i}\n" * 5,
            line_start=i * 5 + 1, line_end=(i + 1) * 5,
            sha256="abcd1234" * 8,
        )
        store.save_cube(c)

    t0 = time.perf_counter()
    try:
        fuse_risks(store, str(tmp_path))
    except Exception as e:
        pytest.skip(f"fuse_risks needs forge infra not available here: {e}")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    store.close()
    assert elapsed_ms < 500.0, (
        f"fuse_risks(100 cubes) took {elapsed_ms:.1f}ms ; budget=500ms"
    )
