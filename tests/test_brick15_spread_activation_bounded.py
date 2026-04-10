"""BRICK 15 — pin the bounded BFS subgraph builder for spread_activation.

Pre-fix: spread_activation() loaded all edges (15.5M on Sky's real DB)
into a Python dict via _build_adj_cache, then iterated. The test
test_lazy_real::test_real_spread_activation was hanging at 60+ seconds.

Post-fix: _build_adj_subgraph(seeds, hops) does bounded BFS with
per-node SQL `LIMIT fanout_cap` so even hub seeds stay manageable.
"""
import importlib
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


@pytest.fixture(scope="module")
def myc():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import muninn  # noqa: F401
    import mycelium
    importlib.reload(mycelium)
    return mycelium.Mycelium(REPO_ROOT)


# ── API surface ──────────────────────────────────────────────


def test_subgraph_builder_exists(myc):
    """The new bounded helper must exist on the class."""
    assert hasattr(myc, "_build_adj_subgraph")
    assert callable(myc._build_adj_subgraph)


def test_full_cache_has_hard_limit():
    """The full _build_adj_cache must have a hard limit constant."""
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import mycelium
    importlib.reload(mycelium)
    assert hasattr(mycelium.Mycelium, "_ADJ_CACHE_HARD_LIMIT")
    assert isinstance(mycelium.Mycelium._ADJ_CACHE_HARD_LIMIT, int)
    assert mycelium.Mycelium._ADJ_CACHE_HARD_LIMIT >= 100_000


# ── Behavior ─────────────────────────────────────────────────


def test_subgraph_empty_seeds_returns_empty(myc):
    adj, max_w = myc._build_adj_subgraph([], hops=2)
    assert adj == {}
    assert max_w == 0.0


def test_subgraph_unknown_seeds_returns_empty(myc):
    adj, max_w = myc._build_adj_subgraph(
        ["__not_a_real_concept_zzz_xyz__"], hops=2
    )
    assert adj == {}


def test_subgraph_real_seed_returns_neighbors(myc):
    """A real seed concept must produce a non-empty subgraph."""
    if myc._db is None:
        pytest.skip("no DB backend")
    # Pick a real seed from top connections
    top = myc._db.top_connections(1)
    if not top:
        pytest.skip("empty DB")
    seeds = top[0][0].split("|")
    adj, max_w = myc._build_adj_subgraph(seeds, hops=2)
    assert len(adj) > 0
    assert max_w > 0
    # Each entry must be (str, float) tuples
    for concept, neighbors in list(adj.items())[:3]:
        assert isinstance(concept, str)
        for n, w in neighbors:
            assert isinstance(n, str)
            assert isinstance(w, float)


def test_subgraph_fanout_cap_respected(myc):
    """No node in the result should have more than fanout_cap neighbors."""
    if myc._db is None:
        pytest.skip("no DB backend")
    top = myc._db.top_connections(1)
    if not top:
        pytest.skip("empty DB")
    seeds = top[0][0].split("|")
    adj, _ = myc._build_adj_subgraph(seeds, hops=2, fanout_cap=10)
    for concept, neighbors in adj.items():
        assert len(neighbors) <= 10, (
            f"node {concept!r} has {len(neighbors)} > 10 neighbors"
        )


# ── Performance contract ─────────────────────────────────────


def test_spread_activation_under_60s_on_real_db(myc):
    """The contract test_lazy_real::test_real_spread_activation expects
    spread_activation to complete in < 60s. BRICK 15 fix made this
    achievable on Sky's 15.5M-edge DB."""
    if myc._db is None:
        pytest.skip("no DB backend")
    top = myc._db.top_connections(1)
    if not top:
        pytest.skip("empty DB")
    seeds = top[0][0].split("|")
    t0 = time.time()
    activated = myc.spread_activation(seeds, hops=2, decay=0.5)
    dt = time.time() - t0
    assert dt < 60.0, (
        f"BRICK 15 REGRESSION: spread_activation took {dt:.1f}s "
        f"(must be < 60s)"
    )
    assert len(activated) > 0, "spread_activation returned empty"


def test_subgraph_builder_under_30s_on_real_db(myc):
    """The bounded subgraph builder itself must be fast even on hub seeds."""
    if myc._db is None:
        pytest.skip("no DB backend")
    top = myc._db.top_connections(1)
    if not top:
        pytest.skip("empty DB")
    seeds = top[0][0].split("|")
    t0 = time.time()
    adj, _ = myc._build_adj_subgraph(seeds, hops=2, fanout_cap=64)
    dt = time.time() - t0
    assert dt < 30.0, (
        f"BRICK 15 REGRESSION: _build_adj_subgraph took {dt:.1f}s on hub seeds"
    )
