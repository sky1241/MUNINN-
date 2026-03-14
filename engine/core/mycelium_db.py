#!/usr/bin/env python3
"""
Muninn Mycelium SQLite Backend — S1+S2 of TIER 3.

Replaces JSON storage with normalized SQLite for mycelium data.
- Concepts stored as integer IDs (4 bytes vs ~15 bytes text)
- Dates as epoch-days since 2020-01-01 (2 bytes vs 10 bytes text)
- WITHOUT ROWID tables for optimal storage
- WAL mode for crash safety and concurrent reads

Estimated savings: x5 disk, x100 RAM vs JSON.
Zero new dependencies (sqlite3 = Python stdlib).
"""
import json
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

# Reference date for epoch-days encoding (S2)
_EPOCH_REF = date(2020, 1, 1)


def date_to_days(d: str) -> int:
    """Convert 'YYYY-MM-DD' string to epoch-days integer."""
    try:
        parts = d.split("-")
        dt = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return (dt - _EPOCH_REF).days
    except (ValueError, IndexError, AttributeError):
        return (date.today() - _EPOCH_REF).days


def days_to_date(days) -> str:
    """Convert epoch-days integer back to 'YYYY-MM-DD' string.

    Handles TEXT values stored by legacy code (returns them as-is if valid date).
    """
    if isinstance(days, str):
        if len(days) == 10 and days[4] == '-':
            return days
        try:
            days = int(days)
        except (ValueError, TypeError):
            return "2026-01-01"
    dt = _EPOCH_REF + timedelta(days=int(days))
    return dt.strftime("%Y-%m-%d")


def today_days() -> int:
    """Get today as epoch-days."""
    return (date.today() - _EPOCH_REF).days


