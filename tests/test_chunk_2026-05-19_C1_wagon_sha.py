"""CHUNK C1 (2026-05-19) — BUG WAGON SHA-256.

Pre-fix: in `run_destruction_cycle`, when a cube reconstruction succeeds,
`cube.content = result.reconstruction` replaces the original content but
`cube.sha256` is NEVER updated. The store persists `(cube_id, sha_OLD,
content_NEW, ...)` — incoherent state.

Consequence on cycle 2+: `recon_sha256 = sha256(NEW)` compared to
`cube.sha256 = OLD` → `exact_match` always False → cube re-processed at
every cycle even though it was already healed in cycle 1. Estimated x2-x5
extra LLM calls on multi-cycle runs.

Fix: 1 line in `run_destruction_cycle` after `cube.content = ...`:
    cube.sha256 = sha256_hash(result.reconstruction)

`sha256_hash` is already imported at the top of cube_analysis.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Make engine/core importable
REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _make_cube(content: str = "original code\nline 2\nline 3"):
    """Build a minimal Cube instance with known sha256."""
    from cube import Cube, sha256_hash
    return Cube(
        id="cube_0",
        sha256=sha256_hash(content),
        content=content,
        file_origin="test.py",
        line_start=1,
        line_end=3,
        level=1,
        score=0.0,
        temperature=0.5,
        token_count=10,
    )


def test_cube_sha256_updated_after_successful_reconstruction(tmp_path, monkeypatch):
    """Wagon effect must update BOTH cube.content AND cube.sha256.

    Pre-fix: only content was updated. This test locks the fix.
    """
    from cube import CubeStore, sha256_hash
    from cube_analysis import run_destruction_cycle
    from cube_providers import MockLLMProvider

    original = "original code\nline 2\nline 3"
    reconstructed = "REBUILT code\nline 2\nline 3"

    cube = _make_cube(original)
    original_sha = cube.sha256
    expected_new_sha = sha256_hash(reconstructed)

    db_path = tmp_path / "cube.db"
    store = CubeStore(str(db_path))
    store.save_cube(cube)

    # Mock provider that always returns the reconstructed string.
    provider = MockLLMProvider(responses={"_default": reconstructed})

    # Force the reconstruction to be considered "successful" by patching
    # reconstruct_cube's return value (we don't care about NCD here,
    # just the side effect on cube.sha256).
    from engine.core import cube_providers as cp_module
    real_reconstruct = cp_module.reconstruct_cube

    def fake_reconstruct(cube_in, neighbors, prov, *args, **kwargs):
        return cp_module.ReconstructionResult(
            cube_id=cube_in.id,
            original_sha256=cube_in.sha256,
            reconstruction=reconstructed,
            reconstruction_sha256=sha256_hash(reconstructed),
            exact_match=False,
            ncd_score=0.05,  # below default threshold 0.3 → success
            perplexity=0.1,
            success=True,
        )

    monkeypatch.setattr("cube_analysis.reconstruct_cube", fake_reconstruct)

    healed: set = set()
    results = run_destruction_cycle([cube], store, provider,
                                    cycle_num=1, healed=healed)

    assert len(results) == 1
    assert results[0].success is True
    assert cube.id in healed

    # THE assertion: sha256 must have been updated to match the new content
    assert cube.content == reconstructed, "wagon effect should swap content"
    assert cube.sha256 == expected_new_sha, (
        f"BUG WAGON SHA: cube.sha256 still {cube.sha256[:8]}... "
        f"(expected {expected_new_sha[:8]}... after reconstruction)"
    )
    assert cube.sha256 != original_sha, "sha256 must have changed"


def test_cube_sha256_in_db_matches_new_content(tmp_path, monkeypatch):
    """The persisted cube in the DB must also have the updated sha256.

    The bug was: save_cube(cube) was called WITH the old sha256 still set.
    The DB therefore stored an incoherent (sha_OLD, content_NEW) row.
    """
    from cube import CubeStore, sha256_hash
    from cube_analysis import run_destruction_cycle
    from cube_providers import MockLLMProvider, ReconstructionResult

    cube = _make_cube("orig content")
    reconstructed = "rebuilt content"
    expected_sha = sha256_hash(reconstructed)

    db_path = tmp_path / "cube.db"
    store = CubeStore(str(db_path))
    store.save_cube(cube)

    def fake_reconstruct(cube_in, neighbors, prov, *args, **kwargs):
        return ReconstructionResult(
            cube_id=cube_in.id, original_sha256=cube_in.sha256,
            reconstruction=reconstructed,
            reconstruction_sha256=sha256_hash(reconstructed),
            exact_match=False, ncd_score=0.05, perplexity=0.1, success=True,
        )

    monkeypatch.setattr("cube_analysis.reconstruct_cube", fake_reconstruct)
    run_destruction_cycle([cube], store, MockLLMProvider(),
                          cycle_num=1, healed=set())

    # Read back from DB
    persisted = store.get_cube(cube.id)
    assert persisted is not None
    assert persisted.content == reconstructed
    assert persisted.sha256 == expected_sha, (
        f"DB persisted incoherent sha: {persisted.sha256[:8]}... "
        f"vs content sha {expected_sha[:8]}..."
    )


def test_failed_reconstruction_does_not_update_sha(tmp_path, monkeypatch):
    """Negative case: when reconstruction fails (success=False), the wagon
    effect doesn't fire and the cube sha256 stays untouched.

    Ensures the C1 fix is in the right branch (only on the success path).
    """
    from cube import CubeStore, sha256_hash
    from cube_analysis import run_destruction_cycle
    from cube_providers import MockLLMProvider, ReconstructionResult

    original = "original code"
    cube = _make_cube(original)
    original_sha = cube.sha256

    db_path = tmp_path / "cube.db"
    store = CubeStore(str(db_path))
    store.save_cube(cube)

    def fake_failed(cube_in, neighbors, prov, *args, **kwargs):
        return ReconstructionResult(
            cube_id=cube_in.id, original_sha256=cube_in.sha256,
            reconstruction="garbage that fails",
            reconstruction_sha256=sha256_hash("garbage that fails"),
            exact_match=False, ncd_score=0.9, perplexity=5.0, success=False,
        )

    monkeypatch.setattr("cube_analysis.reconstruct_cube", fake_failed)
    run_destruction_cycle([cube], store, MockLLMProvider(),
                          cycle_num=1, healed=set())

    # Cube stays as-is
    assert cube.content == original, "failed reco should not swap content"
    assert cube.sha256 == original_sha, "failed reco should not update sha"
