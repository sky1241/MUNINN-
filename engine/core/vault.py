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
import hashlib
import os
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
        Returns: {salt_path, key_derived}
        """
        if not self.muninn_dir.exists():
            raise FileNotFoundError(f".muninn/ not found in {self.repo}")

        salt = os.urandom(32)  # 256-bit random salt
        self.salt_path.write_bytes(salt)
        self._key = _derive_key(password, salt)
        return {"salt_path": str(self.salt_path), "key_derived": True}

    def load_key(self, password: str) -> bool:
        """Load key from password + stored salt. Returns True if salt exists."""
        if not self.salt_path.exists():
            return False
        salt = self.salt_path.read_bytes()
        self._key = _derive_key(password, salt)
        return True

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
            fp.unlink()  # Remove plaintext
            encrypted += 1

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
            plaintext = _decrypt_bytes(data, self._key)
            # Restore original path (strip .vault)
            orig_path = vp.with_suffix("")
            orig_path.write_bytes(plaintext)
            total_bytes += len(plaintext)
            vp.unlink()  # Remove encrypted
            decrypted += 1

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
        fp.unlink()
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
