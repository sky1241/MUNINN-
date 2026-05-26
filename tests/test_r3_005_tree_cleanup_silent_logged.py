"""R3-005 regression: cleanup_tmp_files logs on failure, doesn't crash."""
import logging
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


def test_cleanup_logs_on_unlink_failure(tmp_path, caplog, monkeypatch):
    import muninn_tree
    import muninn as _m

    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir()

    stale = muninn_dir / "old.tmp"
    stale.write_text("garbage")
    old_time = time.time() - 7200
    os.utime(stale, (old_time, old_time))

    os.chmod(str(muninn_dir), 0o555)

    try:
        with caplog.at_level(logging.WARNING):
            muninn_tree.cleanup_tmp_files()
    finally:
        os.chmod(str(muninn_dir), 0o755)

    assert any("cannot remove stale" in r.message for r in caplog.records), \
        f"expected 'cannot remove stale' warning, got: {[r.message for r in caplog.records]}"
