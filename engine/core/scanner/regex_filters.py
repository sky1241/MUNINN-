"""
B-SCAN-07: Regex Filters — deterministic vulnerability scanning per language + secrets
=======================================================================================
Applies language-specific regex patterns from bible entries to source code.
Safety net: if the LLM misses something obvious, the regex catches it.

INPUT:  Code content + language + bible entries (from B-SCAN-01 JSON or direct)
OUTPUT: list of RegexMatch {file, line, pattern_id, cwe, severity, snippet, source}

Includes 24+ secret patterns from muninn.py (_SECRET_PATTERNS) as built-in universal scan.
"""

import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# --- Triple import fallback ---
try:
    from engine.core.scanner import _SCANNER_VERSION
except ImportError:
    try:
        from . import _SCANNER_VERSION
    except ImportError:
        _SCANNER_VERSION = None

_SCANNER_VERSION = "0.1.0"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class RegexMatch:
    """Single regex match result."""
    file: str
    line: int
    pattern_id: str
    cwe: str
    severity: str       # CRIT / HIGH / MED / LOW / INFO
    snippet: str        # the matching line (truncated 200 chars)
    source: str = "regex"  # always "regex" for this brick


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Built-in secret patterns (from muninn.py _SECRET_PATTERNS)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SECRET_PATTERNS = [
    # --- Git/CI ---
    (r'ghp_[A-Za-z0-9]{20,}',                          "SECRET-GHP",   "CWE-798", "CRIT", "GitHub PAT classic"),
    (r'github_pat_[A-Za-z0-9_]{20,}',                  "SECRET-GHPAT", "CWE-798", "CRIT", "GitHub fine-grained PAT"),
    (r'gho_[A-Za-z0-9]{20,}',                          "SECRET-GHO",   "CWE-798", "CRIT", "GitHub OAuth token"),
    (r'ghu_[A-Za-z0-9]{20,}',                          "SECRET-GHU",   "CWE-798", "CRIT", "GitHub user-to-server token"),
    (r'ghs_[A-Za-z0-9]{20,}',                          "SECRET-GHS",   "CWE-798", "CRIT", "GitHub server-to-server token"),
    (r'glpat-[A-Za-z0-9\-_]{20,}',                     "SECRET-GLPAT", "CWE-798", "CRIT", "GitLab PAT"),
    # --- Cloud providers ---
    (r'AKIA[A-Z0-9]{16}',                              "SECRET-AWS",   "CWE-798", "CRIT", "AWS access key"),
    (r'AIzaSy[A-Za-z0-9\-_]{33}',                      "SECRET-GCP",   "CWE-798", "CRIT", "Google Cloud API key"),
    (r'DefaultEndpointsProtocol=[^\s]+',                "SECRET-AZURE", "CWE-798", "CRIT", "Azure storage connection string"),
    # --- AI/SaaS API keys ---
    (r'sk-[A-Za-z0-9\-._]{20,}',                       "SECRET-OPENAI","CWE-798", "CRIT", "Anthropic/OpenAI key"),
    (r'sk_live_[A-Za-z0-9]{20,}',                      "SECRET-STRIPE","CWE-798", "CRIT", "Stripe secret key"),
    (r'pk_live_[A-Za-z0-9]{20,}',                      "SECRET-STRIPEPK","CWE-798","HIGH", "Stripe publishable key"),
    (r'SG\.[A-Za-z0-9\-_.]{20,}',                      "SECRET-SENDGRID","CWE-798","CRIT","SendGrid key"),
    (r'SK[a-f0-9]{32}',                                "SECRET-TWILIO","CWE-798", "CRIT", "Twilio key"),
    (r'HRKU-[a-f0-9\-]{36}',                           "SECRET-HEROKU","CWE-798", "CRIT", "Heroku key"),
    # --- Package registries ---
    (r'npm_[A-Za-z0-9]{20,}',                          "SECRET-NPM",   "CWE-798", "CRIT", "NPM token"),
    (r'pypi-[A-Za-z0-9]{20,}',                         "SECRET-PYPI",  "CWE-798", "CRIT", "PyPI token"),
    # --- Chat/Social ---
    (r'xox[bpsar]-[A-Za-z0-9\-]{10,}',                 "SECRET-SLACK", "CWE-798", "CRIT", "Slack token"),
    (r'[A-Za-z0-9]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}', "SECRET-DISCORD","CWE-798","CRIT","Discord bot token"),
    # --- Database URIs ---
    (r'(?:mongodb(?:\+srv)?|postgresql|mysql|redis|amqp)://[^\s]*:[^\s@]+@[^\s]+', "SECRET-DBURI","CWE-798","CRIT","DB connection string with password"),
    # --- Generic ---
    (r'-----BEGIN\s+\w*\s*PRIVATE KEY-----',           "SECRET-PRIVKEY","CWE-321","CRIT","PEM private key"),
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',               "SECRET-BEARER","CWE-798", "HIGH","OAuth Bearer token"),
    (r'token[=:]\s*\S{20,}',                           "SECRET-TOKEN", "CWE-798", "HIGH","Generic token assignment"),
    (r'password[=:]\s*\S+',                             "SECRET-PASSWD","CWE-798", "HIGH","Generic password assignment"),
    (r'secret[=:]\s*\S{10,}',                          "SECRET-SECRET","CWE-798", "HIGH","Generic secret assignment"),
    (r'api[_-]?key[=:]\s*\S{10,}',                     "SECRET-APIKEY","CWE-798", "HIGH","Generic API key assignment"),
    (r'(?:cl[eé]|mdp|mot\s+de\s+passe|passwd|passphrase)[=:\s]+\S+', "SECRET-FR","CWE-798","HIGH","French secret pattern"),
]

