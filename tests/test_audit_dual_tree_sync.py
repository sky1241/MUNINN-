"""
AUDIT 2026-04-10 — Anti-regression test for BUG-091 dual-tree sync.

BUG-091 (BUGS.md): engine/core/ and muninn/ are fully duplicated. Modifs
to one tree must be mirrored in the other.

This test does NOT fix BUG-091 (out of scope for the audit). It just
ensures that the modifs we made TODAY remain mirrored. If a future
change breaks the sync on these specific markers, this test catches it.

Each marker is a string that should appear in BOTH the engine/core/ file
and the muninn/ package file. If you need to remove one, remove it from
both AND remove the test entry.
"""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (marker_string, [list of files where it must appear])
SYNC_MARKERS = [
    # Chunk 3 — Anti-Adversa clamp
    ("clamp_chained_commands", ["engine/core/_secrets.py", "muninn/_secrets.py"]),
    ("MAX_CHAINED_COMMANDS", ["engine/core/_secrets.py", "muninn/_secrets.py"]),
    ("from _secrets import clamp_chained_commands",
     ["engine/core/muninn_tree.py", "muninn/muninn_tree.py"]),

    # Chunk 4 — PostToolUseFailure generator
    ("_generate_post_tool_failure_hook",
     ["engine/core/muninn.py", "muninn/_engine.py"]),

    # Chunk 5 — SubagentStart generator (LIGHT mode after chunk 14 fix)
    ("_generate_subagent_start_hook",
     ["engine/core/muninn.py", "muninn/_engine.py"]),
    ("MUNINN LIGHT BOOT",
     ["engine/core/muninn.py", "muninn/_engine.py"]),

    # Chunk 12 — PreToolUse enforcement hooks
    ("_install_pre_tool_use_hooks",
     ["engine/core/muninn.py", "muninn/_engine.py"]),
    ("PreToolUse",
     ["engine/core/muninn.py", "muninn/_engine.py"]),

    # Chunk 15 — Scaling hooks
    ("_install_scaling_hooks",
     ["engine/core/muninn.py", "muninn/_engine.py"]),
    ("_copy_hooks_from_source",
     ["engine/core/muninn.py", "muninn/_engine.py"]),

    # Audit 2026-04-10 — type-check fix in hook templates
    ("if not isinstance(payload, dict)",
     ["engine/core/muninn.py", "muninn/_engine.py"]),
    ("if not isinstance(hook_input, dict)",
     ["engine/core/muninn.py", "muninn/_engine.py"]),
]


@pytest.mark.parametrize("marker,files", SYNC_MARKERS)
def test_marker_present_in_both_trees(marker, files):
    """Each chunk's modifs must be mirrored in engine/core/ AND muninn/."""
    missing = []
    for rel_path in files:
        full = REPO_ROOT / rel_path
        if not full.exists():
            missing.append(f"{rel_path} (file does not exist)")
            continue
        try:
            content = full.read_text(encoding="utf-8")
        except OSError as e:
            missing.append(f"{rel_path} (read error: {e})")
            continue
        if marker not in content:
            missing.append(f"{rel_path} (marker not found)")
    assert not missing, (
        f"BUG-091 sync regression: marker {marker!r} missing in: "
        + ", ".join(missing)
    )


def test_audit_marker_count_sanity():
    """Sanity: we should track at least 10 sync markers."""
    assert len(SYNC_MARKERS) >= 10
