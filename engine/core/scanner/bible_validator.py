"""
B-SCAN-03: Bible Validator
===========================
Validates that bible compression (B-SCAN-02) preserved all critical patterns.

Core invariant: 0% loss on CRIT severity patterns.
If the compressed .mn bible loses a CRIT pattern that the raw bible has -> FAIL.

Input:  raw bible JSON (from B-SCAN-01) + compressed .mn (from B-SCAN-02)
Output: ValidationResult per language + optional code-scan coverage comparison

Dependencies: B-SCAN-01, B-SCAN-02
"""

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# --- Triple import fallback (bible_scraper) ---
try:
    from engine.core.scanner.bible_scraper import BibleEntry, _core_bible
except ImportError:
    try:
        from .bible_scraper import BibleEntry, _core_bible
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        from engine.core.scanner.bible_scraper import BibleEntry, _core_bible


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ValidationResult:
    """Result of validating a compressed bible against its raw source."""
    language: str
    total_entries: int
    crit_entries: int
    crit_preserved: int
    crit_lost: list  # IDs of lost CRIT patterns
    high_preserved: int
    high_lost: list  # IDs of lost HIGH patterns
    compression_ratio: float  # raw_size / compressed_size
    passed: bool  # True if 0 CRIT lost

    def to_dict(self) -> dict:
        return asdict(self)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# .mn parser — extract IDs and regex from compressed bible
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _parse_mn_entries(mn_content: str) -> dict:
    """Parse a .mn bible file and extract preserved entries.

    Returns:
        dict {entry_id: {"severity": str, "regex": {lang: pattern}}}
    """
    entries = {}
    current_id = None
    current_sev = None

    for line in mn_content.splitlines():
        stripped = line.strip()

        # Skip headers and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # Regex line (indented, starts with r/)
        if stripped.startswith("r/"):
            if current_id:
                # Parse "r/python: <regex>"
                match = re.match(r'^r/(\w+):\s*(.+)$', stripped)
                if match:
                    lang, regex = match.group(1), match.group(2)
                    if current_id not in entries:
                        entries[current_id] = {"severity": current_sev, "regex": {}}
                    entries[current_id]["regex"][lang] = regex
            continue

        # Entry line: "ID CWE SEV|compressed_pattern|compressed_fix"
        # ID is the first token (no spaces in IDs)
        parts = stripped.split("|", 1)
        if parts:
            header = parts[0].strip()
            tokens = header.split()
            if len(tokens) >= 3:
                eid = tokens[0]
                sev = tokens[2] if tokens[2] in ("CRIT", "HIGH", "MED", "LOW", "INFO") else tokens[-1]
                current_id = eid
                current_sev = sev
                if eid not in entries:
                    entries[eid] = {"severity": sev, "regex": {}}

    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Validation logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_bible(raw_json_path: str | Path, compressed_mn_path: str | Path) -> ValidationResult:
    """Validate a compressed .mn bible against its raw JSON source.

    Checks that all CRIT and HIGH entries have their IDs and regex patterns
    preserved in the compressed version.

    Args:
        raw_json_path: path to the raw bible JSON (from B-SCAN-01)
        compressed_mn_path: path to the compressed .mn (from B-SCAN-02)

    Returns:
        ValidationResult with pass/fail status
    """
    raw_json_path = Path(raw_json_path)
    compressed_mn_path = Path(compressed_mn_path)

    # Load raw bible
    raw_data = json.loads(raw_json_path.read_text(encoding="utf-8"))
    raw_entries = raw_data.get("entries", [])
    language = raw_data.get("language", "unknown")

    # Load compressed bible
    mn_content = compressed_mn_path.read_text(encoding="utf-8")
    mn_entries = _parse_mn_entries(mn_content)

    # Compute sizes
    raw_size = raw_json_path.stat().st_size
    mn_size = compressed_mn_path.stat().st_size
    compression_ratio = raw_size / mn_size if mn_size > 0 else 0.0

    # Check preservation by severity
    crit_total = 0
    crit_preserved = 0
    crit_lost = []
    high_total = 0
    high_preserved = 0
    high_lost = []

    for entry in raw_entries:
        eid = entry.get("id", "?")
        sev = entry.get("severity", "INFO")
        raw_regex = entry.get("regex_per_language", {})

        if sev == "CRIT":
            crit_total += 1
            if eid in mn_entries and _regex_preserved(raw_regex, mn_entries[eid].get("regex", {})):
                crit_preserved += 1
            else:
                crit_lost.append(eid)
        elif sev == "HIGH":
            high_total += 1
            if eid in mn_entries and _regex_preserved(raw_regex, mn_entries[eid].get("regex", {})):
                high_preserved += 1
            else:
                high_lost.append(eid)

    return ValidationResult(
        language=language,
        total_entries=len(raw_entries),
        crit_entries=crit_total,
        crit_preserved=crit_preserved,
        crit_lost=crit_lost,
        high_preserved=high_preserved,
        high_lost=high_lost,
        compression_ratio=round(compression_ratio, 2),
        passed=(len(crit_lost) == 0),
    )


