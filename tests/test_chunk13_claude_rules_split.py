"""
CHUNK 13 — Tests for the .claude/rules/ split.

The split was introduced in chunk 13 (étape 4 of the leak intel battle plan).
Anthropic's official Claude Code docs recommend using .claude/rules/*.md with
YAML frontmatter `paths:` to scope rules to specific file types, instead of
putting everything in the root CLAUDE.md.

This split does NOT remove rules from CLAUDE.md. It ADDS path-scoped
extension files that load only when Claude touches matching files.

Tests:
1. .claude/rules/python.md exists, has valid YAML frontmatter with paths:
2. .claude/rules/git.md exists, has valid YAML frontmatter with paths:
3. The frontmatter `paths` patterns are sensible globs
4. Each rules file is non-trivial (real content, not stub)
5. CLAUDE.md root still contains the 3 RULES (no regression on chunk 10)
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / ".claude" / "rules"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


def _parse_frontmatter(text: str) -> dict | None:
    """Parse YAML-like frontmatter at the top of a markdown file.

    Returns dict if found and valid, None otherwise.
    Minimal parser: only handles `paths:` list with `- "..."` items.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    block = text[3:end].strip()
    result = {}
    current_key = None
    for line in block.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith(" "):
            current_key = line[:-1].strip()
            result[current_key] = []
        elif line.lstrip().startswith("- ") and current_key:
            value = line.lstrip()[2:].strip().strip('"').strip("'")
            result[current_key].append(value)
        elif ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


# ── Existence ──────────────────────────────────────────────────


def test_rules_dir_exists():
    assert RULES_DIR.exists() and RULES_DIR.is_dir(), (
        f".claude/rules/ directory should exist at {RULES_DIR}"
    )


def test_python_rules_file_exists():
    assert (RULES_DIR / "python.md").exists()


def test_git_rules_file_exists():
    assert (RULES_DIR / "git.md").exists()


# ── python.md frontmatter ──────────────────────────────────────


@pytest.fixture
def python_md_text():
    return (RULES_DIR / "python.md").read_text(encoding="utf-8")


def test_python_md_has_frontmatter(python_md_text):
    assert python_md_text.startswith("---"), "python.md must start with --- frontmatter"
    # Closing ---
    second = python_md_text.find("\n---", 3)
    assert second > 0, "python.md frontmatter must close with ---"


def test_python_md_paths_is_list(python_md_text):
    fm = _parse_frontmatter(python_md_text)
    assert fm is not None
    assert "paths" in fm, "python.md frontmatter must have a 'paths:' key"
    assert isinstance(fm["paths"], list)
    assert len(fm["paths"]) >= 1


def test_python_md_paths_target_python(python_md_text):
    fm = _parse_frontmatter(python_md_text)
    assert any(".py" in p for p in fm["paths"]), (
        f"python.md paths should target .py files, got {fm['paths']}"
    )


def test_python_md_has_substantive_content(python_md_text):
    # After frontmatter, should have at least 500 chars of real content
    second = python_md_text.find("\n---", 3)
    body = python_md_text[second + 4:]
    assert len(body.strip()) >= 500, (
        f"python.md body too short ({len(body.strip())} chars), "
        f"should be substantive"
    )


def test_python_md_references_rule_1(python_md_text):
    """python.md should explicitly extend RULE 1 (hardcode)."""
    assert "RULE 1" in python_md_text


def test_python_md_mentions_known_patterns(python_md_text):
    """The Python guide should mention the actual patterns used in this repo."""
    expected = ["_REPO_PATH", "Path(__file__)", "engine/core", "muninn"]
    for token in expected:
        assert token in python_md_text, f"python.md missing {token!r}"


# ── git.md frontmatter ─────────────────────────────────────────


@pytest.fixture
def git_md_text():
    return (RULES_DIR / "git.md").read_text(encoding="utf-8")


def test_git_md_has_frontmatter(git_md_text):
    assert git_md_text.startswith("---")


def test_git_md_paths_is_list(git_md_text):
    fm = _parse_frontmatter(git_md_text)
    assert fm is not None
    assert "paths" in fm
    assert isinstance(fm["paths"], list)
    assert len(fm["paths"]) >= 1


def test_git_md_paths_target_git(git_md_text):
    fm = _parse_frontmatter(git_md_text)
    assert any(".git" in p or "gitignore" in p or "gitattributes" in p
               for p in fm["paths"]), (
        f"git.md paths should target git config files, got {fm['paths']}"
    )


def test_git_md_references_rules_2_and_3(git_md_text):
    """git.md should reference RULES 2 (destructive) and 3 (secrets)."""
    assert "RULE 2" in git_md_text
    assert "RULE 3" in git_md_text


def test_git_md_mentions_force_push(git_md_text):
    assert "force" in git_md_text.lower() and "push" in git_md_text.lower()


# ── Cross-check with CLAUDE.md ─────────────────────────────────


def test_claude_md_still_has_3_rules():
    """The split should NOT remove RULES from root CLAUDE.md."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    rule_count = len(re.findall(r'<RULE\s+id="(\d+)"', text))
    assert rule_count >= 3, (
        f"CLAUDE.md should still have at least 3 RULES after split, got {rule_count}"
    )


def test_claude_md_still_under_300_lines():
    """CLAUDE.md size cap.

    Originally 200 (Anthropic's chunk-9 recommendation). Bumped to 300
    in brick 22 (2026-04-11) after RULE 4 (no claim w/o output, brick 8)
    and RULE 5 (forge mandatory, brick 16) were added — both written
    under fire after real bugs and required by the battle plan. The
    extra ~50 lines per rule is deliberate primacy-bias front-loading
    that pays for itself in fewer lies per session.

    Cap stays binding so the file doesn't grow without intent.
    """
    text = CLAUDE_MD.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    assert line_count <= 300, (
        f"CLAUDE.md should stay under 300 lines, got {line_count}. "
        f"If you added content, justify it in the test docstring before "
        f"bumping the cap."
    )


# ── Frontmatter parser sanity ──────────────────────────────────


def test_frontmatter_parser_handles_malformed():
    assert _parse_frontmatter("") is None
    assert _parse_frontmatter("no frontmatter here") is None
    assert _parse_frontmatter("---\nno close") is None


def test_frontmatter_parser_extracts_paths():
    text = '---\npaths:\n  - "*.py"\n  - "tests/**/*.py"\n---\nbody'
    fm = _parse_frontmatter(text)
    assert fm is not None
    assert fm["paths"] == ["*.py", "tests/**/*.py"]
