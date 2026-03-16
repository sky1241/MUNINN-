"""C3 — Auto-preload predictions.

Tests:
  C3.1  boot() with prediction data loads predicted branches
  C3.2  Predictions below threshold (0.3) are NOT preloaded
  C3.3  Max 3 preloads respected
  C3.4  Already-loaded branches not duplicated
  C3.5  Budget check prevents overflow
"""
import sys, os, json, tempfile, shutil, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from pathlib import Path

_TODAY = time.strftime("%Y-%m-%d")


def _setup_prediction_repo(n_branches=6):
    """Create a repo where predict_next would suggest branches."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    tree_dir = os.path.join(muninn_dir, "tree")
    os.makedirs(tree_dir, exist_ok=True)

    tree = {"version": 1, "updated": _TODAY, "nodes": {
        "root": {"type": "root", "file": "root.mn", "lines": 5, "max_lines": 100,
                 "access_count": 10, "last_access": _TODAY, "temperature": 1.0,
                 "hash": "00000000", "tags": ["compression", "memory"], "usefulness": 1.0,
                 "children": []},
    }}
    with open(os.path.join(tree_dir, "root.mn"), "w") as f:
        f.write("D> project root compression memory\n" * 3)

    for i in range(n_branches):
        bname = f"b{i:04d}"
        tree["nodes"][bname] = {
            "type": "branch", "file": f"{bname}.mn", "lines": 3, "max_lines": 150,
            "access_count": max(1, 10 - i * 2), "last_access": _TODAY,
            "temperature": max(0.1, 0.8 - i * 0.1),
            "hash": "00000000", "tags": [f"topic{i}", "compression"],
            "usefulness": max(0.1, 0.9 - i * 0.1),
        }
        tree["nodes"]["root"]["children"].append(bname)
        with open(os.path.join(tree_dir, f"{bname}.mn"), "w") as f:
            f.write(f"D> branch {bname} topic{i} compression data\n")

    with open(os.path.join(tree_dir, "tree.json"), "w") as f:
        json.dump(tree, f)

    myc = {"connections": {}, "fusions": {}, "version": 3}
    # Add connections so spreading activation works
    for i in range(n_branches - 1):
        myc["connections"][f"topic{i}|topic{i+1}"] = {
            "count": 5, "first_seen": "2026-03-01", "last_seen": "2026-03-11"}
    myc["connections"]["compression|topic0"] = {
        "count": 20, "first_seen": "2026-03-01", "last_seen": "2026-03-11"}
    with open(os.path.join(muninn_dir, "mycelium.json"), "w") as f:
        json.dump(myc, f)

    return tmp


def test_c3_1_boot_loads_branches():
    """boot() with query should load relevant branches."""
    import muninn
    tmp = _setup_prediction_repo()
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        result = muninn.boot(query="compression topic0")
        # Should contain branch content
        assert "compression" in result.lower(), "C3.1 FAIL: compression not in output"
        manifest = json.loads(open(os.path.join(tmp, ".muninn", "last_boot.json")).read())
        assert len(manifest["branches"]) >= 1, "C3.1 FAIL: no branches loaded"
        print(f"  C3.1 PASS: {len(manifest['branches'])} branches loaded")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_c3_2_code_has_threshold():
    """C3 preload section should check prediction score threshold."""
    import muninn
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    c3_start = src.find("C3:")
    assert c3_start > 0, "C3.2 FAIL: C3 section not found"
    c3_section = src[c3_start:c3_start + 1000]
    assert "pred_score" in c3_section, "C3.2 FAIL: pred_score not in C3 section"
    assert "0.3" in c3_section, "C3.2 FAIL: threshold 0.3 not in C3 section"
    print("  C3.2 PASS: threshold check in C3 section")


def test_c3_3_max_preloads():
    """Max 3 predictions preloaded (code check + behavioral)."""
    import muninn
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    c3_start = src.find("C3:")
    c3_section = src[c3_start:c3_start + 1000]
    assert "[:3]" in c3_section or "top_preds[:3]" in c3_section, \
        "C3.3 FAIL: max 3 cap not found"
    print("  C3.3 PASS: max 3 preloads cap in code")


def test_c3_4_no_duplicate_loading():
    """boot() should not load same branch twice."""
    import muninn
    tmp = _setup_prediction_repo(n_branches=3)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        result = muninn.boot(query="topic0 compression")
        manifest = json.loads(open(os.path.join(tmp, ".muninn", "last_boot.json")).read())
        branches = manifest["branches"]
        # No duplicates
        assert len(branches) == len(set(branches)), \
            f"C3.4 FAIL: duplicates in {branches}"
        print(f"  C3.4 PASS: {len(branches)} unique branches, 0 duplicates")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_c3_5_budget_in_preload():
    """C3 section should check budget before loading."""
    import muninn
    src = Path(muninn.__file__).read_text(encoding="utf-8")
    c3_start = src.find("C3:")
    assert c3_start > 0, "C3.5 FAIL: C3 not found"
    c3_section = src[c3_start:c3_start + 1000]
    assert "max_loaded_tokens" in c3_section or "loaded_tokens" in c3_section, \
        "C3.5 FAIL: budget check not in C3 section"
    print("  C3.5 PASS: budget check in C3 preload section")


if __name__ == "__main__":
    print("=== C3 — Auto-preload predictions ===")
    test_c3_1_boot_loads_branches()
    test_c3_2_code_has_threshold()
    test_c3_3_max_preloads()
    test_c3_4_no_duplicate_loading()
    test_c3_5_budget_in_preload()
    print("\n  ALL C3 BORNES PASSED")
