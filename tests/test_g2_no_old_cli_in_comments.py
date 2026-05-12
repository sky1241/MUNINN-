"""G.2 — Doc drift régression sur la renomination `muninn` → `muninn-mem` (E.3).

Le sed E.3 (2026-05-12) a raté les commentaires Python, docstrings, et les
prints user-facing. Ce test verrouille la propreté.

Périmètre :
- engine/core/*.py
- muninn/*.py (excluant muninn/__pycache__)
- examples/*.py
- Les docs root (README, QUICKSTART, CHANGELOG) ne sont PAS dans le scope
  G.2 (historique CHANGELOG cite l'ancien nom intentionnellement).

Faux positifs autorisés :
- `python -m muninn …` — c'est l'invocation module Python valide, pas le CLI
- `muninn-mem …` — c'est le nouveau nom
- `muninn-mycel`, `muninn-ui`, `muninn-mcp` — autres binaires du projet
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Mots qui DOIVENT plus apparaître précédés de `muninn ` (sans suffixe -mem).
OLD_SUBCOMMANDS = [
    "init", "status", "doctor", "boot", "feed",
    "compress", "bootstrap", "prune", "verify",
]

# Pattern: literal "muninn " followed by one of the old subcommands,
# NOT preceded by `-mem`, `-mycel`, `-ui`, `-mcp` and NOT preceded by `-m `.
_BAD_PATTERN = re.compile(
    r"(?<!-mem)(?<!-mycel)(?<!-ui)(?<!-mcp)"  # not already renamed
    r"(?<!-m )"                                  # not python -m muninn
    r"\bmuninn (" + "|".join(OLD_SUBCOMMANDS) + r")\b"
)

SCAN_DIRS = ["engine/core", "muninn", "examples"]


def _scan() -> list[tuple[Path, int, str]]:
    """Return (file, line_num, line_content) for each bad match."""
    hits = []
    for sub in SCAN_DIRS:
        for py in (REPO_ROOT / sub).rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                lines = py.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, start=1):
                # Skip the test file itself
                if py.name == "test_g2_no_old_cli_in_comments.py":
                    continue
                if _BAD_PATTERN.search(line):
                    hits.append((py.relative_to(REPO_ROOT), i, line.strip()))
    return hits


def test_g2_no_old_muninn_subcommand_in_shipped_code() -> None:
    hits = _scan()
    if hits:
        formatted = "\n".join(f"  {p}:{ln}: {txt}" for p, ln, txt in hits)
        pytest.fail(
            f"Found {len(hits)} stale `muninn <subcommand>` references "
            f"in shipped code (should be `muninn-mem <subcommand>`):\n"
            f"{formatted}"
        )


def test_g2_archived_bug_hooks_marked_resolved() -> None:
    """The archived BUG_HOOKS_UNIVERSELS.md should have a 'RESOLVED en E.3' header."""
    archived = REPO_ROOT / "docs" / "archive" / "BUG_HOOKS_UNIVERSELS.md"
    if not archived.exists():
        pytest.skip(f"{archived} not present — skip (already cleaned up)")
    text = archived.read_text(encoding="utf-8")
    assert "RESOLVED" in text and "E.3" in text, (
        f"{archived} should declare RESOLVED en E.3 in its header"
    )
