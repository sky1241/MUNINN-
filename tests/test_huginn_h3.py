"""H3 — Huginn CLI: the thinking raven formulates insights.

Tests:
  H3.1  huginn_think() returns list of dicts with required keys
  H3.2  Relevance filtering: query-matching insights rank higher
  H3.3  Empty insights.json = empty list, no crash
  H3.4  Formatted output contains icon and score
  H3.5  _surface_insights_for_boot() returns string with header
  H3.6  top_n parameter limits results
  H3.7  "think" in CLI choices
  H3.8  huginn_think wired in boot() (code check)
"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from pathlib import Path


def _make_insights_dir(insights=None):
    """Create a temp repo with .muninn/insights.json."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    if insights is not None:
        path = os.path.join(muninn_dir, "insights.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(insights, f)
    return tmp


def _sample_insights():
    """Sample insights for testing."""
    import time
    ts = time.strftime("%Y-%m-%d %H:%M")
    return [
        {"type": "strong_pair", "concepts": ["alpha", "beta"],
         "score": 33.5, "text": "alpha and beta are inseparable (x33.5 avg strength)",
         "timestamp": ts},
        {"type": "absence", "concepts": ["hub1", "hub2"],
         "score": 8.0, "text": "hub1 (deg=8) and hub2 (deg=8) never co-occur — blind spot?",
         "timestamp": ts},
        {"type": "health", "concepts": [],
         "score": 0.92, "text": "Graph entropy: 3.45/3.75 (health=92%, 1.0=max diversity)",
         "timestamp": ts},
        {"type": "validated_dream", "concepts": ["red", "gamma"],
         "score": 3, "text": "Dream connection red-gamma confirmed by real usage (count=3)",
         "timestamp": ts},
        {"type": "imbalance", "concepts": ["zone_main"],
         "score": 0.75, "text": "Zone 'zone_main' dominates with 75% of concepts",
         "timestamp": ts},
    ]


def test_h3_1_returns_list():
    """huginn_think() should return a list of dicts with required keys."""
    import muninn
    tmp = _make_insights_dir(_sample_insights())
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        result = muninn.huginn_think()
        assert isinstance(result, list), f"H3.1 FAIL: not a list: {type(result)}"
        assert len(result) > 0, "H3.1 FAIL: empty results with sample data"
        for ins in result:
            assert isinstance(ins, dict), f"H3.1 FAIL: not a dict"
            for key in ["type", "text", "score", "age", "formatted"]:
                assert key in ins, f"H3.1 FAIL: missing key {key}"
        print(f"  H3.1 PASS: {len(result)} insights, all valid dicts")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_2_relevance():
    """Query-matching insights should rank higher."""
    import muninn
    tmp = _make_insights_dir(_sample_insights())
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        result = muninn.huginn_think(query="alpha beta")
        assert len(result) > 0, "H3.2 FAIL: no results"
        # First result should be the strong_pair with alpha+beta
        assert result[0]["type"] == "strong_pair", \
            f"H3.2 FAIL: expected strong_pair first, got {result[0]['type']}"
        assert "alpha" in result[0]["text"], "H3.2 FAIL: alpha not in top result"
        print(f"  H3.2 PASS: relevance filtering works, top={result[0]['type']}")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_3_empty_no_crash():
    """No insights.json = empty list, no crash."""
    import muninn
    tmp = _make_insights_dir()  # no insights file
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        result = muninn.huginn_think()
        assert result == [], f"H3.3 FAIL: expected [], got {result}"
        # Also test with empty list
        tmp2 = _make_insights_dir([])
        muninn._REPO_PATH = Path(tmp2)
        result2 = muninn.huginn_think()
        assert result2 == [], f"H3.3 FAIL: expected [] for empty list"
        shutil.rmtree(tmp2)
        print("  H3.3 PASS: empty insights, no crash")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_4_formatted_output():
    """Formatted string should contain icon and score."""
    import muninn
    tmp = _make_insights_dir(_sample_insights())
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        result = muninn.huginn_think()
        for ins in result:
            fmt = ins["formatted"]
            assert "[" in fmt and "]" in fmt, f"H3.4 FAIL: no icon brackets in: {fmt}"
            assert "score=" in fmt, f"H3.4 FAIL: no score in: {fmt}"
        print(f"  H3.4 PASS: all {len(result)} insights have icon+score in formatted")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_5_surface_boot():
    """_surface_insights_for_boot() should return string with header."""
    import muninn
    tmp = _make_insights_dir(_sample_insights())
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        output = muninn._surface_insights_for_boot("alpha")
        assert isinstance(output, str), f"H3.5 FAIL: not a string"
        assert "huginn_insights" in output, f"H3.5 FAIL: missing header"
        assert "alpha" in output, f"H3.5 FAIL: alpha not in output"
        # Empty case
        tmp2 = _make_insights_dir()
        muninn._REPO_PATH = Path(tmp2)
        empty = muninn._surface_insights_for_boot()
        assert empty == "", f"H3.5 FAIL: expected empty string, got: {empty}"
        shutil.rmtree(tmp2)
        print(f"  H3.5 PASS: boot surface works, {len(output)} chars")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_6_top_n():
    """top_n should limit results."""
    import muninn
    tmp = _make_insights_dir(_sample_insights())
    old_repo = muninn._REPO_PATH
    muninn._REPO_PATH = Path(tmp)
    try:
        result = muninn.huginn_think(top_n=2)
        assert len(result) <= 2, f"H3.6 FAIL: got {len(result)} results with top_n=2"
        result_all = muninn.huginn_think(top_n=100)
        assert len(result_all) == 5, f"H3.6 FAIL: expected 5, got {len(result_all)}"
        print(f"  H3.6 PASS: top_n=2 gives {len(result)}, top_n=100 gives {len(result_all)}")
    finally:
        muninn._REPO_PATH = old_repo
        shutil.rmtree(tmp)


def test_h3_7_in_cli():
    """'think' should be in CLI choices."""
    import muninn
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["muninn.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    assert '"think"' in src, "H3.7 FAIL: think not in CLI choices"
    print("  H3.7 PASS: think in CLI choices")


def test_h3_8_wired_in_boot():
    """Huginn insights should be surfaced in boot()."""
    import muninn
    _mdir = Path(muninn.__file__).parent
    src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["muninn.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
    boot_start = src.find("def boot(")
    boot_end = src.find("\ndef ", boot_start + 1)
    boot_body = src[boot_start:boot_end]
    assert "_surface_insights_for_boot" in boot_body, \
        "H3.8 FAIL: _surface_insights_for_boot not wired in boot()"
    assert "H3" in boot_body, "H3.8 FAIL: H3 comment not in boot()"
    print("  H3.8 PASS: huginn_think wired in boot()")


if __name__ == "__main__":
    print("=== H3 — Huginn CLI: the thinking raven ===")
    test_h3_1_returns_list()
    test_h3_2_relevance()
    test_h3_3_empty_no_crash()
    test_h3_4_formatted_output()
    test_h3_5_surface_boot()
    test_h3_6_top_n()
    test_h3_7_in_cli()
    test_h3_8_wired_in_boot()
    print("\n  ALL H3 BORNES PASSED")
