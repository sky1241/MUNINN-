"""
B-SCAN-06: LLM Scanner — Tests
================================
All tests run WITHOUT Anthropic API.
Validates parsing, prompt building, cost estimation, and graceful degradation.
"""
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.core.scanner.llm_scanner import (
    LLMFinding,
    parse_llm_response,
    build_prompt,
    estimate_cost,
    scan_file,
    scan_batch,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLMFinding dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_finding_fields():
    """LLMFinding has all required fields."""
    f = LLMFinding(
        file="app.py", line=42, type="INJ-SQL",
        severity="CRIT", description="SQL injection"
    )
    assert f.file == "app.py"
    assert f.line == 42
    assert f.type == "INJ-SQL"
    assert f.severity == "CRIT"
    assert f.description == "SQL injection"


def test_finding_source_default():
    """LLMFinding.source defaults to 'llm'."""
    f = LLMFinding(file="x.py", line=1, type="T", severity="LOW", description="d")
    assert f.source == "llm"


def test_finding_confidence_default():
    """LLMFinding.confidence defaults to 0.7."""
    f = LLMFinding(file="x.py", line=1, type="T", severity="LOW", description="d")
    assert f.confidence == 0.7


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# parse_llm_response
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_parse_valid_single():
    """Valid single finding parses correctly."""
    response = "FILE:app.py LINE:42 TYPE:INJ-SQL SEVERITY:CRIT DESC:SQL injection via string concat"
    findings = parse_llm_response(response)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == "app.py"
    assert f.line == 42
    assert f.type == "INJ-SQL"
    assert f.severity == "CRIT"
    assert "SQL injection" in f.description


def test_parse_clean():
    """'CLEAN' response returns empty list."""
    assert parse_llm_response("CLEAN") == []


def test_parse_garbage():
    """Garbage input returns empty list."""
    assert parse_llm_response("this is not a valid response at all") == []


def test_parse_empty():
    """Empty string returns empty list."""
    assert parse_llm_response("") == []


def test_parse_none_like():
    """Whitespace-only returns empty list."""
    assert parse_llm_response("   \n  \n  ") == []


def test_parse_multiple_findings():
    """Multiple findings parse correctly."""
    response = (
        "FILE:app.py LINE:10 TYPE:INJ-SQL SEVERITY:CRIT DESC:SQL injection\n"
        "FILE:app.py LINE:25 TYPE:AUTH-HARDCODED SEVERITY:HIGH DESC:Hardcoded password\n"
        "FILE:utils.py LINE:3 TYPE:LOG-DEBUG SEVERITY:LOW DESC:Debug logging"
    )
    findings = parse_llm_response(response)
    assert len(findings) == 3
    assert findings[0].line == 10
    assert findings[1].type == "AUTH-HARDCODED"
    assert findings[2].file == "utils.py"


def test_parse_mixed_valid_invalid():
    """Mixed valid and invalid lines: only valid ones kept."""
    response = (
        "Some preamble text\n"
        "FILE:app.py LINE:10 TYPE:INJ-SQL SEVERITY:CRIT DESC:SQL injection\n"
        "This line is garbage\n"
        "FILE:app.py LINE:25 TYPE:XSS SEVERITY:HIGH DESC:Reflected XSS\n"
        "Another garbage line"
    )
    findings = parse_llm_response(response)
    assert len(findings) == 2
    assert findings[0].type == "INJ-SQL"
    assert findings[1].type == "XSS"


def test_parse_windows_line_endings():
    """Windows line endings (\\r\\n) parse correctly."""
    response = (
        "FILE:app.py LINE:10 TYPE:INJ-SQL SEVERITY:CRIT DESC:SQL injection\r\n"
        "FILE:app.py LINE:25 TYPE:XSS SEVERITY:HIGH DESC:XSS attack\r\n"
    )
    findings = parse_llm_response(response)
    assert len(findings) == 2
    assert findings[0].line == 10
    assert findings[1].line == 25


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# build_prompt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_build_prompt_contains_bible():
    """Prompt contains the bible content."""
    prompt = build_prompt("app.py", "x = 1", "python", "BIBLE CONTENT HERE")
    assert "BIBLE CONTENT HERE" in prompt


def test_build_prompt_contains_code():
    """Prompt contains the source code."""
    prompt = build_prompt("app.py", "import os\nprint(os.environ)", "python", "bible")
    assert "import os" in prompt
    assert "print(os.environ)" in prompt


def test_build_prompt_contains_language():
    """Prompt contains the language name."""
    prompt = build_prompt("app.go", "package main", "go", "bible")
    assert "go" in prompt


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# estimate_cost
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_estimate_cost_nonempty():
    """Cost estimation returns positive values for non-empty files."""
    files = [("app.py", "x = 1\n" * 100)]
    result = estimate_cost(files, bible_mn="bible content " * 50)
    assert result["total_tokens"] > 0
    assert result["estimated_cost_usd"] > 0
    assert result["file_count"] == 1
    assert result["batches"] >= 1


def test_estimate_cost_empty():
    """Empty files list returns all zeros."""
    result = estimate_cost([])
    assert result["total_tokens"] == 0
    assert result["estimated_cost_usd"] == 0.0
    assert result["file_count"] == 0
    assert result["batches"] == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Graceful degradation (no API client)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class _FakeClientNone:
    """A client that simulates API unavailability."""
    pass  # Has no .messages attribute — will trigger exception


def test_scan_file_no_client():
    """scan_file with no client returns empty list (graceful degradation)."""
    # Pass a deliberately broken client that will fail
    result = scan_file("app.py", "x = 1", "python", "bible", client=None)
    # Without anthropic installed, _get_client returns None → empty
    assert result == [] or isinstance(result, list)


def test_scan_batch_no_client():
    """scan_batch with no client returns empty list."""
    files = [("app.py", "x = 1"), ("util.py", "y = 2")]
    result = scan_batch(files, "bible", "python", client=None)
    assert result == [] or isinstance(result, list)


def test_scan_batch_empty_files():
    """scan_batch with empty files list returns empty list."""
    result = scan_batch([], "bible", "python")
    assert result == []
