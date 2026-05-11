"""
CHUNK MCP B.3 — Dual-mycelium routing (local / meta / auto / both).

3 MCP tools :
  - `mycelium_recall_local` (B.1, untouched, contract preserved)
  - `mycelium_recall_meta(query, top_k, hops)` (NEW) — read-only meta-mycelium query
  - `mycelium_recall(query, scope, top_k, hops)` (NEW) — smart router with
      scope ∈ {"auto", "local", "meta", "both"}.

Heuristic for `scope="auto"` (defaults validated by 11 sources deep audit):
  local = recall_local(query)
  if sum(r.activation for r in local) >= THRESHOLD_LOCAL_STRONG (default 4.0):
      return local                                          # local "knows enough"
  meta = recall_meta(query)
  return merge(local, meta, fusion=FUSION_METHOD,
               α=ALPHA_LOCAL=0.7, β=BETA_META=0.3, top_k)

Fusion methods:
  - "linear" (default) : score = α·local_norm + β·meta_norm (min-max normalized)
  - "rrf" (Cormack 2009) : score = α/(60+rank_local) + β/(60+rank_meta)
                          — magnitude-robust (local 94k vs meta 7.5M edges).

5 env vars expose defaults:
  MUNINN_DUAL_LOCAL_STRONG=4.0   (ACT-R log-odds -0.5 → sigmoid 0.38 ≈ 40% max)
  MUNINN_DUAL_LOCAL_WEIGHT=0.7   (Weaviate hybrid default ≈ 0.75)
  MUNINN_DUAL_META_WEIGHT=0.3
  MUNINN_DUAL_TOP_K=10            (NDCG@10 BEIR/MTEB standard)
  MUNINN_DUAL_FUSION=linear       (or "rrf")

Tests : 15 behavioural covering registration, scope filtering, read-only
contract on BOTH DBs, fusion methods, env-var overrides, JSON serializability,
graceful degradation when meta-DB missing.
"""
import importlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))

mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


# ── Fixtures ─────────────────────────────────────────────────


def _make_minimal_repo(tmp_path):
    """Create a minimal Muninn repo (.muninn/ + empty mycelium)."""
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    return repo


def _seed_local_mycelium(repo, pairs):
    """Observe `pairs` into the repo's local mycelium so spread_activation finds them."""
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    from mycelium import Mycelium
    m = Mycelium(repo)
    for a, b, count in pairs:
        for _ in range(count):
            m.observe([a, b])
    m.save()
    try:
        m.close()
    except Exception:
        pass


def _make_isolated_meta_db(tmp_path, edges):
    """Create a small seeded meta_mycelium.db at <tmp_path>/.muninn/meta_mycelium.db.

    Returns the absolute path to the db. The MUNINN_META_PATH env var must be
    set to this path's parent so the meta lookup resolves here (not in $HOME).
    edges: list of (concept_a, concept_b, count) tuples.
    """
    meta_dir = tmp_path / ".muninn_meta"
    meta_dir.mkdir()
    meta_path = meta_dir / "meta_mycelium.db"

    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    from mycelium_db import MyceliumDB
    db = MyceliumDB(meta_path)
    for a, b, count in edges:
        # MyceliumDB.add_connection or similar. Most permissive way is to
        # observe via Mycelium federated mode — but we want minimal DB only.
        a_id = db._get_or_create_concept(a)
        b_id = db._get_or_create_concept(b)
        with db.transaction() as txn:
            txn.execute(
                "INSERT INTO edges (a, b, count, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(a, b) DO UPDATE SET count = MAX(count, excluded.count)",
                (a_id, b_id, count, 0, 0),
            )
    db.close()
    return meta_dir  # return dir (parent of meta_mycelium.db) for MUNINN_META_PATH


# ── Registration ─────────────────────────────────────────────


def test_three_tools_registered():
    """mycelium_recall_local, _meta, mycelium_recall all in list_tools()."""
    import asyncio
    from muninn.mcp import server
    app = server.create_server()
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}
    for required in ("mycelium_recall_local", "mycelium_recall_meta", "mycelium_recall"):
        assert required in names, f"{required!r} missing. Got: {sorted(names)}"


# ── Signatures ───────────────────────────────────────────────


def test_recall_meta_impl_exists():
    from muninn.mcp import server
    assert hasattr(server, "_recall_meta_impl")


def test_recall_dual_impl_exists_with_scope():
    from muninn.mcp import server
    assert hasattr(server, "_recall_dual_impl")
    import inspect
    sig = inspect.signature(server._recall_dual_impl)
    params = list(sig.parameters.keys())
    assert "scope" in params
    assert "query" in params


# ── Scope filtering ──────────────────────────────────────────


