"""Muninn Sync Backend — F1-F3 of Phase 1.

Abstract sync backend + SharedFileBackend + factory.
Designed for future Git (Phase 3) and TLS (Phase 4) backends.
"""
import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    from .mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days
except ImportError:
    from mycelium_db import MyceliumDB, date_to_days, days_to_date, today_days


# ── F1: SyncPayload dataclass ────────────────────────────────────

@dataclass
class SyncEdge:
    """A single edge in a sync payload."""
    a: str
    b: str
    count: float
    first_seen: int   # epoch-days
    last_seen: int    # epoch-days
    zones: list[str] = field(default_factory=list)


@dataclass
class SyncFusion:
    """A single fusion in a sync payload."""
    a: str
    b: str
    form: str
    strength: float
    fused_at: int  # epoch-days


@dataclass
class SyncPayload:
    """F1/F5: Delta payload for sync operations.

    Contains edges and fusions to push/pull between repos.
    Serializable to JSON for transport/backup.
    """
    repo_name: str
    zone: str
    edges: list[SyncEdge] = field(default_factory=list)
    fusions: list[SyncFusion] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def to_json(self) -> str:
        """F5: Serialize payload to JSON string."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "SyncPayload":
        """F5: Deserialize payload from JSON string."""
        d = json.loads(data)
        edges = [SyncEdge(**e) for e in d.get("edges", [])]
        fusions = [SyncFusion(**f) for f in d.get("fusions", [])]
        return cls(
            repo_name=d["repo_name"],
            zone=d["zone"],
            edges=edges,
            fusions=fusions,
            timestamp=d.get("timestamp", ""),
        )


# ── F1: SyncBackend ABC ──────────────────────────────────────────

class SyncBackend(ABC):
    """F1: Abstract interface for sync backends.

    All backends must implement push/pull/status.
    SharedFileBackend (F2) = default. GitBackend (Phase 3), TLSBackend (Phase 4) = future.
    """

    @abstractmethod
    def push(self, payload: SyncPayload, local_db: MyceliumDB) -> int:
        """Push local edges/fusions to the shared meta.

        Returns the number of edges synced.
        """
        ...

    @abstractmethod
    def pull(self, local_db: MyceliumDB, query_concepts: list[str] = None,
             max_pull: int = 1000) -> int:
        """Pull relevant edges/fusions from shared meta into local.

        Returns the number of edges pulled.
        """
        ...

    @abstractmethod
    def status(self) -> dict:
        """Return backend status info (type, path, connection count, etc.)."""
        ...


# ── F2: SharedFileBackend ─────────────────────────────────────────

class SharedFileBackend(SyncBackend):
    """F2: Sync via shared SQLite file (NAS, OneDrive, local).

    This is the existing sync mechanism extracted from mycelium.py.
    Zero server, zero infra — just a shared directory.
    """

    def __init__(self, meta_dir: Path):
        self.meta_dir = Path(meta_dir)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.meta_dir / "meta_mycelium.db"

    def push(self, payload: SyncPayload, local_db: MyceliumDB) -> int:
        """Push edges/fusions to shared meta SQLite."""
        db = MyceliumDB(self.db_path)
        n_synced = 0
        try:
            # Track repo
            repos_str = db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            if payload.repo_name not in repos:
                repos.append(payload.repo_name)
                db.set_meta("repos", ",".join(repos))
            db.set_meta("type", "meta")
            db.set_meta("updated", time.strftime("%Y-%m-%d"))
            if not db.get_meta("created"):
                db.set_meta("created", time.strftime("%Y-%m-%d"))

            # Push edges from local DB
            if local_db is not None:
                for row in local_db._conn.execute(
                    "SELECT a, b, count, first_seen, last_seen FROM edges"
                ):
                    a_name = local_db._id_to_name.get(row[0])
                    b_name = local_db._id_to_name.get(row[1])
                    if not a_name or not b_name:
                        continue
                    a_id = db._get_or_create_concept(a_name)
                    b_id = db._get_or_create_concept(b_name)
                    db._conn.execute("""
                        INSERT INTO edges (a, b, count, first_seen, last_seen)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(a, b) DO UPDATE SET
                            count = MAX(count, excluded.count),
                            first_seen = MIN(first_seen, excluded.first_seen),
                            last_seen = MAX(last_seen, excluded.last_seen)
                    """, (a_id, b_id, row[2], row[3], row[4]))
                    # Zone tagging
                    if payload.zone:
                        db._conn.execute(
                            "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                            (a_id, b_id, payload.zone))
                    n_synced += 1

                # Push fusions
                for row in local_db._conn.execute(
                    "SELECT a, b, form, strength, fused_at FROM fusions"
                ):
                    a_name = local_db._id_to_name.get(row[0])
                    b_name = local_db._id_to_name.get(row[1])
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

            db.commit()
        finally:
            db.close()
        return n_synced

    def pull(self, local_db: MyceliumDB, query_concepts: list[str] = None,
             max_pull: int = 1000) -> int:
        """Pull relevant edges from meta into local DB."""
        if not self.db_path.exists():
            return 0

        db = MyceliumDB(self.db_path)
        try:
            pulled = 0
            query_ids = set()

            if query_concepts:
                query_set = {c.lower().strip() for c in query_concepts}
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

                if local_db is not None and not local_db.has_connection(a_name, b_name):
                    local_db.upsert_connection(
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
                        local_db.add_zone_to_edge(a_name, b_name, zr[0])
                    pulled += 1

            # Pull fusions
            if local_db is not None:
                if query_ids:
                    pf = ",".join("?" * len(query_ids))
                    frows = db._conn.execute(f"""
                        SELECT a, b, form, strength, fused_at FROM fusions
                        WHERE a IN ({pf}) OR b IN ({pf})
                    """, list(query_ids) + list(query_ids)).fetchall()
                else:
                    frows = db._conn.execute(
                        "SELECT a, b, form, strength, fused_at FROM fusions "
                        "ORDER BY strength DESC LIMIT ?", (max_pull,)
                    ).fetchall()

                for row in frows:
                    a_name = db._id_to_name.get(row[0]) or db._concept_name(row[0])
                    b_name = db._id_to_name.get(row[1]) or db._concept_name(row[1])
                    if not local_db.has_fusion(a_name, b_name):
                        a_id = local_db._get_or_create_concept(a_name)
                        b_id = local_db._get_or_create_concept(b_name)
                        local_db._conn.execute("""
                            INSERT OR IGNORE INTO fusions (a, b, form, strength, fused_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (a_id, b_id, row[2], row[3], row[4]))

            if local_db is not None:
                local_db.commit()
        finally:
            db.close()
        return pulled

    def status(self) -> dict:
        """Return status of the shared file backend."""
        result = {
            "type": "shared_file",
            "meta_dir": str(self.meta_dir),
            "db_exists": self.db_path.exists(),
        }
        if self.db_path.exists():
            try:
                db = MyceliumDB(self.db_path)
                result["connections"] = db.connection_count()
                result["concepts"] = len(db._concept_cache)
                result["fusions"] = db.fusion_count()
                repos_str = db.get_meta("repos", "")
                result["repos"] = repos_str.split(",") if repos_str else []
                db.close()
            except Exception:
                result["error"] = "failed to read meta DB"
        return result


