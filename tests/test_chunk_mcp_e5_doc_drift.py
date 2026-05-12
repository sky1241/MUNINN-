"""
CHUNK MCP E.5 — Doc drift regression tests.

Pre-E.5 audit found 4 stale claims in user-facing docs that would mislead
fresh users :
- README mentioned "2356 tests" 5 times (actual ~2561)
- README had dead link to docs/BATTLE_PLAN_2026-05-09.md (file doesn't exist)
- QUICKSTART claimed `muninn --version` would print "muninn 0.9.x" (we're at 1.0.x)
- CLAUDE.md said "Hooks installes: 9" while .claude/hooks/ has 10 .py files

E.5 fixed all 4. These tests pin the corrections so any future drift
surfaces in CI instead of in a user's frustration.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
QUICKSTART = REPO_ROOT / "docs" / "QUICKSTART.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def test_e5_readme_no_stale_test_count_2356():
    """README must not advertise the old '2356 tests' count.

    That number was correct ~2026-04-30 but we're now at ~2561. Any
    re-introduction (e.g. via a copy-paste of an old example) should
    fail this test.
    """
    text = README.read_text(encoding="utf-8")
    assert "2356" not in text, (
        "README mentions stale test count '2356'. Update to current count "
        "(check `pytest --collect-only`) or use a moving phrasing like "
        "'2500+ tests'."
    )


def test_e5_readme_no_dead_battle_plan_link():
    """README must not reference the never-created BATTLE_PLAN_2026-05-09.md."""
    text = README.read_text(encoding="utf-8")
    assert "BATTLE_PLAN_2026-05-09" not in text, (
        "README references docs/BATTLE_PLAN_2026-05-09.md which does not exist. "
        "Use docs/BATTLE_PLAN_MASTER_MCP.md (the active roadmap) instead."
    )


def test_e5_quickstart_version_reference_current():
    """QUICKSTART must not claim `muninn --version` returns the obsolete 0.9.x."""
    text = QUICKSTART.read_text(encoding="utf-8")
    assert "0.9.x" not in text, (
        "QUICKSTART mentions stale version 0.9.x. Update to 1.0.x or use a "
        "version-agnostic phrasing like 'should print muninn <version>'."
    )


def test_e5_claude_md_hook_count_matches_reality():
    """CLAUDE.md's `Hooks installes: **N**` must match actual .claude/hooks/*.py count."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    m = re.search(r"Hooks installes:\s*\*\*(\d+)", text)
    assert m is not None, "CLAUDE.md should declare a hook count in 'Hooks installes: **N**' format"
    declared = int(m.group(1))
    actual = len(list(HOOKS_DIR.glob("*.py")))
    assert declared == actual, (
        f"CLAUDE.md declares Hooks installes: {declared} but .claude/hooks/ "
        f"has {actual} Python files. Update CLAUDE.md or remove obsolete hooks."
    )


def test_e5_readme_links_resolve():
    """All `[text](docs/...md)` and `[text](path/...)` in README must point at existing files."""
    text = README.read_text(encoding="utf-8")
    # Capture markdown links to local paths (no http(s)://)
    pattern = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)]+)\)")
    broken = []
    for match in pattern.finditer(text):
        link = match.group(1).split("#")[0]  # strip fragment
        if not link:
            continue
        target = REPO_ROOT / link
        if not target.exists():
            broken.append(link)
    assert not broken, (
        f"README has {len(broken)} broken local link(s): {broken[:5]}"
        + ("…" if len(broken) > 5 else "")
    )


def test_e5_quickstart_links_resolve():
    """All local markdown links in QUICKSTART must point at existing files.

    QUICKSTART.md lives in docs/, so a bare link like `MCP_SETUP.md`
    resolves to `docs/MCP_SETUP.md`. Links starting with `../` resolve
    relative to docs/ (so `../examples` → `examples/`).
    """
    text = QUICKSTART.read_text(encoding="utf-8")
    pattern = re.compile(r"\[[^\]]+\]\((?!https?://|#)([^)]+)\)")
    broken = []
    for match in pattern.finditer(text):
        link = match.group(1).split("#")[0]
        if not link:
            continue
        # All relative links resolve from QUICKSTART's directory (docs/)
        target = (QUICKSTART.parent / link).resolve()
        if not target.exists():
            broken.append(link)
    assert not broken, (
        f"QUICKSTART has {len(broken)} broken local link(s): {broken[:5]}"
    )
