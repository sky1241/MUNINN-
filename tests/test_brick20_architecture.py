"""BRICK 20 — pin architecture thresholds for engine/core/.

Asserts that no module / function exceeds the documented WARN/CRITICAL
thresholds. The known oversized items (boot 646 lines, prune 409, etc.)
are listed in DOCUMENTED_OVERSIZED so a future regression that adds a
NEW oversized item triggers the test, but the existing debt doesn't.

See `tests/benchmark/PHASE_B_ARCHITECTURE_AUDIT.md` for the full report.
"""
import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = REPO_ROOT / "engine" / "core"

# Documented architectural debt — these items existed before brick 20
# and would require multi-day refactors to fix. Adding to this set
# requires a justification in PHASE_B_ARCHITECTURE_AUDIT.md.
DOCUMENTED_OVERSIZED_MODULES = frozenset({
    "muninn_tree.py",   # 3673 lines, split candidate documented
    "mycelium.py",      # 3040 lines, mixin split candidate documented
})

DOCUMENTED_OVERSIZED_FUNCTIONS = frozenset({
    # (file, function) pairs known to be over thresholds
    ("muninn_tree.py", "boot"),       # 646 lines
    ("muninn.py",      "main"),       # 503 lines (CLI dispatcher)
    ("muninn.py",      "scan_repo"),  # 210+ lines (CHUNK 9: + neuron map gen)
    ("bible_scraper.py", "_core_bible"),  # 478 lines (private helper)
    ("muninn_tree.py", "prune"),      # 409 lines
    ("orchestrator.py", "scan"),      # 370 lines
    ("muninn_feed.py", "compress_transcript"),  # 228 lines
    ("muninn_layers.py", "compress_line"),  # 208 lines
})

# Hard caps that NO file/function may cross going forward
HARD_CAP_MODULE_LINES = 4000
HARD_CAP_FUNCTION_LINES = 700


def _scan_engine_core():
    """Return (modules, functions) where each is a list of (lines, name)."""
    modules = []
    functions = []
    for f in ENGINE.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_lines = text.count("\n") + 1
        modules.append((n_lines, f.name))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                end = node.end_lineno or node.lineno
                fn_lines = end - node.lineno + 1
                functions.append((fn_lines, f.name, node.name))
    return modules, functions


# ── Hard caps ────────────────────────────────────────────────


def test_no_module_above_hard_cap():
    """No file may exceed HARD_CAP_MODULE_LINES (4000)."""
    modules, _ = _scan_engine_core()
    over = [(n, name) for n, name in modules if n > HARD_CAP_MODULE_LINES]
    assert not over, (
        f"Module(s) over hard cap {HARD_CAP_MODULE_LINES}: {over}\n"
        f"This is non-negotiable. Split the file before merging."
    )


def test_no_function_above_hard_cap():
    """No function may exceed HARD_CAP_FUNCTION_LINES (700)."""
    _, functions = _scan_engine_core()
    over = [(n, fname, name) for n, fname, name in functions if n > HARD_CAP_FUNCTION_LINES]
    assert not over, (
        f"Function(s) over hard cap {HARD_CAP_FUNCTION_LINES}: {over}\n"
        f"This is non-negotiable. Refactor the function before merging."
    )


# ── Soft caps with documented exceptions ────────────────────


def test_no_new_oversized_modules():
    """No NEW module > 2500 lines beyond the documented set."""
    modules, _ = _scan_engine_core()
    new_oversized = [
        name for n, name in modules
        if n > 2500 and name not in DOCUMENTED_OVERSIZED_MODULES
    ]
    assert not new_oversized, (
        f"NEW oversized modules: {new_oversized}\n"
        f"Either split them or add to DOCUMENTED_OVERSIZED_MODULES "
        f"with a refactor plan in PHASE_B_ARCHITECTURE_AUDIT.md."
    )


def test_no_new_oversized_functions():
    """No NEW function > 200 lines beyond the documented set."""
    _, functions = _scan_engine_core()
    new_oversized = [
        (fname, name)
        for n, fname, name in functions
        if n > 200 and (fname, name) not in DOCUMENTED_OVERSIZED_FUNCTIONS
    ]
    assert not new_oversized, (
        f"NEW oversized functions: {new_oversized}\n"
        f"Either refactor or add to DOCUMENTED_OVERSIZED_FUNCTIONS "
        f"with a refactor plan."
    )


# ── Documented set is still accurate ────────────────────────


def test_documented_oversized_modules_still_oversized():
    """Sanity: every entry in DOCUMENTED_OVERSIZED_MODULES is actually
    oversized. If a documented module shrinks below the threshold, it
    should be removed from the set."""
    modules, _ = _scan_engine_core()
    by_name = {name: n for n, name in modules}
    no_longer_oversized = []
    for documented in DOCUMENTED_OVERSIZED_MODULES:
        if documented in by_name and by_name[documented] <= 2500:
            no_longer_oversized.append((documented, by_name[documented]))
    assert not no_longer_oversized, (
        f"Modules no longer over the 2500 threshold: {no_longer_oversized}\n"
        f"Remove them from DOCUMENTED_OVERSIZED_MODULES."
    )


def test_documented_oversized_functions_still_oversized():
    _, functions = _scan_engine_core()
    by_key = {(fname, name): n for n, fname, name in functions}
    no_longer = []
    for fname, name in DOCUMENTED_OVERSIZED_FUNCTIONS:
        if (fname, name) in by_key and by_key[(fname, name)] <= 200:
            no_longer.append((fname, name, by_key[(fname, name)]))
    assert not no_longer, (
        f"Functions no longer > 200 lines: {no_longer}\n"
        f"Remove them from DOCUMENTED_OVERSIZED_FUNCTIONS."
    )


# ── Doc reference ────────────────────────────────────────────


def test_architecture_audit_doc_exists():
    doc = REPO_ROOT / "tests" / "benchmark" / "PHASE_B_ARCHITECTURE_AUDIT.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    assert "muninn_tree.py" in text
    assert "boot" in text
    assert "646" in text  # the headline number


if __name__ == "__main__":
    modules, functions = _scan_engine_core()
    modules.sort(reverse=True)
    functions.sort(reverse=True)
    print("=" * 60)
    print("MODULE SIZES (top 5)")
    print("=" * 60)
    for n, name in modules[:5]:
        flag = ""
        if n > HARD_CAP_MODULE_LINES:
            flag = " [OVER HARD CAP]"
        elif n > 2500:
            flag = " [WARN]"
        print(f"  {n:>5}  {name}{flag}")
    print()
    print("=" * 60)
    print("FUNCTION SIZES (top 5)")
    print("=" * 60)
    for n, fname, name in functions[:5]:
        flag = ""
        if n > HARD_CAP_FUNCTION_LINES:
            flag = " [OVER HARD CAP]"
        elif n > 200:
            flag = " [WARN]"
        print(f"  {n:>4}  {fname}::{name}{flag}")
    print()
    print(f"Hard caps: module={HARD_CAP_MODULE_LINES}, function={HARD_CAP_FUNCTION_LINES}")
    print(f"Documented oversized: {len(DOCUMENTED_OVERSIZED_MODULES)} modules + "
          f"{len(DOCUMENTED_OVERSIZED_FUNCTIONS)} functions")
