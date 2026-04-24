"""
Integration tests for BUG 1 (AUTH-HARDCODED case-insensitive) and BUG 2 (propagation pipeline).
Uses 3+ synthetic files with imports to verify end-to-end:
  - AUTH-HARDCODED catches PASSWORD/Api_Key variants
  - Propagation produces non-empty blast_radius
  - Patch plan is populated
  - systemic_loss has a real number
"""
import os
import sys
import re

import pytest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.core.scanner.bible_scraper import _core_bible
from engine.core.scanner.regex_filters import scan_file_content
from engine.core.scanner.propagation import propagate_findings, PropagationResult
from engine.core.scanner.report import generate_report, to_markdown, ScanReport


# ── Helpers ────────────────────────────────────────────────────────

def _bible_dicts():
    """Convert core bible to list of dicts (as scan_file_content expects)."""
    return [e.to_dict() for e in _core_bible()]


# ── Synthetic repo files ──────────────────────────────────────────

CONFIG_PY = '''\
# config.py — hardcoded secrets in various cases
PASSWORD = "SuperSecret123"
Api_Key = "abcdefghijkl"
TOKEN = "mytoken_very_long"
db_secret = "changeme!!!"
'''

AUTH_PY = '''\
# auth.py — imports config
from config import PASSWORD, Api_Key
import hashlib

def check_password(user_input):
    return hashlib.md5(user_input.encode()).hexdigest()
'''

MAIN_PY = '''\
# main.py — imports auth
from auth import check_password
import sqlite3

def search(query):
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + query + "'")
    return cursor.fetchall()
'''


# ── Tests ─────────────────────────────────────────────────────────

class TestBug1CaseInsensitiveAuth:
    """BUG 1: AUTH-HARDCODED must catch PASSWORD, Api_Key, etc."""

    def test_regex_matches_uppercase_password(self):
        bible = _bible_dicts()
        matches = scan_file_content(CONFIG_PY, "python", bible, filename="config.py")
        ids = [m.pattern_id for m in matches]
        assert "AUTH-HARDCODED" in ids, (
            f"AUTH-HARDCODED not found. Matched: {ids}"
        )

    def test_regex_matches_multiple_case_variants(self):
        bible = _bible_dicts()
        matches = scan_file_content(CONFIG_PY, "python", bible, filename="config.py")
        auth_matches = [m for m in matches if m.pattern_id == "AUTH-HARDCODED"]
        # PASSWORD, Api_Key, TOKEN, db_secret — all should match
        assert len(auth_matches) >= 3, (
            f"Expected >=3 AUTH-HARDCODED matches, got {len(auth_matches)}: "
            f"{[m.snippet for m in auth_matches]}"
        )

    def test_raw_regex_case_insensitive(self):
        """Direct regex test for case-insensitive matching."""
        entries = _core_bible()
        auth = [e for e in entries if e.id == "AUTH-HARDCODED"][0]
        pat = auth.regex_per_language["python"]

        assert re.search(pat, 'PASSWORD = "SuperSecret123"'), "Failed on PASSWORD"
        assert re.search(pat, 'Api_Key = "abcdefghijkl"'), "Failed on Api_Key"
        assert re.search(pat, 'TOKEN = "mytoken_very_long"'), "Failed on TOKEN"
        assert re.search(pat, 'password = "changeme!!!"'), "Failed on lowercase password"


