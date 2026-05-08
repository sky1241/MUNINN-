"""CHUNK D10 — drift audit: muninn/_engine.py vs engine/core/muninn.py.

The two files share 23 top-level functions but their bodies have drifted
since BUG-091. Full shim reduction is deferred (see docs/D10_DRIFT_AUDIT.md
for the migration plan); this file just locks in the current invariants
so future drift can't grow silently.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D10
"""
import ast
import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
ENGINE_CORE_MUNINN = REPO / "engine" / "core" / "muninn.py"
MUNINN_ENGINE = REPO / "muninn" / "_engine.py"
DRIFT_DOC = REPO / "docs" / "D10_DRIFT_AUDIT.md"


def _function_names(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    return {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _class_names(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def test_drift_doc_exists():
    assert DRIFT_DOC.exists(), (
        "Missing docs/D10_DRIFT_AUDIT.md — see CHUNK D10"
    )


def test_function_surface_parity():
    """Both files must expose the SAME set of top-level functions."""
    e_funcs = _function_names(ENGINE_CORE_MUNINN)
    m_funcs = _function_names(MUNINN_ENGINE)
    only_engine = e_funcs - m_funcs
    only_muninn = m_funcs - e_funcs
    assert not only_engine, (
        f"Functions in engine/core/muninn.py missing from muninn/_engine.py:"
        f" {sorted(only_engine)}"
    )
    assert not only_muninn, (
        f"Functions in muninn/_engine.py missing from engine/core/muninn.py:"
        f" {sorted(only_muninn)}"
    )


def test_class_surface_parity():
    e_cls = _class_names(ENGINE_CORE_MUNINN)
    m_cls = _class_names(MUNINN_ENGINE)
    assert e_cls == m_cls, (
        f"Class set drift: engine_only={e_cls - m_cls} "
        f"muninn_only={m_cls - e_cls}"
    )


def test_drift_size_cap():
    """The total `diff` between the two files must not exceed a cap.
    Currently ~4166. Capped slightly above to allow CHUNK fixes that
    reach engine/core/muninn.py before the shim reduction lands. If a
    future PR pushes this past the cap, either reduce muninn/_engine.py
    to a shim (preferred) or update the cap with justification."""
    import subprocess
    proc = subprocess.run(
        ["diff", str(ENGINE_CORE_MUNINN), str(MUNINN_ENGINE)],
        capture_output=True, text=True
    )
    diff_lines = len(proc.stdout.splitlines())
    cap = 5000  # generous headroom above the audit-time 4166
    assert diff_lines <= cap, (
        f"muninn/_engine.py drift exceeded {cap} diff lines: {diff_lines}.\n"
        "Either reduce _engine.py to a shim (see docs/D10_DRIFT_AUDIT.md) "
        "or update this cap with a comment explaining the increase."
    )


def test_engine_core_uses_importlib_metadata_for_version():
    """CHUNK C8 wired importlib.metadata for engine/core/muninn.py."""
    src = ENGINE_CORE_MUNINN.read_text()
    assert "importlib.metadata" in src, (
        "engine/core/muninn.py should resolve __version__ via "
        "importlib.metadata (CHUNK C8)"
    )


def test_muninn_engine_version_at_least_pyproject():
    """muninn/_engine.py __version__ must not be the stale 0.9.1.

    Either it tracks pyproject.toml dynamically (ideal, like
    engine/core/muninn.py) or it has been manually bumped to >= 0.9.2.
    """
    src = MUNINN_ENGINE.read_text()
    # Find __version__ assignment(s)
    matches = re.findall(r'__version__\s*=\s*["\']([^"\']+)["\']', src)
    if not matches:
        pytest.skip("no __version__ literal in muninn/_engine.py")
    for v in matches:
        # Refuse the known-stale value
        assert v != "0.9.1", (
            f"muninn/_engine.py still has stale version {v!r} — "
            "see CHUNK C8 / D10 drift audit"
        )
