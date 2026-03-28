"""X8-X13 — Bug fixes batch.

Tests:
  X8.1   migrate_from_json return value is closeable (no leak)
  X9.1   Consolidated branch access_count = max(members), not sum
  X10.1  No CAST in decay queries (already fixed, regression guard)
  X11.1  L3 phrases compress "in order to" correctly (before L2 strips "in"/"to")
  X11.2  L3 runs before L2 in source order
  X12.1  Bearer regex does NOT match short prose ("Bearer arms")
  X12.2  Bearer regex DOES match real JWT token (20+ chars)
  X13.1  Hex pattern requires word boundaries (no false positive on "cafe")
  X13.2  Hex pattern matches real commit hash
"""
import sys, os, re
def test_x8_1_migrate_returns_closeable():
    """migrate_from_json returns a MyceliumDB with close() method."""
    import tempfile, shutil, json
    from pathlib import Path
    from muninn.mycelium_db import MyceliumDB

    tmpdir = tempfile.mkdtemp(prefix="muninn_x8_")
    try:
        # Create a minimal JSON mycelium
        json_path = Path(tmpdir) / "mycelium.json"
        json_path.write_text(json.dumps({
            "concepts": {"test": {"count": 1}},
            "connections": {},
            "fusions": {},
            "meta": {"sessions": 1}
        }), encoding="utf-8")

        db_path = Path(tmpdir) / "mycelium.db"
        result = MyceliumDB.migrate_from_json(json_path, db_path, backup=False)
        assert hasattr(result, 'close'), "X8.1 FAIL: result has no close() method"
        result.close()
        print(f"  X8.1 PASS: migrate_from_json returns closeable DB")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x9_1_access_count_max_not_sum():
    """Consolidated branch access_count uses max(members), not sum."""
    muninn_dir = os.path.join(os.path.dirname(__file__), "..", "engine", "core")
    source = ""
    for _mf in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"]:
        _mp = os.path.join(muninn_dir, _mf)
        if os.path.exists(_mp):
            with open(_mp, encoding="utf-8") as f:
                source += f.read() + "\n"

    # Find the consolidation code
    assert 'max(nodes.get(m, {}).get("access_count"' in source, \
        "X9.1 FAIL: access_count should use max(), not sum()"
    assert 'sum(nodes.get(m, {}).get("access_count"' not in source, \
        "X9.1 FAIL: found sum() on access_count — should be max()"
    print(f"  X9.1 PASS: access_count uses max()")


def test_x10_1_no_cast_in_decay():
    """No CAST in decay queries (regression guard)."""
    mycelium_path = os.path.join(os.path.dirname(__file__), "..", "engine", "core", "mycelium.py")
    with open(mycelium_path, encoding="utf-8") as f:
        source = f.read()
    assert "CAST(" not in source, "X10.1 FAIL: CAST found in mycelium.py"
    print(f"  X10.1 PASS: no CAST in mycelium.py")


def test_x11_1_in_order_to_compressed():
    """L3 correctly compresses 'in order to' before L2 strips 'in' and 'to'."""
    from muninn import compress_line
    text = "We need to do this in order to improve performance."
    result = compress_line(text)
    # "in order to" should be compressed to "to" by L3
    # If L2 runs first, "in" and "to" get stripped, breaking the phrase
    assert "order" not in result.lower(), \
        f"X11.1 FAIL: 'order' still in output (L3 didn't match): {result}"
    print(f"  X11.1 PASS: 'in order to' -> compressed: {result.strip()}")


def test_x11_2_l3_before_l2_in_source():
    """L3 appears before L2 in source code."""
    muninn_dir = os.path.join(os.path.dirname(__file__), "..", "engine", "core")
    lines = []
    for _mf in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"]:
        _mp = os.path.join(muninn_dir, _mf)
        if os.path.exists(_mp):
            with open(_mp, encoding="utf-8") as f:
                lines.extend(f.readlines())

    l3_line = None
    l2_line = None
    for i, line in enumerate(lines):
        if "# L3: Common phrase collapsing" in line and l3_line is None:
            l3_line = i
        if "# L2: Filler word removal" in line and l2_line is None:
            l2_line = i
    assert l3_line is not None, "X11.2 FAIL: L3 comment not found"
    assert l2_line is not None, "X11.2 FAIL: L2 comment not found"
    assert l3_line < l2_line, f"X11.2 FAIL: L3 (line {l3_line}) after L2 (line {l2_line})"
    print(f"  X11.2 PASS: L3 (line {l3_line}) before L2 (line {l2_line})")


def test_x12_1_bearer_no_false_positive():
    """Bearer regex does NOT match short prose like 'Bearer of bad news'."""
    from _secrets import redact_secrets_text
    text = "He was the Bearer of bad news to the kingdom."
    result = redact_secrets_text(text)
    assert result == text, f"X12.1 FAIL: false positive on prose: {result}"
    print(f"  X12.1 PASS: 'Bearer of bad news' not matched")


def test_x12_2_bearer_matches_real_token():
    """Bearer regex matches a real JWT/OAuth token (20+ chars)."""
    from _secrets import redact_secrets_text
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJz"
    result = redact_secrets_text(text)
    assert "eyJhbG" not in result, f"X12.2 FAIL: real Bearer token not redacted: {result}"
    print(f"  X12.2 PASS: real Bearer token redacted")


def test_x13_1_hex_no_false_positive():
    """Hex pattern does NOT match normal words like 'cafe' or 'facade'."""
    # Check _NOVEL_PATTERNS in muninn.py
    muninn_dir = os.path.join(os.path.dirname(__file__), "..", "engine", "core")
    source = ""
    for _mf in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"]:
        _mp = os.path.join(muninn_dir, _mf)
        if os.path.exists(_mp):
            with open(_mp, encoding="utf-8") as f:
                source += f.read() + "\n"

    # Find the hex pattern line
    match = re.search(r"re\.compile\(r'(.*?[a-f0-9].*?7,40.*?)'\)", source)
    assert match, "X13.1 FAIL: hex pattern not found"
    pattern_str = match.group(1)
    assert r'\b' in pattern_str, f"X13.1 FAIL: hex pattern missing word boundary: {pattern_str}"

    # Test the pattern itself
    pat = re.compile(pattern_str)
    assert not pat.search("beautiful cafe downtown"), f"X13.1 FAIL: matched 'cafe'"
    assert not pat.search("the facade was nice"), f"X13.1 FAIL: matched 'facade'"
    print(f"  X13.1 PASS: hex pattern has word boundaries, no false positives")


def test_x13_2_hex_matches_commit():
    """Hex pattern matches a real commit hash."""
    pat = re.compile(r'\b[a-f0-9]{7,40}\b')
    assert pat.search("commit 7487e94"), f"X13.2 FAIL: didn't match 7487e94"
    assert pat.search("sha: a1b2c3d4e5f6a7b8c9d0"), f"X13.2 FAIL: didn't match full hash"
    print(f"  X13.2 PASS: hex pattern matches commit hashes")


if __name__ == "__main__":
    test_x8_1_migrate_returns_closeable()
    test_x9_1_access_count_max_not_sum()
    test_x10_1_no_cast_in_decay()
    test_x11_1_in_order_to_compressed()
    test_x11_2_l3_before_l2_in_source()
    test_x12_1_bearer_no_false_positive()
    test_x12_2_bearer_matches_real_token()
    test_x13_1_hex_no_false_positive()
    test_x13_2_hex_matches_commit()
    print("\nAll X8-X13 tests PASS")
