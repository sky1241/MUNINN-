"""CHUNK P0bis — vault.py file permissions on init/lock/unlock/rekey.

Pre-fix: engine/core/vault.py wrote 15 sensitive files (salt, salt backup,
verify hash, ciphertext, ephemeral plaintext, rekey markers) using the
process umask. Default umask 022 → 0o644 (world-readable). On a multi-user
host this exposes:

  - vault.salt          → enables offline PBKDF2 brute-force
  - vault.verify        → confirms a candidate password derived the right key
  - foo.vault           → ciphertext for offline cryptanalysis
  - foo (post-unlock)   → plaintext exposed until next lock

Post-fix: every write_bytes/write_text site followed by secure_perms()
from _secrets.py — chmod 0o600 unconditionally.

Source: docs/BATTLE_PLAN_2026-05-09.md §P0bis-1
"""
import importlib
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _mode(p: Path) -> int:
    return p.stat().st_mode & 0o777


def _setup_vault(tmp_path: Path):
    """Create a tmp .muninn/ dir + Vault instance + a plaintext file matching
    _SENSITIVE_PATTERNS so that lock()/unlock() actually find it."""
    import vault as vault_mod
    importlib.reload(vault_mod)

    repo = tmp_path / "repo"
    muninn_dir = repo / ".muninn"
    muninn_dir.mkdir(parents=True)

    # Plaintext file matching one of vault._SENSITIVE_PATTERNS
    # (errors.json is a top-level file, simplest match)
    plain = muninn_dir / "errors.json"
    plain.write_text('{"super": "secret content"}')
    os.chmod(plain, 0o644)  # explicit 0644 — post-unlock should become 0600

    v = vault_mod.Vault(repo)
    return v, repo, muninn_dir, plain


# ── init ────────────────────────────────────────────────────


def test_vault_init_creates_salt_in_0600(tmp_path):
    """Vault.init() must produce salt + salt.bak + vault.verify all in 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    salt_path = muninn_dir / "vault.salt"
    salt_bak = muninn_dir / "vault.salt.bak"
    verify_path = muninn_dir / "vault.verify"

    assert salt_path.exists(), "salt not created"
    assert salt_bak.exists(), "salt backup not created"
    assert verify_path.exists(), "verify hash not created"

    assert _mode(salt_path) == 0o600, (
        f"vault.salt mode {oct(_mode(salt_path))}; expected 0o600 — "
        f"salt leak enables offline PBKDF2 brute-force"
    )
    assert _mode(salt_bak) == 0o600, (
        f"vault.salt.bak mode {oct(_mode(salt_bak))}; expected 0o600"
    )
    assert _mode(verify_path) == 0o600, (
        f"vault.verify mode {oct(_mode(verify_path))}; expected 0o600 — "
        f"verify hash confirms a candidate password derived the right key"
    )


# ── lock / unlock ─────────────────────────────────────────────


def test_vault_lock_creates_ciphertext_in_0600(tmp_path):
    """Vault.lock() must chmod the .vault ciphertext to 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    v.lock()

    ciphertext = muninn_dir / "errors.json.vault"
    assert ciphertext.exists(), "ciphertext not created"
    assert _mode(ciphertext) == 0o600, (
        f"foo.vault mode {oct(_mode(ciphertext))}; expected 0o600"
    )


def test_vault_unlock_creates_plaintext_in_0600(tmp_path):
    """Vault.unlock() must chmod the restored plaintext to 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    v.lock()
    v.unlock()

    restored = muninn_dir / "errors.json"
    assert restored.exists(), "plaintext not restored"
    assert _mode(restored) == 0o600, (
        f"restored plaintext mode {oct(_mode(restored))}; expected 0o600"
    )


# ── rekey ────────────────────────────────────────────────────


def test_vault_rekey_keeps_salt_and_verify_in_0600(tmp_path):
    """Vault.rekey() rewrites salt + verify with new password — must stay 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    v.lock()
    v.rekey("new_pass_42")

    salt_path = muninn_dir / "vault.salt"
    salt_bak = muninn_dir / "vault.salt.bak"
    verify_path = muninn_dir / "vault.verify"

    assert _mode(salt_path) == 0o600, (
        f"post-rekey vault.salt mode {oct(_mode(salt_path))}; expected 0o600"
    )
    assert _mode(salt_bak) == 0o600
    assert _mode(verify_path) == 0o600

    # Re-encrypted ciphertext must also be 0o600
    ciphertext = muninn_dir / "errors.json.vault"
    assert _mode(ciphertext) == 0o600, (
        f"post-rekey ciphertext mode {oct(_mode(ciphertext))}; expected 0o600"
    )


# ── encrypt_file / decrypt_file ─────────────────────────────


def test_vault_encrypt_file_creates_ciphertext_in_0600(tmp_path):
    """Vault.encrypt_file() must chmod the .vault file to 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    plain = repo / "single.txt"
    plain.write_text("one shot")
    out = v.encrypt_file(plain)

    assert out.exists()
    assert _mode(out) == 0o600


def test_vault_decrypt_file_creates_plaintext_in_0600(tmp_path):
    """Vault.decrypt_file() must chmod the restored plaintext to 0o600."""
    v, repo, muninn_dir, plain = _setup_vault(tmp_path)
    v.init("hunter2")

    plain = repo / "single.txt"
    plain.write_text("one shot")
    out = v.encrypt_file(plain)
    restored = v.decrypt_file(out)

    assert restored.exists()
    assert _mode(restored) == 0o600
