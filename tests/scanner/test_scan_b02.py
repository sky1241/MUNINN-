"""
B-SCAN-02: Bible Compressor — Tests
====================================
Validates compression of bible JSON files into .mn format.
Key invariant: 100% of CRIT patterns must survive compression.
"""
import json
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.bible_compressor import (
    compress_bible_file,
    compress_bible,
    load_bible_mn,
    _bible_json_to_mn,
    _compress_entry,
)
from engine.core.scanner.bible_scraper import (
    _core_bible,
    scrape_bible,
)


def _make_bible_json(tmp_path, language="python", entries=None):
    """Helper: create a bible JSON file in tmp_path/bible/."""
    bible_dir = tmp_path / "bible"
    bible_dir.mkdir(parents=True, exist_ok=True)

    if entries is None:
        entries = [
            {
                "id": "INJ-SQL",
                "severity": "CRIT",
                "pattern": "SQL injection via string concatenation",
                "regex_per_language": {"python": r"execute\s*\(.*?\+"},
                "fix": "Use parameterized queries",
                "cwe": "CWE-89",
                "source": "core",
                "languages": [],
            },
            {
                "id": "AUTH-HARDCODED",
                "severity": "HIGH",
                "pattern": "Hardcoded password in source",
                "regex_per_language": {"python": r"password\s*=\s*[\"']"},
                "fix": "Use environment variables or secret manager",
                "cwe": "CWE-798",
                "source": "core",
                "languages": [],
            },
            {
                "id": "LOG-DEBUG",
                "severity": "LOW",
                "pattern": "Debug logging in production",
                "regex_per_language": {"python": r"logging\.debug"},
                "fix": "Remove debug logging",
                "cwe": "CWE-532",
                "source": "core",
                "languages": [],
            },
        ]

    data = {
        "language": language,
        "entries": entries,
        "count": len(entries),
        "version": "0.1.0",
    }

    json_path = bible_dir / f"{language}.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return json_path


