#!/usr/bin/env python3
"""Muninn scrub/purge — extracted from muninn.py during chunk C.1 split.

Owns:
  - _SCRUB_EXTENSIONS / _TRIGGER_VALUE_PATTERNS constants
  - scrub_secrets(target_path) — universal regex-based redaction
  - purge_secrets_db(repo) — sweep mycelium DBs to redact concept names
  - _handle_scrub_command(args) / _handle_purge_secrets_command(args)
    CLI handlers called from muninn.main().

Read-only of muninn package globals via `import muninn as _m` inside bodies.

Chunk C.1 of docs/BATTLE_PLAN_MASTER_MCP.md (2026-05-11 nuit).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from muninn_layers import _safe_path

_log = logging.getLogger(__name__)

# Shared secret regex patterns — _secrets.py is the single source of truth.
try:
    from _secrets import (
        _SECRET_PATTERNS,
        _COMPILED_PATTERNS as _COMPILED_SECRET_PATTERNS,
        redact_secrets_text as _redact_secrets_text,
        secure_perms,
    )
except ImportError:  # pragma: no cover
    from engine.core._secrets import (
        _SECRET_PATTERNS,
        _COMPILED_PATTERNS as _COMPILED_SECRET_PATTERNS,
        redact_secrets_text as _redact_secrets_text,
        secure_perms,
    )


_SCRUB_EXTENSIONS = {
    ".jsonl", ".json", ".md", ".mn", ".txt", ".log", ".csv",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".conf",
    ".py", ".js", ".ts", ".sh", ".bash", ".zsh", ".ps1",
}

# Trigger-word patterns: "clé xxx", "password xxx", etc. — redact the VALUE not the keyword
_TRIGGER_VALUE_PATTERNS = [
    re.compile(
        r'((?:cl[eé]|key|password|mdp|mot\s+de\s+passe|passwd|secret|token|passphrase'
        r'|api[_\-]?key|credentials?)\s*[=:\s]\s*)(\S+)',
        re.IGNORECASE
    ),
]


def scrub_secrets(target_path: Path, dry_run: bool = False) -> dict:
    """Scan files under target_path and redact secrets in-place.

    Works on any text file — JSONL, JSON, Markdown, logs, code, etc.
    Returns stats: {files_scanned, files_modified, secrets_found, errors}.
    """
    target = Path(target_path).resolve()
    stats = {"files_scanned": 0, "files_modified": 0, "secrets_found": 0, "errors": []}

    # Files that MUST NOT be scrubbed (auth, config, lock files)
    _SKIP_FILES = {
        ".credentials.json", "credentials.json", "settings.json",
        "settings.local.json", "config.json", ".env",
    }

    if target.is_file():
        if target.name in _SKIP_FILES:
            print(f"  SKIPPED (protected): {_safe_path(target)}")
            return stats
        files = [target]
    elif target.is_dir():
        files = []
        for root, _dirs, fnames in os.walk(target):
            # Skip .git, node_modules, __pycache__, .venv
            rp = Path(root)
            if any(p in rp.parts for p in (".git", "node_modules", "__pycache__", ".venv", "venv")):
                continue
            for fn in fnames:
                if fn in _SKIP_FILES:
                    continue
                fp = rp / fn
                if fp.suffix.lower() in _SCRUB_EXTENSIONS:
                    files.append(fp)
    else:
        stats["errors"].append(f"Path not found: {target}")
        return stats

    for fp in files:
        stats["files_scanned"] += 1
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            stats["errors"].append(f"{_safe_path(fp)}: {e}")
            continue

        modified = text
        file_hits = 0

        # 1. P10: Structural patterns (compiled) — redact entire match
        for cpat in _COMPILED_SECRET_PATTERNS:
            new, count = cpat.subn("[REDACTED]", modified)
            file_hits += count
            modified = new

        # 2. Trigger-word patterns — redact only the VALUE after the keyword
        for pat in _TRIGGER_VALUE_PATTERNS:
            def _redact_value(m):
                return m.group(1) + "[REDACTED]"
            new, count = pat.subn(_redact_value, modified)
            file_hits += count
            modified = new

        if file_hits > 0:
            stats["secrets_found"] += file_hits
            stats["files_modified"] += 1
            if not dry_run:
                fp.write_text(modified, encoding="utf-8")
            print(f"  {'[DRY-RUN] ' if dry_run else ''}SCRUBBED {_safe_path(fp)}: {file_hits} secret(s) redacted")

    return stats


# ── X1b: Purge secrets from mycelium databases ──────────────────

def purge_secrets_db(repo_path: Path = None):
    """X1b: Scan mycelium.db + meta_mycelium.db for secret concepts and delete them.

    Removes any concept whose name matches a secret pattern, along with
    all its edges, fusions, and edge_zones.
    """
    from mycelium_db import MyceliumDB

    total = 0

    # 1. Local mycelium.db
    local_db = (repo_path or Path(".")) / ".muninn" / "mycelium.db"
    if local_db.exists():
        db = MyceliumDB(local_db)
        n = db.purge_secret_concepts()
        total += n
        db.close()
        if n:
            print(f"  Purged {n} secret concept(s) from {local_db}")
        else:
            print(f"  No secrets found in {local_db}")

    # 2. Meta mycelium (cross-repo)
    meta_db = Path.home() / ".muninn" / "meta_mycelium.db"
    # Check config for custom meta_path
    config_path = Path.home() / ".muninn" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            mp = cfg.get("meta_path")
            if mp:
                meta_db = Path(mp) / "meta_mycelium.db"
        except Exception as exc:
            _log.warning("corrupt config.json at %s, skipping meta_path override: %s", config_path, exc)

    if meta_db.exists():
        db = MyceliumDB(meta_db)
        n = db.purge_secret_concepts()
        total += n
        db.close()
        if n:
            print(f"  Purged {n} secret concept(s) from {meta_db}")
        else:
            print(f"  No secrets found in {meta_db}")

    print(f"\n  Total purged: {total} concept(s)")
    return total


# ── F1a (2026-05-09): vault command handler ──────────────────────
# Extracted out of main() to keep the dispatcher under control. Behaviour
# unchanged — same _REPO_PATH global mutation, same getpass fallback,
# same exit codes.
def _handle_scrub_command(args) -> None:
    """Run secret-redaction over a target path. Dry-run unless --force.
    Reports files_scanned / files_modified / secrets_found / errors[]."""
    target = Path(args.file or ".").resolve()
    if not target.exists():
        print(f"ERROR: path not found: {target}", file=sys.stderr)
        sys.exit(1)
    dry = not args.force
    print("=== MUNINN SCRUB (dry-run) — use --force to apply ==="
          if dry else "=== MUNINN SCRUB ===")
    stats = scrub_secrets(target, dry_run=dry)
    print(f"\n  Scanned: {stats['files_scanned']} files")
    print(f"  Modified: {stats['files_modified']} files")
    print(f"  Secrets found: {stats['secrets_found']}")
    if stats["errors"]:
        print(f"  Errors: {len(stats['errors'])}")
        for e in stats["errors"][:5]:
            print(f"    {e}")
    if dry and stats["secrets_found"] > 0:
        print(f"\n  Run with --force to redact {stats['secrets_found']} secret(s)")


def _handle_purge_secrets_command(args) -> None:
    """Repo-wide secret scrub of mycelium databases (concept names + edges)."""
    repo = Path(args.file or ".").resolve()
    print("=== MUNINN PURGE-SECRETS — cleaning mycelium databases ===")
    purge_secrets_db(repo)

