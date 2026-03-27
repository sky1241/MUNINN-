"""Tests for BRIQUE 4: Graceful feed timeout.

Validates that:
1. feed_from_transcript saves progress and exits when time budget exceeded
2. Next call resumes from saved offset (not from 0)
3. Normal feed (no timeout) completes fully
4. Progress file tracks correct offset after timeout
5. Timeout only checked at chunk boundaries (every 50 messages)
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))


def _make_repo(tmp_path):
    """Create a minimal repo structure."""
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)
    # Create SQLite DB
    from mycelium_db import MyceliumDB
    db_path = muninn_dir / "mycelium.db"
    db = MyceliumDB(db_path)
    db._conn.execute("INSERT INTO meta (key, value) VALUES ('migration_complete', '1')")
    db._conn.commit()
    db.close()
    return tmp_path


def _make_transcript(tmp_path, n_messages=100):
    """Create a fake JSONL transcript with N user messages."""
    jsonl_path = tmp_path / "test_session.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for i in range(n_messages):
            entry = {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": f"Message number {i} about concept_{i} and topic_{i}"}]
                }
            }
            f.write(json.dumps(entry) + "\n")
    return jsonl_path


class TestFeedTimeout:
    """Test graceful timeout in feed_from_transcript."""

    def test_normal_feed_completes(self, tmp_path):
        """Without timeout pressure, feed should complete all messages."""
        repo = _make_repo(tmp_path)
        jsonl = _make_transcript(tmp_path, n_messages=20)
        import muninn
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        count, texts = muninn.feed_from_transcript(jsonl, repo, max_seconds=60.0)
        assert count == 20

    def test_timeout_saves_progress(self, tmp_path):
        """With very short timeout, feed should save progress and stop early."""
        repo = _make_repo(tmp_path)
        # Create enough messages that we'll hit at least 1 chunk boundary
        jsonl = _make_transcript(tmp_path, n_messages=200)
        import muninn
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        # max_seconds=0 means timeout immediately after first chunk
        count, texts = muninn.feed_from_transcript(jsonl, repo, max_seconds=0.0)
        # Should have stopped after first chunk (50 messages)
        assert count <= 50, f"Should stop after first chunk, got {count}"
        # Progress file should exist with offset
        progress_path = repo / ".muninn" / "feed_progress.json"
        assert progress_path.exists()
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        file_key = jsonl.name
        assert file_key in progress
        assert progress[file_key]["offset"] <= 50

    def test_resume_after_timeout(self, tmp_path):
        """After timeout, next call should resume from saved offset."""
        repo = _make_repo(tmp_path)
        jsonl = _make_transcript(tmp_path, n_messages=200)
        import muninn
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()

        # First call: timeout after first chunk
        count1, _ = muninn.feed_from_transcript(jsonl, repo, max_seconds=0.0)
        assert count1 <= 50

        # Second call: should resume and feed more
        count2, _ = muninn.feed_from_transcript(jsonl, repo, max_seconds=0.0)
        assert count2 > count1, f"Should resume from {count1}, got {count2}"

    def test_full_completion_after_multiple_timeouts(self, tmp_path):
        """Multiple timed-out calls should eventually complete all messages."""
        repo = _make_repo(tmp_path)
        jsonl = _make_transcript(tmp_path, n_messages=10)
        import muninn
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()

        # With 0s timeout, each call processes 1 message then times out.
        # After 10+ calls, all 10 messages should be processed.
        total_fed = 0
        max_rounds = 15  # a few extra for safety
        for _ in range(max_rounds):
            count, _ = muninn.feed_from_transcript(jsonl, repo, max_seconds=0.0)
            if count >= 10:
                total_fed = count
                break
            total_fed = count
        assert total_fed >= 10, f"Should complete after multiple rounds, got {total_fed}"

    def test_progress_file_format(self, tmp_path):
        """Progress file should have correct structure."""
        repo = _make_repo(tmp_path)
        jsonl = _make_transcript(tmp_path, n_messages=100)
        import muninn
        muninn._REPO_PATH = repo
        muninn._refresh_tree_paths()
        muninn.feed_from_transcript(jsonl, repo, max_seconds=0.0)

        progress_path = repo / ".muninn" / "feed_progress.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        entry = progress[jsonl.name]
        assert "offset" in entry
        assert "size" in entry
        assert isinstance(entry["offset"], int)
        assert entry["size"] == jsonl.stat().st_size
