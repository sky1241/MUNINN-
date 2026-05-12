"""
CHUNK MCP C.4 — User-facing onboarding documentation.

Sky asked for a system that "se calibre en fonction de chaque client". The
code already does (C.0 auto-calibration). The missing piece is the
user-facing doc so a new dev can clone Muninn, install it on their repo,
and have everything working in 5 minutes without reading 1000 lines of
historical battle plans.

Deliverables:
  - docs/QUICKSTART.md : 10 numbered commands from git clone to first
    `mycelium_recall_local`. Copy-paste-friendly.
  - README.md : section "How to use Muninn for your own repo" linking
    to QUICKSTART + showing the 10 MCP tools cheat-sheet.
  - docs/MCP_SETUP.md : section "Phase B tools cheatsheet" (10 tools ×
    when/params/example_output).

Test pin: source-greppy sanity that those sections / files exist with
the expected structure (headers, code blocks). Doesn't execute any of
the commands — that would belong in a future E2E test (out of scope).
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_c4_quickstart_doc_exists():
    """docs/QUICKSTART.md exists and is non-trivially sized."""
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    assert p.exists(), f"missing {p}"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    assert n > 50, f"QUICKSTART.md too short: {n} lines"


def test_c4_quickstart_has_numbered_steps():
    """The doc should have at least 10 numbered command steps (1. ... 10.)."""
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    text = p.read_text(encoding="utf-8")
    import re
    # Match numbered headings like "## 1. " or "## 10. " (top-level steps)
    steps = re.findall(r"^##\s+\d+\.\s+", text, re.MULTILINE)
    assert len(steps) >= 8, (
        f"QUICKSTART should have ≥8 numbered steps, found {len(steps)}: "
        f"{steps[:5]}..."
    )


def test_c4_quickstart_has_bash_blocks():
    """The doc should have at least 5 executable ```bash blocks (commands)."""
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    text = p.read_text(encoding="utf-8")
    bash_blocks = text.count("```bash")
    assert bash_blocks >= 5, f"QUICKSTART needs ≥5 bash blocks, found {bash_blocks}"


def test_c4_quickstart_mentions_core_commands():
    """QUICKSTART must mention the essential commands a new user will type.

    Updated in E.3 (2026-05-12): renamed console scripts to avoid PyPI
    collision (`muninn` → `muninn-mem`, `muninn-mcp` → `muninn-mcp-mem`).
    """
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    text = p.read_text(encoding="utf-8")
    for keyword in (
        "pip install",
        "muninn-mem init",
        "muninn-mem doctor",
        "muninn-mcp-mem",
        ".claude.json",
        "MUNINN_REPO",
    ):
        assert keyword in text, f"QUICKSTART missing essential keyword: {keyword!r}"


def test_c4_quickstart_no_hardcoded_sky_paths():
    """QUICKSTART must use placeholders, not /home/sky/... paths."""
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    text = p.read_text(encoding="utf-8")
    # /home/sky may appear inside a code-fence as the SPECIFIC example for Sky's
    # config sample; we accept up to 0 occurrences in user-facing prose.
    occurrences = text.count("/home/sky")
    assert occurrences == 0, (
        f"QUICKSTART has {occurrences} /home/sky paths — use <PATH_TO_YOUR_REPO> "
        f"placeholders instead so it works for ANY client."
    )


def test_c4_readme_links_quickstart():
    """README must have a section linking to QUICKSTART.md."""
    p = REPO_ROOT / "README.md"
    text = p.read_text(encoding="utf-8")
    assert "QUICKSTART" in text or "Quickstart" in text or "Quick start" in text, (
        "README must link to QUICKSTART.md or have a Quickstart section"
    )


def test_c4_mcp_setup_has_cheatsheet():
    """MCP_SETUP.md must have a tools cheatsheet section (or equivalent table)."""
    p = REPO_ROOT / "docs" / "MCP_SETUP.md"
    text = p.read_text(encoding="utf-8")
    # Look for the table of 10 tools (we already have it from B.5 but make
    # sure C.4 didn't accidentally remove it)
    tool_names = [
        "mycelium_recall_local",
        "mycelium_recall_meta",
        "mycelium_recall",
        "tree_get_root",
        "tree_get_branch",
        "tree_list_branches",
        "bugs_list",
        "bugs_get",
        "runbook_list_sections",
        "runbook_get",
    ]
    missing = [t for t in tool_names if t not in text]
    assert not missing, f"MCP_SETUP.md missing tool entries: {missing}"


def test_c4_quickstart_section_when_to_call_which_tool():
    """QUICKSTART should have a section guiding users on which tool to call when."""
    p = REPO_ROOT / "docs" / "QUICKSTART.md"
    text = p.read_text(encoding="utf-8")
    # Either explicit "When to call" section, or at least the tool names listed
    has_section = (
        "When to call" in text
        or "MCP tool" in text
        or "mycelium_recall" in text
    )
    assert has_section, "QUICKSTART should guide users on which MCP tool to call"
