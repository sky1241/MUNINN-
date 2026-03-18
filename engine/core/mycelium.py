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

# Import mycelium_db — works both as package (from .mycelium_db) and standalone
try:
    from .mycelium_db import MyceliumDB, days_to_date, date_to_days, today_days
    try:
        from .mycelium_db import ConceptTranslator
    except ImportError:
        ConceptTranslator = None  # type: ignore[assignment,misc]
except ImportError:
    from mycelium_db import MyceliumDB, days_to_date, date_to_days, today_days  # type: ignore[no-redef]
    try:
        from mycelium_db import ConceptTranslator  # type: ignore[no-redef]
    except ImportError:
        ConceptTranslator = None  # type: ignore[assignment,misc]

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
        self._db = None  # Persistent DB handle (lazy mode)
        self._high_degree_cache = None  # Cached high-degree concepts (reset on save)
        self._adj_cache = None  # Cached adjacency list {concept: [(neighbor, weight)]}
        self._adj_cache_max_weight = 0.0  # max edge weight for normalization
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
                    try:
                        self.db_path.unlink()
                    except PermissionError:
                        pass  # Windows: file locked, skip cleanup
            except Exception:
                if not self.mycelium_path.exists():
                    return self._load_from_sqlite()
                try:
                    self.db_path.unlink(missing_ok=True)
                except PermissionError:
                    pass  # Windows: file locked, skip cleanup

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
        """Load mycelium meta from SQLite. Connections stay on disk (lazy mode).

        TIER 3 Phase 2: No more loading millions of connections into RAM.
        self._db stays open for direct SQL queries throughout the session.
        self.data["connections"] and self.data["fusions"] are empty dicts
        (backward compat stubs — all real access goes through self._db).
        """
        self._db = MyceliumDB(self.db_path)
        data = {
            "version": int(self._db.get_meta("version", "1")),
            "repo": self._db.get_meta("repo", self.repo_path.name),
            "created": self._db.get_meta("created", time.strftime("%Y-%m-%d")),
            "updated": self._db.get_meta("updated", time.strftime("%Y-%m-%d")),
            "session_count": int(self._db.get_meta("session_count", "0")),
            "connections": {},  # Empty — queries go through self._db
            "fusions": {},      # Empty — queries go through self._db
        }
        return data

    def _migrate_json_to_sqlite(self):
        """Migrate mycelium.json to mycelium.db (one-time operation)."""
        # This creates the .db and renames .json to .json.bak
        db = MyceliumDB.migrate_from_json(self.mycelium_path, self.db_path)
        db.set_meta("migration_complete", "1")
        db.close()

    def save(self):
        """Persist mycelium to disk (SQLite with WAL mode).

        TIER 3 Phase 2: In lazy mode, data is already on disk.
        save() just commits pending writes and updates meta.
        """
        self.mycelium_dir.mkdir(exist_ok=True)
        self.data["updated"] = time.strftime("%Y-%m-%d")
        # Invalidate caches (degree distribution may have changed via decay)
        self._high_degree_cache = None
        # Full fusion scan: clean up high-degree fusions that were created before
        # the degree distribution stabilized
        self._check_fusions()

        # S4: Flush pending translations before save
        try:
            if ConceptTranslator:
                translator = ConceptTranslator.get()
                translator.flush_pending()
        except Exception:
            pass

        if self._db is not None:
            # Lazy mode: data is already in SQLite, just update meta + commit
            with self._db._conn:
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("version", str(self.data.get("version", 1))))
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("repo", str(self.data.get("repo", self.repo_path.name))))
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("created", str(self.data.get("created", time.strftime("%Y-%m-%d")))))
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("updated", str(self.data.get("updated", time.strftime("%Y-%m-%d")))))
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("session_count", str(self.data.get("session_count", 0))))
                self._db._conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                       ("migration_complete", "1"))
        else:
            # Fallback: no DB yet (fresh install), create and write everything
            db = MyceliumDB(self.db_path)
            try:
                conns = self.data.get("connections", {})
                fusions = self.data.get("fusions", {})
                with db._conn:
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
                            (a_id, b_id, conn.get("count", 1), fs, ls))
                        for zone in conn.get("zones", []):
                            db._conn.execute(
                                "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                                (a_id, b_id, zone))
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
                            (a_id, b_id, fusion.get("form", f"{a}+{b}"), fusion.get("strength", 1), fa))
            finally:
                db.close()
                self._db = MyceliumDB(self.db_path)  # Open persistent handle

    def close(self):
        """Close the persistent DB handle (for cleanup / tests)."""
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None

    def _key(self, a: str, b: str) -> str:
        """Canonical key for a pair (alphabetical order)."""
        return f"{min(a,b)}|{max(a,b)}"

    def observe(self, concepts: list[str], arousal: float = 0.0):
        """Record co-occurrence of concepts in this context.

        Every pair of concepts in the list gets a +E(a) connection strength.
        V6A (Richter-Levin 2003): E(a) = 1 + kappa * a^n / (a^n + theta^n)
        When arousal=0, E(a)=1.0 (backward compatible, same as +1).
        This is called when processing user input or compressing text.
        S4 (TIER 3): Non-English concepts auto-translated via tokenizer + Haiku.
        """
        # Filter and normalize
        if not concepts:
            return
        clean = []
        for c in concepts:
            c = c.lower().strip()
            if len(c) >= self.MIN_CONCEPT_LEN and c not in _STOPWORDS:
                clean.append(c)

        # S4: Normalize non-English concepts to English
        try:
            if ConceptTranslator:
                translator = ConceptTranslator.get()
                clean = translator.normalize_concepts(clean)
        except Exception:
            pass  # Graceful: no tiktoken/anthropic = no translation

        clean = list(set(clean))  # deduplicate

        # V6A: Emotional tagging — Hill function boost (Richter-Levin 2003)
        _kappa = 1.0
        _hill_n = 3
        _hill_theta = 0.5
        a = max(0.0, float(arousal))
        if a > 0.0:
            e_a = 1.0 + _kappa * (a ** _hill_n) / (a ** _hill_n + _hill_theta ** _hill_n)
        else:
            e_a = 1.0

        # Record all pairs — direct SQL upsert (lazy mode)
        if self._db is not None:
            pairs = []
            for i in range(len(clean)):
                for j in range(i + 1, len(clean)):
                    pairs.append((clean[i], clean[j]))
            if pairs:
                td = today_days()
                with self._db._conn:
                    for ca, cb in pairs:
                        a_key = min(ca, cb)
                        b_key = max(ca, cb)
                        a_id = self._db._get_or_create_concept(a_key)
                        b_id = self._db._get_or_create_concept(b_key)
                        self._db._conn.execute("""
                            INSERT INTO edges (a, b, count, first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                count = count + ?,
                                last_seen = ?
                        """, (a_id, b_id, e_a, td, td, e_a, td))
                        if self.federated:
                            self._db._conn.execute(
                                "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                                (a_id, b_id, self.zone))
        else:
            # Fallback: in-memory dict (fresh install before first save)
            conns = self.data["connections"]
            for i in range(len(clean)):
                for j in range(i + 1, len(clean)):
                    key = self._key(clean[i], clean[j])
                    if key not in conns:
                        conns[key] = {"count": 0, "first_seen": time.strftime("%Y-%m-%d"),
                                      "last_seen": time.strftime("%Y-%m-%d")}
                    conns[key]["count"] += e_a
                    conns[key]["last_seen"] = time.strftime("%Y-%m-%d")
                    # Track zone for federated mode
                    if self.federated and self.zone:
                        zones = conns[key].setdefault("zones", [])
                        if self.zone not in zones:
                            zones.append(self.zone)

        # Check for new fusions (only observed pairs in lazy mode)
        observed_pairs = [(clean[i], clean[j])
                          for i in range(len(clean)) for j in range(i + 1, len(clean))]
        self._check_fusions(observed_pairs=observed_pairs)

        # P41: Self-referential growth — observe fusions as second-order co-occurrences
        if clean and not getattr(self, '_p41_recursion_guard', False):
            fusion_concepts = []
            clean_set = set(clean)
            if self._db is not None:
                # Only check fusions involving observed concepts (not ALL 269K)
                # H2 fix: build id_to_name ONCE before the loop (was O(N*M) inside)
                id_to_name = {v: k for k, v in self._db._concept_cache.items()}
                for concept in clean_set:
                    cid = self._db._concept_cache.get(concept)
                    if cid is None:
                        continue
                    for row in self._db._conn.execute(
                        "SELECT a, b FROM fusions WHERE a=? OR b=?", (cid, cid)
                    ):
                        a_name = id_to_name.get(row[0], "")
                        b_name = id_to_name.get(row[1], "")
                        if a_name and b_name:
                            fusion_concepts.append(f"{a_name}_{b_name}")
            else:
                fusions = self.data.get("fusions", {})
                for key in fusions:
                    parts = key.split("|")
                    if len(parts) == 2 and (parts[0] in clean_set or parts[1] in clean_set):
                        fusion_concepts.append(f"{parts[0]}_{parts[1]}")
            fusion_concepts = list(dict.fromkeys(fusion_concepts))  # deduplicate, preserve order
            max_fusions = max(1, len(clean) // 3)
            fusion_concepts = fusion_concepts[:max_fusions]
            if fusion_concepts:
                self._p41_recursion_guard = True
                try:
                    self.observe(fusion_concepts)
                finally:
                    self._p41_recursion_guard = False

        # M10 fix: invalidate adjacency cache after adding edges
        self._adj_cache = None

        if self.federated:
            self._invalidate_zone_cache()

        # Prune only if limit is set, or if memory pressure
        n_conns = self._db.connection_count() if self._db else len(self.data.get("connections", {}))
        if self.MAX_CONNECTIONS > 0 and n_conns > self.MAX_CONNECTIONS:
            self._prune_weakest()
        elif n_conns > 10000:
            self._prune_if_memory_pressure()

    def observe_text(self, text: str, arousal: float = 0.0):
        """Extract concepts from raw text and observe co-occurrences.

        Works on any text — user messages, code, documentation.
        Chunks text by paragraphs so only nearby concepts co-occur,
        avoiding O(n²) explosion on large documents while keeping
        all concepts (no cap).
        V6A: arousal param passed to observe() for emotional tagging.
        """
        # Split into chunks (paragraphs / double-newline blocks)
        if not text:
            return
        chunks = re.split(r'\n\s*\n', text)

        # For small texts (<50 concepts total), treat as single chunk
        all_words = re.findall(r'[A-Za-zÀ-ÿ_]{3,}', text)
        all_counts = Counter(w.lower() for w in all_words)
        total_unique = sum(1 for w in all_counts if w not in _STOPWORDS)

        if total_unique <= 80:
            # Small text — single observation (original behavior)
            concepts = [w for w in all_counts if w not in _STOPWORDS]
            entities = re.findall(r'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*', text)
            for entity in entities:
                e = entity.lower()
                if e not in _STOPWORDS and len(e) >= 3:
                    concepts.append(e)
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self.observe(concepts, arousal=arousal)
            return

        # Large text — observe each chunk separately
        # Concepts that are in the same paragraph co-occur
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 20:
                continue
            words = re.findall(r'[A-Za-zÀ-ÿ_]{3,}', chunk)
            word_counts = Counter(w.lower() for w in words)
            concepts = [w for w in word_counts if w not in _STOPWORDS]
            entities = re.findall(r'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*', chunk)
            for entity in entities:
                e = entity.lower()
                if e not in _STOPWORDS and len(e) >= 3:
                    concepts.append(e)
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self.observe(concepts, arousal=arousal)

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

        # Pre-compile regex patterns for all concepts (avoid recompilation per chunk)
        concept_patterns = {c: re.compile(r'\b' + re.escape(c) + r'\b') for c in concept_set}
        for chunk in chunks:
            chunk_lower = chunk.lower()
            if len(chunk_lower) < 20:
                continue
            # Find which known concepts appear in this chunk (word boundaries)
            found = [c for c in concept_set
                     if concept_patterns[c].search(chunk_lower)]
            if len(found) >= 2:
                self.observe(found)

    def _check_fusions(self, observed_pairs: list[tuple[str, str]] = None):
        """Check if any connections crossed the fusion threshold.

        S3 (TIER 3): Blocks fusions for high-degree concepts (universal stopwords).
        Lazy mode: only checks the pairs from the current observe() call,
        not ALL edges. Full scan only runs on save() or explicit call.
        """
        # Cache high-degree concepts — computed ONCE per session (~3s on 2.7M edges)
        if self._high_degree_cache is None:
            self._high_degree_cache = self._get_high_degree_concepts()
        high_degree_concepts = self._high_degree_cache

        if self._db is not None:
            # Lazy mode: only check observed pairs, not all edges
            if observed_pairs:
                for a, b in observed_pairs:
                    if a in high_degree_concepts or b in high_degree_concepts:
                        continue
                    conn = self._db.get_connection(a, b)
                    if conn and conn["count"] >= self.FUSION_THRESHOLD:
                        a_key, b_key = min(a, b), max(a, b)
                        a_id = self._db._concept_cache.get(a_key)
                        b_id = self._db._concept_cache.get(b_key)
                        if a_id is not None and b_id is not None:
                            self._db._conn.execute("""
                                INSERT INTO fusions (a, b, form, strength, fused_at)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(a, b) DO UPDATE SET strength = ?
                            """, (a_id, b_id, f"{a_key}+{b_key}",
                                  conn["count"], today_days(), conn["count"]))
                self._db._conn.commit()
            else:
                # Full scan — only on explicit call (save, etc.)
                id_to_name = {v: k for k, v in self._db._concept_cache.items()}
                if high_degree_concepts:
                    hd_ids = {self._db._concept_cache.get(c) for c in high_degree_concepts}
                    hd_ids.discard(None)
                    if hd_ids:
                        for row in self._db._conn.execute("SELECT a, b FROM fusions").fetchall():
                            if row[0] in hd_ids or row[1] in hd_ids:
                                self._db._conn.execute(
                                    "DELETE FROM fusions WHERE a=? AND b=?", (row[0], row[1]))
                # Remove stale fusions (edge dropped below threshold or edge deleted)
                self._db._conn.execute("""
                    DELETE FROM fusions WHERE NOT EXISTS (
                        SELECT 1 FROM edges e WHERE e.a = fusions.a AND e.b = fusions.b
                        AND e.count >= ?
                    )
                """, (self.FUSION_THRESHOLD,))
                for row in self._db._conn.execute(
                        "SELECT a, b, count FROM edges WHERE count >= ?",
                        (self.FUSION_THRESHOLD,)):
                    a_id, b_id, count = row
                    a_name = id_to_name.get(a_id, "")
                    b_name = id_to_name.get(b_id, "")
                    if a_name in high_degree_concepts or b_name in high_degree_concepts:
                        continue
                    self._db._conn.execute("""
                        INSERT INTO fusions (a, b, form, strength, fused_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(a, b) DO UPDATE SET strength = ?
                    """, (a_id, b_id, f"{a_name}+{b_name}", count, today_days(), count))
                self._db._conn.commit()
        else:
            # Fallback: in-memory dict
            conns = self.data["connections"]
            fusions = self.data["fusions"]
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
                        if a in high_degree_concepts or b in high_degree_concepts:
                            continue
                        fusions[key] = {"concepts": [a, b], "form": f"{a}+{b}",
                                        "strength": conn["count"], "fused_at": time.strftime("%Y-%m-%d")}
                    else:
                        fusions[key]["strength"] = conn["count"]

    def _build_adj_cache(self) -> dict:
        """Build and cache adjacency list from all edges. Called once per session.
        Returns {concept: [(neighbor, raw_weight)]}. Also stores max_weight."""
        if self._adj_cache is not None:
            return self._adj_cache
        adj = {}
        max_w = 0.0
        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute("SELECT a, b, count FROM edges"):
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

    def _get_high_degree_concepts(self) -> set:
        """S3: Identify concepts with too many connections (universal stopwords).

        Lazy mode: 2 SQL queries (count distinct + filter by threshold).
        No full scan of 2.7M edges needed.
        """
        if self._db is not None:
            n = self._db.connection_count()
            if n < 50:
                return set()
            # SQL-native 2-step: find threshold, then filter
            n_concepts = self._db._conn.execute(
                "SELECT COUNT(*) FROM concepts").fetchone()[0]
            if n_concepts < 20:
                return set()
            cutoff = max(1, int(n_concepts * self.DEGREE_FILTER_PERCENTILE))

            # Step 1: threshold = degree at the cutoff position
            row = self._db._conn.execute("""
                SELECT degree FROM (
                    SELECT SUM(cnt) as degree FROM (
                        SELECT a as concept_id, COUNT(*) as cnt FROM edges GROUP BY a
                        UNION ALL
                        SELECT b as concept_id, COUNT(*) as cnt FROM edges GROUP BY b
                    ) GROUP BY concept_id
                    ORDER BY degree DESC
                ) LIMIT 1 OFFSET ?
            """, (cutoff,)).fetchone()
            threshold = max(row[0] if row else 20, 20)

            # Step 2: only fetch concepts above threshold (HAVING = fast)
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            result = set()
            for row in self._db._conn.execute("""
                SELECT concept_id, SUM(cnt) as degree FROM (
                    SELECT a as concept_id, COUNT(*) as cnt FROM edges GROUP BY a
                    UNION ALL
                    SELECT b as concept_id, COUNT(*) as cnt FROM edges GROUP BY b
                ) GROUP BY concept_id
                HAVING degree >= ?
            """, (threshold,)):
                name = self._db._id_to_name.get(row[0]) or self._db._concept_name(row[0])
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
            cutoff_idx = max(1, int(len(sorted_degrees) * self.DEGREE_FILTER_PERCENTILE))
            threshold = sorted_degrees[min(cutoff_idx, len(sorted_degrees) - 1)]
            threshold = max(threshold, 20)

            return {c for c, d in degree.items() if d >= threshold}

    def _prune_weakest(self):
        """Remove weakest connections to stay under MAX_CONNECTIONS."""
        if self._db is not None:
            n = self._db.connection_count()
            to_remove = n - self.MAX_CONNECTIONS
            if to_remove <= 0:
                return
            weakest = self._db.weakest_non_fused(to_remove)
            for key, _ in weakest:
                parts = key.split("|")
                if len(parts) == 2:
                    self._db.delete_connection(parts[0], parts[1])
            self._db.commit()
        else:
            conns = self.data["connections"]
            fusions = self.data["fusions"]
            prunable = sorted((k for k in conns if k not in fusions),
                              key=lambda k: conns[k]["count"])
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
                n_conns = self._db.connection_count() if self._db else len(self.data["connections"])
                target = n_conns // 2
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

        if self._db is not None:
            # SQL-native decay: process in batches via cursor
            td = today_days()
            cutoff = td - days
            dead_ids = []

            for row in self._db._conn.execute(
                    "SELECT a, b, count, last_seen FROM edges WHERE last_seen < ?",
                    (cutoff,)).fetchall():
                a_id, b_id, count, last_seen = row
                age_days = td - last_seen

                # P20.4: immortal connections (3+ zones) skip decay
                if self.federated:
                    nz = self._db._conn.execute(
                        "SELECT COUNT(*) FROM edge_zones WHERE a=? AND b=?",
                        (a_id, b_id)).fetchone()[0]
                    if nz >= self.IMMORTAL_ZONE_THRESHOLD:
                        continue

                periods = age_days // days
                new_count = count / (2 ** periods)

                if (self.SATURATION_BETA > 0 and new_count > self.SATURATION_THRESHOLD):
                    saturation_loss = int(self.SATURATION_BETA * new_count * new_count)
                    new_count = max(1, new_count - saturation_loss)

                if new_count < 0.01:
                    dead_ids.append((a_id, b_id))
                else:
                    self._db._conn.execute(
                        "UPDATE edges SET count=? WHERE a=? AND b=?",
                        (new_count, a_id, b_id))

            for a_id, b_id in dead_ids:
                self._db._conn.execute("DELETE FROM edges WHERE a=? AND b=?", (a_id, b_id))
                self._db._conn.execute("DELETE FROM fusions WHERE a=? AND b=?", (a_id, b_id))
                self._db._conn.execute("DELETE FROM edge_zones WHERE a=? AND b=?", (a_id, b_id))
            self._db._conn.commit()
            self._adj_cache = None  # M10 fix: invalidate after decay
            return len(dead_ids)
        else:
            # Fallback: in-memory dict
            today = time.strftime("%Y-%m-%d")
            conns = self.data["connections"]
            dead = []
            for key, conn in conns.items():
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
                    periods = age_days // days
                    new_count = conn["count"] / (2 ** periods)
                    if (self.SATURATION_BETA > 0 and new_count > self.SATURATION_THRESHOLD):
                        saturation_loss = int(self.SATURATION_BETA * new_count * new_count)
                        new_count = max(1, new_count - saturation_loss)
                    if new_count < 0.01:
                        dead.append(key)
                    else:
                        conn["count"] = new_count
            for key in dead:
                del conns[key]
                if key in self.data["fusions"]:
                    del self.data["fusions"][key]
            self._adj_cache = None  # M10 fix: invalidate after decay
            return len(dead)

    def effective_weight(self, key: str, count: float = None) -> float:
        """P20.3: TF-IDF inverse — rare across zones = important, ubiquitous = small.

        weight = count * log(1 + total_zones / zones_present)
        If not federated, returns raw count.
        """
        if self._db is not None:
            parts = key.split("|")
            if len(parts) != 2:
                return 0
            conn = self._db.get_connection(parts[0], parts[1])
            if not conn:
                return 0
            raw_count = count if count is not None else conn["count"]
            if not self.federated:
                return float(raw_count)
            import math
            total_zones = self._count_total_zones()
            zones_present = max(1, len(conn.get("zones", [])))
            return raw_count * math.log(1 + total_zones / zones_present)
        else:
            conn = self.data["connections"].get(key)
            if not conn:
                return 0
            raw_count = count if count is not None else conn["count"]
            if not self.federated or "zones" not in conn:
                return float(raw_count)
            import math
            total_zones = self._count_total_zones()
            zones_present = max(1, len(conn["zones"]))
            return raw_count * math.log(1 + total_zones / zones_present)

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

    def get_fusions(self) -> dict:
        """Get all fused concept blocks.

        Returns dict of {key: {concepts, form, strength}}.
        """
        if self._db is not None:
            return self._db.get_all_fusions()
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
        if self._db is not None:
            # Fetch more than needed to allow zone reordering, but cap to avoid full scan
            neighbors = self._db.neighbors(concept, top_n=max(50, top_n * 10))
            related = []
            for name, count in neighbors:
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
            return related[:top_n]
        else:
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
        # Use cached adjacency (built once, reused by transitive_inference too).
        # S3: Penalize hub concepts at query time (not in cache — seed-dependent).
        raw_adj = self._build_adj_cache()
        if not raw_adj:
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
        return results[:top_n]

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

        # Use cached adjacency (shared with spread_activation)
        adj = self._build_adj_cache()
        max_weight = self._adj_cache_max_weight

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

    def get_learned_fillers(self) -> list[str]:
        """Identify filler words from the mycelium.

        DISABLED: Returns empty list. The L2 hardcoded filler list in compress_line()
        already handles stop word removal. Mycelium-learned fillers caused critical
        data loss — high-frequency domain words (boot, tree, compression, commit)
        were incorrectly classified as fillers and stripped during compression.
        See: Audit V4, BUG 8 (14346 words including all domain keywords).
        """
        return []

    def get_learned_abbreviations(self) -> dict:
        """Generate abbreviation rules from strong fusions.

        Only creates abbreviations when one concept is a prefix/substring
        of the other (e.g., "compression" -> "comp", "encoding" -> "enc").
        Random co-occurrences like "compression|lines" are NOT abbreviations.

        Returns dict {long_form: short_form}.
        """
        abbrevs = {}
        if self._db is not None:
            # SQL-native: only fetch strong fusions with prefix relationship
            # Filter in SQL: form contains '+', strength >= 8
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute(
                "SELECT a, b FROM fusions WHERE strength >= 8"
            ):
                a = id_to_name.get(row[0])
                b = id_to_name.get(row[1])
                if not a or not b:
                    continue
                long_form, short = (a, b) if len(a) > len(b) else (b, a)
                if long_form.startswith(short) and len(short) >= 3:
                    abbrevs[long_form] = short
        else:
            fusions = self.get_fusions()
            for key, fusion in fusions.items():
                if fusion["strength"] >= 8:
                    a, b = fusion["concepts"]
                    long_form, short = (a, b) if len(a) > len(b) else (b, a)
                    if long_form.startswith(short) and len(short) >= 3:
                        abbrevs[long_form] = short
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
            print("detect_zones requires: pip install numpy scipy scikit-learn",
                  file=sys.stderr)
            return {}

        # 1. Build concept index and sparse matrix
        # Cap concepts to avoid eigsh hanging on massive matrices (>2000 concepts)
        MAX_ZONE_CONCEPTS = 2000
        concepts = set()
        rows, cols, vals = [], [], []

        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            # Pre-filter: if too many concepts, keep only top by degree
            top_concepts = None
            total_concepts = len(self._db._concept_cache)
            if total_concepts > MAX_ZONE_CONCEPTS:
                degree = self._db.all_degrees()
                sorted_deg = sorted(degree.items(), key=lambda x: -x[1])
                top_concepts = set(c for c, _ in sorted_deg[:MAX_ZONE_CONCEPTS])

            for row in self._db._conn.execute("SELECT a, b, count FROM edges"):
                a_name = id_to_name.get(row[0], "")
                b_name = id_to_name.get(row[1], "")
                if not a_name or not b_name:
                    continue
                if top_concepts and (a_name not in top_concepts or b_name not in top_concepts):
                    continue
                concepts.add(a_name)
                concepts.add(b_name)
            concepts = sorted(concepts)
            idx = {c: i for i, c in enumerate(concepts)}
            N = len(concepts)
            if N < 6:
                return {}
            for row in self._db._conn.execute("SELECT a, b, count FROM edges"):
                a_name = id_to_name.get(row[0], "")
                b_name = id_to_name.get(row[1], "")
                if not a_name or not b_name:
                    continue
                if top_concepts and (a_name not in top_concepts or b_name not in top_concepts):
                    continue
                i, j = idx.get(a_name), idx.get(b_name)
                if i is None or j is None:
                    continue
                w = row[2]
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
        tagged = 0
        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute("SELECT a, b FROM edges"):
                a_name = id_to_name.get(row[0], "")
                b_name = id_to_name.get(row[1], "")
                if not a_name or not b_name:
                    continue
                zone_a = concept_to_zone.get(a_name)
                zone_b = concept_to_zone.get(b_name)
                if zone_a:
                    self._db.add_zone_to_edge(a_name, b_name, zone_a)
                    tagged += 1
                if zone_b and zone_b != zone_a:
                    self._db.add_zone_to_edge(a_name, b_name, zone_b)
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
            zone_counts = {}
            for row in self._db._conn.execute("SELECT zone, COUNT(*) FROM edge_zones GROUP BY zone"):
                zone_counts[row[0]] = row[1]
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
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            rows = self._db._conn.execute("""
                SELECT a, b, COUNT(zone) as nz FROM edge_zones
                GROUP BY a, b HAVING nz >= 2
            """).fetchall()
            for a_id, b_id, nz in rows:
                a_name = id_to_name.get(a_id, "")
                b_name = id_to_name.get(b_id, "")
                if not a_name or not b_name:
                    continue
                zones = [r[0] for r in self._db._conn.execute(
                    "SELECT zone FROM edge_zones WHERE a=? AND b=?", (a_id, b_id))]
                count_row = self._db._conn.execute(
                    "SELECT count FROM edges WHERE a=? AND b=?", (a_id, b_id)).fetchone()
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
                    row = self._db._conn.execute("""
                        SELECT AVG(e.count) FROM edges e
                        JOIN edge_zones ez ON e.a=ez.a AND e.b=ez.b
                        WHERE ez.zone=?
                    """, (zone_name,)).fetchone()
                    if row and row[0] is not None and row[0] < 2:
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

        # Build connection set and adjacency ONLY for top concepts
        conn_set = set()
        adj = {}
        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute("SELECT a, b FROM edges"):
                a = id_to_name.get(row[0], "")
                b = id_to_name.get(row[1], "")
                if not a or not b:
                    continue
                if a in top_concepts_set or b in top_concepts_set:
                    conn_set.add((a, b))
                    conn_set.add((b, a))
                if a in top_concepts_set and b in top_concepts_set:
                    adj.setdefault(a, set()).add(b)
                    adj.setdefault(b, set()).add(a)
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

        # Build conn_set for fast lookup
        conn_set = set()
        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute("SELECT a, b FROM edges"):
                a_name = id_to_name.get(row[0], "")
                b_name = id_to_name.get(row[1], "")
                if a_name and b_name:
                    conn_set.add((a_name, b_name))
                    conn_set.add((b_name, a_name))
        else:
            for key in conns:
                parts = key.split("|")
                if len(parts) == 2:
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

    def _bfs_zones(self, degree: dict) -> dict[str, list[str]]:
        """Fallback zone detection via connected components (no scipy needed)."""
        adj = {}
        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            for row in self._db._conn.execute("SELECT a, b FROM edges"):
                a = id_to_name.get(row[0], "")
                b = id_to_name.get(row[1], "")
                if not a or not b:
                    continue
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
        else:
            conns = self.data["connections"]
            for key in conns:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)

        visited = set()
        zones = {}
        zone_id = 0
        for start in adj:
            if start in visited:
                continue
            # BFS
            queue = [start]
            component = []
            while queue:
                node = queue.pop(0)
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
                zone_id += 1

        return zones

    # ── H2: Synthèse / rêve — generate insights during sleep ─────
    #
    # During sleep consolidation, analyze patterns in the graph and
    # generate insights: temporal correlations, absences, anomalies.
    # Writes to .muninn/insights.json for boot surfacing.

    def dream(self) -> list[dict]:
        """H2: Generate insights by analyzing the mycelium graph.

        Detects:
        1. Temporal patterns: concepts that always appear together across sessions
        2. Absences: high-degree concepts that SHOULD connect but don't
        3. Dream bridges: dream connections (H1) that got reinforced = validated
        4. Clusters imbalance: one zone dominates, others starve

        Returns list of insight dicts, also saves to .muninn/insights.json.
        Source: Wilson & McNaughton 1994 (sleep consolidation generates insights).
        """
        import math

        if self._db is not None:
            n_conns = self._db.connection_count()
        else:
            n_conns = len(self.data["connections"])
        if n_conns < 10:
            return []

        insights = []

        # Build degree + adjacency
        degree = {}
        adj = {}
        avg_count_sum = 0.0
        avg_count_n = 0

        if self._db is not None:
            id_to_name = {v: k for k, v in self._db._concept_cache.items()}
            strong_pairs = []
            for row in self._db._conn.execute("SELECT a, b, count FROM edges"):
                a = id_to_name.get(row[0], "")
                b = id_to_name.get(row[1], "")
                if not a or not b:
                    continue
                cnt = row[2]
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
                avg_count_sum += cnt
                avg_count_n += 1
                if cnt >= 10:
                    strong_pairs.append((a, b, cnt))
        else:
            conns = self.data["connections"]
            strong_pairs = []
            for key, conn in conns.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                cnt = conn.get("count", 1)
                degree[a] = degree.get(a, 0) + 1
                degree[b] = degree.get(b, 0) + 1
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
                avg_count_sum += cnt
                avg_count_n += 1
                if cnt >= 10:
                    strong_pairs.append((a, b, cnt))

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
        sorted_concepts = sorted(degree.items(), key=lambda x: -x[1])
        top_concepts = [c for c, d in sorted_concepts[:min(30, len(sorted_concepts))]]
        for i, a in enumerate(top_concepts):
            for b in top_concepts[i+1:]:
                if b not in adj.get(a, set()):
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
        insights_path.write_text(json.dumps(combined, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

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
            zone = self.zone

            with db._conn:
                if self._db is not None:
                    # Lazy mode: stream from local SQLite
                    local_id_to_name = {v: k for k, v in self._db._concept_cache.items()}
                    n_synced = 0
                    for row in self._db._conn.execute(
                        "SELECT a, b, count, first_seen, last_seen FROM edges"
                    ):
                        a_name = local_id_to_name.get(row[0], "")
                        b_name = local_id_to_name.get(row[1], "")
                        if not a_name or not b_name:
                            continue
                        a_id = db._get_or_create_concept(a_name)
                        b_id = db._get_or_create_concept(b_name)
                        db._conn.execute("""
                            INSERT INTO edges (a, b, count, first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                count = excluded.count,
                                first_seen = MIN(first_seen, excluded.first_seen),
                                last_seen = MAX(last_seen, excluded.last_seen)
                        """, (a_id, b_id, row[2], row[3], row[4]))
                        db._conn.execute(
                            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                            (a_id, b_id, zone)
                        )
                        n_synced += 1

                    # Merge fusions from local DB
                    for row in self._db._conn.execute(
                        "SELECT a, b, form, strength, fused_at FROM fusions"
                    ):
                        a_name = local_id_to_name.get(row[0], "")
                        b_name = local_id_to_name.get(row[1], "")
                        if not a_name or not b_name:
                            continue
                        a_id = db._get_or_create_concept(a_name)
                        b_id = db._get_or_create_concept(b_name)
                        db._conn.execute("""
                            INSERT INTO fusions (a, b, form, strength, fused_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                strength = MAX(strength, excluded.strength)
                        """, (a_id, b_id, row[2], row[3], row[4]))
                else:
                    # Dict mode: iterate self.data
                    local_conns = self.data["connections"]
                    n_synced = len(local_conns)
                    for key, conn in local_conns.items():
                        parts = key.split("|")
                        if len(parts) != 2:
                            continue
                        a, b = parts
                        a_id = db._get_or_create_concept(a)
                        b_id = db._get_or_create_concept(b)
                        fs = date_to_days(conn.get("first_seen", "2026-01-01"))
                        ls = date_to_days(conn.get("last_seen", "2026-01-01"))
                        db._conn.execute("""
                            INSERT INTO edges (a, b, count, first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                count = excluded.count,
                                first_seen = MIN(first_seen, excluded.first_seen),
                                last_seen = MAX(last_seen, excluded.last_seen)
                        """, (a_id, b_id, conn["count"], fs, ls))
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

        return n_synced

    def pull_from_meta(self, query_concepts: list[str] = None, max_pull: int = 1000):
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
        db = MyceliumDB(self.meta_db_path())
        try:
            pulled = 0
            query_ids = set()  # M9 fix: initialize before if/else to avoid NameError
            id_to_name = {v: k for k, v in db._concept_cache.items()}

            if query_concepts:
                query_set = {c.lower().strip() for c in query_concepts}
                query_ids = set()
                for c in query_set:
                    cid = db._concept_cache.get(c)
                    if cid is not None:
                        query_ids.add(cid)
                if not query_ids:
                    return 0
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

            for row in rows:
                a_name = db._id_to_name.get(row[0]) or db._concept_name(row[0])
                b_name = db._id_to_name.get(row[1]) or db._concept_name(row[1])

                if self._db is not None:
                    # Lazy mode: upsert directly into local DB
                    if not self._db.has_connection(a_name, b_name):
                        self._db.upsert_connection(
                            a_name, b_name,
                            count=row[2],
                            first_seen=days_to_date(row[3]),
                            last_seen=days_to_date(row[4]),
                        )
                        # Pull zones
                        for zr in db._conn.execute(
                            "SELECT zone FROM edge_zones WHERE a=? AND b=?",
                            (row[0], row[1])
                        ):
                            self._db.add_zone_to_edge(a_name, b_name, zr[0])
                        pulled += 1
                else:
                    # Dict mode
                    key = f"{a_name}|{b_name}"
                    local_conns = self.data["connections"]
                    if key not in local_conns:
                        conn = {
                            "count": row[2],
                            "first_seen": days_to_date(row[3]),
                            "last_seen": days_to_date(row[4]),
                        }
                        zones = [r[0] for r in db._conn.execute(
                            "SELECT zone FROM edge_zones WHERE a=? AND b=?",
                            (row[0], row[1])
                        )]
                        if zones:
                            conn["zones"] = zones
                        local_conns[key] = conn
                        pulled += 1

            # Pull fusions — query-related if query, otherwise top by strength
            if self._db is not None:
                if query_ids:
                    placeholders_f = ",".join("?" * len(query_ids))
                    fquery = f"""
                        SELECT a, b, form, strength, fused_at FROM fusions
                        WHERE a IN ({placeholders_f}) OR b IN ({placeholders_f})
                    """
                    fparams = list(query_ids) + list(query_ids)
                else:
                    fquery = "SELECT a, b, form, strength, fused_at FROM fusions ORDER BY strength DESC LIMIT ?"
                    fparams = [max_pull]
                for frow in db._conn.execute(fquery, fparams):
                    a_name = db._id_to_name.get(frow[0]) or db._concept_name(frow[0])
                    b_name = db._id_to_name.get(frow[1]) or db._concept_name(frow[1])
                    if not self._db.has_fusion(a_name, b_name):
                        self._db.upsert_fusion(
                            a_name, b_name,
                            form=frow[2], strength=frow[3],
                            fused_at=frow[4],
                        )
            else:
                local_conns = self.data["connections"]
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
                    frow = db._conn.execute(
                        "SELECT form, strength, fused_at FROM fusions WHERE a=? AND b=?",
                        (a_id, b_id)
                    ).fetchone()
                    if frow:
                        local_fusions[key] = {
                            "concepts": list(parts),
                            "form": frow[0],
                            "strength": frow[1],
                            "fused_at": days_to_date(frow[2]),
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

        if self._db is not None:
            # Lazy mode: write directly to local DB
            for key, conn in candidates:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                if not self._db.has_connection(a, b):
                    self._db.upsert_connection(
                        a, b,
                        count=conn.get("count", 1),
                        first_seen=conn.get("first_seen", "2026-01-01"),
                        last_seen=conn.get("last_seen", "2026-01-01"),
                    )
                    pulled += 1

            meta_fusions = meta.get("fusions", {})
            for key, fusion in meta_fusions.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = parts
                if not self._db.has_fusion(a, b):
                    self._db.upsert_fusion(
                        a, b,
                        form=fusion.get("form", f"{a}+{b}"),
                        strength=fusion.get("strength", 1),
                        fused_at=fusion.get("fused_at", "2026-01-01"),
                    )
        else:
            # Dict mode
            import copy
            local_conns = self.data["connections"]
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
        sessions = self.data.get("session_count", 0)

        if self._db is not None:
            n_conns = self._db.connection_count()
            n_fusions = self._db.fusion_count()
            mode_str = "LAZY SQLite"
        else:
            n_conns = len(self.data["connections"])
            n_fusions = len(self.data["fusions"])
            mode_str = "dict"

        lines = [
            f"=== MUNINN MYCELIUM: {self.data['repo']} ===",
            f"  Mode: {'FEDERATED' if self.federated else 'local'} ({mode_str})",
            f"  Zone: {self.zone}",
            f"  Sessions: {sessions}",
            f"  Connections: {n_conns}",
            f"  Fusions: {n_fusions}",
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

        # Top 10 strongest connections
        if self._db is not None:
            top = self._db.top_connections(10)
            if top:
                lines.append(f"\n  Top connections:")
                for key, conn in top:
                    is_fused = self._db.has_fusion(
                        key.split("|")[0], key.split("|")[1]
                    ) if "|" in key else False
                    fused = " [FUSED]" if is_fused else ""
                    if self.federated:
                        w = self.effective_weight(key)
                        lines.append(f"    {key}: {conn['count']}x (eff={w:.1f}){fused}")
                    else:
                        lines.append(f"    {key}: {conn['count']}x{fused}")

            top_f = self._db.top_fusions(10)
            if top_f:
                lines.append(f"\n  Fusions ({n_fusions}):")
                for key, fusion in top_f:
                    lines.append(f"    {fusion['concepts']} -> {fusion['form']} "
                               f"(strength={fusion['strength']})")
        else:
            conns = self.data["connections"]
            fusions = self.data["fusions"]
            if conns:
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
            if m._db is not None:
                conns = m._db.connection_count()
                fusions = m._db.fusion_count()
            else:
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
            n_conns = m._db.connection_count() if m._db is not None else len(m.data['connections'])
            print(f"Current mycelium: {n_conns} connections (local mode)")
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
        n_conns = m._db.connection_count() if m._db is not None else len(m.data['connections'])
        print(f"Detecting zones in {m.data['repo']} ({n_conns} connections)...")
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
            _db = MyceliumDB(meta_db_p)
            repos_str = _db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            total = _db.connection_count()
            _db.close()
            print(f"Meta: {total} connections from {len(repos)} repos ({', '.join(repos)})")


if __name__ == "__main__":
    main()
