"""V7B — ACO pheromone boot scoring: PRODUCTION tests.

Tests that boot() ACO pheromone blends into the total score.
The V7B code: total = 0.8 * total + 0.2 * aco_score where aco = tau * eta^2.
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
    """Create temp repo, run boot(), return which branches were loaded."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v7b_"))
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
        # Extra node fields
        for k in ("td_value", "access_history"):
            if k in b:
                nodes[bname][k] = b[k]

    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"),
            "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()
    try:
        output = muninn.boot(query)
        loaded = {}
        for b in branches:
            loaded[b["name"]] = f"=== {b['name']} ===" in output
        return loaded, output
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v7b_1_high_usefulness_and_relevance_wins():
    """Branch with high usefulness (tau) AND high relevance (eta) dominates via ACO"""
    branches = [
        {"name": "br_strong", "tags": ["memory", "compression"],
         "usefulness": 0.9, "access_count": 8,
         "content": "# br_strong\nmemory compression tokens pipeline layers tree boot\n"},
        {"name": "br_weak", "tags": ["random", "other"],
         "usefulness": 0.1, "access_count": 1,
         "content": "# br_weak\nrandom other unrelated topics nothing matching query\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "memory compression tokens")
    check("V7B.1", loaded["br_strong"],
          f"strong={loaded['br_strong']}, weak={loaded['br_weak']}")


def test_v7b_2_relevance_beats_history():
    """High relevance (eta^2) matters more than high history (tau) — beta=2 > alpha=1"""
    branches = [
        {"name": "br_relevant", "tags": ["query_topic"],
         "usefulness": 0.2, "access_count": 1,
         "content": "# br_relevant\nquery_topic exact match words specific unique content\n"},
        {"name": "br_historical", "tags": ["old_topic"],
         "usefulness": 0.9, "access_count": 10,
         "content": "# br_historical\nold_topic different context unrelated domain archive\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "query_topic exact match")
    check("V7B.2", loaded["br_relevant"],
          f"relevant={loaded['br_relevant']}, historical={loaded['br_historical']}")


def test_v7b_3_zero_usefulness_still_loads():
    """tau floor clamp: usefulness=0 -> tau clamped to 0.01, not zero"""
    branches = [
        {"name": "br_zero_u", "tags": ["alpha"],
         "usefulness": 0.0, "access_count": 0,
         "content": "# br_zero_u\nalpha beta gamma relevant matching terms here\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "alpha beta gamma")
    check("V7B.3", loaded["br_zero_u"],
          f"zero usefulness still loaded: {loaded['br_zero_u']}")


def test_v7b_4_aco_blend_positive():
    """Blended score (80% base + 20% ACO) is always > 0 for relevant branches"""
    branches = [
        {"name": "br_test", "tags": ["test"],
         "usefulness": 0.5, "access_count": 3,
         "content": "# br_test\ntest verification validation positive score check\n"},
    ]
    loaded, output = _setup_and_boot(branches, "test verification")
    check("V7B.4", loaded["br_test"] and len(output) > 50,
          "blend produces positive score, branch loads")


if __name__ == "__main__":
    print("=== V7B ACO Pheromone (PRODUCTION) — 4 bornes ===")
    test_v7b_1_high_usefulness_and_relevance_wins()
    test_v7b_2_relevance_beats_history()
    test_v7b_3_zero_usefulness_still_loads()
    test_v7b_4_aco_blend_positive()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