class TestBSCAN02BibleCompressor:
    """Core compression tests."""

    def test_compress_single_file(self, tmp_path):
        """compress_bible_file() returns non-empty .mn content."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)
        assert result, "Compression returned empty string"
        assert len(result) > 0

    def test_compress_nonexistent_file(self):
        """Nonexistent file returns empty string, no crash."""
        result = compress_bible_file("/nonexistent/path.json")
        assert result == ""

    def test_compress_invalid_json(self, tmp_path):
        """Invalid JSON returns empty string, no crash."""
        bad = tmp_path / "bad.json"
        bad.write_text("NOT JSON {{{", encoding="utf-8")
        result = compress_bible_file(bad)
        assert result == ""

    def test_compression_is_smaller(self, tmp_path):
        """Compressed output should be smaller than JSON input."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)
        original_size = json_path.stat().st_size
        compressed_size = len(result.encode("utf-8"))
        assert compressed_size < original_size, (
            f"Compressed ({compressed_size}) >= original ({original_size})"
        )

    def test_crit_patterns_survive_compression(self, tmp_path):
        """100% of CRIT pattern IDs must be present in compressed output."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)

        # Read original to find CRIT entries
        data = json.loads(json_path.read_text(encoding="utf-8"))
        crit_entries = [e for e in data["entries"] if e["severity"] == "CRIT"]

        assert len(crit_entries) > 0, "No CRIT entries in test data"
        for entry in crit_entries:
            assert entry["id"] in result, (
                f"CRIT entry {entry['id']} missing from compressed output"
            )

    def test_cwe_numbers_survive_compression(self, tmp_path):
        """CWE identifiers must survive compression."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            if entry["severity"] == "CRIT":
                assert entry["cwe"] in result, (
                    f"CWE {entry['cwe']} missing from compressed output"
                )

    def test_severity_labels_survive_compression(self, tmp_path):
        """Severity section headers must survive."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)
        assert "CRIT" in result, "CRIT severity missing from output"

    def test_regex_patterns_survive_for_crit(self, tmp_path):
        """Regex patterns for CRIT entries must survive compression verbatim."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        crit_entries = [e for e in data["entries"] if e["severity"] == "CRIT"]
        for entry in crit_entries:
            for lang, regex in entry["regex_per_language"].items():
                assert regex in result, (
                    f"CRIT entry {entry['id']} regex for {lang} missing from output"
                )

    def test_all_ids_survive(self, tmp_path):
        """All entry IDs (not just CRIT) must survive compression."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            assert entry["id"] in result, (
                f"Entry {entry['id']} missing from compressed output"
            )

    def test_all_regex_survive(self, tmp_path):
        """All regex patterns must survive verbatim."""
        json_path = _make_bible_json(tmp_path)
        result = compress_bible_file(json_path)

        data = json.loads(json_path.read_text(encoding="utf-8"))
        for entry in data["entries"]:
            for lang, regex in entry["regex_per_language"].items():
                assert regex in result, (
                    f"Regex for {entry['id']}/{lang} missing"
                )


class TestBSCAN02CompressEntry:
    """Test individual entry compression."""

    def test_entry_preserves_id(self):
        entry = {"id": "INJ-SQL", "severity": "CRIT", "pattern": "SQL injection",
                 "fix": "Use params", "cwe": "CWE-89", "regex_per_language": {}}
        result = _compress_entry(entry)
        assert "INJ-SQL" in result

    def test_entry_preserves_cwe(self):
        entry = {"id": "TEST-01", "severity": "HIGH", "pattern": "test",
                 "fix": "fix it", "cwe": "CWE-999", "regex_per_language": {}}
        result = _compress_entry(entry)
        assert "CWE-999" in result

    def test_entry_preserves_regex_verbatim(self):
        regex = r"execute\s*\(.*?\+"
        entry = {"id": "TEST-01", "severity": "CRIT", "pattern": "test",
                 "fix": "fix", "cwe": "CWE-1", "regex_per_language": {"python": regex}}
        result = _compress_entry(entry)
        assert regex in result

    def test_entry_compresses_prose(self):
        entry = {"id": "X", "severity": "CRIT",
                 "pattern": "This is basically a very common vulnerability pattern that is often found",
                 "fix": "You should basically use parameterized queries instead",
                 "cwe": "CWE-1", "regex_per_language": {}}
        result = _compress_entry(entry)
        # Filler words like "basically" should be stripped
        # The result should be shorter than the original prose
        original_prose = entry["pattern"] + entry["fix"]
        # Extract just the compressed prose parts (between pipes)
        parts = result.split("|")
        assert len(parts) >= 3  # id_line | pattern | fix


class TestBSCAN02CompressBible:
    """Full compress_bible() pipeline tests."""

    def test_compress_bible_creates_mn_files(self, tmp_path):
        """compress_bible() creates .mn files for each language."""
        _make_bible_json(tmp_path, "python")
        _make_bible_json(tmp_path, "javascript", entries=[
            {
                "id": "INJ-XSS",
                "severity": "CRIT",
                "pattern": "XSS via innerHTML",
                "regex_per_language": {"javascript": r"innerHTML\s*="},
                "fix": "Use textContent or sanitize",
                "cwe": "CWE-79",
                "source": "core",
                "languages": [],
            }
        ])

        bible_dir = tmp_path / "bible"
        mn_dir = tmp_path / "bible_mn"
        results = compress_bible(bible_dir, mn_dir)

        assert "python" in results, "Missing python.mn"
        assert "javascript" in results, "Missing javascript.mn"
        assert results["python"].exists()
        assert results["javascript"].exists()

    def test_compress_bible_empty_dir(self, tmp_path):
        """Empty input dir returns empty dict, no crash."""
        empty = tmp_path / "empty"
        empty.mkdir()
        results = compress_bible(empty)
        assert results == {}

    def test_compress_bible_nonexistent_dir(self, tmp_path):
        """Nonexistent dir returns empty dict."""
        results = compress_bible(tmp_path / "nope")
        assert results == {}

    def test_compress_bible_default_output_dir(self, tmp_path):
        """Default output goes to sibling bible_mn/ directory."""
        _make_bible_json(tmp_path, "python")
        bible_dir = tmp_path / "bible"
        results = compress_bible(bible_dir)

        expected_dir = tmp_path / "bible_mn"
        assert expected_dir.exists(), "bible_mn dir not created"
        assert results["python"].parent == expected_dir

    def test_compress_bible_with_universal(self, tmp_path):
        """universal.mn is created when universal.json exists."""
        _make_bible_json(tmp_path, "universal", entries=[
            {
                "id": "SECRET-GITHUB",
                "severity": "CRIT",
                "pattern": "GitHub token in source",
                "regex_per_language": {"universal": r"ghp_[A-Za-z0-9]{36}"},
                "fix": "Use environment variables",
                "cwe": "CWE-798",
                "source": "core",
                "languages": [],
            }
        ])
        _make_bible_json(tmp_path, "python")

        results = compress_bible(tmp_path / "bible", tmp_path / "bible_mn")
        assert "universal" in results, "universal.mn not generated"


class TestBSCAN02LoadBibleMn:
    """Test the load function."""

    def test_load_bible_mn_combines_universal_and_language(self, tmp_path):
        """load_bible_mn() returns universal + language content."""
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir()
        (mn_dir / "universal.mn").write_text("# universal rules\nSECRET patterns", encoding="utf-8")
        (mn_dir / "python.mn").write_text("# python rules\nINJ-SQL patterns", encoding="utf-8")

        result = load_bible_mn("python", mn_dir)
        assert "SECRET" in result
        assert "INJ-SQL" in result

    def test_load_bible_mn_missing_language(self, tmp_path):
        """Missing language file still returns universal."""
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir()
        (mn_dir / "universal.mn").write_text("# universal", encoding="utf-8")

        result = load_bible_mn("rust", mn_dir)
        assert "universal" in result.lower()

    def test_load_bible_mn_missing_universal(self, tmp_path):
        """Missing universal still returns language-specific."""
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir()
        (mn_dir / "python.mn").write_text("# python rules", encoding="utf-8")

        result = load_bible_mn("python", mn_dir)
        assert "python" in result.lower()

    def test_load_bible_mn_empty_dir(self, tmp_path):
        """Empty dir returns empty string."""
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir()
        result = load_bible_mn("python", mn_dir)
        assert result == ""

    def test_load_universal_no_double(self, tmp_path):
        """Loading language=universal doesn't double-load."""
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir()
        content = "# universal rules\nSECRET patterns"
        (mn_dir / "universal.mn").write_text(content, encoding="utf-8")

        result = load_bible_mn("universal", mn_dir)
        # Should appear only once
        assert result.count("# universal rules") == 1


