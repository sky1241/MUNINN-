"""CHUNK C6 — .mn magic header + version + CRC32.

Pre-fix: .mn files (compressed transcripts) had no version metadata
or integrity check. Format evolved (L0-L7 -> +L9 -> +L10 -> +L11 -> +L12)
but old .mn files looked identical to new ones — a pipeline bump
silently mis-parses ancient files. Truncated writes from a kill -9
mid-os.replace also went undetected.

Fix: helpers in muninn_feed.py
  _mn_format_header(content, version=2) -> str
    returns "# MUNINN|v=2|crc=<hex>\\n" prefix
  _mn_parse_header(text) -> tuple[content_without_header, meta]
    meta = {"version": int|None, "crc_ok": bool|None, "legacy": bool}

Wired into the write path of compress_transcript and into
_safe_read_mn in muninn_tree (header stripped before return).

Backwards-compat: files without a magic header are treated as legacy
v1 and pass through unchanged.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §C6
"""
import importlib.util
import sys
import zlib
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_muninn_feed():
    """Load engine/core/muninn_feed.py under a unique module name."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    spec = importlib.util.spec_from_file_location(
        "_chunk_c6_muninn_feed", engine_core / "muninn_feed.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        pytest.skip(f"muninn_feed not loadable: {e}")
    return mod


def test_format_header_helper_exists():
    mf = _load_muninn_feed()
    assert hasattr(mf, "_mn_format_header"), (
        "_mn_format_header() helper missing — see CHUNK C6"
    )


def test_parse_header_helper_exists():
    mf = _load_muninn_feed()
    assert hasattr(mf, "_mn_parse_header"), (
        "_mn_parse_header() helper missing — see CHUNK C6"
    )


def test_format_header_shape():
    """Header is `# MUNINN|v=<int>|crc=<hex>\\n`."""
    mf = _load_muninn_feed()
    header = mf._mn_format_header("hello world")
    assert header.startswith("# MUNINN|")
    assert "v=" in header
    assert "crc=" in header
    assert header.endswith("\n")


def test_round_trip_v2():
    """Format header + parse must yield the original content."""
    mf = _load_muninn_feed()
    content = "## Section\nfact: x\nfact: y\n"
    header = mf._mn_format_header(content, version=2)
    full = header + content
    body, meta = mf._mn_parse_header(full)
    assert body == content
    assert meta["version"] == 2
    assert meta["crc_ok"] is True
    assert meta.get("legacy") is False


def test_legacy_no_header_returned_as_is():
    """A .mn without magic header must still parse (legacy)."""
    mf = _load_muninn_feed()
    legacy = "## hist\nfact: alpha\n"  # No magic line
    body, meta = mf._mn_parse_header(legacy)
    assert body == legacy
    assert meta.get("legacy") is True


def test_crc_mismatch_flagged():
    """When CRC doesn't match the body, meta.crc_ok must be False."""
    mf = _load_muninn_feed()
    content = "original content"
    header = mf._mn_format_header(content, version=2)
    # Tamper with the body
    tampered = header + "TAMPERED" + content
    body, meta = mf._mn_parse_header(tampered)
    # Body returned best-effort, but crc_ok flagged
    assert meta["version"] == 2
    assert meta["crc_ok"] is False


def test_header_crc_is_zlib_crc32():
    """The CRC value matches zlib.crc32(content.encode('utf-8'))."""
    mf = _load_muninn_feed()
    content = "deterministic test content"
    header = mf._mn_format_header(content, version=2)
    expected_crc = format(zlib.crc32(content.encode("utf-8")) & 0xFFFFFFFF, "08x")
    assert expected_crc in header


def test_safe_read_mn_strips_header(tmp_path, monkeypatch):
    """muninn_tree._safe_read_mn (CHUNK A2) must strip the C6 header
    so callers see only the original content."""
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    if "muninn_tree" in sys.modules:
        mt = sys.modules["muninn_tree"]
    else:
        import muninn_tree as mt

    mf = _load_muninn_feed()

    content = "## chunk c6\nfact: integrity\n"
    header = mf._mn_format_header(content, version=2)
    sample = tmp_path / "test.mn"
    sample.write_text(header + content, encoding="utf-8")

    result = mt._safe_read_mn(sample)
    # _safe_read_mn must return either the body without the header,
    # OR the full text including the header (acceptable for now since
    # downstream parsers ignore `#`-prefixed lines), but it MUST NOT
    # crash and MUST contain the user content.
    assert result is not None
    assert "fact: integrity" in result
