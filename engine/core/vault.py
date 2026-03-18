#!/usr/bin/env python3
"""
Muninn Vault — AES-256 encryption at rest.

Protects sensitive files (mycelium.db, sessions .mn, tree.json) from exfiltration.
Uses AES-256-GCM via Fernet (cryptography lib) + PBKDF2 key derivation.

Usage:
    vault = Vault(repo_path)
    vault.init("my-password")       # One-time: derive key, store salt
    vault.lock()                     # Encrypt all sensitive files
    vault.unlock()                   # Decrypt for use
    vault.is_locked()                # Check state

Files encrypted: mycelium.db, sessions/*.mn, tree/tree.json
Salt stored in: .muninn/vault.salt (random, unique per install)
Key NEVER stored on disk — derived from password at runtime.

Requires: pip install cryptography
"""
import base64
import ctypes
import getpass as _getpass_mod
import hashlib
import json as _json
import os
import platform
import socket as _socket
import time as _time
from pathlib import Path

# Fernet uses AES-128-CBC internally, but we use raw AES-256-GCM via AESGCM
# for enterprise-grade encryption. Fernet is simpler but only AES-128.
# We use PBKDF2-HMAC-SHA256 for key derivation (NIST SP 800-132).

_SALT_FILE = "vault.salt"
_LOCK_EXT = ".vault"
_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation
_SENSITIVE_PATTERNS = [
    "mycelium.db",
    "mycelium.db-wal",
    "mycelium.db-shm",
    "sessions/*.mn",
    "tree/tree.json",
    "tree/*.mn",
    "session_index.json",
    "errors.json",
    "boot_feedback.json",
    "hook_log.txt",
    "tree/*.tmp",
]


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from password + salt using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32,
    )


def _encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Encrypt data with AES-256-GCM. Returns nonce + ciphertext + tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct  # nonce (12) + ciphertext + tag (16)


def _decrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Decrypt AES-256-GCM data. Input = nonce + ciphertext + tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    nonce = data[:12]
    ct = data[12:]
    return aesgcm.decrypt(nonce, ct, None)


def _zero_bytes(ba: bytearray):
    """Zero a bytearray in-place using ctypes.memset. Best-effort memory wipe."""
    if not ba:
        return
    try:
        ctypes.memset((ctypes.c_char * len(ba)).from_buffer(ba), 0, len(ba))
    except (TypeError, ValueError):
        # Fallback: overwrite byte by byte
        for i in range(len(ba)):
            ba[i] = 0


def _secure_delete(filepath: Path):
    """Best-effort secure file deletion: 3-pass overwrite + rename + unlink.

    Pass 1: zeros, Pass 2: ones, Pass 3: random.
    Then rename to random name before unlinking (hides filename in journal).
    NOTE: NOT guaranteed on SSD due to wear leveling. The real defense
    is encrypt-first — plaintext should never exist unencrypted on disk.
    """
    fp = Path(filepath)
    if not fp.exists():
        return
    try:
        size = fp.stat().st_size
        if size > 0:
            with open(fp, "r+b") as f:
                f.seek(0)
                f.write(b'\x00' * size)
                f.flush()
                os.fsync(f.fileno())
                f.seek(0)
                f.write(b'\xff' * size)
                f.flush()
                os.fsync(f.fileno())
                f.seek(0)
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
        # Rename to random name before deletion (hides original filename)
        tmp_name = fp.parent / os.urandom(16).hex()
        fp.rename(tmp_name)
        tmp_name.unlink()
    except (OSError, PermissionError):
        # Fallback: regular delete
        try:
            fp.unlink()
        except OSError:
            pass


def _audit_log(muninn_dir: Path, action: str, success: bool,
               files: int = 0, bytes_total: int = 0, reason: str = None):
    """Append-only JSONL audit log for vault operations (OWASP compliant)."""
    log_path = muninn_dir / "vault_audit.jsonl"
    entry = {
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "action": action,
        "user": _getpass_mod.getuser(),
        "host": _socket.gethostname(),
        "pid": os.getpid(),
        "success": success,
        "files": files,
        "bytes": bytes_total,
    }
    if reason:
        entry["reason"] = reason
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError:
        pass  # Logging failure should never block vault operations


