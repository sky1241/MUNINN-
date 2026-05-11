"""
CHUNK MCP B.4 — `bugs_list` + `bugs_get` (read-only BUGS.md MCP tools).

Expose le BUGS.md du repo à Claude pendant qu'il génère sans qu'il ait
à charger le fichier complet (700+ lignes, ~25 bugs).

Contracts:
  - bugs_list(repo_path, status_filter, limit) → headers only (id, status, title)
  - bugs_get(bug_id, repo_path) → bug complet parsé en sections
  - Read-only strict (mtime + content snapshot)
  - bug_id validé par regex `^BUG-\\d{3,4}$` (anti path-traversal)
  - BUGS.md absent → empty results, pas raise

10 tests behaviouraux.
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


SAMPLE_BUGS_MD = """# BUGS — Test Repo

> Header text to ignore.

<!-- TEMPLATE
## BUG-XXX: template
- **Status**: OPEN / FIXED / WONTFIX
-->

## Status

Synthesis header to ignore.

### BUG-201: open bug example
- **Status**: OPEN
- **Symptom**: it happens
- **Root cause**: bad code
- **Fix**: TBD
- **Test**: pending
- **Regression**: none

### BUG-202: fixed bug example
- **Status**: FIXED
- **Symptom**: it used to happen
- **Root cause**: missing guard
- **Fix**: added check (commit abc123)
- **Test**: tests/test_x.py::test_y
- **Regression**: none

### BUG-203: wontfix example
- **Status**: WONTFIX
- **Symptom**: edge case nobody hits
- **Root cause**: deep refactor needed
- **Fix**: not planned
- **Test**: N/A
- **Regression**: none
"""


def _make_bugs_repo(tmp_path):
    repo = tmp_path / "bugs_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    (repo / "BUGS.md").write_text(SAMPLE_BUGS_MD, encoding="utf-8")
    return repo


# ── Registration ─────────────────────────────────────────────


def test_two_tools_registered():
    import asyncio
    from muninn.mcp import server
    app = server.create_server()
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    for required in ("bugs_list", "bugs_get"):
        assert required in names, f"{required!r} missing. Got: {sorted(names)}"


# ── bugs_list ────────────────────────────────────────────────


def test_bugs_list_returns_all_by_default(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    r = server._bugs_list_impl(repo_path=str(repo))
    assert isinstance(r, dict)
    assert r["count"] == 3
    ids = [b["id"] for b in r["bugs"]]
    assert ids == ["BUG-201", "BUG-202", "BUG-203"]


def test_bugs_list_filter_by_open(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    r = server._bugs_list_impl(repo_path=str(repo), status_filter="OPEN")
    assert r["count"] == 1
    assert r["bugs"][0]["id"] == "BUG-201"
    assert r["bugs"][0]["status"] == "OPEN"


def test_bugs_list_limit_respected(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    r = server._bugs_list_impl(repo_path=str(repo), limit=2)
    assert len(r["bugs"]) == 2
    assert r.get("truncated") is True or r.get("total", r["count"]) >= 3


# ── bugs_get ────────────────────────────────────────────────


def test_bugs_get_valid_id_returns_sections(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    r = server._bugs_get_impl(bug_id="BUG-202", repo_path=str(repo))
    assert r.get("id") == "BUG-202"
    assert r.get("status") == "FIXED"
    assert "missing guard" in r.get("content", "")
    sections = r.get("sections", {})
    assert "Symptom" in sections
    assert "Fix" in sections


def test_bugs_get_missing_id_returns_friendly_error(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    r = server._bugs_get_impl(bug_id="BUG-999", repo_path=str(repo))
    assert "error" in r
    assert r.get("bug_id") == "BUG-999"
    assert r.get("available_count", 0) == 3


def test_bugs_get_rejects_invalid_format(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    for bad_id in ("../../etc/passwd", "BUG-X", "random", "bug-001"):
        with pytest.raises(ValueError):
            server._bugs_get_impl(bug_id=bad_id, repo_path=str(repo))


# ── Graceful degradation ─────────────────────────────────────


def test_bugs_md_missing_returns_empty_not_crash(tmp_path):
    from muninn.mcp import server
    repo = tmp_path / "no_bugs_repo"
    repo.mkdir()
    # NO BUGS.md created
    r1 = server._bugs_list_impl(repo_path=str(repo))
    assert r1.get("count") == 0
    assert r1.get("bugs") == []
    r2 = server._bugs_get_impl(bug_id="BUG-001", repo_path=str(repo))
    assert "error" in r2


# ── JSON serializability ────────────────────────────────────


def test_all_outputs_json_serializable(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    for r in (
        server._bugs_list_impl(repo_path=str(repo)),
        server._bugs_get_impl(bug_id="BUG-201", repo_path=str(repo)),
    ):
        json.dumps(r)


# ── Read-only contract ──────────────────────────────────────


def test_bugs_md_not_modified(tmp_path):
    from muninn.mcp import server
    repo = _make_bugs_repo(tmp_path)
    bugs_md = repo / "BUGS.md"
    before_mtime = bugs_md.stat().st_mtime
    before_size = bugs_md.stat().st_size
    before_content = bugs_md.read_text(encoding="utf-8")
    time.sleep(0.01)

    server._bugs_list_impl(repo_path=str(repo))
    server._bugs_get_impl(bug_id="BUG-202", repo_path=str(repo))

    assert bugs_md.stat().st_mtime == before_mtime
    assert bugs_md.stat().st_size == before_size
    assert bugs_md.read_text(encoding="utf-8") == before_content


# ── Real-world smoke (on actual MUNINN- BUGS.md) ──────────


def test_real_bugs_md_parses_without_crash():
    """Sanity check: the real BUGS.md (700+ lines) should parse without error."""
    from muninn.mcp import server
    r = server._bugs_list_impl(repo_path=str(REPO_ROOT), limit=500)
    assert isinstance(r, dict)
    assert r.get("count", 0) > 0
    # Should find at least a BUG-1XX (we have 91, 101..111 documented)
    ids = [b["id"] for b in r["bugs"]]
    assert any(i.startswith("BUG-1") for i in ids), (
        f"expected BUG-1XX in real BUGS.md, got: {ids[:10]}"
    )
