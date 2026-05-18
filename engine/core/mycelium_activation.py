#!/usr/bin/env python3
"""Muninn Mycelium — Spreading activation + transitive inference mixin.

H6 chunk 3 (2026-05-09): extracted from engine/core/mycelium.py.
Mixed into Mycelium via multiple inheritance. No behavior change.

Public API exposed by this mixin:
  - Mycelium.get_related(concept, top_n, filter_stopwords)
                          → [(neighbor, weight), ...]
  - Mycelium.adaptive_hops()
                          → int (1=dense, 2=default, 3=sparse)
  - Mycelium.spread_activation(seeds, hops, decay, top_n)
                          → [(concept, activation), ...]
                          (Collins & Loftus 1975)
  - Mycelium.transitive_inference(concept, max_hops, beta, top_n,
                                  min_strength)
                          → [(concept, inferred_strength), ...]
                          (Wynne 1995, Paz-y-Mino 2004)

Internal helpers:
  - _build_adj_cache()        — full adjacency cache (capped 500K edges)
  - _build_adj_subgraph()     — BRICK 15 bounded-BFS for hub-safe queries
  - _dynamic_degree_percentile()
                              — H6 federation-aware stopword threshold
  - _get_high_degree_concepts()
                              — S3/H6 universal stopwords (degree-based)

Class constant moved here:
  - _ADJ_CACHE_HARD_LIMIT = 500_000

Dependencies on core mixin:
  - self._db, self.data, self._adj_cache, self._adj_cache_max_weight,
    self._high_degree_cache, self.federated, self.zone, self.DEGREE_FILTER_PERCENTILE,
    self._key, self.effective_weight, self._adj_index_json

Dependencies on meta mixin (already extracted):
  - self.meta_db_path()       — used by _dynamic_degree_percentile
"""
from __future__ import annotations

import sqlite3
import sys
import time

# --- PIPELINE_TRACE block (removable, see docs/PIPELINE_TRACE_REMOVAL.md) ---  # PIPELINE_TRACE
try:  # PIPELINE_TRACE
    from pipeline_trace import log_event  # PIPELINE_TRACE
except Exception:  # PIPELINE_TRACE
    def log_event(*a, **kw): pass  # PIPELINE_TRACE
# --- end PIPELINE_TRACE block ---  # PIPELINE_TRACE

try:
    from .mycelium_db import MyceliumDB
except ImportError:
    from mycelium_db import MyceliumDB  # type: ignore[no-redef]


