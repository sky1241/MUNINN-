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


# ─── find_bootstrapped_repo ─────────────────────────────────────────


def _make_bootstrapped(repo: Path) -> None:
    """Create a fully-bootstrapped .muninn/ inside `repo`."""
    (repo / ".muninn" / "tree").mkdir(parents=True, exist_ok=True)
    (repo / ".muninn" / "tree" / "tree.json").write_text("{}")
    (repo / ".muninn" / "mycelium.db").write_bytes(b"")


def test_bootstrapped_repo_returns_when_complete(tmp_path):
    """A .muninn/ with BOTH tree.json AND mycelium.db is accepted."""
    from engine.core.repo_discovery import find_bootstrapped_repo
    repo = tmp_path / "myrepo"
    _make_bootstrapped(repo)
    file_in_repo = repo / "src" / "main.go"
    file_in_repo.parent.mkdir()
    file_in_repo.write_text("package main\n")
    assert find_bootstrapped_repo(file_in_repo) == repo.resolve()


def test_bootstrapped_repo_skips_partial_muninn(tmp_path):
    """The 2026-05-18 sandbox drift: /tmp/btree-only/.muninn/ has only
    mycelium.db (from `muninn-mem scan`), no tree. find_bootstrapped_repo
    must walk PAST it and find the real repo upstream.
    """
    from engine.core.repo_discovery import find_bootstrapped_repo
    # Outer = real bootstrapped repo
    real = tmp_path / "real-repo"
    _make_bootstrapped(real)
    # Inner = a scan target that scan_repo decorated with a partial .muninn/
    scan_target = real / "subdir" / "btree-only"
    scan_target.mkdir(parents=True)
    (scan_target / ".muninn").mkdir()
    (scan_target / ".muninn" / "mycelium.db").write_bytes(b"")  # tree absent
    file_being_reco = scan_target / "btree.go"
    file_being_reco.write_text("package main\n")

    found = find_bootstrapped_repo(file_being_reco)
    assert found == real.resolve(), (
        f"Expected to skip the partial scan-output .muninn/ at "
        f"{scan_target}/.muninn/ and find the outer bootstrapped repo "
        f"{real}, but got {found}."
    )


def test_bootstrapped_repo_returns_none_when_nothing_complete(tmp_path, monkeypatch):
    """If no ancestor has the full pair (tree.json + mycelium.db),
    return None so the caller can surface a clear init+bootstrap message.

    Includes a chdir into tmp_path so the CWD fallback (added 2026-05-18)
    can't accidentally hit the developer's host MUNINN repo and turn this
    None-test into a host-environment-dependent assertion.
    """
    from engine.core.repo_discovery import find_bootstrapped_repo
    # Two partial .muninn/ dirs, none complete
    a = tmp_path / "a"; (a / ".muninn").mkdir(parents=True)
    (a / ".muninn" / "mycelium.db").write_bytes(b"")  # no tree
    b = tmp_path / "b"; (b / ".muninn" / "tree").mkdir(parents=True)
    (b / ".muninn" / "tree" / "tree.json").write_text("{}")  # no mycelium
    file_in_a = a / "x.py"; file_in_a.write_text("pass\n")
    monkeypatch.chdir(tmp_path)  # cwd has nothing bootstrapped

    assert find_bootstrapped_repo(file_in_a) is None


def test_bootstrapped_repo_env_var_overrides(tmp_path, monkeypatch):
    """MUNINN_REPO env wins if it points at a bootstrapped repo."""
    from engine.core.repo_discovery import find_bootstrapped_repo
    forced = tmp_path / "forced"
    _make_bootstrapped(forced)
    monkeypatch.setenv("MUNINN_REPO", str(forced))
    # The walk-up start has its own bootstrapped repo, but env wins
    other = tmp_path / "other"; _make_bootstrapped(other)
    assert find_bootstrapped_repo(other / "deep") == forced


def test_bootstrapped_repo_falls_back_to_cwd_when_start_is_disjoint(
    tmp_path, monkeypatch,
):
    """Sky's 2026-05-18 sandbox case: /reconstruct /tmp/btree-only/x.go.

    File lives in /tmp, bootstrapped repo lives in /home/.../muninn.
    Walk-up from /tmp can NEVER reach /home — different FS branches,
    they only share `/`. The helper must fallback to walking up from
    cwd (where the UI was launched from = the loaded repo typically)
    so the gate accepts.
    """
    from engine.core.repo_discovery import find_bootstrapped_repo

    real = tmp_path / "real-repo"
    _make_bootstrapped(real)
    monkeypatch.chdir(real)  # UI process cwd = the loaded repo

    # File in a totally disjoint location (no bootstrap in its ancestors)
    disjoint = tmp_path / "disjoint" / "btree.go"
    disjoint.parent.mkdir(parents=True)
    disjoint.write_text("package main\n")

    found = find_bootstrapped_repo(disjoint)
    assert found == real.resolve(), (
        f"When walking up from {disjoint} finds nothing, helper should "
        f"fall back to cwd walk-up and find {real}, got {found}"
    )


def test_bootstrapped_repo_env_var_ignored_if_partial(tmp_path, monkeypatch):
    """If MUNINN_REPO points at a NON-bootstrapped dir, the env is
    ignored and we walk up looking for a real bootstrapped repo."""
    from engine.core.repo_discovery import find_bootstrapped_repo
    partial = tmp_path / "partial"
    (partial / ".muninn").mkdir(parents=True)  # no tree, no mycelium
    monkeypatch.setenv("MUNINN_REPO", str(partial))
    real = tmp_path / "real"
    _make_bootstrapped(real)
    file_in_real = real / "x.py"; file_in_real.write_text("pass\n")
    assert find_bootstrapped_repo(file_in_real) == real.resolve()