class MyceliumDB:
    """SQLite backend for mycelium storage.

    Provides the same data interface as the old JSON dict but backed by SQLite.
    All reads/writes go through the DB — no full load into RAM.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA mmap_size=100000000")
        self._conn.execute("PRAGMA cache_size=-8000")  # 8MB cache
        self._setup_tables()
        self._concept_cache = {}  # name -> id (in-memory for fast lookups)
        self._load_concept_cache()

    def _setup_tables(self):
        """Create tables if they don't exist."""
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS concepts (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                a INTEGER NOT NULL,
                b INTEGER NOT NULL,
                count REAL NOT NULL DEFAULT 0,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                PRIMARY KEY (a, b)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS fusions (
                a INTEGER NOT NULL,
                b INTEGER NOT NULL,
                form TEXT NOT NULL,
                strength REAL NOT NULL,
                fused_at INTEGER NOT NULL,
                PRIMARY KEY (a, b)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS edge_zones (
                a INTEGER NOT NULL,
                b INTEGER NOT NULL,
                zone TEXT NOT NULL,
                PRIMARY KEY (a, b, zone)
            ) WITHOUT ROWID;
            CREATE INDEX IF NOT EXISTS idx_edges_a ON edges(a);
            CREATE INDEX IF NOT EXISTS idx_edges_b ON edges(b);
            CREATE INDEX IF NOT EXISTS idx_edges_count ON edges(count);
            CREATE INDEX IF NOT EXISTS idx_edges_last_seen ON edges(last_seen);
            CREATE INDEX IF NOT EXISTS idx_fusions_a ON fusions(a);
            CREATE INDEX IF NOT EXISTS idx_fusions_b ON fusions(b);
            CREATE INDEX IF NOT EXISTS idx_fusions_strength ON fusions(strength);
            CREATE INDEX IF NOT EXISTS idx_edge_zones_zone ON edge_zones(zone);
        """)
        c.commit()

    def _load_concept_cache(self):
        """Load concept name->id and id->name mappings into memory (~100KB for 10K concepts)."""
        self._concept_cache = {}
        self._id_to_name = {}
        for row in self._conn.execute("SELECT id, name FROM concepts"):
            self._concept_cache[row[1]] = row[0]
            self._id_to_name[row[0]] = row[1]

    def _get_or_create_concept(self, name: str) -> int:
        """Get concept ID, creating it if needed."""
        if name in self._concept_cache:
            return self._concept_cache[name]
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO concepts (name) VALUES (?)", (name,)
            )
            row = self._conn.execute(
                "SELECT id FROM concepts WHERE name = ?", (name,)
            ).fetchone()
            if row:
                self._concept_cache[name] = row[0]
                self._id_to_name[row[0]] = name
                return row[0]
        except sqlite3.Error:
            pass
        # Fallback: fetch existing
        row = self._conn.execute(
            "SELECT id FROM concepts WHERE name = ?", (name,)
        ).fetchone()
        if row:
            self._concept_cache[name] = row[0]
            self._id_to_name[row[0]] = name
            return row[0]
        raise ValueError(f"Failed to get/create concept: {name}")

    def _concept_name(self, cid: int) -> str:
        """Get concept name from ID. O(1) via reverse cache."""
        # Use reverse cache (built alongside _concept_cache)
        name = self._id_to_name.get(cid)
        if name is not None:
            return name
        # Fallback: query DB (rare — only for IDs added after cache load)
        row = self._conn.execute(
            "SELECT name FROM concepts WHERE id = ?", (cid,)
        ).fetchone()
        if row:
            self._concept_cache[row[0]] = cid
            self._id_to_name[cid] = row[0]
            return row[0]
        return f"?{cid}"

    # ── Meta key-value store ─────────────────────────────────────────

    def get_meta(self, key: str, default: str = None) -> str:
        """Get a metadata value."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str):
        """Set a metadata value."""
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value)
        )
        self._conn.commit()

    # ── Connection operations ────────────────────────────────────────

    def get_connection(self, concept_a: str, concept_b: str) -> dict | None:
        """Get a single connection by concept names. Returns dict or None."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return None
        row = self._conn.execute(
            "SELECT count, first_seen, last_seen FROM edges WHERE a=? AND b=?",
            (a_id, b_id)
        ).fetchone()
        if not row:
            return None
        result = {
            "count": row[0],
            "first_seen": days_to_date(row[1]),
            "last_seen": days_to_date(row[2]),
        }
        # Load zones
        zones = [r[0] for r in self._conn.execute(
            "SELECT zone FROM edge_zones WHERE a=? AND b=?", (a_id, b_id)
        )]
        if zones:
            result["zones"] = zones
        return result

    def upsert_connection(self, concept_a: str, concept_b: str,
                          increment: int = 1, zone: str = None,
                          count: int = None, first_seen: str = None,
                          last_seen: str = None):
        """Increment a connection count (or create/import it).

        If count is provided, uses import mode (set exact count + dates).
        Otherwise, uses increment mode (add to existing count).
        """
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._get_or_create_concept(a_key)
        b_id = self._get_or_create_concept(b_key)
        td = today_days()

        if count is not None:
            # Import mode: set exact count and dates
            fs = date_to_days(first_seen) if first_seen else td
            ls = date_to_days(last_seen) if last_seen else td
            self._conn.execute("""
                INSERT INTO edges (a, b, count, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(a, b) DO UPDATE SET
                    count = ?,
                    first_seen = MIN(edges.first_seen, ?),
                    last_seen = MAX(edges.last_seen, ?)
            """, (a_id, b_id, count, fs, ls, count, fs, ls))
        else:
            # Increment mode: add to existing count
            self._conn.execute("""
                INSERT INTO edges (a, b, count, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(a, b) DO UPDATE SET
                    count = count + ?,
                    last_seen = ?
            """, (a_id, b_id, increment, td, td, increment, td))

        if zone:
            self._conn.execute(
                "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                (a_id, b_id, zone)
            )
        self._conn.commit()  # H3 fix: persist writes immediately

    def get_all_connections(self) -> dict:
        """Get all connections as a dict (for compatibility with existing code).

        Returns {key: {count, first_seen, last_seen, zones?}} like the JSON format.
        WARNING: This loads everything into RAM. Use only for migration/export.
        """
        result = {}

        for row in self._conn.execute("SELECT a, b, count, first_seen, last_seen FROM edges"):
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            result[key] = {
                "count": row[2],
                "first_seen": days_to_date(row[3]),
                "last_seen": days_to_date(row[4]),
            }

        # Load zones in batch
        for row in self._conn.execute("SELECT a, b, zone FROM edge_zones"):
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            if key in result:
                result[key].setdefault("zones", []).append(row[2])

        return result

    def get_all_fusions(self) -> dict:
        """Get all fusions as a dict (for compatibility).

        Returns {key: {concepts, form, strength, fused_at}} like the JSON format.
        """
        result = {}

        for row in self._conn.execute("SELECT a, b, form, strength, fused_at FROM fusions"):
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            result[key] = {
                "concepts": [a_name, b_name],
                "form": row[2],
                "strength": row[3],
                "fused_at": days_to_date(row[4]),
            }

        return result

    def connection_count(self) -> int:
        """Number of connections."""
        row = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0] if row else 0

    def fusion_count(self) -> int:
        """Number of fusions."""
        row = self._conn.execute("SELECT COUNT(*) FROM fusions").fetchone()
        return row[0] if row else 0

    def has_connection(self, concept_a: str, concept_b: str) -> bool:
        """Check if a connection exists."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM edges WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        return row is not None

    def has_fusion(self, concept_a: str, concept_b: str) -> bool:
        """Check if a fusion exists."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return False
        row = self._conn.execute(
            "SELECT 1 FROM fusions WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        return row is not None

    def upsert_fusion(self, concept_a: str, concept_b: str,
                      form: str, strength: int, fused_at=None):
        """Create or update a fusion."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._get_or_create_concept(a_key)
        b_id = self._get_or_create_concept(b_key)
        if fused_at is None:
            fused_at = today_days()
        elif isinstance(fused_at, str):
            fused_at = date_to_days(fused_at)

        self._conn.execute("""
            INSERT INTO fusions (a, b, form, strength, fused_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(a, b) DO UPDATE SET
                strength = ?,
                form = ?
        """, (a_id, b_id, form, strength, fused_at, strength, form))
        self._conn.commit()  # H3 fix: persist writes immediately

    def delete_connection(self, concept_a: str, concept_b: str):
        """Delete a connection and its fusion if any."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return
        self._conn.execute("DELETE FROM edges WHERE a=? AND b=?", (a_id, b_id))
        self._conn.execute("DELETE FROM fusions WHERE a=? AND b=?", (a_id, b_id))
        self._conn.execute("DELETE FROM edge_zones WHERE a=? AND b=?", (a_id, b_id))
        self._conn.commit()  # H4 fix: persist deletes immediately

    def update_connection_count(self, concept_a: str, concept_b: str, new_count: int):
        """Update a connection's count directly."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return
        self._conn.execute(
            "UPDATE edges SET count=? WHERE a=? AND b=?", (new_count, a_id, b_id)
        )
        self._conn.commit()  # M11 fix: persist count update

    # ── Iteration helpers (cursor-based, low RAM) ────────────────────

    def iter_connections(self):
        """Iterate over all connections as (key, {count, first_seen, last_seen}).

        Yields tuples for memory-efficient processing.
        """
        cursor = self._conn.execute(
            "SELECT a, b, count, first_seen, last_seen FROM edges"
        )
        for row in cursor:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            yield key, {
                "count": row[2],
                "first_seen": days_to_date(row[3]),
                "last_seen": days_to_date(row[4]),
            }

    def iter_connections_raw(self):
        """Iterate over raw connection data (a_id, b_id, count, first_seen, last_seen).

        Fastest iteration — no name resolution.
        """
        return self._conn.execute(
            "SELECT a, b, count, first_seen, last_seen FROM edges"
        )

    def iter_fusions(self):
        """Iterate over all fusions as (key, {concepts, form, strength, fused_at})."""
        cursor = self._conn.execute(
            "SELECT a, b, form, strength, fused_at FROM fusions"
        )
        for row in cursor:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            yield key, {
                "concepts": [a_name, b_name],
                "form": row[2],
                "strength": row[3],
                "fused_at": days_to_date(row[4]),
            }

    def get_zones_for_edge(self, concept_a: str, concept_b: str) -> list[str]:
        """Get zones for a specific edge."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return []
        return [r[0] for r in self._conn.execute(
            "SELECT zone FROM edge_zones WHERE a=? AND b=?", (a_id, b_id)
        )]

    def count_zones_for_edge(self, concept_a: str, concept_b: str) -> int:
        """Count zones for a specific edge."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) FROM edge_zones WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        return row[0] if row else 0

    def count_total_zones(self) -> int:
        """Count distinct zones across all connections."""
        row = self._conn.execute(
            "SELECT COUNT(DISTINCT zone) FROM edge_zones"
        ).fetchone()
        return max(1, row[0]) if row else 1

    def add_zone_to_edge(self, concept_a: str, concept_b: str, zone: str):
        """Add a zone to an edge."""
        a_key = min(concept_a, concept_b)
        b_key = max(concept_a, concept_b)
        a_id = self._concept_cache.get(a_key)
        b_id = self._concept_cache.get(b_key)
        if a_id is None or b_id is None:
            return
        self._conn.execute(
            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
            (a_id, b_id, zone)
        )
        self._conn.commit()  # M12 fix: persist zone addition

    # ── Top/sorted queries ───────────────────────────────────────────

    def top_connections(self, n: int = 10) -> list[tuple[str, dict]]:
        """Get top N connections by count."""
        rows = self._conn.execute(
            "SELECT a, b, count, first_seen, last_seen FROM edges ORDER BY count DESC LIMIT ?",
            (n,)
        ).fetchall()
        result = []
        for row in rows:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            result.append((key, {
                "count": row[2],
                "first_seen": days_to_date(row[3]),
                "last_seen": days_to_date(row[4]),
            }))
        return result

    def top_fusions(self, n: int = 10) -> list[tuple[str, dict]]:
        """Get top N fusions by strength."""
        rows = self._conn.execute(
            "SELECT a, b, form, strength, fused_at FROM fusions ORDER BY strength DESC LIMIT ?",
            (n,)
        ).fetchall()
        result = []
        for row in rows:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            result.append((key, {
                "concepts": [a_name, b_name],
                "form": row[2],
                "strength": row[3],
                "fused_at": days_to_date(row[4]),
            }))
        return result

    def weakest_non_fused(self, n: int = 100) -> list[tuple[str, int]]:
        """Get weakest non-fused connections (for pruning)."""
        rows = self._conn.execute("""
            SELECT e.a, e.b, e.count FROM edges e
            LEFT JOIN fusions f ON e.a = f.a AND e.b = f.b
            WHERE f.a IS NULL
            ORDER BY e.count ASC
            LIMIT ?
        """, (n,)).fetchall()
        result = []
        for row in rows:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            result.append((f"{a_name}|{b_name}", row[2]))
        return result

    def connections_older_than(self, days_threshold: int) -> list[tuple[str, dict]]:
        """Get connections whose last_seen is older than threshold days ago."""
        cutoff = today_days() - days_threshold
        rows = self._conn.execute(
            "SELECT a, b, count, first_seen, last_seen FROM edges WHERE last_seen < ?",
            (cutoff,)
        ).fetchall()
        result = []
        for row in rows:
            a_name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            b_name = self._id_to_name.get(row[1]) or self._concept_name(row[1])
            key = f"{a_name}|{b_name}"
            result.append((key, {
                "count": row[2],
                "first_seen": days_to_date(row[3]),
                "last_seen": days_to_date(row[4]),
            }))
        return result

    # ── Degree queries ───────────────────────────────────────────────

    def concept_degree(self, concept: str) -> int:
        """Get the degree (number of connections) for a concept."""
        cid = self._concept_cache.get(concept)
        if cid is None:
            return 0
        row = self._conn.execute(
            "SELECT COUNT(*) FROM edges WHERE a=? OR b=?", (cid, cid)
        ).fetchone()
        return row[0] if row else 0

    def all_degrees(self) -> dict[str, int]:
        """Get degree for all concepts. Returns {name: degree}.

        Uses SQL aggregation + JOIN for name resolution (no Python linear scan).
        """
        degree = {}
        for row in self._conn.execute("""
            SELECT c.name, SUM(d.cnt) as degree FROM (
                SELECT a as concept_id, COUNT(*) as cnt FROM edges GROUP BY a
                UNION ALL
                SELECT b as concept_id, COUNT(*) as cnt FROM edges GROUP BY b
            ) d JOIN concepts c ON c.id = d.concept_id
            GROUP BY d.concept_id
        """):
            degree[row[0]] = row[1]
        return degree

    def neighbors(self, concept: str, top_n: int = None) -> list[tuple[str, int]]:
        """Get neighbors of a concept with their connection counts."""
        cid = self._concept_cache.get(concept)
        if cid is None:
            return []
        query = """
            SELECT CASE WHEN a=? THEN b ELSE a END as neighbor, count
            FROM edges WHERE a=? OR b=?
            ORDER BY count DESC
        """
        params = (cid, cid, cid)
        if top_n is not None:
            query += " LIMIT ?"
            params = (cid, cid, cid, top_n)

        result = []
        for row in self._conn.execute(query, params):
            name = self._id_to_name.get(row[0]) or self._concept_name(row[0])
            result.append((name, row[1]))
        return result

    # ── Batch operations ─────────────────────────────────────────────

    def batch_upsert_connections(self, pairs: list[tuple[str, str]],
                                  zone: str = None):
        """Batch upsert multiple connections in a single transaction."""
        td = today_days()
        with self._conn:
            for a, b in pairs:
                a_key = min(a, b)
                b_key = max(a, b)
                a_id = self._get_or_create_concept(a_key)
                b_id = self._get_or_create_concept(b_key)
                self._conn.execute("""
                    INSERT INTO edges (a, b, count, first_seen, last_seen)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(a, b) DO UPDATE SET
                        count = count + 1,
                        last_seen = ?
                """, (a_id, b_id, td, td, td))
                if zone:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                        (a_id, b_id, zone)
                    )

    def batch_delete_connections(self, keys: list[str]):
        """Batch delete connections by key strings."""
        with self._conn:
            for key in keys:
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                self.delete_connection(parts[0], parts[1])

    def commit(self):
        """Explicit commit."""
        self._conn.commit()

    def close(self):
        """Close the database connection."""
        self._conn.close()

    # ── Migration from JSON ──────────────────────────────────────────

    @staticmethod
    def migrate_from_json(json_path: Path, db_path: Path,
                          backup: bool = True) -> "MyceliumDB":
        """Import a mycelium.json into a new SQLite database.

        Args:
            json_path: path to existing mycelium.json
            db_path: path for the new .db file
            backup: if True, rename json_path to .json.bak after migration

        Returns:
            MyceliumDB instance connected to the new database.
        """
        import sys

        print(f"Migrating {json_path} -> {db_path} ...", file=sys.stderr)
        t0 = time.time()

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        db = MyceliumDB(db_path)

        # Store meta
        for key in ("version", "repo", "created", "updated", "session_count"):
            if key in data:
                db.set_meta(key, str(data[key]))

        # Import connections in batches
        connections = data.get("connections", {})
        batch_size = 5000
        keys = list(connections.keys())
        total = len(keys)

        for i in range(0, total, batch_size):
            batch = keys[i:i + batch_size]
            with db._conn:
                for key in batch:
                    conn = connections[key]
                    parts = key.split("|")
                    if len(parts) != 2:
                        continue
                    a, b = min(parts[0], parts[1]), max(parts[0], parts[1])
                    a_id = db._get_or_create_concept(a)
                    b_id = db._get_or_create_concept(b)
                    fs = date_to_days(conn.get("first_seen", "2026-01-01"))
                    ls = date_to_days(conn.get("last_seen", "2026-01-01"))
                    db._conn.execute(
                        "INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (a_id, b_id, conn.get("count", 1), fs, ls)
                    )
                    # Zones
                    for zone in conn.get("zones", []):
                        db._conn.execute(
                            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                            (a_id, b_id, zone)
                        )
            if (i + batch_size) % 50000 == 0 or i + batch_size >= total:
                print(f"  connections: {min(i + batch_size, total)}/{total}",
                      file=sys.stderr)

        # Import fusions
        fusions = data.get("fusions", {})
        with db._conn:
            for key, fusion in fusions.items():
                parts = key.split("|")
                if len(parts) != 2:
                    continue
                a, b = min(parts[0], parts[1]), max(parts[0], parts[1])
                a_id = db._get_or_create_concept(a)
                b_id = db._get_or_create_concept(b)
                fa = date_to_days(fusion.get("fused_at", "2026-01-01"))
                db._conn.execute(
                    "INSERT OR REPLACE INTO fusions (a, b, form, strength, fused_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (a_id, b_id, fusion.get("form", f"{a}+{b}"),
                     fusion.get("strength", 1), fa)
                )

        db._conn.commit()

        elapsed = time.time() - t0
        db_size = db_path.stat().st_size / (1024 * 1024)
        json_size = json_path.stat().st_size / (1024 * 1024)
        print(f"  Done in {elapsed:.1f}s: {json_size:.0f} MB JSON -> {db_size:.0f} MB SQLite "
              f"(x{json_size/max(db_size, 0.1):.1f} smaller)", file=sys.stderr)
        print(f"  {total} connections, {len(fusions)} fusions, "
              f"{len(db._concept_cache)} concepts", file=sys.stderr)

        if backup:
            bak = json_path.with_suffix(".json.bak")
            import os
            os.replace(str(json_path), str(bak))
            print(f"  Original renamed to {bak.name}", file=sys.stderr)

        return db

    def __del__(self):
        """Close connection on garbage collection."""
        try:
            self._conn.close()
        except Exception:
            pass


