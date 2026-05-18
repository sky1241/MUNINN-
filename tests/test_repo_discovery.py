"""Tests for engine.core.repo_discovery.find_owning_repo.

Locks in the resolution priority order (env → .muninn → .git → None)
and the walk-up semantics. Drift #9 fix in CHUNK 10 — see
docs/SANDBOX_UX_NOTES.md.
"""
import os
from pathlib import Path

import pytest

from engine.core.repo_discovery import find_owning_repo


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Each test starts with a clean MUNINN_REPO / CLAUDE_PROJECT_DIR."""
    monkeypatch.delenv("MUNINN_REPO", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


def test_returns_none_when_no_signal(tmp_path, monkeypatch):
    """Empty dir, no env, no .muninn, no .git → None.

    Critical: must NOT silently fall back to cwd or install dir
    (that was the drift #9 bug).
    """
    monkeypatch.chdir(tmp_path)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_owning_repo(deep) is None


def test_finds_muninn_marker(tmp_path):
    """.muninn/ in an ancestor → that ancestor."""
    repo = tmp_path / "myrepo"
    (repo / ".muninn").mkdir(parents=True)
    deep = repo / "src" / "lib"
    deep.mkdir(parents=True)
    assert find_owning_repo(deep) == repo.resolve()


def test_finds_git_marker_as_fallback(tmp_path):
    """.git but no .muninn → still returns repo (git fallback)."""
    repo = tmp_path / "myrepo"
    (repo / ".git").mkdir(parents=True)
    deep = repo / "src"
    deep.mkdir(parents=True)
    assert find_owning_repo(deep) == repo.resolve()


def test_muninn_wins_over_git(tmp_path):
    """When both .muninn/ and .git/ exist, .muninn wins (bootstrap signal)."""
    repo = tmp_path / "myrepo"
    (repo / ".muninn").mkdir(parents=True)
    (repo / ".git").mkdir(parents=True)
    src = repo / "src"
    src.mkdir()
    assert find_owning_repo(src) == repo.resolve()


def test_muninn_in_nearer_ancestor_wins(tmp_path):
    """If .muninn is nearer to start than .git is, .muninn wins."""
    outer = tmp_path / "outer"
    (outer / ".git").mkdir(parents=True)
    inner = outer / "inner"
    (inner / ".muninn").mkdir(parents=True)
    leaf = inner / "leaf"
    leaf.mkdir()
    # Nearest .muninn = inner. Even though outer has .git, the .muninn
    # marker is checked first in the same walk-up, and inner wins.
    assert find_owning_repo(leaf) == inner.resolve()


def test_env_munninn_repo_overrides_walk_up(tmp_path, monkeypatch):
    """MUNINN_REPO env wins even if walk-up would find something else."""
    forced = tmp_path / "forced"
    forced.mkdir()
    monkeypatch.setenv("MUNINN_REPO", str(forced))

    other = tmp_path / "other"
    (other / ".muninn").mkdir(parents=True)
    leaf = other / "leaf"
    leaf.mkdir()

    assert find_owning_repo(leaf) == forced


def test_env_claude_project_dir_used_when_no_muninn_repo(tmp_path, monkeypatch):
    """CLAUDE_PROJECT_DIR is honored when MUNINN_REPO is absent."""
    forced = tmp_path / "claudeproj"
    forced.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(forced))
    leaf = tmp_path / "anywhere"
    leaf.mkdir()
    assert find_owning_repo(leaf) == forced


def test_muninn_repo_beats_claude_project_dir(tmp_path, monkeypatch):
    """When both env vars set, MUNINN_REPO has priority."""
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    monkeypatch.setenv("MUNINN_REPO", str(a))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(b))
    assert find_owning_repo(tmp_path) == a


def test_env_var_pointing_to_nonexistent_dir_is_ignored(tmp_path, monkeypatch):
    """Bogus env values must NOT short-circuit the walk-up."""
    monkeypatch.setenv("MUNINN_REPO", str(tmp_path / "does-not-exist"))
    repo = tmp_path / "real"
    (repo / ".muninn").mkdir(parents=True)
    leaf = repo / "leaf"; leaf.mkdir()
    assert find_owning_repo(leaf) == repo.resolve()


def test_start_can_be_a_file(tmp_path):
    """Passing a file path walks from its parent."""
    repo = tmp_path / "myrepo"
    (repo / ".muninn").mkdir(parents=True)
    src = repo / "src.go"
    src.write_text("package main\n")
    assert find_owning_repo(src) == repo.resolve()


def test_start_can_be_a_string(tmp_path):
    """String input is accepted (not only Path)."""
    repo = tmp_path / "myrepo"
    (repo / ".muninn").mkdir(parents=True)
    assert find_owning_repo(str(repo)) == repo.resolve()


def test_default_start_is_cwd(tmp_path, monkeypatch):
    """When start is None, use os.getcwd()."""
    repo = tmp_path / "myrepo"
    (repo / ".muninn").mkdir(parents=True)
    sub = repo / "sub"; sub.mkdir()
    monkeypatch.chdir(sub)
    assert find_owning_repo(None) == repo.resolve()
    assert find_owning_repo() == repo.resolve()


def test_nonexistent_start_returns_none(tmp_path):
    """A start path that doesn't exist returns None (no exceptions)."""
    bogus = tmp_path / "does" / "not" / "exist"
    assert find_owning_repo(bogus) is None
