"""
Tests for B-SCAN-10: Propagation Engine (DebtRank + Heat Kernel)
================================================================
Covers: debtrank, heat_kernel, compute_importance, propagate_findings,
        competing_epidemics_order, influence_minimization, dataclasses,
        edge cases (cycles, empty, isolated).
"""

import sys
import os
import math

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest
from engine.core.scanner.propagation import (
    BlastRadius,
    PropagationResult,
    debtrank,
    heat_kernel,
    compute_importance,
    propagate_findings,
    competing_epidemics_order,
    influence_minimization,
    HAS_SCIPY,
)


# ── Helpers ────────────────────────────────────────────────────────

def _graph(*edges):
    """Build adjacency list from (src, dst) pairs."""
    g: dict[str, list[str]] = {}
    for src, dst in edges:
        g.setdefault(src, [])
        g.setdefault(dst, [])
        g[src].append(dst)
    return g


def _star_graph(hub, leaves):
    """Star: hub -> all leaves."""
    edges = [(hub, leaf) for leaf in leaves]
    return _graph(*edges)


def _chain_graph(nodes):
    """Chain: A->B->C->..."""
    edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
    return _graph(*edges)


def _bidir_graph(*edges):
    """Bidirectional graph from (a, b) pairs."""
    all_edges = []
    for a, b in edges:
        all_edges.append((a, b))
        all_edges.append((b, a))
    return _graph(*all_edges)


def _file_metrics(**kwargs):
    """Build file_metrics dict. kwargs: filename=(loc, temp, degree)."""
    return {
        name: {'loc': vals[0], 'temperature': vals[1], 'degree': vals[2]}
        for name, vals in kwargs.items()
    }


# ── Test class ─────────────────────────────────────────────────────

class TestDebtRank:

    def test_single_infected_star_hub_high_stress(self):
        """Star graph: infect hub -> leaves get stress."""
        g = _star_graph("hub", ["L1", "L2", "L3", "L4", "L5"])
        stress = debtrank(g, ["hub"])
        assert stress["hub"] == 1.0
        # Leaves should have positive stress (hub propagates to them)
        for leaf in ["L1", "L2", "L3", "L4", "L5"]:
            assert stress[leaf] > 0.0

    def test_isolated_node_stays_zero(self):
        """Isolated node not connected to infected -> stress stays 0."""
        g = _graph(("A", "B"))
        g["ISOLATED"] = []
        stress = debtrank(g, ["A"])
        assert stress["ISOLATED"] == 0.0

    def test_chain_a_b_c_infect_a(self):
        """Chain A->B->C: infect A. B should get stress, C should get some."""
        g = _chain_graph(["A", "B", "C"])
        stress = debtrank(g, ["A"])
        assert stress["A"] == 1.0
        assert stress["B"] > 0.0
        assert stress["C"] > 0.0
        # B should be >= C (closer to source)
        assert stress["B"] >= stress["C"]

    def test_converges(self):
        """Stress values stabilize (no oscillation)."""
        g = _bidir_graph(("A", "B"), ("B", "C"), ("C", "D"))
        stress1 = debtrank(g, ["A"], max_rounds=5)
        stress2 = debtrank(g, ["A"], max_rounds=50)
        # Should converge — results with more rounds shouldn't change much
        for node in stress1:
            assert abs(stress1[node] - stress2[node]) < 0.1

    def test_stress_capped_at_one(self):
        """h capped at 1.0 even with many incoming edges."""
        # Complete graph: everyone points to everyone
        nodes = ["A", "B", "C", "D"]
        edges = [(a, b) for a in nodes for b in nodes if a != b]
        g = _graph(*edges)
        stress = debtrank(g, ["A"])
        for node in nodes:
            assert stress[node] <= 1.0

    def test_empty_graph(self):
        """Empty graph -> empty result."""
        stress = debtrank({}, ["A"])
        assert stress == {}

    def test_no_infected_files(self):
        """No infected files -> all stress 0."""
        g = _graph(("A", "B"))
        stress = debtrank(g, [])
        assert stress["A"] == 0.0
        assert stress["B"] == 0.0

    def test_graph_with_cycle_no_infinite_loop(self):
        """Graph with cycle A->B->C->A should not loop forever."""
        g = _graph(("A", "B"), ("B", "C"), ("C", "A"))
        stress = debtrank(g, ["A"], max_rounds=20)
        # Should complete and all nodes have stress
        assert len(stress) == 3
        for node in ["A", "B", "C"]:
            assert 0.0 <= stress[node] <= 1.0