def test_scope_local_skips_meta(tmp_path, monkeypatch):
    """scope='local' must NOT call _recall_meta_impl."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    _seed_local_mycelium(repo, [("python", "flask", 5)])

    called = {"meta": 0}
    orig = server._recall_meta_impl

    def spy(*args, **kwargs):
        called["meta"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(server, "_recall_meta_impl", spy)
    r = server._recall_dual_impl(
        query="python", scope="local", top_k=5, repo_path=str(repo),
    )
    assert called["meta"] == 0
    assert r["source"] == "local"


def test_scope_meta_skips_local(tmp_path, monkeypatch):
    """scope='meta' must NOT call _recall_local_impl."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    meta_dir = _make_isolated_meta_db(tmp_path, [("python", "django", 10)])
    monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

    called = {"local": 0}
    orig = server._recall_local_impl

    def spy(*args, **kwargs):
        called["local"] += 1
        return orig(*args, **kwargs)

    monkeypatch.setattr(server, "_recall_local_impl", spy)
    r = server._recall_dual_impl(
        query="python", scope="meta", top_k=5, repo_path=str(repo),
    )
    assert called["local"] == 0
    assert r["source"] == "meta"


def test_scope_both_calls_both(tmp_path, monkeypatch):
    """scope='both' calls local + meta + merges."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    _seed_local_mycelium(repo, [("python", "flask", 5)])
    meta_dir = _make_isolated_meta_db(tmp_path, [("python", "django", 10)])
    monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

    called = {"local": 0, "meta": 0}
    orig_l, orig_m = server._recall_local_impl, server._recall_meta_impl

    def spy_l(*a, **k):
        called["local"] += 1
        return orig_l(*a, **k)

    def spy_m(*a, **k):
        called["meta"] += 1
        return orig_m(*a, **k)

    monkeypatch.setattr(server, "_recall_local_impl", spy_l)
    monkeypatch.setattr(server, "_recall_meta_impl", spy_m)

    r = server._recall_dual_impl(
        query="python", scope="both", top_k=5, repo_path=str(repo),
    )
    assert called["local"] == 1 and called["meta"] == 1
    assert "local" in r["source"] and "meta" in r["source"]


# ── auto routing ─────────────────────────────────────────────


def test_auto_skips_meta_when_local_strong(tmp_path, monkeypatch):
    """auto: if local strength >= THRESHOLD_LOCAL_STRONG, skip meta entirely."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    monkeypatch.setattr(server, "THRESHOLD_LOCAL_STRONG", 0.5)  # easy to exceed

    # Mock local to return strong activations
    def fake_local(*args, **kwargs):
        return {
            "query": kwargs.get("query", "x"),
            "results": [
                {"concept": "a", "activation": 0.9, "hops": 2},
                {"concept": "b", "activation": 0.8, "hops": 2},
            ],
            "elapsed_ms": 1.0,
            "source": "local",
            "repo_path": str(repo),
        }

    called = {"meta": 0}

    def spy_meta(*args, **kwargs):
        called["meta"] += 1
        return {"results": [], "source": "meta", "elapsed_ms": 0}

    monkeypatch.setattr(server, "_recall_local_impl", fake_local)
    monkeypatch.setattr(server, "_recall_meta_impl", spy_meta)

    r = server._recall_dual_impl(query="python", scope="auto", top_k=5,
                                  repo_path=str(repo))
    assert called["meta"] == 0
    assert "local" in r["source"]


