"""Sync TLS — encrypted network transport for meta-mycelium.

Tests:
  T1.1  generate_certs creates valid cert + key files
  T1.2  Server starts and stops cleanly
  T1.3  Client ping gets pong response over TLS
  T1.4  Client push sends connections, server acknowledges
  T1.5  Client pull requests concepts, server responds
  T1.6  TLS enforced: plain socket rejected
  T1.7  Message protocol: send/recv roundtrip
"""
import sys, os, tempfile, time, socket, ssl
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))


def test_t1_1_generate_certs():
    """generate_certs creates cert + key files"""
    from pathlib import Path
    from sync_tls import generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        result = generate_certs(Path(tmpdir))
        cert = Path(result["cert_path"])
        key = Path(result["key_path"])
        assert cert.exists(), "T1.1 FAIL: cert not created"
        assert key.exists(), "T1.1 FAIL: key not created"
        assert cert.stat().st_size > 500, "T1.1 FAIL: cert too small"
        assert key.stat().st_size > 500, "T1.1 FAIL: key too small"
        # Check PEM format
        cert_bytes = cert.read_bytes()
        assert b"BEGIN CERTIFICATE" in cert_bytes, "T1.1 FAIL: not PEM cert"
        assert b"BEGIN RSA PRIVATE KEY" in key.read_bytes(), "T1.1 FAIL: not PEM key"
        cert_size = len(cert_bytes)
    print(f"  T1.1 PASS: certs generated ({cert_size} bytes)")


def test_t1_2_server_lifecycle():
    """Server starts in background and stops cleanly"""
    from pathlib import Path
    from sync_tls import SyncServer, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            port=0,  # We'll use a fixed test port
        )
        # Use a random available port
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        server.port = port
        server.start(background=True)
        time.sleep(0.3)
        assert server._running, "T1.2 FAIL: server not running"
        server.stop()
        assert not server._running, "T1.2 FAIL: server still running after stop"
    print(f"  T1.2 PASS: server lifecycle OK (port {port})")


def test_t1_3_ping_pong():
    """Client ping gets pong over TLS"""
    from pathlib import Path
    from sync_tls import SyncServer, SyncClient, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        # Find free port
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            client = SyncClient(
                host="localhost",
                port=port,
                cert_path=certs["cert_path"],
                verify=False,  # Self-signed cert
            )
            result = client.ping()
            assert result["status"] == "pong", f"T1.3 FAIL: expected pong, got {result}"
            assert "version" in result, "T1.3 FAIL: no version in pong"
        finally:
            server.stop()
    print(f"  T1.3 PASS: ping/pong over TLS (v{result['version']})")


def test_t1_4_push():
    """Client push sends connections"""
    from pathlib import Path
    from sync_tls import SyncServer, SyncClient, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            client = SyncClient(host="localhost", port=port,
                                cert_path=certs["cert_path"], verify=False)
            conns = [{"a": "compression", "b": "mycelium", "count": 42}]
            result = client.push(conns, repo_name="test-repo")
            assert result["status"] == "ok", f"T1.4 FAIL: {result}"
            assert result["merged"] == 1, f"T1.4 FAIL: merged={result['merged']}"
        finally:
            server.stop()
    print(f"  T1.4 PASS: push OK ({result['merged']} connections)")


def test_t1_5_pull():
    """Client pull requests concepts"""
    from pathlib import Path
    from sync_tls import SyncServer, SyncClient, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            client = SyncClient(host="localhost", port=port,
                                cert_path=certs["cert_path"], verify=False)
            result = client.pull(["compression", "mycelium"])
            assert result["status"] == "ok", f"T1.5 FAIL: {result}"
            assert "connections" in result, "T1.5 FAIL: no connections in response"
        finally:
            server.stop()
    print(f"  T1.5 PASS: pull OK (count={result['count']})")


def test_t1_6_tls_enforced():
    """Plain TCP connection rejected by TLS server"""
    from pathlib import Path
    from sync_tls import SyncServer, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            # Try plain TCP (no TLS)
            raw = socket.create_connection(("127.0.0.1", port), timeout=5)
            raw.sendall(b"plain text hello")
            time.sleep(0.5)
            # Server should reject or close — either way, no valid response
            try:
                data = raw.recv(1024)
                # If we get data, it should be garbage (TLS alert) or empty
                # Either way, it's not a valid JSON response
                if data:
                    assert not data.startswith(b'{"status"'), "T1.6 FAIL: server accepted plain TCP"
            except (ConnectionResetError, ConnectionAbortedError, socket.timeout):
                pass  # Expected: server drops plain connection
            raw.close()
        finally:
            server.stop()
    print(f"  T1.6 PASS: plain TCP rejected by TLS server")


