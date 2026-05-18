"""CHUNK 10 follow-up (2026-05-18): scan_repo now grows the mycelium graph.

Before today, `muninn-mem scan <repo>` only wrote a per-target codebook
(`<repo>/.muninn/local.json`). The mycelium graph (`mycelium.db`) was
populated only by `muninn-mem bootstrap`, which had no UI palette
equivalent. User intent was "scan = learn the repo", so observe_text()
calls were added to scan_repo to fill mycelium.db too.

These tests lock the behavior so the next refactor doesn't silently
break it again. The deep audit on 2026-05-18 found zero coverage on
this path — see commit 0fd5a92 for the related /reconstruct gate fix
that surfaced the missing mycelium population.
"""

from pathlib import Path

import pytest


def _make_scannable(repo: Path) -> None:
    """Create a small repo with code + docs that scan_repo will pick up."""
    (repo / "src.py").write_text(
        "import muninn\n"
        "class Mycelium:\n"
        "    def observe_text(self, text):\n"
        "        return text\n"
        "mycelium = Mycelium()\n"
        * 3
    )
    (repo / "README.md").write_text(
        "# Demo repo\n"
        "This repo exercises the mycelium scan growth path.\n"
        "Keywords: mycelium scan compression learning.\n"
        * 3
    )


def test_scan_creates_mycelium_db(tmp_path):
    """scan_repo writes .muninn/mycelium.db on first run."""
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "scan_repo should create mycelium.db"
    assert db.stat().st_size > 0, "mycelium.db should not be empty"


def test_scan_still_writes_local_json(tmp_path):
    """Mycelium growth must not break the existing local.json output."""
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    local = tmp_path / ".muninn" / "local.json"
    assert local.exists(), "scan_repo must still write local.json"
    import json
    data = json.loads(local.read_text(encoding="utf-8"))
    assert data.get("repo_name") == tmp_path.name


def test_scan_mycelium_db_has_concepts(tmp_path):
    """The created mycelium.db must contain at least one concept row.

    Catches the 'creates the file but never observes' regression.
    """
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    import sqlite3
    db = tmp_path / ".muninn" / "mycelium.db"
    conn = sqlite3.connect(db)
    try:
        # The mycelium schema has a `concepts` table (tier3 S1 migration).
        concept_count = conn.execute(
            "SELECT COUNT(*) FROM concepts"
        ).fetchone()[0]
    finally:
        conn.close()
    assert concept_count > 0, (
        f"Expected mycelium to have at least one concept after scan, "
        f"got {concept_count}"
    )


def test_scan_mirror_path_works(tmp_path):
    """The muninn/_engine.py mirror (BUG-091) must also grow mycelium.

    If the mirror was forgotten, importing muninn-mem (which uses
    muninn/_engine.py) would still leave mycelium.db absent.
    """
    _make_scannable(tmp_path)
    from muninn._engine import scan_repo as scan_repo_mirror

    scan_repo_mirror(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "muninn/_engine.py mirror must also create mycelium.db"
    assert db.stat().st_size > 0
