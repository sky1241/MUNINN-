"""
CHUNK MCP B.1 — MCP server scaffold + 1er tool `mycelium_recall_local`.

Premier chunk de Phase B (KILLER FEATURE). Met en place le squelette d'un
serveur MCP (Model Context Protocol) Python via FastMCP + 1 tool de demo
`mycelium_recall_local(query, top_k=10)` qui query le mycelium local du repo.

Le tool est un PURE WRAPPER autour de Mycelium.spread_activation() — pas
de code algo nouveau, donc PAS de forge requis (skip RULE 5 N/A).

Tests behaviouraux (8 + 1 slow stdio smoke) :
1. Module muninn.mcp.server importable
2. create_server() retourne FastMCP instance "muninn"
3. Tool mycelium_recall_local enregistre dans la app
4. Tool callable direct retourne dict bien-forme (5 cles)
5. Tool respecte top_k (cap a max requested)
6. Tool sur mycelium vide retourne results == []
7. Tool sur repo_path invalide leve ValueError user-friendly
8. Tool output 100% json.dumps-serializable
9. (slow) Stdio subprocess accepte initialize JSON-RPC + repond
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skip whole module if mcp not installed (optional dep in pyproject [mcp])
mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


# ── Module + scaffold ────────────────────────────────────────


def test_module_importable():
    """muninn.mcp.server doit s'importer sans erreur."""
    from muninn.mcp import server
    assert hasattr(server, "create_server"), "create_server() missing"
    assert hasattr(server, "main"), "main() missing"


def test_create_server_returns_fastmcp():
    """create_server() retourne un FastMCP nomme 'muninn'."""
    from muninn.mcp import server
    app = server.create_server()
    from mcp.server.fastmcp import FastMCP
    assert isinstance(app, FastMCP), f"expected FastMCP, got {type(app)}"
    assert app.name == "muninn", f"server name: {app.name!r}"


# ── Tool registration ────────────────────────────────────────


def test_tool_registered():
    """mycelium_recall_local doit etre register dans la FastMCP app."""
    import asyncio
    from muninn.mcp import server
    app = server.create_server()
    tools = asyncio.run(app.list_tools())
    names = [t.name for t in tools]
    assert "mycelium_recall_local" in names, (
        f"mycelium_recall_local not registered. Got: {names}"
    )


# ── Direct call behaviour ────────────────────────────────────


def _make_minimal_repo(tmp_path):
    """Create a minimal Muninn-bootstrapped repo (.muninn/ + empty mycelium)."""
    repo = tmp_path / "tmp_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()
    return repo


def _make_repo_with_concepts(tmp_path, concepts_pairs):
    """Create a repo with a mycelium that has observed some co-occurrences.

    concepts_pairs: list of (a, b, count) — observed `count` times each.
    """
    repo = _make_minimal_repo(tmp_path)
    # Bootstrap a fresh Mycelium and feed it
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    from mycelium import Mycelium
    m = Mycelium(repo)
    for a, b, count in concepts_pairs:
        for _ in range(count):
            m.observe([a, b])
    m.save()
    try:
        m.close()
    except Exception:
        pass
    return repo


def test_tool_direct_call_returns_well_formed_dict(tmp_path):
    """Direct call retourne un dict avec exactement 5 keys + types corrects."""
    from muninn.mcp import server
    repo = _make_repo_with_concepts(tmp_path, [
        ("python", "flask", 20),
        ("flask", "jinja", 15),
        ("jinja", "templates", 10),
    ])
    result = server._recall_local_impl(
        query="python",
        top_k=10,
        repo_path=str(repo),
        hops=2,
    )
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    for k in ("query", "results", "elapsed_ms", "source", "repo_path"):
        assert k in result, f"missing key {k!r}. Got: {list(result.keys())}"
    assert result["query"] == "python"
    assert result["source"] == "local"
    assert isinstance(result["results"], list)
    assert isinstance(result["elapsed_ms"], (int, float))


