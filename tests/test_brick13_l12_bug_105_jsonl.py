"""PHASE B BRICK 13 — pin BUG-105 fix.

When the input has fewer than 2 paragraph chunks (split on \\n\\s*\\n),
L12 must NOT run. This protects JSONL transcripts, log files, CSVs,
single-paragraph .md, and any other format that lacks blank lines.

If anyone removes the chunk-count guard in _l12_budget_pass(), this
test fails immediately. The pre-fix behavior collapsed a 22MB JSONL
transcript to 8 tokens — destruction, not compression.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


@pytest.fixture(scope="module")
def ml():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import muninn  # noqa: F401
    import muninn_layers
    importlib.reload(muninn_layers)
    muninn_layers._llm_compress = lambda text, context="": text
    return muninn_layers


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("MUNINN_L12_BUDGET", None)
    yield
    os.environ.pop("MUNINN_L12_BUDGET", None)
    if saved is not None:
        os.environ["MUNINN_L12_BUDGET"] = saved


# ── Single-chunk inputs must be IDENTITY ─────────────────────


def test_jsonl_single_chunk_protected(ml):
    """A JSONL file (no \\n\\n) must pass through L12 unchanged."""
    text = "\n".join([
        '{"role": "user", "content": "hello there friend"}',
        '{"role": "assistant", "content": "hi back to you"}',
        '{"role": "user", "content": "deploy v2.3.1 on 2026-04-10 please"}',
    ] * 50)
    os.environ["MUNINN_L12_BUDGET"] = "100"
    out = ml._l12_budget_pass(text)
    assert out == text, (
        f"BUG-105 REGRESSION: JSONL input was modified. "
        f"In: {len(text)} chars, Out: {len(out)} chars."
    )


def test_log_file_single_chunk_protected(ml):
    """Log files (one entry per line) must pass through L12 unchanged."""
    text = "\n".join([
        f"2026-04-11 12:00:{i:02d} INFO request handled in {i*5}ms"
        for i in range(60)
    ])
    os.environ["MUNINN_L12_BUDGET"] = "50"
    out = ml._l12_budget_pass(text)
    assert out == text


def test_csv_single_chunk_protected(ml):
    """CSV files must pass through L12 unchanged."""
    text = "\n".join([
        "id,name,value,timestamp",
        "1,foo,100,2026-01-01",
        "2,bar,200,2026-01-02",
        "3,baz,300,2026-01-03",
    ] * 20)
    os.environ["MUNINN_L12_BUDGET"] = "50"
    out = ml._l12_budget_pass(text)
    assert out == text


def test_single_paragraph_md_protected(ml):
    """A markdown file with no \\n\\n must pass through L12 unchanged."""
    text = (
        "This is a long single paragraph of text that has no blank lines "
        "anywhere inside it at all. It contains some facts like v2.3.1 "
        "and 2026-04-11 and abc1234 commit hash but they are all in one "
        "single chunk so L12 cannot select between them. The BUG-105 "
        "guard must therefore return identity for this input no matter "
        "how aggressive the budget is set by the caller."
    )
    os.environ["MUNINN_L12_BUDGET"] = "5"
    out = ml._l12_budget_pass(text)
    assert out == text


def test_empty_string_safe(ml):
    os.environ["MUNINN_L12_BUDGET"] = "10"
    assert ml._l12_budget_pass("") == ""


def test_none_safe(ml):
    os.environ["MUNINN_L12_BUDGET"] = "10"
    assert ml._l12_budget_pass(None) == ""


# ── Multi-chunk inputs must STILL run L12 normally ───────────


def test_multi_chunk_md_still_compresses(ml):
    """L12 must still work on multi-paragraph input — BUG-105 fix
    is a guard, not a kill switch."""
    paras = [
        "First filler paragraph completely empty of useful information.",
        "Second filler paragraph with no specific facts to share here today.",
        "Third critical paragraph with v2.3.1 deployed on 2026-04-10 fixing BUG-101.",
        "Fourth filler paragraph saying nothing important about anything.",
        "Fifth Muninn compression hit x4.5 ratio with commit abc1234 today.",
        "Sixth filler paragraph again repeating no specific facts inside.",
    ]
    text = "\n\n".join(paras)
    os.environ["MUNINN_L12_BUDGET"] = "20"
    out = ml._l12_budget_pass(text)
    assert len(out) < len(text), (
        f"BRICK 13 BROKEN: BUG-105 fix neutered L12 entirely. "
        f"Input {len(text)}, output {len(out)}"
    )
    # At least one fact must survive
    assert "abc1234" in out or "v2.3.1" in out or "BUG-101" in out, (
        "L12 dropped ALL fact spans on multi-chunk input"
    )


# ── Real-world: the actual JSONL transcript that crashed pre-fix ──


def test_real_22mb_transcript_safe_via_helper(ml):
    """The exact file that exposed BUG-105. If this file is missing
    on the runner, skip — but if present, verify it stays intact."""
    src = Path(
        "c:/Users/ludov/.claude/projects/c--Users-ludov-MUNINN-/"
        "d00638e7-4405-43c3-b0c2-7523f0907c18.jsonl"
    )
    if not src.exists():
        pytest.skip(f"benchmark transcript not present: {src}")
    text = src.read_text(encoding="utf-8", errors="replace")
    n_chunks = len(text.split("\n\n"))
    assert n_chunks == 1, (
        f"transcript was supposed to be single-chunk, got {n_chunks}"
    )
    os.environ["MUNINN_L12_BUDGET"] = "1000"
    out = ml._l12_budget_pass(text)
    assert out == text, (
        f"BUG-105 REGRESSION on real 22MB transcript: "
        f"in {len(text):,}, out {len(out):,}"
    )


# ── Doc reference ────────────────────────────────────────────


def test_phase_b_big_file_benchmark_doc_exists():
    doc = REPO_ROOT / "tests" / "benchmark" / "PHASE_B_BIG_FILE_BENCHMARK.md"
    assert doc.exists(), "PHASE_B_BIG_FILE_BENCHMARK.md missing"
    text = doc.read_text(encoding="utf-8")
    assert "BUG-105" in text
    assert "23,359,701" in text  # the headline char count
    assert "8 tokens" in text  # the disaster pre-fix
