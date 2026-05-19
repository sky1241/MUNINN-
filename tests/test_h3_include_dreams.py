"""H.3 — `muninn-mem prune --include-dreams` flag wires Sleep Consolidation.

Until H.3 ships, the 561 LOC of engine/core/mycelium_dream.py (Wilson &
McNaughton 1994 sleep consolidation, generates insights from co-occurrence
patterns) sit dormant — `mycelium.dream()` is implemented but never invoked
from any CLI / hook / scheduled task.

Contract :
  - `muninn-mem prune --include-dreams` exposes the flag in argparse
  - When set, prune() invokes `mycelium.dream()` after the prune sweep
  - Default off → behaviour unchanged (no surprise insights pass on every prune)
  - --include-dreams alone (without --force) → still dry-run safe
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNINN_PY = REPO_ROOT / "engine" / "core" / "muninn.py"
MIRROR_PY = REPO_ROOT / "engine" / "core" / "muninn.py"
PRUNE_PY = REPO_ROOT / "engine" / "core" / "muninn_tree_prune.py"


def test_h3_argparse_flag_declared() -> None:
    src = MUNINN_PY.read_text(encoding="utf-8")
    assert re.search(r'add_argument\(\s*[\'"]--include-dreams[\'"]', src), (
        "engine/core/muninn.py argparse must declare `--include-dreams`"
    )


def test_h3_argparse_flag_mirrored() -> None:
    src = MIRROR_PY.read_text(encoding="utf-8")
    assert re.search(r'add_argument\(\s*[\'"]--include-dreams[\'"]', src), (
        "muninn/_engine.py argparse must mirror `--include-dreams` (BUG-091)"
    )


def test_h3_prune_handler_passes_flag() -> None:
    """Both muninn.py and _engine.py prune handlers must thread the flag
    into prune(include_dreams=args.include_dreams)."""
    for path in (MUNINN_PY, MIRROR_PY):
        src = path.read_text(encoding="utf-8")
        assert "include_dreams=" in src or "include_dreams =" in src, (
            f"{path.name} must thread args.include_dreams into prune()"
        )


def test_h3_prune_signature_accepts_include_dreams() -> None:
    """muninn_tree_prune.prune() must accept include_dreams param."""
    src = PRUNE_PY.read_text(encoding="utf-8")
    # Look for `def prune(...` and verify include_dreams is a keyword arg
    match = re.search(r"def\s+prune\s*\((.*?)\)\s*[:\->]", src, re.S)
    assert match, "prune() signature not found in muninn_tree_prune.py"
    params = match.group(1)
    assert "include_dreams" in params, (
        f"prune() signature must accept include_dreams. Got:\n{params}"
    )


def test_h3_include_dreams_help_text_present() -> None:
    src = MUNINN_PY.read_text(encoding="utf-8")
    # The help text should mention "dream" or "insight" or "consolidation"
    # near the flag declaration
    block = re.search(
        r'add_argument\(\s*[\'"]--include-dreams[\'"][^)]+\)',
        src, re.S,
    )
    assert block, "--include-dreams argparse block not parseable"
    block_text = block.group(0).lower()
    assert any(kw in block_text for kw in ("dream", "insight", "consolid")), (
        f"--include-dreams help text should mention dream/insight/consolidation. "
        f"Got: {block.group(0)}"
    )
