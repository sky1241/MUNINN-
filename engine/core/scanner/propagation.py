"""
B-SCAN-10: Propagation Engine (DebtRank + Heat Kernel)
=======================================================
Computes blast radius per finding using epidemic propagation on dependency graphs.

INPUT:  confirmed findings + dependency graph + file_metrics from B-SCAN-04
OUTPUT: blast radius per finding {finding_id, impacted_files, systemic_loss}

Algorithms:
- DebtRank (Battiston et al. 2012) — pure Python, default
- Heat Kernel (Kondor & Lafferty 2002) — requires scipy, fallback to DebtRank
- Competing Epidemics ordering (Prakash et al. 2012)
- Influence Minimization — greedy patching

Pure Python for DebtRank. numpy/scipy OPTIONAL for Heat Kernel.
"""

from __future__ import annotations

import math
import sys
import os
from dataclasses import dataclass, field

# ── Triple import fallback ─────────────────────────────────────────
try:
    from engine.core.scanner import __name__ as _pkg_check
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.normpath(os.path.join(_here, '..', '..', '..'))
    if _root not in sys.path:
        sys.path.insert(0, _root)

# ── Optional scipy/numpy ──────────────────────────────────────────
try:
    import numpy as np
    from scipy.sparse import csr_matrix
    from scipy.sparse.linalg import expm_multiply
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── Dataclasses ───────────────────────────────────────────────────

@dataclass
class BlastRadius:
    finding_id: str
    infected_file: str
    impacted_files: dict[str, float]   # {file: impact_probability}
    systemic_loss: float
    method: str                         # "debtrank" | "heat_kernel"


@dataclass
class PropagationResult:
    blast_radii: list[BlastRadius]
    regime: str                         # "local" | "systemic"
    lambda_c: float
    percolation_pc: float
    patch_order: list[str]             # finding_ids ordered by propagation strength


# ── Helpers ───────────────────────────────────────────────────────

def _collect_all_nodes(graph: dict[str, list[str]]) -> set[str]:
    """Collect all nodes from adjacency list (sources + targets)."""
    nodes: set[str] = set(graph.keys())
    for neighbors in graph.values():
        for n in neighbors:
            nodes.add(n)
    return nodes


def _build_reverse(graph: dict[str, list[str]]) -> dict[str, list[str]]:
    """Build reverse adjacency: if A->B in graph, then B->A in reverse."""
    rev: dict[str, list[str]] = {}
    for node, neighbors in graph.items():
        if node not in rev:
            rev[node] = []
        for n in neighbors:
            if n not in rev:
                rev[n] = []
            rev[n].append(node)
    return rev


def _normalize_weights(
    graph: dict[str, list[str]],
) -> dict[str, dict[str, float]]:
    """
    Build normalized weight matrix W[j][i] for DebtRank.
    W[j][i] = 1 / out_degree(j) for each edge j->i.
    Returns {source: {target: weight}}.
    """
    w: dict[str, dict[str, float]] = {}
    for node, neighbors in graph.items():
        deg = len(neighbors)
        if deg > 0:
            weight = 1.0 / deg
            w[node] = {n: weight for n in neighbors}
        else:
            w[node] = {}
    return w


# ── DebtRank (Battiston 2012) ────────────────────────────────────

