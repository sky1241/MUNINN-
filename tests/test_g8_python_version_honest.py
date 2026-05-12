"""G.8 — pyproject.toml must not claim untested Python versions.

The pyproject classifiers had `Python :: 3.10/3.11/3.12/3.13` but the CI
matrix and local pyenv only test 3.13. Claiming 3.10-3.12 support
without testing it is dishonest (RULE 4 spirit).

This test locks the file to claim only what we test.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_g8_requires_python_matches_classifiers() -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    # 1. requires-python must be >=3.13 (we don't test older)
    req_match = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    assert req_match, "requires-python missing"
    assert ">=3.13" in req_match.group(1), (
        f"requires-python must be >=3.13 (only version tested in CI); "
        f"got '{req_match.group(1)}'"
    )
    # 2. classifiers must NOT advertise untested versions
    for untested in ("Python :: 3.10", "Python :: 3.11", "Python :: 3.12"):
        assert untested not in text, (
            f"pyproject claims '{untested}' but CI doesn't test it. "
            "Either add the version to CI matrix or remove the classifier."
        )
    # 3. Must still advertise 3.13 (we DO test it)
    assert "Python :: 3.13" in text, "Missing Python :: 3.13 classifier"
