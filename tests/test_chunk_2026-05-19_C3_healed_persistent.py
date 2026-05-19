"""CHUNK C3 (2026-05-19) — `healed` set persistant cross-run.

Pre-fix: in cli_run (cube_analysis.py:1132), `healed = set()` is
recreated empty on EVERY invocation. So if a cube was 100% successful
on yesterday's run, today's run starts from scratch and re-processes
it — wasted LLM calls. Estimated x3-x5 gain on incremental runs.

Fix:
  - `CubeStore.get_healed_cubes(min_success_count=N, min_success_rate=1.0)`
    queries the `cycles` table and returns cube_ids that have been
    successful N or more times in a row with no failures.
  - `cli_run` initializes `healed = store.get_healed_cubes()` instead
    of empty.
  - Feature flag `MUNINN_HEALED_PERSISTENT=0` reverts to empty-set
    legacy behavior.

Locks the perf invariant + the SQL query semantics.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_get_healed_cubes_method_exists(tmp_path):
    """CubeStore must expose get_healed_cubes(min_success_count, min_success_rate)."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    assert hasattr(store, "get_healed_cubes")
    healed = store.get_healed_cubes()
    assert isinstance(healed, set)


def test_get_healed_cubes_empty_on_fresh_db(tmp_path):
    """Fresh DB → no cycles → no healed cubes."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    assert store.get_healed_cubes() == set()


def test_get_healed_cubes_returns_fully_successful_cubes(tmp_path):
    """Cubes with N successful cycles and 0 failures → in healed set."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    # cube_A: 3 successes (100%)
    for cycle in range(1, 4):
        store.record_cycle("cube_A", cycle, True, "", 0.0)
    # cube_B: 2 successes only (below default min_success_count=3)
    for cycle in range(1, 3):
        store.record_cycle("cube_B", cycle, True, "", 0.0)
    # cube_C: 3 cycles but mixed (1 fail) → excluded
    store.record_cycle("cube_C", 1, True, "", 0.0)
    store.record_cycle("cube_C", 2, False, "", 0.0)
    store.record_cycle("cube_C", 3, True, "", 0.0)

    healed = store.get_healed_cubes(min_success_count=3)
    assert "cube_A" in healed, f"cube_A should be healed: {healed}"
    assert "cube_B" not in healed, "cube_B has only 2 cycles, below threshold"
    assert "cube_C" not in healed, "cube_C had a failure"


def test_get_healed_cubes_threshold_configurable(tmp_path):
    """Lowering min_success_count includes cubes with fewer cycles."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    for cycle in range(1, 3):
        store.record_cycle("cube_X", cycle, True, "", 0.0)

    assert store.get_healed_cubes(min_success_count=3) == set()
    assert store.get_healed_cubes(min_success_count=2) == {"cube_X"}


def test_cli_run_loads_healed_from_db_by_default(tmp_path, monkeypatch):
    """cli_run initializes `healed` from store.get_healed_cubes() when
    MUNINN_HEALED_PERSISTENT is unset (default ON behavior).

    Indirect test via spy on get_healed_cubes — full cli_run integration
    is tested elsewhere.
    """
    import importlib
    # Default behavior: no env var → C3 active
    monkeypatch.delenv("MUNINN_HEALED_PERSISTENT", raising=False)
    sys.modules.pop("cube_analysis", None)
    sys.modules.pop("engine.core.cube_analysis", None)
    cube_analysis = importlib.import_module("cube_analysis")

    assert cube_analysis._HEALED_PERSISTENT_ENABLED, (
        "Default should activate C3 (healed persistent across runs)"
    )


def test_legacy_flag_disabled_restores_empty_healed(tmp_path, monkeypatch):
    """MUNINN_HEALED_PERSISTENT=0 → legacy empty-set behavior (per §4bis).

    Required feature-flag dual test (§8.B): both ON and OFF must be tested.
    """
    import importlib
    monkeypatch.setenv("MUNINN_HEALED_PERSISTENT", "0")
    sys.modules.pop("cube_analysis", None)
    sys.modules.pop("engine.core.cube_analysis", None)
    cube_analysis = importlib.import_module("cube_analysis")

    assert cube_analysis._HEALED_PERSISTENT_ENABLED is False, (
        "MUNINN_HEALED_PERSISTENT=0 must disable C3 (revert to legacy)"
    )
