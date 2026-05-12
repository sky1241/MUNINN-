"""
CHUNK MCP D.4 — Post-install first-run UX.

A user who just ran `pip install muninn-memory` hits two bad UX walls:

1. `muninn` (no subcommand) → cryptic argparse error
   "muninn: error: the following arguments are required: command"

2. `muninn status` in a fresh repo without .muninn/ → silently
   auto-initializes a tree IN site-packages/.muninn/tree (because
   _REPO_PATH falls back to MUNINN_ROOT = package install dir).
   This is a RULE 1 violation (writes to install location).

D.4 fixes both. These tests pin the new behavior.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNINN_CLI = REPO_ROOT / "engine" / "core" / "muninn.py"


def _run_muninn(args, cwd, env=None):
    """Run muninn CLI as subprocess in given cwd. Returns (returncode, stdout, stderr)."""
    env_full = os.environ.copy()
    if env:
        env_full.update(env)
    # Make sure the subprocess sees engine/core/ on path so bare imports resolve
    env_full["PYTHONPATH"] = f"{REPO_ROOT}/engine/core:{env_full.get('PYTHONPATH', '')}"
    r = subprocess.run(
        [sys.executable, str(MUNINN_CLI), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env_full,
        timeout=30,
    )
    return r.returncode, r.stdout, r.stderr


def test_d4_no_args_shows_welcome_not_argparse_error(tmp_path):
    """`muninn` without subcommand → friendly welcome, not cryptic argparse error.

    The current behavior dumps usage + 'error: required arguments command'.
    Post-D.4: print welcome banner with 3 most useful commands + link to docs.
    """
    rc, out, err = _run_muninn([], cwd=tmp_path)
    combined = out + err
    # Must NOT show argparse "required arguments" error
    assert "the following arguments are required" not in combined, (
        f"Bare `muninn` still shows cryptic argparse error:\n{combined}"
    )
    # Must show something welcoming (case-insensitive)
    welcome_markers = ["welcome", "muninn", "init", "doctor"]
    found = [w for w in welcome_markers if w.lower() in combined.lower()]
    assert len(found) >= 3, (
        f"Welcome message should mention muninn + init + doctor. "
        f"Found markers: {found}. Output:\n{combined}"
    )


def test_d4_status_in_empty_repo_doesnt_write_site_packages(tmp_path, monkeypatch):
    """`muninn status` in a fresh repo WITHOUT .muninn/ MUST NOT auto-init
    a tree in the package install dir (site-packages or engine/core/).

    Current bug: when _REPO_PATH is None, falls back to MUNINN_ROOT, which
    triggers init_tree() to write inside the engine package itself. That's
    a RULE 1 violation (package shouldn't write to its install location)
    and would write to /usr/lib/.../site-packages on a system install.
    """
    # Snapshot mtime of the engine package's .muninn/ if it exists, to detect a write.
    package_dir = REPO_ROOT / "engine" / "core"
    package_muninn = package_dir / ".muninn"
    initial_state = package_muninn.exists()
    initial_mtime = package_muninn.stat().st_mtime_ns if initial_state else None

    rc, out, err = _run_muninn(["status"], cwd=tmp_path)

    # The new behavior should refuse to write to the package dir.
    # Check that no new .muninn/ appeared in the engine package dir.
    if not initial_state:
        assert not package_muninn.exists(), (
            f"muninn status created .muninn/ in the engine package dir: "
            f"{package_muninn} — RULE 1 violation."
        )
    else:
        new_mtime = package_muninn.stat().st_mtime_ns
        assert new_mtime == initial_mtime, (
            f"muninn status MODIFIED engine/.muninn/ — should not write to package dir."
        )


def test_d4_status_in_empty_repo_suggests_init(tmp_path):
    """`muninn status` in a fresh repo without .muninn/ should suggest `muninn init`.

    Not crash. Not silent. Not auto-init in package dir. Just helpfully say
    'this dir has no muninn data yet, run muninn init to set it up'.
    """
    rc, out, err = _run_muninn(["status"], cwd=tmp_path)
    combined = out + err
    # Should mention `init` as the next step
    assert "init" in combined.lower(), (
        f"Status in empty repo should mention `muninn init` as next step. Output:\n{combined}"
    )
    # Should not silently print a fake tree from site-packages
    assert "site-packages" not in combined, (
        f"Status leaked site-packages path:\n{combined}"
    )


def test_d4_welcome_mentions_pip_install_check():
    """The welcome banner should tell the user how to verify the install
    (e.g., `muninn doctor` or version check).
    """
    rc, out, err = _run_muninn([], cwd=Path("/tmp"))
    combined = out + err
    # Should mention either `doctor` or `--version` or `1.0.0`
    has_verify_hint = any(
        marker in combined.lower()
        for marker in ("doctor", "--version", "version")
    )
    assert has_verify_hint, (
        f"Welcome should hint at how to verify the install. Output:\n{combined}"
    )
