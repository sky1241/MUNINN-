"""H.2 — Wire `muninn-ui` console script.

Until H.2 ships, the 11 712 LOC of muninn/ui/* (23 modules: MainWindow,
tree_view, forest, cube_live, neuron_map, terminal, etc.) sit dormant.
`def main()` is already implemented in muninn/ui/main_window.py:578 with
HiDPI setup, OpenGL fallback (MUNINN_GL_SOFTWARE), and CLI scan-path arg.

H.2 adds the wiring so users can run `muninn-ui` after `pip install
'muninn-memory[ui]'`.

Contract :
  - pyproject.toml [project.scripts] declares `muninn-ui = "muninn.ui.main_window:main"`
  - muninn/ui/main_window.py exposes a callable `main()`
  - pyproject.toml [project.optional-dependencies] declares `ui = ["PyQt6>=6.10"]`
  - `python -m muninn.ui` works (via muninn/ui/__main__.py)
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _load_pyproject() -> dict:
    import tomllib
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_h2_console_script_in_pyproject() -> None:
    data = _load_pyproject()
    scripts = data["project"].get("scripts", {})
    assert scripts.get("muninn-ui") == "muninn.ui.main_window:main", (
        f"[project.scripts] muninn-ui must point at muninn.ui.main_window:main, "
        f"got {scripts.get('muninn-ui')!r}"
    )


def test_h2_main_callable_exists() -> None:
    """`muninn.ui.main_window:main` must be importable and callable."""
    import importlib
    mod = importlib.import_module("muninn.ui.main_window")
    func = getattr(mod, "main", None)
    assert callable(func), (
        f"muninn.ui.main_window.main must be callable, got {type(func)}"
    )


def test_h2_pyqt_extra_declared() -> None:
    data = _load_pyproject()
    extras = data["project"].get("optional-dependencies", {})
    ui_deps = extras.get("ui", [])
    assert any("pyqt6" in d.lower() for d in ui_deps), (
        f"[project.optional-dependencies] ui must include PyQt6, got {ui_deps}"
    )


def test_h2_dunder_main_present() -> None:
    """`python -m muninn.ui` must work via muninn/ui/__main__.py."""
    dunder = REPO_ROOT / "muninn" / "ui" / "__main__.py"
    assert dunder.exists(), (
        f"{dunder} must exist so `python -m muninn.ui` resolves to main()"
    )
    text = dunder.read_text(encoding="utf-8")
    assert "main_window" in text and "main" in text, (
        f"{dunder} should import + call main_window.main(). Got:\n{text}"
    )


def test_h2_all_extra_includes_ui() -> None:
    """The `all` extra should aggregate `ui` so `pip install muninn-memory[all]`
    actually installs PyQt6 too."""
    data = _load_pyproject()
    extras = data["project"].get("optional-dependencies", {})
    all_deps = extras.get("all", [])
    assert any("pyqt6" in d.lower() for d in all_deps), (
        f"The `all` extra must include PyQt6 (so `pip install ...[all]` is "
        f"a true superset). Got: {all_deps}"
    )
