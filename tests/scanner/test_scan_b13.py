"""
B-SCAN-13: Report Generator — Tests
=====================================
Validates report generation, markdown/JSON output, exit codes,
amplification detection, and section rendering.
"""
import json
import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.report import (
    ScanReport,
    generate_report,
    to_markdown,
    to_json,
    compute_exit_code,
    detect_amplified_risks,
    _findings_table,
    _epidemio_section,
    _patch_plan_section,
    _amplification_section,
    _dynamic_imports_section,
)


# ── Fixtures ──────────────────────────────────────────────────────

def _make_finding(file="src/main.py", line=42, type_="SQL-INJ", severity="MED",
                  description="SQL injection via string concat", fix="Use parameterized queries",
                  blast_radius=0.15):
    return {
        "file": file, "line": line, "type": type_, "severity": severity,
        "description": description, "fix": fix, "blast_radius": blast_radius,
    }


def _make_propagation():
    return {
        "infected_files": ["src/a.py", "src/b.py", "src/c.py"],
        "total_files": 100,
        "systemic_loss": 0.35,
        "patch_plan": [
            {"file": "src/a.py", "reduction": 0.20},
            {"file": "src/b.py", "reduction": 0.10},
        ],
    }


def _make_graph_metrics():
    return {
        "lambda_c": 0.12,
        "percolation_pc": 0.25,
        "regime": "systemic",
        "mean_degree": 3.4,
    }


def _make_dynamic_imports():
    return [
        {"file": "src/plugin.py", "line": 10, "pattern_type": "importlib", "language": "python"},
        {"file": "src/loader.py", "line": 5, "pattern_type": "eval", "language": "python"},
    ]


def _make_graph():
    """A -> B -> C -> D -> E (depth 4 from root A)."""
    return {
        "A": ["B"],
        "B": ["C"],
        "C": ["D"],
        "D": ["E"],
    }


# ── Tests ─────────────────────────────────────────────────────────

