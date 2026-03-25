"""
B-SCAN-05: Priority Ranker (Carmack scoring)
=============================================
Ranks files by composite priority score for security scanning.

INPUT:  per-file metrics from B-SCAN-04 (FileMetrics dict) + NCD from Cube
OUTPUT: ordered list of files by composite priority score

Algorithms:
- Goldbeter-Koshland 1981 Hill function (ultrasensitive switch)
- Friston 2010 Free Energy surprise (NCD-based structural anomaly)
- Huang & Ferrell 1996 MAPK cascade amplification (depth bonus)

Pure Python, zero external dependencies.
"""

from __future__ import annotations

import math
import os
import sys
import zlib
from dataclasses import dataclass, field

# ── Triple import fallback ─────────────────────────────────────────
try:
    from engine.core.scanner import __name__ as _pkg_check
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.normpath(os.path.join(_here, '..', '..', '..'))
    if _root not in sys.path:
        sys.path.insert(0, _root)

try:
    from engine.core.scanner.r0_calculator import FileMetrics
except ImportError:
    FileMetrics = None  # type: ignore[assignment,misc]


# ── Dataclasses ────────────────────────────────────────────────────

@dataclass
class RankedFile:
    file: str
    priority: float
    components: dict  # sub-scores before weighting
    depth_bonus: float


# ── Hill function (Goldbeter-Koshland 1981) ────────────────────────

def goldbeter(x: float, K: float = 10.0, n: float = 4.0) -> float:
    """
    Hill function switch: x^n / (K^n + x^n).
    Returns 0.0 for x=0, 0.5 for x=K, approaches 1.0 for x >> K.
    """
    if x <= 0.0:
        return 0.0
    xn = x ** n
    kn = K ** n
    denom = kn + xn
    if denom == 0.0:
        return 0.0
    return xn / denom


# ── NCD (Normalized Compression Distance) ─────────────────────────

def _ncd(a: bytes, b: bytes) -> float:
    """
    Normalized Compression Distance using zlib.
    NCD(a,b) = (C(a+b) - min(C(a), C(b))) / max(C(a), C(b))
    Returns value in [0, 1]. Returns 0.0 for empty inputs.
    """
    if not a or not b:
        return 0.0
    ca = len(zlib.compress(a, 6))
    cb = len(zlib.compress(b, 6))
    cab = len(zlib.compress(a + b, 6))
    max_c = max(ca, cb)
    if max_c == 0:
        return 0.0
    return (cab - min(ca, cb)) / max_c


# ── Free Energy surprise (Friston 2010) ───────────────────────────

def free_energy_surprise(
    file: str,
    graph: dict[str, list[str]],
    ncd_func=None,
    file_contents: dict[str, bytes] | None = None,
) -> float:
    """
    Structural anomaly: |mean_NCD(f, neighbors) - global_mean| / global_std.

    Args:
        file: target file path
        graph: adjacency dict {node: [neighbor, ...]}
        ncd_func: optional NCD function(a_bytes, b_bytes) -> float
        file_contents: {file_path: bytes_content} for NCD computation

    Returns:
        surprise score (0.0 if not computable)
    """
    if ncd_func is None:
        ncd_func = _ncd
    if file_contents is None:
        return 0.0

    # Compute all pairwise NCDs for edges
    all_ncds: list[float] = []
    per_node_mean: dict[str, float] = {}

    for node, neighbors in graph.items():
        if not neighbors:
            per_node_mean[node] = 0.0
            continue
        node_content = file_contents.get(node, b'')
        if not node_content:
            per_node_mean[node] = 0.0
            continue
        node_ncds: list[float] = []
        for nb in neighbors:
            nb_content = file_contents.get(nb, b'')
            if not nb_content:
                continue
            d = ncd_func(node_content, nb_content)
            node_ncds.append(d)
            all_ncds.append(d)
        per_node_mean[node] = sum(node_ncds) / len(node_ncds) if node_ncds else 0.0

    if not all_ncds or len(all_ncds) < 2:
        return 0.0

    global_mean = sum(all_ncds) / len(all_ncds)
    variance = sum((x - global_mean) ** 2 for x in all_ncds) / len(all_ncds)
    global_std = math.sqrt(variance) if variance > 0 else 0.0

    if global_std == 0.0:
        return 0.0

    file_mean = per_node_mean.get(file, 0.0)
    return abs(file_mean - global_mean) / global_std


