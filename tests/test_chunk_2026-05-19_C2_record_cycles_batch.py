"""CHUNK C2 (2026-05-19) — Batch `record_cycles` via executemany.

Pre-fix: `record_cycle` (singulier) faisait INSERT + commit() pour CHAQUE
ligne. Sur un run de 1000 cubes × N cycles, ça donne ~25s gaspillés en
overhead SQLite (mesure : 2.5ms par execute+commit). Le pattern batch
existe déjà côté `save_cubes` (executemany), juste pas appliqué aux cycles.

Fix:
  - Nouvelle méthode `CubeStore.record_cycles(batch)` qui prend
    `list[tuple[str, int, bool, str, float]]` et fait UN executemany +
    UN commit.
  - `record_cycle` (singulier) conservé pour backward-compat (tests qui
    en dépendent + appel from-anywhere).
  - `run_destruction_cycle` accumule les results dans une liste et
    appelle `store.record_cycles(batch)` une fois après la boucle.

Locks the perf invariant + le contrat batch.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_record_cycles_plural_method_exists(tmp_path):
    """CubeStore must expose a batch method `record_cycles` (plural)."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    assert hasattr(store, "record_cycles"), (
        "CubeStore must expose record_cycles(batch) method"
    )
    assert callable(store.record_cycles)


def test_record_cycles_batch_persists_all_rows(tmp_path):
    """record_cycles(N items) → N rows in DB. End-to-end persistence."""
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    batch = [
        (f"cube_{i}", 1, True, f"reco_{i}", 0.1 * i)
        for i in range(50)
    ]
    store.record_cycles(batch)
    # Read back
    rows = store.conn.execute("SELECT COUNT(*) FROM cycles").fetchone()
    assert rows[0] == 50, f"expected 50 rows, got {rows[0]}"


def test_record_cycles_batch_is_at_least_2x_faster_than_singular(tmp_path):
    """The batch path is observably faster than N×singular for the same
    number of rows. This is THE perf invariant — the implementation
    detail (executemany) matters only in service of this measurable
    behavior.

    Conservative threshold (2x) chosen to avoid CI flakiness on
    burstable runners; in practice batch is ~10-50x faster locally.
    """
    import time
    from cube import CubeStore

    n_rows = 200

    # Path A: singular (legacy)
    store_a = CubeStore(str(tmp_path / "a.db"))
    t0 = time.perf_counter()
    for i in range(n_rows):
        store_a.record_cycle(f"c{i}", 1, True, "", 0.0)
    t_singular = time.perf_counter() - t0

    # Path B: batch (new)
    store_b = CubeStore(str(tmp_path / "b.db"))
    batch = [(f"c{i}", 1, True, "", 0.0) for i in range(n_rows)]
    t0 = time.perf_counter()
    store_b.record_cycles(batch)
    t_batch = time.perf_counter() - t0

    # Both paths must insert all N rows
    count_a = store_a.conn.execute("SELECT COUNT(*) FROM cycles").fetchone()[0]
    count_b = store_b.conn.execute("SELECT COUNT(*) FROM cycles").fetchone()[0]
    assert count_a == n_rows, f"singular path missed rows: {count_a}/{n_rows}"
    assert count_b == n_rows, f"batch path missed rows: {count_b}/{n_rows}"

    # Batch must be at least 2x faster (in practice 10-50x)
    assert t_batch < t_singular / 2, (
        f"batch ({t_batch * 1000:.1f}ms) should be ≥2x faster than "
        f"singular ({t_singular * 1000:.1f}ms) for {n_rows} rows. "
        f"speedup = {t_singular / t_batch:.1f}x"
    )


def test_record_cycle_singular_still_works_for_backward_compat(tmp_path):
    """The legacy record_cycle (singular) must still insert one row.

    Existing callers and tests rely on this method.
    """
    from cube import CubeStore
    store = CubeStore(str(tmp_path / "cube.db"))
    store.record_cycle("cube_x", 1, True, "rebuilt", 0.5)
    rows = store.conn.execute(
        "SELECT cube_id, cycle_num, success, perplexity FROM cycles"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("cube_x", 1, 1, 0.5)


def test_run_destruction_cycle_uses_batch_record(tmp_path, monkeypatch):
    """run_destruction_cycle must call store.record_cycles ONCE per cycle,
    not record_cycle N times. The actual perf win comes from this wiring.
    """
    from cube import Cube, CubeStore, sha256_hash
    from cube_analysis import run_destruction_cycle
    from cube_providers import MockLLMProvider, ReconstructionResult

    # 3 cubes
    cubes = []
    for i in range(3):
        content = f"content {i}"
        cubes.append(Cube(
            id=f"c{i}", sha256=sha256_hash(content), content=content,
            file_origin="t.py", line_start=i, line_end=i, level=1,
            score=0.0, temperature=0.5, token_count=5,
        ))

    store = CubeStore(str(tmp_path / "cube.db"))
    for c in cubes:
        store.save_cube(c)

    record_singular_count = 0
    record_batch_count = 0
    batch_sizes: list[int] = []
    real_record = store.record_cycle
    real_batch = store.record_cycles

    def count_singular(*args, **kwargs):
        nonlocal record_singular_count
        record_singular_count += 1
        return real_record(*args, **kwargs)

    def count_batch(batch):
        nonlocal record_batch_count
        record_batch_count += 1
        batch_sizes.append(len(batch))
        return real_batch(batch)

    monkeypatch.setattr(store, "record_cycle", count_singular)
    monkeypatch.setattr(store, "record_cycles", count_batch)

    def fake_reconstruct(cube_in, neighbors, prov, *args, **kwargs):
        return ReconstructionResult(
            cube_id=cube_in.id, original_sha256=cube_in.sha256,
            reconstruction=cube_in.content,  # echo back
            reconstruction_sha256=cube_in.sha256,
            exact_match=True, ncd_score=0.0, perplexity=0.0, success=True,
        )

    monkeypatch.setattr("cube_analysis.reconstruct_cube", fake_reconstruct)

    run_destruction_cycle(cubes, store, MockLLMProvider(),
                          cycle_num=1, healed=set())

    assert record_batch_count == 1, (
        f"run_destruction_cycle should call record_cycles ONCE, "
        f"got {record_batch_count}"
    )
    assert batch_sizes == [3], (
        f"batch should contain 3 records (1 per cube), got {batch_sizes}"
    )
    assert record_singular_count == 0, (
        f"run_destruction_cycle should NOT call record_cycle (singular) "
        f"in the hot path, got {record_singular_count}"
    )
