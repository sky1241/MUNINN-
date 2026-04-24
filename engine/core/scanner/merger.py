"""
B-SCAN-09: Merger + Dedup — unified finding consolidation
==========================================================
Merges outputs from B-SCAN-06 (LLM, optional), B-SCAN-07 (regex), B-SCAN-08 (AST)
into a deduplicated list of MergedFinding with confidence scores.

INPUT:  llm_findings (optional), regex_findings (list[RegexMatch-like]),
        ast_verdicts (list[ASTVerdict-like])
OUTPUT: list[MergedFinding] sorted by severity then confidence

CONFIDENCE RULES:
  - "confirmed" = 2+ sources agree (same file + line±tolerance + type)
  - "maybe"     = 1 source only
  - "fp"        = AST explicitly rejects (verdict="false_positive" or "fp")

DEDUP: by file + line + type (exact). Multiple sources → single finding, all sources listed.
MODE DEGRADE: B-SCAN-06 can be None/empty — merger handles gracefully.
"""

from dataclasses import dataclass, field, asdict



# Severity ordering (lower = more critical)
_SEVERITY_ORDER = {"CRIT": 0, "HIGH": 1, "MED": 2, "LOW": 3, "INFO": 4}
_CONFIDENCE_ORDER = {"confirmed": 0, "maybe": 1, "fp": 2}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class MergedFinding:
    """Unified finding after merge + dedup."""
    file: str
    line: int
    type: str               # pattern_id / vulnerability type
    severity: str            # CRIT / HIGH / MED / LOW / INFO
    confidence: str          # confirmed / maybe / fp
    sources: list = field(default_factory=list)   # ["llm", "regex", "ast"]
    fix: str = ""
    cwe: str = ""
    blast_radius: list = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Normalization — convert each source format to common dicts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _normalize_llm(findings: list) -> list:
    """
    Convert LLM findings to common format.
    LLM findings are dicts with at least: file, line, type/pattern_id, severity.
    """
    if not findings:
        return []
    normalized = []
    for f in findings:
        if not isinstance(f, dict):
            # Try dataclass with asdict
            try:
                f = asdict(f)
            except (TypeError, AttributeError):
                continue
        normalized.append({
            "file": f.get("file", ""),
            "line": int(f.get("line", 0)),
            "type": f.get("type") or f.get("pattern_id", ""),
            "severity": f.get("severity", "INFO"),
            "source": "llm",
            "fix": f.get("fix", ""),
            "cwe": f.get("cwe", ""),
            "blast_radius": f.get("blast_radius", []),
        })
    return normalized


def _normalize_regex(findings: list) -> list:
    """
    Convert RegexMatch findings to common format.
    RegexMatch has: file, line, pattern_id, cwe, severity, snippet, source.
    """
    if not findings:
        return []
    normalized = []
    for f in findings:
        if isinstance(f, dict):
            d = f
        else:
            try:
                d = asdict(f)
            except (TypeError, AttributeError):
                # Fallback: read attributes directly
                d = {
                    "file": getattr(f, "file", ""),
                    "line": getattr(f, "line", 0),
                    "pattern_id": getattr(f, "pattern_id", ""),
                    "cwe": getattr(f, "cwe", ""),
                    "severity": getattr(f, "severity", "INFO"),
                }
        normalized.append({
            "file": d.get("file", ""),
            "line": int(d.get("line", 0)),
            "type": d.get("type") or d.get("pattern_id", ""),
            "severity": d.get("severity", "INFO"),
            "source": "regex",
            "fix": d.get("fix", ""),
            "cwe": d.get("cwe", ""),
            "blast_radius": d.get("blast_radius", []),
        })
    return normalized