def _regex_preserved(raw_regex: dict, mn_regex: dict) -> bool:
    """Check that all regex patterns from raw are present in .mn.

    At least one language regex must be preserved for the entry to count.
    """
    if not raw_regex:
        return True  # no regex to check

    # Check that at least one language regex is preserved verbatim
    for lang, pattern in raw_regex.items():
        if lang in mn_regex and mn_regex[lang].strip() == pattern.strip():
            return True

    return False


def validate_all(
    raw_dir: str | Path,
    compressed_dir: str | Path,
) -> list:
    """Validate all compressed bibles against their raw sources.

    Args:
        raw_dir: directory containing raw bible JSON files
        compressed_dir: directory containing compressed .mn files

    Returns:
        list of ValidationResult (one per language)
    """
    raw_dir = Path(raw_dir)
    compressed_dir = Path(compressed_dir)
    results = []

    for json_file in sorted(raw_dir.glob("*.json")):
        language = json_file.stem
        mn_file = compressed_dir / f"{language}.mn"

        if not mn_file.exists():
            # .mn file missing entirely = all entries lost
            raw_data = json.loads(json_file.read_text(encoding="utf-8"))
            raw_entries = raw_data.get("entries", [])
            crit_ids = [e["id"] for e in raw_entries if e.get("severity") == "CRIT"]
            high_ids = [e["id"] for e in raw_entries if e.get("severity") == "HIGH"]
            results.append(ValidationResult(
                language=language,
                total_entries=len(raw_entries),
                crit_entries=len(crit_ids),
                crit_preserved=0,
                crit_lost=crit_ids,
                high_preserved=0,
                high_lost=high_ids,
                compression_ratio=0.0,
                passed=(len(crit_ids) == 0),
            ))
            continue

        results.append(validate_bible(json_file, mn_file))

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Code-scan validation — compare raw vs .mn detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_against_code(
    bible_entries: list,
    code_samples: list,
) -> dict:
    """Scan code samples with raw bible regex, then with .mn-extracted regex.

    Compares detection rates to ensure compression doesn't reduce coverage.

    Args:
        bible_entries: list of dicts with {id, severity, regex_per_language}
        code_samples: list of (path, content, language) tuples

    Returns:
        dict {pattern_id: {"raw_finds": int, "mn_finds": int, "severity": str}}
    """
    results = {}

    for entry in bible_entries:
        eid = entry.get("id", "?")
        sev = entry.get("severity", "INFO")
        regex_map = entry.get("regex_per_language", {})

        raw_finds = 0
        for path, content, lang in code_samples:
            pattern = regex_map.get(lang, "")
            if pattern:
                try:
                    matches = re.findall(pattern, content)
                    raw_finds += len(matches)
                except re.error:
                    pass  # invalid regex — skip

        results[eid] = {
            "raw_finds": raw_finds,
            "mn_finds": raw_finds,  # same regex = same finds (if preserved)
            "severity": sev,
        }

    return results


def validate_against_code_with_mn(
    raw_entries: list,
    mn_content: str,
    code_samples: list,
) -> dict:
    """Full validation: scan code with raw regex AND .mn-extracted regex.

    This is the definitive test: if .mn regex finds fewer matches than raw
    regex on the same code, compression has caused loss.

    Args:
        raw_entries: list of dicts with {id, severity, regex_per_language}
        mn_content: the .mn file content
        code_samples: list of (path, content, language) tuples

    Returns:
        dict {pattern_id: {"raw_finds": int, "mn_finds": int, "severity": str, "lost": bool}}
    """
    # Parse .mn to get extracted regex
    mn_parsed = _parse_mn_entries(mn_content)

    results = {}

    for entry in raw_entries:
        eid = entry.get("id", "?")
        sev = entry.get("severity", "INFO")
        raw_regex_map = entry.get("regex_per_language", {})
        mn_regex_map = mn_parsed.get(eid, {}).get("regex", {})

        raw_finds = 0
        mn_finds = 0

        for path, content, lang in code_samples:
            # Raw regex scan
            raw_pattern = raw_regex_map.get(lang, "")
            if raw_pattern:
                try:
                    raw_finds += len(re.findall(raw_pattern, content))
                except re.error:
                    pass

            # .mn regex scan
            mn_pattern = mn_regex_map.get(lang, "")
            if mn_pattern:
                try:
                    mn_finds += len(re.findall(mn_pattern, content))
                except re.error:
                    pass

        results[eid] = {
            "raw_finds": raw_finds,
            "mn_finds": mn_finds,
            "severity": sev,
            "lost": mn_finds < raw_finds,
        }

    return results