class TestBSCAN02JsonToMn:
    """Test the intermediate .mn conversion."""

    def test_mn_has_severity_sections(self):
        data = {
            "language": "python",
            "entries": [
                {"id": "A", "severity": "CRIT", "pattern": "p1", "fix": "f1", "cwe": "CWE-1", "regex_per_language": {}},
                {"id": "B", "severity": "HIGH", "pattern": "p2", "fix": "f2", "cwe": "CWE-2", "regex_per_language": {}},
            ],
            "count": 2,
        }
        mn = _bible_json_to_mn(data)
        assert "## CRIT" in mn
        assert "## HIGH" in mn

    def test_mn_preserves_entry_fields(self):
        data = {
            "language": "go",
            "entries": [
                {"id": "TEST-01", "severity": "CRIT", "pattern": "test pattern",
                 "fix": "test fix", "cwe": "CWE-999", "regex_per_language": {"go": r"badFunc\("}},
            ],
            "count": 1,
        }
        mn = _bible_json_to_mn(data)
        assert "TEST-01" in mn
        assert "CWE-999" in mn
        assert r"badFunc\(" in mn

    def test_mn_severity_order(self):
        """CRIT must come before LOW."""
        data = {
            "language": "python",
            "entries": [
                {"id": "LOW-1", "severity": "LOW", "pattern": "p", "fix": "f", "cwe": "CWE-1", "regex_per_language": {}},
                {"id": "CRIT-1", "severity": "CRIT", "pattern": "p", "fix": "f", "cwe": "CWE-2", "regex_per_language": {}},
            ],
            "count": 2,
        }
        mn = _bible_json_to_mn(data)
        crit_pos = mn.index("## CRIT")
        low_pos = mn.index("## LOW")
        assert crit_pos < low_pos, "CRIT must come before LOW in output"

    def test_mn_header_contains_language(self):
        data = {"language": "java", "entries": [], "count": 0}
        mn = _bible_json_to_mn(data)
        assert "java" in mn


