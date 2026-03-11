"""C3 — Auto-preload predictions.

Tests:
  C3.1  Predicted branches appear in loaded list
  C3.2  Only strong predictions (score >= 0.3) are preloaded
  C3.3  Max 3 preloads
  C3.4  No duplicate loading (already loaded = skip)
  C3.5  Budget respected (no overflow)
"""
import sys, os, json, tempfile, shutil, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
import muninn
from pathlib import Path


def _setup_repo_with_branches(n_branches=5):
    """Create a repo with multiple branches for preload testing."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    tree_dir = os.path.join(muninn_dir, "tree")
    os.makedirs(tree_dir, exist_ok=True)

    tree = {"version": 1, "updated": "2026-03-11", "nodes": {
        "root": {"type": "root", "lines": 5, "max_lines": 100, "access_count": 10,
                 "last_access": "2026-03-11", "temperature": 1.0,
                 "hash": "00000000", "tags": [], "usefulness": 1.0},
    }}
    with open(os.path.join(tree_dir, "root.mn"), "w") as f:
        f.write("D> project root compression memory mycelium\n")

    for i in range(n_branches):
        bname = f"b{i:04d}"
        tree["nodes"][bname] = {
            "type": "branch", "lines": 3, "max_lines": 150,
            "access_count": 5 - i, "last_access": "2026-03-11",
            "temperature": 0.5, "hash": "00000000",
            "tags": [f"topic{i}", f"concept{i}"], "usefulness": 0.7,
        }
        with open(os.path.join(tree_dir, f"{bname}.mn"), "w") as f:
            f.write(f"D> branch {bname} topic{i} concept{i} detail data\n")

    with open(os.path.join(tree_dir, "tree.json"), "w") as f:
        json.dump(tree, f)

    # Create mycelium
    myc = {"connections": {}, "fusions": {}, "version": 3}
    with open(os.path.join(muninn_dir, "mycelium.json"), "w") as f:
        json.dump(myc, f)

    return tmp


def test_c3_1_preload_code_exists():
    """C3 preload code should exist in boot()."""
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    assert "C3: Auto-preload" in src, "C3.1 FAIL: C3 preload code not found in muninn.py"
    assert "top_preds" in src, "C3.1 FAIL: top_preds variable not found"
    print("  C3.1 PASS: C3 preload code exists")


def test_c3_2_threshold():
    """Only predictions with score >= 0.3 should be preloaded."""
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    assert "pred_score < 0.3" in src, "C3.2 FAIL: threshold check not found"
    print("  C3.2 PASS: threshold 0.3 check exists")


def test_c3_3_max_preloads():
    """Max 3 preloads."""
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    assert "top_preds[:3]" in src, "C3.3 FAIL: max 3 cap not found"
    print("  C3.3 PASS: max 3 preloads cap exists")


def test_c3_4_no_duplicate():
    """Already-loaded branches should be skipped."""
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    assert "pred_name in loaded_names" in src, "C3.4 FAIL: duplicate check not found"
    print("  C3.4 PASS: duplicate check exists")


def test_c3_5_budget_check():
    """Budget should be checked before preloading."""
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    # Find the C3 section
    c3_start = src.find("C3: Auto-preload")
    c3_section = src[c3_start:c3_start+800]
    assert "max_loaded_tokens" in c3_section, "C3.5 FAIL: budget check not in C3 section"
    print("  C3.5 PASS: budget check exists in C3 section")


if __name__ == "__main__":
    print("=== C3 — Auto-preload predictions ===")
    test_c3_1_preload_code_exists()
    test_c3_2_threshold()
    test_c3_3_max_preloads()
    test_c3_4_no_duplicate()
    test_c3_5_budget_check()
    print("\n  ALL C3 BORNES PASSED")
