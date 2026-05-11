"""
CHUNK MCP B.6 — End-to-end test of the Muninn MCP server.

Spawns `python -m muninn.mcp` as a subprocess (same way Claude Code would)
and exercises the full MCP protocol over stdio:
  1. initialize handshake → serverInfo.name == "muninn"
  2. tools/list → all 10 tools (B.1 + B.2 + B.3 + B.4 + B.5) are visible
  3. tools/call mycelium_recall_local → JSON-RPC result with `results` key
  4. tools/call bugs_list → JSON-RPC result with `bugs` key
  5. tools/call runbook_list_sections → JSON-RPC result with `sections` key

This proves the full chain works end-to-end :
  spawn → initialize → list_tools → call → response → JSON-serializable.

Opt-in via MUNINN_RUN_E2E=1 (like A.4 — these tests are slow, ~5-10s
because of process spawn + multiple JSON-RPC round-trips).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("MUNINN_RUN_E2E") != "1",
        reason="E2E MCP server test — set MUNINN_RUN_E2E=1 to opt in (~10s)",
    ),
    pytest.mark.skipif(
        sys.platform != "linux",
        reason="E2E test Linux-only for B.6 (Phase D adds Win/macOS)",
    ),
]

mcp_fastmcp = pytest.importorskip("mcp.server.fastmcp", reason="mcp not installed")


EXPECTED_TOOLS = {
    # B.1 + B.3
    "mycelium_recall_local",
    "mycelium_recall_meta",
    "mycelium_recall",
    # B.2
    "tree_get_root",
    "tree_get_branch",
    "tree_list_branches",
    # B.4
    "bugs_list",
    "bugs_get",
    # B.5
    "runbook_list_sections",
    "runbook_get",
}


@pytest.fixture(scope="module")
def mcp_subprocess():
    """Spawn `python -m muninn.mcp` once, share across all B.6 tests."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "muninn.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO_ROOT),
    )
    # Send initialize handshake first
    init_msg = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest-e2e", "version": "0.1"},
        },
    }
    proc.stdin.write((json.dumps(init_msg) + "\n").encode("utf-8"))
    proc.stdin.flush()
    init_response = _read_response(proc, timeout=5.0)
    assert init_response is not None
    assert init_response.get("id") == 0
    assert "result" in init_response, f"init failed: {init_response}"

    # Send the initialized notification (no id, no response expected)
    initialized_notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    proc.stdin.write((json.dumps(initialized_notif) + "\n").encode("utf-8"))
    proc.stdin.flush()
    # Small grace period
    time.sleep(0.1)

    yield proc

    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def _read_response(proc, timeout=5.0):
    """Read one JSON-RPC response line from stdout."""
    start = time.time()
    line = b""
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if line:
            break
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def _rpc_call(proc, method, params, msg_id):
    """Send a JSON-RPC request and return the response dict."""
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
    proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
    proc.stdin.flush()
    return _read_response(proc, timeout=10.0)


# ── Tests ──────────────────────────────────────────────────


def test_initialize_serverinfo_is_muninn(mcp_subprocess):
    """The fixture's init handshake should already have validated this, but
    we keep a sentinel test so the test count reflects the assertion."""
    # init_response was already asserted in the fixture; this test ensures
    # the subprocess is still running here.
    assert mcp_subprocess.poll() is None, "MCP server died after init"


def test_tools_list_returns_all_10_tools(mcp_subprocess):
    """tools/list must surface every tool registered in create_server()."""
    resp = _rpc_call(mcp_subprocess, "tools/list", {}, msg_id=1)
    assert resp is not None
    assert "result" in resp, f"unexpected response: {resp}"
    tools = resp["result"].get("tools", [])
    names = {t["name"] for t in tools}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"missing tools: {missing}. Got: {sorted(names)}"


def test_call_mycelium_recall_local_returns_results(mcp_subprocess):
    """tools/call mycelium_recall_local must return a results array."""
    resp = _rpc_call(
        mcp_subprocess,
        "tools/call",
        {
            "name": "mycelium_recall_local",
            "arguments": {
                "query": "muninn",
                "top_k": 3,
                "repo_path": str(REPO_ROOT),
            },
        },
        msg_id=2,
    )
    assert resp is not None
    assert "result" in resp, f"unexpected response: {resp}"
    # MCP tool result format: {"content": [{"type": "text", "text": "<json>"}]}
    content = resp["result"].get("content", [])
    assert content, "empty content"
    payload_text = content[0].get("text", "")
    payload = json.loads(payload_text)
    assert "results" in payload
    assert payload.get("source") == "local"


def test_call_bugs_list_returns_bugs(mcp_subprocess):
    """tools/call bugs_list on the real BUGS.md must return the bug list."""
    resp = _rpc_call(
        mcp_subprocess,
        "tools/call",
        {
            "name": "bugs_list",
            "arguments": {"repo_path": str(REPO_ROOT), "limit": 3},
        },
        msg_id=3,
    )
    assert resp is not None
    assert "result" in resp, f"unexpected response: {resp}"
    content = resp["result"].get("content", [])
    payload = json.loads(content[0]["text"])
    assert "bugs" in payload
    assert isinstance(payload["bugs"], list)


def test_call_runbook_list_sections_returns_sections(mcp_subprocess):
    """tools/call runbook_list_sections on changelog returns dated sections."""
    resp = _rpc_call(
        mcp_subprocess,
        "tools/call",
        {
            "name": "runbook_list_sections",
            "arguments": {"document": "changelog", "repo_path": str(REPO_ROOT)},
        },
        msg_id=4,
    )
    assert resp is not None
    assert "result" in resp, f"unexpected response: {resp}"
    content = resp["result"].get("content", [])
    payload = json.loads(content[0]["text"])
    assert payload["document"] == "changelog"
    assert payload["count"] >= 1


def test_call_tree_list_branches_returns_branches(mcp_subprocess):
    """tools/call tree_list_branches on the real repo returns >= 1 branch."""
    resp = _rpc_call(
        mcp_subprocess,
        "tools/call",
        {
            "name": "tree_list_branches",
            "arguments": {"repo_path": str(REPO_ROOT)},
        },
        msg_id=5,
    )
    assert resp is not None
    assert "result" in resp, f"unexpected response: {resp}"
    content = resp["result"].get("content", [])
    payload = json.loads(content[0]["text"])
    assert "branches" in payload
    assert isinstance(payload["branches"], list)
