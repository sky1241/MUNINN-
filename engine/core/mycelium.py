#!/usr/bin/env python3
"""
Muninn Mycelium — Living co-occurrence network for semantic compression.

The mycelium tracks which concepts appear together across sessions.
Concepts that co-occur frequently get fused into compact blocks.
The mycelium grows, persists on disk, and decays when unused.

Like Yggdrasil's mycelium tracks co-occurrences across 348M papers,
Muninn's mycelium tracks co-occurrences across user sessions.

Usage:
    from mycelium import Mycelium
    m = Mycelium(repo_path)
    m.observe(["bug", "codec", "utf8"])   # record co-occurrence
    m.observe(["scan", "pipeline", "chunks"])
    m.save()                               # persist to disk
    fused = m.get_fusions()                # get fused concept blocks
    m.decay()                              # weaken old connections
"""
import io
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


class Mycelium:
    """A living co-occurrence network that grows with each session."""

    FUSION_THRESHOLD = 5      # co-occur N times -> fuse into one block
    DECAY_HALF_LIFE = 30      # days before connection strength halves
    MAX_CONNECTIONS = 0        # 0 = no limit (adapts to available RAM)
    MIN_CONCEPT_LEN = 3       # ignore tiny words
    IMMORTAL_ZONE_THRESHOLD = 3  # connection in N+ zones = skip decay
    SATURATION_BETA = 0.001       # A4: Lotka-Volterra saturation (0=disabled, 0.001=moderate)
    SATURATION_THRESHOLD = 50     # A4: only apply saturation to connections with count > this
    DEGREE_FILTER_PERCENTILE = 0.05  # S3: top 5% degree concepts = stopwords, no fusion

    def __init__(self, repo_path: Path, federated: bool = False, zone: str = None):
        self.repo_path = Path(repo_path).resolve()
        self.mycelium_dir = self.repo_path / ".muninn"
        self.mycelium_path = self.mycelium_dir / "mycelium.json"
        self.db_path = self.mycelium_dir / "mycelium.db"
        self.federated = federated  # P20.1: if False, zero change to behavior
        self.zone = zone or self.repo_path.name  # P20.2: default zone = repo name
        self._sigmoid_k = 10  # A3: sigmoid steepness for spread_activation (0=disabled)
        self._spectral_gap = None  # A5: computed by detect_zones()
        self.data = self._load()

    def _load(self) -> dict:
        """Load mycelium from disk or create fresh.

        S1 (TIER 3): Auto-detects and migrates JSON -> SQLite.
        Priority: .db (SQLite) > .json (legacy, auto-migrates) > fresh.
        """
        self.mycelium_dir.mkdir(parents=True, exist_ok=True)

        # Case 1: SQLite exists — load from it (check migration completeness)
        if self.db_path.exists():
            # Verify DB is not a partial migration
            try:
                import sqlite3
                conn = sqlite3.connect(str(self.db_path), timeout=5)
                marker = conn.execute(
                    "SELECT value FROM meta WHERE key='migration_complete'"
                ).fetchone()
                conn.close()
                if marker or not self.mycelium_path.exists():
                    # DB is complete OR no JSON to fall back to
                    return self._load_from_sqlite()
                else:
                    # Partial migration: delete corrupt DB and retry
                    self.db_path.unlink()
            except Exception:
                if not self.mycelium_path.exists():
                    return self._load_from_sqlite()
                self.db_path.unlink(missing_ok=True)

        # Case 2: JSON exists — migrate to SQLite, then load
        if self.mycelium_path.exists():
            try:
                self._migrate_json_to_sqlite()
                return self._load_from_sqlite()
            except Exception as e:
                print(f"WARNING: SQLite migration failed, falling back to JSON: {e}",
                      file=sys.stderr)
                # Fallback: load JSON directly
                try:
                    with open(self.mycelium_path, encoding="utf-8") as f:
                        return json.load(f)
                except (json.JSONDecodeError, ValueError, OSError) as e2:
                    print(f"WARNING: mycelium.json load also failed: {e2}",
                          file=sys.stderr)

        # Case 3: Fresh mycelium
        return {
            "version": 1,
            "repo": self.repo_path.name,
            "created": time.strftime("%Y-%m-%d"),
            "updated": time.strftime("%Y-%m-%d"),
            "session_count": 0,
            "connections": {},
            "fusions": {},
        }

    def _load_from_sqlite(self) -> dict:
        """Load mycelium data from SQLite database into memory dict."""
        from .mycelium_db import MyceliumDB, days_to_date
        db = MyceliumDB(self.db_path)
        try:
            data = {
                "version": int(db.get_meta("version", "1")),
                "repo": db.get_meta("repo", self.repo_path.name),
                "created": db.get_meta("created", time.strftime("%Y-%m-%d")),
                "updated": db.get_meta("updated", time.strftime("%Y-%m-%d")),
                "session_count": int(db.get_meta("session_count", "0")),
                "connections": db.get_all_connections(),
                "fusions": db.get_all_fusions(),
            }
        finally:
            db.close()
        return data

    def _migrate_json_to_sqlite(self):
        """Migrate mycelium.json to mycelium.db (one-time operation)."""
        from .mycelium_db import MyceliumDB
        # This creates the .db and renames .json to .json.bak
        db = MyceliumDB.migrate_from_json(self.mycelium_path, self.db_path)
        db.set_meta("migration_complete", "1")
        db.close()

    def save(self):
        """Persist mycelium to disk (SQLite with WAL mode).

        S1 (TIER 3): Writes to SQLite instead of JSON.
        S4 (TIER 3): Flushes pending translations before save.
        No temp files, no pretty-print explosion, crash-safe WAL.
        """
        from .mycelium_db import MyceliumDB, date_to_days, today_days
        self.mycelium_dir.mkdir(exist_ok=True)
        self.data["updated"] = time.strftime("%Y-%m-%d")

        # S4: Flush pending translations before save
        try:
            from .mycelium_db import ConceptTranslator
            translator = ConceptTranslator.get()
            translator.flush_pending()
        except Exception:
            pass

        db = MyceliumDB(self.db_path)
        try:
            # Sync connections: write all from self.data to DB
            # Everything in one transaction for atomicity (crash-safe)
            conns = self.data.get("connections", {})
            fusions = self.data.get("fusions", {})

            with db._conn:
                # Update meta inside transaction
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("version", str(self.data.get("version", 1))))
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("repo", str(self.data.get("repo", self.repo_path.name))))
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("created", str(self.data.get("created", time.strftime("%Y-%m-%d")))))
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("updated", str(self.data.get("updated", time.strftime("%Y-%m-%d")))))
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("session_count", str(self.data.get("session_count", 0))))
                db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("migration_complete", "1"))
                # Clear and rewrite (simpler than diffing for Phase 1)
                db._conn.execute("DELETE FROM edges")
                db._conn.execute("DELETE FROM fusions")
                db._conn.execute("DELETE FROM edge_zones")

                td = today_days()
                for key, conn in conns.items():
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    fs = date_to_days(conn.get("first_seen", "2026-01-01"))
                    ls = date_to_days(conn.get("last_seen", "2026-01-01"))
                    db._conn.execute(
                        "INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (a_id, b_id, conn.get("count", 1), fs, ls)
                    )
                    for zone in conn.get("zones", []):
                        db._conn.execute(
                            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                            (a_id, b_id, zone)
                        )

                for key, fusion in fusions.items():
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    fa = date_to_days(fusion.get("fused_at", "2026-01-01"))
                    db._conn.execute(
                        "INSERT OR REPLACE INTO fusions (a, b, form, strength, fused_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (a_id, b_id, fusion.get("form", f"{a}+{b}"), fusion.get("strength", 1), fa)
                    )
        finally:
            db.close()

    def _key(self, a: str, b: str) -> str:
        """Canonical key for a pair (alphabetical order)."""
        return f"{min(a,b)}|{max(a,b)}"

    def observe(self, concepts: list[str]):
        """Record co-occurrence of concepts in this context.

        Every pair of concepts in the list gets a +1 connection strength.
        This is called when processing user input or compressing text.
        S4 (TIER 3): Non-English concepts auto-translated via tokenizer + Haiku.
        """
        # Filter and normalize
        clean = []
        for c in concepts:
            c = c.lower().strip()
            if len(c) >= self.MIN_CONCEPT_LEN and c not in _STOPWORDS:
                clean.append(c)

        # S4: Normalize non-English concepts to English
        try:
            from .mycelium_db import ConceptTranslator
            translator = ConceptTranslator.get()
            clean = translator.normalize_concepts(clean)
        except Exception:
            pass  # Graceful: no tiktoken/anthropic = no translation

        clean = list(set(clean))  # deduplicate

        conns = self.data["connections"]

        # Record all pairs
        for i in range(len(clean)):
            for j in range(i + 1, len(clean)):
                key = self._key(clean[i], clean[j])
                if key not in conns:
                    conns[key] = {
                        "count": 0,
                        "first_seen": time.strftime("%Y-%m-%d"),
                        "last_seen": time.strftime("%Y-%m-%d"),
                    }
                    if self.federated:
                        conns[key]["zones"] = []
                conns[key]["count"] += 1
                conns[key]["last_seen"] = time.strftime("%Y-%m-%d")
                # P20.2: track which zones this connection appears in
                if self.federated:
                    if "zones" not in conns[key]:
                        conns[key]["zones"] = []
                    if self.zone not in conns[key]["zones"]:
                        conns[key]["zones"].append(self.zone)

        # Check for new fusions
        self._check_fusions()
        if self.federated:
            self._invalidate_zone_cache()

        # Prune only if limit is set, or if memory pressure
        if self.MAX_CONNECTIONS > 0 and len(conns) > self.MAX_CONNECTIONS:
            self._prune_weakest()
        elif len(conns) > 10000:
            # Safety: check RAM only when network gets very large
            self._prune_if_memory_pressure()

    def observe_text(self, text: str):
        """Extract concepts from raw text and observe co-occurrences.

        Works on any text — user messages, code, documentation.
        Chunks text by paragraphs so only nearby concepts co-occur,
        avoiding O(n²) explosion on large documents while keeping
        all concepts (no cap).
        """
        # Split into chunks (paragraphs / double-newline blocks)
        chunks = re.split(r'\n\s*\n', text)

        # For small texts (<50 concepts total), treat as single chunk
        all_words = re.findall(r'[A-Za-zÀ-ÿ_]{4,}', text)
        all_counts = Counter(w.lower() for w in all_words)
        total_unique = sum(1 for w in all_counts if w not in _STOPWORDS)

        if total_unique <= 80:
            # Small text — single observation (original behavior)
            concepts = [w for w in all_counts if w not in _STOPWORDS]
            entities = re.findall(r'[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+)*', text)
            for entity in entities:
                e = entity.lower()
                if e not in _STOPWORDS and len(e) >= 4:
                    concepts.append(e)
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self.observe(concepts)
            return

        # Large text — observe each chunk separately
        # Concepts that are in the same paragraph co-occur
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 20:
                continue
            words = re.findall(r'[A-Za-zÀ-ÿ_]{4,}', chunk)
            word_counts = Counter(w.lower() for w in words)
            concepts = [w for w in word_counts if w not in _STOPWORDS]
            entities = re.findall(r'[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+)*', chunk)
            for entity in entities:
                e = entity.lower()
                if e not in _STOPWORDS and len(e) >= 4:
                    concepts.append(e)
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self.observe(concepts)

    def observe_latex(self, text: str):
        """Observe co-occurrences in LaTeX source, chunked by sections.

        Splits on \\section, \\subsection, \\begin{...} instead of \\n\\n.
        Designed for arXiv .tex files.
        """
        # Split on LaTeX structural commands
        chunks = re.split(
            r'\\(?:section|subsection|subsubsection|paragraph|chapter)'
            r'\*?\{[^}]*\}'
            r'|\\begin\{(?:abstract|theorem|lemma|proof|definition|equation'
            r'|figure|table|algorithm|enumerate|itemize)\}',
            text
        )
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 20:
                continue
            # Strip LaTeX commands but keep words
            clean = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', chunk)
            clean = re.sub(r'\\[a-zA-Z]+', '', clean)
            clean = re.sub(r'[{}$^_~\\]', ' ', clean)
            words = re.findall(r'[A-Za-zÀ-ÿ]{4,}', clean)
            word_counts = Counter(w.lower() for w in words)
            concepts = [w for w in word_counts if w not in _STOPWORDS]
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self.observe(concepts)

    def observe_with_concepts(self, text: str, known_concepts: list[str]):
        """Observe co-occurrences using a provided concept list (e.g. OpenAlex 65K).

        Instead of extracting concepts from text, matches known concepts
        in each chunk. Only concepts actually present in the chunk co-occur.
        """
        # Normalize known concepts for matching
        concept_set = {c.lower().strip() for c in known_concepts if len(c) >= 3}

        # Detect LaTeX vs plain text
        if '\\section' in text or '\\begin{' in text:
            chunks = re.split(
                r'\\(?:section|subsection|subsubsection|paragraph|chapter)'
                r'\*?\{[^}]*\}'
                r'|\\begin\{(?:abstract|theorem|lemma|proof|definition|equation'
                r'|figure|table|algorithm|enumerate|itemize)\}',
                text
            )
        else:
            chunks = re.split(r'\n\s*\n', text)

        for chunk in chunks:
            chunk_lower = chunk.lower()
            if len(chunk_lower) < 20:
                continue
            # Find which known concepts appear in this chunk (word boundaries)
            found = [c for c in concept_set
                     if re.search(r'\b' + re.escape(c) + r'\b', chunk_lower)]
            if len(found) >= 2:
                self.observe(found)

    def _check_fusions(self):
        """Check if any connections crossed the fusion threshold.

        S3 (TIER 3): Blocks fusions for high-degree concepts (universal stopwords).
        A concept connected to >top 5% of all concepts is noise in any language.
        """
        conns = self.data["connections"]
        fusions = self.data["fusions"]

        # S3: Build degree map and compute threshold
        high_degree_concepts = self._get_high_degree_concepts()

        # S3: Retroactively remove fusions involving high-degree stopwords
        if high_degree_concepts:
            to_remove = [k for k in fusions
                         if any(c in high_degree_concepts
                                for c in fusions[k].get("concepts", []))]
            for k in to_remove:
                del fusions[k]

        for key, conn in conns.items():
            if conn["count"] >= self.FUSION_THRESHOLD:
                if key not in fusions:
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    # S3: Block fusion if either concept is a high-degree stopword
                    if a in high_degree_concepts or b in high_degree_concepts:
                        continue
                    fused_form = f"{a}+{b}"
                    fusions[key] = {
                        "concepts": [a, b],
                        "form": fused_form,
                        "strength": conn["count"],
                        "fused_at": time.strftime("%Y-%m-%d"),
                    }
                else:
                    # Update strength to match current count
                    fusions[key]["strength"] = conn["count"]

    def _get_high_degree_concepts(self) -> set:
        """S3: Identify concepts with too many connections (universal stopwords).

        A concept in the top DEGREE_FILTER_PERCENTILE by degree is noise.
        This works for any language — no dictionary needed.
        """
        conns = self.data["connections"]
        if len(conns) < 50:
            return set()  # Too small for statistical filtering

        # Count degree per concept
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

        # Find the threshold: top X% by degree
        sorted_degrees = sorted(degree.values(), reverse=True)
        cutoff_idx = max(1, int(len(sorted_degrees) * self.DEGREE_FILTER_PERCENTILE))
        threshold = sorted_degrees[min(cutoff_idx, len(sorted_degrees) - 1)]

        # Must be at least degree 20 to be considered a stopword
        threshold = max(threshold, 20)

        return {c for c, d in degree.items() if d >= threshold}

    def _prune_weakest(self):
        """Remove weakest connections to stay under MAX_CONNECTIONS."""
        conns = self.data["connections"]
        fusions = self.data["fusions"]
        # Sort all non-fused connections by strength ascending
        prunable = sorted(
            (k for k in conns if k not in fusions),
            key=lambda k: conns[k]["count"]
        )
        to_remove = len(conns) - self.MAX_CONNECTIONS
        for key in prunable[:to_remove]:
            del conns[key]

    def _prune_if_memory_pressure(self):
        """Prune only if system RAM is running low (< 500MB free)."""
        try:
            import os
            if hasattr(os, 'sysconf'):  # Unix
                free = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_AVPHYS_PAGES')
            else:  # Windows
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong),
                                ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong),
                                ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong),
                                ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong),
                                ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    return  # API failed, don't prune
                free = stat.ullAvailPhys
            if free < 500 * 1024 * 1024:  # < 500MB free
                target = len(self.data["connections"]) // 2
                self.MAX_CONNECTIONS = target
                self._prune_weakest()
                self.MAX_CONNECTIONS = 0
        except Exception:
            pass  # Can't check RAM = don't prune

    def decay(self, days: int = None):
        """Weaken connections that haven't been seen recently.

        Connections that haven't been reinforced decay over time.
        Dead connections (count drops to 0) are removed.
        """
        if days is None:
            days = self.DECAY_HALF_LIFE
        if days <= 0:
            return 0

        today = time.strftime("%Y-%m-%d")
        conns = self.data["connections"]
        dead = []

        for key, conn in conns.items():
            # P20.4: immortal connections (in 3+ zones) skip decay
            if self.federated and "zones" in conn:
                if len(conn["zones"]) >= self.IMMORTAL_ZONE_THRESHOLD:
                    continue

            try:
                from datetime import datetime
                last = datetime.strptime(conn["last_seen"], "%Y-%m-%d")
                now = datetime.strptime(today, "%Y-%m-%d")
                age_days = (now - last).days
            except (ValueError, KeyError):
                age_days = 0

            if age_days > days:
                # Halve the count for each half-life period passed
                periods = age_days // days
                new_count = conn["count"] >> periods  # integer division by 2^periods

                # A4: Lotka-Volterra saturation — dw -= beta * w^2
                # Only for large connections (w > threshold). Prevents unbounded growth.
                # Source: nlin/0009025 (Lotka-Volterra carrying capacity)
                if (self.SATURATION_BETA > 0 and
                        new_count > self.SATURATION_THRESHOLD):
                    saturation_loss = int(self.SATURATION_BETA * new_count * new_count)
                    new_count = max(1, new_count - saturation_loss)

                if new_count <= 0:
                    dead.append(key)
                else:
                    conn["count"] = new_count

        # Remove dead connections and their fusions
        for key in dead:
            del conns[key]
            if key in self.data["fusions"]:
                del self.data["fusions"][key]

        return len(dead)

    def effective_weight(self, key: str) -> float:
        """P20.3: TF-IDF inverse — rare across zones = important, ubiquitous = small.

        weight = count * log(1 + total_zones / zones_present)
        If not federated, returns raw count.
        """
        conn = self.data["connections"].get(key)
        if not conn:
            return 0
        count = conn["count"]
        if not self.federated or "zones" not in conn:
            return float(count)
        import math
        total_zones = self._count_total_zones()
        zones_present = max(1, len(conn["zones"]))
        return count * math.log(1 + total_zones / zones_present)

    def _count_total_zones(self) -> int:
        """Count distinct zones across all connections."""
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

    def get_fusions(self) -> dict:
        """Get all fused concept blocks.

        Returns dict of {key: {concepts, form, strength}}.
        These are concept pairs that co-occur so often they should
        be compressed as a single unit.
        """
        return self.data.get("fusions", {})

    def get_compression_rules(self) -> dict:
        """Generate compression rules from the mycelium.

        Returns a dict {pattern: replacement} for the compressor.
        Strongest fusions -> shortest codes.
        """
        fusions = self.get_fusions()
        if not fusions:
            return {}

        # Sort by strength (most fused first)
        ranked = sorted(fusions.items(), key=lambda x: x[1]["strength"], reverse=True)

        rules = {}
        for key, fusion in ranked:
            concepts = fusion["concepts"]
            # The compression rule: when both concepts appear nearby,
            # they can be referenced as a single block
            rules[key] = {
                "concepts": concepts,
                "form": fusion["form"],
                "strength": fusion["strength"],
            }

        return rules

    def get_related(self, concept: str, top_n: int = 5) -> list[tuple[str, float]]:
        """Get concepts most strongly connected to a given concept.

        Returns list of (related_concept, weight) sorted by effective weight.
        In federated mode, prioritizes connections from the current zone.
        """
        concept = concept.lower().strip()
        conns = self.data["connections"]
        related = []
        for key, val in conns.items():
            parts = key.split("|")
            if len(parts) != 2:
                continue
            if concept in parts:
                other = parts[1] if parts[0] == concept else parts[0]
                if self.federated:
                    weight = self.effective_weight(key)
                    # P20.7: boost connections from current zone
                    if "zones" in val and self.zone in val["zones"]:
                        weight *= 2.0
                else:
                    weight = float(val["count"])
                related.append((other, weight))
        related.sort(key=lambda x: x[1], reverse=True)
        return related[:top_n]

    def spread_activation(self, seeds: list[str], hops: int = 2,
                          decay: float = 0.5, top_n: int = 20) -> list[tuple[str, float]]:
        """Spreading activation through the semantic network (Collins & Loftus 1975).

        Instead of keyword matching, propagates activation from seed concepts
        through weighted connections. Finds semantically related concepts that
        share NO words with the query.

        Args:
            seeds: starting concepts (e.g. query words)
            hops: how many steps to propagate (2 = neighbors of neighbors)
            decay: activation multiplier per hop (0.5 = halves each step)
            top_n: max concepts to return

        Returns:
            list of (concept, activation) sorted by activation descending.
            Seeds themselves are excluded from results.
        """
        conns = self.data["connections"]
        if not conns:
            return []

        # Build adjacency index for fast lookup
        adj = {}  # concept -> [(neighbor, weight)]
        for key, val in conns.items():
            parts = key.split("|")
            if len(parts) != 2:
                continue
            a, b = parts
            w = float(val["count"])
            adj.setdefault(a, []).append((b, w))
            adj.setdefault(b, []).append((a, w))

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

        # Remove seeds, sort by activation
        results = [(c, a) for c, a in activation.items() if c not in seed_set]
        # A3: Sigmoid filter — suppress noise, preserve strong signals
        # sigma(x) = 1 / (1 + e^(-k*(x - x0)))
        # k=10 (steepness), x0=median activation (adaptive threshold)
        # Source: cond-mat/0202047 (quasispecies sigmoid), Goldbeter-Koshland
        if results and self._sigmoid_k > 0:
            import math
            activations = [a for _, a in results]
            x0 = sorted(activations)[len(activations) // 2]  # median as threshold
            results = [(c, 1.0 / (1.0 + math.exp(-self._sigmoid_k * (a - x0))))
                       for c, a in results]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def get_learned_fillers(self) -> list[str]:
        """Identify filler words from the mycelium.

        A filler = a word that appears in MANY connections but NEVER fuses.
        High connectivity + zero fusion = noise word, carries no information.
        These are candidates for L2 (filler word removal).
        """
        conns = self.data["connections"]
        fusions = self.data["fusions"]

        if not conns:
            return []

        # Count how many connections each concept participates in
        concept_conn_count = {}
        for key in conns:
            parts = key.split("|")
            if len(parts) != 2:
                continue
            a, b = parts
            concept_conn_count[a] = concept_conn_count.get(a, 0) + 1
            concept_conn_count[b] = concept_conn_count.get(b, 0) + 1

        # Concepts that appear in fusions
        fused_concepts = set()
        for key, fusion in fusions.items():
            for c in fusion["concepts"]:
                fused_concepts.add(c)

        # Fillers: in 10+ connections but never fused = noise
        fillers = []
        for concept, count in concept_conn_count.items():
            if count >= 10 and concept not in fused_concepts:
                fillers.append(concept)

        return sorted(fillers)

    def get_learned_abbreviations(self) -> dict:
        """Generate abbreviation rules from strong fusions.

        Only creates abbreviations when one concept is a prefix/substring
        of the other (e.g., "compression" -> "comp", "encoding" -> "enc").
        Random co-occurrences like "compression|lines" are NOT abbreviations.

        Returns dict {long_form: short_form}.
        """
        fusions = self.data["fusions"]
        if not fusions:
            return {}

        abbrevs = {}
        for key, fusion in fusions.items():
            if fusion["strength"] >= 8:
                a, b = fusion["concepts"]
                # Only abbreviate when short is a prefix of long
                # (e.g., "comp" is prefix of "compression")
                long, short = (a, b) if len(a) > len(b) else (b, a)
                if long.startswith(short) and len(short) >= 3:
                    abbrevs[long] = short
        return abbrevs

    def start_session(self):
        """Mark the beginning of a new session."""
        self.data["session_count"] = self.data.get("session_count", 0) + 1

    def detect_zones(self, k: int = None) -> dict[str, list[str]]:
        """P20.5+6: Laplacien spectral clustering — detect semantic zones.

        Builds co-occurrence matrix from connections, computes normalized
        Laplacian, extracts K eigenvectors, clusters with KMeans.
        Auto-names each zone by its dominant concepts (P20.6).

        Returns {zone_name: [concept1, concept2, ...]}.
        Requires numpy + scipy + sklearn. Graceful fallback if not installed.
        """
        conns = self.data["connections"]
        if len(conns) < 10:
            return {}

        try:
            import numpy as np
            from scipy import sparse
            from scipy.sparse.linalg import eigsh
            from sklearn.cluster import KMeans
        except ImportError:
            print("detect_zones requires: pip install numpy scipy scikit-learn",
                  file=sys.stderr)
            return {}

        # 1. Build concept index and sparse matrix
        concepts = set()
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

        # Build sparse adjacency
        rows, cols, vals = [], [], []
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
        except Exception as e:
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
        conns = self.data["connections"]
        tagged = 0
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
        zone_counts = {}
        for conn in self.data["connections"].values():
            if "zones" in conn:
                for z in conn["zones"]:
                    zone_counts[z] = zone_counts.get(z, 0) + 1
        return dict(sorted(zone_counts.items(), key=lambda x: x[1], reverse=True))

    def get_bridges(self) -> list[tuple[str, str, str, float]]:
        """P20.8: Get inter-zone bridges (connections that span 2+ zones).

        Returns list of (concept_a, concept_b, zones, effective_weight).
        """
        bridges = []
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

    # ── B2: Graph anomaly detection ────────────────────────────────

    def detect_anomalies(self) -> dict:
        """B2: Detect structural anomalies in the mycelium graph.

        Returns dict with keys:
          - "isolated": concepts with degree <= 1 (poorly connected)
          - "hubs": concepts with degree > mean + 2*std (monopolies)
          - "weak_zones": zone names where mean connection count < 2
        Source: LITERATURE #16 (graph anomalies), BS-1 Cell Bio briefing
        """
        conns = self.data["connections"]
        if not conns:
            return {"isolated": [], "hubs": [], "weak_zones": []}

        # Build degree map
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
            for zone_name, count in zones.items():
                # Get connections in this zone
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
        conns = self.data["connections"]
        if len(conns) < 10:
            return []

        # Build degree map (lightweight — only counts)
        degree = {}
        for key in conns:
            parts = key.split("|")
            if len(parts) != 2:
                continue
            a, b = parts
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1

        if not degree:
            return []

        # For large graphs (>100K connections), only analyze mid-range concepts
        # Top concepts are always connected; blind spots live in the middle tier
        max_concepts = 500
        if len(degree) > max_concepts:
            # Take concepts with degree in [10, 90th percentile] — the "interesting" range
            sorted_by_deg = sorted(degree.items(), key=lambda x: -x[1])
            p90 = sorted_by_deg[len(sorted_by_deg) // 10][1] if len(sorted_by_deg) > 10 else 999999
            mid_range = [(c, d) for c, d in sorted_by_deg if 10 <= d <= p90]
            mid_range.sort(key=lambda x: -x[1])
            top_concepts_set = set(c for c, _ in mid_range[:max_concepts])
        else:
            top_concepts_set = set(degree.keys())

        # Build connection set and adjacency ONLY for top concepts
        conn_set = set()
        adj = {}
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
        except Exception:
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

    # ── P20b: Meta-mycelium sync ──────────────────────────────────

    @staticmethod
    def meta_path() -> Path:
        """Path to the shared meta-mycelium (~/.muninn/meta_mycelium.json).
        Note: kept for backward compat. SQLite version is meta_mycelium.db."""
        return Path.home() / ".muninn" / "meta_mycelium.json"

    @staticmethod
    def meta_db_path() -> Path:
        """Path to the shared meta-mycelium SQLite DB."""
        return Path.home() / ".muninn" / "meta_mycelium.db"

    def sync_to_meta(self):
        """Push local connections to the shared meta-mycelium.

        S1 (TIER 3): Writes to SQLite meta_mycelium.db.
        Falls back to JSON meta_mycelium.json for backward compat.

        Merge strategy:
        - counts: take max (not sum, to avoid inflation on repeated syncs)
        - zones: union
        - first_seen: earliest
        - last_seen: latest
        - fusions: merge if exists in meta, add if new
        """
        from .mycelium_db import MyceliumDB, date_to_days, today_days

        meta_db_p = self.meta_db_path()
        meta_json_p = self.meta_path()
        meta_db_p.parent.mkdir(exist_ok=True)

        # Auto-migrate JSON meta to SQLite if needed
        if meta_json_p.exists() and not meta_db_p.exists():
            try:
                MyceliumDB.migrate_from_json(meta_json_p, meta_db_p)
            except Exception as e:
                print(f"WARNING: meta migration failed: {e}", file=sys.stderr)

        db = MyceliumDB(meta_db_p)
        try:
            # Track repo
            repos_str = db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            if self.repo_path.name not in repos:
                repos.append(self.repo_path.name)
                db.set_meta("repos", ",".join(repos))
            db.set_meta("type", "meta")
            db.set_meta("updated", time.strftime("%Y-%m-%d"))
            if not db.get_meta("created"):
                db.set_meta("created", time.strftime("%Y-%m-%d"))

            # Merge connections
            local_conns = self.data["connections"]
            zone = self.zone

            with db._conn:
                for key, conn in local_conns.items():
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    fs = date_to_days(conn.get("first_seen", "2026-01-01"))
                    ls = date_to_days(conn.get("last_seen", "2026-01-01"))

                    # Upsert with max(count), min(first_seen), max(last_seen)
                    db._conn.execute("""
                        INSERT INTO edges (a, b, count, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(a, b) DO UPDATE SET
                            count = MAX(count, excluded.count),
                            first_seen = MIN(first_seen, excluded.first_seen),
                            last_seen = MAX(last_seen, excluded.last_seen)
                    """, (a_id, b_id, conn["count"], fs, ls))

                    # Merge zone
                    db._conn.execute(
                        "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                        (a_id, b_id, zone)
                    )

                # Merge fusions
                local_fusions = self.data.get("fusions", {})
                for key, fusion in local_fusions.items():
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = parts
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    fa = date_to_days(fusion.get("fused_at", "2026-01-01"))
                    db._conn.execute("""
                        INSERT INTO fusions (a, b, form, strength, fused_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(a, b) DO UPDATE SET
                            strength = MAX(strength, excluded.strength)
                    """, (a_id, b_id, fusion["form"], fusion["strength"], fa))
        finally:
            db.close()

        return len(local_conns)

    def pull_from_meta(self, query_concepts: list[str] = None, max_pull: int = 500):
        """Pull relevant connections from meta-mycelium into local.

        S1 (TIER 3): Reads from SQLite meta_mycelium.db.
        Falls back to JSON for backward compat.

        If query_concepts given, only pulls connections involving those concepts.
        Otherwise pulls top connections by count.
        Does NOT overwrite local data — only adds what's missing.
        """
        meta_db_p = self.meta_db_path()
        meta_json_p = self.meta_path()

        # Try SQLite first, then JSON fallback
        if meta_db_p.exists():
            return self._pull_from_meta_sqlite(query_concepts, max_pull)
        elif meta_json_p.exists():
            return self._pull_from_meta_json(query_concepts, max_pull)
        return 0

    def _pull_from_meta_sqlite(self, query_concepts, max_pull):
        """Pull from SQLite meta-mycelium."""
        from .mycelium_db import MyceliumDB

        db = MyceliumDB(self.meta_db_path())
        try:
            local_conns = self.data["connections"]
            pulled = 0
            id_to_name = {v: k for k, v in db._concept_cache.items()}

            if query_concepts:
                query_set = {c.lower().strip() for c in query_concepts}
                # Find concept IDs for query terms
                query_ids = set()
                for c in query_set:
                    cid = db._concept_cache.get(c)
                    if cid is not None:
                        query_ids.add(cid)

                if not query_ids:
                    return 0

                # Pull connections involving query concepts
                placeholders = ",".join("?" * len(query_ids))
                rows = db._conn.execute(f"""
                    SELECT a, b, count, first_seen, last_seen FROM edges
                    WHERE a IN ({placeholders}) OR b IN ({placeholders})
                    ORDER BY count DESC LIMIT ?
                """, list(query_ids) + list(query_ids) + [max_pull]).fetchall()
            else:
                rows = db._conn.execute(
                    "SELECT a, b, count, first_seen, last_seen FROM edges "
                    "ORDER BY count DESC LIMIT ?", (max_pull,)
                ).fetchall()

            from .mycelium_db import days_to_date

            for row in rows:
                a_name = id_to_name.get(row[0], db._concept_name(row[0]))
                b_name = id_to_name.get(row[1], db._concept_name(row[1]))
                key = f"{a_name}|{b_name}"
                if key not in local_conns:
                    conn = {
                        "count": row[2],
                        "first_seen": days_to_date(row[3]),
                        "last_seen": days_to_date(row[4]),
                    }
                    # Load zones
                    zones = [r[0] for r in db._conn.execute(
                        "SELECT zone FROM edge_zones WHERE a=? AND b=?",
                        (row[0], row[1])
                    )]
                    if zones:
                        conn["zones"] = zones
                    local_conns[key] = conn
                    pulled += 1

            # Pull fusions for pulled connections
            local_fusions = self.data.setdefault("fusions", {})
            for key in list(local_conns.keys()):
                if key in local_fusions:
                    continue
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a_id = db._concept_cache.get(parts[0])
                b_id = db._concept_cache.get(parts[1])
                if a_id is None or b_id is None:
                    continue
                row = db._conn.execute(
                    "SELECT form, strength, fused_at FROM fusions WHERE a=? AND b=?",
                    (a_id, b_id)
                ).fetchone()
                if row:
                    local_fusions[key] = {
                        "concepts": list(parts),
                        "form": row[0],
                        "strength": row[1],
                        "fused_at": days_to_date(row[2]),
                    }
        finally:
            db.close()

        return pulled

    def _pull_from_meta_json(self, query_concepts, max_pull):
        """Pull from legacy JSON meta-mycelium (backward compat)."""
        meta_p = self.meta_path()
        try:
            with open(meta_p, encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, ValueError):
            return 0

        meta_conns = meta.get("connections", {})
        local_conns = self.data["connections"]
        pulled = 0

        if query_concepts:
            query_set = {c.lower().strip() for c in query_concepts}
            candidates = []
            for key, conn in meta_conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                if a in query_set or b in query_set:
                    candidates.append((key, conn))
            candidates.sort(key=lambda x: x[1]["count"], reverse=True)
            candidates = candidates[:max_pull]
        else:
            candidates = sorted(
                meta_conns.items(), key=lambda x: x[1]["count"], reverse=True
            )[:max_pull]

        import copy
        for key, conn in candidates:
            if key not in local_conns:
                local_conns[key] = copy.deepcopy(conn)
                pulled += 1

        meta_fusions = meta.get("fusions", {})
        local_fusions = self.data.setdefault("fusions", {})
        for key in list(local_conns.keys()):
            if key in meta_fusions and key not in local_fusions:
                local_fusions[key] = copy.deepcopy(meta_fusions[key])

        return pulled

    def status(self) -> str:
        """Print mycelium status."""
        conns = self.data["connections"]
        fusions = self.data["fusions"]
        sessions = self.data.get("session_count", 0)

        lines = [
            f"=== MUNINN MYCELIUM: {self.data['repo']} ===",
            f"  Mode: {'FEDERATED' if self.federated else 'local'}",
            f"  Zone: {self.zone}",
            f"  Sessions: {sessions}",
            f"  Connections: {len(conns)}",
            f"  Fusions: {len(fusions)}",
            f"  Updated: {self.data.get('updated', '?')}",
        ]

        if self.federated:
            zones = self.get_zones()
            if zones:
                lines.append(f"\n  Zones ({len(zones)}):")
                for z, count in zones.items():
                    marker = " <-- current" if z == self.zone else ""
                    lines.append(f"    {z}: {count} connections{marker}")
            bridges = self.get_bridges()
            if bridges:
                lines.append(f"\n  Bridges ({len(bridges)}):")
                for a, b, z, w in bridges[:10]:
                    lines.append(f"    {a}|{b}: zones={z} weight={w:.1f}")

        if conns:
            # Top 10 strongest connections (use effective weight in federated mode)
            if self.federated:
                top = sorted(conns.items(),
                           key=lambda x: self.effective_weight(x[0]),
                           reverse=True)[:10]
            else:
                top = sorted(conns.items(),
                           key=lambda x: x[1]["count"], reverse=True)[:10]
            lines.append(f"\n  Top connections:")
            for key, conn in top:
                fused = " [FUSED]" if key in fusions else ""
                if self.federated:
                    w = self.effective_weight(key)
                    zones_str = f" zones={conn.get('zones', [])}"
                    lines.append(f"    {key}: {conn['count']}x (eff={w:.1f}){zones_str}{fused}")
                else:
                    lines.append(f"    {key}: {conn['count']}x{fused}")

        if fusions:
            lines.append(f"\n  Fusions ({len(fusions)}):")
            for key, fusion in sorted(fusions.items(),
                                       key=lambda x: x[1]["strength"],
                                       reverse=True)[:10]:
                lines.append(f"    {fusion['concepts']} -> {fusion['form']} "
                           f"(strength={fusion['strength']})")

        return "\n".join(lines)


# Stopwords — never track these as concepts
_STOPWORDS = {
    # English
    "this", "that", "with", "from", "have", "been", "will", "would", "could",
    "should", "what", "when", "where", "which", "while", "their", "there",
    "they", "them", "then", "than", "these", "those", "each", "every",
    "some", "also", "just", "like", "make", "only", "over", "such", "after",
    "before", "into", "about", "between", "through", "during", "again",
    "further", "more", "most", "other", "very", "here", "your", "does",
    "doing", "done", "being", "were", "because", "both", "same",
    # French
    "pour", "dans", "avec", "sont", "plus", "tout", "mais", "cette",
    "comme", "elle", "nous", "vous", "leur", "faire", "peut", "bien",
    "encore", "aussi", "autre", "quand", "etre", "avoir", "fait",
    # Programming
    "print", "return", "import", "from", "self", "class", "function",
    "const", "true", "false", "none", "else", "elif", "pass", "break",
    "continue", "lambda", "yield", "async", "await", "raise", "except",
    "finally", "assert", "global", "default", "require", "module",
    "name", "type", "data", "file", "path", "list", "dict", "args",
    "kwargs", "init", "main", "test", "open", "read", "write", "close",
    "string", "number", "boolean", "object", "array", "append", "items",
    "keys", "values", "update", "float", "format", "strip", "split",
    "join", "replace", "encoding", "decode", "encode", "input", "output",
}


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Muninn Mycelium — living compression network")
    parser.add_argument("command", choices=["status", "observe", "decay", "simulate", "zones", "detect", "sync"])
    parser.add_argument("repo", help="Path to the repo")
    parser.add_argument("--text", help="Text to observe (for observe command)")
    parser.add_argument("--file", help="File to observe (for observe command)")
    parser.add_argument("--federated", action="store_true", help="Enable federated mode (P20)")
    parser.add_argument("--zone", help="Zone name for federated mode")
    args = parser.parse_args()

    m = Mycelium(Path(args.repo), federated=args.federated, zone=args.zone)

    if args.command == "status":
        print(m.status())

    elif args.command == "observe":
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
            m.observe_text(text)
            m.save()
            print(f"Observed {args.file}")
            print(m.status())
        elif args.text:
            m.observe_text(args.text)
            m.save()
            print(f"Observed text input")
            print(m.status())
        else:
            print("ERROR: --text or --file required")

    elif args.command == "decay":
        dead = m.decay()
        m.save()
        print(f"Decayed: {dead} dead connections removed")
        print(m.status())

    elif args.command == "simulate":
        # Simulate 10 sessions to show mycelium growth
        print("=== MYCELIUM GROWTH SIMULATION ===\n")
        m.start_session()

        # Simulate typical Sky sessions (20 sessions to see fusions emerge)
        sessions = [
            "bug codec utf8 encoding windows python crash fix",
            "scan pipeline chunks papers arxiv openalex data",
            "tree root branch leaf budget lines memory compression",
            "bug fix codec encoding test validation ci",
            "compression tokens memory tree root branch budget",
            "scan data pipeline chunks arxiv papers results",
            "bug codec fix encoding utf8 windows crash",
            "tree memory compression budget tokens root branch leaf",
            "scan pipeline data chunks arxiv openalex snapshot",
            "bug fix codec utf8 encoding validation test ci",
            "codec bug crash encoding utf8 fix windows",
            "pipeline scan arxiv chunks data papers openalex",
            "memory tree compression root branch tokens budget",
            "encoding codec bug fix crash validation windows",
            "tree compression memory tokens budget branch root",
            "scan arxiv pipeline chunks papers data results",
            "bug codec encoding utf8 fix crash windows python",
            "compression tree memory root branch leaf budget tokens",
            "pipeline scan chunks arxiv data openalex papers",
            "codec bug encoding utf8 fix validation crash ci",
        ]

        for i, session_text in enumerate(sessions):
            m.start_session()
            m.observe_text(session_text)
            conns = len(m.data["connections"])
            fusions = len(m.data["fusions"])
            print(f"  Session {i+1}: +observe -> {conns} connections, {fusions} fusions")

        m.save()
        print(f"\n{m.status()}")

        rules = m.get_compression_rules()
        if rules:
            print(f"\n  Compression rules generated:")
            for key, rule in rules.items():
                print(f"    {rule['concepts']} -> '{rule['form']}' (strength={rule['strength']})")

    elif args.command == "zones":
        if not m.federated:
            print("Federated mode is OFF. Use --federated to enable.")
            print(f"Current mycelium: {len(m.data['connections'])} connections (local mode)")
        else:
            zones = m.get_zones()
            bridges = m.get_bridges()
            print(f"=== ZONE MAP: {m.data['repo']} ===")
            print(f"  Total zones: {len(zones)}")
            print(f"  Total bridges: {len(bridges)}")
            if zones:
                print(f"\n  Continents:")
                for z, count in zones.items():
                    marker = " <-- current" if z == m.zone else ""
                    print(f"    {z}: {count} connections{marker}")
            if bridges:
                print(f"\n  Ponts inter-zones (top 20):")
                for a, b, z, w in bridges[:20]:
                    print(f"    {a}|{b}: {' <-> '.join(z)} (weight={w:.1f})")

    elif args.command == "detect":
        print(f"Detecting zones in {m.data['repo']} ({len(m.data['connections'])} connections)...")
        zones = m.detect_zones()
        if zones:
            print(f"\n=== {len(zones)} ZONES DETECTED ===")
            for name, members in zones.items():
                print(f"\n  [{name}] ({len(members)} concepts)")
                print(f"    Top: {', '.join(members[:15])}")
        else:
            print("Not enough connections to detect zones (need 10+)")

    elif args.command == "sync":
        pushed = m.sync_to_meta()
        meta_db_p = Mycelium.meta_db_path()
        print(f"Synced {pushed} connections from {m.data['repo']} -> {meta_db_p}")
        # Show meta status
        if meta_db_p.exists():
            from .mycelium_db import MyceliumDB as _MDB
            _db = _MDB(meta_db_p)
            repos_str = _db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            total = _db.connection_count()
            _db.close()
            print(f"Meta: {total} connections from {len(repos)} repos ({', '.join(repos)})")


if __name__ == "__main__":
    main()
