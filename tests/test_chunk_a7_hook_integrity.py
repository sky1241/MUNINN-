"""CHUNK A7 — hook integrity (sha256sum manifest + perm tightening).

The .claude/hooks/*.py files are auto-executed by Claude Code on every
session. They are world-readable + world-executable (0755) and have no
checksum verification. Any process / script that can write to the home
can swap a hook for a malicious version → code execution next session.

Fix:
- Generate .claude/hooks/hooks.sha256sum (committed) listing the
  expected sha256 of every hook .py.
- Tighten perms from 0755 -> 0750 (owner+group only, no world-read).

Verification: helper `verify_hook_integrity()` returns True iff every
hook on disk matches its checksum entry.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A7
"""
import hashlib
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO / ".claude" / "hooks"
MANIFEST = HOOKS_DIR / "hooks.sha256sum"


def _sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _parse_manifest(manifest_text: str) -> dict[str, str]:
    """Parse `<sha256>  <filename>` lines into {filename: sha256}."""
    out = {}
    for line in manifest_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        sha, fname = parts
        # `sha256sum -c` output has the filename possibly prefixed by a space-asterisk
        fname = fname.lstrip("* ")
        out[fname] = sha
    return out


def test_manifest_exists():
    """A hooks.sha256sum manifest must be present in .claude/hooks/."""
    assert MANIFEST.exists(), (
        f"Missing manifest: {MANIFEST}. Run `cd .claude/hooks && "
        f"sha256sum *.py > hooks.sha256sum` to generate."
    )


def test_manifest_covers_all_hooks():
    """Every *.py file in hooks/ must have an entry in the manifest."""
    if not MANIFEST.exists():
        pytest.skip("manifest not yet generated")
    expected = _parse_manifest(MANIFEST.read_text())
    actual_files = {p.name for p in HOOKS_DIR.glob("*.py")}
    missing = actual_files - set(expected.keys())
    assert not missing, f"Hooks without manifest entry: {sorted(missing)}"


def test_every_hook_matches_its_sha():
    """Each hook on disk must match its sha256 in the manifest."""
    if not MANIFEST.exists():
        pytest.skip("manifest not yet generated")
    expected = _parse_manifest(MANIFEST.read_text())
    mismatches = []
    for fname, expected_sha in expected.items():
        path = HOOKS_DIR / fname
        if not path.exists():
            mismatches.append((fname, "missing on disk"))
            continue
        actual_sha = _sha256_of(path)
        if actual_sha != expected_sha:
            mismatches.append((fname, f"expected {expected_sha[:12]}, got {actual_sha[:12]}"))
    assert not mismatches, f"Hook checksum mismatches:\n  " + "\n  ".join(
        f"{f}: {m}" for f, m in mismatches
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_hooks_perms_no_world_read():
    """Hook files must not be world-readable (perm bit `o+r` cleared)."""
    if not MANIFEST.exists():
        pytest.skip("manifest not yet generated (skip perm check pre-fix)")
    bad = []
    for hook in HOOKS_DIR.glob("*.py"):
        mode = hook.stat().st_mode
        if mode & stat.S_IROTH:
            bad.append((hook.name, oct(mode & 0o777)))
    assert not bad, f"Hooks with world-readable perms: {bad}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_hooks_perms_no_world_execute():
    """Hook files must not be world-executable (perm bit `o+x` cleared)."""
    if not MANIFEST.exists():
        pytest.skip("manifest not yet generated (skip perm check pre-fix)")
    bad = []
    for hook in HOOKS_DIR.glob("*.py"):
        mode = hook.stat().st_mode
        if mode & stat.S_IXOTH:
            bad.append((hook.name, oct(mode & 0o777)))
    assert not bad, f"Hooks with world-executable perms: {bad}"


def test_modified_hook_detected_by_recompute():
    """Sanity: a 1-byte change must produce a different sha256 (regression check)."""
    sample = HOOKS_DIR / "bridge_hook.py"
    original_sha = _sha256_of(sample)
    # Change in memory only — do NOT modify disk
    altered = sample.read_bytes() + b"\n# tamper\n"
    altered_sha = hashlib.sha256(altered).hexdigest()
    assert original_sha != altered_sha
