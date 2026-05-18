"""Canonical "find the owning repo" helper for Muninn.

The codebase had four conventions before this module (see
docs/SANDBOX_UX_NOTES.md drift #9):

  - Pattern A: `MUNINN_ROOT = Path(__file__).resolve().parent.parent.parent`
    in engine/core/muninn.py:46 — install dir, NOT the loaded repo.
  - Pattern B: function-arg `repo_path: Path` plumbed through call chains.
  - Pattern C: module global `muninn._REPO_PATH` set by hooks via
    `_refresh_tree_paths()`. Hooks honor it; the UI never did.
  - Pattern D: env vars `MUNINN_REPO` / `CLAUDE_PROJECT_DIR`, mostly used
    by ad-hoc scripts.

Five sites in the UI hardcoded Pattern A (`Path(__file__).parents[2]`)
to mean "the loaded repo", which is wrong: when the user scans a
different folder, the UI gate kept checking the muninn install dir's
`.muninn/`. Result: `/reconstruct` rejected with "mycelium.db missing"
even after a clean scan that produced mycelium.db at `<target>/.muninn/`.

`find_owning_repo()` is the single canonical helper. It composes the
four conventions in a defined priority order:

  1. MUNINN_REPO env var (explicit override)
  2. CLAUDE_PROJECT_DIR env var (set by Claude Code in hook context)
  3. Walk up from `start` looking for `.muninn/` (already-bootstrapped repo)
  4. Walk up from `start` looking for `.git/` (any git repo)
  5. None — caller must surface a clear error to the user

The walk-up direction lets a `/reconstruct /any/repo/src/btree.go` find
the correct `.muninn/` regardless of where muninn-ui was installed.

This module is intentionally minimal — no side effects, no logging, no
caching. It is safe to call from a Qt worker thread, from the engine
CLI dispatch, and from MCP handlers without worrying about state leaks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

__all__ = ["find_owning_repo"]


def _candidate_from_env(var: str) -> Optional[Path]:
    val = os.environ.get(var)
    if not val:
        return None
    p = Path(val)
    return p if p.is_dir() else None


def _walk_up_for_marker(start: Path, marker: str) -> Optional[Path]:
    """Walk from `start` up to (and including) the filesystem root,
    returning the first ancestor that contains a child named `marker`.

    If `start` is a file, the search begins at its parent. The marker
    is matched as a direct child of each ancestor (no recursion). The
    function is purely read-only.
    """
    if start.is_file():
        start = start.parent
    here = start.resolve()
    for cand in [here, *here.parents]:
        if (cand / marker).exists():
            return cand
    return None


def find_owning_repo(start: Union[Path, str, None] = None) -> Optional[Path]:
    """Resolve the "owning repo" for a file or directory.

    Resolution order:
      1. ``MUNINN_REPO`` env var, if it points to an existing directory.
      2. ``CLAUDE_PROJECT_DIR`` env var, if it points to an existing dir.
      3. Walk up from ``start`` looking for a ``.muninn/`` directory —
         the strongest signal that the repo has been bootstrapped.
      4. Walk up from ``start`` looking for a ``.git/`` directory.
      5. ``None`` — no convention matched. Callers must handle this
         and surface a clear message to the user (do not silently fall
         back to ``cwd`` or to the install dir, both of which were the
         drift #9 bug).

    Args:
        start: File or directory to walk up from. ``None`` means
            ``Path(os.getcwd())``.

    Returns:
        Path to the owning repo, or ``None`` if no signal was found.

    Example:
        >>> # In a UI command handler:
        >>> repo = find_owning_repo(file_to_reconstruct)
        >>> if repo is None:
        ...     ui.error("File is not inside a Muninn-bootstrapped repo")
        ...     return
        >>> mycelium = Mycelium(repo)
    """
    for var in ("MUNINN_REPO", "CLAUDE_PROJECT_DIR"):
        env_hit = _candidate_from_env(var)
        if env_hit is not None:
            return env_hit

    if start is None:
        start_path = Path(os.getcwd())
    else:
        start_path = Path(start)

    if not start_path.exists():
        return None

    muninn_match = _walk_up_for_marker(start_path, ".muninn")
    if muninn_match is not None:
        return muninn_match

    git_match = _walk_up_for_marker(start_path, ".git")
    return git_match
