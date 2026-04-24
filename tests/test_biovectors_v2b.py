"""V2B — TD-Learning reward prediction error: PRODUCTION tests.

Tests that _update_usefulness() in muninn.py actually updates td_value and usefulness
in tree.json when given a session transcript. Calls real production code.
"""
import sys, os, json, tempfile, shutil, time
from pathlib import Path
import muninn

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {name} PASS{': ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {name} FAIL{': ' + detail if detail else ''}")


def _setup_usefulness_test(branch_tags, branch_content, session_words,
                           initial_usefulness=0.5, initial_td=0.5):
    """Create temp repo + JSONL transcript, run _update_usefulness, return updated node."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v2b_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    muninn_dir = tmpdir / ".muninn"
    (muninn_dir / "sessions").mkdir(parents=True, exist_ok=True)

    # Root
    (tree_dir / "root.mn").write_text("# root\nproject\n", encoding="utf-8")

    # Branch
    (tree_dir / "branch_test.mn").write_text(branch_content, encoding="utf-8")

    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 2, "max_lines": 100,
            "children": ["branch_test"], "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1, "tags": [], "hash": "00000000",
        },
        "branch_test": {
            "type": "branch", "file": "branch_test.mn",
            "lines": len(branch_content.split("\n")), "max_lines": 150,
            "children": [], "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 3, "tags": branch_tags, "temperature": 0.5,
            "usefulness": initial_usefulness, "td_value": initial_td,
            "hash": "00000000",
        }
    }
    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    # Last boot manifest (required by _update_usefulness)
    last_boot = {"branches": ["branch_test"], "query": "test",
                 "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    (muninn_dir / "last_boot.json").write_text(json.dumps(last_boot), encoding="utf-8")

    # JSONL transcript with session_words
    jsonl_path = muninn_dir / "sessions" / "test_session.jsonl"
    lines = []
    for word in session_words:
        msg = {"message": {"content": f"Working on {word} implementation details"}}
        lines.append(json.dumps(msg))
    jsonl_path.write_text("\n".join(lines), encoding="utf-8")

    # Point muninn at this repo
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()

    try:
        # Call the REAL production function
        muninn._update_usefulness(tmpdir, jsonl_path)

        # Reload tree to get updated values
        updated_tree = json.loads((tree_dir / "tree.json").read_text(encoding="utf-8"))
        return updated_tree["nodes"].get("branch_test", {})
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v2b_1_high_overlap_increases_usefulness():
    """High session overlap with branch -> usefulness increases"""
    # Branch about "memory compression tokens" — session uses the same words
    node = _setup_usefulness_test(
        branch_tags=["memory", "compression"],
        branch_content="# branch_test\nmemory compression tokens pipeline layers filters\n",
        session_words=["memory", "compression", "tokens", "pipeline", "layers", "filters"],
        initial_usefulness=0.5, initial_td=0.5,
    )
    check("V2B.1", node.get("usefulness", 0) > 0.5,
          f"usefulness={node.get('usefulness')} (should be > 0.5)")


def test_v2b_2_no_overlap_decreases_usefulness():
    """Zero session overlap -> usefulness decreases"""
    node = _setup_usefulness_test(
        branch_tags=["memory", "compression"],
        branch_content="# branch_test\nmemory compression tokens pipeline layers\n",
        session_words=["quantum", "physics", "relativity", "spacetime"],
        initial_usefulness=0.7, initial_td=0.7,
    )
    check("V2B.2", node.get("usefulness", 1) < 0.7,
          f"usefulness={node.get('usefulness')} (should be < 0.7)")


def test_v2b_3_td_value_stored():
    """td_value and td_delta are stored in the node after update"""
    node = _setup_usefulness_test(
        branch_tags=["test"],
        branch_content="# branch_test\ntest data verification\n",
        session_words=["test", "data"],
        initial_usefulness=0.5, initial_td=0.5,
    )
    check("V2B.3", "td_value" in node and "td_delta" in node,
          f"td_value={node.get('td_value')}, td_delta={node.get('td_delta')}")


def test_v2b_4_td_value_changes():
    """td_value actually changes from initial after update"""
    node = _setup_usefulness_test(
        branch_tags=["alpha"],
        branch_content="# branch_test\nalpha beta gamma delta epsilon zeta\n",
        session_words=["alpha", "beta", "gamma", "delta", "epsilon", "zeta"],
        initial_usefulness=0.5, initial_td=0.5,
    )
    check("V2B.4", node.get("td_value", 0.5) != 0.5,
          f"td_value={node.get('td_value')} (changed from 0.5)")


def test_v2b_5_usefulness_clamped():
    """Usefulness stays in [0, 1] even with extreme initial values"""
    node = _setup_usefulness_test(
        branch_tags=["test"],
        branch_content="# branch_test\ntest extreme values boundary\n",
        session_words=["test", "extreme", "values", "boundary"],
        initial_usefulness=0.99, initial_td=0.99,
    )
    ok = 0.0 <= node.get("usefulness", -1) <= 1.0 and 0.0 <= node.get("td_value", -1) <= 1.0
    check("V2B.5", ok,
          f"usefulness={node.get('usefulness')}, td_value={node.get('td_value')}")


if __name__ == "__main__":
    print("=== V2B TD-Learning (PRODUCTION) — 5 bornes ===")
    test_v2b_1_high_overlap_increases_usefulness()
    test_v2b_2_no_overlap_decreases_usefulness()
    test_v2b_3_td_value_stored()
    test_v2b_4_td_value_changes()
    test_v2b_5_usefulness_clamped()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