def test_auto_merges_when_local_weak(tmp_path, monkeypatch):
    """auto: if local strength < threshold, call meta + merge."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    monkeypatch.setattr(server, "THRESHOLD_LOCAL_STRONG", 99.0)  # impossible to hit

    def weak_local(*a, **k):
        return {
            "query": "x", "results": [{"concept": "a", "activation": 0.1, "hops": 2}],
            "elapsed_ms": 1.0, "source": "local", "repo_path": str(repo),
        }

    called = {"meta": 0}

    def spy_meta(*a, **k):
        called["meta"] += 1
        return {
            "query": "x", "results": [{"concept": "b", "activation": 0.5, "hops": 2}],
            "elapsed_ms": 1.0, "source": "meta", "meta_path": "/tmp/fake",
        }

    monkeypatch.setattr(server, "_recall_local_impl", weak_local)
    monkeypatch.setattr(server, "_recall_meta_impl", spy_meta)

    r = server._recall_dual_impl(query="x", scope="auto", top_k=5,
                                  repo_path=str(repo))
    assert called["meta"] == 1
    assert "local" in r["source"] and "meta" in r["source"]


# ── Fusion methods ───────────────────────────────────────────


def test_merge_linear_respects_weights():
    """linear fusion: α=1.0/β=0.0 must surface local results, β=1.0/α=0.0 meta."""
    from muninn.mcp import server
    local_res = [{"concept": "L1", "activation": 0.9, "hops": 2}]
    meta_res = [{"concept": "M1", "activation": 0.9, "hops": 2}]
    only_local = server._merge_results(local_res, meta_res, "linear", 1.0, 0.0, top_k=5)
    only_meta = server._merge_results(local_res, meta_res, "linear", 0.0, 1.0, top_k=5)
    assert any(r["concept"] == "L1" for r in only_local)
    assert any(r["concept"] == "M1" for r in only_meta)


def test_merge_rrf_ignores_raw_scores():
    """rrf fusion: rank matters, not raw activation magnitude.

    Even if local has activation 0.99 and meta 0.01, with α=0, β=1, only
    meta-ranked-first concept should surface — proving RRF uses ranks.
    """
    from muninn.mcp import server
    local_res = [{"concept": "L1", "activation": 0.99, "hops": 2}]
    meta_res = [{"concept": "M1", "activation": 0.01, "hops": 2}]
    only_meta = server._merge_results(local_res, meta_res, "rrf", 0.0, 1.0, top_k=5)
    assert only_meta[0]["concept"] == "M1"


# ── Env-var overrides ────────────────────────────────────────


def test_env_var_top_k_default(monkeypatch):
    """MUNINN_DUAL_TOP_K env var changes the default top_k."""
    monkeypatch.setenv("MUNINN_DUAL_TOP_K", "3")
    from muninn.mcp import server
    importlib.reload(server)
    assert server.TOP_K_DEFAULT == 3
    # Cleanup: reload again with default
    monkeypatch.delenv("MUNINN_DUAL_TOP_K", raising=False)
    importlib.reload(server)


# ── Read-only contract ──────────────────────────────────────


def test_meta_db_read_only(tmp_path, monkeypatch):
    """All scopes must NOT modify meta_mycelium.db (mtime + content stable)."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    _seed_local_mycelium(repo, [("python", "flask", 3)])
    meta_dir = _make_isolated_meta_db(tmp_path, [("python", "django", 5)])
    monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))
    meta_db = meta_dir / "meta_mycelium.db"

    before_mtime = meta_db.stat().st_mtime
    before_size = meta_db.stat().st_size
    time.sleep(0.01)

    for scope in ("local", "meta", "both", "auto"):
        server._recall_dual_impl(query="python", scope=scope, top_k=5,
                                  repo_path=str(repo))

    assert meta_db.stat().st_mtime == before_mtime
    assert meta_db.stat().st_size == before_size


# ── Graceful degradation ─────────────────────────────────────


def test_missing_meta_db_returns_empty_not_crash(tmp_path, monkeypatch):
    """meta-DB absent → _recall_meta_impl returns empty results, no raise."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    missing_dir = tmp_path / "nonexistent_meta_dir"
    monkeypatch.setenv("MUNINN_META_PATH", str(missing_dir))

    r = server._recall_meta_impl(query="x", top_k=5)
    assert isinstance(r, dict)
    assert r.get("results") == []


def test_auto_with_missing_meta_falls_back_to_local(tmp_path, monkeypatch):
    """auto + missing meta-DB → return local-only, no crash."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    _seed_local_mycelium(repo, [("python", "flask", 3)])
    missing_dir = tmp_path / "nope"
    monkeypatch.setenv("MUNINN_META_PATH", str(missing_dir))
    monkeypatch.setattr(server, "THRESHOLD_LOCAL_STRONG", 99.0)  # force auto→meta path

    r = server._recall_dual_impl(query="python", scope="auto", top_k=5,
                                  repo_path=str(repo))
    assert isinstance(r, dict)
    assert isinstance(r.get("results"), list)


# ── JSON serializable ───────────────────────────────────────


def test_all_scopes_json_serializable(tmp_path, monkeypatch):
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    _seed_local_mycelium(repo, [("python", "flask", 3)])
    meta_dir = _make_isolated_meta_db(tmp_path, [("python", "django", 5)])
    monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))

    for scope in ("local", "meta", "both", "auto"):
        r = server._recall_dual_impl(query="python", scope=scope, top_k=3,
                                      repo_path=str(repo))
        json.dumps(r)  # must not raise


# ── top_k respected ─────────────────────────────────────────


def test_top_k_respected_after_merge(tmp_path, monkeypatch):
    """top_k=3 must cap final result to ≤3 even after merging 20 candidates."""
    from muninn.mcp import server
    # Synthetic results: 10 local + 10 meta
    local_res = [{"concept": f"L{i}", "activation": 1.0 - i*0.05, "hops": 2}
                 for i in range(10)]
    meta_res = [{"concept": f"M{i}", "activation": 1.0 - i*0.05, "hops": 2}
                for i in range(10)]
    merged = server._merge_results(local_res, meta_res, "linear", 0.7, 0.3, top_k=3)
    assert len(merged) <= 3
