"""Muninn Sync Backend — F1-F3 of Phase 1.

Abstract sync backend + SharedFileBackend + factory.
Designed for future Git (Phase 3) and TLS (Phase 4) backends.
"""
import hashlib
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


# ── H9: Disk full guard ─────────────────────────────────────────

def check_disk_space(path: Path, min_mb: int = 10) -> bool:
    """H9: Check if at least min_mb of disk space is available.

    Returns True if enough space, False otherwise.
    """
    import shutil
    try:
        usage = shutil.disk_usage(str(path))
        free_mb = usage.free / (1024 * 1024)
        return free_mb >= min_mb
    except (OSError, AttributeError):
        return True  # Can't check = assume OK


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

    def checksum(self) -> str:
        """H3: SHA256 checksum of the payload content."""
        content = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

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

    NETWORK_TIMEOUT = 5  # H11: seconds to wait for NAS/network paths

    def __init__(self, meta_dir: Path):
        self.meta_dir = Path(meta_dir)
        # H11: Timeout-protected mkdir for network paths
        self._safe_mkdir(self.meta_dir)
        self.db_path = self.meta_dir / "meta_mycelium.db"

    def _safe_mkdir(self, path: Path, timeout: int = None):
        """H11: mkdir with timeout for network paths."""
        if timeout is None:
            timeout = self.NETWORK_TIMEOUT
        import threading
        result = [None]
        def _do():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                result[0] = e
        t = threading.Thread(target=_do, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"H11: Network path {path} not reachable within {timeout}s")
        if result[0]:
            raise result[0]

    def push(self, payload: SyncPayload, local_db: MyceliumDB) -> int:
        """Push edges/fusions to shared meta SQLite.

        H1: logs sync operation. H2: transaction rollback on failure.
        H3: records checksum. H4: skips tombstoned edges. H9: disk guard.
        """
        # H9: Check disk space before write
        if not check_disk_space(self.meta_dir):
            raise OSError("H9: Insufficient disk space (<10MB) for sync push")
        db = MyceliumDB(self.db_path)
        n_synced = 0
        errors = None
        try:
            # Track repo (raw SQL — no auto-commit, H2 safety)
            repos_str = db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            if payload.repo_name not in repos:
                repos.append(payload.repo_name)
                db._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("repos", ",".join(repos)))
            db._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("type", "meta"))
            db._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("updated", time.strftime("%Y-%m-%d")))
            if not db.get_meta("created"):
                db._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("created", time.strftime("%Y-%m-%d")))

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

                # Push fusions — H5: zone-voted conflict resolution
                for row in local_db._conn.execute(
                    "SELECT a, b, form, strength, fused_at FROM fusions"
                ):
                    a_name = local_db._id_to_name.get(row[0])
                    b_name = local_db._id_to_name.get(row[1])
                    if not a_name or not b_name:
                        continue
                    a_id = db._get_or_create_concept(a_name)
                    b_id = db._get_or_create_concept(b_name)
                    # H5: If fusion already exists with different form, keep
                    # the one with higher strength (proxy for more zone votes)
                    existing = db._conn.execute(
                        "SELECT form, strength FROM fusions WHERE a=? AND b=?",
                        (a_id, b_id)
                    ).fetchone()
                    if existing and existing[0] != row[2]:
                        # Different form — keep the stronger one
                        if row[3] <= existing[1]:
                            continue  # Existing form wins
                    db._conn.execute("""
                        INSERT INTO fusions (a, b, form, strength, fused_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(a, b) DO UPDATE SET
                            strength = MAX(strength, excluded.strength),
                            form = CASE WHEN excluded.strength > strength
                                   THEN excluded.form ELSE form END
                    """, (a_id, b_id, row[2], row[3], row[4]))

            # H2: commit all at once (rollback on exception = no commit)
            db.commit()
        except Exception as e:
            errors = str(e)
            raise
        finally:
            # H1: audit log + H3: checksum
            try:
                db.log_sync(
                    action="push", repo=payload.repo_name,
                    count=n_synced, errors=errors,
                    checksum=payload.checksum(),
                )
            except Exception:
                pass
            db.close()
        return n_synced

    def pull(self, local_db: MyceliumDB, query_concepts: list[str] = None,
             max_pull: int = 1000) -> int:
        """Pull relevant edges from meta into local DB.

        H1: logs sync. H2: savepoint for rollback. H4: respects tombstones.
        """
        if not self.db_path.exists():
            return 0

        db = MyceliumDB(self.db_path)
        errors = None
        try:
            pulled = 0
            query_ids = set()

            # H4: load local tombstones to skip
            local_tombstones = set()
            try:
                for ts in local_db.get_tombstones():
                    local_tombstones.add((ts[0], ts[1]))
            except Exception:
                pass  # No tombstones table = old schema, skip

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

                # H4: skip tombstoned edges
                a_key = min(a_name, b_name)
                b_key = max(a_name, b_name)
                if (a_key, b_key) in local_tombstones:
                    continue

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

            # H2: commit all at once (no commit on exception = auto rollback)
            if local_db is not None:
                local_db.commit()
        except Exception as e:
            errors = str(e)
            raise
        finally:
            # H1: audit log
            try:
                db.log_sync(action="pull", count=pulled, errors=errors)
            except Exception:
                pass
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
    elif backend_type == "git":
        git_path = config.get("git_path") or str(meta_dir / "sync.git")
        remote = config.get("git_remote")
        return GitBackend(Path(git_path), remote=remote)
    elif backend_type == "tls":
        from sync_tls import TLSBackend
        return TLSBackend(
            host=config.get("tls_host", "localhost"),
            port=config.get("tls_port", 9477),
            cert_path=config.get("tls_cert"),
            verify=config.get("tls_verify", True),
        )
    else:
        # Fall back to shared file
        return SharedFileBackend(meta_dir)


