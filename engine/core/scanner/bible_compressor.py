"""
B-SCAN-02: Bible Compressor
============================
Compresses bible JSON files (from B-SCAN-01) into .mn files.

Uses Muninn's compress_line() for prose (pattern descriptions, fixes) while
preserving IDs, CWE numbers, and regex patterns verbatim. This is a
structure-aware compression — unlike compress_file() which is designed for
prose documents, bible entries have critical machine-readable fields that
must survive intact.

Input:  .muninn/scanner_data/bible/{language}.json
Output: .muninn/scanner_data/bible_mn/{language}.mn

universal.mn is ALWAYS generated alongside language-specific bibles.
"""

import json
import os
from pathlib import Path
from typing import Optional

# --- Triple import fallback (muninn compress_line) ---
try:
    from engine.core.muninn import compress_line
except ImportError:
    try:
        from ..muninn import compress_line
    except ImportError:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        from engine.core.muninn import compress_line


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Bible-aware compression
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _compress_entry(entry: dict) -> str:
    """Compress a single bible entry into a compact .mn line.

    Format: ID CWE sev|compressed_pattern|compressed_fix
    Regex patterns are appended verbatim (they are machine-readable, not prose).
    """
    eid = entry.get("id", "?")
    sev = entry.get("severity", "INFO")
    cwe = entry.get("cwe", "")
    pattern = entry.get("pattern", "")
    fix = entry.get("fix", "")
    regex_map = entry.get("regex_per_language", {})

    # Compress prose fields only (pattern description + fix)
    c_pattern = compress_line(pattern)
    c_fix = compress_line(fix)

    # Main line: ID and CWE preserved verbatim
    line = f"{eid} {cwe} {sev}|{c_pattern}|{c_fix}"

    # Append regex patterns verbatim (one per language, indented)
    parts = [line]
    for lang, regex in sorted(regex_map.items()):
        parts.append(f"  r/{lang}: {regex}")

    return "\n".join(parts)


def _bible_json_to_mn(data: dict) -> str:
    """Convert a bible JSON structure directly to .mn format.

    Structure-aware: preserves IDs, CWEs, and regex verbatim.
    Compresses only prose (pattern descriptions, fix text).
    """
    language = data.get("language", "unknown")
    entries = data.get("entries", [])

    lines = [f"# MUNINN|bible|{language}"]

    # Group by severity for structured output
    by_severity = {}
    for entry in entries:
        sev = entry.get("severity", "INFO")
        by_severity.setdefault(sev, []).append(entry)

    # Output CRIT first, then HIGH, MED, LOW, INFO
    severity_order = ["CRIT", "HIGH", "MED", "LOW", "INFO"]
    for sev in severity_order:
        sev_entries = by_severity.get(sev, [])
        if not sev_entries:
            continue

        lines.append(f"## {sev}")
        for entry in sev_entries:
            lines.append(_compress_entry(entry))

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main compressor
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compress_bible_file(json_path: Path) -> str:
    """Compress a single bible JSON file into .mn format.

    Args:
        json_path: path to a bible JSON file (e.g. python.json)

    Returns:
        Compressed .mn content string (empty string on error)
    """
    json_path = Path(json_path)
    if not json_path.exists():
        return ""

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    return _bible_json_to_mn(data)


def compress_bible(
    input_dir: str | Path,
    output_dir: Optional[str | Path] = None,
) -> dict[str, Path]:
    """Compress all bible JSON files into .mn files.

    Args:
        input_dir: directory containing bible JSON files (.muninn/scanner_data/bible/)
        output_dir: where to write .mn files (.muninn/scanner_data/bible_mn/)
                    Defaults to sibling bible_mn/ directory.

    Returns:
        dict {language: path_to_mn} of generated .mn files
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        print(f"[B-SCAN-02] Input directory not found: {input_dir}")
        return {}

    if output_dir is None:
        output_dir = input_dir.parent / "bible_mn"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("*.json"))
    if not json_files:
        print(f"[B-SCAN-02] No JSON files found in {input_dir}")
        return {}

    results = {}
    total_in = 0
    total_out = 0

    # Always process universal first (if it exists)
    universal_json = input_dir / "universal.json"
    has_universal = universal_json.exists()

    for json_file in json_files:
        language = json_file.stem
        compressed = compress_bible_file(json_file)

        if not compressed:
            print(f"[B-SCAN-02] SKIP {language} (empty or error)")
            continue

        mn_path = output_dir / f"{language}.mn"
        mn_path.write_text(compressed, encoding="utf-8")

        in_size = json_file.stat().st_size
        out_size = mn_path.stat().st_size
        ratio = in_size / out_size if out_size > 0 else 0
        total_in += in_size
        total_out += out_size

        results[language] = mn_path
        print(f"[B-SCAN-02] {language}: {in_size} -> {out_size} bytes (x{ratio:.1f})")

    if total_out > 0:
        overall = total_in / total_out
        print(f"[B-SCAN-02] Total: {len(results)} files, x{overall:.1f} compression")

    if has_universal and "universal" not in results:
        print("[B-SCAN-02] WARNING: universal.mn was not generated")

    return results


def load_bible_mn(
    language: str,
    bible_mn_dir: str | Path,
) -> str:
    """Load a compressed bible for scanning.

    Always loads universal.mn + the language-specific .mn file.

    Args:
        language: target language (e.g. "python", "go")
        bible_mn_dir: directory containing .mn files

    Returns:
        Combined .mn content (universal + language-specific)
    """
    bible_mn_dir = Path(bible_mn_dir)
    parts = []

    # Universal is ALWAYS loaded
    universal_mn = bible_mn_dir / "universal.mn"
    if universal_mn.exists():
        parts.append(universal_mn.read_text(encoding="utf-8"))

    # Language-specific
    lang_mn = bible_mn_dir / f"{language}.mn"
    if lang_mn.exists():
        content = lang_mn.read_text(encoding="utf-8")
        if content not in parts:  # avoid double-load if language == "universal"
            parts.append(content)

    return "\n\n".join(parts)