def test_tool_respects_top_k(tmp_path):
    """top_k=2 -> au plus 2 results renvoyes (cap respect)."""
    from muninn.mcp import server
    # Crée un mycelium avec >10 concepts liés
    pairs = [("root", f"c{i}", 10) for i in range(15)]
    repo = _make_repo_with_concepts(tmp_path, pairs)
    result = server._recall_local_impl(
        query="root", top_k=2, repo_path=str(repo), hops=2,
    )
    assert len(result["results"]) <= 2, (
        f"top_k=2 violated: got {len(result['results'])} results"
    )


def test_tool_empty_mycelium_returns_empty_list(tmp_path):
    """Mycelium vide (jamais observe) -> results == []."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    result = server._recall_local_impl(
        query="anything", top_k=10, repo_path=str(repo), hops=2,
    )
    assert result["results"] == [], (
        f"expected empty results, got: {result['results']}"
    )


def test_tool_invalid_repo_path_raises_user_friendly():
    """repo_path qui n'existe pas -> ValueError avec message clair."""
    from muninn.mcp import server
    with pytest.raises(ValueError) as exc_info:
        server._recall_local_impl(
            query="foo", top_k=10,
            repo_path="/this/path/does/not/exist/nope/never",
            hops=2,
        )
    msg = str(exc_info.value).lower()
    assert "muninn" in msg or "repo" in msg or "not found" in msg, (
        f"error message not user-friendly: {exc_info.value!r}"
    )


def test_tool_output_json_serializable(tmp_path):
    """Le dict renvoye doit etre json.dumps-able sans error."""
    from muninn.mcp import server
    repo = _make_repo_with_concepts(tmp_path, [("a", "b", 5)])
    result = server._recall_local_impl(
        query="a", top_k=10, repo_path=str(repo), hops=2,
    )
    # Should not raise
    encoded = json.dumps(result)
    assert isinstance(encoded, str)
    assert len(encoded) > 0


def test_tool_bounds_clamping(tmp_path):
    """top_k et hops out-of-bounds doivent etre clampes (pas crash)."""
    from muninn.mcp import server
    repo = _make_minimal_repo(tmp_path)
    # Negative or zero top_k -> clamp to >= 1
    r = server._recall_local_impl(query="x", top_k=0, repo_path=str(repo), hops=2)
    assert isinstance(r, dict)
    # huge top_k -> clamp to <= 100
    r = server._recall_local_impl(query="x", top_k=10000, repo_path=str(repo), hops=2)
    assert isinstance(r, dict)
    # hops out of range
    r = server._recall_local_impl(query="x", top_k=5, repo_path=str(repo), hops=99)
    assert isinstance(r, dict)


# ── Slow: stdio subprocess smoke test ────────────────────────


@pytest.mark.slow
def test_stdio_subprocess_initialize_handshake():
    """Lance `python -m muninn.mcp` en subprocess et fait un handshake
    JSON-RPC `initialize` via stdin/stdout.

    Verifie que le server respond avec serverInfo.name == 'muninn'.
    """
    proc = subprocess.Popen(
        [sys.executable, "-m", "muninn.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    try:
        # Envoie un initialize JSON-RPC (spec MCP)
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest-smoke", "version": "0.1"},
            },
        }
        proc.stdin.write((json.dumps(init_msg) + "\n").encode("utf-8"))
        proc.stdin.flush()

        # Attendre la réponse (timeout 5s)
        start = time.time()
        line = b""
        while time.time() - start < 5.0:
            line = proc.stdout.readline()
            if line:
                break
        assert line, "no response from MCP server within 5s"
        resp = json.loads(line.decode("utf-8"))
        assert resp.get("id") == 1
        assert "result" in resp, f"no result in response: {resp}"
        server_info = resp["result"].get("serverInfo", {})
        assert server_info.get("name") == "muninn", (
            f"unexpected server name: {server_info}"
        )
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