def _normalize_ast(verdicts: list) -> list:
    """
    Convert ASTVerdict findings to common format.
    ASTVerdict has: file, line, pattern_id, original_severity, verdict, reason, source.
    We keep the verdict info for later confidence assignment.
    """
    if not verdicts:
        return []
    normalized = []
    for v in verdicts:
        if isinstance(v, dict):
            d = v
        else:
            try:
                d = asdict(v)
            except (TypeError, AttributeError):
                d = {
                    "file": getattr(v, "file", ""),
                    "line": getattr(v, "line", 0),
                    "pattern_id": getattr(v, "pattern_id", ""),
                    "original_severity": getattr(v, "original_severity", ""),
                    "verdict": getattr(v, "verdict", "unconfirmed"),
                    "reason": getattr(v, "reason", ""),
                }
        normalized.append({
            "file": d.get("file", ""),
            "line": int(d.get("line", 0)),
            "type": d.get("type") or d.get("pattern_id", ""),
            "severity": d.get("original_severity") or d.get("severity", "INFO"),
            "source": "ast",
            "fix": d.get("fix", ""),
            "cwe": d.get("cwe", ""),
            "blast_radius": d.get("blast_radius", []),
            "_verdict": d.get("verdict", "unconfirmed"),
        })
    return normalized


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Grouping + confidence + dedup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _lines_match(line_a: int, line_b: int, tolerance: int) -> bool:
    """Check if two line numbers are within tolerance."""
    return abs(line_a - line_b) <= tolerance


def _assign_confidence(source_count: int, ast_rejected: bool) -> str:
    """Determine confidence level."""
    if ast_rejected:
        return "fp"
    if source_count >= 2:
        return "confirmed"
    return "maybe"


def _dedup(findings: list) -> list:
    """
    Remove exact duplicates by (file, line, type).
    If same key appears multiple times, merge sources.
    """
    seen = {}
    for f in findings:
        key = (f.file, f.line, f.type)
        if key in seen:
            existing = seen[key]
            # Merge sources
            for s in f.sources:
                if s not in existing.sources:
                    existing.sources.append(s)
            # Keep best severity
            if _SEVERITY_ORDER.get(f.severity, 99) < _SEVERITY_ORDER.get(existing.severity, 99):
                existing.severity = f.severity
            # Keep best confidence
            if _CONFIDENCE_ORDER.get(f.confidence, 99) < _CONFIDENCE_ORDER.get(existing.confidence, 99):
                existing.confidence = f.confidence
            # Merge fix/cwe if missing
            if f.fix and not existing.fix:
                existing.fix = f.fix
            if f.cwe and not existing.cwe:
                existing.cwe = f.cwe
            # Merge blast_radius
            for br in f.blast_radius:
                if br not in existing.blast_radius:
                    existing.blast_radius.append(br)
        else:
            seen[key] = f
    return list(seen.values())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def merge_findings(llm_findings=None, regex_findings=None, ast_verdicts=None,
                   line_tolerance: int = 3) -> list:
    """
    Merge findings from LLM, regex, and AST passes into unified MergedFindings.

    Args:
        llm_findings: list of LLM findings (dicts or dataclasses). Can be None.
        regex_findings: list of RegexMatch (dataclass or dicts). Can be None.
        ast_verdicts: list of ASTVerdict (dataclass or dicts). Can be None.
        line_tolerance: max line difference for same-finding grouping (default 3).

    Returns:
        list of MergedFinding, sorted by severity (CRIT first) then confidence.
    """
    # Normalize all inputs
    llm_norm = _normalize_llm(llm_findings)
    regex_norm = _normalize_regex(regex_findings)
    ast_norm = _normalize_ast(ast_verdicts)

    # Combine non-AST findings (LLM + regex) — these are the "finders"
    all_findings = llm_norm + regex_norm

    if not all_findings and not ast_norm:
        return []

    # If no finders but AST has items, use AST as source too
    # (AST can have confirmed findings that stand alone)
    if not all_findings:
        # Use AST confirmed findings as standalone
        for a in ast_norm:
            if a.get("_verdict") == "confirmed":
                all_findings.append(a)
        if not all_findings:
            return []

    # Group by (file, type) with line tolerance
    groups = {}  # (file, type) -> list of items
    for item in all_findings:
        key = (item["file"], item["type"])
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    # Build MergedFindings from groups
    merged = []
    for (file_key, type_key), items in groups.items():
        # Sub-group by line proximity
        line_groups = []
        for item in items:
            placed = False
            for lg in line_groups:
                if any(_lines_match(item["line"], existing["line"], line_tolerance)
                       for existing in lg):
                    lg.append(item)
                    placed = True
                    break
            if not placed:
                line_groups.append([item])

        for lg in line_groups:
            # Pick representative line (minimum)
            rep_line = min(it["line"] for it in lg)
            # Collect unique sources
            sources = []
            for it in lg:
                if it["source"] not in sources:
                    sources.append(it["source"])
            # Best severity
            best_severity = min(
                (it["severity"] for it in lg),
                key=lambda s: _SEVERITY_ORDER.get(s, 99)
            )
            # Merge fix, cwe, blast_radius
            fix = ""
            cwe = ""
            blast_radius = []
            for it in lg:
                if it.get("fix") and not fix:
                    fix = it["fix"]
                if it.get("cwe") and not cwe:
                    cwe = it["cwe"]
                for br in it.get("blast_radius", []):
                    if br not in blast_radius:
                        blast_radius.append(br)

            # Check AST rejection for this group
            ast_rejected = False
            for a in ast_norm:
                if (a["file"] == file_key and a["type"] == type_key
                        and _lines_match(a["line"], rep_line, line_tolerance)):
                    v = a.get("_verdict", "unconfirmed")
                    if v in ("fp", "false_positive"):
                        ast_rejected = True
                    elif v == "confirmed":
                        if "ast" not in sources:
                            sources.append("ast")

            confidence = _assign_confidence(len(sources), ast_rejected)

            merged.append(MergedFinding(
                file=file_key,
                line=rep_line,
                type=type_key,
                severity=best_severity,
                confidence=confidence,
                sources=sources,
                fix=fix,
                cwe=cwe,
                blast_radius=blast_radius,
            ))

    # Dedup exact matches
    merged = _dedup(merged)

    # Sort: severity (CRIT first), then confidence (confirmed first), then file+line
    merged.sort(key=lambda f: (
        _SEVERITY_ORDER.get(f.severity, 99),
        _CONFIDENCE_ORDER.get(f.confidence, 99),
        f.file,
        f.line,
    ))

    return merged


