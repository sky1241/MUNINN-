"""
Offline stress test — zero API calls.
Tests ALL post-processing, hints extraction, edge cases.
"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from engine.core.cube import subdivide_file, extract_ast_hints, normalize_content, sha256_hash, Cube
from engine.core.cube_providers import (
    _adjust_line_count, _insert_missing_blanks, _is_continuation,
    _annealing_schedule, MockLLMProvider, reconstruct_cube,
    WaveResult, LevelResult
)

CORPUS = os.path.join(os.path.dirname(__file__), "cube_corpus")


def test_is_continuation_positive():
    """Open parens, commas, operators = continuation."""
    assert _is_continuation("foo(", "    bar)") > 0
    assert _is_continuation("foo(", "bar)") > 0  # same indent ok for (
    assert _is_continuation("x,", "    y") > 0
    assert _is_continuation("x,", "y") > 0  # same indent ok for ,
    assert _is_continuation("x = [", "    1") > 0
    assert _is_continuation("if a ||", "    b") > 0
    assert _is_continuation("if a &&", "    b") > 0
    assert _is_continuation("x.", "    method()") > 0
    assert _is_continuation("x +", "    y") > 0


def test_is_continuation_negative():
    """Non-continuations should score 0."""
    assert _is_continuation("x = 5", "y = 6") == 0
    assert _is_continuation("}", "func next()") == 0
    assert _is_continuation("", "code") == 0
    assert _is_continuation("code", "") == 0


def test_is_continuation_cobol():
    """COBOL column 7 = '-' is a continuation (6 chars before -)."""
    # COBOL: columns 1-6 = sequence (6 chars), column 7 = indicator (index 6)
    assert _is_continuation("000100 X", "000200-CONTINUED") > 0


def test_is_continuation_brace_low_score():
    """{  should have low score (block open, not wrap)."""
    score = _is_continuation("{", "    code")
    assert 0 < score <= 0.2  # low but non-zero


def test_adjust_line_count_single():
    """Join 2 lines into 1."""
    assert _adjust_line_count(["a(", "    b)"], 1) == "a(b)"


def test_adjust_line_count_no_change():
    """Target equals input = no change."""
    assert _adjust_line_count(["a", "b", "c"], 3) == "a\nb\nc"


def test_adjust_line_count_operator():
    """Operator at start of continuation = no extra space."""
    r = _adjust_line_count(["x(", "    +y)"], 1)
    assert "+y)" in r


def test_adjust_line_count_empty():
    """Empty input."""
    assert _adjust_line_count([], 0) == ""


def test_insert_blanks_go():
    """Go: blank after } before non-brace."""
    r = _insert_missing_blanks(["}", "return x"], 3)
    assert r == "}\n\nreturn x"


def test_insert_blanks_python():
    """Python: blank between def blocks."""
    r = _insert_missing_blanks(["def a():", "    pass", "def b():", "    pass"], 5)
    assert "\n\ndef b" in r


def test_insert_blanks_shell():
    """Shell: blank after fi."""
    r = _insert_missing_blanks(["fi", "echo done"], 3)
    assert r == "fi\n\necho done"


def test_insert_blanks_sql():
    """SQL: blank after END;."""
    r = _insert_missing_blanks(["END;", "CREATE TABLE x ("], 3)
    assert r == "END;\n\nCREATE TABLE x ("


def test_insert_blanks_rust():
    """Rust: blank after } before fn."""
    r = _insert_missing_blanks(["}", "fn next() {"], 3)
    assert r == "}\n\nfn next() {"


def test_insert_blanks_cobol():
    """COBOL: blank after END-IF before PERFORM."""
    r = _insert_missing_blanks(["           END-IF", "           PERFORM 2000"], 3)
    assert "\n\n" in r


def test_insert_blanks_no_change():
    """Already correct count = no change."""
    r = _insert_missing_blanks(["a", "", "b"], 3)
    assert r == "a\n\nb"


def test_annealing_schedule_sizes():
    """Schedule length matches n, bookends at 0.0."""
    for n in [1, 2, 3, 5, 11, 20]:
        s = _annealing_schedule(n)
        assert len(s) == n, f"n={n}: len={len(s)}"
        assert s[0] == 0.0, f"n={n}: start={s[0]}"
        assert s[-1] == 0.0, f"n={n}: end={s[-1]}"
        assert all(0 <= t <= 1 for t in s), f"n={n}: out of range"


def test_annealing_peak():
    """Peak should be around 40% through."""
    s = _annealing_schedule(11)
    peak_idx = s.index(max(s))
    assert 3 <= peak_idx <= 5  # ~40% of 11


def test_extract_hints_go():
    """Go hints: identifiers, strings, types extracted."""
    path = os.path.join(CORPUS, "server.go")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=path, target_tokens=112)
    # Cube 5 = PaginatedResponse struct
    hints = extract_ast_hints(cubes[5])
    assert "PaginatedResponse" in hints["identifiers"]
    assert any("items" in s for s in hints["strings"])
    assert any("Items" in t for t in hints["type_sigs"])
    assert hints["first_line"]
    assert hints["last_line"]
    assert len(hints["anchors"]) > 0


def test_extract_hints_python():
    """Python hints."""
    path = os.path.join(CORPUS, "analytics.py")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=path, target_tokens=112)
    hints = extract_ast_hints(cubes[0])
    assert hints["first_line"]
    assert hints["last_line"]
    assert len(hints["identifiers"]) > 0


def test_extract_hints_cobol():
    """COBOL hints."""
    path = os.path.join(CORPUS, "banking.cob")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=path, target_tokens=112)
    hints = extract_ast_hints(cubes[0])
    assert hints["first_line"]
    assert len(hints["identifiers"]) > 0


def test_sha_roundtrip_mock():
    """Mock provider returning exact content = SHA match."""
    content = "func main() {\n\tfmt.Println(\"hello\")\n}"
    cube = Cube(
        id="test:1", content=content, sha256=sha256_hash(content),
        file_origin="test.go", line_start=1, line_end=3, level=0, token_count=10
    )
    neighbor = Cube(
        id="test:0", content="package main",
        sha256=sha256_hash("package main"), file_origin="test.go",
        line_start=0, line_end=0, level=0, token_count=5
    )
    provider = MockLLMProvider(responses={"test.go": content})
    r = reconstruct_cube(cube, [neighbor], provider, ast_hints=extract_ast_hints(cube))
    assert r.exact_match


def test_dataclass_integrity():
    """WaveResult + LevelResult fields."""
    wr = WaveResult(cube_id="x", sha_matched=True, wave_number=1,
                    attempt_in_wave=3, total_attempts=3,
                    best_ncd=0.0, best_reconstruction="code")
    lr = LevelResult(level=1, target_tokens=112, n_cubes=5,
                     sha_matched=2, sha_pct=40.0, avg_best_ncd=0.15,
                     heatmap=[wr])
    assert wr.sha_matched is True
    assert lr.sha_pct == 40.0
    assert lr.heatmap[0].cube_id == "x"


def test_full_corpus_coverage():
    """Every cube in every language has first_line + identifiers."""
    files = ["analytics.py", "server.go", "components.jsx", "cache.rs",
             "store.ts", "allocator.c", "banking.cob", "pipeline.kt"]
    for fname in files:
        path = os.path.join(CORPUS, fname)
        if not os.path.exists(path):
            continue
        with open(path, "r") as f:
            content = f.read()
        cubes = subdivide_file(content=content, file_path=path, target_tokens=112)
        for c in cubes:
            hints = extract_ast_hints(c)
            assert hints["first_line"], f"{fname} cube {c.id}: no first_line"
            assert hints["last_line"], f"{fname} cube {c.id}: no last_line"
            # Some cubes are just closing braces — no identifiers expected
            lines = normalize_content(c.content).split("\n")
            if any(len(l.strip()) > 3 for l in lines):
                assert len(hints["identifiers"]) > 0, f"{fname} cube {c.id}: no identifiers"


def test_cube30_join_and_blank():
    """Cube 30 regression: both join and blank insert produce SHA match."""
    path = os.path.join(CORPUS, "server.go")
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        content = f.read()
    cubes = subdivide_file(content=content, file_path=path, target_tokens=112)
    orig = normalize_content(cubes[30].content)
    ol = orig.split("\n")
    n = len(ol)

    # Smart join
    wrapped = orig.replace(
        "mc.GetPercentile(strings", "mc.GetPercentile(\n\t\t\t\tstrings"
    ).split("\n")
    assert _adjust_line_count(wrapped, n) == orig, "join failed"

    # Blank insert
    reco = [l for j, l in enumerate(ol)
            if not (l == "" and j > 0 and ol[j-1].strip() == "}" and j == 7)]
    assert _insert_missing_blanks(reco, n) == orig, "blank insert failed"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
