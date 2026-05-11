"""
CHUNK MCP A.2 — SessionEnd auto-sync meta with timeout + opt-out + doctor marker.

Le SessionEnd hook (deja registered, pointe vers `muninn.py feed`) appelle
deja `sync_to_meta()` depuis 2026-03-06 (commit b7c3803). Le gap A.2 est
de fournir des garde-fous :
  - timeout borne (la sync sur 230k edges peut depasser 180s)
  - opt-out propre (MUNINN_SKIP_META_SYNC=1)
  - marker observable pour `muninn doctor` (.muninn/last_meta_sync.json)
  - signal d'erreur (sync echoue silencieusement aujourd'hui)

Le wrapper `_sync_to_meta_guarded(repo_path, hook_event, budget_seconds)`
livre ces 4 garanties et remplace les 3 blocs inline `try: sync_to_meta()`
dans muninn_feed.py (feed_from_hook, feed_from_stop_hook) et muninn.py
(direct-file feed).

Tests behaviouraux (pas source-greppy) :
1. _sync_to_meta_guarded existe et a la bonne signature
2. Honor MUNINN_SKIP_META_SYNC=1 -> status=skipped
3. Returns status=ok sur sync reussie (mocked)
4. Returns status=error sur exception interne (pas de raise)
5. Returns status=timeout quand budget depasse
6. Ecrit .muninn/last_meta_sync.json a chaque call (succes ou echec)
7. Idempotent : 2 calls successifs OK
"""
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))


# ── Helper signature ─────────────────────────────────────────


def test_sync_to_meta_guarded_exists():
    """Le helper doit etre exporte depuis muninn_feed."""
    import muninn_feed
    assert hasattr(muninn_feed, "_sync_to_meta_guarded"), (
        "muninn_feed._sync_to_meta_guarded missing"
    )


def test_sync_to_meta_guarded_signature():
    """Signature : (repo_path: Path, hook_event: str, budget_seconds: float=...) -> dict."""
    import inspect
    import muninn_feed
    sig = inspect.signature(muninn_feed._sync_to_meta_guarded)
    params = list(sig.parameters.keys())
    assert "repo_path" in params
    assert "hook_event" in params
    assert "budget_seconds" in params


# ── Behavioural tests ────────────────────────────────────────


def _make_tmp_repo(tmp_path):
    """Create a minimal repo structure for the sync helper to operate on."""
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    return repo


def test_opt_out_via_env_var(tmp_path, monkeypatch):
    """MUNINN_SKIP_META_SYNC=1 -> early return status=skipped, no sync call."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.setenv("MUNINN_SKIP_META_SYNC", "1")

    import muninn_feed

    # Mock Mycelium.sync_to_meta to ensure it's NEVER called
    with patch("mycelium.Mycelium") as mock_myc:
        result = muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=10.0
        )

    assert isinstance(result, dict)
    assert result["status"] == "skipped"
    mock_myc.assert_not_called()


def test_status_ok_on_successful_sync(tmp_path, monkeypatch):
    """sync_to_meta returns 42 -> wrapper status=ok, pushed=42."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    mock_m = MagicMock()
    mock_m.sync_to_meta.return_value = 42
    mock_m.close = MagicMock()

    with patch("mycelium.Mycelium", return_value=mock_m):
        result = muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=10.0
        )

    assert result["status"] == "ok"
    assert result["pushed"] == 42
    assert "elapsed_s" in result


def test_status_error_on_exception(tmp_path, monkeypatch):
    """Exception inside sync -> wrapper catches, returns status=error, does NOT raise."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    mock_m = MagicMock()
    mock_m.sync_to_meta.side_effect = RuntimeError("boom")
    mock_m.close = MagicMock()

    with patch("mycelium.Mycelium", return_value=mock_m):
        # Must NOT raise
        result = muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=10.0
        )

    assert result["status"] == "error"
    assert "error" in result
    assert "boom" in str(result["error"])


def test_status_timeout_when_sync_too_slow(tmp_path, monkeypatch):
    """sync sleeps > budget_seconds -> wrapper returns status=timeout."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    def slow_sync():
        time.sleep(3.0)  # longer than budget
        return 99

    mock_m = MagicMock()
    mock_m.sync_to_meta.side_effect = slow_sync
    mock_m.close = MagicMock()

    start = time.time()
    with patch("mycelium.Mycelium", return_value=mock_m):
        result = muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=0.5
        )
    elapsed = time.time() - start

    assert result["status"] == "timeout"
    # Wrapper must return within ~budget (some slack for thread overhead)
    assert elapsed < 2.5, f"wrapper waited too long: {elapsed:.2f}s"


def test_marker_file_written_on_success(tmp_path, monkeypatch):
    """After successful sync, .muninn/last_meta_sync.json must exist with metadata."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    mock_m = MagicMock()
    mock_m.sync_to_meta.return_value = 7
    mock_m.close = MagicMock()

    with patch("mycelium.Mycelium", return_value=mock_m):
        muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=10.0
        )

    marker = repo / ".muninn" / "last_meta_sync.json"
    assert marker.exists(), "marker file not written"
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["pushed"] == 7
    assert "timestamp" in data
    assert "hook_event" in data
    assert data["hook_event"] == "SessionEnd"


def test_marker_file_written_on_error(tmp_path, monkeypatch):
    """Marker MUST be written even when sync fails — doctor needs the signal."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    mock_m = MagicMock()
    mock_m.sync_to_meta.side_effect = ValueError("nope")
    mock_m.close = MagicMock()

    with patch("mycelium.Mycelium", return_value=mock_m):
        muninn_feed._sync_to_meta_guarded(
            repo, hook_event="SessionEnd", budget_seconds=10.0
        )

    marker = repo / ".muninn" / "last_meta_sync.json"
    assert marker.exists(), "marker not written on error"
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["status"] == "error"


def test_idempotent_two_calls_in_a_row(tmp_path, monkeypatch):
    """Calling the wrapper twice in a row doesn't crash and updates the marker."""
    repo = _make_tmp_repo(tmp_path)
    monkeypatch.delenv("MUNINN_SKIP_META_SYNC", raising=False)

    import muninn_feed

    mock_m = MagicMock()
    mock_m.sync_to_meta.side_effect = [3, 5]
    mock_m.close = MagicMock()

    with patch("mycelium.Mycelium", return_value=mock_m):
        r1 = muninn_feed._sync_to_meta_guarded(repo, "SessionEnd", 10.0)
        r2 = muninn_feed._sync_to_meta_guarded(repo, "SessionEnd", 10.0)

    assert r1["status"] == "ok" and r1["pushed"] == 3
    assert r2["status"] == "ok" and r2["pushed"] == 5
    marker = repo / ".muninn" / "last_meta_sync.json"
    data = json.loads(marker.read_text(encoding="utf-8"))
    # Marker reflects the LAST call
    assert data["pushed"] == 5
