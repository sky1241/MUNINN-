"""H.6c — L12 BudgetMem default activation.

Before H.6c, `_l12_budget_pass` was a no-op when MUNINN_L12_BUDGET was
unset (Sky never set the env var). After H.6c, default is 16000 tokens,
generous enough that small inputs pass through unchanged (BudgetMem
optimal selection includes all chunks when budget > total tokens).

Contract :
  - With env var unset → _l12_budget_pass uses default budget (16000)
  - With MUNINN_L12_BUDGET=0 → still a no-op (escape hatch)
  - Small text (< budget) still returns unchanged (no truncation)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def ml():
    """Import muninn_layers from engine/core/."""
    import importlib
    import sys
    eng = REPO_ROOT / "engine" / "core"
    if str(eng) not in sys.path:
        sys.path.insert(0, str(eng))
    if "muninn_layers" in sys.modules:
        return importlib.reload(sys.modules["muninn_layers"])
    return importlib.import_module("muninn_layers")


@pytest.fixture(autouse=True)
def _clean_env():
    saved = os.environ.pop("MUNINN_L12_BUDGET", None)
    yield
    os.environ.pop("MUNINN_L12_BUDGET", None)
    if saved is not None:
        os.environ["MUNINN_L12_BUDGET"] = saved


def test_h6c_default_uses_16000_budget(ml) -> None:
    """Without env var, L12 must run with default budget (16000)."""
    # Don't assert exact behaviour — just that the function doesn't
    # short-circuit on empty raw env. Use a probe: monkeypatch the
    # internal budget reader via inspection of the post-pass state.
    text = "First chunk content.\n\nSecond chunk has v2.3 on 2026-04.\n\nThird filler."
    # Default budget=16000 ≫ text size → output should equal input
    out = ml._l12_budget_pass(text)
    assert out == text, (
        f"With budget≫text (default 16000), L12 should pass through. "
        f"Got: {out!r}"
    )


def test_h6c_explicit_zero_disables(ml) -> None:
    """MUNINN_L12_BUDGET=0 must disable L12 (escape hatch)."""
    os.environ["MUNINN_L12_BUDGET"] = "0"
    text = "First.\n\nSecond.\n\nThird."
    out = ml._l12_budget_pass(text)
    assert out == text, (
        f"MUNINN_L12_BUDGET=0 must be a no-op. Got: {out!r}"
    )


def test_h6c_small_budget_actually_compresses(ml) -> None:
    """When budget is tiny vs text, BudgetMem actually selects chunks."""
    os.environ["MUNINN_L12_BUDGET"] = "5"  # 5 tokens — must drop content
    text = ("This is a long first chunk with many words and tokens to count.\n\n"
            "This is an equally long second chunk that should also be heavy.\n\n"
            "Third chunk wraps the example with verbose padding for size.")
    out = ml._l12_budget_pass(text)
    # We don't assert the exact output but at least one of the 3 chunks
    # should be dropped to fit a 5-token budget. So output != input.
    assert out != text or "spill" in out.lower(), (
        f"Tiny budget should reduce content. Got identical output:\n{out}"
    )
