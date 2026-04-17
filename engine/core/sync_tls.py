#!/usr/bin/env python3
"""
Muninn Sync TLS — Secure transport for meta-mycelium synchronization.

Provides encrypted network transport (TLS 1.3) for syncing mycelium data
between machines. Replaces local filesystem sync when offices/teams are remote.

Architecture:
    LOCAL  (current):  sync_to_meta() writes to ~/.muninn/meta_mycelium.db (same machine)
    REMOTE (this):     sync_to_meta() sends encrypted diff to a remote server via TLS

Components:
    SyncServer  — listens on a port, receives mycelium diffs, merges into meta DB
    SyncClient  — connects to server, sends local diff, pulls remote updates
    generate_certs() — generate self-signed certs for testing/internal use

Security:
    - TLS 1.3 minimum (ssl.TLSVersion.TLSv1_3)
    - Certificate verification (can use self-signed for internal)
    - AES-256-GCM under the hood (via TLS cipher suite)
    - No plaintext fallback

Requires: Python 3.10+ (ssl stdlib). No pip dependency.
"""
import collections
import json
import socket
import sqlite3
import ssl
import struct
import threading
import time
import warnings
from pathlib import Path

# Protocol: 4-byte length prefix (big-endian uint32) + JSON payload
_HEADER_SIZE = 4
_DEFAULT_PORT = 9477  # M-U-N-N on phone keypad
_TLS_MIN = ssl.TLSVersion.TLSv1_3  # TLS 1.3 minimum — no downgrade to 1.2


def generate_certs(cert_dir: Path, cn: str = "muninn-sync") -> dict:
    """Generate self-signed TLS certificate + key for internal/testing use.

    Returns: {cert_path, key_path}
    Requires: pip install cryptography (only for cert generation, not for TLS itself)
    """
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timedelta, timezone

    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Muninn"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(__import__("ipaddress").IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path = cert_dir / "muninn.crt"
    key_path = cert_dir / "muninn.key"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

    return {"cert_path": str(cert_path), "key_path": str(key_path)}


def _send_msg(sock, data: dict):
    """Send a length-prefixed JSON message over a socket."""
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack(">I", len(payload)) + payload)


def _recv_msg(sock) -> dict:
    """Receive a length-prefixed JSON message from a socket."""
    header = b""
    while len(header) < _HEADER_SIZE:
        chunk = sock.recv(_HEADER_SIZE - len(header))
        if not chunk:
            raise ConnectionError("Connection closed")
        header += chunk
    length = struct.unpack(">I", header)[0]
    if length > 50 * 1024 * 1024:  # 50MB max message
        raise ValueError(f"Message too large: {length} bytes")
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(min(length - len(payload), 65536))
        if not chunk:
            raise ConnectionError("Connection closed during payload")
        payload += chunk
    return json.loads(payload.decode("utf-8"))


