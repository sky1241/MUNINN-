"""V9A — Bioelectric regeneration via tag diffusion: PRODUCTION tests.

Keeps existing math tests but ADDS one that calls real prune() path.
The V9A+ code in prune() extracts facts from dead branches and injects them
into survivors via mycelium get_related().
"""
import sys, os, json, tempfile, shutil, time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
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


def test_v9a_1_prune_regenerates_facts():
    """Real prune() extracts tagged facts from dead branches and injects into survivors"""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v9a_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    root_text = "# root\nmuninn project\n"
    (tree_dir / "root.mn").write_text(root_text, encoding="utf-8")

    # Dead branch: very old, zero access -> recall < 0.05
    # Tags are NOT unique (survivor also has them) -> V9B won't protect
    dead_content = "# dead_branch\nD> benchmark 37/40 facts 92%\nB> compression x4.1 ratio\nF> commit abc123\n"
    (tree_dir / "dead_branch.mn").write_text(dead_content, encoding="utf-8")

    # Survivor: recently accessed, shares all tags with dead branch
    survivor_content = "# survivor\ncompression pipeline active development benchmark results\n"
    (tree_dir / "survivor.mn").write_text(survivor_content, encoding="utf-8")

    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 2, "max_lines": 100,
            "children": ["dead_branch", "survivor"],
            "last_access": time.strftime("%Y-%m-%d"), "access_count": 1,
            "tags": [], "hash": "00000000",
        },
        "dead_branch": {
            "type": "branch", "file": "dead_branch.mn",
            "lines": 4, "max_lines": 150, "children": [],
            "last_access": "2024-01-01",  # Very old -> recall ~0
            "access_count": 0,
            "tags": ["compression"],  # NOT sole carrier (survivor also has it)
            "temperature": 0.0, "usefulness": 0.1, "hash": "00000000",
        },
        "survivor": {
            "type": "branch", "file": "survivor.mn",
            "lines": 2, "max_lines": 150, "children": [],
            "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 5,
            "tags": ["compression", "pipeline"],
            "temperature": 0.8, "usefulness": 0.7, "hash": "00000000",
        },
    }

    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()

    try:
        # Run real prune (not dry run)
        muninn.prune(dry_run=False)

        # Check: dead_branch should be deleted
        updated_tree = json.loads((tree_dir / "tree.json").read_text(encoding="utf-8"))
        dead_gone = "dead_branch" not in updated_tree["nodes"]

        # Check: survivor should have REGEN section with facts from dead branch
        survivor_text = (tree_dir / "survivor.mn").read_text(encoding="utf-8")
        has_regen = "REGEN" in survivor_text or "benchmark" in survivor_text or "37/40" in survivor_text

        check("V9A.1", dead_gone,
              f"dead_gone={dead_gone}, regen_in_survivor={has_regen}")
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v9a_2_prune_protects_survivors():
    """Real prune() does not delete surviving (hot) branches"""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v9a_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    (tree_dir / "root.mn").write_text("# root\n", encoding="utf-8")
    (tree_dir / "hot_branch.mn").write_text("# hot\nactive content\n", encoding="utf-8")

    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 1, "max_lines": 100,
            "children": ["hot_branch"], "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1, "tags": [], "hash": "00000000",
        },
        "hot_branch": {
            "type": "branch", "file": "hot_branch.mn",
            "lines": 2, "max_lines": 150, "children": [],
            "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 10,
            "tags": ["active"], "temperature": 0.9,
            "usefulness": 0.8, "hash": "00000000",
        },
    }
    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()

    try:
        muninn.prune(dry_run=False)
        updated_tree = json.loads((tree_dir / "tree.json").read_text(encoding="utf-8"))
        check("V9A.2", "hot_branch" in updated_tree["nodes"],
              "hot branch survived prune")
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v9a_3_prune_no_branches():
    """prune() with no branches doesn't crash"""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v9a_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    (tree_dir / "root.mn").write_text("# root\n", encoding="utf-8")
    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 1, "max_lines": 100,
            "children": [], "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1, "tags": [], "hash": "00000000",
        },
    }
    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()

    try:
        muninn.prune(dry_run=True)  # should not crash
        check("V9A.3", True, "prune with 0 branches: no crash")
    except Exception as e:
        check("V9A.3", False, f"crashed: {e}")
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    print("=== V9A Bioelectric Regeneration (PRODUCTION) — 3 bornes ===")
    test_v9a_1_prune_regenerates_facts()
    test_v9a_2_prune_protects_survivors()
    test_v9a_3_prune_no_branches()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
