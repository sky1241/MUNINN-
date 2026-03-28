"""Test M10: _adj_cache never invalidated after observe/decay.

Bug: Adjacency cache built once, never cleared. After observe() adds
edges or decay() removes them, spread_activation() uses stale graph.

Fix: Set self._adj_cache = None in observe() and decay().
"""
import sys, tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m10_cache_invalidated_after_observe():
    """After observe(), spread_activation should see new edges."""
    from muninn.mycelium import Mycelium
    from muninn.mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    try:
        muninn_dir = tmp / ".muninn"
        muninn_dir.mkdir()
        db_path = muninn_dir / "mycelium.db"
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db._conn.commit()
        db._conn.close()

        m = Mycelium(tmp)
        assert m._db is not None

        # Step 1: observe initial concepts
        m.observe(["alpha", "beta", "gamma"])

        # Step 2: build adj cache (force it)
        adj1 = m._build_adj_cache()
        has_alpha = "alpha" in adj1
        print(f"  After initial observe: alpha in adj_cache={has_alpha}")
        assert has_alpha, "alpha should be in adj cache after observe"

        # Step 3: cache should exist
        assert m._adj_cache is not None, "Cache should be built"

        # Step 4: observe NEW concepts
        m.observe(["delta", "epsilon"])

        # Step 5: cache should be invalidated
        cache_after = m._adj_cache
        print(f"  After second observe: _adj_cache is None: {cache_after is None}")
        assert cache_after is None, "Cache should be invalidated after observe()"

        # Step 6: rebuild and check new concepts are visible
        adj2 = m._build_adj_cache()
        has_delta = "delta" in adj2
        print(f"  After rebuild: delta in adj_cache={has_delta}")
        assert has_delta, "delta should be in adj cache after second observe"

        # Close
        if m._db and m._db._conn:
            m._db._conn.close()

        print("  PASS")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("## M10 — _adj_cache invalidation after observe/decay")
    test_m10_cache_invalidated_after_observe()
