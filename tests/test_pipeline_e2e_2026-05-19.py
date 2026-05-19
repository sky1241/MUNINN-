"""CHUNK C13 (2026-05-19) — E2E pipeline tests.

End-to-end proofs that all C0-C12 chunks wire together correctly :
- subdivide_file accepts mycelium kwarg (C7)
- reconstruct_adaptive accepts forge_root + on_cube_extras kwargs (C6/C10)
- pipeline_trace events fire for the wired paths
- record_cycles batch writes work
- healed cubes set survives across runs (C3)

These tests use MockLLMProvider — no Ollama daemon, no API calls. They
run in CI by default.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest


@pytest.fixture
def btree_go_path() -> Path:
    """Path to the canonical Go test corpus file."""
    p = REPO_ROOT / "tests" / "cube_corpus" / "btree_google.go"
    if not p.exists():
        pytest.skip(f"corpus missing: {p}")
    return p


@pytest.fixture
def isolated_repo(tmp_path: Path):
    """A scratch .muninn/ directory for the test; mycelium, traces and
    cube store all live under tmp_path."""
    (tmp_path / ".muninn").mkdir(parents=True, exist_ok=True)
    yield tmp_path


def test_subdivide_file_accepts_mycelium_kwarg(btree_go_path, isolated_repo):
    """C7 wire proof — subdivide_file accepts mycelium kwarg without error."""
    from cube import subdivide_file
    from mycelium import Mycelium
    mycelium = Mycelium(isolated_repo)
    content = btree_go_path.read_text(encoding="utf-8")
    cubes = subdivide_file(str(btree_go_path), content,
                           target_tokens=112, level=0,
                           mycelium=mycelium)
    assert cubes, "subdivide_file should return at least one cube"
    # Each cube must carry line_start/line_end + content.
    for c in cubes[:5]:
        assert c.line_start >= 1
        assert c.line_end >= c.line_start
        assert c.content
    try:
        mycelium.close()
    except Exception:
        pass


def test_reconstruct_adaptive_accepts_new_kwargs(btree_go_path, isolated_repo):
    """C6 + C10 wire proof — reconstruct_adaptive accepts forge_root +
    on_cube_extras without TypeError."""
    from cube_providers import reconstruct_adaptive, MockLLMProvider
    from mycelium import Mycelium

    mycelium = Mycelium(isolated_repo)
    # Use only the first ~500 lines so the test runs fast under Mock.
    content = "\n".join(btree_go_path.read_text(encoding="utf-8").split("\n")[:200])

    cube_events: list = []
    cube_extras: list = []

    def on_cube(cycle, level, idx, status, attempts, ncd):
        cube_events.append((cycle, level, idx, status))

    def on_cube_extras(idx, gap_lines, unknown_idents):
        cube_extras.append((idx, len(gap_lines), len(unknown_idents)))

    result = reconstruct_adaptive(
        str(btree_go_path), content, MockLLMProvider(),
        base_tokens=112,
        max_cycles=1,
        attempts_per_cube=1,
        mycelium=mycelium,
        forge_root=str(isolated_repo),
        on_cube=on_cube,
        on_cube_extras=on_cube_extras,
    )
    # Mock provider produces deterministic stubs — exact counts depend
    # on the file. The point is: no kwargs blow up + callbacks fire.
    assert isinstance(result, dict)
    assert "total_cubes" in result
    assert "cycles" in result
    assert cube_events, "on_cube should fire at least once"
    # on_cube_extras may or may not fire depending on Mock output (gap
    # extraction needs ast_hints from the cube). Don't assert it fires
    # — just that the kwarg was accepted (passing this far proves it).
    try:
        mycelium.close()
    except Exception:
        pass


def test_record_cycles_batch_persists(isolated_repo):
    """C2 wire proof — record_cycles writes rows readable by get_healed_cubes."""
    from cube import CubeStore
    db_path = isolated_repo / ".muninn" / "test_e2e.db"
    store = CubeStore(str(db_path))

    # Insert 3 successful cycles for cube_X — should be picked up as healed.
    batch = [
        ("cube_X", 1, True, "stub", 0.0),
        ("cube_X", 2, True, "stub", 0.0),
        ("cube_X", 3, True, "stub", 0.0),
        ("cube_Y", 1, False, "stub", 0.0),
    ]
    store.record_cycles(batch)
    healed = store.get_healed_cubes(min_success_count=3, min_success_rate=1.0)
    assert "cube_X" in healed, "cube_X should be healed after 3 successful cycles"
    assert "cube_Y" not in healed, "cube_Y failed once → not healed"
    store.close()


def test_pipeline_trace_emits_during_reco(btree_go_path, isolated_repo, monkeypatch):
    """C5/C6/C10 wire proof — pipeline_trace events fire during reconstruction.

    CHUNK D7 (2026-05-19 remediation) — durci : pré-D7 ce test ne faisait
    que `assert isinstance(events, list)` (no-op : read_trace_events
    retourne [] sur fichier absent). Post-D7, on asserte qu'au moins
    UN event nommé attendu fire vraiment.

    Events observés runtime sur une vraie session reconstruct_adaptive
    avec MockLLMProvider sur btree_google.go (100 premières lignes) :
      - pipeline.engine.reco.cube_ordering_applied  (C6 fuse_risks wire)
      - pipeline.mycelium.spread.begin  (mycelium spread activation)
      - pipeline.mycelium.spread.end
    """
    # Point pipeline_trace at our isolated repo.
    monkeypatch.setenv("MUNINN_REPO", str(isolated_repo))
    # Force a fresh _resolve_repo cache.
    import importlib
    import pipeline_trace as _pt
    importlib.reload(_pt)

    from cube_providers import reconstruct_adaptive, MockLLMProvider
    from mycelium import Mycelium
    from tests._helpers.pipeline_trace import read_trace_events, has_event

    mycelium = Mycelium(isolated_repo)
    content = "\n".join(btree_go_path.read_text(encoding="utf-8").split("\n")[:100])

    reconstruct_adaptive(
        str(btree_go_path), content, MockLLMProvider(),
        base_tokens=112, max_cycles=1, attempts_per_cube=1,
        mycelium=mycelium,
        forge_root=str(isolated_repo),
    )

    events = read_trace_events(isolated_repo)
    # D7 : assert qu'au moins UN event fire vraiment (pas un no-op).
    assert len(events) > 0, (
        "no pipeline_trace events emitted during reconstruct_adaptive — "
        "trace machinery not wired (D7 regression). Expected events like "
        "pipeline.engine.reco.cube_ordering_applied or "
        "pipeline.mycelium.spread.* to fire."
    )
    event_names = {e.get("event") for e in events}
    # Au minimum un de ces 3 events DOIT fire pour que le wire-claim tienne.
    expected_any = {
        "pipeline.engine.reco.cube_ordering_applied",
        "pipeline.mycelium.spread.begin",
        "pipeline.mycelium.spread.end",
    }
    assert event_names & expected_any, (
        f"expected at least one of {expected_any}, got: {event_names}"
    )
    # Bonus : has_event helper must agree
    assert any(has_event(events, n) for n in expected_any)
    try:
        mycelium.close()
    except Exception:
        pass


def test_pipeline_metrics_match_flag_toggles(btree_go_path, isolated_repo, monkeypatch):
    """C6+C7 wire proof — toggling MUNINN_FUSE_RISKS_ORDERING / MUNINN_SCAN_AWARE_SUBDIVIDE
    changes the flag values observed by the engine. (Pure flag-readback
    check ; deep behavioral diff lives in chunk-specific tests.)"""
    monkeypatch.setenv("MUNINN_FUSE_RISKS_ORDERING", "0")
    monkeypatch.setenv("MUNINN_SCAN_AWARE_SUBDIVIDE", "0")
    import importlib
    import cube_providers as _cp
    import cube as _c
    importlib.reload(_cp)
    importlib.reload(_c)
    assert _cp._FUSE_RISKS_ORDERING_ENABLED is False
    assert _c._SCAN_AWARE_SUBDIVIDE_ENABLED is False

    monkeypatch.setenv("MUNINN_FUSE_RISKS_ORDERING", "1")
    monkeypatch.setenv("MUNINN_SCAN_AWARE_SUBDIVIDE", "1")
    importlib.reload(_cp)
    importlib.reload(_c)
    assert _cp._FUSE_RISKS_ORDERING_ENABLED is True
    assert _c._SCAN_AWARE_SUBDIVIDE_ENABLED is True


def test_recon_result_has_c10_fields():
    """C10 wire proof — ReconstructionResult dataclass has new fields,
    even when instantiated with defaults."""
    from cube_providers import ReconstructionResult
    r = ReconstructionResult(
        cube_id="x", original_sha256="a", reconstruction="",
        reconstruction_sha256="b", exact_match=True,
        ncd_score=0.0, perplexity=0.0, success=True,
    )
    assert r.gap_lines == []
    assert r.unknown_identifiers == []


def test_wave_result_has_c10_fields():
    """C10 wire proof — WaveResult also propagates the new fields."""
    from cube_providers import WaveResult
    w = WaveResult(
        cube_id="x", sha_matched=True, wave_number=1,
        attempt_in_wave=1, total_attempts=1,
        best_ncd=0.0, best_reconstruction="",
    )
    assert w.gap_lines == []
    assert w.unknown_identifiers == []