# ── F3: Factory + Config ─────────────────────────────────────────

def _load_sync_config() -> dict:
    """F3/F6: Load sync config from config.json + env var override.

    Priority: MUNINN_META_PATH env var > config.json > default ~/.muninn/
    """
    config = {"backend": "shared_file", "meta_path": None}

    # F6: Env var override (highest priority)
    env_path = os.environ.get("MUNINN_META_PATH")
    if env_path:
        config["meta_path"] = env_path
        return config

    # Config file
    config_path = Path.home() / ".muninn" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(cfg.get("meta_path"), str):
                p = Path(cfg["meta_path"])
                # X14: Validate path
                if ".." not in p.parts:
                    config["meta_path"] = str(p)
            config["backend"] = cfg.get("backend", "shared_file")
        except (ValueError, OSError):
            pass

    return config


def get_sync_backend(config: dict = None) -> SyncBackend:
    """F3: Factory — return the right backend based on config.

    Currently only SharedFileBackend. Git and TLS backends added in Phases 3-4.
    """
    if config is None:
        config = _load_sync_config()

    meta_path = config.get("meta_path")
    if meta_path:
        meta_dir = Path(meta_path)
    else:
        meta_dir = Path.home() / ".muninn"

    backend_type = config.get("backend", "shared_file")

    if backend_type == "shared_file":
        return SharedFileBackend(meta_dir)
    # Future: "git" -> GitBackend, "tls" -> TLSBackend
    else:
        # Fall back to shared file
        return SharedFileBackend(meta_dir)


# ── F7: Config atomic write ──────────────────────────────────────

def save_sync_config(config: dict):
    """F7: Atomic write config.json."""
    import tempfile
    config_path = Path.home() / ".muninn" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(config_path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(config_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
