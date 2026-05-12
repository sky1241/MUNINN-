"""H.2b — Reactivate UI tests in CI.

Before H.2b, .github/workflows/ci.yml passed `--ignore-glob='tests/test_ui_*.py'`
to pytest, leaving 173 UI tests permanently grey. With H.2 wiring the
`muninn-ui` console script, these tests are now meaningful again.

This test pins the ci.yml configuration: no UI ignore + QT offscreen env
+ PyQt6 + pytest-qt installed.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CONSTRAINTS = REPO_ROOT / "constraints.txt"


def test_h2b_ci_does_not_ignore_ui_tests() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "--ignore-glob='tests/test_ui_*.py'" not in text, (
        "ci.yml still ignores UI tests. H.2b should have removed "
        "--ignore-glob='tests/test_ui_*.py' from the pytest step."
    )


def test_h2b_ci_sets_qt_offscreen() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "QT_QPA_PLATFORM" in text and "offscreen" in text, (
        "ci.yml must set QT_QPA_PLATFORM=offscreen so headless runners "
        "can execute the UI tests."
    )


def test_h2b_pyqt6_in_constraints() -> None:
    text = CONSTRAINTS.read_text(encoding="utf-8") if CONSTRAINTS.exists() else ""
    assert "PyQt6" in text or "pyqt6" in text.lower(), (
        "constraints.txt must pin PyQt6 (UI runtime)."
    )


def test_h2b_pytest_qt_in_constraints() -> None:
    text = CONSTRAINTS.read_text(encoding="utf-8") if CONSTRAINTS.exists() else ""
    assert "pytest-qt" in text.lower(), (
        "constraints.txt must pin pytest-qt (provides qtbot fixture)."
    )