class TestBug2PropagationPipeline:
    """BUG 2: Propagation must produce non-empty blast_radius, patch_plan, systemic_loss."""

    @pytest.fixture
    def graph(self):
        """config.py -> auth.py -> main.py dependency graph."""
        return {
            "config.py": ["auth.py"],
            "auth.py": ["main.py"],
            "main.py": [],
        }

    @pytest.fixture
    def file_metrics(self):
        return {
            "config.py": {"loc": 5, "temperature": 0.8, "degree": 1},
            "auth.py": {"loc": 10, "temperature": 0.5, "degree": 2},
            "main.py": {"loc": 12, "temperature": 0.3, "degree": 1},
        }

    @pytest.fixture
    def findings(self):
        return [
            {"id": "F-0", "file": "config.py", "severity": "CRIT"},
            {"id": "F-1", "file": "auth.py", "severity": "HIGH"},
            {"id": "F-2", "file": "main.py", "severity": "CRIT"},
        ]

    def test_propagation_returns_blast_radii(self, findings, graph, file_metrics):
        result = propagate_findings(findings, graph, file_metrics)
        assert isinstance(result, PropagationResult)
        assert len(result.blast_radii) == 3

    def test_blast_radius_has_impacted_files(self, findings, graph, file_metrics):
        result = propagate_findings(findings, graph, file_metrics)
        # config.py finding should propagate to auth.py and main.py
        br_config = [br for br in result.blast_radii if br.infected_file == "config.py"][0]
        assert len(br_config.impacted_files) >= 1, (
            f"Expected impacted files from config.py, got: {br_config.impacted_files}"
        )

    def test_systemic_loss_is_real_number(self, findings, graph, file_metrics):
        result = propagate_findings(findings, graph, file_metrics)
        total_loss = sum(br.systemic_loss for br in result.blast_radii)
        assert total_loss > 0.0, f"Total systemic_loss should be > 0, got {total_loss}"

    def test_patch_order_populated(self, findings, graph, file_metrics):
        result = propagate_findings(findings, graph, file_metrics)
        assert len(result.patch_order) >= 1, (
            f"patch_order should be non-empty, got: {result.patch_order}"
        )

    def test_report_has_systemic_loss(self, findings, graph, file_metrics):
        """generate_report must surface systemic_loss from propagation."""
        from dataclasses import asdict
        prop_result = propagate_findings(findings, graph, file_metrics)
        prop_dict = asdict(prop_result)

        report = generate_report(
            findings=[
                {"file": "config.py", "line": 2, "type": "AUTH-HARDCODED",
                 "severity": "CRIT", "description": "Hardcoded password"},
                {"file": "auth.py", "line": 6, "type": "AUTH-WEAK-HASH",
                 "severity": "HIGH", "description": "MD5 for passwords"},
                {"file": "main.py", "line": 8, "type": "INJ-SQL",
                 "severity": "CRIT", "description": "SQL injection"},
            ],
            propagation_result=prop_dict,
            graph=graph,
        )

        assert isinstance(report, ScanReport)
        # systemic_loss must be a real number, not "N/A"
        sl = report.epidemio_metrics.get("systemic_loss")
        assert sl != "N/A", f"systemic_loss should not be N/A, got: {report.epidemio_metrics}"
        assert isinstance(sl, (int, float)), f"systemic_loss should be numeric, got: {type(sl)}"
        assert sl > 0, f"systemic_loss should be > 0, got: {sl}"

    def test_report_patch_plan_populated(self, findings, graph, file_metrics):
        """generate_report must extract patch_order as patch_plan."""
        from dataclasses import asdict
        prop_result = propagate_findings(findings, graph, file_metrics)
        prop_dict = asdict(prop_result)

        report = generate_report(
            findings=[
                {"file": "config.py", "line": 2, "type": "AUTH-HARDCODED", "severity": "CRIT"},
            ],
            propagation_result=prop_dict,
        )

        assert len(report.patch_plan) >= 1, (
            f"patch_plan should be non-empty, got: {report.patch_plan}"
        )

    def test_report_blast_radius_injected(self, findings, graph, file_metrics):
        """Findings should have blast_radius injected from propagation."""
        from dataclasses import asdict
        prop_result = propagate_findings(findings, graph, file_metrics)
        prop_dict = asdict(prop_result)

        input_findings = [
            {"file": "config.py", "line": 2, "type": "AUTH-HARDCODED", "severity": "CRIT"},
            {"file": "auth.py", "line": 6, "type": "AUTH-WEAK-HASH", "severity": "HIGH"},
            {"file": "main.py", "line": 8, "type": "INJ-SQL", "severity": "CRIT"},
        ]

        report = generate_report(
            findings=input_findings,
            propagation_result=prop_dict,
            graph=graph,
        )

        # At least one finding should have a non-zero blast_radius
        blast_values = [f.get("blast_radius", 0) for f in report.findings]
        assert any(v > 0 for v in blast_values), (
            f"At least one finding should have blast_radius > 0, got: {blast_values}"
        )

    def test_markdown_has_real_regime_and_lambda(self, findings, graph, file_metrics):
        """Markdown report must show real regime and lambda_c from propagation."""
        from dataclasses import asdict
        prop_result = propagate_findings(findings, graph, file_metrics)
        prop_dict = asdict(prop_result)

        report = generate_report(
            findings=[
                {"file": "config.py", "line": 2, "type": "AUTH-HARDCODED", "severity": "CRIT"},
            ],
            propagation_result=prop_dict,
            graph=graph,
        )

        md = to_markdown(report)
        # Regime and lambda_c must be real values from propagation
        assert "**Regime:** local" in md or "**Regime:** systemic" in md, (
            "Regime should be 'local' or 'systemic', not N/A"
        )
        # systemic_loss in report data must be real
        sl = report.epidemio_metrics.get("systemic_loss")
        assert isinstance(sl, (int, float)), f"systemic_loss should be numeric, got {sl}"