class TestHeatKernel:

    def test_fallback_to_debtrank_no_scipy(self):
        """If scipy not available, heat_kernel falls back to debtrank."""
        import engine.core.scanner.propagation as prop
        orig = prop.HAS_SCIPY
        try:
            prop.HAS_SCIPY = False
            g = _chain_graph(["A", "B", "C"])
            result = heat_kernel(g, ["A"])
            # Should still return valid results (via debtrank fallback)
            assert "A" in result
            assert result["A"] == 1.0
        finally:
            prop.HAS_SCIPY = orig

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_heat_kernel_star_hub_high(self):
        """Heat kernel on star graph: hub infected -> leaves impacted."""
        g = _star_graph("hub", ["L1", "L2", "L3"])
        # Make bidirectional for heat diffusion
        g = _bidir_graph(("hub", "L1"), ("hub", "L2"), ("hub", "L3"))
        result = heat_kernel(g, ["hub"])
        assert result["hub"] > 0.0
        for leaf in ["L1", "L2", "L3"]:
            assert result[leaf] > 0.0

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_heat_kernel_chain(self):
        """Heat kernel on chain: A->B->C, infect A."""
        g = _chain_graph(["A", "B", "C"])
        result = heat_kernel(g, ["A"])
        assert result["A"] > 0.0

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_heat_kernel_empty_graph(self):
        """Heat kernel on empty graph -> empty."""
        result = heat_kernel({}, ["A"])
        assert result == {}

    @pytest.mark.skipif(not HAS_SCIPY, reason="scipy not installed")
    def test_heat_kernel_cycle_no_infinite_loop(self):
        """Heat kernel with cycle should complete."""
        g = _graph(("A", "B"), ("B", "C"), ("C", "A"))
        result = heat_kernel(g, ["A"])
        assert len(result) == 3
        for v in result.values():
            assert 0.0 <= v <= 1.0


class TestComputeImportance:

    def test_high_loc_temp_degree_highest(self):
        """File with high LOC*temp*degree -> highest importance."""
        metrics = _file_metrics(
            core=(5000, 0.9, 30),
            test=(100, 0.1, 2),
        )
        imp = compute_importance(metrics)
        assert imp["core"] > imp["test"]
        assert abs(imp["core"] - 1.0) < 1e-6  # normalized to 1

    def test_empty_metrics(self):
        """Empty metrics -> empty dict."""
        assert compute_importance({}) == {}

    def test_all_zero(self):
        """All-zero metrics -> all zero importance."""
        metrics = _file_metrics(a=(0, 0.0, 0), b=(0, 0.0, 0))
        imp = compute_importance(metrics)
        assert imp["a"] == 0.0
        assert imp["b"] == 0.0


class TestPropagateFindings:

    def test_empty_findings(self):
        """Empty findings -> empty result."""
        g = _graph(("A", "B"))
        result = propagate_findings([], g, {})
        assert result.blast_radii == []
        assert result.patch_order == []

    def test_single_crit_finding(self):
        """Single CRIT finding -> blast radius computed."""
        g = _bidir_graph(("core", "util"), ("core", "auth"), ("auth", "db"))
        metrics = _file_metrics(
            core=(5000, 0.9, 3),
            util=(200, 0.3, 1),
            auth=(3000, 0.8, 2),
            db=(1000, 0.5, 1),
        )
        findings = [{'id': 'F1', 'file': 'core', 'severity': 'CRIT'}]
        result = propagate_findings(findings, g, metrics, method="debtrank")
        assert len(result.blast_radii) == 1
        br = result.blast_radii[0]
        assert br.finding_id == 'F1'
        assert br.infected_file == 'core'
        assert len(br.impacted_files) > 0
        assert br.systemic_loss > 0.0
        assert br.method == "debtrank"

    def test_multiple_findings(self):
        """Multiple findings -> multiple blast radii."""
        g = _chain_graph(["A", "B", "C", "D"])
        findings = [
            {'id': 'F1', 'file': 'A', 'severity': 'CRIT'},
            {'id': 'F2', 'file': 'D', 'severity': 'HIGH'},
        ]
        result = propagate_findings(findings, g, {}, method="debtrank")
        assert len(result.blast_radii) == 2
        ids = [br.finding_id for br in result.blast_radii]
        assert 'F1' in ids
        assert 'F2' in ids

    def test_systemic_loss_core_more_than_test(self):
        """Core files contribute more to systemic_loss than test files."""
        # Directed graph: core -> auth, core -> db (core is hub)
        # test1 is isolated leaf (no outgoing edges to important nodes)
        # Infecting core propagates to auth+db; infecting test1 goes nowhere.
        g = _graph(
            ("core", "auth"), ("core", "db"),
        )
        g["test1"] = []  # isolated leaf
        metrics = _file_metrics(
            core=(5000, 0.9, 2),
            auth=(3000, 0.8, 1),
            db=(1000, 0.5, 1),
            test1=(50, 0.1, 0),
        )
        findings_core = [{'id': 'F1', 'file': 'core', 'severity': 'CRIT'}]
        findings_test = [{'id': 'F2', 'file': 'test1', 'severity': 'CRIT'}]

        r_core = propagate_findings(findings_core, dict(g), metrics, method="debtrank")
        r_test = propagate_findings(findings_test, dict(g), metrics, method="debtrank")

        loss_core = r_core.blast_radii[0].systemic_loss
        loss_test = r_test.blast_radii[0].systemic_loss
        # Core infection reaches auth+db (high importance). test1 reaches nothing.
        assert loss_core > loss_test

    def test_empty_graph_empty_result(self):
        """Empty graph -> result with empty blast radii."""
        result = propagate_findings(
            [{'id': 'F1', 'file': 'X', 'severity': 'HIGH'}],
            {},
            {},
        )
        # File X not in graph => blast radius with no impacted files
        assert len(result.blast_radii) == 1

    def test_regime_field(self):
        """Result has regime field."""
        g = _graph(("A", "B"))
        result = propagate_findings([], g, {})
        assert result.regime in ("local", "systemic")

    def test_lambda_c_and_percolation(self):
        """Result has lambda_c and percolation_pc."""
        g = _graph(("A", "B"))
        result = propagate_findings([], g, {})
        assert isinstance(result.lambda_c, float)
        assert isinstance(result.percolation_pc, float)


