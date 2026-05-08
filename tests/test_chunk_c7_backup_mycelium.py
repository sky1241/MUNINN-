"""CHUNK C7 — Mycelium backup script (WAL checkpoint + rotation)."""
import importlib.util
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_backup_module():
    src = REPO / "scripts" / "backup_mycelium.py"
    if not src.exists():
        pytest.skip("scripts/backup_mycelium.py missing — see CHUNK C7")
    spec = importlib.util.spec_from_file_location("_chunk_c7_backup", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_db(db_path: Path) -> None:
    """Create a tiny SQLite DB with WAL mode enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS edges (a INT, b INT, count INT)")
    conn.execute("INSERT INTO edges VALUES (1, 2, 5), (3, 4, 7)")
    conn.commit()
    conn.close()


def test_backup_module_exists():
    src = REPO / "scripts" / "backup_mycelium.py"
    assert src.exists(), "scripts/backup_mycelium.py must exist (CHUNK C7)"


def test_backup_returns_none_when_no_db(tmp_path):
    mod = _load_backup_module()
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    result = mod.backup_mycelium(repo)
    assert result is None


def test_backup_creates_snapshot(tmp_path):
    mod = _load_backup_module()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    _seed_db(db)

    backup = mod.backup_mycelium(repo, compress=False)
    assert backup is not None
    assert backup.exists()
    assert "backup-" in backup.name


def test_backup_with_gzip_creates_gz(tmp_path):
    mod = _load_backup_module()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    _seed_db(db)

    backup = mod.backup_mycelium(repo, compress=True)
    assert backup is not None
    assert backup.suffix == ".gz"
    # The uncompressed intermediate file should be removed
    intermediate = backup.with_suffix("")
    assert not intermediate.exists() or intermediate == backup


def test_backup_rotation_removes_old(tmp_path):
    mod = _load_backup_module()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    _seed_db(db)

    # Plant an old backup (15 days ago)
    old = repo / ".muninn" / "mycelium.db.backup-2026-04-23-1200"
    old.write_text("old")
    old_time = time.time() - (15 * 24 * 3600)
    os.utime(old, (old_time, old_time))

    mod.backup_mycelium(repo, keep_days=7, compress=False)
    assert not old.exists(), "old backup beyond keep_days should be removed"


def test_backup_runs_wal_checkpoint(tmp_path):
    """The backup function must invoke PRAGMA wal_checkpoint to flush
    pending writes into the main DB before the snapshot."""
    mod = _load_backup_module()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    _seed_db(db)

    # Write extra data while WAL is active
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO edges VALUES (5, 6, 9)")
    conn.commit()
    conn.close()

    backup = mod.backup_mycelium(repo, compress=False)
    assert backup is not None and backup.exists()
    # Open the backup and verify all 3 edges are present (proves WAL was merged)
    bconn = sqlite3.connect(str(backup))
    n = bconn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    bconn.close()
    assert n == 3, f"backup missing edges: got {n} expected 3"


def test_backup_keeps_recent_backups(tmp_path):
    """A recent backup (<keep_days) must NOT be removed during rotation."""
    mod = _load_backup_module()
    repo = tmp_path / "repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    _seed_db(db)

    recent = repo / ".muninn" / "mycelium.db.backup-2026-05-07-1200"
    recent.write_text("recent")
    fresh = time.time() - (1 * 24 * 3600)  # 1 day old
    os.utime(recent, (fresh, fresh))

    mod.backup_mycelium(repo, keep_days=7, compress=False)
    assert recent.exists()