def summary(findings: list) -> dict:
    """
    Summary counts for a list of MergedFinding.

    Returns:
        dict with keys:
        - total: int
        - by_severity: {CRIT: n, HIGH: n, ...}
        - by_confidence: {confirmed: n, maybe: n, fp: n}
        - by_source: {llm: n, regex: n, ast: n}
    """
    by_severity = {}
    by_confidence = {}
    by_source = {}

    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_confidence[f.confidence] = by_confidence.get(f.confidence, 0) + 1
        for s in f.sources:
            by_source[s] = by_source.get(s, 0) + 1

    return {
        "total": len(findings),
        "by_severity": by_severity,
        "by_confidence": by_confidence,
        "by_source": by_source,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import json
    import sys

    print("B-SCAN-09: Merger + Dedup")
    print("Usage: merger.py <regex_json> [ast_json] [llm_json]")
    print("  Reads JSON arrays from files, merges, prints result.")

    if len(sys.argv) < 2:
        sys.exit(1)

    regex_path = sys.argv[1]
    ast_path = sys.argv[2] if len(sys.argv) > 2 else None
    llm_path = sys.argv[3] if len(sys.argv) > 3 else None

    def _load_json(path):
        if not path:
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    regex_data = _load_json(regex_path)
    ast_data = _load_json(ast_path) if ast_path else None
    llm_data = _load_json(llm_path) if llm_path else None

    results = merge_findings(
        llm_findings=llm_data,
        regex_findings=regex_data,
        ast_verdicts=ast_data,
    )

    for r in results:
        print(f"[{r.severity}][{r.confidence}] {r.file}:{r.line} {r.type} "
              f"(sources: {','.join(r.sources)}) {r.cwe}")

    s = summary(results)
    print(f"\nTotal: {s['total']} | Severity: {s['by_severity']} | "
          f"Confidence: {s['by_confidence']} | Sources: {s['by_source']}")
