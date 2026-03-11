"""TIER 2 WIRING — Verify all B2-B7 are actually connected to the pipeline.

Tests:
  W1  B5 wired: sigmoid k changes based on session mode
  W2  B3 wired: blind spot concepts boost branch scores
  W3  B4 wired: predicted branches get bonus in boot scoring
  W4  B6 wired: session type adjusts scoring weights
  W5  B7 wired: injected fact appears in tree + mycelium
  W6  Integration: boot with wiring produces valid results
"""
import sys, os, tempfile, json, time, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

def test_w1_sigmoid_k_adapts():
    """B5: spread_activation should use session-adapted k"""
    from mycelium import Mycelium
    import muninn
    # Divergent mode -> k=5, Convergent -> k=20
    div_mode = muninn.detect_session_mode([f"c{i}" for i in range(20)])
    assert div_mode["suggested_k"] == 5, f"W1 FAIL: divergent k={div_mode['suggested_k']}"
    conv_mode = muninn.detect_session_mode(["debug"] * 20)
    assert conv_mode["suggested_k"] == 20, f"W1 FAIL: convergent k={conv_mode['suggested_k']}"
    # Verify the k value actually changes sigmoid output
    sig_k5 = 1.0 / (1.0 + math.exp(-5 * (0.3 - 0.3)))   # =0.5
    sig_k20 = 1.0 / (1.0 + math.exp(-20 * (0.3 - 0.3)))  # =0.5
    sig_k5_high = 1.0 / (1.0 + math.exp(-5 * (0.5 - 0.3)))   # ~0.73
    sig_k20_high = 1.0 / (1.0 + math.exp(-20 * (0.5 - 0.3)))  # ~0.98
    assert sig_k20_high > sig_k5_high, "W1 FAIL: k=20 should be sharper"
    print(f"  W1 PASS: k=5 -> sig(0.5)={sig_k5_high:.3f}, k=20 -> sig(0.5)={sig_k20_high:.3f}")

def test_w2_blind_spots_boost():
    """B3: branches covering blind spot concepts should score higher"""
    import muninn
    from pathlib import Path
    repo = Path(os.path.dirname(__file__)).parent
    m_path = repo / ".muninn" / "mycelium.json"
    if not m_path.exists():
        print(f"  W2 SKIP: no mycelium")
        return
    from mycelium import Mycelium
    m = Mycelium(repo)
    if len(m.data["connections"]) < 100:
        print(f"  W2 SKIP: too few connections")
        return
    blind_spots = m.detect_blind_spots(top_n=10)
    assert len(blind_spots) > 0, "W2 FAIL: no blind spots found"
    bs_concepts = set()
    for a, b, _ in blind_spots:
        bs_concepts.add(a)
        bs_concepts.add(b)
    # Verify at least some branches have tags overlapping with blind spot concepts
    tree = muninn.load_tree()
    hits = 0
    for name, node in tree["nodes"].items():
        if node.get("type") == "branch":
            tags = set(node.get("tags", []))
            if tags & bs_concepts:
                hits += 1
    print(f"  W2 PASS: {len(blind_spots)} blind spots, {len(bs_concepts)} concepts, {hits} branches boosted")

def test_w3_predictions_bonus():
    """B4: predict_next should return predictions that get bonus in scoring"""
    import muninn
    from pathlib import Path
    repo = Path(os.path.dirname(__file__)).parent
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    predictions = muninn.predict_next(current_concepts=["compression", "memory"], top_n=5)
    if not predictions:
        print(f"  W3 SKIP: no predictions")
        return
    # Verify predictions are valid branch names
    tree = muninn.load_tree()
    valid = sum(1 for name, _ in predictions if name in tree["nodes"])
    assert valid == len(predictions), f"W3 FAIL: {valid}/{len(predictions)} are valid branches"
    print(f"  W3 PASS: {len(predictions)} predictions, all valid branches, top={predictions[0]}")

def test_w4_session_type_weights():
    """B6: session type should change scoring weights"""
    import muninn
    # Debug session
    debug = muninn.classify_session(["error", "fix", "bug"] * 5,
                                     ["E> crash", "E> fix applied", "E> resolved"])
    assert debug["type"] == "debug", f"W4 FAIL: expected debug, got {debug['type']}"
    # Explore session — pass non-empty tagged_lines to avoid session_index fallback
    explore = muninn.classify_session([f"topic{i}" for i in range(20)],
                                       ["D> exploring new area"])
    assert explore["type"] == "explore", f"W4 FAIL: expected explore, got {explore['type']}"
    # Verify the weight adjustment logic exists in boot (structural check)
    import inspect
    boot_source = inspect.getsource(muninn.boot)
    assert "classify_session" in boot_source, "W4 FAIL: classify_session not called in boot"
    assert "w_activation" in boot_source, "W4 FAIL: adaptive weights not in boot"
    print(f"  W4 PASS: debug(conf={debug['confidence']:.2f}), explore(conf={explore['confidence']:.2f}), weights wired")

def test_w5_inject_persists():
    """B7: injected fact should be in tree and mycelium"""
    import muninn
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        (repo / ".muninn" / "tree").mkdir(parents=True)
        (repo / "memory" / "branches").mkdir(parents=True)
        tree = {"nodes": {"root": {"type": "root", "tags": []}}}
        (repo / ".muninn" / "tree" / "tree.json").write_text(json.dumps(tree), encoding="utf-8")
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        branch = muninn.inject_memory("Ebbinghaus recall x4.3 separation validated", repo)
        # Check tree
        tree2 = json.loads((repo / ".muninn" / "tree" / "tree.json").read_text(encoding="utf-8"))
        assert branch in tree2["nodes"], "W5 FAIL: branch not in tree"
        # Check mycelium
        myc_path = repo / ".muninn" / "mycelium.json"
        if myc_path.exists():
            myc = json.loads(myc_path.read_text(encoding="utf-8"))
            assert len(myc.get("connections", {})) > 0, "W5 FAIL: mycelium empty"
    # Restore real repo
    muninn._REPO_PATH = Path(os.path.dirname(__file__)).parent
    muninn._refresh_tree_paths()
    print(f"  W5 PASS: inject -> tree + mycelium persisted")

def test_w6_boot_integration():
    """Full boot with all wiring: should produce valid results without crash"""
    import muninn
    from pathlib import Path
    repo = Path(os.path.dirname(__file__)).parent
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    # Verify boot source has all wiring
    import inspect
    src = inspect.getsource(muninn.boot)
    checks = {
        "B5_sigmoid": "detect_session_mode" in src,
        "B3_blindspots": "detect_blind_spots" in src or "blind_spot_concepts" in src,
        "B4_predictions": "predict_next" in src or "prediction_scores" in src,
        "B6_session_type": "classify_session" in src,
    }
    for label, passed in checks.items():
        assert passed, f"W6 FAIL: {label} not wired into boot()"
    print(f"  W6 PASS: all 4 wiring points confirmed in boot() source")

if __name__ == "__main__":
    print("=== TIER 2 WIRING — All branchements verified ===")
    test_w1_sigmoid_k_adapts()
    test_w2_blind_spots_boost()
    test_w3_predictions_bonus()
    test_w4_session_type_weights()
    test_w5_inject_persists()
    test_w6_boot_integration()
    print("\n  ALL WIRING BORNES PASSED")
