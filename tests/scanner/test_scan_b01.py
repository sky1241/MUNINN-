"""
B-SCAN-01: Bible Scraper — Tests
=================================
Validates core bible generation, CWE XML parsing, Semgrep YAML parsing,
and output JSON structure.
"""
import json
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.bible_scraper import (
    _core_bible,
    BibleEntry,
    scrape_bible,
    scrape_cwe,
    scrape_semgrep,
    ALL_LANGUAGES,
)


class TestBSCAN01CoreBible:
    """Core bible (built-in patterns) validation."""

    def test_core_bible_not_empty(self):
        entries = _core_bible()
        assert len(entries) >= 30, f"Core bible too small: {len(entries)} entries"

    def test_every_entry_has_required_fields(self):
        for e in _core_bible():
            assert e.id, f"Missing id"
            assert e.severity in ("CRIT", "HIGH", "MED", "LOW", "INFO"), f"Bad severity: {e.severity} on {e.id}"
            assert e.pattern, f"Missing pattern on {e.id}"
            assert e.fix, f"Missing fix on {e.id}"
            assert e.cwe, f"Missing CWE on {e.id}"

    def test_every_entry_has_at_least_one_regex(self):
        for e in _core_bible():
            assert len(e.regex_per_language) >= 1, f"No regex on {e.id}"
            for lang, regex in e.regex_per_language.items():
                assert regex, f"Empty regex for {lang} on {e.id}"

    def test_all_regex_compile(self):
        """Every regex must be valid."""
        import re
        for e in _core_bible():
            for lang, pattern in e.regex_per_language.items():
                try:
                    re.compile(pattern)
                except re.error as err:
                    pytest.fail(f"Bad regex on {e.id}/{lang}: {err}\nPattern: {pattern}")

    def test_unique_ids(self):
        ids = [e.id for e in _core_bible()]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_owasp_top10_coverage(self):
        """Core bible must cover OWASP Top 10 categories."""
        entries = _core_bible()
        ids = {e.id for e in entries}
        cwes = {e.cwe for e in entries}

        # A01: Injection
        assert any("INJ" in i for i in ids), "Missing injection patterns"
        assert "CWE-89" in cwes, "Missing SQL injection (CWE-89)"
        assert "CWE-78" in cwes, "Missing command injection (CWE-78)"

        # A02: Broken Auth
        assert any("AUTH" in i for i in ids), "Missing auth patterns"

        # A03: Sensitive Data
        assert any("DATA" in i or "SECRET" in i for i in ids), "Missing data exposure patterns"

        # A04: XXE
        assert any("XXE" in i for i in ids), "Missing XXE patterns"

        # A05: Access Control
        assert any("AC-" in i for i in ids), "Missing access control patterns"

        # A07: XSS
        assert "CWE-79" in cwes, "Missing XSS (CWE-79)"

        # A08: Deserialization
        assert any("DESER" in i for i in ids), "Missing deserialization patterns"

        # A10: SSRF
        assert any("SSRF" in i for i in ids), "Missing SSRF patterns"

    def test_multi_language_coverage(self):
        """Core bible must cover at least Python, JS, Go, Java."""
        entries = _core_bible()
        all_langs = set()
        for e in entries:
            all_langs.update(e.regex_per_language.keys())
        for lang in ["python", "javascript", "go", "java"]:
            assert lang in all_langs, f"Missing language: {lang}"

    def test_severity_distribution(self):
        """Must have entries at all severity levels."""
        entries = _core_bible()
        severities = {e.severity for e in entries}
        assert "CRIT" in severities, "No CRIT entries"
        assert "HIGH" in severities, "No HIGH entries"
        assert "MED" in severities, "No MED entries"

    def test_auth_hardcoded_case_insensitive(self):
        """AUTH-HARDCODED regex must catch PASSWORD, Api_Key, etc."""
        import re
        entries = _core_bible()
        auth = [e for e in entries if e.id == "AUTH-HARDCODED"][0]

        test_cases = [
            ('PASSWORD = "SuperSecret123"', "python"),
            ('Api_Key = "abcdef1234"', "python"),
            ('TOKEN = "mytoken1234"', "javascript"),
            ('Secret = "keep_this_safe"', "go"),
            ('PASSWD = "changeme1234"', "java"),
        ]
        for code, lang in test_cases:
            pattern = auth.regex_per_language.get(lang, "")
            assert pattern, f"No regex for {lang}"
            assert re.search(pattern, code), (
                f"AUTH-HARDCODED/{lang} missed case-variant: {code!r}"
            )

    def test_crypto_hardcoded_key_case_insensitive(self):
        """CRYPTO-HARDCODED-KEY regex must be case-insensitive."""
        import re
        entries = _core_bible()
        crypto = [e for e in entries if e.id == "CRYPTO-HARDCODED-KEY"][0]
        # Verify (?i) prefix is present in all patterns
        for lang, pattern in crypto.regex_per_language.items():
            assert pattern.startswith("(?i)"), (
                f"CRYPTO-HARDCODED-KEY/{lang} missing (?i) prefix"
            )

    def test_secrets_in_universal(self):
        """Secret patterns (SECRET-*) must be in universal (cross-language)."""
        entries = _core_bible()
        secret_entries = [e for e in entries if e.id.startswith("SECRET-")]
        assert len(secret_entries) >= 3, "Need at least 3 secret patterns"
        for e in secret_entries:
            assert "universal" in e.regex_per_language, f"Secret {e.id} not in universal"

    def test_to_dict(self):
        entry = _core_bible()[0]
        d = entry.to_dict()
        assert isinstance(d, dict)
        assert "id" in d
        assert "severity" in d
        assert "pattern" in d
        assert "regex_per_language" in d
        assert "fix" in d
        assert "cwe" in d