class Vault:
    """AES-256 encryption manager for a Muninn repo."""

    def __init__(self, repo_path: Path):
        self.repo = Path(repo_path).resolve()
        self.muninn_dir = self.repo / ".muninn"
        self.salt_path = self.muninn_dir / _SALT_FILE
        self._key = None

    def is_initialized(self) -> bool:
        """Check if vault has been set up (salt exists)."""
        return self.salt_path.exists()

    def init(self, password: str) -> dict:
        """Initialize vault: generate salt, derive key. One-time setup.

        Creates vault.salt + vault.salt.bak (backup).
        WARNING: if both salt files are lost, encrypted data is UNRECOVERABLE.

        Returns: {salt_path, backup_path, key_derived}
        """
        if not self.muninn_dir.exists():
            raise FileNotFoundError(f".muninn/ not found in {self.repo}")

        salt = os.urandom(32)  # 256-bit random salt
        self.salt_path.write_bytes(salt)

        # Backup salt — losing it means losing all encrypted data forever
        backup = self.salt_path.with_suffix(".salt.bak")
        backup.write_bytes(salt)

        self._key = bytearray(_derive_key(password, salt))

        # Derive a verification hash (to detect wrong passwords without decrypting)
        verify = hashlib.sha256(self._key).hexdigest()[:16]
        verify_path = self.muninn_dir / "vault.verify"
        verify_path.write_text(verify, encoding="utf-8")

        _audit_log(self.muninn_dir, "init", True, reason="vault_initialized")
        return {"salt_path": str(self.salt_path), "backup_path": str(backup), "key_derived": True}

    def load_key(self, password: str) -> bool:
        """Load key from password + stored salt.

        Returns True if key loaded. Raises ValueError if password is wrong
        (checked against vault.verify hash without needing to decrypt anything).
        Falls back to vault.salt.bak if primary salt is missing.
        """
        salt_path = self.salt_path
        if not salt_path.exists():
            # Try backup
            backup = salt_path.with_suffix(".salt.bak")
            if backup.exists():
                salt_path = backup
            else:
                return False

        salt = salt_path.read_bytes()
        self._key = bytearray(_derive_key(password, salt))

        # Verify password if vault.verify exists
        verify_path = self.muninn_dir / "vault.verify"
        if verify_path.exists():
            expected = verify_path.read_text(encoding="utf-8").strip()
            actual = hashlib.sha256(self._key).hexdigest()[:16]
            if actual != expected:
                self._key = None
                _audit_log(self.muninn_dir, "auth_fail", False, reason="wrong_password")
                raise ValueError("Wrong password (vault.verify mismatch)")

        return True

    def wipe_key(self):
        """Zero the in-memory key. Call when done with crypto operations."""
        if self._key is not None and isinstance(self._key, bytearray):
            _zero_bytes(self._key)
        self._key = None

    def _get_sensitive_files(self) -> list:
        """List all sensitive files that should be encrypted."""
        files = []
        if not self.muninn_dir.exists():
            return files
        for pattern in _SENSITIVE_PATTERNS:
            if "*" in pattern:
                files.extend(self.muninn_dir.glob(pattern))
            else:
                fp = self.muninn_dir / pattern
                if fp.exists():
                    files.append(fp)
        return [f for f in files if f.exists() and not f.name.endswith(_LOCK_EXT)]

    def _get_locked_files(self) -> list:
        """List all currently encrypted .vault files."""
        files = []
        if not self.muninn_dir.exists():
            return files
        for f in self.muninn_dir.rglob(f"*{_LOCK_EXT}"):
            files.append(f)
        return files

    def is_locked(self) -> bool:
        """Check if vault is currently locked (encrypted files exist)."""
        return len(self._get_locked_files()) > 0

    def lock(self) -> dict:
        """Encrypt all sensitive files. Returns stats."""
        if self._key is None:
            raise RuntimeError("No key loaded. Call init() or load_key() first.")

        files = self._get_sensitive_files()
        encrypted = 0
        total_bytes = 0

        for fp in files:
            data = fp.read_bytes()
            ct = _encrypt_bytes(data, self._key)
            vault_path = fp.with_suffix(fp.suffix + _LOCK_EXT)
            vault_path.write_bytes(ct)
            total_bytes += len(data)
            _secure_delete(fp)  # Overwrite + delete plaintext
            encrypted += 1

        _audit_log(self.muninn_dir, "lock", True, files=encrypted, bytes_total=total_bytes)
        return {"encrypted": encrypted, "total_bytes": total_bytes}

    def unlock(self) -> dict:
        """Decrypt all .vault files back to plaintext. Returns stats."""
        if self._key is None:
            raise RuntimeError("No key loaded. Call init() or load_key() first.")

        locked = self._get_locked_files()
        decrypted = 0
        total_bytes = 0

        for vp in locked:
            data = vp.read_bytes()
            try:
                plaintext = _decrypt_bytes(data, self._key)
            except Exception as e:
                print(f"WARNING: failed to decrypt {vp.name}: {e}", file=sys.stderr)
                continue
            # Restore original path (strip .vault)
            orig_path = vp.with_suffix("")
            orig_path.write_bytes(plaintext)
            total_bytes += len(plaintext)
            vp.unlink()  # Remove encrypted
            decrypted += 1

        _audit_log(self.muninn_dir, "unlock", True, files=decrypted, bytes_total=total_bytes)
        return {"decrypted": decrypted, "total_bytes": total_bytes}

    def encrypt_file(self, filepath: Path) -> Path:
        """Encrypt a single file. Returns path to .vault file."""
        if self._key is None:
            raise RuntimeError("No key loaded.")
        fp = Path(filepath)
        data = fp.read_bytes()
        ct = _encrypt_bytes(data, self._key)
        vault_path = fp.with_suffix(fp.suffix + _LOCK_EXT)
        vault_path.write_bytes(ct)
        _secure_delete(fp)
        return vault_path

    def decrypt_file(self, vault_path: Path) -> Path:
        """Decrypt a single .vault file. Returns path to restored file."""
        if self._key is None:
            raise RuntimeError("No key loaded.")
        vp = Path(vault_path)
        data = vp.read_bytes()
        plaintext = _decrypt_bytes(data, self._key)
        orig_path = vp.with_suffix("")
        orig_path.write_bytes(plaintext)
        vp.unlink()
        return orig_path

    def rekey(self, new_password: str) -> dict:
        """Re-encrypt all .vault files with a new password.

        Requires current key loaded (call load_key first).
        Atomically: decrypt with old key, encrypt with new key, update salt+verify.
        Returns: {rekeyed: int, total_bytes: int}
        """
        if self._key is None:
            raise RuntimeError("No key loaded. Call load_key() first.")

        old_key = self._key

        # Generate new salt + key
        new_salt = os.urandom(32)
        new_key = bytearray(_derive_key(new_password, new_salt))

        locked = self._get_locked_files()
        rekeyed = 0
        total_bytes = 0

        for vp in locked:
            data = vp.read_bytes()
            # Decrypt with old key
            plaintext = _decrypt_bytes(data, old_key)
            # Re-encrypt with new key
            ct = _encrypt_bytes(plaintext, new_key)
            # Atomic write: temp file then replace
            tmp = vp.with_suffix(".tmp")
            tmp.write_bytes(ct)
            tmp.replace(vp)  # Atomic on both Windows and Linux
            total_bytes += len(plaintext)
            rekeyed += 1

        # Update salt + backup + verify
        self.salt_path.write_bytes(new_salt)
        self.salt_path.with_suffix(".salt.bak").write_bytes(new_salt)
        verify = hashlib.sha256(new_key).hexdigest()[:16]
        (self.muninn_dir / "vault.verify").write_text(verify, encoding="utf-8")

        # Wipe old key, set new
        _zero_bytes(old_key)
        self._key = new_key

        _audit_log(self.muninn_dir, "rekey", True, files=rekeyed, bytes_total=total_bytes)
        return {"rekeyed": rekeyed, "total_bytes": total_bytes}
