"""
B-SCAN-13: Report Generator (with epidemio metrics + patch plan)
=================================================================
Generates human-readable (markdown) and machine-parseable (JSON) scan reports.

INPUT:  merged findings (B-SCAN-09), propagation/blast radius (B-SCAN-10),
        dynamic imports (B-SCAN-11), global graph metrics (B-SCAN-04)
OUTPUT: ScanReport dataclass with markdown/JSON export

Algorithms:
- Kempe, Kleinberg & Tardos 2003 (Influence Minimization, inverse)
- Huang & Ferrell 1996 MAPK cascade (amplification detection)

Pure Python, zero external dependencies.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# ── Triple import fallback ─────────────────────────────────────────
try:
    from engine.core.scanner import __name__ as _pkg_check
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.normpath(os.path.join(_here, '..', '..', '..'))
    if _root not in sys.path:
        sys.path.insert(0, _root)


# ── Dataclasses ────────────────────────────────────────────────────

@dataclass
class ScanReport:
    """Complete scan report with all sections."""
    findings: list = field(default_factory=list)
    epidemio_metrics: dict = field(default_factory=dict)
    patch_plan: list = field(default_factory=list)
    amplified_risks: list = field(default_factory=list)
    dynamic_imports: list = field(default_factory=list)
    coverage_flags: dict = field(default_factory=dict)
    exit_code: int = 0
    scan_duration: float = 0.0
    files_scanned: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Severity constants ────────────────────────────────────────────

_SEVERITY_ORDER = {"CRIT": 4, "HIGH": 3, "MED": 2, "LOW": 1, "INFO": 0}


# ── Core functions ─────────────────────────────────────────────────

def compute_exit_code(findings: list) -> int:
    """
    Compute exit code from findings list.
    0 = clean, 1 = non-critical findings, 2 = critical findings.
    """
    if not findings:
        return 0
    severities = {_get_severity(f) for f in findings}
    if "CRIT" in severities:
        return 2
    return 1


def detect_amplified_risks(
    findings: list,
    graph: dict | None = None,
    depth_threshold: int = 3,
) -> list:
    """
    Find LOW findings that traverse depth_threshold+ dependency layers.
    MAPK cascade: a LOW finding deep in the dependency tree gets an
    "amplified risk" flag because it can cascade through layers.

    Only LOW findings are candidates (CRIT/HIGH/MED are already prioritized).

    Args:
        findings: list of finding dicts with at least {file, severity}
        graph: adjacency dict {node: [neighbor, ...]} or {node: [(neighbor, weight), ...]}
        depth_threshold: minimum depth for amplification (default 3)

    Returns:
        list of dicts with amplified finding info
    """
    if not graph or not findings:
        return []

    # Pre-compute depths via BFS from all root nodes (nodes with no incoming edges)
    all_targets = set()
    for neighbors in graph.values():
        for item in neighbors:
            if isinstance(item, (list, tuple)):
                all_targets.add(item[0])
            else:
                all_targets.add(item)

    roots = set(graph.keys()) - all_targets
    if not roots:
        roots = set(graph.keys())  # cycle: use all as roots

    depths: dict[str, int] = {}
    for root in roots:
        _bfs_depth(graph, root, depths)

    amplified = []
    for f in findings:
        sev = _get_severity(f)
        if sev != "LOW":
            continue
        fpath = _get_file(f)
        depth = depths.get(fpath, 0)
        if depth >= depth_threshold:
            amplified.append({
                "file": fpath,
                "line": _get_line(f),
                "type": _get_type(f),
                "original_severity": "LOW",
                "depth": depth,
                "amplified": True,
                "reason": f"LOW finding traverses {depth} dependency layers (>= {depth_threshold})",
            })

    return amplified


def generate_report(
    findings: list,
    propagation_result: dict | None = None,
    dynamic_imports: list | None = None,
    graph_metrics: dict | None = None,
    scan_duration: float = 0.0,
    files_scanned: int = 0,
    graph: dict | None = None,
) -> ScanReport:
    """
    Generate a complete scan report from all scanner outputs.

    Args:
        findings: merged findings from B-SCAN-09 (list of dicts or dataclasses)
        propagation_result: from B-SCAN-10 (dict with blast_radius, systemic_loss, etc.)
        dynamic_imports: from B-SCAN-11 (list of dynamic import findings)
        graph_metrics: from B-SCAN-04 (dict or GraphMetrics dataclass)
        scan_duration: total scan time in seconds
        files_scanned: number of files scanned
        graph: dependency graph for amplification detection

    Returns:
        ScanReport with all sections populated
    """
    exit_code = compute_exit_code(findings)

    # Epidemio metrics
    epidemio = _build_epidemio(propagation_result, graph_metrics)

    # Patch plan from propagation result
    patch_plan = []
    if propagation_result and isinstance(propagation_result, dict):
        patch_plan = propagation_result.get("patch_plan", [])

    # Amplified risks
    amplified = detect_amplified_risks(findings, graph)

    # Dynamic imports
    dyn_imports = dynamic_imports or []

    # Coverage flags
    coverage = {}
    if dynamic_imports:
        coverage["dynamic_imports_detected"] = True
        coverage["coverage_incomplete"] = True
    else:
        coverage["dynamic_imports_detected"] = False
        coverage["coverage_incomplete"] = False

    return ScanReport(
        findings=_normalize_findings(findings),
        epidemio_metrics=epidemio,
        patch_plan=patch_plan,
        amplified_risks=amplified,
        dynamic_imports=[_normalize_dynamic(d) for d in dyn_imports],
        coverage_flags=coverage,
        exit_code=exit_code,
        scan_duration=scan_duration,
        files_scanned=files_scanned,
    )


# ── Markdown output ────────────────────────────────────────────────

def to_markdown(report: ScanReport) -> str:
    """Render a ScanReport as GitHub-flavored markdown."""
    sections = []

    sections.append(f"# Muninn Security Scan Report")
    sections.append("")
    sections.append(f"**Timestamp:** {report.timestamp}  ")
    sections.append(f"**Files scanned:** {report.files_scanned}  ")
    sections.append(f"**Scan duration:** {report.scan_duration:.2f}s  ")
    sections.append(f"**Exit code:** {report.exit_code}  ")
    sections.append("")

    # Findings
    sections.append("## Findings")
    sections.append("")
    if report.findings:
        sections.append(_findings_table(report.findings))
    else:
        sections.append("No vulnerabilities found.")
    sections.append("")

    # Epidemio
    sections.append("## Epidemiology")
    sections.append("")
    sections.append(_epidemio_section(report.epidemio_metrics))
    sections.append("")

    # Patch plan
    sections.append("## Patch Plan")
    sections.append("")
    sections.append(_patch_plan_section(report.patch_plan))
    sections.append("")

    # Amplification
    sections.append("## Amplification (MAPK Cascade)")
    sections.append("")
    sections.append(_amplification_section(report.amplified_risks))
    sections.append("")

    # Dynamic imports
    sections.append("## Dynamic Import Warnings")
    sections.append("")
    sections.append(_dynamic_imports_section(report.dynamic_imports))
    sections.append("")

    return "\n".join(sections)


# ── JSON output ────────────────────────────────────────────────────

def to_json(report: ScanReport) -> str:
    """Render a ScanReport as JSON string."""
    data = {
        "timestamp": report.timestamp,
        "files_scanned": report.files_scanned,
        "scan_duration": report.scan_duration,
        "exit_code": report.exit_code,
        "findings": report.findings,
        "epidemio_metrics": report.epidemio_metrics,
        "patch_plan": report.patch_plan,
        "amplified_risks": report.amplified_risks,
        "dynamic_imports": report.dynamic_imports,
        "coverage_flags": report.coverage_flags,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Section renderers ──────────────────────────────────────────────

def _findings_table(findings: list) -> str:
    """Render findings as a markdown table."""
    lines = []
    lines.append("| File | Line | Type | Severity | Fix | Blast Radius |")
    lines.append("|------|------|------|----------|-----|--------------|")
    for f in findings:
        file_ = f.get("file", "N/A")
        line_ = f.get("line", "N/A")
        type_ = f.get("type", "N/A")
        sev = f.get("severity", "N/A")
        fix = f.get("fix", f.get("description", "N/A"))
        blast = f.get("blast_radius", "N/A")
        lines.append(f"| {file_} | {line_} | {type_} | {sev} | {fix} | {blast} |")
    return "\n".join(lines)


def _epidemio_section(metrics: dict) -> str:
    """Render epidemiology section."""
    if not metrics or metrics.get("status") == "N/A":
        return "Epidemiology data not available (propagation analysis was not run)."

    lines = []
    regime = metrics.get("regime", "N/A")
    lambda_c = metrics.get("lambda_c", "N/A")
    pc = metrics.get("percolation_pc", "N/A")
    infected_pct = metrics.get("infected_pct", "N/A")

    lines.append(f"- **Regime:** {regime}")
    lines.append(f"- **Epidemic threshold (lambda_c):** {lambda_c}")
    lines.append(f"- **Percolation threshold (p_c):** {pc}")
    lines.append(f"- **Infected files vs p_c:** {infected_pct}")

    return "\n".join(lines)


def _patch_plan_section(patch_plan: list) -> str:
    """Render ordered patch plan."""
    if not patch_plan:
        return "No patch plan available."

    lines = []
    lines.append("Ordered list of files to patch for maximum propagation reduction:")
    lines.append("")
    for i, entry in enumerate(patch_plan, 1):
        if isinstance(entry, dict):
            file_ = entry.get("file", "N/A")
            reduction = entry.get("reduction", "N/A")
            lines.append(f"{i}. `{file_}` — reduction: {reduction}")
        else:
            lines.append(f"{i}. `{entry}`")

    return "\n".join(lines)


def _amplification_section(amplified: list) -> str:
    """Render MAPK amplification section."""
    if not amplified:
        return "No amplified risks detected."

    lines = []
    lines.append(f"**{len(amplified)} LOW finding(s) amplified by deep dependency chains:**")
    lines.append("")
    for a in amplified:
        file_ = a.get("file", "N/A")
        depth = a.get("depth", "N/A")
        reason = a.get("reason", "")
        lines.append(f"- `{file_}` (depth {depth}): {reason}")

    return "\n".join(lines)


def _dynamic_imports_section(imports: list) -> str:
    """Render dynamic import warnings."""
    if not imports:
        return "No dynamic imports detected."

    lines = []
    lines.append(f"**{len(imports)} dynamic import(s) detected — coverage may be incomplete:**")
    lines.append("")
    for imp in imports:
        if isinstance(imp, dict):
            file_ = imp.get("file", "N/A")
            line_ = imp.get("line", "N/A")
            ptype = imp.get("pattern_type", "N/A")
            lines.append(f"- `{file_}` line {line_}: {ptype}")
        else:
            lines.append(f"- {imp}")

    return "\n".join(lines)


# ── Helpers ────────────────────────────────────────────────────────

def _get_severity(f) -> str:
    """Extract severity from a finding (dict or dataclass)."""
    if isinstance(f, dict):
        return f.get("severity", "INFO").upper()
    return getattr(f, "severity", "INFO").upper()


def _get_file(f) -> str:
    if isinstance(f, dict):
        return f.get("file", "")
    return getattr(f, "file", "")


def _get_line(f):
    if isinstance(f, dict):
        return f.get("line", 0)
    return getattr(f, "line", 0)


def _get_type(f) -> str:
    if isinstance(f, dict):
        return f.get("type", "")
    return getattr(f, "type", "")


def _normalize_findings(findings: list) -> list:
    """Normalize findings to list of dicts."""
    result = []
    for f in findings:
        if isinstance(f, dict):
            result.append(f)
        else:
            # Dataclass — convert relevant fields
            d = {}
            for attr in ("file", "line", "type", "severity", "description",
                         "fix", "blast_radius", "confidence", "source",
                         "pattern_id"):
                if hasattr(f, attr):
                    d[attr] = getattr(f, attr)
            result.append(d)
    return result


def _normalize_dynamic(d) -> dict:
    """Normalize a dynamic import to dict."""
    if isinstance(d, dict):
        return d
    result = {}
    for attr in ("file", "line", "pattern_type", "language", "snippet"):
        if hasattr(d, attr):
            result[attr] = getattr(d, attr)
    return result


def _build_epidemio(propagation_result: dict | None, graph_metrics: dict | None) -> dict:
    """Build epidemiology metrics dict from propagation + graph data."""
    if not propagation_result and not graph_metrics:
        return {"status": "N/A"}

    metrics: dict = {}

    # From graph_metrics (B-SCAN-04)
    if graph_metrics:
        gm = graph_metrics if isinstance(graph_metrics, dict) else _dc_to_dict(graph_metrics)
        metrics["lambda_c"] = gm.get("lambda_c", "N/A")
        metrics["percolation_pc"] = gm.get("percolation_pc", "N/A")
        metrics["regime"] = gm.get("regime", "N/A")
        metrics["mean_degree"] = gm.get("mean_degree", "N/A")

    # From propagation_result (B-SCAN-10)
    if propagation_result and isinstance(propagation_result, dict):
        infected = propagation_result.get("infected_files", [])
        total = propagation_result.get("total_files", 0)
        if total > 0:
            pct = len(infected) / total * 100 if isinstance(infected, list) else 0
            metrics["infected_pct"] = f"{pct:.1f}%"
        else:
            metrics["infected_pct"] = "N/A"
        metrics["systemic_loss"] = propagation_result.get("systemic_loss", "N/A")

    return metrics


def _dc_to_dict(obj) -> dict:
    """Convert a dataclass to dict, falling back to vars()."""
    try:
        return asdict(obj)
    except Exception:
        try:
            return vars(obj)
        except Exception:
            return {}


def _bfs_depth(graph: dict, start: str, depths: dict) -> None:
    """BFS from start, recording maximum depth for each node."""
    from collections import deque
    queue = deque([(start, 0)])
    visited = {start}
    if start not in depths or depths[start] < 0:
        depths[start] = 0

    while queue:
        node, d = queue.popleft()
        if node not in graph:
            continue
        for item in graph[node]:
            neighbor = item[0] if isinstance(item, (list, tuple)) else item
            new_depth = d + 1
            if neighbor not in depths or new_depth > depths[neighbor]:
                depths[neighbor] = new_depth
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, new_depth))