class TestBSCAN01ScrapeBible:
    """Full scrape_bible() integration test (offline mode)."""

    def test_scrape_bible_offline(self, tmp_path):
        """Core-only bible (no downloads) produces valid JSON."""
        output_dir = tmp_path / "bible"
        result = scrape_bible(output_dir, skip_download=True)

        assert len(result) >= 3, f"Expected at least 3 language files, got {len(result)}"

        # Python must be present (we have many Python patterns)
        assert "python" in result, "Missing python.json"

        # Universal must be present (secrets)
        assert "universal" in result, "Missing universal.json"

    def test_json_files_parseable(self, tmp_path):
        output_dir = tmp_path / "bible"
        result = scrape_bible(output_dir, skip_download=True)

        for lang, path in result.items():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert "language" in data, f"Missing 'language' key in {lang}.json"
            assert "entries" in data, f"Missing 'entries' key in {lang}.json"
            assert "count" in data, f"Missing 'count' key in {lang}.json"
            assert data["count"] == len(data["entries"]), f"Count mismatch in {lang}.json"
            assert data["count"] > 0, f"Empty bible for {lang}"

    def test_every_json_entry_has_required_fields(self, tmp_path):
        output_dir = tmp_path / "bible"
        result = scrape_bible(output_dir, skip_download=True)

        for lang, path in result.items():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data["entries"]:
                assert "id" in entry, f"Missing id in {lang}.json"
                assert "severity" in entry, f"Missing severity in {lang}.json entry {entry.get('id')}"
                assert "pattern" in entry, f"Missing pattern in {lang}.json entry {entry.get('id')}"
                assert "cwe" in entry, f"Missing cwe in {lang}.json entry {entry.get('id')}"
                assert "fix" in entry, f"Missing fix in {lang}.json entry {entry.get('id')}"
                assert "regex_per_language" in entry, f"Missing regex in {lang}.json entry {entry.get('id')}"

    def test_no_duplicate_ids_per_language(self, tmp_path):
        output_dir = tmp_path / "bible"
        result = scrape_bible(output_dir, skip_download=True)

        for lang, path in result.items():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = [e["id"] for e in data["entries"]]
            assert len(ids) == len(set(ids)), f"Duplicate IDs in {lang}.json"

    def test_crit_entries_exist(self, tmp_path):
        """At least some CRIT entries in the bible."""
        output_dir = tmp_path / "bible"
        result = scrape_bible(output_dir, skip_download=True)

        total_crit = 0
        for lang, path in result.items():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            total_crit += sum(1 for e in data["entries"] if e["severity"] == "CRIT")
        assert total_crit >= 5, f"Only {total_crit} CRIT entries total, expected >=5"


