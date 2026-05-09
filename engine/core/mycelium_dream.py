#!/usr/bin/env python3
"""Muninn Mycelium — Dream / trip / anomalies / blind-spots mixin.

H6 chunk 4 (2026-05-09): extracted from engine/core/mycelium.py.
Mixed into Mycelium via multiple inheritance. No behavior change.

Public API exposed by this mixin:
  - Mycelium.detect_anomalies()           (B2 — graph anomalies)
  - Mycelium.detect_blind_spots(top_n)    (B3 — Burt 1992 structural holes)
  - Mycelium.trip(intensity, max_dreams)  (H1 — BARE Wave + Carhart-Harris)
  - Mycelium.dream(strong_pair_limit)     (H2 — Wilson & McNaughton 1994)

Internal helper:
  - _save_insights(insights)              (H2 — atomic JSON persist)

Dependencies on other mixins (already extracted):
  - self.detect_zones / self._bfs_zones / self._graph_entropy
    / self.get_zones                      (from _MyceliumZonesMixin)

Dependencies on core mixin:
  - self._db, self.data, self.mycelium_dir
"""
from __future__ import annotations

import json
import os
import sqlite3
import time


class _MyceliumDreamMixin:
    """Sleep consolidation + divergent exploration + anomaly detection."""

    # ── B2: Graph anomaly detection ────────────────────────────────

    def detect_anomalies(self) -> dict:
        """B2: Detect structural anomalies in the mycelium graph.

        Returns dict with keys:
          - "isolated": concepts with degree <= 1 (poorly connected)
          - "hubs": concepts with degree > mean + 2*std (monopolies)
          - "weak_zones": zone names where mean connection count < 2
        Source: LITERATURE #16 (graph anomalies), BS-1 Cell Bio briefing
        """
        if self._db is not None:
            degree = self._db.all_degrees()
        else:
            conns = self.data["connections"]
            if not conns:
                return {"isolated": [], "hubs": [], "weak_zones": []}
            degree = {}
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1

        if not degree:
            return {"isolated": [], "hubs": [], "weak_zones": []}

        # Isolated: degree <= 1
        isolated = sorted([c for c, d in degree.items() if d <= 1])

        # Hubs: degree > mean + 2*std
        vals = list(degree.values())
        mean_d = sum(vals) / len(vals)
        variance = sum((v - mean_d) ** 2 for v in vals) / len(vals)
        std_d = variance ** 0.5
        hub_threshold = mean_d + 2 * std_d
        hubs = sorted([(c, d) for c, d in degree.items() if d > hub_threshold],
                       key=lambda x: -x[1])

        # Weak zones: zones where mean count < 2
        weak_zones = []
        zones = self.get_zones()
        if zones:
            if self._db is not None:
                for zone_name in zones:
                    avg_count = self._db.get_zone_avg_count(zone_name)
                    if avg_count < 2:
                        weak_zones.append(zone_name)
            else:
                conns = self.data.get("connections", {})
                for zone_name, count in zones.items():
                    zone_counts = []
                    for key, conn in conns.items():
                        if "zones" in conn and zone_name in conn["zones"]:
                            zone_counts.append(conn["count"])
                    if zone_counts and sum(zone_counts) / len(zone_counts) < 2:
                        weak_zones.append(zone_name)

        return {"isolated": isolated, "hubs": hubs, "weak_zones": weak_zones}

    # ── B3: Blind spot detection (angles morts) ────────────────────

    def detect_blind_spots(self, top_n: int = 20) -> list[tuple[str, str, str]]:
        """B3: Find concept pairs that SHOULD be connected but aren't.

        Two heuristics:
        1. Same-zone gap: concepts in the same zone with no direct connection
           but both have high degree (top 20% in zone). These are structural holes.
        2. Transitive gap: A-B connected, B-C connected, but A-C not connected,
           and both A-C have degree >= 5.

        Returns list of (concept_a, concept_b, reason) sorted by estimated
        importance (product of degrees).
        Source: Burt 1992 (structural holes), BS-4 Hodge Laplacien
        """
        if self._db is not None:
            n_conns = self._db.connection_count()
            degree = self._db.all_degrees()
        else:
            conns = self.data["connections"]
            n_conns = len(conns)
            degree = {}
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1

        if n_conns < 10 or not degree:
            return []

        max_concepts = 500
        if len(degree) > max_concepts:
            sorted_by_deg = sorted(degree.items(), key=lambda x: -x[1])
            p90 = sorted_by_deg[len(sorted_by_deg) // 10][1] if len(sorted_by_deg) > 10 else 999999
            mid_range = [(c, d) for c, d in sorted_by_deg if 10 <= d <= p90]
            mid_range.sort(key=lambda x: -x[1])
            top_concepts_set = set(c for c, _ in mid_range[:max_concepts])
        else:
            top_concepts_set = set(degree.keys())

        # Build connection set and adjacency ONLY for top concepts.
        # Robinet: query per-concept neighbors instead of loading all edges.
        conn_set = set()
        adj = {}
        if self._db is not None:
            for concept in top_concepts_set:
                neighbors = self._db.neighbors(concept, top_n=64)
                for neighbor, _ in neighbors:
                    conn_set.add((concept, neighbor))
                    conn_set.add((neighbor, concept))
                    if neighbor in top_concepts_set:
                        adj.setdefault(concept, set()).add(neighbor)
                        adj.setdefault(neighbor, set()).add(concept)
        else:
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                if a in top_concepts_set or b in top_concepts_set:
                    conn_set.add((a, b))
                    conn_set.add((b, a))
                if a in top_concepts_set and b in top_concepts_set:
                    adj.setdefault(a, set()).add(b)
                    adj.setdefault(b, set()).add(a)

        blind_spots = []

        # Heuristic 1: Same-zone gaps (needs zones tagged on connections)
        try:
            zones = self.detect_zones()
        except (ValueError, sqlite3.Error):
            zones = {}

        if zones:
            for zone_name, members in zones.items():
                if len(members) < 3:
                    continue
                # Top 20% by degree in this zone (capped at 30)
                zone_degs = [(c, degree.get(c, 0)) for c in members
                             if c in top_concepts_set]
                zone_degs.sort(key=lambda x: -x[1])
                cutoff = min(30, max(1, len(zone_degs) // 5))
                top_zone = [c for c, _ in zone_degs[:cutoff]]

                for i, ca in enumerate(top_zone):
                    for cb in top_zone[i+1:]:
                        if (ca, cb) not in conn_set:
                            score = degree.get(ca, 0) * degree.get(cb, 0)
                            blind_spots.append((ca, cb, f"zone_gap:{zone_name}", score))

        # Heuristic 2: Transitive gaps (A-B, B-C exist, A-C missing)
        # Only check top-degree concepts, cap neighbors at 20
        min_degree = 5
        max_neighbors = 20
        checked = set()
        for b_concept in top_concepts_set:
            neighbors = adj.get(b_concept)
            if not neighbors or degree.get(b_concept, 0) < min_degree:
                continue
            neighbor_list = [n for n in neighbors if degree.get(n, 0) >= min_degree]
            if len(neighbor_list) > max_neighbors:
                neighbor_list.sort(key=lambda n: -degree.get(n, 0))
                neighbor_list = neighbor_list[:max_neighbors]
            for i, a in enumerate(neighbor_list):
                for c in neighbor_list[i+1:]:
                    pair = tuple(sorted([a, c]))
                    if pair in checked:
                        continue
                    checked.add(pair)
                    if (a, c) not in conn_set:
                        score = degree.get(a, 0) * degree.get(c, 0)
                        blind_spots.append((a, c, f"transitive_via:{b_concept}", score))

        # Deduplicate and sort by score
        seen = set()
        unique = []
        for a, b, reason, score in blind_spots:
            pair = tuple(sorted([a, b]))
            if pair not in seen:
                seen.add(pair)
                unique.append((pair[0], pair[1], reason, score))

        unique.sort(key=lambda x: -x[3])
        return [(a, b, reason) for a, b, reason, _ in unique[:top_n]]

    # ── H1: Mode trip — psilocybine du mycelium ──────────────────
    #
    # BARE Wave Model (Nature 2025): dn/dt = alpha*n - beta*n*rho
    # Psilocybin (Carhart-Harris 2014): lower beta → tips explore without fusing
    # Entropy: H = -sum(p * log(p)) on degree distribution

    def trip(self, intensity: float = 0.5, max_dreams: int = 20) -> dict:
        """H1: Divergent exploration — create cross-cluster dream connections.

        Like psilocybin dissolving the Default Mode Network, this temporarily
        lowers the anastomosis rate (beta) so conceptual 'tips' can explore
        connections between normally isolated clusters.

        Args:
            intensity: 0.0-1.0, how aggressively to explore (higher = more dreams)
            max_dreams: cap on dream connections created

        Returns dict with: created, entropy_before, entropy_after, dreams list.
        Source: BARE Wave (Nature 2025), Carhart-Harris 2014 (entropic brain).
        """
        import math
        import random

        if self._db is not None:
            n_conns = self._db.connection_count()
            degree = self._db.all_degrees()
        else:
            conns = self.data["connections"]
            n_conns = len(conns)
            degree = {}
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                degree[parts[0]] = degree.get(parts[0], 0) + 1
                degree[parts[1]] = degree.get(parts[1], 0) + 1

        if n_conns < 20:
            return {"created": 0, "entropy_before": 0, "entropy_after": 0, "dreams": []}

        # 1. Compute entropy BEFORE (degree distribution)
        entropy_before = self._graph_entropy(degree)

        # 2. Detect zones (clusters) — spectral if available, BFS fallback
        zones = self.detect_zones()
        if len(zones) < 2:
            zones = self._bfs_zones(degree)
        if len(zones) < 2:
            return {"created": 0, "entropy_before": entropy_before,
                    "entropy_after": entropy_before, "dreams": [],
                    "reason": "fewer than 2 zones"}

        # 3. BARE Wave model: alpha creates tips, beta*rho limits them
        alpha = 0.04 * (1 + intensity)
        beta = 0.02 * (1 - intensity * 0.8)

        zone_names = list(zones.keys())
        zone_concepts = {z: set(concepts) for z, concepts in zones.items()}

        # Build conn_set for fast lookup — only for zone concepts (bounded)
        # Memory-safe: only load edges between concepts that are in zones,
        # not all 11M+ edges. Fixed after BUG-M2 MemoryError.
        all_zone_concepts = set()
        for members in zones.values():
            all_zone_concepts.update(members)

        conn_set = set()
        if self._db is not None:
            for concept in all_zone_concepts:
                neighbors = self._db.neighbors(concept, top_n=64)
                for neighbor, _ in neighbors:
                    if neighbor in all_zone_concepts:
                        conn_set.add((concept, neighbor))
                        conn_set.add((neighbor, concept))
        else:
            for key in conns:
                parts = key.split("|")
                if len(parts) == 2:
                    if parts[0] in all_zone_concepts and parts[1] in all_zone_concepts:
                        conn_set.add((parts[0], parts[1]))
                        conn_set.add((parts[1], parts[0]))

        # 4. Create dream connections between distant clusters
        dreams = []
        attempts = 0
        max_attempts = max_dreams * 10

        while len(dreams) < max_dreams and attempts < max_attempts:
            attempts += 1

            z1, z2 = random.sample(zone_names, 2)
            c1_list = list(zone_concepts[z1])
            c2_list = list(zone_concepts[z2])
            if not c1_list or not c2_list:
                continue

            a = random.choice(c1_list)
            b = random.choice(c2_list)

            if (a, b) in conn_set:
                continue

            rho_local = (degree.get(a, 0) + degree.get(b, 0)) / 2
            tip_survival = alpha - beta * rho_local
            if tip_survival < 0 and random.random() > intensity:
                continue

            # Create dream connection
            key = f"{a}|{b}" if a < b else f"{b}|{a}"
            if (a, b) not in conn_set and (b, a) not in conn_set:
                if self._db is not None:
                    self._db.upsert_connection(
                        key.split("|")[0], key.split("|")[1],
                        increment=1,
                    )
                else:
                    conns[key] = {
                        "count": 1,
                        "first_seen": time.strftime("%Y-%m-%d"),
                        "last_seen": time.strftime("%Y-%m-%d"),
                        "type": "dream",
                    }
                conn_set.add((a, b))
                conn_set.add((b, a))
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1
                dreams.append({"from": a, "to": b, "zones": [z1, z2],
                                "tip_survival": round(tip_survival, 4)})

        # 5. Compute entropy AFTER
        entropy_after = self._graph_entropy(degree)

        return {
            "created": len(dreams),
            "entropy_before": round(entropy_before, 4),
            "entropy_after": round(entropy_after, 4),
            "entropy_delta": round(entropy_after - entropy_before, 4),
            "dreams": dreams,
        }

    # ── H2: Synthèse / rêve — generate insights during sleep ─────
    #
    # During sleep consolidation, analyze patterns in the graph and
    # generate insights: temporal correlations, absences, anomalies.
    # Writes to .muninn/insights.json for boot surfacing.

    def dream(self, strong_pair_limit: int = 5000) -> list[dict]:
        """H2: Generate insights by analyzing the mycelium graph.

        Detects:
        1. Temporal patterns: concepts that always appear together across sessions
        2. Absences: high-degree concepts that SHOULD connect but don't
        3. Dream bridges: dream connections (H1) that got reinforced = validated
        4. Clusters imbalance: one zone dominates, others starve

        Returns list of insight dicts, also saves to .muninn/insights.json.
        Source: Wilson & McNaughton 1994 (sleep consolidation generates insights).

        Memory-safe: uses all_degrees() + top_connections() instead of loading
        all 11M+ edges into RAM. Fixed after BUG-M1 MemoryError.
        """
        import math

        if self._db is not None:
            n_conns = self._db.connection_count()
        else:
            n_conns = len(self.data["connections"])
        if n_conns < 10:
            return []

        insights = []

        # Build degree dict (memory-safe: uses SQL aggregation in DB mode)
        if self._db is not None:
            degree = self._db.all_degrees()
        else:
            degree = {}
            conns = self.data["connections"]
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                degree[parts[0]] = degree.get(parts[0], 0) + 1
                degree[parts[1]] = degree.get(parts[1], 0) + 1

        if not degree:
            return []

        # Strong pairs: fetch only top-N strongest edges (not all 11M)
        strong_pairs = []
        if self._db is not None:
            top_conns = self._db.top_connections(n=strong_pair_limit)
            for key, info in top_conns:
                parts = key.split("|")
                if len(parts) == 2:
                    cnt = info.get("count", 0) if isinstance(info, dict) else 0
                    strong_pairs.append((parts[0], parts[1], cnt))
            # Compute average count from degree sums (approximate but O(1))
            avg_count_n = n_conns
            # Use the median of strong pairs as a proxy for avg
            avg_count_sum = sum(c for _, _, c in strong_pairs)
        else:
            conns = self.data["connections"]
            avg_count_sum = 0.0
            avg_count_n = 0
            for key, conn in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                cnt = conn.get("count", 1)
                avg_count_sum += cnt
                avg_count_n += 1
                if cnt >= 10:
                    strong_pairs.append((parts[0], parts[1], cnt))

        if not degree:
            return []

        # 1. Strong pairs: concepts with unusually high co-occurrence
        avg_count = avg_count_sum / max(avg_count_n, 1)
        for a, b, cnt in strong_pairs:
            if cnt > avg_count * 5:
                insights.append({
                    "type": "strong_pair",
                    "concepts": [a, b],
                    "score": round(cnt / avg_count, 2),
                    "text": f"{a} and {b} are inseparable "
                            f"(x{cnt / avg_count:.1f} avg strength)",
                })

        # 2. Absences: high-degree concepts with no direct connection
        # Memory-safe: check pairs via DB lookup instead of full adj dict
        sorted_concepts = sorted(degree.items(), key=lambda x: -x[1])
        top_concepts = [c for c, d in sorted_concepts[:min(30, len(sorted_concepts))]]
        for i, a in enumerate(top_concepts):
            for b in top_concepts[i+1:]:
                connected = False
                if self._db is not None:
                    connected = self._db.has_connection(a, b)
                else:
                    key1 = f"{a}|{b}"
                    key2 = f"{b}|{a}"
                    connected = key1 in conns or key2 in conns
                if not connected:
                    score = (degree[a] + degree[b]) / 2
                    if score >= 5:
                        insights.append({
                            "type": "absence",
                            "concepts": [a, b],
                            "score": round(score, 2),
                            "text": f"{a} (deg={degree[a]}) and {b} (deg={degree[b]}) "
                                    f"never co-occur — blind spot?",
                        })

        # 3. Validated dreams — only available in dict mode (DB doesn't store type)
        if self._db is None:
            conns = self.data["connections"]
            for key, conn in conns.items():
                if conn.get("type") == "dream" and conn.get("count", 0) > 1:
                    parts = key.split("|")
                    if len(parts) == 2:
                        insights.append({
                            "type": "validated_dream",
                            "concepts": parts,
                            "score": conn["count"],
                            "text": f"Dream connection {parts[0]}-{parts[1]} confirmed "
                                    f"by real usage (count={conn['count']})",
                        })

        # 4. Cluster imbalance: detect if one zone has >60% of connections
        zones = self.detect_zones()
        if not zones:
            zones = self._bfs_zones(degree)
        if len(zones) >= 2:
            zone_sizes = {z: len(members) for z, members in zones.items()}
            total = sum(zone_sizes.values())
            if total > 0:
                dominant = max(zone_sizes.items(), key=lambda x: x[1])
                ratio = dominant[1] / total
                if ratio > 0.6:
                    insights.append({
                        "type": "imbalance",
                        "concepts": [dominant[0]],
                        "score": round(ratio, 2),
                        "text": f"Zone '{dominant[0][:30]}' dominates with "
                                f"{ratio:.0%} of concepts — explore other zones?",
                    })

        # 5. Graph entropy as health metric
        entropy = self._graph_entropy(degree)
        max_entropy = math.log2(len(degree)) if len(degree) > 1 else 1
        health = entropy / max_entropy if max_entropy > 0 else 0
        insights.append({
            "type": "health",
            "concepts": [],
            "score": round(health, 4),
            "text": f"Graph entropy: {entropy:.2f}/{max_entropy:.2f} "
                    f"(health={health:.0%}, 1.0=max diversity)",
        })

        # Sort by score descending, cap at 20
        insights.sort(key=lambda x: -x.get("score", 0))
        insights = insights[:20]

        # Save to disk
        self._save_insights(insights)

        return insights

    def _save_insights(self, insights: list[dict]):
        """Save insights to .muninn/insights.json."""
        insights_path = self.mycelium_dir / "insights.json"
        # Load existing, append new with timestamp, keep last 50
        existing = []
        if insights_path.exists():
            try:
                existing = json.loads(insights_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                existing = []
        timestamp = time.strftime("%Y-%m-%d %H:%M")
        for ins in insights:
            ins["timestamp"] = timestamp
        combined = insights + existing
        combined = combined[:50]
        # Atomic write: tempfile + os.replace to avoid corruption on crash
        import tempfile as _tf
        _fd, _tmp = _tf.mkstemp(dir=str(insights_path.parent), suffix=".tmp")
        try:
            with os.fdopen(_fd, "w", encoding="utf-8") as _f:
                json.dump(combined, _f, indent=2, ensure_ascii=False)
            os.replace(_tmp, str(insights_path))
        except BaseException:
            try:
                os.unlink(_tmp)
            except OSError:
                pass
            raise
