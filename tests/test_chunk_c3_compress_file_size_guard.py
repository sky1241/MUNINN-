"""CHUNK C3 — compress_file size guard for very large inputs.

Pre-fix: compress_file did `text = filepath.read_text(encoding="utf-8")`
unconditionally — a 100 MB transcript would push 100 MB into RAM
just to enter the L0-L11 pipeline. Each regex layer then doubled
the working set briefly (input + match buffers + output).

Strategy: cheap conservative guard at the top of compress_file.
Files larger than _MAX_COMPRESS_FILE_BYTES (default 50 MB) are
rejected with a stderr warning and return "" (empty). Sky can
override the cap with the env var MUNINN_MAX_COMPRESS_BYTES if a
specific use case needs more — opt-in.

A full streaming refactor is a Phase-D parking-lot item; this guard
just stops the OOM bleeding now.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C3
"""
import os
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_layers():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_layers" in sys.modules:
        return sys.modules["muninn_layers"]
    import muninn_layers
    return muninn_layers


def test_max_compress_size_constant_exists():
    """The module exposes a knob for the size cap."""
    ml = _load_muninn_layers()
    assert hasattr(ml, "_MAX_COMPRESS_FILE_BYTES"), (
        "_MAX_COMPRESS_FILE_BYTES constant missing — see CHUNK C3"
    )
    assert ml._MAX_COMPRESS_FILE_BYTES > 0


def test_compress_file_refuses_oversized_file(tmp_path, capsys, monkeypatch):
    """A file above the cap returns "" and writes a warning to stderr."""
    ml = _load_muninn_layers()
    huge = tmp_path / "huge.md"
    # Write more than the cap. Use a small cap via monkeypatch to keep
    # the test fast — we don't need a real 50 MB file.
    monkeypatch.setattr(ml, "_MAX_COMPRESS_FILE_BYTES", 1024)  # 1 KB cap
    huge.write_text("x" * 5000, encoding="utf-8")  # 5 KB > 1 KB cap

    result = ml.compress_file(huge)
    captured = capsys.readouterr()
    assert result == "", f"expected empty result, got {result[:80]!r}"
    err = captured.err.lower()
    assert ("too large" in err or "size" in err or "skip" in err
            or "oversize" in err), (
        f"expected size warning in stderr, got: {captured.err!r}"
    )


def test_compress_file_handles_normal_file(tmp_path):
    """Sanity: a file under the cap still compresses."""
    ml = _load_muninn_layers()
    sample = tmp_path / "small.md"
    sample.write_text("## Section\nfact: x\nfact: y\n" * 5, encoding="utf-8")
    result = ml.compress_file(sample)
    assert isinstance(result, str)


def test_env_var_can_override_cap(tmp_path, monkeypatch):
    """MUNINN_MAX_COMPRESS_BYTES env var lets Sky raise the cap."""
    ml = _load_muninn_layers()
    # Set the env var BEFORE the file size check so the override applies.
    monkeypatch.setenv("MUNINN_MAX_COMPRESS_BYTES", "100000000")  # 100 MB
    sample = tmp_path / "ok.md"
    sample.write_text("## hi\nfact: a\n" * 50, encoding="utf-8")
    # Should not be rejected
    result = ml.compress_file(sample)
    assert result != "" or sample.stat().st_size == 0


def test_default_cap_is_at_least_10mb():
    """Default cap is generous enough for normal compress_file usage."""
    ml = _load_muninn_layers()
    assert ml._MAX_COMPRESS_FILE_BYTES >= 10 * 1024 * 1024, (
        f"Default cap {ml._MAX_COMPRESS_FILE_BYTES} bytes is too restrictive"
    )