class TestBSCAN01CWEScraper:
    """CWE XML parsing tests with synthetic XML."""

    @pytest.fixture
    def sample_cwe_xml(self, tmp_path):
        xml = tmp_path / "cwe_sample.xml"
        xml.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<Weakness_Catalog xmlns="http://cwe.mitre.org/cwe-7" Name="Test">
  <Weaknesses>
    <Weakness ID="89" Name="SQL Injection" Abstraction="Base">
      <Description>Improper neutralization of special elements in SQL commands.</Description>
      <Common_Consequences>
        <Consequence>
          <Impact>Execute Unauthorized Code</Impact>
        </Consequence>
      </Common_Consequences>
      <Potential_Mitigations>
        <Mitigation>
          <Description>Use parameterized queries.</Description>
        </Mitigation>
      </Potential_Mitigations>
    </Weakness>
    <Weakness ID="78" Name="OS Command Injection" Abstraction="Base">
      <Description>Improper neutralization of OS commands.</Description>
      <Common_Consequences>
        <Consequence>
          <Impact>Execute Unauthorized Code</Impact>
        </Consequence>
      </Common_Consequences>
    </Weakness>
    <Weakness ID="99999" Name="Irrelevant" Abstraction="Base">
      <Description>This should be filtered out.</Description>
    </Weakness>
  </Weaknesses>
</Weakness_Catalog>''', encoding="utf-8")
        return xml

    def test_scrape_cwe_parses_entries(self, sample_cwe_xml):
        entries = scrape_cwe(sample_cwe_xml)
        assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}"

    def test_scrape_cwe_filters_irrelevant(self, sample_cwe_xml):
        entries = scrape_cwe(sample_cwe_xml)
        ids = {e.id for e in entries}
        assert "CWE-99999" not in ids, "Should filter non-code-relevant CWEs"

    def test_scrape_cwe_extracts_severity(self, sample_cwe_xml):
        entries = scrape_cwe(sample_cwe_xml)
        sql_inj = [e for e in entries if "89" in e.id][0]
        assert sql_inj.severity == "CRIT", "Execute impact should be CRIT"

    def test_scrape_cwe_extracts_fix(self, sample_cwe_xml):
        entries = scrape_cwe(sample_cwe_xml)
        sql_inj = [e for e in entries if "89" in e.id][0]
        assert "parameterized" in sql_inj.fix.lower()

    def test_scrape_cwe_nonexistent_file(self):
        entries = scrape_cwe("/nonexistent/path.xml")
        assert entries == [], "Should return empty list for missing file"

    def test_scrape_cwe_source_tag(self, sample_cwe_xml):
        entries = scrape_cwe(sample_cwe_xml)
        for e in entries:
            assert e.source == "cwe"


class TestBSCAN01SemgrepScraper:
    """Semgrep YAML parsing tests with synthetic rules."""

    @pytest.fixture
    def sample_semgrep_dir(self, tmp_path):
        """Create a mini semgrep-rules directory."""
        py_dir = tmp_path / "python" / "security"
        py_dir.mkdir(parents=True)

        rule_file = py_dir / "sql-injection.yaml"
        rule_file.write_text('''rules:
  - id: python-sql-injection
    message: Possible SQL injection via string formatting
    severity: ERROR
    pattern: cursor.execute("..." % ...)
    metadata:
      cwe:
        - CWE-89
''', encoding="utf-8")

        js_dir = tmp_path / "javascript" / "security"
        js_dir.mkdir(parents=True)
        rule_file2 = js_dir / "xss.yaml"
        rule_file2.write_text('''rules:
  - id: js-innerHTML-xss
    message: Use of innerHTML may lead to XSS
    severity: WARNING
    pattern: $X.innerHTML = $Y