class TestBSCAN13ReportGenerator:
    """Core report generator validation."""

    # ── generate_report ───────────────────────────────────────────

    def test_generate_report_full_inputs(self):
        """Full inputs produce report with all sections present."""
        findings = [_make_finding(), _make_finding(severity="CRIT", type_="RCE")]
        report = generate_report(
            findings=findings,
            propagation_result=_make_propagation(),
            dynamic_imports=_make_dynamic_imports(),
            graph_metrics=_make_graph_metrics(),
            scan_duration=1.5,
            files_scanned=42,
        )
        assert len(report.findings) == 2
        assert report.epidemio_metrics.get("regime") == "systemic"
        assert len(report.patch_plan) == 2
        assert report.files_scanned == 42
        assert report.scan_duration == 1.5
        assert report.exit_code == 2  # CRIT present

    def test_generate_report_propagation_none(self):
        """Missing propagation → epidemio section says N/A."""
        report = generate_report(findings=[_make_finding()], propagation_result=None)
        assert report.epidemio_metrics.get("status") == "N/A"

    def test_generate_report_no_findings(self):
        """No findings → exit_code 0, no vulnerabilities."""
        report = generate_report(findings=[])
        assert report.exit_code == 0
        assert len(report.findings) == 0

    def test_generate_report_med_findings(self):
        """Only MED findings → exit_code 1."""
        report = generate_report(findings=[_make_finding(severity="MED")])
        assert report.exit_code == 1

    def test_generate_report_crit_findings(self):
        """CRIT findings → exit_code 2."""
        report = generate_report(findings=[_make_finding(severity="CRIT")])
        assert report.exit_code == 2

    # ── to_markdown ───────────────────────────────────────────────

    def test_to_markdown_valid_with_findings(self):
        """Markdown output contains findings table."""
        findings = [_make_finding()]
        report = generate_report(findings=findings, graph_metrics=_make_graph_metrics())
        md = to_markdown(report)
        assert "## Findings" in md
        assert "| File |" in md
        assert "src/main.py" in md

    def test_to_markdown_epidemio_section_header(self):
        """Markdown contains epidemiology section header."""
        report = generate_report(findings=[])
        md = to_markdown(report)
        assert "## Epidemiology" in md

    def test_to_markdown_patch_plan_section(self):
        """Markdown contains patch plan section."""
        report = generate_report(
            findings=[_make_finding()],
            propagation_result=_make_propagation(),
        )
        md = to_markdown(report)
        assert "## Patch Plan" in md
        assert "src/a.py" in md

    def test_to_markdown_no_findings_message(self):
        """No findings → 'No vulnerabilities found' in markdown."""
        report = generate_report(findings=[])
        md = to_markdown(report)
        assert "No vulnerabilities found" in md

    # ── to_json ───────────────────────────────────────────────────

    def test_to_json_valid(self):
        """JSON output is parseable."""
        report = generate_report(findings=[_make_finding()])
        data = json.loads(to_json(report))
        assert isinstance(data, dict)

    def test_to_json_all_fields_present(self):
        """JSON contains all expected top-level fields."""
        report = generate_report(findings=[_make_finding()])
        data = json.loads(to_json(report))
        expected_keys = {
            "timestamp", "files_scanned", "scan_duration", "exit_code",
            "findings", "epidemio_metrics", "patch_plan", "amplified_risks",
            "dynamic_imports", "coverage_flags",
        }
        assert expected_keys.issubset(set(data.keys()))

    # ── compute_exit_code ─────────────────────────────────────────

    def test_exit_code_empty(self):
        """No findings → 0."""
        assert compute_exit_code([]) == 0

    def test_exit_code_med(self):
        """MED → 1."""
        assert compute_exit_code([_make_finding(severity="MED")]) == 1

    def test_exit_code_high(self):
        """HIGH → 1 (non-critical)."""
        assert compute_exit_code([_make_finding(severity="HIGH")]) == 1

    def test_exit_code_crit(self):
        """CRIT → 2."""
        assert compute_exit_code([_make_finding(severity="CRIT")]) == 2

    # ── _findings_table ───────────────────────────────────────────

    def test_findings_table_columns(self):
        """Table has correct column headers."""
        table = _findings_table([_make_finding()])
        assert "| File |" in table
        assert "| Line |" in table
        assert "| Type |" in table
        assert "| Severity |" in table
        assert "| Fix |" in table
        assert "| Blast Radius |" in table

    # ── detect_amplified_risks ────────────────────────────────────

    def test_amplified_low_deep(self):
        """LOW at depth 4 → flagged as amplified."""
        graph = _make_graph()
        findings = [_make_finding(file="E", severity="LOW")]
        result = detect_amplified_risks(findings, graph, depth_threshold=3)
        assert len(result) == 1
        assert result[0]["amplified"] is True
        assert result[0]["depth"] >= 3

    def test_amplified_crit_deep(self):
        """CRIT at depth 4 → NOT flagged (already critical)."""
        graph = _make_graph()
        findings = [_make_finding(file="E", severity="CRIT")]
        result = detect_amplified_risks(findings, graph, depth_threshold=3)
        assert len(result) == 0

    def test_amplified_low_shallow(self):
        """LOW at depth 1 → NOT flagged."""
        graph = _make_graph()
        findings = [_make_finding(file="B", severity="LOW")]
        result = detect_amplified_risks(findings, graph, depth_threshold=3)
        assert len(result) == 0

    # ── ScanReport dataclass ──────────────────────────────────────

    def test_scanreport_fields(self):
        """ScanReport has all expected fields."""
        report = ScanReport()
        assert hasattr(report, "findings")
        assert hasattr(report, "epidemio_metrics")
        assert hasattr(report, "patch_plan")
        assert hasattr(report, "amplified_risks")
        assert hasattr(report, "dynamic_imports")
        assert hasattr(report, "coverage_flags")
        assert hasattr(report, "exit_code")
        assert hasattr(report, "scan_duration")
        assert hasattr(report, "files_scanned")
        assert hasattr(report, "timestamp")

    def test_report_timestamp_iso_format(self):
        """Timestamp is ISO format."""
        report = generate_report(findings=[])
        ts = report.timestamp
        # Should contain date separator and time separator
        assert "T" in ts
        assert ts.endswith("Z")
        # Should be parseable
        from datetime import datetime
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        assert dt.year >= 2026

    # ── dynamic imports section ───────────────────────────────────

    def test_dynamic_imports_warning_present(self):
        """Dynamic imports detected → warning in report."""
        report = generate_report(
            findings=[_make_finding()],
            dynamic_imports=_make_dynamic_imports(),
        )
        md = to_markdown(report)
        assert "Dynamic Import Warnings" in md
        assert "src/plugin.py" in md
        assert report.coverage_flags.get("dynamic_imports_detected") is True

    def test_no_dynamic_imports(self):
        """No dynamic imports → no warning."""
        report = generate_report(findings=[], dynamic_imports=None)
        assert report.coverage_flags.get("dynamic_imports_detected") is False

    # ── Edge cases ────────────────────────────────────────────────

    def test_amplified_risks_no_graph(self):
        """No graph → empty amplified list."""
        result = detect_amplified_risks([_make_finding(severity="LOW")], graph=None)
        assert result == []

    def test_epidemio_with_graph_metrics_only(self):
        """Graph metrics without propagation still produces epidemio section."""
        report = generate_report(
            findings=[_make_finding()],
            graph_metrics=_make_graph_metrics(),
        )
        assert report.epidemio_metrics.get("lambda_c") == 0.12
        assert report.epidemio_metrics.get("regime") == "systemic"
