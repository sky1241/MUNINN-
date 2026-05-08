"""CHUNK B4 — cleanup orphan tree.lock and other stale .lock files.

`cleanup_tmp_files()` exists and removes .tmp files >1h old in .muninn/.
But it does NOT clean .lock files. After Run-3 audit, a 1-byte
memory/tree.lock was observed orphaned (process killed mid-write
between lock acquire and unlock).

Fix: extend cleanup_tmp_files to also remove .lock files >1h in
both .muninn/ and TREE_DIR. Locks held by live processes are
short-lived (<5s in `_tree_lock`); a .lock older than 1h is
unambiguously stale.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B4
"""
import os
import sys
import time
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_tree():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_tree" in sys.modules:
        return sys.modules["muninn_tree"]
    import muninn_tree
    return muninn_tree


@pytest.fixture
def isolated_repo(tmp_path, monkeypatch):
    muninn_dir = tmp_path / ".muninn"
    muninn_dir.mkdir()
    tree_dir = muninn_dir / "tree"
    tree_dir.mkdir()

    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    monkeypatch.setattr(_m, "TREE_DIR", tree_dir)
    return tmp_path, muninn_dir, tree_dir


def _make_aged_file(path: Path, age_seconds: int, content: bytes = b"x"):
    """Create a file then backdate its mtime."""
    path.write_bytes(content)
    old_time = time.time() - age_seconds
    os.utime(path, (old_time, old_time))


def test_cleanup_removes_orphan_lock_2h_old(isolated_repo):
    """A .lock file >1h old must be removed."""
    mt = _load_muninn_tree()
    tmp_path, muninn_dir, tree_dir = isolated_repo
    lock = tree_dir / "tree.lock"
    _make_aged_file(lock, age_seconds=2 * 3600)
    assert lock.exists()
    mt.cleanup_tmp_files()
    assert not lock.exists(), "Stale .lock should have been removed"


def test_cleanup_keeps_recent_lock(isolated_repo):
    """A .lock file <1h old (probably live) must NOT be removed."""
    mt = _load_muninn_tree()
    tmp_path, muninn_dir, tree_dir = isolated_repo
    lock = tree_dir / "tree.lock"
    _make_aged_file(lock, age_seconds=300)  # 5 min old
    mt.cleanup_tmp_files()
    assert lock.exists(), "Recent .lock must NOT be removed"


def test_cleanup_still_removes_old_tmp_files(isolated_repo):
    """Regression: existing .tmp cleanup must still work."""
    mt = _load_muninn_tree()
    tmp_path, muninn_dir, tree_dir = isolated_repo
    tmp = muninn_dir / "tree_abc.tmp"
    _make_aged_file(tmp, age_seconds=2 * 3600)
    mt.cleanup_tmp_files()
    assert not tmp.exists()


def test_cleanup_keeps_recent_tmp(isolated_repo):
    """Regression: recent .tmp files must NOT be removed."""
    mt = _load_muninn_tree()
    tmp_path, muninn_dir, tree_dir = isolated_repo
    tmp = muninn_dir / "fresh.tmp"
    _make_aged_file(tmp, age_seconds=300)
    mt.cleanup_tmp_files()
    assert tmp.exists()


def test_cleanup_returns_count(isolated_repo):
    """cleanup_tmp_files returns the number of files removed."""
    mt = _load_muninn_tree()
    tmp_path, muninn_dir, tree_dir = isolated_repo
    _make_aged_file(tree_dir / "a.lock", age_seconds=2 * 3600)
    _make_aged_file(tree_dir / "b.lock", age_seconds=2 * 3600)
    _make_aged_file(muninn_dir / "c.tmp", age_seconds=2 * 3600)
    n = mt.cleanup_tmp_files()
    assert n == 3, f"expected 3 removed, got {n}"


def test_cleanup_handles_missing_dirs(tmp_path, monkeypatch):
    """cleanup_tmp_files must not crash if .muninn/ does not exist."""
    mt = _load_muninn_tree()
    import muninn as _m
    monkeypatch.setattr(_m, "_REPO_PATH", tmp_path)
    if hasattr(_m, "_refresh_tree_paths"):
        _m._refresh_tree_paths()
    n = mt.cleanup_tmp_files()
    assert n == 0
