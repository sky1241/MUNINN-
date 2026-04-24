"""Test H2: id_to_name rebuilt O(N*M) per observe() in P41.

Bug: Inside the per-concept loop in observe(), id_to_name is rebuilt
from scratch for EVERY concept. With 88K cache entries and 50 concepts,
that's 4.4M dict operations per call.

Fix: Build id_to_name once before the loop.
"""
import sys, os, tempfile, time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_h2_id_to_name_built_once():
    """Verify id_to_name is not rebuilt inside the concept loop."""
    from muninn.mycelium import Mycelium
    from muninn.mycelium_db import MyceliumDB

    tmp = Path(tempfile.mkdtemp())
    try:
        muninn_dir = tmp / ".muninn"
        muninn_dir.mkdir()
        db_path = muninn_dir / "mycelium.db"

        # Create SQLite DB first so Mycelium detects it
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db._conn.commit()
        db._conn.close()

        # Now create Mycelium — it will load from SQLite
        m = Mycelium(tmp)
        assert m._db is not None, "Mycelium should use SQLite mode"

        # Seed some concepts + fusions so P41 has work to do
        concepts_base = [f"concept_{i}" for i in range(20)]
        m.observe(concepts_base)

        # Create some fusions manually
        for i in range(0, 18, 2):
            m._db.upsert_fusion(concepts_base[i], concepts_base[i+1],
                                f"{concepts_base[i]}+{concepts_base[i+1]}",
                                strength=15)
        m._db._conn.commit()

        # Populate concept_cache with many entries to simulate real load
        # (In production this is 88K entries)
        for i in range(1000):
            name = f"extra_concept_{i}"
            m._db._get_or_create_concept(name)
        m._db._conn.commit()

        cache_size = len(m._db._concept_cache)
        print(f"  concept_cache size: {cache_size}")

        # Now observe with multiple concepts — measure time
        test_concepts = [f"concept_{i}" for i in range(10)]

        t0 = time.perf_counter()
        for _ in range(5):
            m.observe(test_concepts)
        t1 = time.perf_counter()
        elapsed = t1 - t0

        print(f"  5x observe(10 concepts): {elapsed:.3f}s")
        print(f"  Perf acceptable (<2s): {elapsed < 2.0}")
        assert elapsed < 2.0, f"observe() too slow: {elapsed:.3f}s"

        # Verify functionality: P41 should still add fusion concepts
        has_fusions = m._db._conn.execute("SELECT COUNT(*) FROM fusions").fetchone()[0]
        print(f"  Fusions in DB: {has_fusions} (expected >= 9)")
        assert has_fusions >= 9, f"Fusions lost: {has_fusions}"

        # Verify the FIX specifically: inspect the source to confirm
        # id_to_name is built OUTSIDE the loop
        import inspect
        source = inspect.getsource(m.observe)
        # Find the P41 section
        p41_start = source.find("P41")
        if p41_start > 0:
            p41_section = source[p41_start:p41_start + 500]
            # id_to_name should be BEFORE "for concept in clean_set"
            id_pos = p41_section.find("id_to_name")
            loop_pos = p41_section.find("for concept in clean_set")
            if id_pos > 0 and loop_pos > 0:
                print(f"  id_to_name at offset {id_pos}, loop at offset {loop_pos}")
                print(f"  id_to_name BEFORE loop: {id_pos < loop_pos}")
                assert id_pos < loop_pos, "id_to_name should be built BEFORE the concept loop"
            else:
                print(f"  Code structure check: id_to_name={id_pos}, loop={loop_pos}")

        # Close DB properly (Windows lock)
        if m._db and m._db._conn:
            m._db._conn.close()

        print("  PASS")
    finally:
        import shutil
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    print("## H2 — id_to_name O(N*M) in observe()")
    test_h2_id_to_name_built_once()
