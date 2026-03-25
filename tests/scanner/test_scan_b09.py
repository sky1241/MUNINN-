"""
B-SCAN-09: Merger + Dedup — Tests
==================================
Validates merging logic, deduplication, confidence assignment,
severity ordering, degraded mode (LLM=None), and summary stats.
"""
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.merger import (
    MergedFinding,
    merge_findings,
    summary,
    _normalize_llm,
    _normalize_regex,
    _normalize_ast,
    _assign_confidence,
    _dedup,
    _lines_match,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixtures — sample findings from each source
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_regex(file="app.py", line=10, pattern_id="SQLI-001",
                cwe="CWE-89", severity="HIGH"):
    return {
        "file": file, "line": line, "pattern_id": pattern_id,
        "cwe": cwe, "severity": severity, "snippet": "SELECT * FROM ...",
        "source": "regex",
    }


def _make_llm(file="app.py", line=10, type_="SQLI-001",
              severity="HIGH", fix="Use parameterized queries"):
    return {
        "file": file, "line": line, "type": type_,
        "severity": severity, "source": "llm", "fix": fix, "cwe": "CWE-89",
    }


def _make_ast(file="app.py", line=10, pattern_id="SQLI-001",
              severity="HIGH", verdict="confirmed", reason="string format"):
    return {
        "file": file, "line": line, "pattern_id": pattern_id,
        "original_severity": severity, "verdict": verdict,
        "reason": reason, "source": "ast",
    }


class TestBSCAN09Merger:
    """Core merger + dedup validation."""

    # --- 1. Regex only (LLM=None) → all "maybe" ---
    def test_regex_only_llm_none(self):
        regex = [_make_regex(), _make_regex(line=20, pattern_id="XSS-001")]
        result = merge_findings(llm_findings=None, regex_findings=regex)
        assert len(result) == 2
        for f in result:
            assert f.confidence == "maybe"
            assert f.sources == ["regex"]

    # --- 2. Regex + AST confirmed → "confirmed" ---
    def test_regex_plus_ast_confirmed(self):
        regex = [_make_regex()]
        ast = [_make_ast(verdict="confirmed")]
        result = merge_findings(regex_findings=regex, ast_verdicts=ast)
        assert len(result) == 1
        assert result[0].confidence == "confirmed"
        assert "regex" in result[0].sources
        assert "ast" in result[0].sources

    # --- 3. Regex + AST rejected → "fp" ---
    def test_regex_plus_ast_rejected(self):
        regex = [_make_regex()]
        ast = [_make_ast(verdict="fp")]
        result = merge_findings(regex_findings=regex, ast_verdicts=ast)
        assert len(result) == 1
        assert result[0].confidence == "fp"

    # --- 4. LLM + regex same finding → "confirmed" ---
    def test_llm_plus_regex_confirmed(self):
        llm = [_make_llm()]
        regex = [_make_regex()]
        result = merge_findings(llm_findings=llm, regex_findings=regex)
        assert len(result) == 1
        assert result[0].confidence == "confirmed"
        assert "llm" in result[0].sources
        assert "regex" in result[0].sources

    # --- 5. All 3 sources → "confirmed" ---
    def test_all_three_sources(self):
        llm = [_make_llm()]
        regex = [_make_regex()]
        ast = [_make_ast(verdict="confirmed")]
        result = merge_findings(llm_findings=llm, regex_findings=regex,
                                ast_verdicts=ast)
        assert len(result) == 1
        assert result[0].confidence == "confirmed"
        assert len(result[0].sources) == 3

    # --- 6. Dedup: same file+line+type from 2 sources → 1 finding ---
    def test_dedup_same_location(self):
        regex = [_make_regex(), _make_regex()]  # exact dupe from same source
        llm = [_make_llm()]
        result = merge_findings(llm_findings=llm, regex_findings=regex)
        # All three normalize to same (file, type, line) group
        assert len(result) == 1
        assert "llm" in result[0].sources
        assert "regex" in result[0].sources

    # --- 7. Different lines → 2 separate findings ---
    def test_different_lines_separate(self):
        regex = [
            _make_regex(line=10),
            _make_regex(line=100),  # far apart
        ]
        result = merge_findings(regex_findings=regex)
        assert len(result) == 2

    # --- 8. Nearby lines (within tolerance) same type → merged ---
    def test_nearby_lines_merged(self):
        regex = [
            _make_regex(line=10),
            _make_regex(line=12),  # within default tolerance=3
        ]
        llm = [_make_llm(line=11)]
        result = merge_findings(llm_findings=llm, regex_findings=regex)
        assert len(result) == 1
        assert result[0].line == 10  # min line
        assert result[0].confidence == "confirmed"

    # --- 9. Empty inputs → empty output ---
    def test_empty_inputs(self):
        assert merge_findings() == []
        assert merge_findings(None, None, None) == []
        assert merge_findings(llm_findings=[], regex_findings=[], ast_verdicts=[]) == []

    # --- 10. Severity ordering: CRIT before HIGH before MED ---
    def test_severity_ordering(self):
        regex = [
            _make_regex(line=10, severity="MED", pattern_id="A"),
            _make_regex(line=20, severity="CRIT", pattern_id="B"),
            _make_regex(line=30, severity="HIGH", pattern_id="C"),
        ]
        result = merge_findings(regex_findings=regex)
        assert result[0].severity == "CRIT"
        assert result[1].severity == "HIGH"
        assert result[2].severity == "MED"

    # --- 11. Confidence ordering within same severity ---
    def test_confidence_ordering(self):
        regex_a = [_make_regex(line=10, pattern_id="A")]
        regex_b = [_make_regex(line=20, pattern_id="B")]
        llm_b = [_make_llm(line=20, type_="B")]
        # A = maybe (regex only), B = confirmed (regex+llm)
        result = merge_findings(
            llm_findings=llm_b,
            regex_findings=regex_a + regex_b,
        )
        assert len(result) == 2
        assert result[0].confidence == "confirmed"  # B first
        assert result[1].confidence == "maybe"       # A second

    # --- 12. Summary counts correct ---
    def test_summary_counts(self):
        regex = [
            _make_regex(line=10, severity="CRIT"),
            _make_regex(line=20, severity="HIGH", pattern_id="XSS-001"),
        ]
        llm = [_make_llm(line=10)]
        result = merge_findings(llm_findings=llm, regex_findings=regex)
        s = summary(result)
        assert s["total"] == 2
        assert s["by_severity"]["CRIT"] == 1
        assert s["by_severity"]["HIGH"] == 1
        assert s["by_confidence"]["confirmed"] == 1
        assert s["by_confidence"]["maybe"] == 1
        assert s["by_source"]["regex"] == 2
        assert s["by_source"]["llm"] == 1

    # --- 13. MergedFinding dataclass fields ---
    def test_merged_finding_fields(self):
        f = MergedFinding(
            file="x.py", line=1, type="T", severity="HIGH",
            confidence="maybe", sources=["regex"],
        )
        assert f.file == "x.py"
        assert f.line == 1
        assert f.type == "T"
        assert f.severity == "HIGH"
        assert f.confidence == "maybe"
        assert f.sources == ["regex"]
        assert f.fix == ""
        assert f.cwe == ""
        assert f.blast_radius == []

    # --- 14. line_tolerance parameter works ---
    def test_line_tolerance_parameter(self):
        regex = [
            _make_regex(line=10),
            _make_regex(line=15),  # 5 apart
        ]
        # Default tolerance=3 → separate
        result_default = merge_findings(regex_findings=regex, line_tolerance=3)
        assert len(result_default) == 2

        # Tolerance=5 → merged
        result_wide = merge_findings(regex_findings=regex, line_tolerance=5)
        assert len(result_wide) == 1

    # --- 15. Sources list is deduplicated ---
    def test_sources_deduplicated(self):
        regex = [_make_regex(), _make_regex()]  # two regex matches same location
        result = merge_findings(regex_findings=regex)
        assert len(result) == 1
        assert result[0].sources.count("regex") == 1

    # --- 16. blast_radius defaults to empty ---
    def test_blast_radius_default(self):
        regex = [_make_regex()]
        result = merge_findings(regex_findings=regex)
        assert result[0].blast_radius == []

    # --- 17. fix field preserved from input ---
    def test_fix_preserved(self):
        llm = [_make_llm(fix="Use prepared statements")]
        result = merge_findings(llm_findings=llm)
        assert result[0].fix == "Use prepared statements"

    # --- 18. cwe field preserved from input ---
    def test_cwe_preserved(self):
        regex = [_make_regex(cwe="CWE-89")]
        result = merge_findings(regex_findings=regex)
        assert result[0].cwe == "CWE-89"

    # --- 19. AST false_positive string variant ---
    def test_ast_false_positive_variant(self):
        regex = [_make_regex()]
        ast = [_make_ast(verdict="false_positive")]
        result = merge_findings(regex_findings=regex, ast_verdicts=ast)
        assert result[0].confidence == "fp"

    # --- 20. AST unconfirmed does not affect confidence ---
    def test_ast_unconfirmed_no_effect(self):
        regex = [_make_regex()]
        ast = [_make_ast(verdict="unconfirmed")]
        result = merge_findings(regex_findings=regex, ast_verdicts=ast)
        assert result[0].confidence == "maybe"
        assert result[0].sources == ["regex"]

    # --- 21. _assign_confidence unit ---
    def test_assign_confidence_unit(self):
        assert _assign_confidence(1, False) == "maybe"
        assert _assign_confidence(2, False) == "confirmed"
        assert _assign_confidence(3, False) == "confirmed"
        assert _assign_confidence(1, True) == "fp"
        assert _assign_confidence(2, True) == "fp"

    # --- 22. _lines_match unit ---
    def test_lines_match_unit(self):
        assert _lines_match(10, 10, 3) is True
        assert _lines_match(10, 13, 3) is True
        assert _lines_match(10, 14, 3) is False
        assert _lines_match(10, 7, 3) is True
        assert _lines_match(10, 6, 3) is False

    # --- 23. Mixed severity from different sources picks best ---
    def test_mixed_severity_best_wins(self):
        llm = [_make_llm(severity="CRIT")]
        regex = [_make_regex(severity="HIGH")]
        result = merge_findings(llm_findings=llm, regex_findings=regex)
        assert result[0].severity == "CRIT"

    # --- 24. Multiple different findings on same file ---
    def test_multiple_types_same_file(self):
        regex = [
            _make_regex(line=10, pattern_id="SQLI-001"),
            _make_regex(line=10, pattern_id="XSS-001"),
        ]
        result = merge_findings(regex_findings=regex)
        assert len(result) == 2
        types = {f.type for f in result}
        assert "SQLI-001" in types
        assert "XSS-001" in types


class TestBSCAN09Normalize:
    """Normalization function tests."""

    def test_normalize_llm_none(self):
        assert _normalize_llm(None) == []
        assert _normalize_llm([]) == []

    def test_normalize_regex_none(self):
        assert _normalize_regex(None) == []
        assert _normalize_regex([]) == []

    def test_normalize_ast_none(self):
        assert _normalize_ast(None) == []
        assert _normalize_ast([]) == []

    def test_normalize_llm_dict(self):
        items = _normalize_llm([{"file": "a.py", "line": 5, "type": "T", "severity": "HIGH"}])
        assert len(items) == 1
        assert items[0]["source"] == "llm"
        assert items[0]["type"] == "T"

    def test_normalize_regex_dict(self):
        items = _normalize_regex([_make_regex()])
        assert len(items) == 1
        assert items[0]["source"] == "regex"
        assert items[0]["type"] == "SQLI-001"

    def test_normalize_ast_verdict_field(self):
        items = _normalize_ast([_make_ast(verdict="fp")])
        assert len(items) == 1
        assert items[0]["_verdict"] == "fp"
        assert items[0]["source"] == "ast"
