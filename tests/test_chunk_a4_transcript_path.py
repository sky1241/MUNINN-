"""CHUNK A4 — path validation transcript_path (hook input).

`feed_from_hook` reads transcript_path from stdin JSON. Without
validation, a malicious payload can make Muninn read arbitrary files
(e.g. /etc/passwd) — limited to user permissions, but still defense-in-depth.

Fix: helper `_validate_transcript_path(p)` returning True only if
the path resolves under `~/.claude/projects/`. Caller refuses + exit(1)
with a clear stderr message.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A4
"""
import sys
from pathlib import Path

import pytest

ENGINE_CORE = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def test_validate_refuses_etc_passwd():
    """Validator must refuse /etc/passwd (clear-cut malicious)."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    assert muninn_feed._validate_transcript_path(Path("/etc/passwd")) is False


def test_validate_refuses_tmp_outside():
    """Validator must refuse arbitrary /tmp paths."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    assert muninn_feed._validate_transcript_path(Path("/tmp/evil.jsonl")) is False


def test_validate_refuses_home_outside_claude():
    """Validator must refuse paths in user home but outside .claude/projects/."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    bad = Path.home() / "Documents" / "secret.txt"
    assert muninn_feed._validate_transcript_path(bad) is False


def test_validate_accepts_claude_projects(tmp_path, monkeypatch):
    """Validator must accept paths under ~/.claude/projects/."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    # Use tmp_path as a stand-in for ~/.claude/projects/ via env var
    fake_root = tmp_path / "fake_claude_projects"
    fake_root.mkdir()
    legit = fake_root / "session-abc.jsonl"
    legit.write_text("{}")
    monkeypatch.setattr(muninn_feed, "_TRANSCRIPT_ROOT", fake_root.resolve())
    assert muninn_feed._validate_transcript_path(legit) is True


def test_validate_accepts_subdir_of_projects(tmp_path, monkeypatch):
    """Validator must accept paths in a subdirectory of projects root."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    fake_root = tmp_path / "fake_projects"
    fake_root.mkdir()
    nested = fake_root / "repo-foo" / "session-xyz.jsonl"
    nested.parent.mkdir()
    nested.write_text("{}")
    monkeypatch.setattr(muninn_feed, "_TRANSCRIPT_ROOT", fake_root.resolve())
    assert muninn_feed._validate_transcript_path(nested) is True


def test_validate_refuses_traversal_via_dotdot(tmp_path, monkeypatch):
    """Validator must refuse paths that resolve outside root via ../."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    fake_root = tmp_path / "projects"
    fake_root.mkdir()
    monkeypatch.setattr(muninn_feed, "_TRANSCRIPT_ROOT", fake_root.resolve())
    # Path that contains projects/ but resolves outside via ../
    sneaky = fake_root / ".." / "outside.jsonl"
    (tmp_path / "outside.jsonl").write_text("{}")
    assert muninn_feed._validate_transcript_path(sneaky) is False


def test_validate_accepts_real_claude_path_format(tmp_path, monkeypatch):
    """Sanity: a path in the format Claude Code actually sends must pass."""
    import muninn_feed
    if not hasattr(muninn_feed, "_validate_transcript_path"):
        pytest.skip("_validate_transcript_path not yet implemented")
    # Real Claude format: ~/.claude/projects/<encoded-path>/<uuid>.jsonl
    fake_root = tmp_path / "claude_projects"
    fake_root.mkdir()
    project_dir = fake_root / "-home-user-myrepo"
    project_dir.mkdir()
    transcript = project_dir / "deadbeef-1234-5678-90ab-cdef12345678.jsonl"
    transcript.write_text("{}")
    monkeypatch.setattr(muninn_feed, "_TRANSCRIPT_ROOT", fake_root.resolve())
    assert muninn_feed._validate_transcript_path(transcript) is True
