"""
B-SCAN-12: Incremental Cache
=============================
Tracks file hashes to enable incremental scanning.
Only files that changed (or are new) since last scan get rescanned.

Storage: .muninn/scan_cache.json = {filepath: {sha256, last_scan_date, findings[]}}
Input: dict of {filepath: sha256_hash} from Cube or any SHA-256 source.
Output: DeltaResult with to_scan, unchanged, removed lists.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# --- Triple import fallback ---
try:
    from engine.core.scanner import _SCANNER_VERSION
except ImportError:
    try:
        from . import _SCANNER_VERSION
    except ImportError:
        _SCANNER_VERSION = None

_SCANNER_VERSION = "0.1.0"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclasses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ScanCacheEntry:
    sha256: str
    last_scan_date: str  # ISO format
    findings: list = field(default_factory=list)


@dataclass
class DeltaResult:
    to_scan: list = field(default_factory=list)       # files that changed or are new
    unchanged: list = field(default_factory=list)      # files that haven't changed
    removed: list = field(default_factory=list)        # files deleted since last scan
    is_first_run: bool = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cache I/O
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_cache(cache_path: str) -> dict:
    """Load scan cache from JSON file. Returns dict of {filepath: ScanCacheEntry}."""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    result = {}
    for filepath, entry_data in raw.items():
        result[filepath] = ScanCacheEntry(
            sha256=entry_data.get("sha256", ""),
            last_scan_date=entry_data.get("last_scan_date", ""),
            findings=entry_data.get("findings", []),
        )
    return result


def save_cache(cache_path: str, cache_data: dict) -> None:
    """Save scan cache to JSON file. cache_data = {filepath: ScanCacheEntry}."""
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    serialized = {}
    for filepath, entry in cache_data.items():
        if isinstance(entry, ScanCacheEntry):
            serialized[filepath] = asdict(entry)
        else:
            serialized[filepath] = entry
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Delta computation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def compute_delta(current_hashes: dict, cache_path: str) -> DeltaResult:
    """
    Compare current file hashes against cached hashes.

    Args:
        current_hashes: dict of {filepath: sha256_hash} from current scan
        cache_path: path to .muninn/scan_cache.json

    Returns:
        DeltaResult with to_scan, unchanged, removed lists
    """
    cache = load_cache(cache_path)

    if not cache:
        return DeltaResult(
            to_scan=sorted(current_hashes.keys()),
            unchanged=[],
            removed=[],
            is_first_run=True,
        )

    to_scan = []
    unchanged = []

    for filepath, sha256 in current_hashes.items():
        if filepath not in cache:
            # New file
            to_scan.append(filepath)
        elif cache[filepath].sha256 != sha256:
            # Modified file
            to_scan.append(filepath)
        else:
            # Unchanged
            unchanged.append(filepath)

    # Files in cache but not in current hashes = removed
    removed = [fp for fp in cache if fp not in current_hashes]

    return DeltaResult(
        to_scan=sorted(to_scan),
        unchanged=sorted(unchanged),
        removed=sorted(removed),
        is_first_run=False,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cache update
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def update_cache(cache_path: str, file_path: str, sha256: str, findings: list = None) -> None:
    """
    Update a single file's entry in the scan cache.

    Args:
        cache_path: path to scan_cache.json
        file_path: the scanned file
        sha256: current hash of the file
        findings: list of finding dicts (default empty)
    """
    cache = load_cache(cache_path)
    cache[file_path] = ScanCacheEntry(
        sha256=sha256,
        last_scan_date=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        findings=findings or [],
    )
    save_cache(cache_path, cache)