# ── MAPK depth bonus (Huang & Ferrell 1996) ───────────────────────

def mapk_depth_bonus(file: str, graph: dict[str, list[str]]) -> float:
    """
    Dependency chain amplification: 1.0 + 0.1 * max_dependency_depth(f).
    Uses BFS from the file to find the longest reachable chain.

    Args:
        file: target file
        graph: adjacency dict {node: [neighbor, ...]}

    Returns:
        depth bonus multiplier (>= 1.0)
    """
    if file not in graph or not graph[file]:
        return 1.0

    # BFS to find max depth
    visited: set[str] = {file}
    queue: list[tuple[str, int]] = [(file, 0)]
    max_depth = 0

    while queue:
        node, depth = queue.pop(0)
        for nb in graph.get(node, []):
            if nb not in visited:
                visited.add(nb)
                new_depth = depth + 1
                if new_depth > max_depth:
                    max_depth = new_depth
                queue.append((nb, new_depth))

    return 1.0 + 0.1 * max_depth


# ── Main ranking function ─────────────────────────────────────────

def rank_files(
    file_metrics: dict,
    graph: dict[str, list[str]],
    ncd_func=None,
    file_contents: dict[str, bytes] | None = None,
) -> list[RankedFile]:
    """
    Rank files by composite priority score.

    priority(f) = (
        0.25 * goldbeter(R0, K=10, n=4)
        + 0.20 * free_energy_surprise(f)
        + 0.20 * betweenness_norm(f)
        + 0.20 * temperature(f)
        + 0.15 * cheeger_bottleneck(f)
    ) * mapk_depth_bonus(f)

    Args:
        file_metrics: {filename: FileMetrics} from B-SCAN-04
        graph: adjacency dict {node: [neighbor, ...]} (unweighted for BFS)
        ncd_func: optional NCD function for free energy computation
        file_contents: optional {file: bytes} for NCD computation

    Returns:
        List of RankedFile sorted by priority descending
    """
    if not file_metrics:
        return []

    results: list[RankedFile] = []

    for fname, fm in file_metrics.items():
        # Extract sub-scores from FileMetrics
        r0_val = getattr(fm, 'r0', 0)
        betweenness_val = getattr(fm, 'betweenness_centrality', 0.0)
        temp_val = getattr(fm, 'temperature', 0.0)
        cheeger_val = 1.0 if getattr(fm, 'cheeger_bottleneck', False) else 0.0

        # Compute sub-scores
        g_score = goldbeter(float(r0_val), K=10.0, n=4.0)
        fe_score = free_energy_surprise(fname, graph, ncd_func, file_contents)
        bt_score = float(betweenness_val)
        t_score = float(temp_val)
        ch_score = float(cheeger_val)

        # Composite priority (before MAPK)
        priority_raw = (
            0.25 * g_score
            + 0.20 * fe_score
            + 0.20 * bt_score
            + 0.20 * t_score
            + 0.15 * ch_score
        )

        # MAPK depth bonus
        depth = mapk_depth_bonus(fname, graph)

        priority_final = priority_raw * depth

        components = {
            'goldbeter': g_score,
            'free_energy': fe_score,
            'betweenness': bt_score,
            'temperature': t_score,
            'cheeger': ch_score,
        }

        results.append(RankedFile(
            file=fname,
            priority=priority_final,
            components=components,
            depth_bonus=depth,
        ))

    # Sort descending by priority
    results.sort(key=lambda r: r.priority, reverse=True)
    return results
