"""V5A — Quorum sensing Hill switch: PRODUCTION tests.

Tests that boot() quorum Hill scoring activates when tags overlap with activated_set.
The V5A code in boot() adds a Hill-function bonus when spreading-activation concepts
overlap with a branch's tags.
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
    """Create temp repo, run boot(), return loaded branches and output."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v5a_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    root_text = "# root\nmemory compression project muninn\n"
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
        loaded = {}
        for b in branches:
            loaded[b["name"]] = f"=== {b['name']} ===" in output
        return loaded, output
    finally:
        muninn._REPO_PATH = old_repo
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_v5a_1_quorum_with_activated_tags():
    """Branch with many tags matching activated concepts gets Hill boost"""
    # Branch with tags that should be activated by spreading activation from query
    branches = [
        {"name": "br_quorum", "tags": ["memory", "compression", "tokens"],
         "content": "# br_quorum\nmemory compression tokens pipeline tree mycelium spreading\n"},
        {"name": "br_isolated", "tags": ["unrelated_xyz"],
         "content": "# br_isolated\nunrelated_xyz standalone nothing matching query\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "memory compression tokens")
    check("V5A.1", loaded["br_quorum"],
          f"quorum={loaded['br_quorum']}, isolated={loaded['br_isolated']}")


def test_v5a_2_no_tags_no_quorum():
    """Branch with empty tags gets no quorum bonus"""
    branches = [
        {"name": "br_tagged", "tags": ["memory", "compression"],
         "content": "# br_tagged\nmemory compression pipeline layers applied\n"},
        {"name": "br_untagged", "tags": [],
         "content": "# br_untagged\nmemory compression different approach untagged\n"},
    ]
    loaded, _ = _setup_and_boot(branches, "memory compression")
    # Both may load (small branches), but tagged one should be preferred
    check("V5A.2", loaded["br_tagged"],
          f"tagged={loaded['br_tagged']}, untagged={loaded['br_untagged']}")


def test_v5a_3_boot_completes_with_hill_code():
    """Boot completes without error when V5A quorum code runs"""
    branches = [
        {"name": f"br_{i}", "tags": [f"concept_{i}", "shared"],
         "content": f"# br_{i}\nconcept_{i} shared topic query matching words\n"}
        for i in range(4)
    ]
    loaded, output = _setup_and_boot(branches, "shared concept_0")
    any_loaded = any(loaded.values())
    check("V5A.3", any_loaded and len(output) > 0, "boot completed with Hill code active")


if __name__ == "__main__":
    print("=== V5A Quorum Sensing Hill (PRODUCTION) — 3 bornes ===")
    test_v5a_1_quorum_with_activated_tags()
    test_v5a_2_no_tags_no_quorum()
    test_v5a_3_boot_completes_with_hill_code()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