def test_t1_7_protocol():
    """Message protocol send/recv roundtrip"""
    from sync_tls import _send_msg, _recv_msg
    import io

    # Create a socket pair for testing
    s1, s2 = socket.socketpair()
    try:
        test_data = {"action": "test", "payload": "hello muninn", "count": 42}
        _send_msg(s1, test_data)
        received = _recv_msg(s2)
        assert received == test_data, f"T1.7 FAIL: {received} != {test_data}"
    finally:
        s1.close()
        s2.close()
    print(f"  T1.7 PASS: protocol roundtrip OK")


def test_t1_8_rate_limiter():
    """Rate limiter blocks after max requests"""
    from sync_tls import RateLimiter
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("1.2.3.4"), "T1.8 FAIL: first request denied"
    assert limiter.allow("1.2.3.4"), "T1.8 FAIL: second request denied"
    assert limiter.allow("1.2.3.4"), "T1.8 FAIL: third request denied"
    assert not limiter.allow("1.2.3.4"), "T1.8 FAIL: fourth request should be blocked"
    # Different IP should still be allowed
    assert limiter.allow("5.6.7.8"), "T1.8 FAIL: different IP should be allowed"
    print(f"  T1.8 PASS: rate limiter blocks after max (3/min)")


def test_t1_9_rate_limit_server():
    """Server rate-limits excessive requests from same client"""
    from pathlib import Path
    from sync_tls import SyncServer, SyncClient, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir))
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        # Server with very low rate limit (3/min)
        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
            max_requests_per_min=3,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            client = SyncClient(host="localhost", port=port,
                                cert_path=certs["cert_path"], verify=False)
            # First 3 should succeed
            for i in range(3):
                r = client.ping()
                assert r["status"] == "pong", f"T1.9 FAIL: request {i+1} failed: {r}"

            # 4th should be rate limited
            r = client.ping()
            assert r["status"] == "error", f"T1.9 FAIL: 4th request should be rate-limited: {r}"
            assert "rate_limited" in r.get("message", ""), f"T1.9 FAIL: wrong error: {r}"
        finally:
            server.stop()
    print(f"  T1.9 PASS: server rate limiting works (3/min)")


def test_t1_10_mtls():
    """mTLS: server requires client cert, rejects unauthenticated"""
    from pathlib import Path
    from sync_tls import SyncServer, SyncClient, generate_certs
    with tempfile.TemporaryDirectory() as tmpdir:
        certs = generate_certs(Path(tmpdir), cn="muninn-ca")
        import socket as _s
        with _s.socket(_s.AF_INET, _s.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

        # Server with mTLS enabled (uses same cert as CA for self-signed)
        server = SyncServer(
            cert_path=certs["cert_path"],
            key_path=certs["key_path"],
            meta_db_path=str(Path(tmpdir) / "meta.db"),
            host="127.0.0.1",
            port=port,
            ca_path=certs["cert_path"],
            require_client_cert=True,
        )
        server.start(background=True)
        time.sleep(0.5)

        try:
            # Client WITHOUT client cert — should fail
            client_no_cert = SyncClient(host="localhost", port=port, verify=False)
            try:
                r = client_no_cert.ping()
                # If we get here, mTLS is not enforced (fail)
                assert False, f"T1.10 FAIL: server accepted client without cert: {r}"
            except (ConnectionError, OSError, ssl.SSLError):
                pass  # Expected: server rejects
        finally:
            server.stop()
    print(f"  T1.10 PASS: mTLS rejects unauthenticated client")


if __name__ == "__main__":
    print("=== SYNC TLS TESTS ===")
    test_t1_1_generate_certs()
    test_t1_2_server_lifecycle()
    test_t1_3_ping_pong()
    test_t1_4_push()
    test_t1_5_pull()
    test_t1_6_tls_enforced()
    test_t1_7_protocol()
    test_t1_8_rate_limiter()
    test_t1_9_rate_limit_server()
    test_t1_10_mtls()
    print("\n  ALL PASS")
