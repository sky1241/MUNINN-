#!/usr/bin/env python3
"""Muninn Mycelium — Thematic zones (Laplacian spectral clustering) mixin.

H6 chunk 2 (2026-05-09): extracted from engine/core/mycelium.py.
Mixed into Mycelium via multiple inheritance. No behavior change.

Public API exposed by this mixin:
  - Mycelium.detect_zones(k=None)        → {zone_name: [concept, ...]}
  - Mycelium.auto_label_zones(k=None)    → tags edges with zone (side-effect)
  - Mycelium.get_zones()                 → {zone_name: count}
  - Mycelium.get_bridges()               → [(a, b, [zones], weight), ...]
  - Mycelium._count_total_zones()        → int (cached)
  - Mycelium._invalidate_zone_cache()    → None

Internal helpers:
  - _bfs_zones()       — connected-component fallback when scipy missing
  - _graph_entropy()   — Shannon entropy of degree distribution

Dependencies on core mixin: self._db, self.data, self._key,
self.effective_weight, self._spectral_gap (set here).

Heavy imports (numpy/scipy/sklearn) are lazy inside detect_zones.
"""
from __future__ import annotations

import sys


class _MyceliumZonesMixin:
    """Spectral zone detection + labelling + bridges + cache helpers."""

    # ── Zone count cache ─────────────────────────────────────────

    def _count_total_zones(self) -> int:
        """Count distinct zones across all connections."""
        if self._db is not None:
            if not hasattr(self, '_zone_cache_count'):
                self._zone_cache_count = self._db.count_total_zones()
            return self._zone_cache_count
        if not hasattr(self, '_zone_cache_count'):
            all_zones = set()
            for conn in self.data["connections"].values():
                if "zones" in conn:
                    all_zones.update(conn["zones"])
            self._zone_cache_count = max(1, len(all_zones))
        return self._zone_cache_count

    def _invalidate_zone_cache(self):
        """Clear zone count cache (call after observe/merge)."""
        if hasattr(self, '_zone_cache_count'):
            del self._zone_cache_count

    # ── P20.5 + P20.6: spectral zone detection ───────────────────

    def detect_zones(self, k: int = None) -> dict[str, list[str]]:
        """P20.5+6: Laplacien spectral clustering — detect semantic zones.

        Builds co-occurrence matrix from connections, computes normalized
        Laplacian, extracts K eigenvectors, clusters with KMeans.
        Auto-names each zone by its dominant concepts (P20.6).

        Returns {zone_name: [concept1, concept2, ...]}.
        Requires numpy + scipy + sklearn. Graceful fallback if not installed.
        """
        if self._db is not None:
            n_conns = self._db.connection_count()
        else:
            n_conns = len(self.data["connections"])
        if n_conns < 10:
            return {}

        try:
            import numpy as np
            from scipy import sparse
            from scipy.sparse.linalg import eigsh
            from sklearn.cluster import KMeans
        except ImportError:
            # BUGFIX: tenir la promesse du docstring (fallback BFS connected-components)
            # au lieu de retourner {} en silence quand scipy/sklearn manque. Degrade le
            # clustering spectral en composantes connexes, mais ne disparait pas sans bruit.
            print("detect_zones: scipy/sklearn absent -> fallback BFS (connected components)",
                  file=sys.stderr)
            if self._db is not None:
                degree = self._db.all_degrees()
            else:
                degree = {}
                for key in self.data["connections"]:
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    degree[parts[0]] = degree.get(parts[0], 0) + 1
                    degree[parts[1]] = degree.get(parts[1], 0) + 1
            return self._bfs_zones(degree)

        # 1. Build concept index and sparse matrix
        # Cap concepts to avoid eigsh hanging on massive matrices (>2000 concepts)
        MAX_ZONE_CONCEPTS = 2000
        concepts = set()
        rows, cols, vals = [], [], []

        if self._db is not None:
            id_to_name = self._db._id_to_name
            # Pre-filter: if too many concepts, keep only top by degree
            top_concepts = None
            total_concepts = len(self._db._concept_cache)
            if total_concepts > MAX_ZONE_CONCEPTS:
                degree = self._db.all_degrees()
                sorted_deg = sorted(degree.items(), key=lambda x: -x[1])
                top_concepts = set(c for c, _ in sorted_deg[:MAX_ZONE_CONCEPTS])

            # P7: Bounded edge scan — query per-concept neighbors instead of
            # loading all 11M+ edges. Each concept gets top-64 strongest edges.
            # Robinet scaling: O(concepts * fanout) instead of O(all_edges).
            ZONE_FANOUT = 64
            edge_triples = []
            scan_concepts = top_concepts if top_concepts else set(id_to_name.values())
            for concept in scan_concepts:
                neighbors = self._db.neighbors(concept, top_n=ZONE_FANOUT)
                for neighbor, count in neighbors:
                    if top_concepts and neighbor not in top_concepts:
                        continue
                    concepts.add(concept)
                    concepts.add(neighbor)
                    edge_triples.append((concept, neighbor, count))
            concepts = sorted(concepts)
            idx = {c: i for i, c in enumerate(concepts)}
            N = len(concepts)
            if N < 6:
                return {}
            for a_name, b_name, w in edge_triples:
                i, j = idx[a_name], idx[b_name]
                rows.extend([i, j])
                cols.extend([j, i])
                vals.extend([w, w])
        else:
            conns = self.data["connections"]
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                concepts.add(parts[0])
                concepts.add(parts[1])
            concepts = sorted(concepts)
            idx = {c: i for i, c in enumerate(concepts)}
            N = len(concepts)
            if N < 6:
                return {}
            for key, conn in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                i, j = idx[a], idx[b]
                w = conn["count"]
                rows.extend([i, j])
                cols.extend([j, i])
                vals.extend([w, w])

        W = sparse.csr_matrix((vals, (rows, cols)), shape=(N, N))

        # 2. Normalized Laplacian: L_sym = D^{-1/2} W D^{-1/2}
        degrees = np.array(W.sum(axis=1)).flatten()
        d_inv_sqrt = np.zeros(N, dtype=np.float64)
        mask = degrees > 0
        d_inv_sqrt[mask] = 1.0 / np.sqrt(degrees[mask])
        D_inv_sqrt = sparse.diags(d_inv_sqrt)
        L_sym = D_inv_sqrt @ W.astype(np.float64) @ D_inv_sqrt

        # 3. Auto-detect K (or use provided)
        if k is None:
            # Heuristic: sqrt(N/10), clamped [2, 12]
            import math
            k = max(2, min(12, int(math.sqrt(N / 10))))

        k = min(k, N - 1)  # eigsh needs k < N

        # 4. Eigenvectors
        try:
            eigenvalues, eigenvectors = eigsh(L_sym, k=k, which='LM')
        except (ValueError, ArithmeticError, RuntimeError) as e:
            print(f"detect_zones eigsh failed: {e}", file=sys.stderr)
            return {}

        # A5: Spectral gap = lambda_2 / lambda_1 (mixing time metric)
        # Source: Bowman (Stanford, >1000 cit.), BS-1 Cell Bio briefing
        sorted_eigs = sorted(eigenvalues, reverse=True)
        if len(sorted_eigs) >= 2 and sorted_eigs[0] > 0:
            self._spectral_gap = sorted_eigs[1] / sorted_eigs[0]
        else:
            self._spectral_gap = None

        # 5. KMeans on L2-normalized eigenvectors
        norms = np.linalg.norm(eigenvectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        eigvec_normed = eigenvectors / norms

        kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = kmeans.fit_predict(eigvec_normed)

        # 6. P20.6: Auto-name zones by top-3 concepts (highest degree in cluster)
        zones = {}
        for cluster_id in range(k):
            cluster_mask = labels == cluster_id
            cluster_indices = np.where(cluster_mask)[0]
            if len(cluster_indices) == 0:
                continue

            # Sort by degree within cluster
            cluster_concepts = [(concepts[i], degrees[i]) for i in cluster_indices]
            cluster_concepts.sort(key=lambda x: -x[1])

            # Zone name = top 3 concepts joined
            top_names = [c[0] for c in cluster_concepts[:3]]
            zone_name = "/".join(top_names)
            zone_members = [concepts[i] for i in cluster_indices]
            zones[zone_name] = zone_members

        return zones

    def auto_label_zones(self, k: int = None):
        """P20.5+6: Run detect_zones and tag all connections with their zone.

        Updates connections in-place with detected zone labels.
        """
        zones = self.detect_zones(k=k)
        if not zones:
            return {}

        # Build reverse map: concept -> zone_name
        concept_to_zone = {}
        for zone_name, members in zones.items():
            for concept in members:
                concept_to_zone[concept] = zone_name

        # Tag connections: zone = zone of concept_a (or shared if both same zone)
        # Robinet: iterate only zone concepts' neighbors, not all 11M+ edges.
        tagged = 0
        if self._db is not None:
            for concept, zone_name in concept_to_zone.items():
                neighbors = self._db.neighbors(concept, top_n=64)
                for neighbor, _ in neighbors:
                    self._db.add_zone_to_edge(concept, neighbor, zone_name)
                    tagged += 1
                    zone_b = concept_to_zone.get(neighbor)
                    if zone_b and zone_b != zone_name:
                        self._db.add_zone_to_edge(concept, neighbor, zone_b)
        else:
            conns = self.data["connections"]
            for key, conn in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                zone_a = concept_to_zone.get(a)
                zone_b = concept_to_zone.get(b)
                if "zones" not in conn:
                    conn["zones"] = []
                if zone_a and zone_a not in conn["zones"]:
                    conn["zones"].append(zone_a)
                    tagged += 1
                if zone_b and zone_b != zone_a and zone_b not in conn["zones"]:
                    conn["zones"].append(zone_b)

        self._invalidate_zone_cache()
        return zones

    def get_zones(self) -> dict[str, int]:
        """P20.8: Get all zones and their connection counts."""
        if self._db is not None:
            zone_counts = self._db.get_zone_counts()
            return dict(sorted(zone_counts.items(), key=lambda x: x[1], reverse=True))
        zone_counts = {}
        for conn in self.data["connections"].values():
            if "zones" in conn:
                for z in conn["zones"]:
                    zone_counts[z] = zone_counts.get(z, 0) + 1
        return dict(sorted(zone_counts.items(), key=lambda x: x[1], reverse=True))

    def get_bridges(self) -> list[tuple[str, str, str, float]]:
        """P20.8: Get inter-zone bridges (connections that span 2+ zones)."""
        bridges = []
        if self._db is not None:
            id_to_name = self._db._id_to_name
            bridge_data = []
            for a_id, b_id, nz in self._db.get_multi_zone_edges(min_zones=2):
                a_name = id_to_name.get(a_id, "")
                b_name = id_to_name.get(b_id, "")
                if not a_name or not b_name:
                    continue
                zones = [r[0] for r in self._db._conn.execute(
                    "SELECT zone FROM edge_zones WHERE a=? AND b=?", (a_id, b_id))]
                count_row = self._db._conn.execute(
                    "SELECT count FROM edges WHERE a=? AND b=?", (a_id, b_id)).fetchone()
                bridge_data.append((a_name, b_name, zones, count_row))
            for a_name, b_name, zones, count_row in bridge_data:
                count = count_row[0] if count_row else 1
                key = self._key(a_name, b_name)
                weight = self.effective_weight(key, count)
                bridges.append((a_name, b_name, zones, weight))
        else:
            for key, conn in self.data["connections"].items():
                if "zones" in conn and len(conn["zones"]) >= 2:
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    weight = self.effective_weight(key)
                    bridges.append((a, b, conn["zones"], weight))
        bridges.sort(key=lambda x: x[3], reverse=True)
        return bridges

    # ── Internal helpers used by detect_zones / fallback ─────────

    def _graph_entropy(self, degree: dict) -> float:
        """Shannon entropy of degree distribution: H = -sum(p * log2(p))."""
        import math
        if not degree:
            return 0.0
        total = sum(degree.values())
        if total == 0:
            return 0.0
        entropy = 0.0
        counts = {}
        for d in degree.values():
            counts[d] = counts.get(d, 0) + 1
        for count in counts.values():
            p = count / len(degree)
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def _bfs_zones(self, degree: dict,
                   fanout: int = 32, max_concepts: int = 5000) -> dict[str, list[str]]:
        """Fallback zone detection via connected components (no scipy needed).

        Memory-safe: builds adjacency from top-degree concepts only (bounded
        by *max_concepts*), each with at most *fanout* strongest neighbors.
        Uses collections.deque for O(1) popleft instead of list.pop(0).
        """
        from collections import deque

        # Pick the top-degree concepts as seeds — these define the zones
        if not degree:
            return {}
        sorted_concepts = sorted(degree.items(), key=lambda x: -x[1])
        seeds = [c for c, _ in sorted_concepts[:max_concepts]]
        seed_set = set(seeds)

        # Build bounded adjacency: top-fanout neighbors per seed
        adj: dict[str, list[str]] = {}
        if self._db is not None:
            for concept in seeds:
                neighbors = self._db.neighbors(concept, top_n=fanout)
                adj[concept] = [n for n, _ in neighbors if n in seed_set]
        else:
            conns = self.data["connections"]
            # Pre-build per-concept edge list
            concept_edges: dict[str, list[tuple[str, float]]] = {}
            for key, val in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                cnt = val.get("count", 1) if isinstance(val, dict) else 1
                if a in seed_set:
                    concept_edges.setdefault(a, []).append((b, cnt))
                if b in seed_set:
                    concept_edges.setdefault(b, []).append((a, cnt))
            for concept in seeds:
                edges = concept_edges.get(concept, [])
                edges.sort(key=lambda x: -x[1])
                adj[concept] = [n for n, _ in edges[:fanout] if n in seed_set]

        # BFS connected components with deque
        visited: set[str] = set()
        zones: dict[str, list[str]] = {}
        for start in seeds:
            if start in visited:
                continue
            queue = deque([start])
            component: list[str] = []
            while queue:
                node = queue.popleft()
                if node in visited:
                    continue
                visited.add(node)
                component.append(node)
                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if len(component) >= 3:
                top = sorted(component, key=lambda c: -degree.get(c, 0))[:3]
                name = "/".join(top)
                zones[name] = component

        return zones
