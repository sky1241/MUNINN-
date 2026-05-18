"""CHUNK 10 follow-up (2026-05-18): scan_repo now grows the mycelium graph.

Before today, `muninn-mem scan <repo>` only wrote a per-target codebook
(`<repo>/.muninn/local.json`). The mycelium graph (`mycelium.db`) was
populated only by `muninn-mem bootstrap`, which had no UI palette
equivalent. User intent was "scan = learn the repo", so observe_text()
calls were added to scan_repo to fill mycelium.db too.

These tests lock the behavior so the next refactor doesn't silently
break it again. The deep audit on 2026-05-18 found zero coverage on
this path — see commit 0fd5a92 for the related /reconstruct gate fix
that surfaced the missing mycelium population.
"""

from pathlib import Path

import pytest


def _make_scannable(repo: Path) -> None:
    """Create a small repo with code + docs that scan_repo will pick up."""
    (repo / "src.py").write_text(
        "import muninn\n"
        "class Mycelium:\n"
        "    def observe_text(self, text):\n"
        "        return text\n"
        "mycelium = Mycelium()\n"
        * 3
    )
    (repo / "README.md").write_text(
        "# Demo repo\n"
        "This repo exercises the mycelium scan growth path.\n"
        "Keywords: mycelium scan compression learning.\n"
        * 3
    )


def test_scan_creates_mycelium_db(tmp_path):
    """scan_repo writes .muninn/mycelium.db on first run."""
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "scan_repo should create mycelium.db"
    assert db.stat().st_size > 0, "mycelium.db should not be empty"


def test_scan_still_writes_local_json(tmp_path):
    """Mycelium growth must not break the existing local.json output."""
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    local = tmp_path / ".muninn" / "local.json"
    assert local.exists(), "scan_repo must still write local.json"
    import json
    data = json.loads(local.read_text(encoding="utf-8"))
    assert data.get("repo_name") == tmp_path.name


def test_scan_mycelium_db_has_concepts(tmp_path):
    """The created mycelium.db must contain at least one concept row.

    Catches the 'creates the file but never observes' regression.
    """
    _make_scannable(tmp_path)
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    import sqlite3
    db = tmp_path / ".muninn" / "mycelium.db"
    conn = sqlite3.connect(db)
    try:
        # The mycelium schema has a `concepts` table (tier3 S1 migration).
        concept_count = conn.execute(
            "SELECT COUNT(*) FROM concepts"
        ).fetchone()[0]
    finally:
        conn.close()
    assert concept_count > 0, (
        f"Expected mycelium to have at least one concept after scan, "
        f"got {concept_count}"
    )


