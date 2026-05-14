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
import os
import re
import sqlite3
import sys
import threading
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

try:
    from ._secrets import redact_secrets_text as _redact_secrets_text
except ImportError:
    from _secrets import redact_secrets_text as _redact_secrets_text  # type: ignore[no-redef]

# H6 chunks 1-4 (2026-05-09): meta + zones + activation + dream extracted
# to their own mixin modules. Same self attributes, same public API on
# Mycelium. Mixed in via class Mycelium(_Mixin1, _Mixin2, ...).
try:
    from .mycelium_meta import _MyceliumMetaMixin
    from .mycelium_zones import _MyceliumZonesMixin
    from .mycelium_activation import _MyceliumActivationMixin
    from .mycelium_dream import _MyceliumDreamMixin
except ImportError:
    from mycelium_meta import _MyceliumMetaMixin  # type: ignore[no-redef]
    from mycelium_zones import _MyceliumZonesMixin  # type: ignore[no-redef]
    from mycelium_activation import _MyceliumActivationMixin  # type: ignore[no-redef]
    from mycelium_dream import _MyceliumDreamMixin  # type: ignore[no-redef]

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


class Mycelium(_MyceliumMetaMixin, _MyceliumZonesMixin,
               _MyceliumActivationMixin, _MyceliumDreamMixin):
    """A living co-occurrence network that grows with each session."""

    FUSION_THRESHOLD = 5      # co-occur N times -> fuse into one block (base; A1 adapts)
    DECAY_HALF_LIFE = 30      # days before connection strength halves (base; A2 adapts)
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
        self._session_seen = set()  # Delta observe: skip already-upserted pairs
        self._session_lock = threading.Lock()  # Protects _session_seen across threads
        self._congestion_checked = False  # Congestion detection flag
        # Phase 3 (2026-05-14): auto-calibration of failure weight
        import os as _os
        self._auto_cal_enabled = _os.environ.get(
            "MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE", "0") == "1"
        self._failure_calibrated_weight = None
        self._failure_obs_count = 0
        # Load persisted calibration if present
        self._calib_path = self.mycelium_dir / "failure_weight_calibration.json"
        if self._auto_cal_enabled and self._calib_path.exists():
            try:
                import json as _json
                state = _json.loads(self._calib_path.read_text(encoding="utf-8"))
                self._failure_calibrated_weight = float(state.get("weight"))
            except (OSError, ValueError, KeyError, TypeError):
                pass  # Calibration file corrupt → ignore, recompute on next batch
        self.data = self._load()

    def _load(self) -> dict:
        """Load mycelium from disk or create fresh.

        S1 (TIER 3): Auto-detects and migrates JSON -> SQLite.
        Priority: .db (SQLite) > .json (legacy, auto-migrates) > fresh.
        """
        self.mycelium_dir.mkdir(parents=True, exist_ok=True)

        # Case 1: SQLite exists — load from it (check migration completeness)
        if self.db_path.exists():
            # P0: opportunistic re-chmod to 0600 (fixes legacy DBs created
            # with default umask before this defense was in place).
            try:
                from _secrets import secure_perms
                secure_perms(self.db_path)
            except ImportError:
                pass
            # Verify DB is not a partial migration
            try:
                import sqlite3
                conn = sqlite3.connect(str(self.db_path), timeout=5)
                try:
                    marker = conn.execute(
                        "SELECT value FROM meta WHERE key='migration_complete'"
                    ).fetchone()
                finally:
                    conn.close()
                if marker or not self.mycelium_path.exists():
                    # DB is complete OR no JSON to fall back to
                    return self._load_from_sqlite()
                else:
                    # Partial migration: rename corrupt DB and retry (H7 fix: don't delete)
                    try:
                        corrupt_path = self.db_path.with_suffix(".db.corrupt")
                        self.db_path.rename(corrupt_path)
                    except (PermissionError, OSError):
                        pass  # Windows: file locked, skip cleanup
            except (sqlite3.Error, OSError) as e:
                print(f"WARNING: mycelium DB check failed: {e}", file=sys.stderr)
                if not self.mycelium_path.exists():
                    return self._load_from_sqlite()
                try:
                    corrupt_path = self.db_path.with_suffix(".db.corrupt")
                    self.db_path.rename(corrupt_path)
                except (PermissionError, OSError):
                    pass  # Windows: file locked, skip cleanup

        # Case 2: JSON exists — migrate to SQLite, then load
        if self.mycelium_path.exists():
            try:
                self._migrate_json_to_sqlite()
                return self._load_from_sqlite()
            except (sqlite3.Error, OSError, json.JSONDecodeError, ValueError) as e:
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
        try:
            self._db = MyceliumDB(self.db_path)
        except (sqlite3.Error, OSError) as e:
            print(f"WARNING: corrupted mycelium DB, recreating: {e}", file=sys.stderr)
            try:
                self.db_path.unlink(missing_ok=True)
            except PermissionError:
                pass
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

        # P20.5+6: Auto-label zones on save when federated and enough data
        if self.federated and self._db is not None:
            n_conns = self._db.connection_count()
            if n_conns >= 50:
                try:
                    self.auto_label_zones()
                except Exception:
                    pass  # numpy/scipy not installed or clustering failed

        # S4: Flush pending translations before save
        try:
            if ConceptTranslator:
                translator = ConceptTranslator.get()
                translator.flush_pending()
        except (AttributeError, sqlite3.Error):
            pass  # ConceptTranslator not available or flush failed

        if self._db is not None:
            # Lazy mode: data is already in SQLite, just update meta + commit
            with self._db.transaction() as conn:
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("version", str(self.data.get("version", 1))))
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("repo", str(self.data.get("repo", self.repo_path.name))))
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("created", str(self.data.get("created", time.strftime("%Y-%m-%d")))))
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("updated", str(self.data.get("updated", time.strftime("%Y-%m-%d")))))
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("session_count", str(self.data.get("session_count", 0))))
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             ("migration_complete", "1"))
            # WAL auto-checkpoint
            self._db.checkpoint_wal()
        else:
            # Fallback: no DB yet (fresh install), create and write everything
            db = MyceliumDB(self.db_path)
            try:
                conns = self.data.get("connections", {})
                fusions = self.data.get("fusions", {})
                with db.transaction() as conn:
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("version", str(self.data.get("version", 1))))
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("repo", str(self.data.get("repo", self.repo_path.name))))
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("created", str(self.data.get("created", time.strftime("%Y-%m-%d")))))
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("updated", str(self.data.get("updated", time.strftime("%Y-%m-%d")))))
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("session_count", str(self.data.get("session_count", 0))))
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 ("migration_complete", "1"))
                    td = today_days()
                    for key, edge_data in conns.items():
                        parts = key.split("|")
                        if len(parts) != 2:
                            continue
                        a, b = parts
                        a_id = db._get_or_create_concept(a)
                        b_id = db._get_or_create_concept(b)
                        fs = date_to_days(edge_data.get("first_seen", "2026-01-01"))
                        ls = date_to_days(edge_data.get("last_seen", "2026-01-01"))
                        conn.execute(
                            "INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) "
                            "VALUES (?, ?, ?, ?, ?)",
                            (a_id, b_id, edge_data.get("count", 1), fs, ls))
                        for zone in edge_data.get("zones", []):
                            conn.execute(
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
                        conn.execute(
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
            except (sqlite3.Error, AttributeError):
                pass
            self._db = None

    def _key(self, a: str, b: str) -> str:
        """Canonical key for a pair (alphabetical order)."""
        return f"{min(a,b)}|{max(a,b)}"

    def _k2_fuse_cross_lingual(self, concepts: list[str]) -> list[str]:
        """K.2 (2026-05-14): map foreign-language concepts to existing
        canonical concepts via sentence-embedding cosine similarity.

        Triggered from observe() after the K.1 dict lookup. Bypassed
        entirely when MUNINN_EMBEDDINGS != "1" or when sentence-transformers
        is not importable — in both cases this returns the input list
        unchanged.

        Algorithm:
          1. Split concepts into 'already known' (existing concept_id)
             and 'new' (would be created).
          2. Embed the 'new' batch in one model call (cheaper than N).
          3. For each new concept, find the best cosine match in the
             existing embedding matrix.
          4. If cosine >= threshold, rewrite the concept to the canonical
             name (= fusion). Otherwise persist the new embedding so
             future lookups can fuse against it.
        """
        try:
            from .embeddings import EmbeddingProvider
        except ImportError:
            try:
                from embeddings import EmbeddingProvider  # type: ignore[no-redef]
            except ImportError:
                return concepts
        provider = EmbeddingProvider.get()
        if not provider.is_available():
            return concepts
        try:
            self._db._ensure_embedding_matrix(provider)
        except (sqlite3.Error, AttributeError, OSError):
            return concepts

        new_concepts = [c for c in concepts if c not in self._db._concept_cache]
        if not new_concepts:
            return concepts

        try:
            new_vecs = provider.embed_batch(new_concepts)
        except Exception:  # noqa: BLE001 — model errors must not break observe()
            return concepts
        if new_vecs is None:
            return concepts

        mapping: dict[str, str] = {}
        matrix = self._db._embedding_matrix
        names = self._db._embedding_names
        threshold = provider.threshold
        model_name = provider.model_name

        for concept, vec in zip(new_concepts, new_vecs):
            best_name, score = provider.find_best_match(vec, matrix, names)
            if best_name is not None and score >= threshold:
                mapping[concept] = best_name
                continue
            # No fusion — create the concept now and seed its embedding so
            # the NEXT concept in this loop (or session) can fuse against it.
            try:
                cid = self._db._get_or_create_concept(concept)
                self._db._persist_embedding(cid, model_name, vec)
                matrix = self._db._embedding_matrix
                names = self._db._embedding_names
            except (sqlite3.Error, ValueError):
                continue

        if not mapping:
            return concepts
        rewritten = [mapping.get(c, c) for c in concepts]
        return list(set(rewritten))

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
            if c is None:
                continue
            import unicodedata
            c = unicodedata.normalize("NFC", str(c).lower().strip())
            if len(c) >= self.MIN_CONCEPT_LEN and c not in _STOPWORDS:
                clean.append(c)

        # S4: Normalize non-English concepts to English
        try:
            if ConceptTranslator:
                translator = ConceptTranslator.get()
                clean = translator.normalize_concepts(clean)
        except (AttributeError, TypeError):
            pass  # Graceful: no tiktoken/anthropic = no translation

        clean = list(set(clean))  # deduplicate

        # K.2 (2026-05-14): cross-lingual fusion via sentence embeddings.
        # Off by default — only fires if MUNINN_EMBEDDINGS=1 AND a model
        # actually loaded. Catches multilingual variants the K.1 dict
        # misses (Baum/árbol/木 → tree, jargon equivalents, etc.).
        if self._db is not None and clean:
            clean = self._k2_fuse_cross_lingual(clean)

        # V6A: Emotional tagging — Hill function boost (Richter-Levin 2003)
        _kappa = 1.0
        _hill_n = 3
        _hill_theta = 0.5
        a = max(0.0, float(arousal))
        if a > 0.0:
            e_a = 1.0 + _kappa * (a ** _hill_n) / (a ** _hill_n + _hill_theta ** _hill_n)
        else:
            e_a = 1.0

        # Record pairs — DELTA MODE: skip pairs already upserted this session.
        # On a 14.9M edge DB, skipping known pairs avoids ~90% of slow upserts.
        # _session_seen tracks (a_id, b_id) pairs already written this session.
        if self._db is not None:
            pairs = []
            for i in range(len(clean)):
                for j in range(i + 1, len(clean)):
                    a_key = min(clean[i], clean[j])
                    b_key = max(clean[i], clean[j])
                    pairs.append((a_key, b_key))
            if pairs:
                td = today_days()
                _batch_size = 5000
                _congestion_checked = self._congestion_checked
                for batch_start in range(0, len(pairs), _batch_size):
                    batch = pairs[batch_start:batch_start + _batch_size]
                    _t0 = time.time() if not _congestion_checked else 0
                    with self._db.transaction() as conn:
                        for a_key, b_key in batch:
                            a_id = self._db._get_or_create_concept(a_key)
                            b_id = self._db._get_or_create_concept(b_key)
                            pair_key = (a_id, b_id)
                            with self._session_lock:
                                if pair_key in self._session_seen:
                                    continue  # Delta: already upserted this session
                                self._session_seen.add(pair_key)
                            conn.execute("""
                                INSERT INTO edges (a, b, count, first_seen, last_seen)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(a, b) DO UPDATE SET
                                    count = count + ?,
                                    last_seen = ?
                            """, (a_id, b_id, e_a, td, td, e_a, td))
                            if self.federated:
                                conn.execute(
                                    "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                                    (a_id, b_id, self.zone))
                    # CONGESTION DETECTION: if first batch takes > 2s, the DB is
                    # too large. Run emergency decay to unclog before continuing.
                    if not _congestion_checked:
                        _batch_elapsed = time.time() - _t0
                        self._congestion_checked = True
                        _congestion_checked = True
                        if _batch_elapsed > 2.0:
                            print(f"  CONGESTION: batch took {_batch_elapsed:.1f}s, "
                                  f"running emergency decay", file=sys.stderr)
                            try:
                                dead = self.decay()
                                if dead > 0:
                                    self.save()
                                    print(f"  EMERGENCY DECAY: {dead} dead edges removed",
                                          file=sys.stderr)
                            except (sqlite3.Error, OSError, ValueError) as e:
                                print(f"  EMERGENCY DECAY failed: {e}", file=sys.stderr)
                # WAL guard: checkpoint if WAL > 50MB (prevents 300MB+ WAL buildup)
                if not getattr(self, '_wal_check_count', 0) % 50:
                    try:
                        wal_path = str(self.db_path) + "-wal"
                        if os.path.exists(wal_path) and os.path.getsize(wal_path) > 50_000_000:
                            self._db.checkpoint_wal()
                    except (sqlite3.OperationalError, OSError):
                        pass
                self._wal_check_count = getattr(self, '_wal_check_count', 0) + 1
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
                id_to_name = self._db._id_to_name
                for concept in clean_set:
                    cid = self._db._concept_cache.get(concept)
                    if cid is None:
                        continue
                    with self._db._lock:
                        fusion_rows = self._db._conn.execute(
                            "SELECT a, b FROM fusions WHERE a=? OR b=?", (cid, cid)
                        ).fetchall()
                    for row in fusion_rows:
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
        # Audit fix: invalidate degree cache — degree distribution changes after observe
        self._high_degree_cache = None

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
        # X1: Defense-in-depth — redact secrets before extracting concepts
        text = _redact_secrets_text(text)
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

    def observe_failure(self, text: str, weight: float = None):
        """Phase 3 (2026-05-14): record failure patterns — concepts that
        appeared in failed LLM reconstruction contexts.

        Unlike observe_text (positive learning that strengthens connections),
        failures are NEGATIVE signals: concepts co-occurring in failed
        contexts get penalized in future spread_activation lookups.

        Weight resolution order (caller override > calibration > env > default):
          1. weight param if explicitly passed
          2. self._failure_calibrated_weight if auto-calibration active
          3. env MUNINN_OBSERVE_FAILURE_WEIGHT
          4. -0.5 (BCM-style Hebbian, LTD < LTP convention)

        Mirrors observe_text() chunking + regex extraction. Writes go
        to the `failures` table instead of `edges` via _record_failure().
        """
        import os as _os
        if weight is None:
            # Auto-cal takes priority over env var if active
            if getattr(self, "_auto_cal_enabled", False) and \
               getattr(self, "_failure_calibrated_weight", None) is not None:
                weight = self._failure_calibrated_weight
            else:
                try:
                    weight = float(_os.environ.get(
                        "MUNINN_OBSERVE_FAILURE_WEIGHT", "-0.5"))
                except ValueError:
                    weight = -0.5
        # Clamp to safe range — refuse positive (would be a logic bug)
        weight = max(-10.0, min(0.0, float(weight)))

        text = _redact_secrets_text(text)
        if not text:
            return
        chunks = re.split(r'\n\s*\n', text)
        all_words = re.findall(r'[A-Za-zÀ-ÿ_]{3,}', text)
        all_counts = Counter(w.lower() for w in all_words)
        total_unique = sum(1 for w in all_counts if w not in _STOPWORDS)

        if total_unique <= 80:
            concepts = [w for w in all_counts if w not in _STOPWORDS]
            entities = re.findall(r'[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*', text)
            for entity in entities:
                e = entity.lower()
                if e not in _STOPWORDS and len(e) >= 3:
                    concepts.append(e)
            concepts = list(set(concepts))
            if len(concepts) >= 2:
                self._record_failure(concepts, weight)
            return

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
                self._record_failure(concepts, weight)

    def _record_failure(self, concepts: list, weight: float = -0.5):
        """Internal: record failure edges between all pairs of concepts.

        Mirrors observe() structure but writes to the failures table via
        MyceliumDB.upsert_failure(). Uses _session_seen with a separate
        keyspace ('fail' tag) so a positive and a negative observation
        of the same pair don't deduplicate each other.
        """
        if not concepts or self._db is None:
            return
        # Normalize: lowercase NFC, strip stopwords, dedupe
        import unicodedata as _ud
        clean = []
        for c in concepts:
            if c is None:
                continue
            c = _ud.normalize("NFC", str(c).lower().strip())
            if len(c) >= self.MIN_CONCEPT_LEN and c not in _STOPWORDS:
                clean.append(c)
        clean = list(set(clean))
        if len(clean) < 2:
            return
        # Build pairs (alphabetical order matches upsert_failure)
        for i in range(len(clean)):
            for j in range(i + 1, len(clean)):
                a_key = min(clean[i], clean[j])
                b_key = max(clean[i], clean[j])
                # Session-level dedup with 'fail' tag to keep separate
                # from positive observations of the same pair.
                with self._session_lock:
                    sess_key = (a_key, b_key, "fail")
                    if sess_key in self._session_seen:
                        continue
                    self._session_seen.add(sess_key)
                self._db.upsert_failure(a_key, b_key, weight=weight)
        # Auto-calibration tick (no-op if disabled)
        self._maybe_calibrate_failure_weight()

    def _maybe_calibrate_failure_weight(self):
        """Phase 3 (2026-05-14): if MUNINN_FAILURE_WEIGHT_AUTO_CALIBRATE=1,
        recompute the failure weight every 50 observations using a sigmoid
        on the global fail/success ratio.

        Sigmoid centered at fail_rate=0.5:
          - fail_rate=0.05  → weight ≈ -0.12 (rare fails, weak signal)
          - fail_rate=0.50  → weight = -0.50  (balanced)
          - fail_rate=0.95  → weight ≈ -0.88 (fails dominate, strong signal)

        Persists last weight to .muninn/failure_weight_calibration.json
        so the value survives session restarts.
        """
        if not self._auto_cal_enabled or self._db is None:
            return
        self._failure_obs_count += 1
        if self._failure_obs_count % 50 != 0:
            return
        try:
            n_fail = self._db._conn.execute(
                "SELECT COUNT(*) FROM failures").fetchone()[0]
            n_edge = self._db._conn.execute(
                "SELECT COUNT(*) FROM edges").fetchone()[0]
        except Exception:
            return
        total = n_fail + n_edge
        if total < 100:
            return  # not enough data to recompute
        fail_rate = n_fail / total
        import math as _math
        # Sigmoid centered at 0.5, scaled to [-1.0, 0.0]
        new_weight = -1.0 / (1.0 + _math.exp(-4.0 * (fail_rate - 0.5)))
        new_weight = max(-1.0, min(-0.05, new_weight))
        self._failure_calibrated_weight = new_weight
        # Persist
        try:
            import json as _json
            import time as _time
            self._calib_path.write_text(_json.dumps({
                "weight": new_weight,
                "fail_rate": fail_rate,
                "n_failures": n_fail,
                "n_edges": n_edge,
                "computed_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "obs_count": self._failure_obs_count,
            }, indent=2), encoding="utf-8")
        except OSError:
            pass  # disk error → keep in-memory state, retry next batch

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
                with self._db.transaction() as txn:
                    for a, b in observed_pairs:
                        if a in high_degree_concepts or b in high_degree_concepts:
                            continue
                        edge = self._db.get_connection(a, b)
                        if edge and edge["count"] >= self.FUSION_THRESHOLD:
                            a_key, b_key = min(a, b), max(a, b)
                            a_id = self._db._concept_cache.get(a_key)
                            b_id = self._db._concept_cache.get(b_key)
                            if a_id is not None and b_id is not None:
                                txn.execute("""
                                    INSERT INTO fusions (a, b, form, strength, fused_at)
                                    VALUES (?, ?, ?, ?, ?)
                                    ON CONFLICT(a, b) DO UPDATE SET strength = ?
                                """, (a_id, b_id, f"{a_key}+{b_key}",
                                      edge["count"], today_days(), edge["count"]))
            else:
                # Full scan — only on explicit call (save, etc.)
                with self._db.transaction() as txn:
                    id_to_name = self._db._id_to_name
                    if high_degree_concepts:
                        hd_ids = {self._db._concept_cache.get(c) for c in high_degree_concepts}
                        hd_ids.discard(None)
                        if hd_ids:
                            for row in txn.execute("SELECT a, b FROM fusions").fetchall():
                                if row[0] in hd_ids or row[1] in hd_ids:
                                    txn.execute(
                                        "DELETE FROM fusions WHERE a=? AND b=?", (row[0], row[1]))
                    # Remove stale fusions (edge dropped below threshold or edge deleted)
                    txn.execute("""
                        DELETE FROM fusions WHERE NOT EXISTS (
                            SELECT 1 FROM edges e WHERE e.a = fusions.a AND e.b = fusions.b
                            AND e.count >= ?
                        )
                    """, (self.FUSION_THRESHOLD,))
                    for row in txn.execute(
                            "SELECT a, b, count FROM edges WHERE count >= ?",
                            (self.FUSION_THRESHOLD,)):
                        a_id, b_id, count = row
                        a_name = id_to_name.get(a_id, "")
                        b_name = id_to_name.get(b_id, "")
                        if a_name in high_degree_concepts or b_name in high_degree_concepts:
                            continue
                        txn.execute("""
                            INSERT INTO fusions (a, b, form, strength, fused_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET strength = ?
                        """, (a_id, b_id, f"{a_name}+{b_name}", count, today_days(), count))
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
        except (OSError, MemoryError):
            pass  # Can't check RAM = don't prune

    def decay(self, days: int = None):
        """Weaken connections that haven't been seen recently.

        Connections that haven't been reinforced decay over time.
        Dead connections (count drops to 0) are removed.
        A4: Auto-vacuum if decay takes > 10s.
        """
        if days is None:
            days = self.DECAY_HALF_LIFE
        if days <= 0:
            return 0

        _decay_start = time.time()

        if self._db is not None:
            # SQL-native decay: process in batches via cursor
            td = today_days()
            cutoff = td - days
            dead_ids = []

            with self._db.transaction() as txn:
                for row in txn.execute(
                        "SELECT a, b, count, last_seen FROM edges WHERE last_seen < ?",
                        (cutoff,)).fetchall():
                    a_id, b_id, count, last_seen = row
                    age_days = td - last_seen

                    # P20.4: immortal connections (3+ zones) skip decay
                    if self.federated:
                        nz_row = txn.execute(
                            "SELECT COUNT(*) FROM edge_zones WHERE a=? AND b=?",
                            (a_id, b_id)).fetchone()
                        nz = nz_row[0] if nz_row else 0
                        if nz >= self.IMMORTAL_ZONE_THRESHOLD:
                            continue

                    periods = age_days // days
                    new_count = count / (2 ** periods)

                    # Guard against NaN/Inf from corrupted data
                    if not isinstance(new_count, (int, float)) or new_count != new_count or new_count == float('inf'):
                        dead_ids.append((a_id, b_id))
                        continue

                    if (self.SATURATION_BETA > 0 and new_count > self.SATURATION_THRESHOLD):
                        saturation_loss = self.SATURATION_BETA * new_count * new_count
                        new_count = max(1, new_count - saturation_loss)

                    if new_count < 0.01:
                        dead_ids.append((a_id, b_id))
                    else:
                        txn.execute(
                            "UPDATE edges SET count=? WHERE a=? AND b=?",
                            (new_count, a_id, b_id))

                # P6: Batch deletes with executemany() instead of loop
                if dead_ids:
                    td = today_days()
                    # H4: record tombstones before deletion
                    try:
                        txn.executemany(
                            "INSERT OR REPLACE INTO tombstones (a, b, deleted_at, deleted_by) "
                            "VALUES (?, ?, ?, ?)",
                            [(a_id, b_id, td, "decay") for a_id, b_id in dead_ids])
                    except sqlite3.OperationalError:
                        pass  # Old schema without tombstones table
                    txn.executemany(
                        "DELETE FROM edges WHERE a=? AND b=?", dead_ids)
                    txn.executemany(
                        "DELETE FROM fusions WHERE a=? AND b=?", dead_ids)
                    txn.executemany(
                        "DELETE FROM edge_zones WHERE a=? AND b=?", dead_ids)
            # Clean up orphaned fusions whose edges were just removed
            if dead_ids:
                try:
                    self._db.delete_stale_fusions(min_edge_count=1)
                except (sqlite3.OperationalError, AttributeError):
                    pass
            # BUG-M8: cleanup orphan concepts left behind by dead edges
            if dead_ids:
                self.cleanup_orphan_concepts()
            self._adj_cache = None  # M10 fix: invalidate after decay
            # A4: Auto-vacuum if decay took > 10s
            if time.time() - _decay_start > 10.0:
                self.vacuum_if_needed()
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
                        saturation_loss = self.SATURATION_BETA * new_count * new_count
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

    def adaptive_fusion_threshold(self) -> int:
        """A1: Adaptive fusion threshold — max(2, sqrt(n_concepts) * 0.4).

        Small mycelium (few concepts) = low threshold (fuse aggressively).
        Large mycelium = higher threshold (avoid noise fusions).
        """
        import math
        if self._db is not None:
            n = len(self._db._concept_cache)
        else:
            concepts = set()
            for key in self.data.get("connections", {}):
                parts = key.split("|")
                if len(parts) == 2:
                    concepts.update(parts)
            n = len(concepts)
        return max(2, int(math.sqrt(n) * 0.4))

    def adaptive_decay_half_life(self) -> int:
        """A2: Adaptive decay half-life — scales with sessions/day.

        Active repos (many sessions) = faster decay (more turnover).
        Inactive repos = slower decay (preserve knowledge).
        """
        session_count = self.data.get("session_count", 0)
        created = self.data.get("created", "")
        if not created or session_count <= 0:
            return self.DECAY_HALF_LIFE

        try:
            from datetime import datetime
            created_date = datetime.strptime(created, "%Y-%m-%d")
            days_active = max(1, (datetime.now() - created_date).days)
            sessions_per_day = session_count / days_active
            # More sessions = faster decay; fewer sessions = slower decay
            # Scale: 0.1 sessions/day -> 60 days, 1/day -> 30 days, 5/day -> 15 days
            adaptive = max(15, int(self.DECAY_HALF_LIFE / max(0.5, sessions_per_day)))
            return min(adaptive, 90)  # Cap at 90 days
        except (ValueError, ZeroDivisionError):
            return self.DECAY_HALF_LIFE

    def cleanup_orphan_concepts(self) -> int:
        """A3: Auto-cleanup concepts without edges when orphans > 20%.

        Returns number of orphaned concepts removed.
        """
        if self._db is None:
            return 0
        try:
            total = len(self._db._concept_cache)
            if total == 0:
                return 0
            # Count orphans (concepts not referenced in any edge)
            with self._db.transaction() as txn:
                orphan_count = txn.execute("""
                    SELECT COUNT(*) FROM concepts
                    WHERE id NOT IN (SELECT a FROM edges UNION SELECT b FROM edges)
                """).fetchone()[0]

                if orphan_count / total < 0.2:
                    return 0  # Below 20% threshold

                result = txn.execute("""
                    DELETE FROM concepts
                    WHERE id NOT IN (SELECT a FROM edges UNION SELECT b FROM edges)
                """)
                removed = result.rowcount
            if removed > 0:
                self._db._load_concept_cache()  # Refresh caches
            return removed
        except sqlite3.OperationalError as e:
            print(f"WARNING: cleanup_orphan_concepts failed: {e}", file=sys.stderr)
            return 0

    def cleanup_orphan_zones(self) -> int:
        """P2: Delete zone entries whose edges no longer exist.

        Returns number of orphaned zone entries removed.
        """
        if self._db is None:
            return 0
        try:
            with self._db.transaction() as txn:
                result = txn.execute("""
                    DELETE FROM edge_zones
                    WHERE NOT EXISTS (
                        SELECT 1 FROM edges WHERE edges.a = edge_zones.a AND edges.b = edge_zones.b
                    )
                """)
                removed = result.rowcount
            return removed
        except sqlite3.OperationalError as e:
            print(f"WARNING: cleanup_orphan_zones failed: {e}", file=sys.stderr)
            return 0

    def vacuum_if_needed(self, threshold_seconds: float = 10.0) -> bool:
        """P3: Run VACUUM + PRAGMA optimize if decay took longer than threshold.

        Returns True if VACUUM was executed.
        """
        if self._db is None:
            return False
        try:
            self._db.vacuum()
            return True
        except sqlite3.OperationalError as e:
            print(f"WARNING: vacuum failed: {e}", file=sys.stderr)
            return False

    def growth_stats(self) -> dict:
        """P3: Return growth statistics for monitoring.

        Returns dict with connection/concept counts and quota info.
        """
        if self._db is None:
            return {"connections": 0, "concepts": 0}
        n_edges = self._db.connection_count()
        n_concepts = len(self._db._concept_cache)
        return {
            "connections": n_edges,
            "concepts": n_concepts,
            "max_connections": self.MAX_CONNECTIONS,
            "at_limit": self.MAX_CONNECTIONS > 0 and n_edges >= self.MAX_CONNECTIONS,
        }

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

    def get_fusions(self) -> dict:
        """Get all fused concept blocks.

        Returns dict of {key: {concepts, form, strength}}.
        """
        if self._db is not None:
            return self._db.get_all_fusions()
        return self.data.get("fusions", {})

    def get_compression_rules(self, min_strength: float = 10,
                              max_rules: int = 5000) -> dict:
        """Generate compression rules from the mycelium.

        Returns a dict {pattern: replacement} for the compressor.
        Strongest fusions -> shortest codes.

        Filters: only fusions with strength >= min_strength, concepts
        of length >= MIN_CONCEPT_LEN, and not in high-degree stopword set.
        Capped at max_rules to avoid loading 445K+ fusions into the
        compression pipeline. Fixed after BUG-M6 (fusion pollution).
        """
        if self._high_degree_cache is None:
            self._high_degree_cache = self._get_high_degree_concepts()
        hub_set = self._high_degree_cache

        if self._db is not None:
            # SQL-native: fetch only strong fusions, sorted by strength
            id_to_name = self._db._id_to_name
            with self._db._lock:
                rows = self._db._conn.execute(
                    "SELECT a, b, strength FROM fusions "
                    "WHERE strength >= ? ORDER BY strength DESC LIMIT ?",
                    (min_strength, max_rules * 2),
                ).fetchall()
            rules = {}
            for a_id, b_id, strength in rows:
                a = id_to_name.get(a_id)
                b = id_to_name.get(b_id)
                if not a or not b:
                    continue
                if a in hub_set or b in hub_set:
                    continue
                if len(a) < self.MIN_CONCEPT_LEN or len(b) < self.MIN_CONCEPT_LEN:
                    continue
                key = self._key(a, b)
                rules[key] = {
                    "concepts": [a, b],
                    "form": f"{a}+{b}",
                    "strength": strength,
                }
                if len(rules) >= max_rules:
                    break
            return rules
        else:
            fusions = self.get_fusions()
            if not fusions:
                return {}
            ranked = sorted(fusions.items(),
                            key=lambda x: x[1]["strength"], reverse=True)
            rules = {}
            for key, fusion in ranked:
                if fusion["strength"] < min_strength:
                    break
                concepts = fusion["concepts"]
                if any(c in hub_set for c in concepts):
                    continue
                if any(len(c) < self.MIN_CONCEPT_LEN for c in concepts):
                    continue
                rules[key] = {
                    "concepts": concepts,
                    "form": fusion["form"],
                    "strength": fusion["strength"],
                }
                if len(rules) >= max_rules:
                    break
            return rules

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
            id_to_name = self._db._id_to_name
            with self._db._lock:
                fusion_rows = self._db._conn.execute(
                    "SELECT a, b FROM fusions WHERE strength >= 8"
                ).fetchall()
            for row in fusion_rows:
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
        self._session_seen = set()  # Reset delta tracking for new session

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