def debtrank(
    graph: dict[str, list[str]],
    infected_files: list[str],
    importance: dict[str, float] | None = None,
    max_rounds: int = 20,
) -> dict[str, float]:
    """
    DebtRank propagation. Pure Python, no external deps.

    Args:
        graph: adjacency list {node: [neighbor, ...]}
        infected_files: initial infected nodes (stress=1.0)
        importance: {file: importance_value} for systemic loss (unused in propagation itself)
        max_rounds: max iterations (converges in 5-10 typically)

    Returns:
        {file: stress} where stress in [0.0, 1.0]
    """
    all_nodes = _collect_all_nodes(graph)
    if not all_nodes:
        return {}

    # Ensure all nodes in graph
    for node in list(all_nodes):
        if node not in graph:
            graph[node] = []

    # Normalized weights
    W = _normalize_weights(graph)

    # Build reverse map for efficient lookup: who points TO i?
    reverse = _build_reverse(graph)

    # Initialize stress
    h: dict[str, float] = {n: 0.0 for n in all_nodes}
    # Track which nodes have been "inactive" (already fully propagated)
    inactive: set[str] = set()

    for f in infected_files:
        if f in h:
            h[f] = 1.0
            inactive.add(f)

    for _t in range(max_rounds):
        h_prev = dict(h)
        changed = False

        for i in all_nodes:
            if i in inactive:
                continue
            # DebtRank formula:
            # h_i(t+1) = min(1, h_i(t) + sum(W_ji * h_j(t) * (1 - h_prev_j_before_infected)))
            # The (1 - h_prev[j]) term means only the NEW stress from j contributes
            contribution = 0.0
            for j in reverse.get(i, []):
                w_ji = W.get(j, {}).get(i, 0.0)
                # Newly active j: contributes proportional to its stress
                contribution += w_ji * h[j]

            new_h = min(1.0, h_prev[i] + contribution)
            if abs(new_h - h_prev[i]) > 1e-12:
                changed = True
            h[i] = new_h

            # Once a node reaches 1.0, mark inactive
            if h[i] >= 1.0:
                inactive.add(i)

        if not changed:
            break

    return h


# ── Heat Kernel (Kondor & Lafferty 2002) ─────────────────────────

def heat_kernel(
    graph: dict[str, list[str]],
    infected_files: list[str],
    laplacian: object | None = None,
    t: float = 1.0,
) -> dict[str, float]:
    """
    Heat Kernel diffusion. Requires scipy.

    u(t) = expm(-t * L) @ u(0)

    If scipy not available, falls back to debtrank.

    Args:
        graph: adjacency list {node: [neighbor, ...]}
        infected_files: initial infected nodes
        laplacian: precomputed Laplacian (unused, we build our own)
        t: diffusion time parameter

    Returns:
        {file: impact_probability}
    """
    if not HAS_SCIPY:
        return debtrank(graph, infected_files)

    all_nodes = _collect_all_nodes(graph)
    if not all_nodes:
        return {}

    # Ensure all nodes in graph
    for node in list(all_nodes):
        if node not in graph:
            graph[node] = []

    nodes = sorted(all_nodes)
    n = len(nodes)
    idx = {node: i for i, node in enumerate(nodes)}

    # Build adjacency matrix
    rows, cols, data = [], [], []
    for src, neighbors in graph.items():
        for dst in neighbors:
            rows.append(idx[src])
            cols.append(idx[dst])
            data.append(1.0)

    A = csr_matrix((data, (rows, cols)), shape=(n, n))

    # Symmetrize for Laplacian (undirected view)
    A_sym = A + A.T
    A_sym.data[:] = np.minimum(A_sym.data, 1.0)  # cap at 1

    # Degree matrix
    degrees = np.array(A_sym.sum(axis=1)).flatten()
    D = csr_matrix((degrees, (range(n), range(n))), shape=(n, n))

    # Laplacian L = D - A
    L = D - A_sym

    # Initial vector
    u0 = np.zeros(n)
    for f in infected_files:
        if f in idx:
            u0[idx[f]] = 1.0

    # u(t) = expm(-t * L) @ u(0)
    u_t = expm_multiply(-t * L, u0)

    # Clamp to [0, 1]
    u_t = np.clip(u_t, 0.0, 1.0)

    return {node: float(u_t[idx[node]]) for node in nodes}


# ── Importance ────────────────────────────────────────────────────

def compute_importance(
    file_metrics: dict[str, dict],
) -> dict[str, float]:
    """
    Compute importance v_i = LOC * temperature * degree / max.

    file_metrics: {filename: {loc: int, temperature: float, degree: int, ...}}

    Returns {filename: importance} normalized to [0, 1].
    """
    if not file_metrics:
        return {}

    raw: dict[str, float] = {}
    for fname, metrics in file_metrics.items():
        loc = metrics.get('loc', 0)
        temp = metrics.get('temperature', 0.0)
        degree = metrics.get('degree', 0)
        raw[fname] = loc * temp * degree

    max_val = max(raw.values()) if raw else 1.0
    if max_val <= 0:
        # All zero importance — return uniform small values
        return {f: 0.0 for f in raw}

    return {f: v / max_val for f, v in raw.items()}


# ── Competing Epidemics (Prakash 2012) ────────────────────────────

