"""
B-SCAN-04: R0 Calculator + Graph Metrics
==========================================
Computes graph metrics on a dependency graph for security scan prioritization.

INPUT:  adjacency dict {node: [(neighbor, weight), ...]}
OUTPUT: per-file metrics (R0, degree centrality, betweenness, temperature, bottleneck)
        global metrics (lambda_c, percolation_pc, regime, mean_degree, ...)

Algorithms:
- Brandes 2001 betweenness centrality O(n*m)
- Pastor-Satorras & Vespignani 2001 epidemic threshold
- Molloy & Reed 1995 percolation threshold

Pure Python, zero external dependencies.
"""

from __future__ import annotations

import sys
import os
from collections import deque
from dataclasses import dataclass

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
class FileMetrics:
    file: str
    r0: int                        # out-degree (how many files depend on this)
    degree_centrality: float       # degree / max_degree, normalized [0,1]
    betweenness_centrality: float  # Brandes, normalized [0,1]
    temperature: float             # from external data, 0.0 default
    cheeger_bottleneck: bool       # from external Cheeger analysis


@dataclass
class GraphMetrics:
    lambda_c: float        # epidemic threshold
    percolation_pc: float  # percolation threshold
    regime: str            # "local" or "systemic"
    mean_degree: float
    mean_sq_degree: float
    num_nodes: int
    num_edges: int


# ── Helpers ────────────────────────────────────────────────────────

def _build_undirected(adj: dict[str, list[tuple[str, float]]]) -> dict[str, set[str]]:
    """Convert weighted directed adjacency to unweighted undirected adjacency."""
    g: dict[str, set[str]] = {}
    for node in adj:
        if node not in g:
            g[node] = set()
        for neighbor, _w in adj[node]:
            g[node].add(neighbor)
            if neighbor not in g:
                g[neighbor] = set()
            g[neighbor].add(node)
    return g


def _brandes_betweenness(adj_undirected: dict[str, set[str]]) -> dict[str, float]:
    """
    Brandes 2001 betweenness centrality for unweighted undirected graphs.
    Returns normalized values in [0, 1].
    """
    nodes = list(adj_undirected.keys())
    n = len(nodes)
    cb: dict[str, float] = {v: 0.0 for v in nodes}

    if n <= 2:
        return cb

    for s in nodes:
        # BFS
        stack: list[str] = []
        pred: dict[str, list[str]] = {v: [] for v in nodes}
        sigma: dict[str, int] = {v: 0 for v in nodes}
        sigma[s] = 1
        dist: dict[str, int] = {v: -1 for v in nodes}
        dist[s] = 0
        queue: deque[str] = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adj_undirected.get(v, set()):
                # w found for the first time?
                if dist[w] < 0:
                    dist[w] = dist[v] + 1
                    queue.append(w)
                # shortest path to w via v?
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        # Accumulation
        delta: dict[str, float] = {v: 0.0 for v in nodes}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                frac = sigma[v] / sigma[w] if sigma[w] else 0.0
                delta[v] += frac * (1.0 + delta[w])
            if w != s:
                cb[w] += delta[w]

    # Normalize: for undirected graph, divide by 2/((n-1)*(n-2))
    # Brandes accumulates each pair twice for undirected, so divide by 2 first
    norm = (n - 1) * (n - 2)
    if norm > 0:
        for v in nodes:
            cb[v] = cb[v] / norm
    return cb


def _compute_degrees(adj_undirected: dict[str, set[str]]) -> dict[str, int]:
    """Compute degree for each node."""
    return {v: len(neighbors) for v, neighbors in adj_undirected.items()}


def _compute_out_degrees(adj: dict[str, list[tuple[str, float]]]) -> dict[str, int]:
    """R0 = out-degree in the DIRECTED dependency graph."""
    # First collect all nodes
    all_nodes: set[str] = set(adj.keys())
    for node in adj:
        for neighbor, _w in adj[node]:
            all_nodes.add(neighbor)

    out: dict[str, int] = {n: 0 for n in all_nodes}
    for node in adj:
        out[node] = len(adj[node])
    return out


# ── Main function ──────────────────────────────────────────────────

def compute_graph_metrics(
    adj: dict[str, list[tuple[str, float]]],
    temperatures: dict[str, float] | None = None,
    bottleneck_nodes: set[str] | None = None,
) -> tuple[dict[str, FileMetrics], GraphMetrics]:
    """
    Compute per-file and global graph metrics.

    Args:
        adj: directed weighted adjacency {node: [(neighbor, weight), ...]}
        temperatures: optional {node: temperature} from tree
        bottleneck_nodes: optional set of Cheeger bottleneck nodes

    Returns:
        (per_file_metrics: {node: FileMetrics}, global_metrics: GraphMetrics)
    """
    if temperatures is None:
        temperatures = {}
    if bottleneck_nodes is None:
        bottleneck_nodes = set()

    # Collect all nodes (some may only appear as targets)
    all_nodes: set[str] = set(adj.keys())
    for node in adj:
        for neighbor, _w in adj[node]:
            all_nodes.add(neighbor)

    n = len(all_nodes)

    # Handle trivial cases
    if n == 0:
        global_m = GraphMetrics(
            lambda_c=0.0, percolation_pc=0.0, regime="local",
            mean_degree=0.0, mean_sq_degree=0.0, num_nodes=0, num_edges=0,
        )
        return {}, global_m

    # Ensure all nodes are in adj
    for node in list(all_nodes):
        if node not in adj:
            adj[node] = []

    # Build undirected view
    undirected = _build_undirected(adj)

    # Degrees (undirected)
    degrees = _compute_degrees(undirected)
    max_degree = max(degrees.values()) if degrees else 1

    # R0 (directed out-degree)
    out_degrees = _compute_out_degrees(adj)

    # Betweenness (Brandes)
    betweenness = _brandes_betweenness(undirected)

    # Count edges (directed)
    num_edges = sum(len(neighbors) for neighbors in adj.values())

    # Degree stats (undirected)
    deg_values = list(degrees.values())
    mean_k = sum(deg_values) / n if n > 0 else 0.0
    mean_k2 = sum(d * d for d in deg_values) / n if n > 0 else 0.0

    # Epidemic threshold (Pastor-Satorras & Vespignani 2001)
    if mean_k2 > 0:
        lambda_c = mean_k / mean_k2
    else:
        lambda_c = 0.0

    regime = "systemic" if lambda_c < 0.05 else "local"

    # Percolation threshold (Molloy & Reed 1995)
    # kappa = <k^2>/<k>, p_c = 1/(kappa - 1)
    if mean_k > 0:
        kappa = mean_k2 / mean_k
        if kappa > 1:
            percolation_pc = 1.0 / (kappa - 1.0)
        else:
            percolation_pc = float('inf')
    else:
        percolation_pc = float('inf')

    # Build per-file metrics
    per_file: dict[str, FileMetrics] = {}
    for node in all_nodes:
        deg_c = degrees.get(node, 0) / max_degree if max_degree > 0 else 0.0
        per_file[node] = FileMetrics(
            file=node,
            r0=out_degrees.get(node, 0),
            degree_centrality=deg_c,
            betweenness_centrality=betweenness.get(node, 0.0),
            temperature=temperatures.get(node, 0.0),
            cheeger_bottleneck=node in bottleneck_nodes,
        )

    global_m = GraphMetrics(
        lambda_c=lambda_c,
        percolation_pc=percolation_pc,
        regime=regime,
        mean_degree=mean_k,
        mean_sq_degree=mean_k2,
        num_nodes=n,
        num_edges=num_edges,
    )

    return per_file, global_m
