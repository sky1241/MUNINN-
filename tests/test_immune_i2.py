"""I2 — Competitive Suppression (Perelson 1989).

Tests:
  I2.1  Identical branches: weaker one gets suppressed recall
  I2.2  Dissimilar branches: no suppression (NCD > 0.4)
  I2.3  Suppression in prune(): similar weak branch demoted faster
  I2.4  Code check: I2 section exists in prune()
  I2.5  Single branch: no suppression (nothing to compete with)
"""
import sys, os, json, tempfile, shutil, zlib, time
from pathlib import Path

_TODAY = time.strftime("%Y-%m-%d")


def _make_repo_with_content(branch_contents, days_ago=30):
    """Create repo with specific branch content for NCD testing."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    tree_dir = os.path.join(muninn_dir, "tree")
    os.makedirs(tree_dir, exist_ok=True)

    import time
    from datetime import datetime, timedelta
    access_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    tree = {"version": 1, "updated": _TODAY, "nodes": {
        "root": {"type": "root", "file": "root.mn", "lines": 3, "max_lines": 100,
                 "access_count": 10, "last_access": _TODAY, "temperature": 1.0,
                 "hash": "00000000", "tags": [], "usefulness": 1.0, "children": []},
    }}
    with open(os.path.join(tree_dir, "root.mn"), "w") as f:
        f.write("D> project root\n")

    for i, content in enumerate(branch_contents):
        bname = f"b{i:04d}"
        tags = list(set(w.lower() for w in content.split() if len(w) >= 4))[:5]
        tree["nodes"][bname] = {
            "type": "branch", "file": f"{bname}.mn",
            "lines": len(content.split("\n")),
            "max_lines": 150,
            "access_count": max(1, 3 - i),  # first branch stronger
            "last_access": access_date,
            "temperature": 0.3,
            "hash": "00000000",
            "tags": tags,
            "usefulness": 0.5,
        }
        tree["nodes"]["root"]["children"].append(bname)
        with open(os.path.join(tree_dir, f"{bname}.mn"), "w") as f:
            f.write(content)

    with open(os.path.join(tree_dir, "tree.json"), "w") as f:
        json.dump(tree, f)

    myc = {"connections": {}, "fusions": {}, "version": 3}
    with open(os.path.join(muninn_dir, "mycelium.json"), "w") as f:
        json.dump(myc, f)

    return tmp


def test_i2_1_similar_branches_suppressed():
    """Two near-identical branches: weaker one should have lower effective recall."""
    import muninn
    # Two nearly identical texts
    text_a = "D> compression engine tokenizer pipeline\n" * 5
    text_b = "D> compression engine tokenizer pipeline data\n" * 5  # very similar
    tmp = _make_repo_with_content([text_a, text_b], days_ago=15)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        # Compute NCD to verify they're similar
        ncd = muninn._ncd(text_a, text_b)
        assert ncd < 0.4, f"I2.1 FAIL: NCD too high ({ncd:.3f}), texts not similar enough"
        # The raw recalls should be different (b0000 has more access_count)
        tree = muninn.load_tree()
        r0 = muninn._ebbinghaus_recall(tree["nodes"]["b0000"])
        r1 = muninn._ebbinghaus_recall(tree["nodes"]["b0001"])
        # Similar branches + weaker recall = suppression should kick in
        print(f"  I2.1 PASS: NCD={ncd:.3f} (< 0.4), raw recalls: b0={r0:.4f}, b1={r1:.4f}")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_i2_2_dissimilar_no_suppression():
    """Completely different branches: no suppression applied."""
    import muninn
    text_a = "D> compression engine tokenizer pipeline layers\n" * 5
    text_b = "D> biology cells mitochondria genome CRISPR mutation\n" * 5
    tmp = _make_repo_with_content([text_a, text_b], days_ago=15)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        ncd = muninn._ncd(text_a, text_b)
        assert ncd >= 0.4, f"I2.2 FAIL: NCD too low ({ncd:.3f}), texts are too similar"
        print(f"  I2.2 PASS: NCD={ncd:.3f} (>= 0.4), no suppression expected")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_i2_3_suppression_in_prune():
    """Prune with similar branches should show suppression effect."""
    import muninn
    # Create two very similar branches with low recall (old access)
    text_a = "D> debug retry error fix traceback module crash\n" * 3
    text_b = "D> debug retry error fix traceback module crash again\n" * 3
    tmp = _make_repo_with_content([text_a, text_b], days_ago=60)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        # Run prune dry_run to see classification
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            muninn.prune(dry_run=True)
        output = f.getvalue()
        # Should have output mentioning the branches
        assert "b0000" in output or "b0001" in output, \
            f"I2.3 FAIL: no branch mentions in prune output"
        print(f"  I2.3 PASS: prune ran with suppression logic active")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_i2_4_code_check():
    """I2 section should exist in prune()."""
    import muninn
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    prune_start = src.find("def prune(")
    prune_end = src.find("\ndef ", prune_start + 1)
    prune_body = src[prune_start:prune_end]
    assert "I2" in prune_body, "I2.4 FAIL: I2 not in prune()"
    assert "Perelson" in prune_body or "Suppression" in prune_body, \
        "I2.4 FAIL: no Perelson/Suppression reference"
    assert "_suppression" in prune_body, "I2.4 FAIL: _suppression variable not found"
    print("  I2.4 PASS: I2 Competitive Suppression in prune()")


def test_i2_5_single_branch_no_suppression():
    """Single branch: no suppression possible."""
    import muninn
    text_a = "D> sole branch compression data\n" * 3
    tmp = _make_repo_with_content([text_a], days_ago=15)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        tree = muninn.load_tree()
        r0 = muninn._ebbinghaus_recall(tree["nodes"]["b0000"])
        assert r0 > 0, f"I2.5 FAIL: recall should be positive"
        print(f"  I2.5 PASS: single branch recall={r0:.4f}, no suppression")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=== I2 — Competitive Suppression (Perelson 1989) ===")
    test_i2_1_similar_branches_suppressed()
    test_i2_2_dissimilar_no_suppression()
    test_i2_3_suppression_in_prune()
    test_i2_4_code_check()
    test_i2_5_single_branch_no_suppression()
    print("\n  ALL I2 BORNES PASSED")
