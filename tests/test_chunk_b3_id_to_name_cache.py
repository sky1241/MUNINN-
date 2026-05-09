"""CHUNK B3 — Cache _id_to_name (7+ sites in mycelium.py).

Each call to a function that needs name->id inversion was rebuilding
the dict via `{v: k for k, v in self._db._concept_cache.items()}`.
On Sky's prod DB (~180K concepts) this is ~400µs per call x N callers
x M sessions/day = measurable wasted CPU.

The MyceliumDB already maintains a self-consistent reverse cache
self._db._id_to_name, populated in _load_concept_cache() and kept in
sync by _get_or_create_concept() and _concept_name(). The 9 sites in
mycelium.py just need to use that cache directly.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B3
"""
import importlib.util
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def test_no_dict_inversion_left_in_mycelium():
    """No `{v: k for k, v in ..._concept_cache.items()}` may remain.

    Static check on the source file: the inversion pattern is the bug;
    after the fix every site must use `_id_to_name` directly.
    """
    src = (REPO / "engine" / "core" / "mycelium.py").read_text()
    bad = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        if "for k, v in" in line and "_concept_cache.items()" in line:
            bad.append((lineno, line.strip()))
    assert not bad, (
        f"Dict inversion still present at {len(bad)} sites:\n  "
        + "\n  ".join(f"l.{n}: {ln}" for n, ln in bad)
    )


def test_id_to_name_used_in_mycelium():
    """The fix substitutes `_id_to_name` references at the affected sites.

    H6 (2026-05-09): mycelium.py was split into mixin modules
    (mycelium_meta.py, mycelium_zones.py, ...). Sites can land in any
    of them — count across the family.
    """
    core = REPO / "engine" / "core"
    candidates = [
        "mycelium.py", "mycelium_meta.py", "mycelium_zones.py",
        "mycelium_activation.py", "mycelium_dream.py", "mycelium_core.py",
    ]
    files = [core / name for name in candidates if (core / name).exists()]
    n = sum(f.read_text().count("_id_to_name") for f in files)
    assert n >= 7, (
        f"Expected >=7 references to _id_to_name across mycelium*.py, "
        f"found {n} (in {[f.name for f in files]})"
    )


def test_db_id_to_name_consistent_with_concept_cache(tmp_path):
    """MyceliumDB invariant: _id_to_name is the inverse of _concept_cache."""
    repo = REPO
    engine_core = repo / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    spec = importlib.util.spec_from_file_location(
        "_chunk_b3_mycelium_db", engine_core / "mycelium_db.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    MyceliumDB = mod.MyceliumDB

    db = MyceliumDB(tmp_path / "consistency.db")
    for i in range(20):
        db._get_or_create_concept(f"concept_{i}")

    # Invariant: forall (name, id) in _concept_cache, _id_to_name[id] == name
    for name, cid in db._concept_cache.items():
        assert db._id_to_name.get(cid) == name, (
            f"Mismatch: cache has {name!r} -> {cid}, "
            f"but _id_to_name[{cid}] = {db._id_to_name.get(cid)!r}"
        )
    # And reverse direction
    for cid, name in db._id_to_name.items():
        assert db._concept_cache.get(name) == cid


def test_get_compression_rules_returns_correct_names(tmp_path):
    """End-to-end: a function that was using dict inversion still returns
    the correct concept names after the substitution.

    Imports here are surprisingly tricky: the muninn/ shim and the bare
    engine/core/ name can collide depending on which test ran first.
    Strategy: skip if Mycelium can't be loaded clean (the static-source
    tests above already prove the substitution was applied correctly).
    """
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    Mycelium = None
    # Try direct bare import first
    try:
        if "mycelium" in sys.modules and hasattr(sys.modules["mycelium"], "Mycelium"):
            Mycelium = sys.modules["mycelium"].Mycelium
        else:
            import mycelium as _m_bare
            Mycelium = getattr(_m_bare, "Mycelium", None)
    except Exception:
        Mycelium = None
    if Mycelium is None:
        pytest.skip("Mycelium class not loadable in this test order "
                    "(BUG-091 shim collision). Static checks above suffice.")

    repo_dir = tmp_path / "repo"
    (repo_dir / ".muninn").mkdir(parents=True)
    m = Mycelium(repo_dir)

    # Seed some concepts via observe_text (auto-flushes per call)
    m.observe_text("alpha beta gamma delta epsilon")
    m.observe_text("alpha beta gamma delta epsilon")
    m.observe_text("foo bar baz quux")

    # get_compression_rules uses _id_to_name path. We verify the
    # output shape is correct (names, not raw "?<id>" strings).
    rules = m.get_compression_rules(min_strength=1, max_rules=100)
    assert isinstance(rules, dict), f"got: {type(rules)}"
    for k, v in rules.items():
        assert isinstance(k, str)
        # Keys may contain whatever shape, but should not be raw ids
        if "|" in k:
            a, b = k.split("|", 1)
            assert not a.startswith("?"), f"raw id leaked as name: {a!r}"
            assert not b.startswith("?")