class TestInfluenceMinimization:

    def test_returns_k_files(self):
        """Returns at most k files."""
        g = _bidir_graph(("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"))
        metrics = _file_metrics(
            A=(100, 0.5, 1), B=(200, 0.7, 2),
            C=(300, 0.8, 2), D=(200, 0.6, 2), E=(100, 0.4, 1),
        )
        result = influence_minimization(g, metrics, k=3)
        assert len(result) <= 3
        assert len(result) > 0

    def test_patching_hub_first(self):
        """Hub with most connections and importance should be patched first."""
        g = _bidir_graph(
            ("hub", "L1"), ("hub", "L2"), ("hub", "L3"),
            ("hub", "L4"), ("hub", "L5"),
        )
        metrics = _file_metrics(
            hub=(5000, 0.9, 5),
            L1=(100, 0.1, 1), L2=(100, 0.1, 1), L3=(100, 0.1, 1),
            L4=(100, 0.1, 1), L5=(100, 0.1, 1),
        )
        result = influence_minimization(g, metrics, k=1)
        assert result[0] == "hub"

    def test_empty_graph(self):
        """Empty graph -> empty result."""
        result = influence_minimization({}, {}, k=5)
        assert result == []


class TestCompetingEpidemicsOrder:

    def test_highest_propagation_first(self):
        """Finding with highest systemic_loss should be first."""
        findings = [
            {'id': 'F1', 'file': 'A'},
            {'id': 'F2', 'file': 'B'},
        ]
        blast_radii = [
            BlastRadius('F1', 'A', {'A': 1.0}, systemic_loss=0.2, method='debtrank'),
            BlastRadius('F2', 'B', {'B': 1.0, 'C': 0.5}, systemic_loss=0.8, method='debtrank'),
        ]
        order = competing_epidemics_order(findings, blast_radii)
        assert order[0] == 'F2'
        assert order[1] == 'F1'

    def test_empty_findings(self):
        """Empty findings -> empty order."""
        assert competing_epidemics_order([], []) == []


class TestDataclasses:

    def test_blast_radius_fields(self):
        """BlastRadius has all expected fields."""
        br = BlastRadius(
            finding_id='F1',
            infected_file='core.py',
            impacted_files={'core.py': 1.0, 'util.py': 0.5},
            systemic_loss=0.75,
            method='debtrank',
        )
        assert br.finding_id == 'F1'
        assert br.infected_file == 'core.py'
        assert br.impacted_files == {'core.py': 1.0, 'util.py': 0.5}
        assert br.systemic_loss == 0.75
        assert br.method == 'debtrank'

    def test_propagation_result_fields(self):
        """PropagationResult has all expected fields."""
        pr = PropagationResult(
            blast_radii=[],
            regime='local',
            lambda_c=0.1,
            percolation_pc=0.5,
            patch_order=['F1'],
        )
        assert pr.blast_radii == []
        assert pr.regime == 'local'
        assert pr.lambda_c == 0.1
        assert pr.percolation_pc == 0.5
        assert pr.patch_order == ['F1']
