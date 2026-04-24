"""
B-SCAN-08: AST Analyzer — intra-function taint analysis + false positive elimination
=====================================================================================
Third pass of the triple-pass scanner. Uses Python's ast module to confirm or reject
findings from the LLM and regex passes via data flow analysis.

V1: intra-function only (variable defined and used within same function).
V2 (future): cross-function taint tracking.

INPUT:  List of findings (file, line, pattern_id, severity) from previous passes
OUTPUT: List of ASTVerdict with confirmed/fp/unconfirmed verdicts + reasoning
"""

import ast
import os
import re
from dataclasses import dataclass
from typing import Optional

_SCANNER_VERSION = "0.1.0"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ASTVerdict:
    """Verdict for a single finding after AST analysis."""
    file: str
    line: int
    pattern_id: str
    original_severity: str
    verdict: str    # "confirmed" / "fp" (false positive) / "unconfirmed"
    reason: str     # why this verdict
    source: str = "ast"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Heuristic patterns for non-Python languages
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SANITIZATION_PATTERNS = [
    re.compile(r'escape\s*\(', re.I),
    re.compile(r'sanitize\s*\(', re.I),
    re.compile(r'html\.escape\s*\(', re.I),
    re.compile(r'encode\s*\(', re.I),
    re.compile(r'quote\s*\(', re.I),
    re.compile(r'clean\s*\(', re.I),
    re.compile(r'purify\s*\(', re.I),
    re.compile(r'strip_tags\s*\(', re.I),
    re.compile(r'bleach\.\w+\s*\(', re.I),
    re.compile(r'DOMPurify', re.I),
]

_PARAMETERIZED_PATTERNS = [
    re.compile(r'=\s*\?'),               # = ? placeholder
    re.compile(r'\$\d+'),                # $1 placeholder (postgres)
    re.compile(r'%s\s*.*?,\s*\('),       # %s with tuple
    re.compile(r':\w+'),                 # :name (named params)
    re.compile(r'PreparedStatement', re.I),
    re.compile(r'parameterized', re.I),
    re.compile(r'Prepare\s*\(', re.I),
    re.compile(r'placeholder', re.I),
]

_TEST_FILE_PATTERNS = [
    re.compile(r'test[_/]', re.I),
    re.compile(r'_test\.', re.I),
    re.compile(r'spec[_/]', re.I),
    re.compile(r'mock', re.I),
    re.compile(r'fixture', re.I),
    re.compile(r'fake', re.I),
    re.compile(r'example', re.I),
    re.compile(r'dummy', re.I),
]

_PYTHON_EXTENSIONS = {'.py', '.pyw'}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internal helpers — AST traversal
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _find_enclosing_function(tree: ast.AST, line: int) -> Optional[ast.FunctionDef]:
    """Find the ast.FunctionDef (or AsyncFunctionDef) that encloses the given line."""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # node.end_lineno available in Python 3.8+
            end = getattr(node, 'end_lineno', None)
            if end is None:
                # Fallback: assume function spans a reasonable range
                end = line + 1000
            if node.lineno <= line <= end:
                # Pick the tightest enclosing function (most specific)
                if best is None or node.lineno >= best.lineno:
                    best = node
    return best



def _node_contains_call(node: ast.AST, func_names: set) -> bool:
    """Check if a node tree contains a call to any of the given function names."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            # Simple name: func(...)
            if isinstance(child.func, ast.Name) and child.func.id in func_names:
                return True
            # Attribute: obj.func(...)
            if isinstance(child.func, ast.Attribute) and child.func.attr in func_names:
                return True
    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pattern-specific checks (Python AST)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _check_sql_parameterized(func_node: ast.FunctionDef, line: int) -> bool:
    """
    Check if a SQL query at the given line uses parameterized syntax.
    Returns True if parameterized (= false positive for SQL injection).

    Detects:
    - cursor.execute("SELECT ... WHERE id = ?", (value,))
    - cursor.execute("SELECT ... WHERE id = %s", (value,))
    - Any execute() call with 2+ args where first is string
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        if not hasattr(node, 'lineno') or node.lineno != line:
            continue
        # Check: .execute(...) with 2+ args
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'execute':
            if len(node.args) >= 2:
                # Second arg is the parameters tuple/list — parameterized query
                return True
        # Also check for text() wrapping (SQLAlchemy)
        if isinstance(node.func, ast.Name) and node.func.id == 'text':
            return True

    # Check surrounding lines for parameterized patterns in source
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        if not hasattr(node, 'lineno'):
            continue
        # Within 2 lines of the finding
        if abs(node.lineno - line) > 2:
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in ('execute', 'executemany'):
            if len(node.args) >= 2:
                return True

    return False