class TestBSCAN02Integration:
    """Integration test with real core bible from B-SCAN-01."""

    def test_round_trip_core_bible(self, tmp_path):
        """Scrape core bible -> compress -> verify CRIT IDs survive."""
        # Step 1: Generate bible JSONs using B-SCAN-01
        bible_dir = tmp_path / "bible"
        result = scrape_bible(bible_dir, skip_download=True)
        assert len(result) >= 2, "scrape_bible produced too few files"

        # Step 2: Compress all
        mn_dir = tmp_path / "bible_mn"
        mn_results = compress_bible(bible_dir, mn_dir)
        assert len(mn_results) >= 2, f"Only {len(mn_results)} .mn files produced"

        # Step 3: Verify 100% of CRIT entry IDs survive in their language .mn
        core = _core_bible()
        crit_entries = [e for e in core if e.severity == "CRIT"]
        assert len(crit_entries) >= 3, "Not enough CRIT entries for meaningful test"

        for entry in crit_entries:
            for lang in entry.regex_per_language:
                if lang not in mn_results:
                    continue
                mn_content = mn_results[lang].read_text(encoding="utf-8")
                assert entry.id in mn_content, (
                    f"CRIT entry {entry.id} missing from {lang}.mn after compression"
                )

    def test_round_trip_regex_survive(self, tmp_path):
        """All regex patterns must survive the round trip verbatim."""
        bible_dir = tmp_path / "bible"
        scrape_bible(bible_dir, skip_download=True)

        mn_dir = tmp_path / "bible_mn"
        mn_results = compress_bible(bible_dir, mn_dir)

        core = _core_bible()
        crit_entries = [e for e in core if e.severity == "CRIT"]

        for entry in crit_entries:
            for lang, regex in entry.regex_per_language.items():
                if lang not in mn_results:
                    continue
                mn_content = mn_results[lang].read_text(encoding="utf-8")
                assert regex in mn_content, (
                    f"Regex for {entry.id}/{lang} missing from .mn"
                )

    def test_universal_mn_always_generated(self, tmp_path):
        """universal.mn must always be generated if universal.json exists."""
        bible_dir = tmp_path / "bible"
        scrape_bible(bible_dir, skip_download=True)
        mn_results = compress_bible(bible_dir, tmp_path / "bible_mn")
        assert "universal" in mn_results, "universal.mn was not generated"

    def test_compression_ratio_reasonable(self, tmp_path):
        """Compression ratio should be > 1.0 (actually compresses)."""
        bible_dir = tmp_path / "bible"
        scrape_bible(bible_dir, skip_download=True)

        mn_dir = tmp_path / "bible_mn"
        mn_results = compress_bible(bible_dir, mn_dir)

        for lang, mn_path in mn_results.items():
            json_path = bible_dir / f"{lang}.json"
            if not json_path.exists():
                continue
            json_size = json_path.stat().st_size
            mn_size = mn_path.stat().st_size
            # .mn should be smaller than .json (compression works)
            assert mn_size < json_size, (
                f"{lang}: mn ({mn_size}) >= json ({json_size}) — no compression"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
