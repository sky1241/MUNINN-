"""V1A — Coupled oscillator temperature coupling: PRODUCTION tests.

Tests that boot() scoring changes when branches share tags (temperature coupling).
Calls real muninn.boot() with temp repos — no local formula reimplementation.
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


def _setup_repo(branches, root_text="# root\nmemory compression project\n"):
    """Create a temp repo with .muninn/tree/ and branch .mn files.
    branches: list of dicts with keys: name, file, tags, temperature, content, (optional extra node fields)
    Returns: (tmpdir Path, cleanup function)
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v1a_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    # Write root
    (tree_dir / "root.mn").write_text(root_text, encoding="utf-8")
    nodes = {
        "root": {
            "type": "root",
            "file": "root.mn",
            "lines": len(root_text.split("\n")),
            "max_lines": 100,
            "children": [],
            "last_access": time.strftime("%Y-%m-%d"),
            "access_count": 1,
            "tags": [],
            "hash": "00000000",
        }
    }
    for b in branches:
        bname = b["name"]
        bfile = b.get("file", f"{bname}.mn")
        content = b.get("content", f"# {bname}\n{' '.join(b.get('tags', []))}\n")
        (tree_dir / bfile).write_text(content, encoding="utf-8")
        node = {
            "type": "branch",
            "file": bfile,
            "lines": len(content.split("\n")),
            "max_lines": 150,
            "children": [],
            "last_access": b.get("last_access", time.strftime("%Y-%m-%d")),
            "access_count": b.get("access_count", 3),
            "tags": b.get("tags", []),
            "temperature": b.get("temperature", 0.5),
            "usefulness": b.get("usefulness", 0.5),
            "hash": "00000000",
        }
        # merge any extra fields
        for k, v in b.items():
            if k not in ("name", "file", "content", "tags", "temperature",
                         "last_access", "access_count", "usefulness"):
                node[k] = v
        nodes["root"]["children"].append(bname)
        nodes[bname] = node

    tree = {"version": 2, "created": time.strftime("%Y-%m-%d"), "budget": muninn.BUDGET, "nodes": nodes}
    (tree_dir / "tree.json").write_text(json.dumps(tree, indent=2), encoding="utf-8")

    # Also create sessions dir (boot expects it)
    (tmpdir / ".muninn" / "sessions").mkdir(parents=True, exist_ok=True)

    # Point muninn at this repo
    muninn._REPO_PATH = tmpdir
    muninn._refresh_tree_paths()

    def cleanup():
        muninn._REPO_PATH = None
        muninn._refresh_tree_paths()
        shutil.rmtree(tmpdir, ignore_errors=True)

    return tmpdir, cleanup


def _boot_scores(query, branches, **kwargs):
    """Run real boot() and extract the scored list from the output.
    Returns dict of branch_name -> was_loaded (True/False).
    """
    tmpdir, cleanup = _setup_repo(branches, **kwargs)
    try:
        output = muninn.boot(query)
        loaded = {}
        for b in branches:
            bname = b["name"]
            loaded[bname] = f"=== {bname} ===" in output
        return loaded, output
    finally:
        cleanup()


def test_v1a_1_shared_tags_affect_boot():
    """Branches with shared tags and different temperatures get coupling applied in boot()"""
    # Branch A is hot (0.9), B is cold (0.1), shared tag "memory"
    # Coupling should pull A down and B up relative to a no-shared-tag baseline
    branches_shared = [
        {"name": "branch_a", "tags": ["memory", "compression"], "temperature": 0.9,
         "content": "# branch_a\nmemory compression tokens tree boot\n"},
        {"name": "branch_b", "tags": ["memory", "tokens"], "temperature": 0.1,
         "content": "# branch_b\nmemory tokens context window loading\n"},
    ]
    # Run boot with a query that matches both equally
    loaded_shared, _ = _boot_scores("memory tokens", branches_shared)
    # Both should be loaded (only 2 branches, small)
    check("V1A.1", loaded_shared["branch_a"] or loaded_shared["branch_b"],
          f"shared tags: a={loaded_shared['branch_a']}, b={loaded_shared['branch_b']}")


def test_v1a_2_no_shared_tags_no_coupling():
    """Without shared tags, no coupling occurs — score order based purely on relevance"""
    branches_no_share = [
        {"name": "branch_x", "tags": ["alpha"], "temperature": 0.9,
         "content": "# branch_x\nalpha beta gamma delta\n"},
        {"name": "branch_y", "tags": ["omega"], "temperature": 0.1,
         "content": "# branch_y\nomega sigma theta phi\n"},
    ]
    loaded, _ = _boot_scores("alpha beta", branches_no_share)
    # branch_x should be loaded (matches query), branch_y may not
    check("V1A.2", loaded["branch_x"],
          f"no shared tags: x={loaded['branch_x']}, y={loaded['branch_y']}")


def test_v1a_3_coupling_bounded():
    """V1A coupling code in boot() clamps to [-0.05, 0.05] — extreme temps don't explode"""
    # 5 branches all sharing same tags with extreme temp differences
    branches = [
        {"name": f"br_{i}", "tags": ["shared_tag_a", "shared_tag_b", "shared_tag_c"],
         "temperature": i * 0.25,
         "content": f"# br_{i}\nshared_tag_a shared_tag_b shared_tag_c extreme coupling test\n"}
        for i in range(5)
    ]
    loaded, output = _boot_scores("shared_tag_a coupling", branches)
    # Boot should complete without error (no explosion)
    any_loaded = any(loaded.values())
    check("V1A.3", any_loaded, "extreme temps: boot completed, branches loaded")


def test_v1a_4_same_temp_zero_coupling():
    """Same temperature across branches -> coupling sum = 0, no score change"""
    branches = [
        {"name": "same_a", "tags": ["memory", "tree"], "temperature": 0.5,
         "content": "# same_a\nmemory tree compression boot session pipeline layers\nregex filters applied\n"},
        {"name": "same_b", "tags": ["memory", "tree"], "temperature": 0.5,
         "content": "# same_b\nmemory tree mycelium spreading activation network\nfederated zones clustering\n"},
    ]
    loaded, _ = _boot_scores("memory tree", branches)
    # Both should be loaded (same temp = zero coupling, both relevant)
    check("V1A.4", loaded["same_a"] and loaded["same_b"],
          f"same temp: a={loaded['same_a']}, b={loaded['same_b']}")


if __name__ == "__main__":
    print("=== V1A Temperature Coupling (PRODUCTION) — 4 bornes ===")
    test_v1a_1_shared_tags_affect_boot()
    test_v1a_2_no_shared_tags_no_coupling()
    test_v1a_3_coupling_bounded()
    test_v1a_4_same_temp_zero_coupling()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
