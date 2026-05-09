#!/usr/bin/env python3
"""Muninn Mycelium — Meta-mycelium federation mixin.

H6 chunk 1 (2026-05-09): extracted from engine/core/mycelium.py
to reduce the god-class. Mixed into Mycelium via multiple inheritance,
no behavior change. All methods access self attributes provided by the
core mixin (self._db, self.data, self.zone, self.repo_path).

Public API exposed by this mixin (called by tests + sync_backend):
  - Mycelium._load_meta_dir()    @staticmethod  (resolves meta dir)
  - Mycelium.meta_path()         @staticmethod  (legacy JSON path)
  - Mycelium.meta_db_path()      @staticmethod  (SQLite DB path)
  - Mycelium.sync_to_meta()                     (push local → meta)
  - Mycelium.pull_from_meta()                   (pull meta → local)

See docs/BATTLE_PLAN_FINAL_PROD_v3_2026-05-09.md H6.
"""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# Same dual import dance as mycelium.py — works as package or standalone.
try:
    from .mycelium_db import MyceliumDB, days_to_date, date_to_days
except ImportError:
    from mycelium_db import MyceliumDB, days_to_date, date_to_days  # type: ignore[no-redef]


class _MyceliumMetaMixin:
    """Cross-repo federation: meta-mycelium sync + pull.

    All methods rely on attributes set up by the core Mycelium __init__
    (self._db, self.data, self.zone, self.repo_path).
    """

    # ── P20b: Meta-mycelium sync ──────────────────────────────────

    @staticmethod
    def _load_meta_dir() -> Path:
        """Load meta-mycelium directory.

        Resolution order:
          1. env MUNINN_META_PATH — used by tests to point at tmp_path,
             and by BRICK 22 guards that explicitly check it
          2. ~/.muninn/config.json {"meta_path": "..."} — user override
          3. ~/.muninn/ — default

        Supports: local path, NAS (//server/share), OneDrive, any mounted folder.
        Team use: point all devs to the same meta_path for shared collective brain.
        """
        env_path = os.environ.get("MUNINN_META_PATH")
        if env_path:
            p = Path(env_path).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        config_path = Path.home() / ".muninn" / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                custom = cfg.get("meta_path")
                if custom and isinstance(custom, str):
                    p = Path(custom).resolve()
                    # X14: Validate path — no traversal, no symlink to outside
                    if ".." in Path(custom).parts:
                        print("WARNING: meta_path contains '..', ignoring", file=sys.stderr)
                    elif p.is_symlink() and not p.resolve().is_dir():
                        print("WARNING: meta_path symlink target is not a directory", file=sys.stderr)
                    else:
                        p.mkdir(parents=True, exist_ok=True)
                        return p
            except (ValueError, OSError, KeyError):
                pass
        return Path.home() / ".muninn"

    @staticmethod
    def meta_path() -> Path:
        """Path to the shared meta-mycelium JSON (legacy compat)."""
        return _MyceliumMetaMixin._load_meta_dir() / "meta_mycelium.json"

    @staticmethod
    def meta_db_path() -> Path:
        """Path to the shared meta-mycelium SQLite DB.
        Configurable via ~/.muninn/config.json {"meta_path": "..."}"""
        return _MyceliumMetaMixin._load_meta_dir() / "meta_mycelium.db"

    def sync_to_meta(self):
        """F4: Push local connections to the shared meta-mycelium.

        Delegates to SyncBackend (F1-F3). Default: SharedFileBackend.
        Falls back to legacy code for dict mode (JSON mycelium).

        Merge strategy: MAX(count), MIN(first_seen), MAX(last_seen), union(zones).
        """
        try:
            from sync_backend import get_sync_backend, SyncPayload
        except ImportError:
            from .sync_backend import get_sync_backend, SyncPayload

        meta_db_p = self.meta_db_path()
        meta_json_p = self.meta_path()
        meta_db_p.parent.mkdir(exist_ok=True)

        # Auto-migrate JSON meta to SQLite if needed
        if meta_json_p.exists() and not meta_db_p.exists():
            try:
                migrated_db = MyceliumDB.migrate_from_json(meta_json_p, meta_db_p)
                migrated_db.close()  # X8: close returned handle
            except (sqlite3.Error, OSError, json.JSONDecodeError, ValueError) as e:
                print(f"WARNING: meta migration failed: {e}", file=sys.stderr)

        if self._db is not None:
            # F4: Delegate to backend
            backend = get_sync_backend()
            payload = SyncPayload(
                repo_name=self.repo_path.name,
                zone=self.zone or self.repo_path.name,
            )
            return backend.push(payload, self._db)
        else:
            # Legacy dict mode — direct sync (unchanged)
            db = MyceliumDB(meta_db_p)
            n_synced = 0
            try:
                repos_str = db.get_meta("repos", "")
                repos = repos_str.split(",") if repos_str else []
                if self.repo_path.name not in repos:
                    repos.append(self.repo_path.name)
                    db.set_meta("repos", ",".join(repos))
                db.set_meta("type", "meta")
                db.set_meta("updated", time.strftime("%Y-%m-%d"))
                if not db.get_meta("created"):
                    db.set_meta("created", time.strftime("%Y-%m-%d"))

                zone = self.zone
                local_conns = self.data["connections"]
                n_synced = len(local_conns)
                with db.transaction() as txn:
                    for key, edge_data in local_conns.items():
                        parts = key.split("|")
                        if len(parts) != 2:
                            continue
                        a, b = parts
                        a_id = db._get_or_create_concept(a)
                        b_id = db._get_or_create_concept(b)
                        fs = date_to_days(edge_data.get("first_seen", "2026-01-01"))
                        ls = date_to_days(edge_data.get("last_seen", "2026-01-01"))
                        txn.execute("""
                            INSERT INTO edges (a, b, count, first_seen, last_seen)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                count = MAX(count, excluded.count),
                                first_seen = MIN(first_seen, excluded.first_seen),
                                last_seen = MAX(last_seen, excluded.last_seen)
                        """, (a_id, b_id, edge_data["count"], fs, ls))
                        txn.execute(
                            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                            (a_id, b_id, zone))

                    local_fusions = self.data.get("fusions", {})
                    for key, fusion in local_fusions.items():
                        parts = key.split("|")
                        if len(parts) != 2:
                            continue
                        a, b = parts
                        a_id = db._get_or_create_concept(a)
                        b_id = db._get_or_create_concept(b)
                        fa = date_to_days(fusion.get("fused_at", "2026-01-01"))
                        txn.execute("""
                            INSERT INTO fusions (a, b, form, strength, fused_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(a, b) DO UPDATE SET
                                strength = MAX(strength, excluded.strength)
                        """, (a_id, b_id, fusion["form"], fusion["strength"], fa))
            finally:
                db.close()
            return n_synced

    def pull_from_meta(self, query_concepts: list[str] = None, max_pull: int = 1000):
        """F4: Pull relevant connections from meta-mycelium into local.

        Delegates to SyncBackend (F1-F3) when in SQLite mode.
        Falls back to legacy code for dict mode (JSON mycelium).

        If query_concepts given, only pulls connections involving those concepts.
        Otherwise pulls top connections by count.
        Does NOT overwrite local data — only adds what's missing.

        BRICK 22 fix (BUG-110): bypass meta pull when in dict mode and the
        meta DB is the user's global home one (>100MB). Tests that
        explicitly set MUNINN_META_PATH to tmp still work.
        """
        meta_db_p = self.meta_db_path()
        meta_json_p = self.meta_path()

        # BUG-110 guard
        if self._db is None and not os.environ.get("MUNINN_META_PATH"):
            try:
                if meta_db_p.exists() and meta_db_p.stat().st_size > 100 * 1024 * 1024:
                    return 0
            except OSError:
                pass

        # F4: Delegate to backend for SQLite mode
        if self._db is not None and meta_db_p.exists():
            try:
                from sync_backend import get_sync_backend
            except ImportError:
                from .sync_backend import get_sync_backend
            backend = get_sync_backend()
            # H8: Auto-filter by local concepts if no explicit query
            if query_concepts is None and self._db is not None:
                local_concepts = list(self._db._concept_cache.keys())
                if local_concepts:
                    query_concepts = local_concepts[:500]  # Cap to avoid huge queries
            return backend.pull(self._db, query_concepts, max_pull)

        # Legacy: dict mode or JSON fallback
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
            id_to_name = db._id_to_name

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
                with db._lock:
                    rows = db._conn.execute(f"""
                        SELECT a, b, count, first_seen, last_seen FROM edges
                        WHERE a IN ({placeholders}) OR b IN ({placeholders})
                        ORDER BY count DESC LIMIT ?
                    """, list(query_ids) + list(query_ids) + [max_pull]).fetchall()
            else:
                with db._lock:
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
                        with db._lock:
                            zone_rows = db._conn.execute(
                                "SELECT zone FROM edge_zones WHERE a=? AND b=?",
                                (row[0], row[1])
                            ).fetchall()
                        for zr in zone_rows:
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
                        with db._lock:
                            zones = [r[0] for r in db._conn.execute(
                                "SELECT zone FROM edge_zones WHERE a=? AND b=?",
                                (row[0], row[1])
                            ).fetchall()]
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
                with db._lock:
                    fusion_rows = db._conn.execute(fquery, fparams).fetchall()
                for frow in fusion_rows:
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
                    with db._lock:
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
