"""
CHUNK MCP B.5 — `runbook_list_sections` + `runbook_get` MCP tools.

Expose CHANGELOG.md / WINTER_TREE.md / docs/BATTLE_PLAN_MASTER_MCP.md à
Claude pendant qu'il génère, scopés par sections (date / titre / numéro)
plutôt qu'en chargeant les fichiers entiers (~150KB+).

Contracts:
  - document ∈ {"changelog", "winter_tree", "battle_plan"} (whitelist)
  - section_id regex `^[a-z0-9][a-z0-9_-]{0,79}$`
  - Cap 40K chars sur runbook_get.content
  - Read-only strict (mtime + content snapshot)
  - Missing file → error tag, pas raise

Tests : 12 behavioural.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))

mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


SAMPLE_CHANGELOG = """# CHANGELOG

Header preamble.

## 2026-05-11 (soir) — Phase B livré

Lots of content here.

- bullet 1
- bullet 2

## 2026-05-10 (matin) — BUG-104 fix

Earlier content.

- decay
- spill-to-tree

## 2026-05-09 — forge bump

Even older.
"""

SAMPLE_WINTER_TREE = """# WINTER TREE — MUNINN snapshot

> Header description.

## Architecture

Architecture text.

## Mycelium — Le Champignon Vivant

Mycelium text.

## Hooks Claude Code

9 hooks installed.
"""

SAMPLE_BATTLE_PLAN = """# BATTLE PLAN MASTER

> Document de référence.

## 0. POURQUOI CE PLAN

Body of section 0.

## 1. CONTEXTE

Body of section 1.

## 2. ROADMAP

Body of section 2.
"""


def _make_runbook_repo(tmp_path):
    """Create a tmp repo with the 3 runbook files in canonical locations."""
    repo = tmp_path / "runbook_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    (repo / "CHANGELOG.md").write_text(SAMPLE_CHANGELOG, encoding="utf-8")
    (repo / "WINTER_TREE.md").write_text(SAMPLE_WINTER_TREE, encoding="utf-8")
    docs = repo / "docs"
    docs.mkdir()
    (docs / "BATTLE_PLAN_MASTER_MCP.md").write_text(
        SAMPLE_BATTLE_PLAN, encoding="utf-8"
    )
    return repo


# ── Registration ─────────────────────────────────────────────


def test_two_tools_registered():
    import asyncio
    from muninn.mcp import server
    app = server.create_server()
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    for required in ("runbook_list_sections", "runbook_get"):
        assert required in names, f"{required!r} missing. Got: {sorted(names)}"


# ── list_sections per document ───────────────────────────────


def test_list_sections_changelog(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_list_sections_impl(document="changelog", repo_path=str(repo))
    assert r["document"] == "changelog"
    assert r["count"] == 3
    ids = [s["id"] for s in r["sections"]]
    assert any("2026-05-11" in i for i in ids)


def test_list_sections_winter_tree(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_list_sections_impl(document="winter_tree", repo_path=str(repo))
    assert r["count"] == 3
    ids = [s["id"] for s in r["sections"]]
    assert "architecture" in ids


def test_list_sections_battle_plan(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_list_sections_impl(document="battle_plan", repo_path=str(repo))
    assert r["count"] == 3
    ids = [s["id"] for s in r["sections"]]
    # Numbered → "0", "1", "2"
    assert "0" in ids
    assert "2" in ids


# ── runbook_get per document ─────────────────────────────────


def test_get_changelog_section_returns_content(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    # First list, then get
    listing = server._runbook_list_sections_impl(document="changelog",
                                                   repo_path=str(repo))
    section_id = listing["sections"][0]["id"]
    r = server._runbook_get_impl(
        document="changelog", section_id=section_id, repo_path=str(repo),
    )
    assert r["document"] == "changelog"
    assert r["section_id"] == section_id
    assert "Phase B livré" in r["title"]
    assert "Lots of content" in r["content"]


def test_get_winter_tree_section_returns_content(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_get_impl(
        document="winter_tree", section_id="architecture", repo_path=str(repo),
    )
    assert "Architecture text" in r["content"]


def test_get_battle_plan_section_zero(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_get_impl(
        document="battle_plan", section_id="0", repo_path=str(repo),
    )
    assert "Body of section 0" in r["content"]


# ── Error handling ───────────────────────────────────────────


def test_get_missing_section_returns_friendly_error(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    r = server._runbook_get_impl(
        document="changelog", section_id="zzz-nonexistent",
        repo_path=str(repo),
    )
    assert "error" in r
    assert "available_sections" in r
    assert len(r["available_sections"]) == 3


def test_invalid_document_raises(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    for bad_doc in ("secrets", "../../etc/passwd", "BUGS", "RANDOM"):
        with pytest.raises(ValueError):
            server._runbook_list_sections_impl(document=bad_doc, repo_path=str(repo))


def test_invalid_section_id_raises(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    for bad in ("../../etc", "BAD/path", "UPPERCASE"):
        with pytest.raises(ValueError):
            server._runbook_get_impl(
                document="changelog", section_id=bad, repo_path=str(repo),
            )


def test_missing_file_returns_error_not_crash(tmp_path):
    from muninn.mcp import server
    # Empty repo, no CHANGELOG
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    r = server._runbook_list_sections_impl(document="changelog", repo_path=str(repo))
    assert r.get("count", 0) == 0 or "error" in r


# ── Read-only contract ──────────────────────────────────────


def test_files_not_modified(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    files = [repo / "CHANGELOG.md", repo / "WINTER_TREE.md",
             repo / "docs" / "BATTLE_PLAN_MASTER_MCP.md"]
    before = [(f.stat().st_mtime, f.stat().st_size, f.read_text(encoding="utf-8"))
              for f in files]
    time.sleep(0.01)

    for doc in ("changelog", "winter_tree", "battle_plan"):
        server._runbook_list_sections_impl(document=doc, repo_path=str(repo))
    server._runbook_get_impl(
        document="winter_tree", section_id="architecture", repo_path=str(repo),
    )

    for (mt, sz, ct), f in zip(before, files):
        assert f.stat().st_mtime == mt
        assert f.stat().st_size == sz
        assert f.read_text(encoding="utf-8") == ct


# ── JSON serializability ────────────────────────────────────


def test_all_outputs_json_serializable(tmp_path):
    from muninn.mcp import server
    repo = _make_runbook_repo(tmp_path)
    for doc in ("changelog", "winter_tree", "battle_plan"):
        json.dumps(server._runbook_list_sections_impl(document=doc,
                                                       repo_path=str(repo)))
    json.dumps(server._runbook_get_impl(
        document="winter_tree", section_id="architecture", repo_path=str(repo),
    ))


# ── Real-world smoke ─────────────────────────────────────────


def test_real_changelog_parses():
    from muninn.mcp import server
    r = server._runbook_list_sections_impl(document="changelog",
                                             repo_path=str(REPO_ROOT))
    assert r["count"] >= 1