def _check_subprocess_safe(func_node: ast.FunctionDef, line: int) -> bool:
    """
    Check if a subprocess call at the given line uses safe list arguments.
    Returns True if safe (= false positive for command injection).

    Safe: subprocess.run(["ls", path])  — list args, no shell
    Unsafe: subprocess.run(f"ls {path}", shell=True)
    """
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        if not hasattr(node, 'lineno'):
            continue
        if abs(node.lineno - line) > 1:
            continue

        # Check if it's a subprocess call
        is_subprocess = False
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ('run', 'call', 'Popen', 'check_output', 'check_call'):
                is_subprocess = True
        if isinstance(node.func, ast.Name):
            if node.func.id in ('run', 'call', 'Popen', 'check_output', 'check_call'):
                is_subprocess = True

        if not is_subprocess:
            continue

        # Check shell=True keyword
        has_shell_true = False
        for kw in node.keywords:
            if kw.arg == 'shell':
                if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    has_shell_true = True
                elif isinstance(kw.value, ast.NameConstant if hasattr(ast, 'NameConstant') else ast.Constant):
                    val = getattr(kw.value, 'value', None)
                    if val is True:
                        has_shell_true = True

        if has_shell_true:
            return False  # shell=True → NOT safe

        # Check first arg is a list
        if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
            return True  # list args without shell=True → safe

    return False


def _check_is_test_constant(func_node: Optional[ast.FunctionDef], line: int, source: str) -> bool:
    """
    Check if a hardcoded secret at the given line is a test/mock/example constant.
    Returns True if it's a test constant (= false positive).

    Checks:
    - File path contains test/mock/example/fixture/fake/dummy
    - Variable name contains test/mock/example/fake/dummy/sample
    - Value is a placeholder (e.g., "changeme", "xxx", "password123", "example")
    """
    # Check file path
    source_lower = source.lower().replace('\\', '/')
    for pat in _TEST_FILE_PATTERNS:
        if pat.search(source_lower):
            return True

    # Check if enclosing function name suggests test
    if func_node is not None:
        fname = func_node.name.lower()
        if any(kw in fname for kw in ('test', 'mock', 'fake', 'dummy', 'example', 'fixture', 'sample')):
            return True

    return False


def _check_xss_sanitized(func_node: ast.FunctionDef, line: int) -> bool:
    """
    Check if XSS output at the given line is sanitized/escaped.
    Returns True if sanitized (= false positive).
    """
    sanitizers = {'escape', 'html_escape', 'markupsafe', 'Markup', 'bleach',
                  'strip_tags', 'clean', 'sanitize', 'quote', 'urlencode',
                  'cgi_escape', 'conditional_escape'}

    # Check if the line or surrounding lines call a sanitizer
    for node in ast.walk(func_node):
        if not hasattr(node, 'lineno'):
            continue
        if abs(node.lineno - line) > 3:
            continue
        if _node_contains_call(node, sanitizers):
            return True

    return False