def _spectral_radius(graph: dict[str, list[str]]) -> float:
    """
    Compute spectral radius (largest eigenvalue) of adjacency matrix.
    Uses power iteration (pure Python) if no numpy, exact if numpy available.
    """
    all_nodes = _collect_all_nodes(graph)
    if not all_nodes:
        return 0.0

    nodes = sorted(all_nodes)
    n = len(nodes)
    idx = {node: i for i, node in enumerate(nodes)}

    if n <= 1:
        return 0.0

    if HAS_SCIPY and n > 0:
        rows, cols, data = [], [], []
        for src, neighbors in graph.items():
            for dst in neighbors:
                rows.append(idx[src])
                cols.append(idx[dst])
                data.append(1.0)
        if not data:
            return 0.0
        A = csr_matrix((data, (rows, cols)), shape=(n, n))
        # Symmetrize
        A_sym = A + A.T
        try:
            from scipy.sparse.linalg import eigsh
            vals = eigsh(A_sym.astype(float), k=min(1, n - 1), which='LM', return_eigenvectors=False)
            return float(max(abs(v) for v in vals)) if len(vals) > 0 else 0.0
        except Exception:
            pass

    # Fallback: power iteration (pure Python)
    # Build adjacency as dict of dicts for fast multiply
    adj_dict: dict[int, list[int]] = {i: [] for i in range(n)}
    for src, neighbors in graph.items():
        si = idx[src]
        for dst in neighbors:
            adj_dict[si].append(idx[dst])
            adj_dict.setdefault(idx[dst], [])

    # Symmetrize
    sym: dict[int, set[int]] = {i: set() for i in range(n)}
    for i, js in adj_dict.items():
        for j in js:
            sym[i].add(j)
            sym[j].add(i)

    # Power iteration
    x = [1.0 / math.sqrt(n)] * n
    for _ in range(50):
        y = [0.0] * n
        for i in range(n):
            for j in sym[i]:
                y[i] += x[j]
        norm = math.sqrt(sum(v * v for v in y))
        if norm < 1e-15:
            return 0.0
        x = [v / norm for v in y]
        # Rayleigh quotient
        num = sum(y[i] * x[i] for i in range(n))
        # x is already normalized, so lambda ~ norm
    return norm if n > 0 else 0.0


def competing_epidemics_order(
    findings: list[dict],
    blast_radii: list[BlastRadius],
) -> list[str]:
    """
    Order findings by propagation strength (Prakash 2012).
    Higher beta * lambda_1 / delta => propagates first => patch first.

    findings: list of {id, file, severity, ...}
    blast_radii: computed blast radii

    Returns: list of finding_ids ordered by propagation strength (strongest first).
    """
    if not findings or not blast_radii:
        return []

    # Map finding_id -> blast_radius
    br_map = {br.finding_id: br for br in blast_radii}

    scored: list[tuple[float, str]] = []
    for f in findings:
        fid = f.get('id', '')
        br = br_map.get(fid)
        if br is None:
            scored.append((0.0, fid))
            continue
        # Use systemic_loss as proxy for beta * lambda_1 / delta
        scored.append((br.systemic_loss, fid))

    scored.sort(key=lambda x: -x[0])
    return [fid for _, fid in scored]


# ── Influence Minimization ────────────────────────────────────────

def influence_minimization(
    graph: dict[str, list[str]],
    file_metrics: dict[str, dict],
    k: int = 10,
    method: str = "debtrank",
) -> list[str]:
    """
    Greedy influence minimization: pick k files to patch that maximize
    systemic_loss reduction.

    Strategy: iteratively pick the file whose removal from the graph
    causes the largest drop in total systemic loss.

    Returns: list of k file paths to patch (ordered by impact).
    """
    all_nodes = _collect_all_nodes(graph)
    if not all_nodes:
        return []

    importance = compute_importance(file_metrics)
    patched: list[str] = []
    remaining_graph = {n: list(neighbors) for n, neighbors in graph.items()}
    for n in all_nodes:
        if n not in remaining_graph:
            remaining_graph[n] = []

    for _ in range(min(k, len(all_nodes))):
        best_file = None
        best_reduction = -1.0

        # Compute baseline loss: infect each node, sum weighted stress
        # For efficiency, use total importance-weighted degree as proxy
        candidates = [n for n in _collect_all_nodes(remaining_graph) if n not in patched]
        if not candidates:
            break

        for candidate in candidates:
            # Simulate removing candidate: what's the total outgoing impact?
            # Proxy: importance * out_degree
            out_deg = len(remaining_graph.get(candidate, []))
            imp = importance.get(candidate, 0.0)
            score = imp * (out_deg + 1)  # +1 for the node itself

            if score > best_reduction:
                best_reduction = score
                best_file = candidate

        if best_file is None:
            break

        patched.append(best_file)
        # Remove node from graph
        remaining_graph.pop(best_file, None)
        for n in remaining_graph:
            remaining_graph[n] = [nb for nb in remaining_graph[n] if nb != best_file]

    return patched


