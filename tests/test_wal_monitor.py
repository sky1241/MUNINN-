"""Tests for WAL Adaptive Flush monitor."""
import sqlite3
import tempfile
import time
import os
import sys
import pytest

from wal_monitor import WALMonitor, WALConfig


@pytest.fixture
def wal_db():
    """Create a temporary SQLite DB with WAL mode."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    yield conn, tmp.name
    conn.close()
    try:
        os.unlink(tmp.name)
        for ext in ("-wal", "-shm"):
            p = tmp.name + ext
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


def test_should_checkpoint_over_threshold(wal_db):
    """should_checkpoint() returns True when WAL > threshold."""
    conn, _ = wal_db
    config = WALConfig(check_every=1, default_threshold_pages=1)
    monitor = WALMonitor(conn, config)
    # Write enough to exceed 1 page threshold
    for i in range(100):
        conn.execute("INSERT INTO test (val) VALUES (?)", (f"data_{i}" * 50,))
    conn.commit()
    assert monitor.should_checkpoint() is True


def test_should_checkpoint_over_interval(wal_db):
    """should_checkpoint() returns True when interval > max_interval_sec."""
    conn, _ = wal_db
    config = WALConfig(max_interval_sec=0.01)  # 10ms
    monitor = WALMonitor(conn, config)
    time.sleep(0.02)
    assert monitor.should_checkpoint() is True


def test_compute_threshold_reduces_on_slow_checkpoints(wal_db):
    """compute_threshold() reduces threshold when checkpoints are slow."""
    conn, _ = wal_db
    config = WALConfig(default_threshold_pages=1000)
    monitor = WALMonitor(conn, config)
    # Fake slow checkpoint history (>500ms each)
    monitor.checkpoint_history = [
        (time.time(), 500, 600.0),
        (time.time(), 500, 700.0),
        (time.time(), 500, 550.0),
    ]
    threshold = config.compute_threshold(monitor.checkpoint_history)
    assert threshold == 500  # Should be reduced to 50% of default


def test_compute_threshold_increases_on_fast_checkpoints(wal_db):
    """compute_threshold() increases threshold when checkpoints are fast."""
    conn, _ = wal_db
    config = WALConfig(default_threshold_pages=1000)
    monitor = WALMonitor(conn, config)
    # Fake fast checkpoint history (<50ms each)
    monitor.checkpoint_history = [
        (time.time(), 100, 10.0),
        (time.time(), 100, 15.0),
        (time.time(), 100, 12.0),
    ]
    threshold = config.compute_threshold(monitor.checkpoint_history)
    assert threshold == 2000  # Should be increased to 200% of default


def test_batch_writes_trigger_checkpoint(wal_db):
    """Batch writes with low interval trigger at least one checkpoint."""
    conn, db_path = wal_db
    config = WALConfig(
        check_every=5,
        default_threshold_pages=1,  # Very low threshold
        max_interval_sec=0.01,  # Very short interval
    )
    monitor = WALMonitor(conn, config)
    for i in range(100):
        conn.execute("INSERT INTO test (val) VALUES (?)", (f"data_{i}" * 100,))
        conn.commit()
        monitor.on_write()
    # With such low thresholds, should have checkpointed at least once
    assert len(monitor.checkpoint_history) > 0


def test_passive_does_not_block_reads(wal_db):
    """PASSIVE checkpoint does not block concurrent reads."""
    conn, db_path = wal_db
    monitor = WALMonitor(conn)
    # Insert data
    for i in range(50):
        conn.execute("INSERT INTO test (val) VALUES (?)", (f"data_{i}",))
    conn.commit()
    # Open a second connection for reading
    conn2 = sqlite3.connect(db_path)
    rows = conn2.execute("SELECT COUNT(*) FROM test").fetchone()
    assert rows[0] == 50
    # Checkpoint while second connection is reading
    monitor.checkpoint()  # Should not raise
    # Second connection still works
    rows2 = conn2.execute("SELECT COUNT(*) FROM test").fetchone()
    assert rows2[0] == 50
    conn2.close()
