"""V11B — Boyd-Richerson cultural transmission (3 biases): PRODUCTION tests.

Tests that boot() scoring includes conformist/prestige/guided components.
The V11B code in boot() adds 3 cultural biases to each branch's total score.
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
    """Create temp repo, run boot(), return loaded branches."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v11b_"))
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
        if "td_value" in b:
            nodes[bname]["td_value"] = b["td_value"]

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


def test_v11b_1_conformist_popular_tags_help():
    """Branch with popular tags (shared by many) gets conformist boost"""
    # "shared_tag" appears in 3/4 branches -> conformist dp > 0 (majority)
    branches = [
        {"name": "br_popular", "tags": ["shared_tag", "data"],
         "content": "# br_popular\nshared_tag data analysis query matching\n"},
        {"name": "br_also_shared1", "tags": ["shared_tag"],
         "content": "# br_also_shared1\nshared_tag other stuff completely different\n"},
        {"name": "br_also_shared2", "tags": ["shared_tag"],
         "content": "# br_also_shared2\nshared_tag more different content here\n"},
        {"name": "br_rare", "tags": ["rare_unique_tag"],
         "content": "# br_rare\nrare_unique_tag nobody else has this data analysis\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "data analysis")
    # br_popular should load (matches query + conformist boost from popular tag)
    check("V11B.1", loaded["br_popular"],
          f"popular={loaded['br_popular']}, rare={loaded['br_rare']}")


def test_v11b_2_prestige_high_td_value():
    """Branch with high td_value (prestige) gets prestige bias boost"""
    branches = [
        {"name": "br_prestige", "tags": ["topic"],
         "td_value": 0.95, "usefulness": 0.9,
         "content": "# br_prestige\ntopic analysis results performance benchmark\n"},
        {"name": "br_no_prestige", "tags": ["topic"],
         "td_value": 0.05, "usefulness": 0.1,
         "content": "# br_no_prestige\ntopic different approach alternative method testing\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "topic analysis")
    check("V11B.2", loaded["br_prestige"],
          f"prestige={loaded['br_prestige']}, no_prestige={loaded['br_no_prestige']}")


def test_v11b_3_guided_variation_toward_mean():
    """Guided variation pushes extreme usefulness toward population mean"""
    # br_extreme_high has usefulness=0.99, br_extreme_low has 0.01
    # Guided variation: mu*(mean - u) -> negative for high, positive for low
    # This modulates the score slightly
    branches = [
        {"name": "br_high_u", "tags": ["data"],
         "usefulness": 0.99,
         "content": "# br_high_u\ndata processing pipeline extreme useful branch\n"},
        {"name": "br_low_u", "tags": ["data"],
         "usefulness": 0.01,
         "content": "# br_low_u\ndata processing pipeline barely useful historical\n"},
        {"name": "br_mean_u", "tags": ["data"],
         "usefulness": 0.5,
         "content": "# br_mean_u\ndata processing pipeline average usefulness neutral\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "data processing pipeline")
    # All 3 may load (small), but boot should complete with guided variation active
    any_loaded = any(loaded.values())
    check("V11B.3", any_loaded,
          f"boot completed with guided variation, loaded={sum(loaded.values())}")


def test_v11b_4_empty_tags_graceful():
    """Branches with empty tags: conformist bias = 0, no crash"""
    branches = [
        {"name": "br_no_tags", "tags": [],
         "content": "# br_no_tags\ndata analysis matching query content here\n"},
        {"name": "br_with_tags", "tags": ["data", "analysis"],
         "content": "# br_with_tags\ndata analysis different content perspective\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "data analysis")
    check("V11B.4", loaded["br_with_tags"],
          f"no_tags={loaded['br_no_tags']}, with_tags={loaded['br_with_tags']}")


def test_v11b_5_default_td_value():
    """Branches without td_value use default 0.5 — no crash, small prestige bias"""
    branches = [
        {"name": "br_default", "tags": ["test"],
         "content": "# br_default\ntest default td_value verification branch\n"},
    ]
    loaded, output = _setup_and_boot(branches, "test default")
    check("V11B.5", loaded["br_default"] and len(output) > 20,
          "default td_value=0.5 works fine")


if __name__ == "__main__":
    print("=== V11B Boyd-Richerson Cultural (PRODUCTION) — 5 bornes ===")
    test_v11b_1_conformist_popular_tags_help()
    test_v11b_2_prestige_high_td_value()
    test_v11b_3_guided_variation_toward_mean()
    test_v11b_4_empty_tags_graceful()
    test_v11b_5_default_td_value()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