# Config file extensions/patterns
_CONFIG_PATTERNS = {
    "yaml", "yml", "json", "toml", "ini", "env",
    "dockerfile", "docker-compose", "docker-compose.yml",
    "docker-compose.yaml", "nginx", "nginx.conf",
}


def _is_config_file(filename: str) -> bool:
    """Check if filename matches config file patterns."""
    if not filename:
        return False
    name_lower = filename.lower()
    base = os.path.basename(name_lower)
    # Check extension
    ext = base.rsplit(".", 1)[-1] if "." in base else ""
    if ext in _CONFIG_PATTERNS:
        return True
    # Check basename patterns
    for pat in ("dockerfile", "docker-compose", "nginx", ".env"):
        if pat in base:
            return True
    return False


def _compile_regex(pattern: str):
    """Compile regex safely. Returns None on invalid pattern."""
    try:
        return re.compile(pattern)
    except re.error:
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Core scan functions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_file_content(content: str, language: str, bible_entries: list,
                      filename: str = "") -> list:
    """
    Scan file content with regex patterns from bible entries.

    Args:
        content: source code as string
        language: file language (python, javascript, go, etc.)
        bible_entries: list of dicts with {id, severity, regex_per_language, cwe, ...}
        filename: optional filename for config detection and match reporting

    Returns:
        list of RegexMatch
    """
    if not content or not content.strip():
        return []

    matches = []
    lines = content.split("\n")
    is_config = _is_config_file(filename)

    # --- 1. Apply bible entry regex for this language ---
    for entry in bible_entries:
        regex_map = entry.get("regex_per_language", {})
        if not regex_map:
            continue

        # Collect applicable regex patterns for this entry
        patterns_to_try = []

        # Language-specific regex
        if language in regex_map:
            patterns_to_try.append(regex_map[language])

        # Universal entries apply to ALL files
        if "universal" in regex_map:
            patterns_to_try.append(regex_map["universal"])

        # Config entries apply only to config files
        if "config" in regex_map and is_config:
            patterns_to_try.append(regex_map["config"])

        entry_id = entry.get("id", "UNKNOWN")
        entry_cwe = entry.get("cwe", "")
        entry_severity = entry.get("severity", "INFO")

        for pat_str in patterns_to_try:
            if not pat_str:
                continue
            compiled = _compile_regex(pat_str)
            if compiled is None:
                continue  # Invalid regex — skip gracefully

            for line_num, line_text in enumerate(lines, start=1):
                try:
                    if compiled.search(line_text):
                        snippet = line_text.strip()[:200]
                        matches.append(RegexMatch(
                            file=filename,
                            line=line_num,
                            pattern_id=entry_id,
                            cwe=entry_cwe,
                            severity=entry_severity,
                            snippet=snippet,
                        ))
                except Exception:
                    # Some regex may fail on specific input (catastrophic backtracking, etc.)
                    continue

    # --- 2. Apply built-in secret patterns (universal, always) ---
    for pat_str, pat_id, cwe, severity, _desc in _SECRET_PATTERNS:
        compiled = _compile_regex(pat_str)
        if compiled is None:
            continue
        for line_num, line_text in enumerate(lines, start=1):
            try:
                if compiled.search(line_text):
                    snippet = line_text.strip()[:200]
                    matches.append(RegexMatch(
                        file=filename,
                        line=line_num,
                        pattern_id=pat_id,
                        cwe=cwe,
                        severity=severity,
                        snippet=snippet,
                    ))
            except Exception:
                continue

    return matches


def scan_file(file_path: str, language: str, bible_entries: list) -> list:
    """
    Scan a file on disk with regex patterns.

    Args:
        file_path: path to the file
        language: file language
        bible_entries: list of bible entry dicts

    Returns:
        list of RegexMatch
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, IOError):
        return []

    return scan_file_content(content, language, bible_entries, filename=file_path)


def scan_repo(files: list, bible_entries: list) -> list:
    """
    Scan multiple files with regex patterns.

    Args:
        files: list of (path, content, language) tuples
        bible_entries: list of bible entry dicts

    Returns:
        list of RegexMatch (all files combined)
    """
    all_matches = []
    for path, content, language in files:
        file_matches = scan_file_content(content, language, bible_entries, filename=path)
        all_matches.extend(file_matches)
    return all_matches


def load_bible(bible_dir: str, language: str) -> list:
    """
    Load bible entries from JSON files.

    Loads {language}.json + universal.json from bible_dir.

    Args:
        bible_dir: directory containing bible JSON files
        language: language to load (e.g. "python", "go")

    Returns:
        list of bible entry dicts
    """
    entries = []
    bible_path = Path(bible_dir)

    for fname in [f"{language}.json", "universal.json", "config.json"]:
        fpath = bible_path / fname
        if fpath.exists():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    entries.extend(data)
            except (json.JSONDecodeError, OSError):
                continue

    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: regex_filters.py <file_path> <language> [bible_dir]")
        sys.exit(1)

    target = sys.argv[1]
    lang = sys.argv[2]
    bible_dir = sys.argv[3] if len(sys.argv) > 3 else None

    entries = []
    if bible_dir:
        entries = load_bible(bible_dir, lang)

    results = scan_file(target, lang, entries)
    for m in results:
        print(f"[{m.severity}] {m.file}:{m.line} {m.pattern_id} ({m.cwe}) — {m.snippet[:80]}")

    print(f"\nTotal: {len(results)} matches")
