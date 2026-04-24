"""Phase 8 tests — Cleanup (C1-C2).

Tests cover: legacy tree.json removal, orphaned .tmp file cleanup.
"""
import os
import sys
import time
from pathlib import Path

import pytest

# ── C1: Remove memory/tree.json legacy ──────────────────────────

class TestC1LegacyTree:
    def test_cleanup_removes_legacy(self, tmp_path, monkeypatch):
        """C1: Removes legacy memory/tree.json when .muninn/tree/ exists."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        # Create both trees
        legacy_dir = tmp_path / "memory"
        legacy_dir.mkdir()
        (legacy_dir / "tree.json").write_text("{}", encoding="utf-8")
        (legacy_dir / "old_branch.mn").write_text("content", encoding="utf-8")

        new_dir = tmp_path / ".muninn" / "tree"
        new_dir.mkdir(parents=True)
        (new_dir / "tree.json").write_text("{}", encoding="utf-8")
        (new_dir / "old_branch.mn").write_text("content", encoding="utf-8")

        result = muninn.cleanup_legacy_tree()
        assert result is True
        assert not (legacy_dir / "tree.json").exists()

    def test_no_cleanup_when_no_new_tree(self, tmp_path, monkeypatch):
        """C1: No cleanup if .muninn/tree/tree.json doesn't exist."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        legacy_dir = tmp_path / "memory"
        legacy_dir.mkdir()
        (legacy_dir / "tree.json").write_text("{}", encoding="utf-8")

        result = muninn.cleanup_legacy_tree()
        assert result is False
        assert (legacy_dir / "tree.json").exists()

    def test_no_cleanup_when_no_legacy(self, tmp_path, monkeypatch):
        """C1: No cleanup if legacy tree doesn't exist."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        new_dir = tmp_path / ".muninn" / "tree"
        new_dir.mkdir(parents=True)
        (new_dir / "tree.json").write_text("{}", encoding="utf-8")

        result = muninn.cleanup_legacy_tree()
        assert result is False


# ── C2: Cleanup orphaned .tmp files ─────────────────────────────

class TestC2TmpCleanup:
    def test_cleanup_old_tmp_files(self, tmp_path, monkeypatch):
        """C2: Removes .tmp files older than 1 hour."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir()
        # Create old .tmp file (fake old mtime)
        tmp_file = muninn_dir / "old_file.tmp"
        tmp_file.write_text("stale", encoding="utf-8")
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(str(tmp_file), (old_time, old_time))

        removed = muninn.cleanup_tmp_files()
        assert removed == 1
        assert not tmp_file.exists()

    def test_keep_recent_tmp_files(self, tmp_path, monkeypatch):
        """C2: Keeps .tmp files younger than 1 hour."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir()
        tmp_file = muninn_dir / "fresh_file.tmp"
        tmp_file.write_text("fresh", encoding="utf-8")

        removed = muninn.cleanup_tmp_files()
        assert removed == 0
        assert tmp_file.exists()

    def test_cleanup_nested_tmp(self, tmp_path, monkeypatch):
        """C2: Cleanup finds .tmp in subdirectories."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        subdir = tmp_path / ".muninn" / "tree"
        subdir.mkdir(parents=True)
        tmp_file = subdir / "tree_12345.tmp"
        tmp_file.write_text("stale", encoding="utf-8")
        old_time = time.time() - 7200
        os.utime(str(tmp_file), (old_time, old_time))

        removed = muninn.cleanup_tmp_files()
        assert removed == 1

    def test_no_cleanup_no_muninn(self, tmp_path, monkeypatch):
        """C2: Returns 0 when .muninn/ doesn't exist."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)

        removed = muninn.cleanup_tmp_files()
        assert removed == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
