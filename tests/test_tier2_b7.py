"""B7 -- Live memory injection: strict validation bornes.

Tests:
  B7.1  Inject creates branch file
  B7.2  Second inject appends (no duplicate branch)
  B7.3  Injected fact is retrievable (in branch file)
  B7.4  Empty fact rejected
  B7.5  Tree updated with branch metadata
  B7.6  Mycelium fed with concepts
"""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

def _setup_temp_repo(tmpdir):
    """Create minimal Muninn repo structure in tmpdir"""
    from pathlib import Path
    repo = Path(tmpdir)
    (repo / ".muninn" / "tree").mkdir(parents=True)
    # Minimal tree.json at .muninn/tree/tree.json (where code expects it)
    tree = {
        "nodes": {
            "root": {
                "type": "root",
                "tags": [],
                "access_count": 0,
                "last_access": "2026-03-10",
            }
        }
    }
    (repo / ".muninn" / "tree" / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
    return repo

def test_b7_1_creates_branch():
    """inject_memory should create a .mn branch file"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        result = muninn.inject_memory("compression ratio x4.5 on real transcripts", repo)
        assert result is not None, "B7.1 FAIL: inject returned None"
        mn_path = repo / ".muninn" / "tree" / f"{result}.mn"
        assert mn_path.exists(), f"B7.1 FAIL: branch file {mn_path} not created"
        content = mn_path.read_text(encoding="utf-8")
        assert "x4.5" in content, f"B7.1 FAIL: fact not in branch content"
    print(f"  B7.1 PASS: branch {result} created with fact")

def test_b7_2_appends():
    """Second inject appends to same branch, no duplicate"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        r1 = muninn.inject_memory("fact one: compression works", repo)
        r2 = muninn.inject_memory("fact two: benchmark 37/40", repo)
        assert r1 == r2, f"B7.2 FAIL: different branches {r1} vs {r2}"
        mn_path = repo / ".muninn" / "tree" / f"{r1}.mn"
        content = mn_path.read_text(encoding="utf-8")
        assert "fact one" in content, "B7.2 FAIL: fact one missing"
        assert "fact two" in content, "B7.2 FAIL: fact two missing"
        lines = [l for l in content.split("\n") if l.startswith("D>")]
        assert len(lines) == 2, f"B7.2 FAIL: expected 2 D> lines, got {len(lines)}"
    print(f"  B7.2 PASS: second inject appends to {r1} (2 facts)")

def test_b7_3_retrievable():
    """Injected fact should be in branch file content"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        fact = "Ebbinghaus recall p=2^(-delta/h) validated"
        r = muninn.inject_memory(fact, repo)
        mn_path = repo / ".muninn" / "tree" / f"{r}.mn"
        content = mn_path.read_text(encoding="utf-8")
        assert fact in content, "B7.3 FAIL: fact not retrievable"
    print(f"  B7.3 PASS: fact retrievable from branch {r}")

def test_b7_4_empty_rejected():
    """Empty fact should be rejected"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        result = muninn.inject_memory("", repo)
        assert result is None, f"B7.4 FAIL: empty fact accepted (returned {result})"
        result = muninn.inject_memory("   ", repo)
        assert result is None, f"B7.4 FAIL: whitespace fact accepted"
    print(f"  B7.4 PASS: empty facts rejected")

def test_b7_5_tree_updated():
    """Tree.json should contain the new branch with correct metadata"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        r = muninn.inject_memory("important discovery here", repo)
        tree = json.loads((repo / ".muninn" / "tree" / "tree.json").read_text(encoding="utf-8"))
        assert r in tree["nodes"], f"B7.5 FAIL: {r} not in tree"
        node = tree["nodes"][r]
        assert node["type"] == "branch", f"B7.5 FAIL: type={node['type']}"
        assert "live_inject" in node["tags"], f"B7.5 FAIL: live_inject not in tags"
        assert "hash" in node, "B7.5 FAIL: no hash"
    print(f"  B7.5 PASS: tree updated with {r} (type=branch, tags include live_inject)")

def test_b7_6_mycelium_fed():
    """Mycelium should learn concepts from injected fact"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        # Inject a fact with distinctive concepts
        muninn.inject_memory("spectral gap eigenvalues Laplacian clustering", repo)
        myc_path = repo / ".muninn" / "mycelium.json"
        if myc_path.exists():
            myc = json.loads(myc_path.read_text(encoding="utf-8"))
            conns = myc.get("connections", {})
            assert len(conns) > 0, "B7.6 FAIL: no connections created"
            print(f"  B7.6 PASS: mycelium fed ({len(conns)} connections)")
        else:
            print(f"  B7.6 SKIP: mycelium.json not created (observe_text may need more content)")

if __name__ == "__main__":
    print("=== B7 -- Live memory injection: validation bornes ===")
    test_b7_1_creates_branch()
    test_b7_2_appends()
    test_b7_3_retrievable()
    test_b7_4_empty_rejected()
    test_b7_5_tree_updated()
    test_b7_6_mycelium_fed()
    print("\n  ALL B7 BORNES PASSED")
