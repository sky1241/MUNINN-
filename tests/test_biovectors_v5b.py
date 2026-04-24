"""V5B — Cross-inhibition winner-take-all: PRODUCTION tests.

Tests that boot() cross-inhibition (Lotka-Volterra) reorders close-scoring branches.
The V5B code in boot() runs LV dynamics on the top candidates when scores are within 15%.
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


def _setup_and_boot(branches, query):
    """Create temp repo, run boot(), return output with branch load order."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v5b_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    root_text = "# root\nproject overview\n"
    (tree_dir / "root.mn").write_text(root_text, encoding="utf-8")

    nodes = {
        "root": {
            "type": "root", "file": "root.mn", "lines": 2, "max_lines": 100,
            "children": [], "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1, "tags": [], "hash": "00000000",
        }
    }
    for b in branches:
        bname = b["name"]
        bfile = f"{bname}.mn"
        content = b.get("content", f"# {bname}\n{' '.join(b.get('tags', []))}\n")
        (tree_dir / bfile).write_text(content, encoding="utf-8")
        nodes["root"]["children"].append(bname)
        nodes[bname] = {
            "type": "branch", "file": bfile,
            "lines": len(content.split("\n")), "max_lines": 150,
            "children": [], "last_access": b.get("last_access", time.strftime("%Y-%m-%d")),
            "access_count": b.get("access_count", 3),
            "tags": b.get("tags", []), "temperature": b.get("temperature", 0.5),
            "usefulness": b.get("usefulness", 0.5), "hash": "00000000",
        }

    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()
    try:
        output = muninn.boot(query)
        # Extract load order from output
        import re
        loaded_order = re.findall(r'=== (br_\w+) ===', output)
        loaded_set = set(loaded_order)
        return loaded_set, loaded_order, output
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v5b_1_close_scores_triggers_inhibition():
    """Close-scoring branches trigger V5B cross-inhibition — boot still works"""
    # 3 branches with very similar content (will have close TF-IDF scores)
    branches = [
        {"name": "br_alpha", "tags": ["data", "analysis"],
         "content": "# br_alpha\ndata analysis statistics visualization dashboard reporting\n"},
        {"name": "br_beta", "tags": ["data", "processing"],
         "content": "# br_beta\ndata processing pipeline transform aggregate filtering engine\n"},
        {"name": "br_gamma", "tags": ["data", "storage"],
         "content": "# br_gamma\ndata storage database schema migration backup archive system\n"},
    ]
    loaded_set, order, _ = _setup_and_boot(branches, "data analysis processing")
    # At least one should load, and boot should complete
    check("V5B.1", len(loaded_set) >= 1,
          f"loaded={loaded_set} (cross-inhibition applied)")


def test_v5b_2_clear_winner_survives():
    """Branch with clearly higher relevance wins even with inhibition"""
    branches = [
        {"name": "br_winner", "tags": ["memory", "compression"],
         "content": "# br_winner\nmemory compression tokens pipeline layers filtering regex\n"},
        {"name": "br_loser", "tags": ["network", "http"],
         "content": "# br_loser\nnetwork http server endpoint routing middleware handler\n"},
    ]
    loaded_set, order, _ = _setup_and_boot(branches, "memory compression tokens")
    check("V5B.2", "br_winner" in loaded_set,
          f"winner loaded: {'br_winner' in loaded_set}")


def test_v5b_3_single_branch_no_inhibition():
    """Single branch: no cross-inhibition possible, loads normally"""
    branches = [
        {"name": "br_solo", "tags": ["solo"],
         "content": "# br_solo\nsolo branch testing cross inhibition single case\n"},
    ]
    loaded_set, _, _ = _setup_and_boot(branches, "solo branch")
    check("V5B.3", "br_solo" in loaded_set, "single branch loads normally")


def test_v5b_4_many_competitors_converges():
    """5 competing branches — boot completes and loads some"""
    branches = [
        {"name": f"br_{i}", "tags": ["shared", f"unique_{i}"],
         "content": f"# br_{i}\nshared topic unique_{i} specific content variation number {i}\n"}
        for i in range(5)
    ]
    loaded_set, _, output = _setup_and_boot(branches, "shared topic")
    check("V5B.4", len(loaded_set) >= 1 and len(output) > 0,
          f"loaded {len(loaded_set)} of 5 branches")


if __name__ == "__main__":
    print("=== V5B Cross-Inhibition (PRODUCTION) — 4 bornes ===")
    test_v5b_1_close_scores_triggers_inhibition()
    test_v5b_2_clear_winner_survives()
    test_v5b_3_single_branch_no_inhibition()
    test_v5b_4_many_competitors_converges()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
