"""
Tests for B-SCAN-04: R0 Calculator + Graph Metrics
====================================================
Covers: star graph, chain graph, complete graph, empty, single node,
        scale-free-like, regular graph, betweenness normalization.
"""

import sys
import os
import math

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest
from engine.core.scanner.r0_calculator import (
    compute_graph_metrics, FileMetrics, GraphMetrics,
)


# ── Helpers ────────────────────────────────────────────────────────

def _adj(*edges):
    """Build adjacency dict from (src, dst, weight) triples."""
    adj: dict[str, list[tuple[str, float]]] = {}
    for src, dst, w in edges:
        adj.setdefault(src, [])
        adj.setdefault(dst, [])
        adj[src].append((dst, w))
    return adj


def _bidir(*edges):
    """Build bidirectional adjacency from (a, b, weight) triples."""
    adj: dict[str, list[tuple[str, float]]] = {}
    for a, b, w in edges:
        adj.setdefault(a, [])
        adj.setdefault(b, [])
        adj[a].append((b, w))
        adj[b].append((a, w))
    return adj


# ── Test class ─────────────────────────────────────────────────────

class TestBSCAN04R0Calculator:

    # ── Star graph ─────────────────────────────────────────────────
    def test_star_graph_hub_highest_betweenness(self):
        """Star: hub connected to 5 leaves. Hub should have highest betweenness."""
        edges = []
        for i in range(5):
            edges.append(("hub", f"leaf{i}", 1.0))
        adj = _adj(*edges)

        per_file, gm = compute_graph_metrics(adj)

        # Hub has highest betweenness
        hub_b = per_file["hub"].betweenness_centrality
        for i in range(5):
            assert hub_b >= per_file[f"leaf{i}"].betweenness_centrality

    def test_star_graph_hub_highest_degree(self):
        """Star: hub has degree_centrality == 1.0."""
        edges = [("hub", f"leaf{i}", 1.0) for i in range(5)]
        adj = _adj(*edges)

        per_file, gm = compute_graph_metrics(adj)
        assert per_file["hub"].degree_centrality == 1.0

    def test_star_graph_r0(self):
        """Star: hub R0 = 5 (out-degree), leaves R0 = 0."""
        edges = [("hub", f"leaf{i}", 1.0) for i in range(5)]
        adj = _adj(*edges)

        per_file, gm = compute_graph_metrics(adj)
        assert per_file["hub"].r0 == 5
        for i in range(5):
            assert per_file[f"leaf{i}"].r0 == 0

    # ── Chain graph ────────────────────────────────────────────────
    def test_chain_middle_highest_betweenness(self):
        """Chain A->B->C->D: B and C should have highest betweenness."""
        adj = _adj(("A", "B", 1.0), ("B", "C", 1.0), ("C", "D", 1.0))

        per_file, gm = compute_graph_metrics(adj)

        b_bw = per_file["B"].betweenness_centrality
        c_bw = per_file["C"].betweenness_centrality
        a_bw = per_file["A"].betweenness_centrality
        d_bw = per_file["D"].betweenness_centrality

        # Middle nodes have higher betweenness than endpoints
        assert b_bw > a_bw
        assert c_bw > d_bw
        assert b_bw >= a_bw
        assert c_bw >= d_bw

    # ── Complete graph ─────────────────────────────────────────────
    def test_complete_graph_equal_betweenness(self):
        """Complete graph K5: all nodes should have equal betweenness."""
        nodes = ["A", "B", "C", "D", "E"]
        adj: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
        for i, a in enumerate(nodes):
            for j, b in enumerate(nodes):
                if i != j:
                    adj[a].append((b, 1.0))

        per_file, gm = compute_graph_metrics(adj)

        bws = [per_file[n].betweenness_centrality for n in nodes]
        # All should be equal (within float tolerance)
        for bw in bws:
            assert abs(bw - bws[0]) < 1e-10

    def test_complete_graph_all_degree_centrality_one(self):
        """Complete K5: all degree centralities should be 1.0."""
        nodes = ["A", "B", "C", "D", "E"]
        adj: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
        for i, a in enumerate(nodes):
            for j, b in enumerate(nodes):
                if i != j:
                    adj[a].append((b, 1.0))

        per_file, gm = compute_graph_metrics(adj)
        for n in nodes:
            assert abs(per_file[n].degree_centrality - 1.0) < 1e-10

    # ── Empty graph ────────────────────────────────────────────────
    def test_empty_graph(self):
        """Empty graph: no nodes, no edges."""
        per_file, gm = compute_graph_metrics({})

        assert per_file == {}
        assert gm.num_nodes == 0
        assert gm.num_edges == 0
        assert gm.regime == "local"

    # ── Single node ────────────────────────────────────────────────
    def test_single_node(self):
        """Single node, no edges."""
        adj = {"A": []}
        per_file, gm = compute_graph_metrics(adj)

        assert len(per_file) == 1
        assert per_file["A"].r0 == 0
        assert per_file["A"].betweenness_centrality == 0.0
        assert gm.num_nodes == 1
        assert gm.num_edges == 0

    # ── Scale-free-like graph ──────────────────────────────────────
    def test_scale_free_small_lambda_c(self):
        """
        Scale-free-like graph: one hub with many connections, most nodes
        with few. lambda_c should be small (< 0.15).
        """
        # Hub connects to 20 leaves; a few leaves interconnect
        adj: dict[str, list[tuple[str, float]]] = {"hub": []}
        for i in range(20):
            n = f"n{i}"
            adj.setdefault(n, [])
            adj["hub"].append((n, 1.0))
            adj[n].append(("hub", 1.0))

        # Add a few inter-leaf edges
        for i in range(0, 4):
            a, b = f"n{i}", f"n{i+1}"
            adj[a].append((b, 1.0))
            adj[b].append((a, 1.0))

        per_file, gm = compute_graph_metrics(adj)
        # Scale-free: high variance in degree -> small lambda_c
        assert gm.lambda_c < 0.15

    # ── Regular graph ──────────────────────────────────────────────
    def test_regular_graph_larger_lambda_c(self):
        """
        Regular ring graph: all nodes degree 2. lambda_c = <k>/<k^2> = 2/4 = 0.5.
        Should be "local" regime.
        """
        n = 10
        nodes = [f"n{i}" for i in range(n)]
        adj: dict[str, list[tuple[str, float]]] = {nd: [] for nd in nodes}
        for i in range(n):
            a, b = nodes[i], nodes[(i + 1) % n]
            adj[a].append((b, 1.0))
            adj[b].append((a, 1.0))

        per_file, gm = compute_graph_metrics(adj)
        # Regular: mean_k=2, mean_k2=4, lambda_c=0.5
        assert abs(gm.lambda_c - 0.5) < 0.01
        assert gm.regime == "local"

    # ── Betweenness normalized 0-1 ─────────────────────────────────
    def test_betweenness_normalized_0_1(self):
        """All betweenness values should be in [0, 1]."""
        # Moderately complex graph
        adj = _bidir(
            ("A", "B", 1.0), ("B", "C", 1.0), ("C", "D", 1.0),
            ("A", "D", 1.0), ("B", "D", 1.0), ("C", "E", 1.0),
            ("E", "F", 1.0), ("F", "A", 1.0),
        )

        per_file, gm = compute_graph_metrics(adj)
        for node, fm in per_file.items():
            assert 0.0 <= fm.betweenness_centrality <= 1.0, \
                f"{node} betweenness {fm.betweenness_centrality} out of [0,1]"

    # ── Temperature and bottleneck passthrough ─────────────────────
    def test_temperature_passthrough(self):
        """Temperature values are passed through from input."""
        adj = _adj(("A", "B", 1.0))
        temps = {"A": 0.8, "B": 0.2}
        per_file, gm = compute_graph_metrics(adj, temperatures=temps)

        assert per_file["A"].temperature == 0.8
        assert per_file["B"].temperature == 0.2

    def test_bottleneck_passthrough(self):
        """Cheeger bottleneck flags are passed through."""
        adj = _adj(("A", "B", 1.0), ("B", "C", 1.0))
        bn = {"B"}
        per_file, gm = compute_graph_metrics(adj, bottleneck_nodes=bn)

        assert per_file["B"].cheeger_bottleneck is True
        assert per_file["A"].cheeger_bottleneck is False
        assert per_file["C"].cheeger_bottleneck is False

    # ── Global metrics consistency ─────────────────────────────────
    def test_global_num_nodes_edges(self):
        """num_nodes and num_edges match the graph."""
        adj = _adj(
            ("A", "B", 1.0), ("B", "C", 1.0), ("A", "C", 1.0),
        )
        per_file, gm = compute_graph_metrics(adj)

        assert gm.num_nodes == 3
        assert gm.num_edges == 3  # 3 directed edges

    def test_percolation_regular_ring(self):
        """Regular ring: kappa = <k^2>/<k> = 4/2 = 2, p_c = 1/(2-1) = 1.0."""
        n = 8
        nodes = [f"n{i}" for i in range(n)]
        adj: dict[str, list[tuple[str, float]]] = {nd: [] for nd in nodes}
        for i in range(n):
            a, b = nodes[i], nodes[(i + 1) % n]
            adj[a].append((b, 1.0))
            adj[b].append((a, 1.0))

        per_file, gm = compute_graph_metrics(adj)
        assert abs(gm.percolation_pc - 1.0) < 0.01

    def test_percolation_inf_on_isolated(self):
        """Single node: percolation_pc should be inf."""
        adj = {"A": []}
        per_file, gm = compute_graph_metrics(adj)
        assert gm.percolation_pc == float('inf')

    # ── Dataclass fields ───────────────────────────────────────────
    def test_file_metrics_fields(self):
        """FileMetrics has all required fields."""
        fm = FileMetrics("test.py", 3, 0.5, 0.1, 0.8, True)
        assert fm.file == "test.py"
        assert fm.r0 == 3
        assert fm.degree_centrality == 0.5
        assert fm.betweenness_centrality == 0.1
        assert fm.temperature == 0.8
        assert fm.cheeger_bottleneck is True

    def test_graph_metrics_fields(self):
        """GraphMetrics has all required fields."""
        gm = GraphMetrics(0.05, 0.3, "local", 2.0, 6.0, 10, 20)
        assert gm.lambda_c == 0.05
        assert gm.percolation_pc == 0.3
        assert gm.regime == "local"
        assert gm.mean_degree == 2.0
        assert gm.mean_sq_degree == 6.0
        assert gm.num_nodes == 10
        assert gm.num_edges == 20


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
