"""
B-SCAN-11: Dynamic Import Detector
====================================
Detects dynamic imports, eval/exec, reflection, and DI container patterns
across multiple languages. Pure regex, zero external dependencies.

INPUT:  file path or content string
OUTPUT: list[DynamicImport] + coverage_incomplete flag
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class DynamicImport:
    file: str
    line: int
    pattern_type: str  # eval/exec/importlib/require_dynamic/reflection/di_container
    language: str
    snippet: str  # matching line, truncated to 200 chars


@dataclass
class ScanResult:
    findings: List[DynamicImport] = field(default_factory=list)
    coverage_incomplete: bool = False


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_TO_LANG = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".php": "php",
    ".rb": "ruby",
}


def _detect_language(file_path: str) -> str:
    """Detect language from file extension. Returns '' if unknown."""
    if not file_path:
        return ""
    _, ext = os.path.splitext(file_path.lower())
    return _EXT_TO_LANG.get(ext, "")


# ---------------------------------------------------------------------------
# Pattern definitions: (regex, pattern_type, language)
# Each regex is compiled once at module load.
# ---------------------------------------------------------------------------

# Python patterns
_PYTHON_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\beval\s*\('), "eval"),
    (re.compile(r'\bexec\s*\('), "exec"),
    (re.compile(r'\bimportlib\s*\.\s*import_module\s*\('), "importlib"),
    (re.compile(r'\b__import__\s*\('), "importlib"),
    (re.compile(r'\bgetattr\s*\(.+,.+\)\s*\('), "reflection"),
]

# JavaScript patterns
_JS_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\beval\s*\('), "eval"),
    (re.compile(r'\bnew\s+Function\s*\('), "eval"),
    # require() with variable (not a string literal)
    (re.compile(r'\brequire\s*\(\s*[^\'"\s)][^)]*\)'), "require_dynamic"),
    # import() with variable (not a string literal)
    (re.compile(r'\bimport\s*\(\s*[^\'"\s)][^)]*\)'), "require_dynamic"),
]

# Go patterns
_GO_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\breflect\s*\.'), "reflection"),
]

# Java patterns
_JAVA_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\bClass\s*\.\s*forName\s*\('), "reflection"),
    (re.compile(r'\b\.getMethod\s*\('), "reflection"),
    (re.compile(r'\b\.getDeclaredMethod\s*\('), "reflection"),
    (re.compile(r'\b\.invoke\s*\('), "reflection"),
    (re.compile(r'\b\.newInstance\s*\('), "reflection"),
    (re.compile(r'\bServiceLoader\s*\.\s*load\s*\('), "di_container"),
    (re.compile(r'@Autowired'), "di_container"),
]

# PHP patterns
_PHP_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\beval\s*\('), "eval"),
    # include/require with variable (not a plain string literal)
    (re.compile(r'\b(?:include|require)(?:_once)?\s*[\(\s]+\$'), "require_dynamic"),
    (re.compile(r'\b(?:include|require)(?:_once)?\s+\$'), "require_dynamic"),
]

# Ruby patterns
_RUBY_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\beval\s*[\(\s]'), "eval"),
    (re.compile(r'\b\.send\s*[\(\s]'), "reflection"),
    (re.compile(r'\bconst_get\s*[\(\s]'), "reflection"),
]

_LANG_PATTERNS = {
    "python": _PYTHON_PATTERNS,
    "javascript": _JS_PATTERNS,
    "go": _GO_PATTERNS,
    "java": _JAVA_PATTERNS,
    "php": _PHP_PATTERNS,
    "ruby": _RUBY_PATTERNS,
}


# ---------------------------------------------------------------------------
# Comment detection (simple heuristic — not a full parser)
# ---------------------------------------------------------------------------

def _is_comment(line: str, language: str) -> bool:
    """Check if a line is a comment. Simple heuristic."""
    stripped = line.lstrip()
    if not stripped:
        return False
    if language == "python":
        return stripped.startswith("#")
    if language in ("javascript", "go", "java", "php"):
        return stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*")
    if language == "ruby":
        return stripped.startswith("#")
    if language == "php":
        return stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*")
    return False


# ---------------------------------------------------------------------------
# Core scanning
# ---------------------------------------------------------------------------

def _truncate(s: str, max_len: int = 200) -> str:
    """Truncate string to max_len chars."""
    return s[:max_len] if len(s) > max_len else s


def scan_content(content: str, file_path: str = "", language: str = "") -> ScanResult:
    """
    Scan source code content for dynamic import patterns.

    Args:
        content: source code as string
        file_path: optional file path (for language detection and output)
        language: override language detection (python/javascript/go/java/php/ruby)

    Returns:
        ScanResult with findings and coverage_incomplete flag
    """
    if not language:
        language = _detect_language(file_path)

    result = ScanResult()

    if not language:
        # Unknown language — try all patterns, flag incomplete
        result.coverage_incomplete = True
        all_patterns = []
        for lang, patterns in _LANG_PATTERNS.items():
            for pat, ptype in patterns:
                all_patterns.append((pat, ptype, lang))
    else:
        lang_patterns = _LANG_PATTERNS.get(language, [])
        if not lang_patterns:
            result.coverage_incomplete = True
            return result
        all_patterns = [(pat, ptype, language) for pat, ptype in lang_patterns]

    lines = content.splitlines()
    for line_num, line in enumerate(lines, start=1):
        for pat, ptype, lang in all_patterns:
            if pat.search(line) and not _is_comment(line, lang):
                result.findings.append(DynamicImport(
                    file=file_path,
                    line=line_num,
                    pattern_type=ptype,
                    language=lang,
                    snippet=_truncate(line.strip()),
                ))

    return result


def scan_file(file_path: str, language: str = "") -> ScanResult:
    """
    Scan a file for dynamic import patterns.

    Args:
        file_path: path to source file
        language: override language detection

    Returns:
        ScanResult with findings and coverage_incomplete flag
    """
    try:
        if os.path.getsize(file_path) > 10_000_000:
            return ScanResult()
    except OSError:
        pass
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, IOError) as e:
        result = ScanResult()
        result.coverage_incomplete = True
        return result

    return scan_content(content, file_path=file_path, language=language)


def scan_directory(dir_path: str) -> ScanResult:
    """
    Recursively scan a directory for dynamic import patterns.

    Returns:
        ScanResult with all findings aggregated
    """
    result = ScanResult()

    for root, dirs, files in os.walk(dir_path):
        # Skip hidden and common non-source dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                   ("node_modules", "__pycache__", "venv", ".git", "vendor", "dist", "build")]
        for fname in files:
            fpath = os.path.join(root, fname)
            lang = _detect_language(fpath)
            if not lang:
                continue
            file_result = scan_file(fpath, language=lang)
            result.findings.extend(file_result.findings)
            if file_result.coverage_incomplete:
                result.coverage_incomplete = True

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    """Minimal CLI: python dynamic_detector.py <path>"""
    import sys
    if len(sys.argv) < 2:
        print("Usage: dynamic_detector.py <file_or_dir>")
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isdir(target):
        result = scan_directory(target)
    elif os.path.isfile(target):
        result = scan_file(target)
    else:
        print(f"Not found: {target}")
        sys.exit(1)

    for f in result.findings:
        print(f"  {f.language:12s} {f.pattern_type:20s} {f.file}:{f.line}  {f.snippet}")

    print(f"\nTotal: {len(result.findings)} findings, coverage_incomplete={result.coverage_incomplete}")


if __name__ == "__main__":
    _cli()