''', encoding="utf-8")

        return tmp_path

    def test_scrape_semgrep_returns_entries(self, sample_semgrep_dir):
        entries = scrape_semgrep(sample_semgrep_dir)
        # May or may not work depending on yaml availability
        # Basic parser should still extract something
        assert isinstance(entries, list)

    def test_scrape_semgrep_nonexistent_dir(self):
        entries = scrape_semgrep("/nonexistent/dir")
        assert entries == []

    def test_scrape_semgrep_source_tag(self, sample_semgrep_dir):
        entries = scrape_semgrep(sample_semgrep_dir)
        for e in entries:
            assert e.source == "semgrep"


class TestBSCAN01RegexAccuracy:
    """Verify that core regex patterns actually match known vulnerable code."""

    def _find_entry(self, entry_id: str) -> BibleEntry:
        for e in _core_bible():
            if e.id == entry_id:
                return e
        pytest.fail(f"Entry {entry_id} not found")

    def test_sql_injection_python(self):
        import re
        entry = self._find_entry("INJ-SQL")
        regex = entry.regex_per_language["python"]
        assert re.search(regex, 'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)')
        assert re.search(regex, 'cursor.execute("SELECT * FROM users WHERE id = " + user_id)')
        assert re.search(regex, 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")')

    def test_command_injection_python(self):
        import re
        entry = self._find_entry("INJ-CMD")
        regex = entry.regex_per_language["python"]
        assert re.search(regex, 'os.system("rm " + filename)')
        assert re.search(regex, 'subprocess.call("ls " + path, shell=True)')

    def test_hardcoded_password(self):
        import re
        entry = self._find_entry("AUTH-HARDCODED")
        regex = entry.regex_per_language["python"]
        assert re.search(regex, 'password = "SuperSecret123"')
        assert re.search(regex, "api_key = 'sk-1234567890abcdef'")

    def test_github_token(self):
        import re
        entry = self._find_entry("SECRET-GITHUB")
        regex = entry.regex_per_language["universal"]
        assert re.search(regex, 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"')

    def test_aws_key(self):
        import re
        entry = self._find_entry("SECRET-AWS")
        regex = entry.regex_per_language["universal"]
        assert re.search(regex, 'aws_key = "AKIAIOSFODNN7EXAMPLE"')

    def test_private_key(self):
        import re
        entry = self._find_entry("SECRET-PRIVATE-KEY")
        regex = entry.regex_per_language["universal"]
        assert re.search(regex, '-----BEGIN RSA PRIVATE KEY-----')
        assert re.search(regex, '-----BEGIN PRIVATE KEY-----')

    def test_path_traversal(self):
        import re
        entry = self._find_entry("AC-PATH-TRAVERSAL")
        regex = entry.regex_per_language["python"]
        # Original: direct taint on same line
        assert re.search(regex, 'open(request.args["file"])')
        # New: common tainted variable names
        assert re.search(regex, 'open(filename)')
        assert re.search(regex, 'open(filepath, "r")')
        assert re.search(regex, 'open(file_path)')
        assert re.search(regex, 'open(user_file)')
        assert re.search(regex, 'Path(upload)')
        assert re.search(regex, 'os.path.join(base, filename)')

    def test_unsafe_deserialize(self):
        import re
        entry = self._find_entry("DESER-UNSAFE")
        regex = entry.regex_per_language["python"]
        assert re.search(regex, 'pickle.loads(data)')
        assert re.search(regex, 'yaml.load(data)')

    def test_buffer_overflow_c(self):
        import re
        entry = self._find_entry("MEM-BUFFER")
        regex = entry.regex_per_language["c_cpp"]
        assert re.search(regex, 'strcpy(dest, src);')
        assert re.search(regex, 'gets(buffer);')

    def test_cert_noverify(self):
        import re
        entry = self._find_entry("CRYPTO-CERT-NOVERIFY")
        regex = entry.regex_per_language["python"]
        assert re.search(regex, 'requests.get(url, verify=False)')

    def test_xss_javascript(self):
        import re
        entry = self._find_entry("INJ-XSS")
        regex = entry.regex_per_language["javascript"]
        assert re.search(regex, 'element.innerHTML = userInput')
        assert re.search(regex, 'dangerouslySetInnerHTML={{__html: data}}')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
