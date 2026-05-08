#!/usr/bin/env python3
"""CHUNK C7 — Mycelium DB backup with WAL checkpoint.

Pre-fix: ~/.muninn/mycelium.db.backup-2026-04-30 was the only backup,
8 days stale at audit time. No incremental procedure, no rotation.
A corruption today would lose ~8 days of mycelium learning.

Usage:
    python scripts/backup_mycelium.py [--repo PATH] [--keep N]

What it does:
    1. PRAGMA wal_checkpoint(TRUNCATE) -- merges WAL into the main DB
       so the snapshot is point-in-time consistent.
    2. Copies mycelium.db -> mycelium.db.YYYY-MM-DD-HHMM
    3. Optionally compresses the snapshot with gzip.
    4. Removes backups older than --keep days (default 7).

Restore procedure:
    sqlite3 mycelium.db ".restore <backup_file>"
    OR cp <backup_file> mycelium.db (DB must be closed)

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C7
"""
import argparse
import gzip
import shutil
import sqlite3
import sys
import time
from pathlib import Path


def backup_mycelium(
    repo_path: Path,
    keep_days: int = 7,
    compress: bool = True,
    *,
    timestamp: str | None = None,
) -> Path | None:
    """Create a point-in-time mycelium.db snapshot. Returns the backup path
    or None if there is nothing to back up."""
    db_path = Path(repo_path) / ".muninn" / "mycelium.db"
    if not db_path.exists():
        return None

    # 1. Force WAL checkpoint so the .db file is fully up to date.
    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        print(f"WARN: wal_checkpoint failed ({e}); proceeding with copy anyway",
              file=sys.stderr)

    # 2. Copy with a timestamped name.
    if timestamp is None:
        timestamp = time.strftime("%Y-%m-%d-%H%M")
    backup = db_path.with_suffix(f".db.backup-{timestamp}")
    shutil.copy2(str(db_path), str(backup))

    # 3. Optional gzip.
    if compress:
        gz = backup.with_suffix(backup.suffix + ".gz")
        with open(backup, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        backup.unlink()
        backup = gz

    # 4. Rotate: remove backups older than keep_days.
    cutoff = time.time() - (keep_days * 24 * 3600)
    for old in db_path.parent.glob("mycelium.db.backup-*"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass

    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--keep", type=int, default=7, help="Days of backups to keep (default 7)")
    parser.add_argument("--no-gzip", action="store_true", help="Skip gzip compression")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    backup = backup_mycelium(repo, keep_days=args.keep, compress=not args.no_gzip)
    if backup is None:
        print(f"No mycelium.db at {repo}/.muninn/", file=sys.stderr)
        return 1
    print(f"Backup written: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
