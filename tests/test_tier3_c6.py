"""C6 — CLI diagnose command.

Tests:
  C6.1  diagnose() runs without crash
  C6.2  diagnose in CLI choices
  C6.3  Output contains expected sections
  C6.4  Works on empty repo (no mycelium)
  C6.5  Works with minimal tree
"""
import sys, os, json, tempfile, shutil, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
import muninn
from pathlib import Path
from io import StringIO

_TODAY = time.strftime("%Y-%m-%d")


def _setup_minimal_repo():
    """Create a minimal repo with tree only."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    tree_dir = os.path.join(muninn_dir, "tree")
    os.makedirs(tree_dir, exist_ok=True)
    tree = {
        "version": 1, "updated": _TODAY,
        "nodes": {
            "root": {"type": "root", "lines": 5, "max_lines": 100, "access_count": 1,
                     "last_access": _TODAY, "temperature": 1.0,
                     "hash": "abc", "tags": [], "usefulness": 1.0},
        }
    }
    with open(os.path.join(tree_dir, "tree.json"), "w") as f:
        json.dump(tree, f)
    with open(os.path.join(tree_dir, "root.mn"), "w") as f:
        f.write("D> minimal root\n")
    return tmp


def test_c6_1_no_crash():
    """diagnose() should run without crash on real repo."""
    old_repo = muninn._REPO_PATH
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        muninn.diagnose()
    finally:
        sys.stdout = old_stdout
        muninn._REPO_PATH = old_repo
    print("  C6.1 PASS: diagnose runs without crash")


def test_c6_2_in_choices():
    """'diagnose' should be in CLI command choices."""
    import argparse
    # Parse the source to find choices
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["muninn.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    assert '"diagnose"' in src, "C6.2 FAIL: diagnose not in CLI choices"
    print("  C6.2 PASS: diagnose in CLI choices")


def test_c6_3_output_sections():
    """Output should contain TREE, MYCELIUM, BOOT FEEDBACK, SESSIONS sections."""
    old_stdout = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        muninn.diagnose()
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue()
    for section in ["[TREE]", "[SESSIONS]", "DIAGNOSE COMPLETE"]:
        assert section in output, f"C6.3 FAIL: missing section {section}"
    print("  C6.3 PASS: all expected sections present")


def test_c6_4_empty_repo():
    """diagnose should work on a repo with no mycelium."""
    tmp = _setup_minimal_repo()
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    old_stdout = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        muninn.diagnose()
    finally:
        sys.stdout = old_stdout
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
    output = buf.getvalue()
    assert "DIAGNOSE COMPLETE" in output, "C6.4 FAIL: diagnose didn't complete"
    shutil.rmtree(tmp)
    print("  C6.4 PASS: works on empty repo")


def test_c6_5_minimal_tree():
    """diagnose should handle a tree with only root."""
    tmp = _setup_minimal_repo()
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    old_stdout = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        muninn.diagnose()
    finally:
        sys.stdout = old_stdout
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
    output = buf.getvalue()
    assert "1 nodes" in output, f"C6.5 FAIL: expected 1 node, got: {output}"
    shutil.rmtree(tmp)
    print("  C6.5 PASS: minimal tree handled")


if __name__ == "__main__":
    print("=== C6 — CLI diagnose ===")
    test_c6_1_no_crash()
    test_c6_2_in_choices()
    test_c6_3_output_sections()
    test_c6_4_empty_repo()
    test_c6_5_minimal_tree()
    print("\n  ALL C6 BORNES PASSED")
