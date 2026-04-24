"""Vault — AES-256 encryption at rest.

Tests:
  V1.1  Init creates salt file (32 bytes)
  V1.2  Encrypt + decrypt roundtrip preserves data exactly
  V1.3  Wrong password fails to decrypt (InvalidTag)
  V1.4  Lock/unlock cycle on a temp .muninn directory
  V1.5  is_locked() / is_initialized() state checks
  V1.6  PBKDF2: same password + salt = same key (deterministic)
  V1.7  CLI: lock + unlock without crash
"""
import sys, os, tempfile, subprocess
MUNINN_PY = os.path.join(os.path.dirname(__file__), "..", "engine", "core", "muninn.py")


def _make_repo(tmpdir):
    """Create a fake .muninn/ with test files."""
    from pathlib import Path
    repo = Path(tmpdir)
    muninn = repo / ".muninn"
    muninn.mkdir()
    (muninn / "tree").mkdir()
    (muninn / "sessions").mkdir()

    # Fake sensitive files
    (muninn / "tree" / "tree.json").write_text('{"nodes": {}}', encoding="utf-8")
    (muninn / "sessions" / "test.mn").write_text("F>some compressed data\nB>test line", encoding="utf-8")
    (muninn / "session_index.json").write_text("[]", encoding="utf-8")
    return repo


def test_v1_1_init_salt():
    """Init creates a 32-byte salt file"""
    from pathlib import Path
    from vault import Vault
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _make_repo(tmpdir)
        v = Vault(repo)
        result = v.init("test-password-123")
        assert v.salt_path.exists(), "V1.1 FAIL: salt file not created"
        salt = v.salt_path.read_bytes()
        assert len(salt) == 32, f"V1.1 FAIL: salt is {len(salt)} bytes, expected 32"
        assert result["key_derived"], "V1.1 FAIL: key not derived"
    print(f"  V1.1 PASS: salt created (32 bytes)")


def test_v1_2_roundtrip():
    """Encrypt then decrypt preserves data exactly"""
    from vault import _derive_key, _encrypt_bytes, _decrypt_bytes
    key = _derive_key("my-password", b"x" * 32)
    original = b"Hello Muninn! \x00\xff This is binary data with unicode: \xc3\xa9"
    ct = _encrypt_bytes(original, key)
    assert ct != original, "V1.2 FAIL: ciphertext same as plaintext"
    assert len(ct) > len(original), "V1.2 FAIL: ciphertext shorter than plaintext"
    pt = _decrypt_bytes(ct, key)
    assert pt == original, f"V1.2 FAIL: decrypted != original"
    print(f"  V1.2 PASS: roundtrip OK ({len(original)} bytes)")


def test_v1_3_wrong_password():
    """Wrong password raises InvalidTag"""
    from vault import _derive_key, _encrypt_bytes, _decrypt_bytes
    key1 = _derive_key("correct-password", b"s" * 32)
    key2 = _derive_key("wrong-password", b"s" * 32)
    ct = _encrypt_bytes(b"secret data", key1)
    try:
        _decrypt_bytes(ct, key2)
        assert False, "V1.3 FAIL: wrong password did not raise"
    except Exception as e:
        assert "tag" in str(e).lower() or "InvalidTag" in type(e).__name__, \
            f"V1.3 FAIL: unexpected error: {e}"
    print(f"  V1.3 PASS: wrong password rejected")


