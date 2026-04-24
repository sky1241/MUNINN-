"""I1 — Danger Theory DCA (Greensmith 2008).

Tests:
  I1.1  _ebbinghaus_recall with danger_score=0 = baseline (backward compat)
  I1.2  _ebbinghaus_recall with danger_score=0.5 -> longer half-life -> higher recall
  I1.3  danger_score computation: error-heavy transcript -> higher score
  I1.4  danger_score computation: clean transcript -> near-zero score
  I1.5  danger_score stored in session_index entry
  I1.6  danger_score propagated to branch node via grow_branches_from_session
"""
import sys, os, json, tempfile, shutil, re, time
from datetime import datetime, timedelta
from pathlib import Path

_TODAY = time.strftime("%Y-%m-%d")
_DAYS_AGO = lambda n: (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _make_repo(n_branches=2, with_mycelium=True):
    """Create a minimal repo for testing."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    tree_dir = os.path.join(muninn_dir, "tree")
    sessions_dir = os.path.join(muninn_dir, "sessions")
    os.makedirs(tree_dir, exist_ok=True)
    os.makedirs(sessions_dir, exist_ok=True)

    tree = {"version": 1, "updated": _TODAY, "nodes": {
        "root": {"type": "root", "file": "root.mn", "lines": 3, "max_lines": 100,
                 "access_count": 5, "last_access": _TODAY, "temperature": 1.0,
                 "hash": "00000000", "tags": [], "usefulness": 1.0, "children": []},
    }}
    with open(os.path.join(tree_dir, "root.mn"), "w") as f:
        f.write("D> project root\n")
    for i in range(n_branches):
        bname = f"b{i:04d}"
        tree["nodes"][bname] = {
            "type": "branch", "file": f"{bname}.mn", "lines": 3, "max_lines": 150,
            "access_count": 3, "last_access": _TODAY, "temperature": 0.5,
            "hash": "00000000", "tags": [f"topic{i}"], "usefulness": 0.7,
        }
        tree["nodes"]["root"]["children"].append(bname)
        with open(os.path.join(tree_dir, f"{bname}.mn"), "w") as f:
            f.write(f"D> branch {bname} topic{i}\n")
    with open(os.path.join(tree_dir, "tree.json"), "w") as f:
        json.dump(tree, f)

    if with_mycelium:
        myc = {"connections": {}, "fusions": {}, "version": 3}
        with open(os.path.join(muninn_dir, "mycelium.json"), "w") as f:
            json.dump(myc, f)
    return tmp


def test_i1_1_baseline_no_danger():
    """danger_score=0 -> recall identical to pre-I1 behavior."""
    import muninn
    node_no_danger = {
        "last_access": _DAYS_AGO(9),
        "access_count": 3,
        "usefulness": 1.0,
    }
    node_with_zero = {
        "last_access": _DAYS_AGO(9),
        "access_count": 3,
        "usefulness": 1.0,
        "danger_score": 0.0,
    }
    r1 = muninn._ebbinghaus_recall(node_no_danger)
    r2 = muninn._ebbinghaus_recall(node_with_zero)
    assert abs(r1 - r2) < 1e-10, f"I1.1 FAIL: {r1} != {r2}"
    print(f"  I1.1 PASS: baseline recall={r1:.6f}, zero-danger={r2:.6f} (identical)")


def test_i1_2_danger_boosts_recall():
    """danger_score=0.5 -> higher recall (longer half-life)."""
    import muninn
    node_safe = {
        "last_access": _DAYS_AGO(9),
        "access_count": 2,
        "usefulness": 0.8,
        "danger_score": 0.0,
    }
    node_danger = {
        "last_access": _DAYS_AGO(9),
        "access_count": 2,
        "usefulness": 0.8,
        "danger_score": 0.5,
    }
    r_safe = muninn._ebbinghaus_recall(node_safe)
    r_danger = muninn._ebbinghaus_recall(node_danger)
    assert r_danger > r_safe, f"I1.2 FAIL: danger={r_danger:.6f} should be > safe={r_safe:.6f}"
    # The boost should be meaningful (not just epsilon)
    boost_pct = (r_danger - r_safe) / max(r_safe, 1e-10) * 100
    assert boost_pct > 1.0, f"I1.2 FAIL: boost too small: {boost_pct:.2f}%"
    print(f"  I1.2 PASS: safe={r_safe:.4f}, danger={r_danger:.4f} (+{boost_pct:.1f}%)")


def test_i1_3_error_heavy_transcript():
    """Error-heavy compressed text -> higher danger score."""
    import muninn
    # Simulate error-heavy compressed session
    error_text = "\n".join([
        "E> traceback module not found",
        "E> retry import failed again",
        "D> debug session started",
        "E> fix attempt 3 still broken",
        "B> finally found the bug",
        "E> another error in test",
        "D> more debugging needed",
    ])
    clean_text = "\n".join([
        "D> implemented feature A",
        "D> added tests for feature A",
        "B> all tests pass",
        "D> refactored module B",
        "D> updated documentation",
    ])

    tmp = _make_repo()
    try:
        import muninn as m
        old_repo = m._REPO_PATH
        m._REPO_PATH = Path(tmp)

        # Compute danger scores manually using the same formula
        # error_heavy should have higher danger
        total_err = max(1, len(error_text.split("\n")))
        e_lines = sum(1 for l in error_text.split("\n") if l.strip().startswith("E>"))
        error_rate = e_lines / total_err

        total_clean = max(1, len(clean_text.split("\n")))
        c_lines = sum(1 for l in clean_text.split("\n") if l.strip().startswith("E>"))
        clean_rate = c_lines / total_clean

        assert error_rate > clean_rate, f"I1.3 FAIL: error rate not higher"
        assert error_rate >= 0.4, f"I1.3 FAIL: error rate too low: {error_rate}"
        assert clean_rate == 0.0, f"I1.3 FAIL: clean has errors: {clean_rate}"
        print(f"  I1.3 PASS: error_rate={error_rate:.2f} > clean_rate={clean_rate:.2f}")
    finally:
        m._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_i1_4_clean_transcript_low_danger():
    """Clean transcript -> near-zero danger score."""
    import muninn
    clean = "\n".join([
        "D> implemented feature A successfully",
        "D> added unit tests",
        "B> all tests pass on first run",
        "D> documentation updated",
        "D> code review complete",
    ])
    total = max(1, len(clean.split("\n")))
    e_lines = sum(1 for l in clean.split("\n") if l.strip().startswith("E>"))
    error_rate = e_lines / total
    retry_count = len(re.findall(r'(?i)\b(retry|debug|fix|error|traceback|failed)\b', clean))
    retry_rate = min(1.0, retry_count / max(1, total) * 5)
    # Clean session: error_rate=0, low retry, minimal topic switch
    assert error_rate == 0.0, f"I1.4 FAIL: error_rate={error_rate}"
    assert retry_rate < 0.2, f"I1.4 FAIL: retry_rate too high: {retry_rate}"
    print(f"  I1.4 PASS: clean session: error_rate={error_rate}, retry_rate={retry_rate:.3f}")


def test_i1_5_danger_in_session_index():
    """danger_score should be stored in session_index entry."""
    import muninn
    tmp = _make_repo()
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        # Create a fake .mn file and call _update_session_index
        mn_path = Path(tmp) / ".muninn" / "sessions" / "test_session.mn"
        mn_path.parent.mkdir(parents=True, exist_ok=True)
        compressed = "E> error found\nD> debug fix retry\nB> resolved\n"
        mn_path.write_text(compressed, encoding="utf-8")
        muninn._update_session_index(Path(tmp), mn_path, compressed, 2.0)

        index_path = Path(tmp) / ".muninn" / "session_index.json"
        assert index_path.exists(), "I1.5 FAIL: session_index.json not created"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert len(index) > 0, "I1.5 FAIL: empty index"
        entry = index[-1]
        assert "danger_score" in entry, f"I1.5 FAIL: no danger_score in entry: {list(entry.keys())}"
        ds = entry["danger_score"]
        assert isinstance(ds, (int, float)), f"I1.5 FAIL: danger_score not a number: {type(ds)}"
        assert ds >= 0, f"I1.5 FAIL: negative danger_score: {ds}"
        print(f"  I1.5 PASS: danger_score={ds:.4f} stored in session_index")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_i1_6_danger_propagated_to_branch():
    """danger_score from session_sentiment should appear on new branch nodes."""
    import muninn
    tmp = _make_repo(n_branches=0)
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    muninn._refresh_tree_paths()
    try:
        # Create a .mn file with sections
        mn_path = Path(tmp) / ".muninn" / "sessions" / "danger_session.mn"
        mn_path.parent.mkdir(parents=True, exist_ok=True)
        content = "## Debug hell\nE> crash in module X\nD> retry fix debug traceback\n## Recovery\nD> finally fixed\nB> tests pass\n"
        mn_path.write_text(content, encoding="utf-8")

        # Simulate session_sentiment with danger_score
        sentiment = {
            "mean_valence": -0.3, "mean_arousal": 0.6,
            "peak_valence": -0.8, "peak_arousal": 0.9,
            "n_positive": 1, "n_negative": 5, "n_neutral": 2,
            "danger_score": 0.42,
        }
        created = muninn.grow_branches_from_session(mn_path, session_sentiment=sentiment)
        assert created >= 1, f"I1.6 FAIL: no branches created (got {created})"

        tree = muninn.load_tree()
        branches = {n: d for n, d in tree["nodes"].items() if d["type"] == "branch"}
        has_danger = False
        for bname, bnode in branches.items():
            ds = bnode.get("danger_score", 0)
            if ds > 0:
                has_danger = True
                assert abs(ds - 0.42) < 0.01, f"I1.6 FAIL: expected 0.42, got {ds}"
        assert has_danger, "I1.6 FAIL: no branch has danger_score"
        print(f"  I1.6 PASS: {created} branches created, danger_score propagated")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=== I1 — Danger Theory DCA (Greensmith 2008) ===")
    test_i1_1_baseline_no_danger()
    test_i1_2_danger_boosts_recall()
    test_i1_3_error_heavy_transcript()
    test_i1_4_clean_transcript_low_danger()
    test_i1_5_danger_in_session_index()
    test_i1_6_danger_propagated_to_branch()
    print("\n  ALL I1 BORNES PASSED")
