"""PHASE B BRICK 12 — pin L12 fact-recall behavior.

Two contracts to lock:

1. With a generous budget (>= original file size), L12 must NOT
   regress fact recall vs L12 OFF on the existing benchmark files.

2. With a tight budget (< original / 2), L12 IS expected to drop
   facts. This is documented limitation BUG-104 — the test asserts
   the loss to make sure we never silently "improve" L12 to claim
   it has no trade-off when in fact it does.

If this test fails because BUG-104 was fixed and tight-budget L12
now preserves facts, that is GREAT — update the test thresholds
upward and update PHASE_B_FACT_RECALL.md.
"""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
BENCH_DIR = REPO_ROOT / "tests" / "benchmark"


@pytest.fixture(scope="module")
def ml():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import muninn  # noqa: F401
    import muninn_layers
    importlib.reload(muninn_layers)
    # Disable L9 (no API call, deterministic)
    muninn_layers._llm_compress = lambda text, context="": text
    return muninn_layers


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("MUNINN_L12_BUDGET", None)
    yield
    os.environ.pop("MUNINN_L12_BUDGET", None)
    if saved is not None:
        os.environ["MUNINN_L12_BUDGET"] = saved


def _run_recall(ml, sample_name, questions_name):
    sample = BENCH_DIR / sample_name
    questions_path = BENCH_DIR / questions_name
    if not sample.exists() or not questions_path.exists():
        pytest.skip(f"benchmark file missing: {sample_name}")
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    compressed = ml.compress_file(sample)
    answered = 0
    for q in questions:
        ans = q["answer"]
        found = ans.lower() in compressed.lower()
        if not found:
            clean = ans.replace(",", "")
            found = clean.lower() in compressed.lower()
        if not found and any(c.isdigit() for c in ans):
            digits = "".join(c for c in ans if c.isdigit() or c == ".")
            if digits and len(digits) >= 2:
                found = digits in compressed
        if found:
            answered += 1
    return answered, len(questions)


# ── Generous-budget contract: ZERO regression ──────────────────


def test_l12_off_baseline_verbose(ml):
    """Document the L12-OFF baseline so future regressions are visible."""
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    assert answered == 15 and total == 15, (
        f"verbose_memory L12 OFF baseline drift: {answered}/{total} (was 15/15)"
    )


def test_l12_huge_budget_no_regression_verbose(ml):
    """L12 with huge budget must keep all facts (same as OFF)."""
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    assert answered == 15, (
        f"L12 with huge budget regressed verbose_memory: {answered}/{total}"
    )


def test_l12_off_baseline_session(ml):
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    assert answered == 12 and total == 15, (
        f"sample_session L12 OFF baseline drift: {answered}/{total} (was 12/15)"
    )


def test_l12_huge_budget_no_regression_session(ml):
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    assert answered == 12, (
        f"L12 with huge budget regressed sample_session: {answered}/{total}"
    )


def test_l12_huge_budget_no_regression_compact(ml):
    os.environ["MUNINN_L12_BUDGET"] = "5000"
    answered, total = _run_recall(ml, "sample_compact.md", "questions_compact.json")
    assert answered == 8


# ── Tight-budget contract: BUG-104 documents the loss ──────────


def test_l12_tight_budget_loses_facts_verbose_bug_104(ml):
    """BUG-104 documentation: at tight budget, verbose_memory loses
    a measurable number of facts. This test EXPECTS the loss so it
    fails the day BUG-104 is fixed (alerts to update the doc)."""
    os.environ["MUNINN_L12_BUDGET"] = "500"
    answered, total = _run_recall(ml, "verbose_memory.md", "questions_verbose.json")
    # Empirically measured 2026-04-10: 6/15 (40%)
    # If this drops to 0/15, the algorithm broke. If it rises to 14+/15,
    # BUG-104 was fixed and this test should be updated.
    assert 3 <= answered <= 12, (
        f"verbose_memory at b=500 returned {answered}/15 — outside expected "
        f"BUG-104 envelope [3, 12]. Either the algorithm broke or improved "
        f"meaningfully. Update PHASE_B_FACT_RECALL.md."
    )


def test_l12_tight_budget_loses_facts_session_bug_104(ml):
    os.environ["MUNINN_L12_BUDGET"] = "500"
    answered, total = _run_recall(ml, "sample_session.md", "questions_session.json")
    # Empirically measured 2026-04-10: 9/15 (60%)
    assert 6 <= answered <= 13, (
        f"sample_session at b=500 returned {answered}/15 — outside BUG-104 envelope [6, 13]"
    )


def test_phase_b_fact_recall_doc_exists():
    """The benchmark results doc must exist and be non-trivial."""
    doc = BENCH_DIR / "PHASE_B_FACT_RECALL.md"
    assert doc.exists(), "PHASE_B_FACT_RECALL.md missing"
    text = doc.read_text(encoding="utf-8")
    assert "BUG-104" in text
    assert "verbose_memory" in text
    assert "100.0%" in text and "40.0%" in text  # the headline numbers
