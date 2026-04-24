"""
B-SCAN-08: AST Analyzer — Tests
================================
Validates AST-based false positive elimination and confirmation logic.
Tests cover SQL injection, command injection, XSS, hardcoded secrets,
path traversal, non-Python files, and graceful failure modes.
"""
import pytest
import sys
import os
import textwrap

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.ast_analyzer import (
    ASTVerdict,
    analyze_finding,
    analyze_findings,
    _find_enclosing_function,
    _check_sql_parameterized,
    _check_subprocess_safe,
    _check_is_test_constant,
    _classify_pattern,
    _analyze_python,
)


class TestBSCAN08ASTAnalyzer:
    """Core AST analyzer validation."""

    # ── SQL injection ──────────────────────────────────────────────

    def test_sql_injection_string_format_confirmed(self):
        """SQL injection with string format → confirmed."""
        code = textwrap.dedent("""\
            import sqlite3
            def get_user(user_id):
                conn = sqlite3.connect("db.sqlite")
                cursor = conn.cursor()
                query = f"SELECT * FROM users WHERE id = {user_id}"
                cursor.execute(query)
                return cursor.fetchone()
        """)
        v = analyze_finding("app.py", 6, "SQLI-001", "CRIT", content=code)
        assert v.verdict == "confirmed", f"Expected confirmed, got {v.verdict}: {v.reason}"
        assert v.pattern_id == "SQLI-001"
        assert v.original_severity == "CRIT"
        assert v.source == "ast"

    def test_sql_injection_parameterized_fp(self):
        """SQL injection with parameterized query → fp."""
        code = textwrap.dedent("""\
            import sqlite3
            def get_user(user_id):
                conn = sqlite3.connect("db.sqlite")
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                return cursor.fetchone()
        """)
        v = analyze_finding("app.py", 5, "SQLI-001", "CRIT", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"
        assert "parameterized" in v.reason.lower()

    def test_sql_injection_percent_s_parameterized_fp(self):
        """SQL with %s and tuple params → fp."""
        code = textwrap.dedent("""\
            import psycopg2
            def get_user(user_id):
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return cursor.fetchone()
        """)
        v = analyze_finding("app.py", 4, "SQLI-001", "HIGH", content=code)
        assert v.verdict == "fp"

    # ── Command injection ──────────────────────────────────────────

    def test_command_injection_shell_true_confirmed(self):
        """Command injection with shell=True → confirmed."""
        code = textwrap.dedent("""\
            import subprocess
            def run_command(user_input):
                cmd = f"ls {user_input}"
                subprocess.run(cmd, shell=True)
        """)
        v = analyze_finding("app.py", 4, "CMD-001", "CRIT", content=code)
        assert v.verdict == "confirmed", f"Expected confirmed, got {v.verdict}: {v.reason}"

    def test_command_injection_list_args_fp(self):
        """Command injection with list args (no shell) → fp."""
        code = textwrap.dedent("""\
            import subprocess
            def run_command(path):
                subprocess.run(["ls", path])
        """)
        v = analyze_finding("app.py", 3, "CMD-001", "HIGH", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"
        assert "list" in v.reason.lower()

    def test_command_injection_check_output_list_fp(self):
        """check_output with list args → fp."""
        code = textwrap.dedent("""\
            import subprocess
            def get_files(directory):
                output = subprocess.check_output(["find", directory, "-name", "*.py"])
                return output.decode()
        """)
        v = analyze_finding("app.py", 3, "CMD-EXEC", "HIGH", content=code)
        assert v.verdict == "fp"

    # ── Hardcoded secrets ──────────────────────────────────────────

    def test_hardcoded_password_in_test_file_fp(self):
        """Hardcoded password in test file → fp."""
        code = textwrap.dedent("""\
            def test_login():
                password = "test_password_123"
                assert login("admin", password)
        """)
        v = analyze_finding("tests/test_auth.py", 2, "SECRET-HARDCODED", "CRIT", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"
        assert "test" in v.reason.lower()

    def test_hardcoded_password_production_confirmed(self):
        """Hardcoded password in production code → confirmed."""
        code = textwrap.dedent("""\
            def connect_db():
                password = "super_secret_prod_password"
                return psycopg2.connect(host="db.prod", password=password)
        """)
        v = analyze_finding("config/database.py", 2, "SECRET-HARDCODED", "CRIT", content=code)
        assert v.verdict == "confirmed", f"Expected confirmed, got {v.verdict}: {v.reason}"

    def test_hardcoded_secret_in_mock_function_fp(self):
        """Secret in a mock function → fp."""
        code = textwrap.dedent("""\
            def mock_authenticate():
                api_key = "fake_key_12345"
                return {"token": api_key}
        """)
        v = analyze_finding("utils/helpers.py", 2, "SECRET-HARDCODED", "HIGH", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"

    # ── Path traversal ─────────────────────────────────────────────

    def test_path_traversal_no_validation_confirmed(self):
        """Path traversal with os.path.join + no validation → confirmed."""
        code = textwrap.dedent("""\
            import os
            def read_file(user_path):
                full = os.path.join("/data", user_path)
                with open(full) as f:
                    return f.read()
        """)
        v = analyze_finding("app.py", 3, "PATH-TRAVERSAL", "HIGH", content=code)
        assert v.verdict == "confirmed", f"Expected confirmed, got {v.verdict}: {v.reason}"

    def test_path_traversal_with_realpath_fp(self):
        """Path traversal with realpath validation → fp."""
        code = textwrap.dedent("""\
            import os
            def read_file(user_path):
                safe = os.path.realpath(os.path.join("/data", user_path))
                if not safe.startswith("/data"):
                    raise ValueError("nope")
                with open(safe) as f:
                    return f.read()
        """)
        v = analyze_finding("app.py", 6, "PATH-TRAVERSAL", "HIGH", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"

    # ── XSS ────────────────────────────────────────────────────────

    def test_xss_unsanitized_confirmed(self):
        """XSS with unsanitized output → confirmed."""
        code = textwrap.dedent("""\
            def render_name(name):
                return f"<h1>{name}</h1>"
        """)
        v = analyze_finding("app.py", 2, "XSS-001", "HIGH", content=code)
        assert v.verdict == "confirmed"

    def test_xss_with_escape_fp(self):
        """XSS with html.escape → fp."""
        code = textwrap.dedent("""\
            import html
            def render_name(name):
                safe_name = html.escape(name)
                return f"<h1>{safe_name}</h1>"
        """)
        v = analyze_finding("app.py", 4, "XSS-001", "HIGH", content=code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"

    # ── Non-Python file ────────────────────────────────────────────

    def test_non_python_file_unconfirmed(self):
        """Non-Python file → unconfirmed."""
        js_code = textwrap.dedent("""\
            function getUser(id) {
                const query = "SELECT * FROM users WHERE id = " + id;
                db.execute(query);
            }
        """)
        v = analyze_finding("app.js", 2, "SQLI-001", "CRIT", content=js_code)
        assert v.verdict == "unconfirmed", f"Expected unconfirmed, got {v.verdict}: {v.reason}"

    def test_non_python_with_parameterized_fp(self):
        """Non-Python file with parameterized query → fp via heuristic."""
        js_code = textwrap.dedent("""\
            function getUser(id) {
                const query = "SELECT * FROM users WHERE id = ?";
                db.execute(query, [id]);
            }
        """)
        v = analyze_finding("app.js", 2, "SQLI-001", "CRIT", content=js_code)
        assert v.verdict == "fp", f"Expected fp, got {v.verdict}: {v.reason}"

    # ── Edge cases ─────────────────────────────────────────────────

    def test_unparseable_python_unconfirmed(self):
        """Unparseable Python → unconfirmed (graceful failure)."""
        bad_code = "def broken(\n    this is not valid python !@#$\n"
        v = analyze_finding("broken.py", 1, "SQLI-001", "HIGH", content=bad_code)
        assert v.verdict == "unconfirmed", f"Expected unconfirmed, got {v.verdict}: {v.reason}"
        assert "syntax" in v.reason.lower()

    def test_line_out_of_range_unconfirmed(self):
        """Finding on line that doesn't exist → unconfirmed."""
        code = "x = 1\ny = 2\n"
        v = analyze_finding("small.py", 999, "SECRET-HARDCODED", "HIGH", content=code)
        assert v.verdict == "unconfirmed", f"Expected unconfirmed, got {v.verdict}: {v.reason}"
        assert "out of range" in v.reason.lower()

    def test_analyze_findings_batch(self):
        """Batch analysis returns correct count of verdicts."""
        code = textwrap.dedent("""\
            import subprocess
            def safe_run(path):
                subprocess.run(["ls", path])
            def unsafe_run(cmd):
                subprocess.run(cmd, shell=True)
        """)
        findings = [
            {"file": "app.py", "line": 3, "pattern_id": "CMD-001", "severity": "HIGH", "content": code},
            {"file": "app.py", "line": 5, "pattern_id": "CMD-001", "severity": "CRIT", "content": code},
        ]
        verdicts = analyze_findings(findings)
        assert len(verdicts) == 2
        # First: list args → fp
        assert verdicts[0].verdict == "fp"
        # Second: shell=True → confirmed
        assert verdicts[1].verdict == "confirmed"

    def test_verdict_dataclass_fields(self):
        """ASTVerdict has all required fields."""
        v = ASTVerdict(
            file="test.py", line=1, pattern_id="SQLI-001",
            original_severity="HIGH", verdict="confirmed",
            reason="test reason"
        )
        assert v.file == "test.py"
        assert v.line == 1
        assert v.pattern_id == "SQLI-001"
        assert v.original_severity == "HIGH"
        assert v.verdict == "confirmed"
        assert v.reason == "test reason"
        assert v.source == "ast"

    def test_classify_pattern_sql(self):
        """Pattern classification works for SQL."""
        assert _classify_pattern("SQLI-001") == "sql_injection"
        assert _classify_pattern("SQL-INJECTION") == "sql_injection"

    def test_classify_pattern_cmd(self):
        """Pattern classification works for commands."""
        assert _classify_pattern("CMD-001") == "command_injection"
        assert _classify_pattern("COMMAND-EXEC") == "command_injection"
        assert _classify_pattern("OS-INJECTION") == "command_injection"
        assert _classify_pattern("SUBPROCESS-001") == "command_injection"

    def test_classify_pattern_secret(self):
        """Pattern classification works for secrets."""
        assert _classify_pattern("SECRET-GHP") == "hardcoded_secret"
        assert _classify_pattern("HARDCODED-PASSWORD") == "hardcoded_secret"

    def test_classify_pattern_path(self):
        """Pattern classification works for path traversal."""
        assert _classify_pattern("PATH-TRAVERSAL") == "path_traversal"

    def test_classify_pattern_xss(self):
        """Pattern classification works for XSS."""
        assert _classify_pattern("XSS-001") == "xss"

    def test_unknown_pattern_unconfirmed(self):
        """Unknown pattern type → unconfirmed."""
        code = textwrap.dedent("""\
            def something():
                x = 1
                return x
        """)
        v = analyze_finding("app.py", 2, "UNKNOWN-PATTERN-42", "LOW", content=code)
        assert v.verdict == "unconfirmed"

    def test_file_contents_dict_in_batch(self):
        """analyze_findings uses file_contents dict."""
        code = textwrap.dedent("""\
            def test_func():
                password = "test123"
        """)
        findings = [
            {"file": "tests/test_x.py", "line": 2, "pattern_id": "SECRET-HARDCODED", "severity": "HIGH"},
        ]
        verdicts = analyze_findings(findings, file_contents={"tests/test_x.py": code})
        assert len(verdicts) == 1
        assert verdicts[0].verdict == "fp"

    def test_non_python_no_content_unconfirmed(self):
        """Non-Python file with no content → unconfirmed."""
        v = analyze_finding("app.go", 5, "SQLI-001", "HIGH", content=None)
        # Will try to read from disk (will fail), so unconfirmed
        assert v.verdict == "unconfirmed"