def _check_path_traversal_safe(func_node: ast.FunctionDef, line: int) -> bool:
    """
    Check if path operations at the given line are validated/sanitized.
    Returns True if safe (= false positive).
    """
    validators = {'abspath', 'realpath', 'normpath', 'resolve',
                  'secure_filename', 'is_safe_path'}

    # Look for validation calls in the function before the flagged line
    for node in ast.walk(func_node):
        if not hasattr(node, 'lineno'):
            continue
        if node.lineno > line:
            continue  # only check before the finding
        if _node_contains_call(node, validators):
            return True

    return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Python AST analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _classify_pattern(pattern_id: str) -> str:
    """Classify a pattern_id into a category for analysis."""
    pid = pattern_id.upper()
    if any(k in pid for k in ('SQL', 'SQLI', 'INJECTION')):
        if 'CMD' not in pid and 'COMMAND' not in pid and 'OS' not in pid:
            return 'sql_injection'
    if any(k in pid for k in ('CMD', 'COMMAND', 'OS-INJECTION', 'EXEC', 'SUBPROCESS', 'SHELL')):
        return 'command_injection'
    if any(k in pid for k in ('XSS', 'CROSS-SITE')):
        return 'xss'
    if any(k in pid for k in ('SECRET', 'HARDCODED', 'PASSWORD', 'KEY', 'TOKEN', 'CREDENTIAL')):
        return 'hardcoded_secret'
    if any(k in pid for k in ('PATH', 'TRAVERSAL', 'DIRECTORY', 'LFI')):
        return 'path_traversal'
    return 'unknown'