class _MyceliumActivationMixin:
    """Spreading activation + transitive inference + adjacency helpers."""

    # BRICK 15 (2026-04-11): hard size cap to protect against the
    # spread_activation infinite-loop on graphs with millions of edges.
    # On Sky's real mycelium DB (180K concepts, 15.5M edges) the original
    # _build_adj_cache loaded all 15.5M rows into a Python dict, blowing
    # up memory and hanging the test_lazy_real::test_real_spread_activation
    # test for 60+ seconds. The fix below adds a bounded BFS-subgraph
    # builder so spread_activation and find_chain only see the edges
    # they actually need.
    _ADJ_CACHE_HARD_LIMIT = 500_000  # max edges loaded by full _build_adj_cache

    def _build_adj_cache(self) -> dict:
        """Build and cache adjacency list from all edges. Called once per session.
        Returns {concept: [(neighbor, raw_weight)]}. Also stores max_weight.

        BRICK 15 SAFETY: hard cap of _ADJ_CACHE_HARD_LIMIT edges. On graphs
        larger than this, returns an empty dict and logs a warning, forcing
        callers to use _build_adj_subgraph(seeds, hops) instead.
        """
        if self._adj_cache is not None:
            return self._adj_cache
        adj = {}
        max_w = 0.0
        if self._db is not None:
            with self._db._lock:
                n_edges = self._db._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            if n_edges > self._ADJ_CACHE_HARD_LIMIT:
                # Refuse to load. Cache empty dict so we don't re-check.
                print(
                    f"  [mycelium] _build_adj_cache REFUSED: {n_edges:,} edges > "
                    f"hard limit {self._ADJ_CACHE_HARD_LIMIT:,}. "
                    f"Use _build_adj_subgraph(seeds, hops) for bounded queries.",
                    file=sys.stderr,
                )
                self._adj_cache = {}
                self._adj_cache_max_weight = 0.0
                return self._adj_cache
            id_to_name = self._db._id_to_name
            with self._db._lock:
                rows = self._db._conn.execute("SELECT a, b, count FROM edges").fetchall()
            for row in rows:
                a_name = id_to_name.get(row[0], "")
                b_name = id_to_name.get(row[1], "")
                if not a_name or not b_name:
                    continue
                w = float(row[2])
                if w > max_w:
                    max_w = w
                adj.setdefault(a_name, []).append((b_name, w))
                adj.setdefault(b_name, []).append((a_name, w))
        else:
            conns = self.data.get("connections", {})
            for key, val in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                w = float(val["count"])
                if w > max_w:
                    max_w = w
                adj.setdefault(a, []).append((b, w))
                adj.setdefault(b, []).append((a, w))
        self._adj_cache = adj
        self._adj_cache_max_weight = max_w
        return adj

    def _build_adj_subgraph(self, seeds, hops: int = 2, fanout_cap: int = 64) -> tuple:
        """BRICK 15: bounded-BFS adjacency builder for query-time use.

        Returns (adj_dict, max_weight) for the subgraph reachable from
        `seeds` within `hops` hops. At each hop, queries the top-`fanout_cap`
        strongest edges PER frontier node, so a hub concept (e.g. user
        name appearing in every session) cannot blow up the BFS.

        Pure on the input. Does NOT mutate self._adj_cache. Safe for
        concurrent calls. Suitable for graphs with 10M+ edges.

        Performance on Sky's real DB (180K concepts, 15.5M edges):
          - Hub seed ['ludov', 'users']: 127s pre-fanout-tune -> ~5s post
          - Mid-degree seed ['compression']: <1s

        Args:
            seeds: iterable of concept name strings.
            hops: BFS depth (default 2 = enough for spreading activation).
            fanout_cap: top-N strongest edges per node (default 64).
                Lower = faster but may miss weak-but-relevant edges.

        Returns:
            (adj_dict, max_weight) — same format as _build_adj_cache.
        """
        adj = {}
        max_w = 0.0
        if self._db is None:
            # JSON path: fall back to full cache (no DB → small graph)
            full = self._build_adj_cache()
            return full, self._adj_cache_max_weight
        seed_lower = {s.lower().strip() for s in seeds if s}
        if not seed_lower:
            return adj, 0.0
        # Resolve seed names to ids via the concept cache
        name_to_id = self._db._concept_cache
        id_to_name = {v: k for k, v in name_to_id.items()}
        frontier_ids = {name_to_id[n] for n in seed_lower if n in name_to_id}
        if not frontier_ids:
            return adj, 0.0
        visited_ids = set(frontier_ids)
        for hop in range(hops + 1):
            if not frontier_ids:
                break
            new_frontier = set()
            # Per-node bounded query: top-N strongest edges per frontier node.
            # This is the key optimization vs IN(...) batching: a hub concept
            # with 50K edges only contributes its top-N (default 64), not all.
            with self._db._lock:
                for node_id in frontier_ids:
                    rows = self._db._conn.execute(
                        "SELECT a, b, count FROM edges "
                        "WHERE a = ? OR b = ? "
                        "ORDER BY count DESC LIMIT ?",
                        (node_id, node_id, fanout_cap),
                    ).fetchall()
                    for a_id, b_id, count in rows:
                        a_name = id_to_name.get(a_id, "")
                        b_name = id_to_name.get(b_id, "")
                        if not a_name or not b_name:
                            continue
                        w = float(count)
                        if w > max_w:
                            max_w = w
                        if len(adj.get(a_name, [])) < fanout_cap:
                            adj.setdefault(a_name, []).append((b_name, w))
                        if len(adj.get(b_name, [])) < fanout_cap:
                            adj.setdefault(b_name, []).append((a_name, w))
                        if a_id not in visited_ids:
                            new_frontier.add(a_id)
                        if b_id not in visited_ids:
                            new_frontier.add(b_id)
            visited_ids.update(new_frontier)
            frontier_ids = new_frontier
        return adj, max_w

    def _dynamic_degree_percentile(self) -> float:
        """H6: Adjust degree filter percentile based on meta repo count.

        With more repos, common concepts are more frequent so we tighten the filter.
        Formula: base_percentile / sqrt(n_repos), min 0.5%, max = base.
        """
        if not self.federated:
            return self.DEGREE_FILTER_PERCENTILE
        try:
            meta_db_p = self.meta_db_path()
            if meta_db_p.exists():
                db = MyceliumDB(meta_db_p)
                repos_str = db.get_meta("repos", "")
                db.close()
                n_repos = len(repos_str.split(",")) if repos_str else 1
                if n_repos > 1:
                    import math
                    adjusted = self.DEGREE_FILTER_PERCENTILE / math.sqrt(n_repos)
                    return max(0.005, adjusted)  # Floor at 0.5%
        except (sqlite3.OperationalError, ValueError):
            pass
        return self.DEGREE_FILTER_PERCENTILE

    def _get_high_degree_concepts(self) -> set:
        """S3/H6: Identify concepts with too many connections (universal stopwords).

        H6: Percentile adjusts dynamically based on meta repo count.
        Lazy mode: 2 SQL queries (count distinct + filter by threshold).
        No full scan of 2.7M edges needed.
        """
        pct = self._dynamic_degree_percentile()
        if self._db is not None:
            n = self._db.connection_count()
            if n < 50:
                return set()
            # CHUNK B8 (2026-05-08): single SQL scan instead of two.
            # Pre-fix did the same UNION-ALL+GROUP-BY twice (once for
            # percentile, once for filter). Now we materialize
            # (concept_id, degree)
            # rows once, sort in SQL, and apply the percentile cutoff in
            # Python — same semantics, half the SQL work.
            with self._db._lock:
                row = self._db._conn.execute(
                    "SELECT COUNT(*) FROM concepts").fetchone()
                n_concepts = row[0] if row else 0
                if n_concepts < 20:
                    return set()
                cutoff = max(1, int(n_concepts * pct))

                rows = self._db._conn.execute("""
                    SELECT concept_id, SUM(cnt) AS degree FROM (
                        SELECT a AS concept_id, COUNT(*) AS cnt FROM edges GROUP BY a
                        UNION ALL
                        SELECT b AS concept_id, COUNT(*) AS cnt FROM edges GROUP BY b
                    ) GROUP BY concept_id
                    ORDER BY degree DESC
                """).fetchall()

                if not rows:
                    return set()
                # Threshold = degree at cutoff position, floored to 20.
                idx = min(cutoff - 1, len(rows) - 1)
                threshold = max(rows[idx][1], 20)

                id_to_name = self._db._id_to_name
                result = set()
                for cid, degree in rows:
                    if degree < threshold:
                        # rows are sorted DESC; can stop early
                        break
                    name = id_to_name.get(cid) or self._db._concept_name(cid)
                    result.add(name)
            return result
        else:
            conns = self.data["connections"]
            if len(conns) < 50:
                return set()
            degree = {}
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1

            if not degree:
                return set()

            sorted_degrees = sorted(degree.values(), reverse=True)
            cutoff_idx = max(1, int(len(sorted_degrees) * pct))
            threshold = sorted_degrees[min(cutoff_idx, len(sorted_degrees) - 1)]
            threshold = max(threshold, 20)

            return {c for c, d in degree.items() if d >= threshold}

    def get_related(self, concept: str, top_n: int = 5,
                    filter_stopwords: bool = True) -> list[tuple[str, float]]:
        """Get concepts most strongly connected to a given concept.

        Returns list of (related_concept, weight) sorted by effective weight.
        In federated mode, prioritizes connections from the current zone.

        When filter_stopwords=True (default), high-degree hub concepts
        (stopwords like 'est', 'les', 'pas') are excluded from results
        to surface meaningful semantic neighbors. Fixed after BUG-M4.
        """
        _pt_t0 = time.perf_counter()  # PIPELINE_TRACE
        if not concept:
            return []
        concept = str(concept).lower().strip()

        # Build stopword set for filtering (lazy-cached)
        hub_set: set[str] = set()
        if filter_stopwords:
            if self._high_degree_cache is None:
                self._high_degree_cache = self._get_high_degree_concepts()
            hub_set = self._high_degree_cache

        if self._db is not None:
            # Fetch more than needed to allow zone reordering + stopword filtering
            neighbors = self._db.neighbors(concept, top_n=max(50, top_n * 10))
            related = []
            for name, count in neighbors:
                if name in hub_set:
                    continue
                if self.federated:
                    key = self._key(concept, name)
                    weight = self.effective_weight(key, count)
                    zones = self._db.get_zones_for_edge(concept, name)
                    if self.zone in zones:
                        weight *= 2.0
                else:
                    weight = float(count)
                related.append((name, weight))
            related.sort(key=lambda x: x[1], reverse=True)
            _pt_out = related[:top_n]  # PIPELINE_TRACE
            log_event("pipeline.mycelium.get_related.end", {"concept": concept, "found": len(_pt_out), "backend": "sqlite", "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
            return _pt_out
        else:
            # CHUNK D2 (2026-05-08): pre-index conns by concept so
            # subsequent get_related() calls don't re-scan the entire
            # connections dict (was O(E) per query). Lazy build, cached
            # on the instance, invalidated by setting _adj_index_json
            # to None after observe()/save().
            if not hasattr(self, "_adj_index_json") or self._adj_index_json is None:
                idx: dict[str, list[tuple[str, str, dict]]] = {}
                for key, val in self.data["connections"].items():
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    idx.setdefault(a, []).append((b, key, val))
                    idx.setdefault(b, []).append((a, key, val))
                self._adj_index_json = idx
            related = []
            for other, key, val in self._adj_index_json.get(concept, []):
                if other in hub_set:
                    continue
                if self.federated:
                    weight = self.effective_weight(key)
                    if "zones" in val and self.zone in val["zones"]:
                        weight *= 2.0
                else:
                    weight = float(val["count"])
                related.append((other, weight))
            related.sort(key=lambda x: x[1], reverse=True)
            _pt_out = related[:top_n]  # PIPELINE_TRACE
            log_event("pipeline.mycelium.get_related.end", {"concept": concept, "found": len(_pt_out), "backend": "memory_dict", "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
            return _pt_out

    def adaptive_hops(self) -> int:
        """A5: Adaptive spreading activation hops — 1 if dense, 3 if sparse.

        Dense network (many edges per concept) = fewer hops to avoid flooding.
        Sparse network = more hops to reach relevant concepts.
        """
        if self._db is not None:
            n_edges = self._db.connection_count()
            n_concepts = len(self._db._concept_cache)
        else:
            n_edges = len(self.data.get("connections", {}))
            concepts = set()
            for key in self.data.get("connections", {}):
                parts = key.split("|")
                if len(parts) == 2:
                    concepts.update(parts)
            n_concepts = len(concepts)

        if n_concepts == 0:
            return 2
        avg_degree = n_edges / max(n_concepts, 1)
        if avg_degree > 10:
            return 1  # Dense — 1 hop to avoid flooding
        elif avg_degree < 3:
            return 3  # Sparse — need more hops to reach
        return 2  # Default

    def spread_activation(self, seeds: list[str], hops: int = None,
                          decay: float = 0.5, top_n: int = 20,
                          apply_failure_penalty: bool = True) -> list[tuple[str, float]]:
        """Spreading activation through the semantic network (Collins & Loftus 1975).

        Instead of keyword matching, propagates activation from seed concepts
        through weighted connections. Finds semantically related concepts that
        share NO words with the query.

        Args:
            seeds: starting concepts (e.g. query words)
            hops: how many steps to propagate (None = A5 adaptive, 2 = default)
            decay: activation multiplier per hop (0.5 = halves each step)
            top_n: max concepts to return
            apply_failure_penalty: if True (default), subtract failure weight
                from final activation (Phase 3 2026-05-14, negative learning).
                Set False for strict backward-compat with pre-Phase-3 behavior.

        Returns:
            list of (concept, activation) sorted by activation descending.
            Seeds themselves are excluded from results.
        """
        _pt_t0 = time.perf_counter()  # PIPELINE_TRACE
        # A5: Adaptive hops if not explicitly set
        _pt_hops_passed = hops  # PIPELINE_TRACE
        if hops is None:
            hops = self.adaptive_hops()
        log_event("pipeline.mycelium.spread.begin", {"n_seeds": len(seeds), "hops": hops, "hops_adaptive": _pt_hops_passed is None, "decay": decay, "top_n": top_n})  # PIPELINE_TRACE
        # BRICK 15 (2026-04-11): use bounded BFS subgraph instead of loading
        # the entire 15M-edge graph. On Sky's real DB the full _build_adj_cache
        # hangs for 60+s; the bounded version queries only the edges within
        # `hops` hops of the seeds — typically <50K rows even on huge graphs.
        raw_adj, _max_w = self._build_adj_subgraph(seeds, hops=hops)
        if not raw_adj:
            log_event("pipeline.mycelium.spread.end", {"reason": "empty_subgraph", "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
            return []
        if self._high_degree_cache is None:
            self._high_degree_cache = self._get_high_degree_concepts()
        hub_concepts = self._high_degree_cache
        seed_lower = {s.lower().strip() for s in seeds}
        # Apply hub penalty on a copy (hub penalty depends on seeds)
        adj = {}
        for concept, neighbors in raw_adj.items():
            is_hub = concept in hub_concepts and concept not in seed_lower
            new_neighbors = []
            for n, w in neighbors:
                pw = w
                if is_hub or (n in hub_concepts and n not in seed_lower):
                    pw = w * 0.1
                new_neighbors.append((n, pw))
            adj[concept] = new_neighbors

        # Normalize weights per node (so high-degree nodes don't dominate)
        for concept in adj:
            total = sum(w for _, w in adj[concept])
            if total > 0:
                adj[concept] = [(n, w / total) for n, w in adj[concept]]

        # Initialize activation
        activation = {}
        seed_set = set()
        for s in seeds:
            s = s.lower().strip()
            if s in adj:
                activation[s] = 1.0
                seed_set.add(s)

        if not activation:
            log_event("pipeline.mycelium.spread.end", {"reason": "no_seed_in_adj", "subgraph_size": len(raw_adj), "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
            return []

        # Propagate — only from current frontier (not all activated nodes)
        frontier = dict(activation)  # start with seeds
        for hop in range(hops):
            new_activation = {}
            factor = decay ** (hop + 1)
            for concept, act in frontier.items():
                for neighbor, weight in adj.get(concept, []):
                    spread = act * weight * factor
                    new_activation[neighbor] = new_activation.get(neighbor, 0) + spread
            # Merge into main activation (keep max, not sum, to avoid runaway)
            for concept, act in new_activation.items():
                if concept not in activation:
                    activation[concept] = act
                else:
                    activation[concept] = max(activation[concept], act)
            frontier = new_activation  # next hop propagates from new nodes only

        # Phase 3 (2026-05-14): apply failure penalty BEFORE min-max norm.
        # Batched 1-SQL query (audit: 50 concepts = 0.38ms vs ~500ms sequential).
        # Gated by apply_failure_penalty for strict backward-compat.
        if (apply_failure_penalty and self._db is not None
                and hasattr(self._db, "get_failure_weights_batch")):
            non_seed_concepts = [c for c in activation if c not in seed_set]
            if non_seed_concepts:
                try:
                    fail_weights = self._db.get_failure_weights_batch(
                        non_seed_concepts)
                    for concept, fw in fail_weights.items():
                        # fw is negative; decay scales the penalty
                        activation[concept] = activation[concept] + fw * decay
                except Exception:
                    pass  # never fail spread_activation due to fail-penalty query

        # Remove seeds, sort by activation
        results = [(c, a) for c, a in activation.items() if c not in seed_set]
        # A3: Normalize activations to [0, 1] via min-max scaling.
        # Previous sigmoid (k=10, x0=median) squashed all values to ~0.50 ± 0.003
        # because normalized edge weights produce tiny raw activations (~0.002).
        # Min-max preserves the relative ordering that Collins & Loftus intended.
        if results:
            activations = [a for _, a in results]
            max_a = max(activations)
            min_a = min(activations)
            spread = max_a - min_a
            if spread > 0:
                results = [(c, (a - min_a) / spread) for c, a in results]
            else:
                results = [(c, 0.5) for c, a in results]
        results.sort(key=lambda x: x[1], reverse=True)
        _pt_out = results[:top_n]  # PIPELINE_TRACE
        log_event("pipeline.mycelium.spread.end", {"subgraph_size": len(raw_adj), "activated": len(results), "returned": len(_pt_out), "hops": hops, "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
        return _pt_out

    def transitive_inference(self, concept: str, max_hops: int = 3,
                              beta: float = 0.5, top_n: int = 15,
                              min_strength: float = 0.01) -> list[tuple[str, float]]:
        """V3A Transitive inference value transfer (Wynne 1995, Paz-y-Mino 2004).

        If A->B strong and B->C strong, infer A->C with weight = product of
        edge strengths along path * beta^hops. Unlike spreading activation,
        this tracks multiplicative chain strength (ordered transitive closure).

        V(A->C) = strength(A,B) * strength(B,C) * beta^2

        Args:
            concept: starting concept
            max_hops: maximum chain length (3 = A->B->C->D)
            beta: decay per hop (0.5 = halves each step)
            top_n: max concepts to return
            min_strength: prune paths below this threshold

        Returns:
            list of (concept, inferred_strength) sorted descending.
        """
        concept = concept.lower().strip()

        # BRICK 15 (2026-04-11): use bounded BFS subgraph instead of full
        # adjacency cache. find_chain is BFS-bounded by max_hops anyway,
        # so loading 15M edges to traverse <50K is wasteful.
        adj, max_weight = self._build_adj_subgraph([concept], hops=max_hops)

        if concept not in adj or max_weight == 0:
            return []

        # Normalize weights to [0,1] for meaningful chain products
        inv_max = 1.0 / max(max_weight, 1e-10)

        # BFS with multiplicative path strength + relaxation
        # Unlike spreading activation, we track path products and allow
        # updates if a longer path is stronger (Dijkstra-like relaxation).
        inferred = {}  # concept -> best inferred strength
        frontier = [(concept, 1.0)]  # (node, cumulative_strength)
        seed = concept

        for hop in range(1, max_hops + 1):
            decay = beta ** hop
            next_frontier = {}  # node -> best path_strength (deduped)
            for node, path_strength in frontier:
                for neighbor, edge_w in adj.get(node, []):
                    if neighbor == seed:
                        continue  # never return to seed
                    chain_strength = path_strength * (edge_w * inv_max) * decay
                    if chain_strength < min_strength:
                        continue
                    # Update inferred if this path is stronger
                    if neighbor not in inferred or chain_strength > inferred[neighbor]:
                        inferred[neighbor] = chain_strength
                    # Dedup frontier: keep best path_strength per node
                    raw_path = path_strength * (edge_w * inv_max)
                    if neighbor not in next_frontier or raw_path > next_frontier[neighbor]:
                        next_frontier[neighbor] = raw_path
            frontier = list(next_frontier.items())

        # Sort by inferred strength
        results = sorted(inferred.items(), key=lambda x: x[1], reverse=True)
        return results[:top_n]
