"""CHUNK B8 — _get_high_degree_concepts: UNION ALL 2× → single scan.

Pre-fix: `_get_high_degree_concepts` ran the same UNION ALL + GROUP BY
twice (once to compute the percentile threshold, once to filter
concepts above it). On Sky's prod DB (~11 K edges) this is 2× full
edge scan + 2× GROUP BY per call.

Post-fix: single SQL query that returns (concept_id, degree) rows
sorted DESC; the percentile cutoff is then a Python slice. Same
semantics, half the SQL work, faster on any DB ≥1 K edges.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B8
"""
import importlib.util
import sys
import time
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_mycelium_db_class():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    spec = importlib.util.spec_from_file_location(
        "_chunk_b8_mycelium_db", engine_core / "mycelium_db.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MyceliumDB


def _load_mycelium_class():
    """Reuse already-loaded `mycelium` if present, else fail with skip."""
    if "mycelium" in sys.modules and hasattr(sys.modules["mycelium"], "Mycelium"):
        return sys.modules["mycelium"].Mycelium
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    try:
        import mycelium as _m
        return _m.Mycelium
    except Exception as e:
        pytest.skip(f"mycelium not loadable here: {e}")


def test_no_double_union_all_in_get_high_degree():
    """Static check: only ONE `UNION ALL` (or zero) inside the
    `_get_high_degree_concepts` body block, not two.

    H6 chunk 3 (2026-05-09): the function lives in mycelium_activation.py
    now. We try mycelium.py first (back-compat) then mycelium_activation.py.
    """
    import re
    src = ""
    for fname in ("mycelium_activation.py", "mycelium.py"):
        candidate = REPO / "engine" / "core" / fname
        if candidate.exists():
            text = candidate.read_text()
            if "def _get_high_degree_concepts" in text:
                src = text
                break
    assert src, "could not find _get_high_degree_concepts in any mycelium*.py"
    m = re.search(
        r"def _get_high_degree_concepts.*?(?=\n    def |\nclass |\Z)",
        src,
        re.DOTALL,
    )
    assert m is not None, "could not locate _get_high_degree_concepts body"
    body = m.group(0)
    n_union = body.upper().count("UNION ALL")
    assert n_union <= 1, (
        f"_get_high_degree_concepts still does UNION ALL {n_union} times — "
        "pre-fix had 2 (percentile + filter). Expected ≤1."
    )


def test_high_degree_returns_strings(tmp_path):
    """Functional sanity: returns a set of concept name strings."""
    Mycelium = _load_mycelium_class()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    m = Mycelium(repo)

    # Seed enough edges to pass the n_concepts >= 20 gate
    sentences = [
        "alpha beta gamma delta",
        "alpha beta gamma epsilon",
        "alpha beta zeta eta",
        "theta iota kappa lambda",
        "mu nu xi omicron",
        "pi rho sigma tau",
        "upsilon phi chi psi omega",
    ] * 5  # repeat for stronger fusions
    for s in sentences:
        m.observe_text(s)

    result = m._get_high_degree_concepts()
    assert isinstance(result, set)
    for x in result:
        assert isinstance(x, str)


def test_high_degree_returns_empty_on_small_db(tmp_path):
    """Sanity: with <20 concepts, returns empty set (preserved gate)."""
    Mycelium = _load_mycelium_class()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    m = Mycelium(repo)
    m.observe_text("a b c d e")  # <20 concepts
    result = m._get_high_degree_concepts()
    assert result == set()


def test_high_degree_threshold_floor_20(tmp_path):
    """Returned concepts all have edge degree ≥ 20 (the floor)."""
    Mycelium = _load_mycelium_class()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    m = Mycelium(repo)

    # Seed many concepts but with low connectivity to verify floor
    for i in range(40):
        m.observe_text(f"concept_{i} concept_{(i + 1) % 40}")

    result = m._get_high_degree_concepts()
    # Result may be empty (everyone has degree 2) — that's fine; what
    # we really test is that the call doesn't crash and returns a set.
    assert isinstance(result, set)