class RateLimiter:
    """Per-IP token bucket rate limiter. Thread-safe."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max = max_requests
        self.window = window_seconds
        self._hits = collections.defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.monotonic()
        with self._lock:
            self._hits[ip] = [t for t in self._hits[ip] if now - t < self.window]
            if not self._hits[ip]:
                del self._hits[ip]
                # Fresh entry — allow and record
                self._hits[ip] = [now]
                return True
            if len(self._hits[ip]) >= self.max:
                return False
            self._hits[ip].append(now)
            return True


class SyncServer:
    """TLS server that receives mycelium diffs and merges them."""

    def __init__(self, cert_path: str, key_path: str, meta_db_path: str,
                 host: str = "0.0.0.0", port: int = _DEFAULT_PORT,
                 ca_path: str = None, require_client_cert: bool = False,
                 max_requests_per_min: int = 30,
                 allowed_users: list = None):
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
        self.require_client_cert = require_client_cert
        self.meta_db_path = meta_db_path
        self.host = host
        self.port = port
        self._running = False
        self._server_socket = None
        self._thread = None
        self._limiter = RateLimiter(max_requests=max_requests_per_min, window_seconds=60)
        # T4: ACL — list of allowed CN values (None = allow all)
        self.allowed_users = allowed_users

    def _create_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = _TLS_MIN
        ctx.load_cert_chain(self.cert_path, self.key_path)
        # mTLS: require client certificate if CA provided
        if self.require_client_cert:
            if not self.ca_path:
                raise ValueError("require_client_cert=True requires ca_path to verify clients")
            ctx.load_verify_locations(self.ca_path)
            ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def _check_acl(self, conn) -> str | None:
        """T4: Check client cert CN against allowed users.

        Returns CN string if authorized, None if no cert or not checked.
        Raises PermissionError if CN not in allowed_users.
        """
        if not self.require_client_cert:
            return None
        try:
            cert = conn.getpeercert()
            if not cert:
                return None
            # Extract CN from subject
            for field in cert.get("subject", ()):
                for key, value in field:
                    if key == "commonName":
                        if self.allowed_users and value not in self.allowed_users:
                            raise PermissionError(f"T4: User '{value}' not authorized")
                        return value
        except PermissionError:
            raise
        except (ssl.SSLError, ValueError, AttributeError):
            pass
        return None

    def _handle_client(self, conn, addr):
        # Rate limiting
        ip = addr[0] if addr else "unknown"
        if not self._limiter.allow(ip):
            try:
                _send_msg(conn, {"status": "error", "message": "rate_limited"})
            except (OSError, ssl.SSLError):
                pass
            conn.close()
            return

        try:
            # T4: ACL check
            try:
                user_cn = self._check_acl(conn)
            except PermissionError as pe:
                _send_msg(conn, {"status": "error", "message": str(pe)})
                conn.close()
                return

            msg = _recv_msg(conn)
            action = msg.get("action")

            if action == "push":
                # T1: Real CRDT merge into meta DB
                connections = msg.get("connections", [])
                repo_name = msg.get("repo", "unknown")
                zone = msg.get("zone", repo_name)
                merged = self._merge_push(connections, repo_name, zone)
                _send_msg(conn, {
                    "status": "ok",
                    "merged": merged,
                    "repo": repo_name,
                })

            elif action == "pull":
                # T1: Real data return from meta DB
                concepts = msg.get("concepts", [])
                max_pull = msg.get("max_pull", 1000)
                result = self._query_pull(concepts, max_pull)
                _send_msg(conn, {
                    "status": "ok",
                    "connections": result["connections"],
                    "fusions": result["fusions"],
                    "count": result["count"],
                })

            elif action == "ping":
                _send_msg(conn, {"status": "pong", "version": "0.9.1"})

            else:
                _send_msg(conn, {"status": "error", "message": f"unknown action: {action}"})

        except (OSError, ssl.SSLError, ValueError, json.JSONDecodeError) as e:
            try:
                _send_msg(conn, {"status": "error", "message": "internal error"})
            except (OSError, ssl.SSLError):
                pass
        finally:
            conn.close()

    def _merge_push(self, connections: list, repo_name: str, zone: str) -> int:
        """T1: CRDT merge incoming connections into meta DB.

        MAX(count), MIN(first_seen), MAX(last_seen), union(zones).
        """
        try:
            from mycelium_db import MyceliumDB, date_to_days, today_days
        except ImportError:
            from .mycelium_db import MyceliumDB, date_to_days, today_days

        db = MyceliumDB(Path(self.meta_db_path))
        merged = 0
        try:
            # Track repo
            repos_str = db.get_meta("repos", "")
            repos = repos_str.split(",") if repos_str else []
            if repo_name not in repos:
                repos.append(repo_name)
                db._conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("repos", ",".join(repos)))

            for conn in connections:
                a, b = conn.get("a", ""), conn.get("b", "")
                if not a or not b:
                    continue
                # Normalize key order (min/max) to match MyceliumDB convention
                a_norm, b_norm = min(a, b), max(a, b)
                a_id = db._get_or_create_concept(a_norm)
                b_id = db._get_or_create_concept(b_norm)
                count = conn.get("count", 1)
                fs = conn.get("first_seen", today_days())
                ls = conn.get("last_seen", today_days())
                db._conn.execute("""
                    INSERT INTO edges (a, b, count, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(a, b) DO UPDATE SET
                        count = MAX(count, excluded.count),
                        first_seen = MIN(first_seen, excluded.first_seen),
                        last_seen = MAX(last_seen, excluded.last_seen)
                """, (a_id, b_id, count, fs, ls))
                if zone:
                    db._conn.execute(
                        "INSERT OR IGNORE INTO edge_zones (a, b, zone) VALUES (?, ?, ?)",
                        (a_id, b_id, zone))
                merged += 1

            db.commit()
            # H1: audit log
            try:
                db.log_sync(action="push_tls", repo=repo_name, count=merged)
            except (sqlite3.Error, OSError):
                pass
        finally:
            db.close()
        return merged

    def _query_pull(self, concepts: list, max_pull: int) -> dict:
        """T1: Query meta DB for connections matching concepts."""
        try:
            from mycelium_db import MyceliumDB, days_to_date
        except ImportError:
            from .mycelium_db import MyceliumDB, days_to_date

        db = MyceliumDB(Path(self.meta_db_path))
        result = {"connections": [], "fusions": [], "count": 0}
        query_ids = set()  # CHUNK 8 fix: init before the if/else
        try:
            if concepts:
                query_ids = set()
                for c in concepts:
                    cid = db._concept_cache.get(c.lower().strip())
                    if cid is not None:
                        query_ids.add(cid)
                if not query_ids:
                    return result
                ph = ",".join("?" * len(query_ids))
                rows = db._conn.execute(f"""
                    SELECT a, b, count, first_seen, last_seen FROM edges
                    WHERE a IN ({ph}) OR b IN ({ph})
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
                result["connections"].append({
                    "a": a_name, "b": b_name,
                    "count": row[2], "first_seen": row[3], "last_seen": row[4],
                })
            result["count"] = len(result["connections"])

            # CHUNK 8: Also pull fusions (same as SharedFileBackend)
            if query_ids:
                ph = ",".join("?" * len(query_ids))
                fusion_rows = db._conn.execute(f"""
                    SELECT a, b, form, strength, fused_at FROM fusions
                    WHERE a IN ({ph}) OR b IN ({ph})
                """, list(query_ids) + list(query_ids)).fetchall()
            else:
                fusion_rows = db._conn.execute(
                    "SELECT a, b, form, strength, fused_at FROM fusions "
                    "ORDER BY strength DESC LIMIT ?", (max_pull,)
                ).fetchall()
            for row in fusion_rows:
                a_name = db._id_to_name.get(row[0]) or db._concept_name(row[0])
                b_name = db._id_to_name.get(row[1]) or db._concept_name(row[1])
                result["fusions"].append({
                    "a": a_name, "b": b_name,
                    "form": row[2], "strength": row[3], "fused_at": row[4],
                })
        finally:
            db.close()
        return result

    def start(self, background: bool = True):
        """Start the TLS server. If background=True, runs in a thread."""
        ctx = self._create_context()
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)
        self._running = True

        def _serve():
            with ctx.wrap_socket(self._server_socket, server_side=True) as ssock:
                while self._running:
                    try:
                        conn, addr = ssock.accept()
                        try:
                            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                        except (RuntimeError, OSError):
                            conn.close()
                    except socket.timeout:
                        continue
                    except OSError:
                        break

        if background:
            self._thread = threading.Thread(target=_serve, daemon=True)
            self._thread.start()
        else:
            _serve()

    def stop(self):
        """Stop the server."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=5)


class SyncClient:
    """TLS client that sends mycelium diffs to a remote server."""

    def __init__(self, host: str = "localhost", port: int = _DEFAULT_PORT,
                 cert_path: str = None, verify: bool = True):
        self.host = host
        self.port = port
        self.cert_path = cert_path
        self.verify = verify

    def _create_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = _TLS_MIN
        if self.cert_path:
            ctx.load_verify_locations(self.cert_path)
        if not self.verify:
            warnings.warn("verify=False disables TLS certificate validation", stacklevel=2)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _send(self, data: dict) -> dict:
        """Send a message and receive response."""
        ctx = self._create_context()
        hostname = self.host if self.verify else None
        with socket.create_connection((self.host, self.port), timeout=30) as raw:
            with ctx.wrap_socket(raw, server_hostname=hostname) as sock:
                _send_msg(sock, data)
                return _recv_msg(sock)

    def ping(self) -> dict:
        """Check server connectivity."""
        return self._send({"action": "ping"})

    def push(self, connections: list, repo_name: str, zone: str = None) -> dict:
        """Push local connections to remote meta-mycelium."""
        return self._send({
            "action": "push",
            "connections": connections,
            "repo": repo_name,
            "zone": zone or repo_name,
        })

    def pull(self, concepts: list, max_pull: int = 1000) -> dict:
        """Pull connections for specific concepts from remote."""
        return self._send({
            "action": "pull",
            "concepts": concepts,
            "max_pull": max_pull,
        })


# ── T2: TLSBackend ──────────────────────────────────────────────

class TLSBackend:
    """T2: SyncBackend implementation that delegates to SyncClient.

    Implements the same push/pull/status interface as SharedFileBackend
    and GitBackend, but sends data over TLS to a remote SyncServer.
    """

    def __init__(self, host: str = "localhost", port: int = _DEFAULT_PORT,
                 cert_path: str = None, verify: bool = True,
                 client_cert: str = None, client_key: str = None):
        self.client = SyncClient(host=host, port=port,
                                 cert_path=cert_path, verify=verify)
        self.host = host
        self.port = port
        # T4: mTLS client cert
        self.client_cert = client_cert
        self.client_key = client_key

    def push(self, payload, local_db) -> int:
        """T2: Push local edges to remote server via TLS."""
        try:
            from mycelium_db import days_to_date
        except ImportError:
            from .mycelium_db import days_to_date

        connections = []
        if local_db is not None:
            for row in local_db._conn.execute(
                "SELECT a, b, count, first_seen, last_seen FROM edges"
            ):
                a_name = local_db._id_to_name.get(row[0])
                b_name = local_db._id_to_name.get(row[1])
                if not a_name or not b_name:
                    continue
                connections.append({
                    "a": a_name, "b": b_name,
                    "count": row[2], "first_seen": row[3], "last_seen": row[4],
                })

        result = self.client.push(
            connections,
            repo_name=getattr(payload, 'repo_name', 'unknown'),
            zone=getattr(payload, 'zone', None),
        )
        return result.get("merged", 0)

    def pull(self, local_db, query_concepts=None, max_pull=1000) -> int:
        """T2: Pull edges from remote server via TLS."""
        try:
            from mycelium_db import days_to_date
        except ImportError:
            from .mycelium_db import days_to_date

        concepts = query_concepts or []
        result = self.client.pull(concepts, max_pull=max_pull)

        if result.get("status") != "ok":
            return 0

        pulled = 0
        # Load tombstones
        local_tombstones = set()
        try:
            for ts in local_db.get_tombstones():
                local_tombstones.add((ts[0], ts[1]))
        except (sqlite3.Error, AttributeError):
            pass

        for conn in result.get("connections", []):
            a, b = conn["a"], conn["b"]
            a_key, b_key = min(a, b), max(a, b)
            if (a_key, b_key) in local_tombstones:
                continue
            if not local_db.has_connection(a, b):
                local_db.upsert_connection(
                    a, b, count=conn["count"],
                    first_seen=days_to_date(conn["first_seen"]),
                    last_seen=days_to_date(conn["last_seen"]),
                )
                pulled += 1

        # CHUNK 8: Also pull fusions from TLS server
        for fusion in result.get("fusions", []):
            a, b = fusion["a"], fusion["b"]
            if not local_db.has_fusion(a, b):
                a_id = local_db._get_or_create_concept(a)
                b_id = local_db._get_or_create_concept(b)
                local_db._conn.execute("""
                    INSERT OR IGNORE INTO fusions (a, b, form, strength, fused_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (a_id, b_id, fusion.get("form", f"{a}+{b}"),
                      fusion.get("strength", 1), fusion.get("fused_at", "")))
                pulled += 1

        local_db.commit()
        return pulled

    def status(self) -> dict:
        """T2: Return TLS backend status."""
        result = {
            "type": "tls",
            "host": self.host,
            "port": self.port,
        }
        try:
            pong = self.client.ping()
            result["connected"] = pong.get("status") == "pong"
            result["server_version"] = pong.get("version")
        except (OSError, ssl.SSLError, ConnectionError) as e:
            result["connected"] = False
            result["error"] = str(e)
        return result


