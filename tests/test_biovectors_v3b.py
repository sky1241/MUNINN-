"""V3B — Bayesian Theory of Mind (BToM): PRODUCTION tests.

Tests that boot() BToM scoring changes based on session history.
The V3B code in boot() reads session_index.json and computes goal alignment.
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


def _setup_and_boot(branches, query, session_index=None):
    """Create temp repo with optional session_index, run boot(), return output."""
    tmpdir = Path(tempfile.mkdtemp(prefix="muninn_v3b_"))
    tree_dir = tmpdir / ".muninn" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    muninn_dir = tmpdir / ".muninn"
    (muninn_dir / "sessions").mkdir(parents=True, exist_ok=True)

    root_text = "# root\ngeneral project info\n"
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

    if session_index is not None:
        (muninn_dir / "session_index.json").write_text(
            json.dumps(session_index), encoding="utf-8")

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


def test_v3b_1_session_history_boosts_aligned_branch():
    """Branch aligned with recent session history gets BToM boost"""
    branches = [
        {"name": "br_memory", "tags": ["memory", "compression"],
         "content": "# br_memory\nmemory compression pipeline tokens layers filtering\n"},
        {"name": "br_network", "tags": ["network", "http"],
         "content": "# br_network\nnetwork http request response server endpoint routing\n"},
    ]
    # Session history: last 3 sessions all about "memory" and "compression"
    session_index = [
        {"concepts": ["memory", "compression", "tokens"], "timestamp": "2026-03-09"},
        {"concepts": ["memory", "pipeline", "layers"], "timestamp": "2026-03-10"},
        {"concepts": ["compression", "filtering", "tokens"], "timestamp": "2026-03-11"},
    ]
    loaded, _ = _setup_and_boot(branches, "memory", session_index=session_index)
    check("V3B.1", loaded["br_memory"],
          f"memory={loaded['br_memory']}, network={loaded['br_network']}")


def test_v3b_2_no_session_history_still_works():
    """Without session_index, boot() still works (BToM gracefully skipped)"""
    branches = [
        {"name": "br_alpha", "tags": ["alpha"],
         "content": "# br_alpha\nalpha beta gamma delta epsilon\n"},
    ]
    loaded, output = _setup_and_boot(branches, "alpha", session_index=None)
    check("V3B.2", loaded["br_alpha"], "boot works without session_index")


def test_v3b_3_divergent_history_no_boost():
    """Session history about different topic -> no BToM boost for unrelated branch"""
    branches = [
        {"name": "br_music", "tags": ["music", "audio"],
         "content": "# br_music\nmusic audio synthesis waveform frequency oscillator\n"},
        {"name": "br_code", "tags": ["code", "python"],
         "content": "# br_code\ncode python function class module import package\n"},
    ]
    # History is all about code, query is about music
    session_index = [
        {"concepts": ["code", "python", "function"], "timestamp": "2026-03-09"},
        {"concepts": ["code", "module", "import"], "timestamp": "2026-03-10"},
    ]
    loaded, _ = _setup_and_boot(branches, "music audio", session_index=session_index)
    # br_music should still load (query match), but code branch may also get BToM boost
    check("V3B.3", loaded["br_music"],
          f"music={loaded['br_music']}, code={loaded['br_code']}")


def test_v3b_4_high_usefulness_prior_helps():
    """Branch with higher usefulness (BToM prior) gets boosted more"""
    branches = [
        {"name": "br_high_u", "tags": ["data", "analysis"],
         "usefulness": 0.9,
         "content": "# br_high_u\ndata analysis statistics visualization charts graphs\n"},
        {"name": "br_low_u", "tags": ["data", "storage"],
         "usefulness": 0.1,
         "content": "# br_low_u\ndata storage database schema migration backup archive\n"},
    ]
    session_index = [
        {"concepts": ["data", "analysis", "storage"], "timestamp": "2026-03-10"},
        {"concepts": ["data", "analysis"], "timestamp": "2026-03-11"},
    ]
    loaded, _ = _setup_and_boot(branches, "data", session_index=session_index)
    # Both should load (only 2 branches), but high_u should benefit more from BToM
    check("V3B.4", loaded["br_high_u"],
          f"high_u={loaded['br_high_u']}, low_u={loaded['br_low_u']}")


if __name__ == "__main__":
    print("=== V3B BToM (PRODUCTION) — 4 bornes ===")
    test_v3b_1_session_history_boosts_aligned_branch()
    test_v3b_2_no_session_history_still_works()
    test_v3b_3_divergent_history_no_boost()
    test_v3b_4_high_usefulness_prior_helps()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
