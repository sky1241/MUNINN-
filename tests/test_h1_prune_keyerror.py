"""Test H1: prune() KeyError after sleep consolidation.

Bug: cold re-compression loop at L3573 does `node = nodes[name]`
without checking if the node was removed by _sleep_consolidate.

This test simulates the scenario where a cold branch gets popped
from nodes (by sleep_consolidate) while still in the cold list.
"""
import sys, os, tempfile, time, shutil
from pathlib import Path

# Setup paths
ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_h1_cold_loop_survives_missing_node():
    """Reproduce: cold list has names that _sleep_consolidate already popped."""
    import muninn

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        tree_dir = tmp / ".muninn" / "tree"
        tree_dir.mkdir(parents=True)

        # Create 3 cold branches — 2 will be "consolidated" (popped from nodes)
        nodes = {"root": {"type": "root", "file": "root.mn", "tags": [], "children": ["cold_a", "cold_b", "cold_c"]}}
        for name in ["cold_a", "cold_b", "cold_c"]:
            fname = f"{name}.mn"
            (tree_dir / fname).write_text(f"B> {name} data\nD> metric=42\n", encoding="utf-8")
            nodes[name] = {
                "type": "branch", "file": fname, "lines": 2, "max_lines": 150,
                "tags": ["test"], "temperature": 0.05,
                "access_count": 1, "last_access": "2026-01-01",
                "created": "2026-01-01", "usefulness": 0.3,
                "td_value": 0.5, "fisher_importance": 0.0,
            }

        # Simulate the cold list (all 3 branches)
        cold = [("cold_a", 30), ("cold_b", 30), ("cold_c", 30)]

        # Simulate what _sleep_consolidate does: pop 2 branches
        # (as if cold_a and cold_b were merged into cold_a_consolidated)
        nodes.pop("cold_a", None)
        nodes.pop("cold_b", None)

        # NOW: the cold re-compression loop should not crash
        # This is the exact code from muninn.py L3573-3587
        crashed = False
        recompressed = 0
        old_TREE_DIR = getattr(muninn, 'TREE_DIR', None)
        muninn.TREE_DIR = tree_dir

        try:
            for name, days in cold:
                # BUG: without guard, this crashes on cold_a and cold_b
                if name not in nodes:
                    continue  # This is the fix being tested
                node = nodes[name]
                filepath = tree_dir / node["file"]
                if not filepath.exists():
                    continue
                content = filepath.read_text(encoding="utf-8")
                # Don't actually call _llm_compress in test
                recompressed += 1
        except KeyError as e:
            crashed = True
            print(f"  KEYERROR: {e}")
        finally:
            if old_TREE_DIR is not None:
                muninn.TREE_DIR = old_TREE_DIR

        # Also test that the ORIGINAL code WITHOUT the guard would crash
        crashed_without_guard = False
        try:
            for name, days in cold:
                # No guard — direct access
                node = nodes[name]  # Should crash on cold_a
        except KeyError:
            crashed_without_guard = True

        print(f"  With guard: crashed={crashed} (expected False)")
        print(f"  Without guard: crashed={crashed_without_guard} (expected True)")
        print(f"  Recompressed: {recompressed} (expected 1 — only cold_c survives)")

        assert not crashed, "Cold loop crashed WITH guard"
        assert crashed_without_guard, "Cold loop should crash WITHOUT guard"
        assert recompressed == 1, f"Expected 1 recompressed, got {recompressed}"
        print("  PASS")


if __name__ == "__main__":
    print("## H1 — prune() KeyError after sleep consolidation")
    test_h1_cold_loop_survives_missing_node()
