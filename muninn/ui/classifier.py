"""Muninn UI — Auto-classification (B-UI-09).

Pure Python logic — zero UI, testable with pytest.
Classifies a repo scan into one of 6 botanical families based on 5 metrics.

Families: conifere, feuillu, palmier, baobab, buisson, liane
Metrics: concentration, depth, breadth, dispersion, external_deps
"""

import json
from pathlib import Path
from dataclasses import dataclass

FAMILIES = ["conifere", "feuillu", "palmier", "baobab", "buisson", "liane"]


@dataclass
class ScanMetrics:
    """5 metrics extracted from a scan JSON."""
    concentration: float = 0.0   # How concentrated is the codebase (few large files vs many small)
    depth: float = 0.0           # Max dependency chain depth
    breadth: float = 0.0         # Number of top-level modules
    dispersion: float = 0.0      # How spread out are the nodes
    external_deps: float = 0.0   # Ratio of external dependencies


def extract_metrics(scan_data: dict) -> ScanMetrics:
    """Extract 5 metrics from scan JSON data."""
    nodes = scan_data.get("nodes", [])
    if not nodes:
        return ScanMetrics()

    n = len(nodes)

    # Concentration: if few nodes have most depends, it's concentrated
    dep_counts = [len(nd.get("depends", [])) for nd in nodes]
    total_deps = sum(dep_counts)
    max_deps = max(dep_counts) if dep_counts else 0
    concentration = max_deps / max(total_deps, 1)

    # Depth: max depth value from nodes
    depths = [nd.get("depth", 0) for nd in nodes]
    max_depth = max(depths) if depths else 0
    depth = min(max_depth / 10.0, 1.0)  # Normalize to [0, 1]

    # Breadth: number of root-level nodes (depth 0 or -1, or level R)
    roots = sum(1 for nd in nodes if nd.get("level", "") == "R" or nd.get("depth", 0) <= 0)
    breadth = min(roots / max(n, 1), 1.0)

    # Dispersion: how many different levels
    levels = set(nd.get("level", "") for nd in nodes)
    dispersion = min(len(levels) / 6.0, 1.0)

    # External deps: nodes with external entries (no local path)
    external = sum(1 for nd in nodes if _is_external(nd))
    external_deps = external / max(n, 1)

    return ScanMetrics(
        concentration=concentration,
        depth=depth,
        breadth=breadth,
        dispersion=dispersion,
        external_deps=external_deps,
    )


def _is_external(node: dict) -> bool:
    """Check if a node represents an external dependency."""
    entry = node.get("entry", "")
    label = node.get("label", "").lower()
    # External if entry looks like a package name (no path separator)
    if "/" not in entry and "\\" not in entry and "." not in entry:
        return True
    # Or if the label suggests external
    if any(kw in label for kw in ["pip", "npm", "gem", "cargo", "maven"]):
        return True
    return False


def classify_repo(scan_data: dict) -> dict:
    """Classify a repo scan into a botanical family.

    Returns:
        dict with 'family' (str), 'scores' (dict[str, float]), 'metrics' (ScanMetrics)
    """
    # If scan already has a family, trust it
    if "family" in scan_data and scan_data["family"] in FAMILIES:
        return {
            "family": scan_data["family"],
            "scores": {f: (1.0 if f == scan_data["family"] else 0.0) for f in FAMILIES},
            "metrics": extract_metrics(scan_data),
        }

    metrics = extract_metrics(scan_data)
    scores = {f: 0.0 for f in FAMILIES}

    # Scoring rules based on metrics
    # Conifere: high concentration, high depth, low breadth (pipeline)
    scores["conifere"] += metrics.concentration * 3
    scores["conifere"] += metrics.depth * 2
    scores["conifere"] -= metrics.breadth * 2

    # Feuillu: balanced, moderate everything, high dispersion
    scores["feuillu"] += metrics.dispersion * 3
    scores["feuillu"] += (1 - abs(metrics.concentration - 0.5)) * 2
    scores["feuillu"] += metrics.breadth * 1

    # Palmier: very deep, narrow (single tall trunk)
    scores["palmier"] += metrics.depth * 3
    scores["palmier"] += metrics.concentration * 2
    scores["palmier"] -= metrics.breadth * 3

    # Baobab: large core, low depth, wide (engine pattern)
    scores["baobab"] += (1 - metrics.depth) * 2
    scores["baobab"] += metrics.concentration * 2
    scores["baobab"] += (1 - metrics.breadth) * 1

    # Buisson: lots of small independent modules
    scores["buisson"] += metrics.breadth * 3
    scores["buisson"] += (1 - metrics.concentration) * 2
    scores["buisson"] += (1 - metrics.depth) * 1

    # Liane: high external deps, parasitic/wrapping pattern
    scores["liane"] += metrics.external_deps * 4
    scores["liane"] += metrics.dispersion * 1
    scores["liane"] -= metrics.concentration * 1

    # Domain hints from scan
    domain = scan_data.get("domain", "").lower()
    domain_hints = {
        "audio": "feuillu", "web": "buisson", "ml": "palmier",
        "api": "conifere", "game": "baobab", "crypto": "conifere",
        "data": "palmier", "tools": "buisson", "plugin": "liane",
    }
    if domain in domain_hints:
        scores[domain_hints[domain]] += 1.5

    # Stats-based hints
    stats = scan_data.get("stats", {})
    total_loc = stats.get("total_loc", 0)
    if total_loc > 10000:
        scores["baobab"] += 1
        scores["feuillu"] += 0.5
    elif total_loc < 1000:
        scores["buisson"] += 1

    winner = max(scores, key=scores.get)
    return {
        "family": winner,
        "scores": scores,
        "metrics": metrics,
    }


def classify_scan_file(scan_path: str | Path) -> dict:
    """Classify from a scan JSON file path."""
    with open(scan_path, encoding="utf-8") as f:
        data = json.load(f)
    return classify_repo(data)
