"""BRICK 19 — pin the dead code audit on engine/core/.

Runs the AST-based dead code scan and asserts the count of in-tree
candidates is exactly the documented set. If a new public function
is added that's not called from inside engine/core/ AND not in the
known-tested set, this test fails and forces a manual review:
either delete the function or add it to the documented set.

See `tests/benchmark/PHASE_B_DEAD_CODE_AUDIT.md` for the full report.
"""
import ast
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


# These 11 functions are public APIs of engine/core/ that are tested
# in tests/ but not called from inside engine/core/ itself. They are
# the expected "in-tree dead candidates" — adding to this set requires
# either a justification or a deletion.
DOCUMENTED_IN_TREE_DEAD_CANDIDATES = frozenset({
    "dedup_paragraphs",
    "similar",
    "analyze_findings",
    "validate_against_code",
    "validate_against_code_with_mn",
    "validate_all",
    "estimate_cost",
    "scan_batch",
    "influence_minimization",
    "to_markdown",
    "sync_metrics",
})


def _scan_engine_core_dead_code():
    """AST scan of engine/core/. Returns set of in-tree dead candidates."""
    defs_by_file = defaultdict(set)
    all_defs = set()
    called_names = set()
    exported_names = set()
    class_methods = set()
    imported_names = set()

    for py_file in ENGINE_CORE.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except SyntaxError:
            continue

        # Imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in (node.names or []):
                    imported_names.add(alias.name)
                    if alias.asname:
                        imported_names.add(alias.asname)
            elif isinstance(node, ast.Import):
                for alias in (node.names or []):
                    imported_names.add(alias.name)

        # __all__
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant):
                                    exported_names.add(elt.value)

        # Top-level public functions
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                defs_by_file[str(py_file)].add(node.name)
                all_defs.add(node.name)

        # Class methods
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        class_methods.add(item.name)

        # Calls + references
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called_names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called_names.add(func.attr)
            elif isinstance(node, ast.Attribute):
                called_names.add(node.attr)
            elif isinstance(node, ast.Name):
                if node.id in all_defs:
                    called_names.add(node.id)

    entry_points = {"main", "cli_run"}
    dead = set()
    for fpath, fns in defs_by_file.items():
        for fn in fns:
            if fn in entry_points:
                continue
            if fn in exported_names:
                continue
            if fn in class_methods:
                continue
            if "hook" in fn:
                continue
            if fn in imported_names:
                continue
            if fn not in called_names:
                dead.add(fn)
    return dead


# ── The actual contract ─────────────────────────────────────


def test_dead_code_set_matches_documented():
    """The in-tree dead candidates must match the documented set exactly.

    If this test fails:
      - A NEW dead function exists -> either delete it or add it to
        DOCUMENTED_IN_TREE_DEAD_CANDIDATES with a justification
      - A documented function became referenced -> remove from set
    """
    actual = _scan_engine_core_dead_code()

    new_dead = actual - DOCUMENTED_IN_TREE_DEAD_CANDIDATES
    no_longer_dead = DOCUMENTED_IN_TREE_DEAD_CANDIDATES - actual

    msg_parts = []
    if new_dead:
        msg_parts.append(
            f"NEW dead candidates: {sorted(new_dead)}\n"
            f"  -> Either delete these functions or add them to "
            f"DOCUMENTED_IN_TREE_DEAD_CANDIDATES with a comment "
            f"explaining why they're public API kept for external use."
        )
    if no_longer_dead:
        msg_parts.append(
            f"NO LONGER dead (now referenced): {sorted(no_longer_dead)}\n"
            f"  -> Remove these from DOCUMENTED_IN_TREE_DEAD_CANDIDATES."
        )

    assert not msg_parts, "\n\n".join(msg_parts)


def test_documented_dead_candidates_are_tested():
    """Every entry in DOCUMENTED_IN_TREE_DEAD_CANDIDATES must be referenced
    from at least one test file under tests/. If not, it's truly dead and
    should be deleted, not documented as 'kept for external use'."""
    test_files = list((REPO_ROOT / "tests").rglob("*.py"))
    test_text = ""
    for tf in test_files:
        if "__pycache__" in str(tf):
            continue
        try:
            test_text += tf.read_text(encoding="utf-8", errors="replace") + "\n"
        except OSError:
            continue

    untested = []
    for fn in DOCUMENTED_IN_TREE_DEAD_CANDIDATES:
        if fn not in test_text:
            untested.append(fn)

    assert not untested, (
        f"DOCUMENTED dead candidates not referenced in any test: {untested}\n"
        f"Either add tests for them, delete them, or remove from the "
        f"documented set with a clear note."
    )


def test_dead_code_audit_doc_exists():
    """The benchmark / audit doc must exist."""
    doc = REPO_ROOT / "tests" / "benchmark" / "PHASE_B_DEAD_CODE_AUDIT.md"
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    # Doc must contain the headline numbers
    assert "11 candidates" in text or "11 in-tree" in text
    assert "0 truly dead" in text.lower() or "no dead" in text.lower() or "0 truly dead" in text


if __name__ == "__main__":
    actual = _scan_engine_core_dead_code()
    print(f"In-tree dead candidates: {len(actual)}")
    for fn in sorted(actual):
        in_doc = "OK" if fn in DOCUMENTED_IN_TREE_DEAD_CANDIDATES else "NEW!"
        print(f"  [{in_doc}] {fn}")
    diff_new = actual - DOCUMENTED_IN_TREE_DEAD_CANDIDATES
    diff_old = DOCUMENTED_IN_TREE_DEAD_CANDIDATES - actual
    if diff_new:
        print(f"\nNEW (not documented): {sorted(diff_new)}")
    if diff_old:
        print(f"\nGONE (no longer dead): {sorted(diff_old)}")
    if not diff_new and not diff_old:
        print("\nAUDIT CLEAN ✓")
