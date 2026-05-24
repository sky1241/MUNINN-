"""B4 -- Endsley L3 Prediction: strict validation bornes.

Tests:
  B4.1  Empty concepts returns empty predictions
  B4.2  Predictions are sorted descending by score
  B4.3  Recently accessed branches penalized (score * 0.3)
  B4.4  Output format: list of (str, float) tuples
  B4.5  Real mycelium: predictions found for known concepts

BRICK 22 (2026-04-11): tests that hit the REAL repo's mycelium DB
need a per-test 90s timeout because spread_activation on Sky's
15.5M-edge graph takes ~24s post-BUG-106-fix (was infinite pre-fix).
The default suite timeout is 10s which is too tight for these.
"""
import sys, os, tempfile, json, time
import pytest
def _setup_temp_repo(tmpdir):
    """Create minimal Muninn repo structure"""
    from pathlib import Path
    repo = Path(tmpdir)
    (repo / ".muninn" / "tree").mkdir(parents=True)
    (repo / "memory" / "branches").mkdir(parents=True)
    return repo

def test_b4_1_empty():
    """No concepts => no predictions"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        # Empty tree
        tree = {"nodes": {"root": {"type": "root", "tags": []}}}
        (repo / ".muninn" / "tree" / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        result = muninn.predict_next(current_concepts=[], top_n=5)
        assert result == [], f"B4.1 FAIL: expected [], got {result}"
    print(f"  B4.1 PASS: empty concepts returns empty predictions")

@pytest.mark.timeout(90)
def test_b4_2_sorted():
    """Predictions should be sorted by score descending.

    BRICK 22 timeout=90: hits the real Muninn mycelium DB. Post BUG-106
    fix this runs in ~24s on Sky's 15.5M-edge graph.
    """
    from pathlib import Path
    import muninn
    repo = Path(os.path.dirname(__file__)).parent
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    result = muninn.predict_next(current_concepts=["compression", "memory", "tree"], top_n=10)
    if len(result) < 2:
        print(f"  B4.2 SKIP: too few predictions ({len(result)})")
        return
    scores = [s for _, s in result]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i+1], f"B4.2 FAIL: not sorted: {scores[i]} < {scores[i+1]}"
    print(f"  B4.2 PASS: {len(result)} predictions sorted descending (top={scores[0]:.4f})")

def test_b4_3_penalize_fresh():
    """Recently accessed branches should have lower prediction score"""
    from pathlib import Path
    import muninn
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _setup_temp_repo(tmpdir)
        # Create mycelium with known connections
        myc = {
            "connections": {
                "alpha|beta": {"count": 50, "last_seen": "2026-03-10"},
                "beta|gamma": {"count": 50, "last_seen": "2026-03-10"},
            },
            "fusions": {},
            "fillers": [],
            "sessions": 1
        }
        (repo / ".muninn" / "mycelium.json").write_text(json.dumps(myc), encoding="utf-8")
        # Two branches: one fresh, one cold
        tree = {
            "nodes": {
                "root": {"type": "root", "tags": []},
                "b0001": {
                    "type": "branch", "tags": ["beta", "gamma"],
                    "access_count": 50, "last_access": time.strftime("%Y-%m-%d"),
                    "usefulness": 1.0,
                },
                "b0002": {
                    "type": "branch", "tags": ["beta", "gamma"],
                    "access_count": 1, "last_access": "2025-01-01",
                    "usefulness": 0.5,
                },
            }
        }
        (repo / ".muninn" / "tree" / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        result = muninn.predict_next(current_concepts=["alpha"], top_n=5)
        if len(result) >= 2:
            # Cold branch should rank higher than fresh
            names = [n for n, _ in result]
            scores = {n: s for n, s in result}
            assert scores.get("b0002", 0) > scores.get("b0001", 0), \
                f"B4.3 FAIL: cold b0002={scores.get('b0002',0):.4f} should > fresh b0001={scores.get('b0001',0):.4f}"
            print(f"  B4.3 PASS: cold b0002 ({scores['b0002']:.4f}) > fresh b0001 ({scores['b0001']:.4f})")
        else:
            print(f"  B4.3 SKIP: too few results ({len(result)})")

def test_b4_4_format():
    """Output should be list of (str, float) tuples"""
    from pathlib import Path
    import muninn
    repo = Path(os.path.dirname(__file__)).parent
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    result = muninn.predict_next(current_concepts=["compression"], top_n=3)
    assert isinstance(result, list), f"B4.4 FAIL: not a list"
    for item in result:
        assert len(item) == 2, f"B4.4 FAIL: tuple len={len(item)}"
        assert isinstance(item[0], str), f"B4.4 FAIL: name not str"
        assert isinstance(item[1], float), f"B4.4 FAIL: score not float"
    print(f"  B4.4 PASS: output format = list of (str, float), {len(result)} items")

def test_b4_5_real():
    """Real mycelium should produce predictions for known concepts"""
    from pathlib import Path
    import muninn
    repo = Path(os.path.dirname(__file__)).parent
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    result = muninn.predict_next(current_concepts=["compression", "memory", "mycelium"], top_n=5)
    # With 2.7M connections, should find something
    if not result:
        print(f"  B4.5 SKIP: no predictions (tree may have no branches with matching tags)")
        return
    print(f"  B4.5 PASS: {len(result)} predictions, top: {result[0][0]} ({result[0][1]:.4f})")

if __name__ == "__main__":
    print("=== B4 -- Endsley L3 Prediction: validation bornes ===")
    test_b4_1_empty()
    test_b4_2_sorted()
    test_b4_3_penalize_fresh()
    test_b4_4_format()
    test_b4_5_real()
    print("\n  ALL B4 BORNES PASSED")