class ConceptTranslator:
    """S4: Auto-translate non-English concepts to English using tokenizer + Haiku.

    Detection: tiktoken says 1 token = English, 2+ tokens = likely foreign.
    Translation: batch non-English words, send to Haiku API, cache forever.
    Cache: SQLite table in ~/.muninn/translations.db (one word = one API call ever).

    Zero dependency when tiktoken or anthropic not installed — silently passes through.
    """

    _instance = None  # Singleton

    def __init__(self):
        self._cache = {}  # in-memory: foreign -> english
        self._db_path = Path.home() / ".muninn" / "translations.db"
        self._db = None
        self._tokenizer = None
        self._api_available = False
        self._init_tokenizer()
        self._init_db()
        self._pending = []  # words waiting for batch translation

    @classmethod
    def get(cls) -> "ConceptTranslator":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_tokenizer(self):
        """Try to load tiktoken."""
        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            self._tokenizer = None

    def _init_db(self):
        """Initialize translation cache DB."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self._db_path), timeout=5)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    source TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    created TEXT NOT NULL
                )
            """)
            self._db.commit()
            # Load cache into memory
            for row in self._db.execute("SELECT source, target FROM translations"):
                self._cache[row[0]] = row[1]
        except Exception:
            self._db = None

    def is_english(self, word: str) -> bool:
        """Check if a word is English (1 token in BPE).

        ASCII-only words (with underscores/digits) are always treated as English
        to avoid translating programming identifiers like 'concept_a'.
        """
        if not self._tokenizer:
            return True  # No tokenizer = assume English (safe fallback)
        # ASCII-only words are programming identifiers, not foreign words
        if word.isascii():
            return True
        try:
            tokens = self._tokenizer.encode(word)
            return len(tokens) <= 1
        except Exception:
            return True

    def translate(self, word: str) -> str:
        """Translate a single word. Returns cached translation or original."""
        word_lower = word.lower().strip()

        # Already cached?
        if word_lower in self._cache:
            return self._cache[word_lower]

        # Is it English?
        if self.is_english(word_lower):
            return word_lower

        # Queue for batch translation
        if word_lower not in self._pending:
            self._pending.append(word_lower)

        return word_lower  # Return original until translated

    def translate_batch(self, words: list[str]) -> dict[str, str]:
        """Translate a batch of words. Returns {original: translated}.

        Only translates words not already in cache.
        Uses Haiku API if available, otherwise returns originals.
        """
        if not self._tokenizer:
            return {w: w for w in words}

        # Split into English (pass through) and non-English (need translation)
        to_translate = []
        result = {}
        for w in words:
            w_lower = w.lower().strip()
            if w_lower in self._cache:
                result[w_lower] = self._cache[w_lower]
            elif self.is_english(w_lower):
                result[w_lower] = w_lower
            else:
                to_translate.append(w_lower)
                result[w_lower] = w_lower  # default

        if not to_translate:
            return result

        # Try API translation
        translations = self._api_translate(to_translate)
        if translations:
            for src, tgt in translations.items():
                result[src] = tgt
                self._cache[src] = tgt
                self._save_translation(src, tgt)

        return result

    def _api_translate(self, words: list[str]) -> dict[str, str] | None:
        """Batch translate words via Haiku API."""
        try:
            import anthropic
        except ImportError:
            return None

        if not words:
            return None

        # Build prompt
        word_list = "\n".join(words)
        prompt = (
            f"Translate each word below to its English equivalent. "
            f"Reply with ONLY the translations, one per line, same order. "
            f"If a word is already English or a proper noun, repeat it as-is.\n\n"
            f"{word_list}"
        )

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=len(words) * 20,
                messages=[{"role": "user", "content": prompt}],
            )
            lines = response.content[0].text.strip().split("\n")

            result = {}
            for i, word in enumerate(words):
                if i < len(lines):
                    translated = lines[i].strip().lower()
                    # Sanity: translation should be shorter or similar length
                    if translated and len(translated) < len(word) * 3:
                        result[word] = translated
                    else:
                        result[word] = word
                else:
                    result[word] = word
            return result
        except Exception as e:
            import sys
            print(f"S4 translation API error: {e}", file=sys.stderr)
            return None

    def _save_translation(self, source: str, target: str):
        """Persist a translation to the cache DB."""
        if not self._db:
            return
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO translations (source, target, created) "
                "VALUES (?, ?, ?)",
                (source, target, time.strftime("%Y-%m-%d"))
            )
            self._db.commit()
        except Exception:
            pass

    def flush_pending(self) -> int:
        """Translate all pending words in one batch. Returns count translated."""
        if not self._pending:
            return 0
        words = list(set(self._pending))
        self._pending.clear()
        translations = self._api_translate(words)
        if translations:
            for src, tgt in translations.items():
                self._cache[src] = tgt
                self._save_translation(src, tgt)
            return len(translations)
        return 0

    def normalize_concepts(self, concepts: list[str]) -> list[str]:
        """Normalize a list of concepts: translate non-English to English.

        Fast path: if all concepts are English (1 token), returns as-is.
        Slow path: looks up cache, queues unknowns for batch translation.
        """
        if not self._tokenizer:
            return concepts

        result = []
        for c in concepts:
            c_lower = c.lower().strip()
            if c_lower in self._cache:
                result.append(self._cache[c_lower])
            elif self.is_english(c_lower):
                result.append(c_lower)
            else:
                # Queue for future batch translation, use original for now
                if c_lower not in self._pending:
                    self._pending.append(c_lower)
                result.append(c_lower)
        return result
