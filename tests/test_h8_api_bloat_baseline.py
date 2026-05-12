"""H.8 — API surface baselines, ratchet against silent bloat.

Audit reports flagged ~81% of MyceliumDB methods as "low caller density"
— a sign the public surface has grown beyond what consumers actually
use. H.8 pins the current public-method count so any future PR adding
a method has to justify it (CI red unless baseline is bumped).

This is a RATCHET, not a refactor. It freezes growth at the current
level; cleaning the dead surface itself is Phase J.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE = REPO_ROOT / "engine" / "core"

# Frozen public-method counts (no leading underscore). Captured 2026-05-12.
# If you add a method, decide: is it really needed?
#   - YES → bump the baseline below + justify in commit message.
#   - NO  → prefix with `_` to mark internal, or refactor an existing one.
BASELINES = {
    ("mycelium_db.py", "MyceliumDB"): 52,
    ("mycelium.py", "Mycelium"): 20,
    ("cube.py", "Cube"): 4,
}


def _count_public_methods(path: Path, class_name: str) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return sum(
                1 for item in node.body
                if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
            )
    pytest.skip(f"Class {class_name} not found in {path.name}")
    return 0


@pytest.mark.parametrize("file_name,class_name", list(BASELINES))
def test_h8_public_method_count_does_not_grow(file_name: str, class_name: str) -> None:
    path = CORE / file_name
    if not path.exists():
        pytest.skip(f"{path} missing")
    baseline = BASELINES[(file_name, class_name)]
    actual = _count_public_methods(path, class_name)
    assert actual <= baseline, (
        f"{class_name} has {actual} public methods, baseline is {baseline}. "
        f"Don't grow the public API silently. Either:\n"
        f"  1) prefix the new method with `_` (internal)\n"
        f"  2) refactor an existing method to absorb the new behaviour\n"
        f"  3) bump BASELINES in this test file + justify in commit msg"
    )


def test_h8_baseline_not_under_actual() -> None:
    """If actual drops (cleanup), the baseline should drop too — not stay
    inflated. This catches the "ratchet down" case."""
    drift: list[str] = []
    for (fname, cls), baseline in BASELINES.items():
        path = CORE / fname
        if not path.exists():
            continue
        actual = _count_public_methods(path, cls)
        if actual < baseline - 5:
            drift.append(
                f"{cls}: baseline={baseline} but actual={actual}. "
                f"Lower the baseline to lock in the cleanup."
            )
    if drift:
        pytest.fail("Baselines too loose:\n  " + "\n  ".join(drift))
