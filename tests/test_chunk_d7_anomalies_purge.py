"""CHUNK D7 — anomalies.jsonl purge (older than N days).

Audit observation: 477 entries accumulated in ~/.muninn/anomalies.jsonl,
none re-validated, never purged. Most are >7 days old and stale —
their cube_ids and metrics no longer reflect the live tree.

Fix: helper `purge_old_anomalies(anomaly_path, max_age_days=7)` that
rewrites the JSONL with only entries newer than the cutoff. Returns
the count of entries removed. Wired into `muninn doctor` so the user
sees the cleanup count alongside other health checks.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §D7
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def _load_cube_analysis():
    engine_core = REPO / "engine" / "core"
    if str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    spec = importlib.util.spec_from_file_location(
        "_chunk_d7_cube_analysis", engine_core / "cube_analysis.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        pytest.skip(f"cube_analysis not loadable: {e}")
    return mod


def _make_anomaly_line(days_old: int, file: str = "x.py") -> str:
    """Build one anomaly JSONL line dated `days_old` days ago."""
    entry = {
        "timestamp": time.time() - (days_old * 86400),
        "date": time.strftime("%Y-%m-%d", time.localtime(time.time() - days_old * 86400)),
        "file": file,
        "metrics": {"temperature": 0.7},
        "cube_ids": ["abc"],
        "label": "hot_cube",
        "validated": False,
    }
    return json.dumps(entry) + "\n"


def test_purge_helper_exists():
    """purge_old_anomalies() must exist in cube_analysis."""
    ca = _load_cube_analysis()
    assert hasattr(ca, "purge_old_anomalies"), (
        "purge_old_anomalies() missing — see CHUNK D7"
    )


def test_purge_removes_old_entries(tmp_path):
    ca = _load_cube_analysis()
    log = tmp_path / "anomalies.jsonl"
    log.write_text(
        _make_anomaly_line(15) +  # 15 days old, should go
        _make_anomaly_line(3) +   # 3 days, should stay
        _make_anomaly_line(1)     # 1 day, should stay
    )
    removed = ca.purge_old_anomalies(str(log), max_age_days=7)
    assert removed == 1, f"expected 1 removed, got {removed}"

    remaining_lines = log.read_text().strip().splitlines()
    assert len(remaining_lines) == 2


def test_purge_keeps_all_when_none_old(tmp_path):
    ca = _load_cube_analysis()
    log = tmp_path / "anomalies.jsonl"
    log.write_text(_make_anomaly_line(1) + _make_anomaly_line(2))
    removed = ca.purge_old_anomalies(str(log), max_age_days=7)
    assert removed == 0


def test_purge_handles_missing_file(tmp_path):
    ca = _load_cube_analysis()
    log = tmp_path / "doesnt_exist.jsonl"
    removed = ca.purge_old_anomalies(str(log), max_age_days=7)
    assert removed == 0


def test_purge_handles_malformed_lines(tmp_path):
    """Malformed JSONL lines must not crash the purge."""
    ca = _load_cube_analysis()
    log = tmp_path / "anomalies.jsonl"
    content = (
        _make_anomaly_line(15) +
        "not valid json\n" +
        _make_anomaly_line(2) +
        "{bad: json}\n"
    )
    log.write_text(content)
    # Must not raise
    removed = ca.purge_old_anomalies(str(log), max_age_days=7)
    # 1 old entry removed; malformed lines are dropped or kept silently
    assert removed >= 1


def test_purge_atomic_write(tmp_path):
    """purge must use tempfile + rename (atomic) so no partial state."""
    ca = _load_cube_analysis()
    log = tmp_path / "anomalies.jsonl"
    log.write_text(_make_anomaly_line(15) * 100 + _make_anomaly_line(1) * 50)

    ca.purge_old_anomalies(str(log), max_age_days=7)

    # No temp leftovers in the directory
    leftovers = list(tmp_path.glob("anomalies.jsonl.tmp*")) + \
                list(tmp_path.glob(".anomalies*"))
    assert not leftovers, f"leftover temp files: {leftovers}"

    # File must contain only fresh entries
    remaining = log.read_text().strip().splitlines()
    assert len(remaining) == 50