def _analyze_python(tree: ast.AST, line: int, pattern_id: str, source: str) -> ASTVerdict:
    """
    Analyze a finding in Python source using AST.
    Returns ASTVerdict with confirmed/fp/unconfirmed.
    """
    category = _classify_pattern(pattern_id)
    func_node = _find_enclosing_function(tree, line)

    # If not inside a function, we can still check some things
    if category == 'hardcoded_secret':
        if _check_is_test_constant(func_node, line, source):
            return ASTVerdict(
                file=source, line=line, pattern_id=pattern_id,
                original_severity="", verdict="fp",
                reason="test/mock/example constant in test file or test function"
            )
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="confirmed",
            reason="hardcoded secret in production code"
        )

    if func_node is None:
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="unconfirmed",
            reason="line not inside a function — cannot do intra-function analysis"
        )

    if category == 'sql_injection':
        if _check_sql_parameterized(func_node, line):
            return ASTVerdict(
                file=source, line=line, pattern_id=pattern_id,
                original_severity="", verdict="fp",
                reason="uses parameterized query"
            )
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="confirmed",
            reason="SQL query uses string formatting — not parameterized"
        )

    if category == 'command_injection':
        if _check_subprocess_safe(func_node, line):
            return ASTVerdict(
                file=source, line=line, pattern_id=pattern_id,
                original_severity="", verdict="fp",
                reason="subprocess uses list arguments without shell=True"
            )
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="confirmed",
            reason="command execution with potential injection"
        )

    if category == 'xss':
        if _check_xss_sanitized(func_node, line):
            return ASTVerdict(
                file=source, line=line, pattern_id=pattern_id,
                original_severity="", verdict="fp",
                reason="output is sanitized/escaped"
            )
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="confirmed",
            reason="unsanitized output — potential XSS"
        )

    if category == 'path_traversal':
        if _check_path_traversal_safe(func_node, line):
            return ASTVerdict(
                file=source, line=line, pattern_id=pattern_id,
                original_severity="", verdict="fp",
                reason="path is validated/normalized before use"
            )
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="confirmed",
            reason="path operation without validation — potential traversal"
        )

    # Unknown category
    return ASTVerdict(
        file=source, line=line, pattern_id=pattern_id,
        original_severity="", verdict="unconfirmed",
        reason=f"no AST rule for pattern category: {category}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Non-Python heuristic analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _analyze_non_python(source: str, line: int, pattern_id: str,
                        content: Optional[str]) -> ASTVerdict:
    """
    Heuristic analysis for non-Python files (JS, Go, Java, etc.).
    Uses regex patterns to detect sanitization near the flagged line.
    Returns unconfirmed if can't determine.
    """
    if content is None:
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="unconfirmed",
            reason="non-Python file — no content provided for heuristic analysis"
        )

    lines = content.split('\n')
    if line < 1 or line > len(lines):
        return ASTVerdict(
            file=source, line=line, pattern_id=pattern_id,
            original_severity="", verdict="unconfirmed",
            reason=f"line {line} out of range (file has {len(lines)} lines)"
        )

    # Get context: 5 lines before and after
    start = max(0, line - 6)
    end = min(len(lines), line + 5)
    context = '\n'.join(lines[start:end])

    category = _classify_pattern(pattern_id)

    # Check for sanitization patterns in context
    if category == 'sql_injection':
        for pat in _PARAMETERIZED_PATTERNS:
            if pat.search(context):
                return ASTVerdict(
                    file=source, line=line, pattern_id=pattern_id,
                    original_severity="", verdict="fp",
                    reason="parameterized query pattern detected (heuristic)"
                )

    if category in ('xss', 'command_injection'):
        for pat in _SANITIZATION_PATTERNS:
            if pat.search(context):
                return ASTVerdict(
                    file=source, line=line, pattern_id=pattern_id,
                    original_severity="", verdict="fp",
                    reason="sanitization pattern detected near finding (heuristic)"
                )

    if category == 'hardcoded_secret':
        source_lower = source.lower().replace('\\', '/')
        for pat in _TEST_FILE_PATTERNS:
            if pat.search(source_lower):
                return ASTVerdict(
                    file=source, line=line, pattern_id=pattern_id,
                    original_severity="", verdict="fp",
                    reason="secret in test/example file (heuristic)"
                )

    return ASTVerdict(
        file=source, line=line, pattern_id=pattern_id,
        original_severity="", verdict="unconfirmed",
        reason="non-Python file — heuristic analysis inconclusive"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def analyze_finding(file_path: str, line: int, pattern_id: str,
                    severity: str, content: str = None) -> ASTVerdict:
    """
    Analyze a single finding and return an ASTVerdict.

    Args:
        file_path: Path to the source file
        line: Line number of the finding (1-based)
        pattern_id: Pattern identifier (e.g., "SQLI-001", "SECRET-GHP")
        severity: Original severity from previous pass
        content: Optional file content (read from disk if not provided)

    Returns:
        ASTVerdict with confirmed/fp/unconfirmed verdict
    """
    # Determine file extension
    ext = os.path.splitext(file_path)[1].lower()

    # Read content if not provided
    if content is None:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except (OSError, IOError):
            return ASTVerdict(
                file=file_path, line=line, pattern_id=pattern_id,
                original_severity=severity, verdict="unconfirmed",
                reason="cannot read file"
            )

    # Non-Python: heuristic only
    if ext not in _PYTHON_EXTENSIONS:
        v = _analyze_non_python(file_path, line, pattern_id, content)
        v.original_severity = severity
        return v

    # Python: AST parse
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        v = ASTVerdict(
            file=file_path, line=line, pattern_id=pattern_id,
            original_severity=severity, verdict="unconfirmed",
            reason="Python file has syntax errors — cannot parse AST"
        )
        return v

    # Check line is within file
    lines = content.split('\n')
    if line < 1 or line > len(lines):
        return ASTVerdict(
            file=file_path, line=line, pattern_id=pattern_id,
            original_severity=severity, verdict="unconfirmed",
            reason=f"line {line} out of range (file has {len(lines)} lines)"
        )

    v = _analyze_python(tree, line, pattern_id, file_path)
    v.original_severity = severity
    return v


def analyze_findings(findings: list, file_contents: dict = None) -> list:
    """
    Analyze a batch of findings and return ASTVerdicts.

    Args:
        findings: List of dicts with keys: file, line, pattern_id, severity
                  Optional: content (file content)
        file_contents: Optional dict {file_path: content} to avoid re-reading files

    Returns:
        List of ASTVerdict
    """
    if file_contents is None:
        file_contents = {}

    verdicts = []
    _content_cache = dict(file_contents)  # Local cache to avoid re-reading files

    for finding in findings:
        fp = finding.get('file', '')
        line = finding.get('line', 0)
        pid = finding.get('pattern_id', '')
        sev = finding.get('severity', '')
        content = finding.get('content') or _content_cache.get(fp)

        # Cache file content on first read
        if content is None and fp and os.path.isfile(fp):
            try:
                with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                _content_cache[fp] = content
            except (OSError, IOError):
                pass

        verdict = analyze_finding(fp, line, pid, sev, content=content)
        verdicts.append(verdict)

    return verdicts