def test_scan_mirror_path_works(tmp_path):
    """The muninn/_engine.py mirror (BUG-091) must also grow mycelium.

    If the mirror was forgotten, importing muninn-mem (which uses
    muninn/_engine.py) would still leave mycelium.db absent.
    """
    _make_scannable(tmp_path)
    from muninn._engine import scan_repo as scan_repo_mirror

    scan_repo_mirror(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "muninn/_engine.py mirror must also create mycelium.db"
    assert db.stat().st_size > 0


def test_scan_picks_up_go_files(tmp_path):
    """Drift #12 regression — `.go` files MUST be scanned.

    Before the 2026-05-18 fix, scan_repo's hardcoded extension list
    omitted .go even though the reconstruction path supports Go via
    gofmt. A `/scan /tmp/dir-with-only-a-go-file` came back with
    files=0 and the mycelium silently never grew. This test pins the
    bug closed.
    """
    (tmp_path / "main.go").write_text(
        "package main\n\nimport \"fmt\"\n\nfunc main() {\n"
        "    fmt.Println(\"hello mycelium\")\n}\n"
    )
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "Mycelium DB must be created from a .go file alone"
    assert db.stat().st_size > 0


def test_extension_constants_align_across_mirror():
    """BUG-091 — the constant sets in engine/core/muninn.py and
    muninn/_engine.py must be byte-identical, else scan/bootstrap/branches
    drift apart between the two entry points.
    """
    from engine.core import muninn as canon
    from muninn import _engine as mirror

    for name in ("SOURCE_CODE_EXTENSIONS", "PROSE_EXTENSIONS",
                 "CONFIG_EXTENSIONS", "MEMORY_EXTENSIONS"):
        a = getattr(canon, name)
        b = getattr(mirror, name)
        assert a == b, f"{name} drifted between canonical and mirror: {a} vs {b}"


def test_scan_picks_up_unknown_languages(tmp_path):
    """Universal scanner: any UTF-8 text file is picked up.

    CHUNK 10 phase 2 — Sky's request "scan n'importe quel langage du
    monde". Tests Zig, Crystal, V, Nim, Elixir — extensions that are
    NOT in SOURCE_CODE_EXTENSIONS but should still be scanned because
    they're plain UTF-8 source code.
    """
    (tmp_path / "main.zig").write_text(
        "const std = @import(\"std\");\npub fn main() void {}\n"
    )
    (tmp_path / "lib.cr").write_text("class Foo\n  def bar; end\nend\n")  # Crystal
    (tmp_path / "app.v").write_text("fn main() { println('hi') }\n")  # V
    (tmp_path / "core.nim").write_text("proc hello() = echo \"hi\"\n")  # Nim
    (tmp_path / "mod.ex").write_text("defmodule Foo do\nend\n")  # Elixir
    from engine.core.muninn import scan_repo

    scan_repo(tmp_path)

    db = tmp_path / ".muninn" / "mycelium.db"
    assert db.exists(), "Universal scanner must pick up Zig/Crystal/V/Nim/Elixir"
    assert db.stat().st_size > 0


def test_scan_skips_noise(tmp_path):
    """Universal scanner must skip .log .json .csv .lock and binaries."""
    (tmp_path / "real.py").write_text("def hello(): pass\n")
    (tmp_path / "app.log").write_text("ERROR: noise\n" * 50)
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n")
    (tmp_path / "package-lock.json").write_text('{"name":"x"}\n')
    (tmp_path / "bin.exe").write_bytes(b"\x7f\x45\x4c\x46" + b"\x00" * 100)

    from engine.core.muninn import is_scannable_text

    assert is_scannable_text(tmp_path / "real.py")
    assert not is_scannable_text(tmp_path / "app.log"), ".log is noise"
    assert not is_scannable_text(tmp_path / "data.csv"), ".csv is data"
    assert not is_scannable_text(tmp_path / "package-lock.json"), "lockfile is data"
    assert not is_scannable_text(tmp_path / "bin.exe"), "binary fails UTF-8 decode"


def test_format_code_no_crash_on_extended_langs(tmp_path):
    """CHUNK 10 phase 3 (2026-05-18): format_code accepts new languages
    (C/C++/Java/Shell/PHP) without crashing. Falls back gracefully to
    normalize_content if the binary is missing.
    """
    from engine.core.cube import format_code

    samples = {
        ".c":    "int main() { return 0; }",
        ".cpp":  "#include <iostream>\nint main(){return 0;}",
        ".h":    "#ifndef FOO\n#define FOO\n#endif",
        ".hpp":  "#pragma once\nclass Foo {};",
        ".cc":   "int main() { return 0; }",
        ".cxx":  "int main() { return 0; }",
        ".cs":   "class Foo { void Bar() {} }",
        ".java": "class Foo { void bar() {} }",
        ".sh":   "#!/bin/bash\necho hello",
        ".bash": "echo $PATH",
        ".php":  "<?php echo \"hi\"; ?>",
        ".zig":  "pub fn main() void {}",   # universal scan, no formatter
    }
    for ext, code in samples.items():
        out = format_code(code, f"sample{ext}")
        assert isinstance(out, str), f"{ext} returned non-str"
        assert out, f"{ext} returned empty"


def test_ext_to_formatter_mapping_includes_new_langs():
    """The _EXT_TO_FORMATTER lookup must list the new extensions —
    used by formatter detection / install messages.
    """
    from engine.core.cube import _EXT_TO_FORMATTER
    expected = {
        ".c": "clang-format", ".cpp": "clang-format", ".h": "clang-format",
        ".cs": "clang-format",
        ".java": "google-java-format",
        ".sh": "shfmt", ".bash": "shfmt",
        ".php": "php-cs-fixer",
    }
    for ext, tool in expected.items():
        assert _EXT_TO_FORMATTER.get(ext) == tool, (
            f"{ext} should map to {tool}, got {_EXT_TO_FORMATTER.get(ext)}"
        )


def test_scan_rejects_oversized_file(tmp_path):
    """Generated/dump files over SCAN_MAX_BYTES are rejected."""
    big = tmp_path / "huge.py"
    big.write_text("# noise\n" * 10000)  # 80KB > 50KB cap
    from engine.core.muninn import is_scannable_text, SCAN_MAX_BYTES
    assert big.stat().st_size > SCAN_MAX_BYTES
    assert not is_scannable_text(big)


def test_extension_constants_cover_cube_corpus():
    """The cube_corpus benchmark files must all be scannable.

    Adding a new test corpus file with an unsupported extension would
    silently drop it from the mycelium graph — catch it here.
    """
    from pathlib import Path
    from engine.core.muninn import (
        SOURCE_CODE_EXTENSIONS, PROSE_EXTENSIONS, CONFIG_EXTENSIONS,
    )
    all_supported = SOURCE_CODE_EXTENSIONS | PROSE_EXTENSIONS | CONFIG_EXTENSIONS

    corpus = Path(__file__).resolve().parent / "cube_corpus"
    if not corpus.exists():
        return  # corpus may not be shipped with installed package
    skipped_intentionally = {".json"}  # JSON benchmark data, not source code
    missing = []
    for f in corpus.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in skipped_intentionally or ext in all_supported:
            continue
        missing.append(f.name)
    assert not missing, (
        f"cube_corpus has files with unsupported extensions: {missing}. "
        f"Add the extension to the appropriate frozenset in "
        f"engine/core/muninn.py (and mirror in muninn/_engine.py)."
    )