# ── Main orchestrator ─────────────────────────────────────────────

def propagate_findings(
    findings: list[dict],
    graph: dict[str, list[str]],
    file_metrics: dict[str, dict],
    method: str = "auto",
) -> PropagationResult:
    """
    Main entry point. Compute blast radius for each finding.

    Args:
        findings: list of {id: str, file: str, severity: str, ...}
        graph: adjacency list {node: [neighbor, ...]}
        file_metrics: {filename: {loc, temperature, degree, ...}}
        method: "auto" (heat_kernel with debtrank fallback), "debtrank", "heat_kernel"

    Returns:
        PropagationResult with blast_radii, regime, lambda_c, percolation_pc, patch_order
    """
    all_nodes = _collect_all_nodes(graph)

    # Compute global graph stats for regime classification
    degrees = {n: len(graph.get(n, [])) for n in all_nodes}
    n = len(all_nodes)

    if n > 0:
        deg_vals = list(degrees.values())
        mean_k = sum(deg_vals) / n
        mean_k2 = sum(d * d for d in deg_vals) / n
        lambda_c = mean_k / mean_k2 if mean_k2 > 0 else 0.0
        regime = "systemic" if lambda_c < 0.05 else "local"

        if mean_k > 0:
            kappa = mean_k2 / mean_k
            percolation_pc = 1.0 / (kappa - 1.0) if kappa > 1 else float('inf')
        else:
            percolation_pc = float('inf')
    else:
        lambda_c = 0.0
        percolation_pc = 0.0
        regime = "local"

    if not findings:
        return PropagationResult(
            blast_radii=[],
            regime=regime,
            lambda_c=lambda_c,
            percolation_pc=percolation_pc,
            patch_order=[],
        )

    importance = compute_importance(file_metrics)

    # Choose method
    use_heat = False
    if method == "auto":
        use_heat = HAS_SCIPY
    elif method == "heat_kernel":
        use_heat = HAS_SCIPY  # fallback to debtrank if no scipy
    # method == "debtrank" => use_heat stays False

    method_name = "heat_kernel" if use_heat else "debtrank"
    propagate_fn = heat_kernel if use_heat else debtrank

    blast_radii: list[BlastRadius] = []

    for finding in findings:
        fid = finding.get('id', 'unknown')
        infected_file = finding.get('file', '')

        if not infected_file:
            blast_radii.append(BlastRadius(
                finding_id=fid,
                infected_file='',
                impacted_files={},
                systemic_loss=0.0,
                method=method_name,
            ))
            continue

        # Make a copy of graph to avoid mutation
        g_copy = {n: list(neighbors) for n, neighbors in graph.items()}
        for node in all_nodes:
            if node not in g_copy:
                g_copy[node] = []

        stress = propagate_fn(g_copy, [infected_file])

        # Filter to nodes with non-trivial stress
        impacted = {f: s for f, s in stress.items() if s > 1e-6}

        # Systemic loss = sum(h[i] * v[i])
        sys_loss = sum(
            stress.get(f, 0.0) * importance.get(f, 0.0)
            for f in stress
        )

        blast_radii.append(BlastRadius(
            finding_id=fid,
            infected_file=infected_file,
            impacted_files=impacted,
            systemic_loss=sys_loss,
            method=method_name,
        ))

    patch_order = competing_epidemics_order(findings, blast_radii)

    return PropagationResult(
        blast_radii=blast_radii,
        regime=regime,
        lambda_c=lambda_c,
        percolation_pc=percolation_pc,
        patch_order=patch_order,
    )
