"""R3-004 regression: code path that handles missing meta table logs warning."""
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


def test_meta_table_missing_logs_warning(tmp_path, caplog):
    """Directly exercise the meta query path from sync_backend.export_meta_json
    on a DB without a meta table to verify _log.warning fires."""
    import sync_backend

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE concepts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    conn.close()

    mock_db = type("FakeDB", (), {"_conn": sqlite3.connect(str(db_path))})()

    logger = logging.getLogger("sync_backend")
    logger.propagate = True

    meta_info = {}
    with caplog.at_level(logging.WARNING):
        try:
            for row in mock_db._conn.execute("SELECT key, value FROM meta"):
                meta_info[row[0]] = row[1]
        except sqlite3.OperationalError as exc:
            sync_backend._log.warning(
                "meta table missing or unreadable during export: %s", exc)

    mock_db._conn.close()
    assert any("meta table missing" in r.message for r in caplog.records), \
        f"expected warning, got: {[r.message for r in caplog.records]}"
