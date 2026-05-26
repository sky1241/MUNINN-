"""R2-008: SharedFileBackend.push() incremental via last_sync_day.

PC1 R2 fix (commit fabe8a0) changed sync_backend.py:230-274 to push only edges
with `last_seen >= last_sync_day` instead of full table. Pre-existing
test_phase1_sync covered general SharedFileBackend behavior but NOT the
specific incremental WHERE clause. This test plugs the gap.

Verifies:
1. First push (no last_sync_day) sees all edges.
2. After push, last_sync_day is set in working DB meta.
3. Second push with same edges pushes 0 new (incremental filter works).
4. Add new edge with later last_seen → second push picks it up.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.expanduser("~/Bureau/MUNINN-/engine/core"))


@pytest.fixture
def repo_with_db():
    """Create a temp repo with mycelium DB + a few edges."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        muninn_dir = repo / ".muninn"
        muninn_dir.mkdir()
        from mycelium_db import MyceliumDB
        db = MyceliumDB(muninn_dir / "mycelium.db")
        # Insert 3 edges, all with last_seen=100 (old day)
        c1 = db._get_or_create_concept("alpha")
        c2 = db._get_or_create_concept("beta")
        c3 = db._get_or_create_concept("gamma")
        for a, b in [(c1, c2), (c2, c3), (c1, c3)]:
            db._conn.execute("""
                INSERT INTO edges (a, b, count, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
            """, (a, b, 1, 100, 100))
        db._conn.commit()
        yield repo, db
        db.close()


@pytest.fixture
def shared_meta_repo():
    """Create a temp shared meta_dir for SharedFileBackend."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def test_first_push_sends_all_edges(repo_with_db, shared_meta_repo):
    """No last_sync_day set → all 3 edges pushed."""
    from sync_backend import SharedFileBackend, SyncPayload
    repo, local_db = repo_with_db
    backend = SharedFileBackend(meta_dir=shared_meta_repo)
    payload = SyncPayload(repo_name="test_repo", zone=None)
    n_synced = backend.push(payload, local_db=local_db)
    assert n_synced == 3, f"first push expected 3 edges, got {n_synced}"


def test_last_sync_day_set_after_push(repo_with_db, shared_meta_repo):
    """After push, working DB meta has last_sync_day = today."""
    from sync_backend import SharedFileBackend, SyncPayload
    repo, local_db = repo_with_db
    backend = SharedFileBackend(meta_dir=shared_meta_repo)
    backend.push(SyncPayload(repo_name="test_repo", zone=None), local_db=local_db)

    row = local_db._conn.execute(
        "SELECT value FROM meta WHERE key='last_sync_day'"
    ).fetchone()
    assert row is not None, "last_sync_day not set after push"
    today_day = int(time.time() / 86400)
    assert int(row[0]) == today_day, f"expected last_sync_day={today_day}, got {row[0]}"


def test_incremental_push_skips_unchanged(repo_with_db, shared_meta_repo):
    """Second push with no new edges → 0 synced (WHERE last_seen >= last_sync_day filter)."""
    from sync_backend import SharedFileBackend, SyncPayload
    repo, local_db = repo_with_db
    backend = SharedFileBackend(meta_dir=shared_meta_repo)
    payload = SyncPayload(repo_name="test_repo", zone=None)

    # First push: all 3 edges (last_seen=100, last_sync_day not set yet)
    first = backend.push(payload, local_db=local_db)
    assert first == 3

    # Second push: same edges, but now last_sync_day = today (a huge number).
    # Since edges have last_seen=100 which is < today_day, they should be filtered OUT.
    second = backend.push(payload, local_db=local_db)
    assert second == 0, f"incremental push expected 0 (no new edges), got {second}"


def test_incremental_picks_up_new_edges(repo_with_db, shared_meta_repo):
    """Add edge with last_seen=today → second push picks it up."""
    from sync_backend import SharedFileBackend, SyncPayload
    repo, local_db = repo_with_db
    backend = SharedFileBackend(meta_dir=shared_meta_repo)
    payload = SyncPayload(repo_name="test_repo", zone=None)

    backend.push(payload, local_db=local_db)  # First push (sets last_sync_day=today)
    today_day = int(time.time() / 86400)

    # Add a new edge with last_seen=today_day + 1 (future) — should be pushed
    c4 = local_db._get_or_create_concept("delta")
    c5 = local_db._get_or_create_concept("epsilon")
    local_db._conn.execute("""
        INSERT INTO edges (a, b, count, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
    """, (c4, c5, 1, today_day + 1, today_day + 1))
    local_db._conn.commit()

    second = backend.push(payload, local_db=local_db)
    assert second >= 1, f"expected at least 1 new edge pushed, got {second}"
