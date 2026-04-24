"""
B-SCAN-03: Bible Validator — Tests
====================================
Validates that bible compression preserves all CRIT patterns.
Key invariant: 0% loss on CRIT severity.
"""
import json
import pytest
import sys
import os
import re

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.bible_validator import (
    ValidationResult,
    validate_bible,
    validate_all,
    validate_against_code,
    validate_against_code_with_mn,
    _parse_mn_entries,
    _regex_preserved,
)
from engine.core.scanner.bible_compressor import (
    compress_bible_file,
    compress_bible,
    _compress_entry,
)
from engine.core.scanner.bible_scraper import (
    _core_bible,
    BibleEntry,
)

# Path to fixtures
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_bible_json(tmp_path, language="python", entries=None):
    """Helper: create a bible JSON file in tmp_path/bible/."""
    bible_dir = tmp_path / "bible"
    bible_dir.mkdir(parents=True, exist_ok=True)

    if entries is None:
        entries = _default_entries()

    data = {
        "language": language,
        "entries": entries,
        "count": len(entries),
        "version": "0.1.0",
    }

    json_path = bible_dir / f"{language}.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return json_path


def _default_entries():
    """Minimal set of entries covering CRIT, HIGH, MED, LOW."""
    return [
        {
            "id": "INJ-SQL",
            "severity": "CRIT",
            "pattern": "SQL injection via string concatenation/formatting",
            "regex_per_language": {
                "python": r'(?:execute|executemany|cursor\.execute)\s*\(\s*(?:["\'].*?%|f["\']|.*?\.format|.*?\+)',
            },
            "fix": "Use parameterized queries / prepared statements",
            "cwe": "CWE-89",
            "source": "core",
            "languages": [],
        },
        {
            "id": "INJ-CMD",
            "severity": "CRIT",
            "pattern": "OS command injection via user input",
            "regex_per_language": {
                "python": r'(?:subprocess\.(?:call|run|Popen|check_output)|os\.(?:system|popen|exec\w*))\s*\(.*?(?:\+|%|format|f["\'])',
            },
            "fix": "Use allowlist validation, avoid shell=True",
            "cwe": "CWE-78",
            "source": "core",
            "languages": [],
        },
        {
            "id": "AUTH-HARDCODED",
            "severity": "CRIT",
            "pattern": "Hardcoded password or credentials",
            "regex_per_language": {
                "python": r'(?:password|passwd|secret|api_key|token)\s*=\s*["\'][^"\']{4,}["\']',
            },
            "fix": "Use environment variables or secret management",
            "cwe": "CWE-798",
            "source": "core",
            "languages": [],
        },
        {
            "id": "DESER-UNSAFE",
            "severity": "CRIT",
            "pattern": "Unsafe deserialization of untrusted data",
            "regex_per_language": {
                "python": r'(?:pickle\.(?:loads?|Unpickler)|yaml\.(?:load|unsafe_load)\s*\((?!.*?Loader=yaml\.SafeLoader)|marshal\.loads?|shelve\.open)',
            },
            "fix": "Use safe serialization formats (JSON)",
            "cwe": "CWE-502",
            "source": "core",
            "languages": [],
        },
        {
            "id": "AC-PATH-TRAVERSAL",
            "severity": "CRIT",
            "pattern": "Path traversal via user-controlled file path",
            "regex_per_language": {
                "python": r'(?:open|Path|os\.path\.join)\s*\(.*?(?:request|input|args|params|argv)',
            },
            "fix": "Validate and sanitize file paths",
            "cwe": "CWE-22",
            "source": "core",
            "languages": [],
        },
        {
            "id": "INJ-XSS",
            "severity": "HIGH",
            "pattern": "Cross-site scripting via unescaped output",
            "regex_per_language": {
                "python": r'(?:render_template_string|Markup|\.safe|\|safe|innerHTML)',
            },
            "fix": "Use context-aware output encoding",
            "cwe": "CWE-79",
            "source": "core",
            "languages": [],
        },
        {
            "id": "CONF-DEBUG",
            "severity": "MED",
            "pattern": "Debug mode enabled in production",
            "regex_per_language": {
                "python": r'(?:DEBUG\s*=\s*True|app\.debug\s*=\s*True)',
            },
            "fix": "Disable debug mode in production",
            "cwe": "CWE-489",
            "source": "core",
            "languages": [],
        },
        {
            "id": "LOG-DEBUG",
            "severity": "LOW",
            "pattern": "Debug logging in production",
            "regex_per_language": {
                "python": r"logging\.debug",
            },
            "fix": "Remove debug logging",
            "cwe": "CWE-532",
            "source": "core",
            "languages": [],
        },
    ]


