"""
CHUNK MCP C.0 — Auto-calibration adaptive du dual-mycelium threshold per-client.

Demande explicite Sky (2026-05-11 nuit) : « je veux pas calibrer pour moi, je
veux un système qui se calibre en fonction de chaque client et que tout
soit clean et en production ». Le THRESHOLD_LOCAL_STRONG=4.0 actuel est un
default théorique (11 sources convergent vers 40 % du max). On veut maintenant
qu'il s'auto-ajuste sur les VRAIES données de l'utilisateur.

Architecture :
- Chaque appel `mycelium_recall(scope=auto)` log `strength_local` dans
  `<repo>/.muninn/dual_mycelium_calibration.jsonl` (fire-and-forget,
  jamais raise).
- Toutes les `CALIBRATION_RECOMPUTE_EVERY` lignes (par défaut 30), si on a
  au moins `CALIBRATION_MIN_SAMPLES` (par défaut 30), on calcule le
  quantile `CALIBRATION_PERCENTILE` (par défaut 75) et on écrit
  `<repo>/.muninn/dual_mycelium_threshold.json`.
- Au prochain appel, `_recall_dual_impl` lit ce JSON et utilise sa valeur
  au lieu du default.
- Opt-out via `MUNINN_DUAL_AUTO_CALIBRATE=0`.

Contracts :
- Fichiers calibration TOUS dans `<repo>/.muninn/` (gitignored).
- Aucune écriture dans le source repo de Muninn lui-même (RULE 1).
- Pas de raise si fichier corrompu / verrouillé / absent.
- Threshold calibré dans [0.5, 50.0] (garde-fou anti aberration).
- Si pas de fichier ou pas assez de samples → fallback default.

Tests (10 behavioural) :
1. _get_calibrated_threshold returns default when no file
2. _get_calibrated_threshold reads stored value when file exists
3. MUNINN_DUAL_AUTO_CALIBRATE=0 forces default even if file exists
4. _log_strength_to_calibration appends to jsonl
5. _log_strength_to_calibration is fire-and-forget (no raise on bad dir)
6. _recompute_calibration_if_needed writes threshold.json after N samples
7. _recompute_calibration_if_needed skips if not enough samples
8. _recall_dual_impl uses calibrated threshold when present
9. _recall_dual_impl logs strength on each scope=auto call
10. Threshold clamped to [0.5, 50.0] (no aberrations)
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))

mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


def _make_calib_repo(tmp_path):
    repo = tmp_path / "calib_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    return repo


# ── Threshold lookup ─────────────────────────────────────────


def test_get_calibrated_returns_default_when_no_file(tmp_path, monkeypatch):
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)
    t = server._get_calibrated_threshold(repo)
    assert t == server.THRESHOLD_LOCAL_STRONG


def test_get_calibrated_reads_stored_value(tmp_path, monkeypatch):
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    threshold_path.write_text(
        json.dumps({"threshold": 6.5, "samples": 30, "percentile": 75}),
        encoding="utf-8",
    )
    t = server._get_calibrated_threshold(repo)
    assert t == 6.5


def test_opt_out_env_var_forces_default(tmp_path, monkeypatch):
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "0")
    repo = _make_calib_repo(tmp_path)
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    threshold_path.write_text(
        json.dumps({"threshold": 99.9, "samples": 30, "percentile": 75}),
        encoding="utf-8",
    )
    t = server._get_calibrated_threshold(repo)
    # Opt-out: must use default, ignore the file
    assert t == server.THRESHOLD_LOCAL_STRONG


# ── Logger ───────────────────────────────────────────────────


def test_log_strength_appends_to_jsonl(tmp_path):
    from muninn.mcp import server
    repo = _make_calib_repo(tmp_path)
    server._log_strength_to_calibration(repo, 3.5)
    server._log_strength_to_calibration(repo, 4.2)
    log_path = repo / ".muninn" / "dual_mycelium_calibration.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    assert parsed[0]["strength"] == 3.5
    assert parsed[1]["strength"] == 4.2


def test_log_strength_fire_and_forget(tmp_path):
    """Bad dir → no raise (fail-safe contract for MCP tool path)."""
    from muninn.mcp import server
    # Pass a path that doesn't exist and can't be created
    bad_repo = Path("/dev/null/not_a_dir")
    # Must NOT raise
    server._log_strength_to_calibration(bad_repo, 3.5)


# ── Recompute ────────────────────────────────────────────────


def test_recompute_writes_threshold_after_min_samples(tmp_path):
    from muninn.mcp import server
    repo = _make_calib_repo(tmp_path)
    # Pre-populate with 30+ synthetic samples spanning [1.0, 10.0]
    log_path = repo / ".muninn" / "dual_mycelium_calibration.jsonl"
    samples = []
    for i in range(30):
        val = 1.0 + (i / 29.0) * 9.0  # 1.0 → 10.0 linearly
        samples.append(val)
        log_path.write_text(
            (log_path.read_text(encoding="utf-8") if log_path.exists() else "")
            + json.dumps({"timestamp": "2026-05-11", "strength": val}) + "\n",
            encoding="utf-8",
        )
    # Trigger recompute
    written = server._recompute_calibration_if_needed(repo, force=True)
    assert written is True
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    assert threshold_path.exists()
    data = json.loads(threshold_path.read_text(encoding="utf-8"))
    # p75 of linear [1, 10] ≈ 7.75
    assert 7.0 <= data["threshold"] <= 8.5, (
        f"p75 should be ~7.75, got {data['threshold']}"
    )
    assert data["samples"] == 30


def test_recompute_skips_if_not_enough_samples(tmp_path):
    from muninn.mcp import server
    repo = _make_calib_repo(tmp_path)
    log_path = repo / ".muninn" / "dual_mycelium_calibration.jsonl"
    # Only 5 samples — below MIN
    for i in range(5):
        log_path.write_text(
            (log_path.read_text(encoding="utf-8") if log_path.exists() else "")
            + json.dumps({"strength": 3.0 + i}) + "\n",
            encoding="utf-8",
        )
    written = server._recompute_calibration_if_needed(repo, force=True)
    assert written is False
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    assert not threshold_path.exists()


# ── Integration with _recall_dual_impl ──────────────────────


def test_recall_dual_uses_calibrated_threshold(tmp_path, monkeypatch):
    """When .muninn/dual_mycelium_threshold.json exists, _recall_dual_impl
    uses ITS value (not THRESHOLD_LOCAL_STRONG) for the auto-routing decision.
    """
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)
    # Set calibrated threshold to 99.0 (impossible to hit) → auto should
    # always fall through to merge with meta.
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    threshold_path.write_text(
        json.dumps({"threshold": 99.0, "samples": 30, "percentile": 75}),
        encoding="utf-8",
    )

    # Mock local + meta
    def fake_local(*a, **k):
        return {"query": "x", "results": [
            {"concept": "a", "activation": 5.0, "hops": 2}  # strength_local=5.0
        ], "elapsed_ms": 1.0, "source": "local", "repo_path": str(repo)}

    called = {"meta": 0}

    def spy_meta(*a, **k):
        called["meta"] += 1
        return {"query": "x", "results": [
            {"concept": "b", "activation": 0.5, "hops": 2}
        ], "elapsed_ms": 1.0, "source": "meta", "meta_path": "/tmp/fake"}

    monkeypatch.setattr(server, "_recall_local_impl", fake_local)
    monkeypatch.setattr(server, "_recall_meta_impl", spy_meta)

    r = server._recall_dual_impl(query="x", scope="auto", top_k=5,
                                   repo_path=str(repo))
    # With calibrated=99.0, strength_local=5.0 < 99 → should fallback to merge
    assert called["meta"] == 1
    assert "merged" in r["scope_used"] or "+" in r["source"]


def test_recall_dual_logs_strength_on_auto(tmp_path, monkeypatch):
    """Each scope=auto call must append one line to the calibration log."""
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)

    def fake_local(*a, **k):
        return {"query": "x", "results": [
            {"concept": "a", "activation": 3.0, "hops": 2}
        ], "elapsed_ms": 1.0, "source": "local", "repo_path": str(repo)}

    def fake_meta(*a, **k):
        return {"query": "x", "results": [], "elapsed_ms": 1.0,
                "source": "meta", "meta_path": "/tmp/x"}

    monkeypatch.setattr(server, "_recall_local_impl", fake_local)
    monkeypatch.setattr(server, "_recall_meta_impl", fake_meta)

    server._recall_dual_impl(query="x", scope="auto", top_k=5,
                              repo_path=str(repo))
    log_path = repo / ".muninn" / "dual_mycelium_calibration.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["strength"] == 3.0


# ── Safety ───────────────────────────────────────────────────


def test_threshold_clamped_to_safe_range(tmp_path, monkeypatch):
    """Calibrated threshold clamped to [0.5, 50.0] regardless of stored value."""
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)
    threshold_path = repo / ".muninn" / "dual_mycelium_threshold.json"
    # Aberrant value
    threshold_path.write_text(
        json.dumps({"threshold": 99999.0, "samples": 30, "percentile": 75}),
        encoding="utf-8",
    )
    t = server._get_calibrated_threshold(repo)
    assert 0.5 <= t <= 50.0, f"threshold not clamped: {t}"


def test_other_scopes_dont_log(tmp_path, monkeypatch):
    """Only scope=auto should log to the calibration jsonl.
    scope=local/meta/both should NOT pollute the calibration data.
    """
    from muninn.mcp import server
    monkeypatch.setenv("MUNINN_DUAL_AUTO_CALIBRATE", "1")
    repo = _make_calib_repo(tmp_path)

    def fake_local(*a, **k):
        return {"query": "x", "results": [], "elapsed_ms": 1.0,
                "source": "local", "repo_path": str(repo)}

    def fake_meta(*a, **k):
        return {"query": "x", "results": [], "elapsed_ms": 1.0,
                "source": "meta", "meta_path": "/tmp/x"}

    monkeypatch.setattr(server, "_recall_local_impl", fake_local)
    monkeypatch.setattr(server, "_recall_meta_impl", fake_meta)

    for scope in ("local", "meta", "both"):
        server._recall_dual_impl(query="x", scope=scope, top_k=5,
                                   repo_path=str(repo))
    log_path = repo / ".muninn" / "dual_mycelium_calibration.jsonl"
    assert not log_path.exists() or log_path.read_text(encoding="utf-8").strip() == ""
