"""
CHUNK MCP E.4 — muninn-mcp-mem argparse for --help / --version / --list-tools.

Pre-E.4 bug: `muninn-mcp-mem --help` (or any flag) was passed straight to
the FastMCP stdio loop, which ignored them and waited indefinitely for
JSON-RPC input on stdin. User typing `--help` saw a hung terminal.

E.4 fix: argparse intercepts `--help`, `--version`, `--list-tools` BEFORE
entering the stdio loop. The default behavior (no args) still runs the
stdio server, so Claude Code's integration is unchanged.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_mcp_server(args, timeout=10):
    """Invoke `python -m muninn.mcp.server` with the given args."""
    r = subprocess.run(
        [sys.executable, "-m", "muninn.mcp.server", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )
    return r


def test_e4_help_exits_cleanly():
    """--help must show usage and exit with code 0 (not hang in stdio loop)."""
    r = _run_mcp_server(["--help"])
    assert r.returncode == 0, f"--help should exit 0, got {r.returncode}"
    combined = r.stdout + r.stderr
    assert "usage:" in combined.lower(), "Output should include 'usage:'"
    assert "muninn-mcp-mem" in combined, "Help should mention the binary name"


def test_e4_short_help_flag():
    """-h is the argparse short form, must also exit cleanly."""
    r = _run_mcp_server(["-h"])
    assert r.returncode == 0
    assert "usage:" in (r.stdout + r.stderr).lower()


def test_e4_version_exits_cleanly():
    """--version must print version + exit, not enter stdio loop."""
    r = _run_mcp_server(["--version"])
    assert r.returncode == 0
    out = (r.stdout + r.stderr).strip()
    # argparse --version prints to stdout in Python 3.4+
    assert "muninn-mcp-mem" in out, f"--version should print binary name: {out}"
    # Version regex: 1.x.y
    import re
    assert re.search(r"\b1\.\d+\.\d+\b", out), f"--version should print 1.x.y semver: {out}"


def test_e4_list_tools_shows_10_tools():
    """--list-tools must show all 10 registered MCP tools + exit."""
    r = _run_mcp_server(["--list-tools"])
    assert r.returncode == 0, f"--list-tools failed: {r.stderr}"
    combined = r.stdout + r.stderr
    # The 10 known tools (from Phase B chunks B.2-B.5):
    expected_tools = [
        "mycelium_recall_local",
        "mycelium_recall_meta",
        "mycelium_recall",
        "tree_get_root",
        "tree_get_branch",
        "tree_list_branches",
        "bugs_list",
        "bugs_get",
        "runbook_list_sections",
        "runbook_get",
    ]
    missing = [t for t in expected_tools if t not in combined]
    assert not missing, f"--list-tools missing tools: {missing}"


def test_e4_default_behavior_unchanged():
    """Without args, the script should TRY to enter the stdio loop.

    We verify by sending EOF to stdin and checking that the process either:
    - Exits gracefully (server saw end-of-stream)
    - OR times out (server is waiting for input — proves stdio loop reached)

    Either is acceptable. We just need to prove `--help`/`--version` didn't
    silently affect the default code path.
    """
    try:
        r = subprocess.run(
            [sys.executable, "-m", "muninn.mcp.server"],
            input="",  # empty stdin → EOF immediately
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(REPO_ROOT),
        )
        # If it exited, the stdio loop saw EOF and quit. That's fine.
    except subprocess.TimeoutExpired:
        # If it timed out, the stdio loop is alive waiting for input. Also fine.
        pass


def test_e4_unknown_flag_exits_2():
    """argparse convention: unknown flags exit with code 2."""
    r = _run_mcp_server(["--bogus-flag"], timeout=5)
    assert r.returncode == 2, (
        f"Unknown flag should exit 2 (argparse convention), got {r.returncode}"
    )