def _compress_and_write(tmp_path, json_path):
    """Compress a bible JSON and write the .mn file. Returns .mn path."""
    mn_dir = tmp_path / "bible_mn"
    mn_dir.mkdir(parents=True, exist_ok=True)

    mn_content = compress_bible_file(json_path)
    language = json_path.stem
    mn_path = mn_dir / f"{language}.mn"
    mn_path.write_text(mn_content, encoding="utf-8")
    return mn_path


def _load_fixture(name):
    """Load a fixture file content."""
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestBSCAN03BibleValidator:
    """Core validation tests for B-SCAN-03."""

    # ── _parse_mn_entries ────────────────────────────────────────

    def test_parse_mn_entries_basic(self):
        """Parse a minimal .mn file and extract entries."""
        mn = """# MUNINN|bible|python
## CRIT
INJ-SQL CWE-89 CRIT|SQL injection via string concat|Use parameterized queries
  r/python: (?:execute|cursor\\.execute)\\s*\\(.*?\\+
## HIGH
INJ-XSS CWE-79 HIGH|XSS via unescaped output|Use encoding
  r/python: (?:innerHTML|document\\.write)
"""
        entries = _parse_mn_entries(mn)
        assert "INJ-SQL" in entries
        assert "INJ-XSS" in entries
        assert entries["INJ-SQL"]["severity"] == "CRIT"
        assert entries["INJ-XSS"]["severity"] == "HIGH"
        assert "python" in entries["INJ-SQL"]["regex"]

    def test_parse_mn_entries_empty(self):
        """Empty .mn file yields empty dict."""
        entries = _parse_mn_entries("")
        assert entries == {}

    def test_parse_mn_entries_header_only(self):
        """Header-only .mn file yields empty dict."""
        entries = _parse_mn_entries("# MUNINN|bible|python\n## CRIT\n")
        assert entries == {}

    # ── _regex_preserved ─────────────────────────────────────────

    def test_regex_preserved_exact(self):
        """Exact match regex is preserved."""
        raw = {"python": r"execute\s*\(.*?\+"}
        mn = {"python": r"execute\s*\(.*?\+"}
        assert _regex_preserved(raw, mn) is True

    def test_regex_preserved_missing_lang(self):
        """If the language is missing from .mn, not preserved."""
        raw = {"python": r"execute\s*\(.*?\+"}
        mn = {"go": r"something"}
        assert _regex_preserved(raw, mn) is False

    def test_regex_preserved_empty_raw(self):
        """Empty raw regex = trivially preserved."""
        assert _regex_preserved({}, {}) is True

    def test_regex_preserved_partial(self):
        """At least one language match = preserved."""
        raw = {"python": r"execute\s*\(", "go": r"Exec\("}
        mn = {"python": r"execute\s*\("}
        assert _regex_preserved(raw, mn) is True

    # ── validate_bible ───────────────────────────────────────────

    def test_validate_bible_all_preserved(self, tmp_path):
        """All entries preserved -> passed=True, 0 CRIT lost."""
        json_path = _make_bible_json(tmp_path)
        mn_path = _compress_and_write(tmp_path, json_path)

        result = validate_bible(json_path, mn_path)

        assert result.passed is True
        assert result.crit_lost == []
        assert result.crit_entries == 5  # 5 CRIT entries
        assert result.crit_preserved == 5
        assert result.language == "python"
        assert result.compression_ratio > 0

    def test_validate_bible_crit_lost_fails(self, tmp_path):
        """If a CRIT entry is missing from .mn -> passed=False."""
        json_path = _make_bible_json(tmp_path)

        # Create a truncated .mn that's missing INJ-SQL
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir(parents=True, exist_ok=True)
        mn_path = mn_dir / "python.mn"
        mn_path.write_text("""# MUNINN|bible|python
## CRIT
INJ-CMD CWE-78 CRIT|cmd injection|Use allowlist
  r/python: (?:subprocess|os\\.system)
AUTH-HARDCODED CWE-798 CRIT|Hardcoded creds|Use env vars
  r/python: (?:password|secret)\\s*=\\s*["\']
DESER-UNSAFE CWE-502 CRIT|Unsafe deser|Use JSON
  r/python: pickle\\.loads
AC-PATH-TRAVERSAL CWE-22 CRIT|Path traversal|Sanitize paths
  r/python: (?:open|Path)\\s*\\(.*?request
""", encoding="utf-8")

        result = validate_bible(json_path, mn_path)

        assert result.passed is False
        assert "INJ-SQL" in result.crit_lost

    def test_validate_bible_high_lost_still_passes(self, tmp_path):
        """HIGH loss doesn't fail the validator (only CRIT matters)."""
        entries = _default_entries()
        json_path = _make_bible_json(tmp_path, entries=entries)

        # .mn with all CRITs but missing the HIGH entry
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir(parents=True, exist_ok=True)
        mn_path = mn_dir / "python.mn"

        # Compress normally then strip the entire HIGH section
        mn_content = compress_bible_file(json_path)
        lines = mn_content.splitlines()
        filtered = []
        in_high = False
        for line in lines:
            if line.strip() == "## HIGH":
                in_high = True
                continue
            if in_high and line.strip().startswith("##"):
                in_high = False
            if in_high:
                continue
            filtered.append(line)
        mn_path.write_text("\n".join(filtered), encoding="utf-8")

        result = validate_bible(json_path, mn_path)

        assert result.passed is True  # CRIT all preserved
        assert "INJ-XSS" in result.high_lost

    def test_validate_bible_compression_ratio(self, tmp_path):
        """Compression ratio is computed correctly."""
        json_path = _make_bible_json(tmp_path)
        mn_path = _compress_and_write(tmp_path, json_path)

        result = validate_bible(json_path, mn_path)
        assert result.compression_ratio > 1.0  # JSON is larger than .mn

    # ── validate_all ─────────────────────────────────────────────

    def test_validate_all_multiple_languages(self, tmp_path):
        """Validate across multiple languages."""
        bible_dir = tmp_path / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir(parents=True, exist_ok=True)

        for lang in ["python", "javascript"]:
            json_path = _make_bible_json(tmp_path, language=lang)
            _compress_and_write(tmp_path, json_path)

        results = validate_all(bible_dir, mn_dir)

        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_validate_all_missing_mn(self, tmp_path):
        """Missing .mn file -> all entries counted as lost."""
        bible_dir = tmp_path / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir(parents=True, exist_ok=True)

        _make_bible_json(tmp_path, language="python")
        # Don't create the .mn file

        results = validate_all(bible_dir, mn_dir)
        assert len(results) == 1
        assert results[0].passed is False
        assert len(results[0].crit_lost) == 5

    # ── validate_against_code ────────────────────────────────────

    def test_validate_against_code_finds_vulns(self):
        """Raw regex finds vulnerabilities in synthetic Python fixture."""
        vuln_py = _load_fixture("vuln_python.py")
        entries = _default_entries()
        samples = [("vuln_python.py", vuln_py, "python")]

        results = validate_against_code(entries, samples)

        # INJ-SQL should find the execute() + concatenation
        assert results["INJ-SQL"]["raw_finds"] > 0
        # AUTH-HARDCODED should find password = "..."
        assert results["AUTH-HARDCODED"]["raw_finds"] > 0
        # DESER-UNSAFE should find pickle.loads
        assert results["DESER-UNSAFE"]["raw_finds"] > 0

    def test_validate_against_code_javascript(self):
        """Raw regex finds vulnerabilities in synthetic JS fixture."""
        vuln_js = _load_fixture("vuln_javascript.js")

        js_entries = [
            {
                "id": "INJ-XSS",
                "severity": "HIGH",
                "regex_per_language": {
                    "javascript": r'(?:innerHTML|outerHTML|document\.write|\.html\(|dangerouslySetInnerHTML|v-html)',
                },
            },
            {
                "id": "AUTH-HARDCODED",
                "severity": "CRIT",
                "regex_per_language": {
                    "javascript": r'(?:password|passwd|secret|apiKey|token)\s*[=:]\s*["\'][^"\']{4,}["\']',
                },
            },
        ]
        samples = [("vuln_javascript.js", vuln_js, "javascript")]

        results = validate_against_code(js_entries, samples)
        assert results["INJ-XSS"]["raw_finds"] > 0
        assert results["AUTH-HARDCODED"]["raw_finds"] > 0

    # ── validate_against_code_with_mn ────────────────────────────

    def test_mn_regex_matches_raw_on_code(self, tmp_path):
        """Compressed .mn regex finds same vulns as raw regex on fixtures."""
        json_path = _make_bible_json(tmp_path)
        mn_path = _compress_and_write(tmp_path, json_path)
        mn_content = mn_path.read_text(encoding="utf-8")

        vuln_py = _load_fixture("vuln_python.py")
        entries = _default_entries()
        samples = [("vuln_python.py", vuln_py, "python")]

        results = validate_against_code_with_mn(entries, mn_content, samples)

        # For CRIT entries: .mn finds must equal raw finds (0% loss)
        for eid, data in results.items():
            if data["severity"] == "CRIT":
                assert data["mn_finds"] >= data["raw_finds"], (
                    f"CRIT {eid}: mn_finds={data['mn_finds']} < raw_finds={data['raw_finds']}"
                )

    # ── Core bible full roundtrip ────────────────────────────────

    def test_core_bible_full_roundtrip(self, tmp_path):
        """Full roundtrip: core bible -> JSON -> compress -> validate.
        This is the integration test that proves zero CRIT loss on the real bible."""
        from engine.core.scanner.bible_scraper import _core_bible
        from dataclasses import asdict

        core = _core_bible()
        entries = [e.to_dict() for e in core]

        # Write JSON
        bible_dir = tmp_path / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "language": "universal",
            "entries": entries,
            "count": len(entries),
            "version": "0.1.0",
        }
        json_path = bible_dir / "universal.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Compress
        mn_path = _compress_and_write(tmp_path, json_path)

        # Validate
        result = validate_bible(json_path, mn_path)

        assert result.passed is True, (
            f"CRIT loss in core bible roundtrip: {result.crit_lost}"
        )
        assert result.crit_lost == []
        assert result.crit_entries > 0  # sanity check: there ARE crit entries

    def test_core_bible_crit_count(self):
        """Verify we know how many CRIT entries exist in core bible."""
        core = _core_bible()
        crit_count = sum(1 for e in core if e.severity == "CRIT")
        # Core bible has at least 5 CRIT entries
        assert crit_count >= 5

    # ── ValidationResult dataclass ───────────────────────────────

    def test_validation_result_to_dict(self):
        """ValidationResult serializes to dict."""
        r = ValidationResult(
            language="python",
            total_entries=10,
            crit_entries=3,
            crit_preserved=3,
            crit_lost=[],
            high_preserved=5,
            high_lost=[],
            compression_ratio=2.5,
            passed=True,
        )
        d = r.to_dict()
        assert d["language"] == "python"
        assert d["passed"] is True
        assert d["compression_ratio"] == 2.5

    # ── Edge cases ───────────────────────────────────────────────

    def test_empty_bible(self, tmp_path):
        """Empty bible (no entries) validates as passed."""
        bible_dir = tmp_path / "bible"
        bible_dir.mkdir(parents=True, exist_ok=True)
        mn_dir = tmp_path / "bible_mn"
        mn_dir.mkdir(parents=True, exist_ok=True)

        data = {"language": "empty", "entries": [], "count": 0, "version": "0.1.0"}
        json_path = bible_dir / "empty.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        mn_path = mn_dir / "empty.mn"
        mn_path.write_text("# MUNINN|bible|empty\n", encoding="utf-8")

        result = validate_bible(json_path, mn_path)
        assert result.passed is True
        assert result.crit_entries == 0

    def test_fixture_files_exist(self):
        """All fixture files exist and are non-empty."""
        for name in ["vuln_python.py", "vuln_javascript.js", "vuln_config.yaml"]:
            path = os.path.join(FIXTURES_DIR, name)
            assert os.path.exists(path), f"Missing fixture: {name}"
            assert os.path.getsize(path) > 0, f"Empty fixture: {name}"
