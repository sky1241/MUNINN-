"""CHUNK C8 — single version source of truth.

Pre-fix:
  pyproject.toml         -> "0.9.2"
  muninn/__init__.py     -> "0.9.2"
  engine/core/muninn.py  -> "0.9.1"   ← drift

Three places, two values. The drift was introduced by BUG-091 dual-tree
refactor and went unnoticed.

Fix: pyproject.toml is the single source of truth. Both muninn/__init__.py
and engine/core/muninn.py read the version dynamically from
importlib.metadata.version("muninn"), with a hardcoded fallback for the
case the package is run from a checkout without `pip install -e .`.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C8
"""
import re
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _read_pyproject_version():
    text = (REPO / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "could not find version in pyproject.toml"
    return m.group(1)


def test_versions_in_sync():
    """muninn.__version__ matches pyproject.toml version."""
    expected = _read_pyproject_version()
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import muninn
    assert muninn.__version__ == expected, (
        f"muninn.__version__ = {muninn.__version__!r} but "
        f"pyproject.toml version = {expected!r}"
    )


def test_engine_core_version_in_sync():
    """engine/core/muninn.py exposes the same __version__ as pyproject."""
    expected = _read_pyproject_version()
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    # Either bare-loaded or already in sys.modules
    if "muninn" in sys.modules and Path(sys.modules["muninn"].__file__).is_relative_to(engine_core):
        engine_muninn = sys.modules["muninn"]
    else:
        # Read source directly to avoid module-name collision
        src = (engine_core / "muninn.py").read_text()
        # Find the fallback hardcoded version (after an `__version__ =`
        # assignment that is followed by a string literal). The dynamic
        # importlib.metadata path returns whatever pyproject says, so the
        # only static value worth checking is the fallback literal.
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', src)
        assert m, "no __version__ found in engine/core/muninn.py"
        engine_muninn_version = m.group(1)

        # Static check is enough; the dynamic check would require loading
        # a 2000-line module that has many side effects.
        assert engine_muninn_version == expected, (
            f"engine/core/muninn.py __version__ = {engine_muninn_version!r} "
            f"but pyproject.toml = {expected!r}"
        )
        return

    assert engine_muninn.__version__ == expected


def test_no_hardcoded_version_string_in_engine_core():
    """The literal "0.9.1" must not appear anywhere in engine/core/muninn.py
    (was the stale value pre-fix). We do not forbid the current version
    literal because the importlib.metadata fallback may keep it as a
    last-resort default."""
    src = (REPO / "engine" / "core" / "muninn.py").read_text()
    assert '"0.9.1"' not in src, (
        "stale version literal '0.9.1' still present in engine/core/muninn.py"
    )