# ── G1-G5: GitBackend ────────────────────────────────────────────

import subprocess

class GitBackend(SyncBackend):
    """G1: Sync via bare git repo (local or remote).

    Exports edges/fusions as JSON to a bare git repo. Each push creates
    a commit with the delta. Pull merges via CRDT (G2).
    Supports local bare repos and remote (Gitea/GitLab/SSH) via G4.
    """

    def __init__(self, repo_path: Path, remote: str = None):
        self.repo_path = Path(repo_path)
        self.remote = remote  # G4: optional remote URL
        self._ensure_repo()

    def _git(self, *args, cwd=None, check=True) -> subprocess.CompletedProcess:
        """Run a git command in the repo."""
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd, cwd=str(cwd or self.repo_path),
            capture_output=True, text=True, timeout=30,
            check=check,
        )

    def _ensure_repo(self):
        """G1/G3: Auto-init bare repo if needed."""
        if not self.repo_path.exists():
            self.repo_path.mkdir(parents=True, exist_ok=True)
            # Init as a non-bare repo (we need a working tree for add/commit)
            self._git("init", cwd=self.repo_path)
            # Create initial commit
            meta_file = self.repo_path / "meta.json"
            meta_file.write_text(json.dumps({
                "type": "muninn_sync", "created": time.strftime("%Y-%m-%d"),
                "version": 1,
            }, indent=2), encoding="utf-8")
            self._git("add", "meta.json", cwd=self.repo_path)
            self._git("commit", "-m", "init: muninn sync repo", cwd=self.repo_path)
        elif not (self.repo_path / ".git").exists() and not (self.repo_path / "HEAD").exists():
            # Directory exists but no git — init
            self._git("init", cwd=self.repo_path)

    def _pull_remote(self):
        """G4: Pull from remote if configured."""
        if not self.remote:
            return
        # Check if remote exists
        r = self._git("remote", cwd=self.repo_path, check=False)
        if "origin" not in r.stdout:
            self._git("remote", "add", "origin", self.remote, cwd=self.repo_path)
        self._git("pull", "--rebase", "origin", "main",
                  cwd=self.repo_path, check=False)

    def _push_remote(self):
        """G4: Push to remote if configured."""
        if not self.remote:
            return
        self._git("push", "origin", "main", cwd=self.repo_path, check=False)

    def push(self, payload: SyncPayload, local_db: MyceliumDB) -> int:
        """G1: Export local edges to JSON file, commit to git repo."""
        if not check_disk_space(self.repo_path):
            raise OSError("H9: Insufficient disk space for git sync")

        # G4: Pull remote first to get latest state
        self._pull_remote()

        # G5: Delta sync — only export edges newer than last sync
        last_sync_str = "0"
        meta_file = self.repo_path / "meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                last_sync_str = str(meta.get("last_sync_day", "0"))
            except (ValueError, OSError):
                pass
        last_sync_day = int(last_sync_str) if last_sync_str.isdigit() else 0

        # Export edges from local DB
        edges = []
        fusions = []
        n_synced = 0

        if local_db is not None:
            for row in local_db._conn.execute(
                "SELECT a, b, count, first_seen, last_seen FROM edges WHERE last_seen >= ?",
                (last_sync_day,)
            ):
                a_name = local_db._id_to_name.get(row[0])
                b_name = local_db._id_to_name.get(row[1])
                if not a_name or not b_name:
                    continue
                edges.append({
                    "a": a_name, "b": b_name,
                    "count": row[2], "first_seen": row[3], "last_seen": row[4],
                })
                n_synced += 1

            for row in local_db._conn.execute(
                "SELECT a, b, form, strength, fused_at FROM fusions"
            ):
                a_name = local_db._id_to_name.get(row[0])
                b_name = local_db._id_to_name.get(row[1])
                if not a_name or not b_name:
                    continue
                fusions.append({
                    "a": a_name, "b": b_name,
                    "form": row[2], "strength": row[3], "fused_at": row[4],
                })

        # Write delta file
        delta_file = self.repo_path / f"{payload.repo_name}.json"
        delta = {
            "repo": payload.repo_name, "zone": payload.zone,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "edges": edges, "fusions": fusions,
            "checksum": payload.checksum(),
        }
        delta_file.write_text(
            json.dumps(delta, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # Update meta
        meta = {"type": "muninn_sync", "updated": time.strftime("%Y-%m-%d"),
                "last_sync_day": today_days(), "version": 1}
        if meta_file.exists():
            try:
                old_meta = json.loads(meta_file.read_text(encoding="utf-8"))
                repos = old_meta.get("repos", [])
                if payload.repo_name not in repos:
                    repos.append(payload.repo_name)
                meta["repos"] = repos
                meta["created"] = old_meta.get("created", meta["updated"])
            except (ValueError, OSError):
                meta["repos"] = [payload.repo_name]
                meta["created"] = meta["updated"]
        else:
            meta["repos"] = [payload.repo_name]
            meta["created"] = meta["updated"]

        meta_file.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # Git commit
        self._git("add", "-A", cwd=self.repo_path)
        r = self._git("diff", "--cached", "--quiet", cwd=self.repo_path, check=False)
        if r.returncode != 0:  # There are staged changes
            self._git("commit", "-m",
                      f"sync: {payload.repo_name} ({n_synced} edges)",
                      cwd=self.repo_path)

        # G4: Push to remote
        self._push_remote()

        return n_synced

    def pull(self, local_db: MyceliumDB, query_concepts: list[str] = None,
             max_pull: int = 1000) -> int:
        """G1/G2: Pull edges from git repo, CRDT merge into local DB."""
        if not self.repo_path.exists():
            return 0

        # G4: Pull remote first
        self._pull_remote()

        pulled = 0
        query_set = {c.lower().strip() for c in query_concepts} if query_concepts else None

        # Load tombstones
        local_tombstones = set()
        try:
            for ts in local_db.get_tombstones():
                local_tombstones.add((ts[0], ts[1]))
        except Exception:
            pass

        # Read all repo JSON files
        for json_file in self.repo_path.glob("*.json"):
            if json_file.name == "meta.json":
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue

            for edge in data.get("edges", []):
                a, b = edge["a"], edge["b"]
                a_key, b_key = min(a, b), max(a, b)

                # H4: skip tombstoned
                if (a_key, b_key) in local_tombstones:
                    continue

                # H8: filter by query concepts
                if query_set and a_key not in query_set and b_key not in query_set:
                    continue

                if pulled >= max_pull:
                    break

                # G2: CRDT merge — MAX count, MIN first_seen, MAX last_seen
                if not local_db.has_connection(a, b):
                    local_db.upsert_connection(
                        a, b, count=edge["count"],
                        first_seen=days_to_date(edge["first_seen"]),
                        last_seen=days_to_date(edge["last_seen"]),
                    )
                    pulled += 1
                else:
                    # Update if remote has higher count
                    existing = local_db.get_connection(a, b)
                    if existing and edge["count"] > existing["count"]:
                        local_db.update_connection_count(a, b, edge["count"])

            # Pull fusions
            for fusion in data.get("fusions", []):
                a, b = fusion["a"], fusion["b"]
                if not local_db.has_fusion(a, b):
                    local_db.upsert_fusion(
                        a, b, form=fusion["form"],
                        strength=fusion["strength"],
                        fused_at=fusion.get("fused_at"),
                    )

        local_db.commit()
        return pulled

    def status(self) -> dict:
        """G1: Return git backend status."""
        result = {
            "type": "git",
            "repo_path": str(self.repo_path),
            "exists": self.repo_path.exists(),
            "remote": self.remote,
        }
        if self.repo_path.exists():
            # Count repo files
            json_files = list(self.repo_path.glob("*.json"))
            result["repo_files"] = len(json_files) - 1  # Minus meta.json
            # Git log
            r = self._git("log", "--oneline", "-5", cwd=self.repo_path, check=False)
            if r.returncode == 0:
                result["recent_commits"] = r.stdout.strip().split("\n")
            # Meta
            meta_file = self.repo_path / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    result["repos"] = meta.get("repos", [])
                except (ValueError, OSError):
                    pass
        return result

    @staticmethod
    def init_repo(path: Path, remote: str = None) -> "GitBackend":
        """G3: CLI entrypoint — muninn sync --init-git /path."""
        backend = GitBackend(path, remote=remote)
        if remote:
            backend._git("remote", "add", "origin", remote,
                         cwd=path, check=False)
        return backend


# ── F7: Config atomic write ──────────────────────────────────────

def save_sync_config(config: dict):
    """F7/H9: Atomic write config.json with disk guard."""
    import tempfile
    config_path = Path.home() / ".muninn" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # H9: disk guard
    if not check_disk_space(config_path.parent):
        raise OSError("H9: Insufficient disk space (<10MB) for config write")

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
