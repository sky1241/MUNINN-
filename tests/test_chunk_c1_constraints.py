"""CHUNK C1 — constraints.txt for reproducible builds.

pyproject.toml used very loose ranges (`tiktoken>=0.5`, `anthropic>=0.20`)
which let builds drift across environments. constraints.txt provides a
single tested set of versions that CI / fresh installs can pin to via
`pip install -c constraints.txt -e '.[all]'`.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C1
"""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
CONSTRAINTS = REPO / "constraints.txt"


def test_constraints_file_exists():
    assert CONSTRAINTS.exists(), "constraints.txt missing — see CHUNK C1"


def test_constraints_pins_tiktoken_exactly():
    """tiktoken must be pinned with == (no >= ranges in the lock)."""
    src = CONSTRAINTS.read_text()
    m = re.search(r"^tiktoken\s*==\s*(\S+)", src, re.MULTILINE)
    assert m, "tiktoken==<version> line missing in constraints.txt"


def test_constraints_pins_anthropic_exactly():
    """anthropic must be pinned with ==."""
    src = CONSTRAINTS.read_text()
    m = re.search(r"^anthropic\s*==\s*(\S+)", src, re.MULTILINE)
    assert m, "anthropic==<version> line missing in constraints.txt"


def test_constraints_no_loose_ranges():
    """No `>=` in constraints.txt — that defeats the purpose."""
    src = CONSTRAINTS.read_text()
    # Strip comments
    code_lines = [
        ln.strip() for ln in src.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    for ln in code_lines:
        assert ">=" not in ln, (
            f"constraints.txt has a loose range: {ln!r} — "
            "use == for true reproducibility"
        )