# ── T3: Server CLI ───────────────────────────────────────────────

def serve_cli():
    """T3: CLI entrypoint — python sync_tls.py serve --port 9477."""
    import argparse
    parser = argparse.ArgumentParser(description="Muninn Sync TLS Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT, help="Port (default 9477)")
    parser.add_argument("--cert", required=True, help="TLS certificate path")
    parser.add_argument("--key", required=True, help="TLS private key path")
    parser.add_argument("--meta-db", default=str(Path.home() / ".muninn" / "meta_mycelium.db"),
                        help="Meta-mycelium DB path")
    parser.add_argument("--ca", help="CA cert for mTLS client verification")
    parser.add_argument("--require-client-cert", action="store_true",
                        help="Require client certificate (mTLS)")
    parser.add_argument("--allowed-users", nargs="*",
                        help="T4: Allowed certificate CNs")
    parser.add_argument("--generate-certs", help="Generate self-signed certs in this directory")
    args = parser.parse_args()

    if args.generate_certs:
        certs = generate_certs(Path(args.generate_certs))
        print(f"Generated: {certs['cert_path']}, {certs['key_path']}")
        return

    server = SyncServer(
        cert_path=args.cert, key_path=args.key,
        meta_db_path=args.meta_db,
        host=args.host, port=args.port,
        ca_path=args.ca,
        require_client_cert=args.require_client_cert,
        allowed_users=args.allowed_users,
    )
    print(f"Muninn Sync Server listening on {args.host}:{args.port}")
    server.start(background=False)


if __name__ == "__main__":
    serve_cli()
