"""
B-SCAN-12: Incremental Cache — Tests
======================================
Validates cache load/save, delta computation, and update logic.
"""
import json
import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.cache import (
    ScanCacheEntry,
    DeltaResult,
    load_cache,
    save_cache,
    compute_delta,
    update_cache,
)


class TestBSCAN12IncrementalCache:
    """Core incremental cache validation."""

    # ── load / save ──────────────────────────────────────────────

    def test_load_cache_missing_file(self, tmp_path):
        """Loading a non-existent cache returns empty dict."""
        result = load_cache(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_load_cache_corrupt_json(self, tmp_path):
        """Loading a corrupt JSON returns empty dict (no crash)."""
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json!!!", encoding="utf-8")
        result = load_cache(str(bad))
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        """Save then load preserves all fields."""
        cache_path = str(tmp_path / "cache.json")
        data = {
            "src/main.py": ScanCacheEntry(
                sha256="abc123",
                last_scan_date="2026-03-25T12:00:00Z",
                findings=[{"rule": "SQL-INJ", "line": 42}],
            ),
            "src/util.py": ScanCacheEntry(
                sha256="def456",
                last_scan_date="2026-03-25T12:01:00Z",
                findings=[],
            ),
        }
        save_cache(cache_path, data)
        loaded = load_cache(cache_path)
        assert len(loaded) == 2
        assert loaded["src/main.py"].sha256 == "abc123"
        assert loaded["src/main.py"].findings == [{"rule": "SQL-INJ", "line": 42}]
        assert loaded["src/util.py"].sha256 == "def456"
        assert loaded["src/util.py"].findings == []

    def test_save_creates_parent_dirs(self, tmp_path):
        """save_cache creates intermediate directories."""
        cache_path = str(tmp_path / "deep" / "nested" / "cache.json")
        save_cache(cache_path, {"a.py": ScanCacheEntry("h1", "2026-01-01T00:00:00Z", [])})
        assert os.path.exists(cache_path)

    # ── compute_delta ────────────────────────────────────────────

    def test_first_run_all_to_scan(self, tmp_path):
        """First run (no cache) marks all files as to_scan."""
        cache_path = str(tmp_path / "cache.json")
        hashes = {"a.py": "aaa", "b.py": "bbb", "c.py": "ccc"}
        delta = compute_delta(hashes, cache_path)
        assert delta.is_first_run is True
        assert sorted(delta.to_scan) == ["a.py", "b.py", "c.py"]
        assert delta.unchanged == []
        assert delta.removed == []

    def test_unchanged_files_skipped(self, tmp_path):
        """Files with same hash are in unchanged, not to_scan."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "a.py": ScanCacheEntry("aaa", "2026-03-25T00:00:00Z", []),
            "b.py": ScanCacheEntry("bbb", "2026-03-25T00:00:00Z", []),
        })
        hashes = {"a.py": "aaa", "b.py": "bbb"}
        delta = compute_delta(hashes, cache_path)
        assert delta.is_first_run is False
        assert delta.to_scan == []
        assert sorted(delta.unchanged) == ["a.py", "b.py"]
        assert delta.removed == []

    def test_modified_file_in_delta(self, tmp_path):
        """A file whose hash changed must appear in to_scan."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "a.py": ScanCacheEntry("aaa", "2026-03-25T00:00:00Z", []),
        })
        hashes = {"a.py": "CHANGED_HASH"}
        delta = compute_delta(hashes, cache_path)
        assert "a.py" in delta.to_scan
        assert "a.py" not in delta.unchanged

    def test_new_file_in_delta(self, tmp_path):
        """A file not in cache must appear in to_scan."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "a.py": ScanCacheEntry("aaa", "2026-03-25T00:00:00Z", []),
        })
        hashes = {"a.py": "aaa", "new.py": "nnn"}
        delta = compute_delta(hashes, cache_path)
        assert "new.py" in delta.to_scan
        assert "a.py" in delta.unchanged

    def test_removed_file_detected(self, tmp_path):
        """A file in cache but not in current hashes is removed."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "a.py": ScanCacheEntry("aaa", "2026-03-25T00:00:00Z", []),
            "deleted.py": ScanCacheEntry("ddd", "2026-03-25T00:00:00Z", []),
        })
        hashes = {"a.py": "aaa"}
        delta = compute_delta(hashes, cache_path)
        assert "deleted.py" in delta.removed
        assert "a.py" in delta.unchanged

    def test_mixed_scenario(self, tmp_path):
        """New + modified + unchanged + removed all at once."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "unchanged.py": ScanCacheEntry("uuu", "2026-03-25T00:00:00Z", []),
            "modified.py": ScanCacheEntry("old_hash", "2026-03-25T00:00:00Z", []),
            "removed.py": ScanCacheEntry("rrr", "2026-03-25T00:00:00Z", []),
        })
        hashes = {
            "unchanged.py": "uuu",
            "modified.py": "new_hash",
            "brand_new.py": "nnn",
        }
        delta = compute_delta(hashes, cache_path)
        assert sorted(delta.to_scan) == ["brand_new.py", "modified.py"]
        assert delta.unchanged == ["unchanged.py"]
        assert delta.removed == ["removed.py"]
        assert delta.is_first_run is False

    # ── update_cache ─────────────────────────────────────────────

    def test_update_cache_adds_entry(self, tmp_path):
        """update_cache creates a new entry with correct fields."""
        cache_path = str(tmp_path / "cache.json")
        update_cache(cache_path, "src/app.py", "hash123", [{"rule": "XSS", "line": 10}])
        cache = load_cache(cache_path)
        assert "src/app.py" in cache
        entry = cache["src/app.py"]
        assert entry.sha256 == "hash123"
        assert entry.findings == [{"rule": "XSS", "line": 10}]
        assert "T" in entry.last_scan_date  # ISO format

    def test_update_cache_overwrites_existing(self, tmp_path):
        """update_cache replaces an existing entry."""
        cache_path = str(tmp_path / "cache.json")
        update_cache(cache_path, "x.py", "old", [])
        update_cache(cache_path, "x.py", "new", [{"rule": "SQLI"}])
        cache = load_cache(cache_path)
        assert cache["x.py"].sha256 == "new"
        assert len(cache["x.py"].findings) == 1

    def test_update_cache_default_empty_findings(self, tmp_path):
        """update_cache with no findings defaults to empty list."""
        cache_path = str(tmp_path / "cache.json")
        update_cache(cache_path, "clean.py", "h1")
        cache = load_cache(cache_path)
        assert cache["clean.py"].findings == []

    def test_update_preserves_other_entries(self, tmp_path):
        """Updating one file doesn't clobber other entries."""
        cache_path = str(tmp_path / "cache.json")
        update_cache(cache_path, "a.py", "aaa")
        update_cache(cache_path, "b.py", "bbb")
        cache = load_cache(cache_path)
        assert "a.py" in cache
        assert "b.py" in cache

    # ── edge cases ───────────────────────────────────────────────

    def test_empty_hashes_all_removed(self, tmp_path):
        """Empty current_hashes means everything in cache is removed."""
        cache_path = str(tmp_path / "cache.json")
        save_cache(cache_path, {
            "a.py": ScanCacheEntry("aaa", "2026-03-25T00:00:00Z", []),
        })
        delta = compute_delta({}, cache_path)
        assert delta.to_scan == []
        assert delta.removed == ["a.py"]
        assert delta.is_first_run is False

    def test_empty_hashes_empty_cache(self, tmp_path):
        """Empty hashes + no cache = first run with nothing to scan."""
        cache_path = str(tmp_path / "cache.json")
        delta = compute_delta({}, cache_path)
        assert delta.is_first_run is True
        assert delta.to_scan == []