def test_v1_4_lock_unlock():
    """Full lock/unlock cycle preserves all files"""
    from pathlib import Path
    from vault import Vault
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _make_repo(tmpdir)
        muninn = repo / ".muninn"

        # Save original contents
        orig_tree = (muninn / "tree" / "tree.json").read_bytes()
        orig_mn = (muninn / "sessions" / "test.mn").read_bytes()

        v = Vault(repo)
        v.init("lock-test-pw")

        # Lock
        result = v.lock()
        assert result["encrypted"] >= 2, f"V1.4 FAIL: only {result['encrypted']} files encrypted"
        assert not (muninn / "tree" / "tree.json").exists(), "V1.4 FAIL: plaintext still exists"
        assert (muninn / "tree" / "tree.json.vault").exists(), "V1.4 FAIL: .vault file missing"

        # Unlock
        v2 = Vault(repo)
        v2.load_key("lock-test-pw")
        result2 = v2.unlock()
        assert result2["decrypted"] >= 2, f"V1.4 FAIL: only {result2['decrypted']} files decrypted"

        # Verify contents match
        assert (muninn / "tree" / "tree.json").read_bytes() == orig_tree, "V1.4 FAIL: tree.json corrupted"
        assert (muninn / "sessions" / "test.mn").read_bytes() == orig_mn, "V1.4 FAIL: test.mn corrupted"

    print(f"  V1.4 PASS: lock/unlock cycle OK ({result['encrypted']} files)")


def test_v1_5_state_checks():
    """is_locked() and is_initialized() return correct state"""
    from pathlib import Path
    from vault import Vault
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _make_repo(tmpdir)
        v = Vault(repo)

        assert not v.is_initialized(), "V1.5 FAIL: should not be initialized"
        assert not v.is_locked(), "V1.5 FAIL: should not be locked"

        v.init("state-test")
        assert v.is_initialized(), "V1.5 FAIL: should be initialized after init"
        assert not v.is_locked(), "V1.5 FAIL: should not be locked after init"

        v.lock()
        assert v.is_locked(), "V1.5 FAIL: should be locked after lock"

        v.unlock()
        assert not v.is_locked(), "V1.5 FAIL: should not be locked after unlock"

    print(f"  V1.5 PASS: state checks correct")


def test_v1_6_pbkdf2_deterministic():
    """Same password + salt always produces same key"""
    from vault import _derive_key
    salt = b"fixed-salt-for-test-1234567890ab"
    k1 = _derive_key("my-password", salt)
    k2 = _derive_key("my-password", salt)
    k3 = _derive_key("different-pw", salt)
    assert k1 == k2, "V1.6 FAIL: same input different key"
    assert k1 != k3, "V1.6 FAIL: different password same key"
    assert len(k1) == 32, f"V1.6 FAIL: key is {len(k1)} bytes, expected 32"
    print(f"  V1.6 PASS: PBKDF2 deterministic (256-bit key)")


def test_v1_7_cli():
    """CLI lock + unlock runs without crash"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        repo = _make_repo(tmpdir)

        # Lock
        result = subprocess.run(
            [sys.executable, MUNINN_PY, "lock", "--password", "cli-test-pw", "--repo", str(repo)],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        assert result.returncode == 0, f"V1.7 FAIL lock: exit {result.returncode}\n{result.stderr}"
        assert "LOCKED" in result.stdout, f"V1.7 FAIL: no LOCKED in output\n{result.stdout}"

        # Unlock
        result2 = subprocess.run(
            [sys.executable, MUNINN_PY, "unlock", "--password", "cli-test-pw", "--repo", str(repo)],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.join(os.path.dirname(__file__), "..")
        )
        assert result2.returncode == 0, f"V1.7 FAIL unlock: exit {result2.returncode}\n{result2.stderr}"
        assert "UNLOCKED" in result2.stdout, f"V1.7 FAIL: no UNLOCKED in output\n{result2.stdout}"

    print(f"  V1.7 PASS: CLI lock + unlock clean")


if __name__ == "__main__":
    print("=== VAULT TESTS ===")
    test_v1_1_init_salt()
    test_v1_2_roundtrip()
    test_v1_3_wrong_password()
    test_v1_4_lock_unlock()
    test_v1_5_state_checks()
    test_v1_6_pbkdf2_deterministic()
    test_v1_7_cli()
    print("\n  ALL PASS")
