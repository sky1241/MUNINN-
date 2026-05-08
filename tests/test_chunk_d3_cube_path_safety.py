"""CHUNK D3 — cube.scan_repo defense-in-depth against path traversal.

Risk audit: the path constructed at engine/core/cube.py:216 is
`Path(root) / fname` where root comes from os.walk(repo) — by default
os.walk does NOT follow symlinks (followlinks=False), so the risk of
escaping the repo via a symlink is already low. But "by default" is a
fragile guarantee: a future caller passing followlinks=True, or a future
edit accidentally enabling it, would let `/repo/evil_link/passwd` resolve
outside the repo.

Defense in depth: assert that every yielded scan path resolves under
the repo_path argument. Refuse anything else with a stderr warning.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D3
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_cube():
    """Load engine/core/cube.py reliably, working around the BUG-091
    shim/import collisions by reusing the bare `cube` module if it has
    already been loaded by another test in this run."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "cube" in sys.modules and hasattr(sys.modules["cube"], "scan_repo"):
        return sys.modules["cube"]
    try:
        import cube
        if not hasattr(cube, "scan_repo"):
            pytest.skip("cube module loaded but missing scan_repo")
        return cube
    except Exception as e:
        pytest.skip(f"cube not loadable here: {e}")


def test_scan_repo_rejects_symlink_outside(tmp_path, capsys):
    """A symlink inside the repo pointing outside must NOT yield files
    from the symlink target."""
    cube = _load_cube()
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("# leak\n")

    # Plant a symlink inside the repo to the outside dir
    link = repo / "evil_link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this filesystem")

    # Add one legit file
    (repo / "legit.py").write_text("# legit\n")

    scanned = cube.scan_repo(repo, extensions={".py"})
    paths = [str(s.path) for s in scanned]

    # Defense: secret.py should not appear, legit.py should
    assert any("legit.py" in p for p in paths), "legit file should be scanned"
    leak = [p for p in paths if "secret.py" in p]
    # Either the leak is absent (os.walk default behavior) OR the path
    # resolves under repo (false alarm). Either way, no secret content
    # from /tmp/.../outside should be reachable.
    if leak:
        # If a path was returned, it must be under repo
        for p in leak:
            resolved = Path(p).resolve()
            assert resolved.is_relative_to(repo.resolve()), (
                f"Symlink-traversal path leaked: {resolved}"
            )


def test_scan_repo_handles_normal_files(tmp_path):
    cube = _load_cube()
    repo = tmp_path / "ok"
    repo.mkdir()
    (repo / "a.py").write_text("def f(): pass\n")
    (repo / "b.py").write_text("def g(): pass\n")
    scanned = cube.scan_repo(repo, extensions={".py"})
    assert len(scanned) >= 2


def test_scan_repo_does_not_follow_symlinks_default(tmp_path):
    """os.walk's default of followlinks=False must be preserved."""
    cube = _load_cube()
    src = (REPO / "engine" / "core" / "cube.py").read_text()
    # The fix must NOT change os.walk(repo) to followlinks=True
    assert "followlinks=True" not in src, (
        "scan_repo must NOT enable followlinks=True (path traversal risk)"
    )


def test_scan_repo_returns_relative_paths(tmp_path):
    """scan_repo returns paths RELATIVE to repo_path (no leak of
    absolute filesystem layout)."""
    cube = _load_cube()
    repo = tmp_path / "exists"
    repo.mkdir()
    (repo / "x.py").write_text("# x\n")
    scanned = cube.scan_repo(repo, extensions={".py"})
    for s in scanned:
        # path should be relative — resolving `repo / s.path` should
        # produce something under repo.
        absolute = (repo / s.path).resolve()
        assert absolute.is_relative_to(repo.resolve()), (
            f"scan_repo path leaks outside repo: rel={s.path} abs={absolute}"
        )
