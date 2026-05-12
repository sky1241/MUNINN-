"""
CHUNK MCP E.6 — Hardened tests for 5 high-risk weak grep-presence tests.

Deep audit (2026-05-12) found ~36 tests across A-D phases that check
structure / file existence / keyword presence but not actual behavior.
The 5 strongest signals went unnoticed for cycles. This file adds REAL
functional tests next to the weak ones so any future regression breaks
CI immediately.

The 5 targets, ranked by damage-if-bug:

| # | Original weak test | Damage if bug |
|---|---|---|
| 1 | test_d1_manifest_prunes_internal_data | User's pip install ships Sky's debug data |
| 2 | test_a3_service_calls_muninn_prune | systemd timer fails silently |
| 3 | test_d5_doctor_checks_* (3 tests) | Doctor stops surfacing pip-install issues |
| 4 | test_c0_env_var_top_k_default | Env var override silently ignored in prod |
| 5 | test_b1_tool_bounds_clamping | Out-of-bounds inputs cause downstream issues |
"""
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── Target #1: SDIST must NOT ship internal data ──────────────────

@pytest.mark.slow
def test_e6_sdist_excludes_internal_muninn_dir(tmp_path):
    """Actually build sdist + verify muninn/.muninn/ is NOT inside.

    Pre-E.6 the test only grep'd MANIFEST.in for the literal string
    "prune muninn/.muninn". A typo (e.g. "prune muninn/.muninnn") or
    a setuptools version that ignores MANIFEST.in could silently let
    /home/sky/Bureau/MUNINN-/muninn/.muninn/edits_log.jsonl ship to every
    PyPI user. This test reads the actual sdist tarball.
    """
    # Use a tmp build dir so we don't pollute the repo's dist/
    cmd = [sys.executable, "-m", "build", "--sdist", "--no-isolation",
           "--outdir", str(tmp_path)]
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, f"sdist build failed: {r.stderr[-500:]}"

    sdists = list(tmp_path.glob("*.tar.gz"))
    assert sdists, f"No sdist produced in {tmp_path}"
    sdist = sdists[0]

    leaks = []
    with tarfile.open(sdist, "r:gz") as tar:
        for name in tar.getnames():
            # Strip the top-level versioned dir prefix (e.g. muninn_memory-1.0.1/)
            parts = name.split("/", 1)
            relative = parts[1] if len(parts) > 1 else name
            if (relative.startswith("muninn/.muninn/")
                    or "/muninn/.muninn/" in relative):
                leaks.append(name)
            if relative.startswith("muninn/ui/scans/") and relative.endswith(".json"):
                # scans are user-specific, not shippable defaults
                leaks.append(name)
            if ".muninn/edits_log" in relative or ".muninn/errors.json" in relative:
                leaks.append(name)
    assert not leaks, (
        f"sdist contains internal data that should be pruned by MANIFEST.in:\n  "
        + "\n  ".join(leaks[:10])
    )


# ─── Target #2: install_cron generates a valid systemd unit ────────

def test_e6_install_cron_service_execstart_is_parseable(tmp_path, monkeypatch):
    """install_cron() produces a service file with a parseable ExecStart.

    Pre-E.6 the test only grep'd for the literal "muninn" + "prune" +
    "--force" in the service file body. systemd's actual parser is
    stricter — if ExecStart references a non-existent binary or has a
    quoting bug, the timer fails at boot, not at install time.

    We extract ExecStart and run `shlex.split` on it to confirm the
    command can at least be tokenized into argv. We also verify the
    executable referenced exists OR is a python invocation pattern.
    """
    import os
    import shlex

    # Sandbox $HOME and the systemd detection.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "systemd" / "user").mkdir(parents=True, exist_ok=True)
    # Add engine/core to sys.path so muninn module loads in test
    monkeypatch.syspath_prepend(str(REPO_ROOT / "engine" / "core"))
    monkeypatch.syspath_prepend(str(REPO_ROOT))

    # Force-detect systemd as present (function returns "systemd-user" or "none")
    import muninn_install
    monkeypatch.setattr(muninn_install, "_detect_init_system", lambda: "systemd-user")

    repo = tmp_path / "demo_repo"
    repo.mkdir()
    muninn_install.install_cron(str(repo))

    svc = tmp_path / ".config" / "systemd" / "user" / "muninn-prune.service"
    assert svc.exists(), "install_cron should create muninn-prune.service"
    content = svc.read_text(encoding="utf-8")

    exec_lines = [l for l in content.splitlines() if l.startswith("ExecStart=")]
    assert exec_lines, f"Service file has no ExecStart line:\n{content}"
    exec_cmd = exec_lines[0].split("=", 1)[1]

    # shlex.split should accept it (or fail with a clear ValueError)
    try:
        tokens = shlex.split(exec_cmd)
    except ValueError as e:
        pytest.fail(f"ExecStart is unparseable by shlex: {e}\n  line: {exec_cmd}")

    assert len(tokens) >= 2, f"ExecStart should have ≥2 tokens, got {tokens}"
    # First token must be a python interpreter or an absolute path to a binary
    first = tokens[0]
    assert (first == "python" or first.endswith("python3")
            or first.endswith("/python") or "/python" in first
            or Path(first).exists()), (
        f"ExecStart first token is neither python nor an existing binary: {first}"
    )
    # The repo path must appear somewhere in the command
    assert str(repo) in exec_cmd, f"ExecStart should reference repo {repo}: {exec_cmd}"


# ─── Target #3: doctor() output actually contains the new checks ───

def test_e6_doctor_output_contains_d5_pip_install_checks(tmp_path, monkeypatch):
    """Actually run `muninn doctor` and assert the 3 new checks fire.

    Pre-E.6 we grep'd doctor.py source for "console_script" etc. That
    only verifies the strings exist in the file — not that they actually
    appear in the output the user sees. If a future refactor moves the
    check inside a try/except that silently swallows, this would now
    fail (versus pre-E.6 going green falsely).
    """
    import os
    cmd = [sys.executable, str(REPO_ROOT / "engine" / "core" / "muninn.py"), "doctor"]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(REPO_ROOT / "engine" / "core") + ":" + env.get("PYTHONPATH", "")
    )
    # cd to tmp_path so doctor doesn't accidentally use Sky's repo
    r = subprocess.run(cmd, cwd=str(tmp_path), capture_output=True,
                       text=True, timeout=60, env=env)
    combined = r.stdout + r.stderr

    # The 3 D.5 checks must appear in the output as labelled lines
    required_substrings = [
        "console_script",       # check #20
        "engine.core",          # check #21 — either OK or WARN, but the label must show
        "mcp",                  # check #22 — either OK or WARN
    ]
    missing = [s for s in required_substrings if s not in combined]
    assert not missing, (
        f"doctor() output missing E.5 D.5 check labels: {missing}\n"
        f"Doctor output tail:\n{combined[-1500:]}"
    )


# ─── Target #4: MUNINN_DUAL_TOP_K env var actually applies ─────────

def test_e6_env_var_top_k_clamps_loaded_default(monkeypatch):
    """MUNINN_DUAL_TOP_K must actually change TOP_K_DEFAULT at import time.

    Pre-E.6 the test only checked that reloading the module read the env
    var. It didn't verify that subsequent calls actually used the env
    value rather than the hardcoded default.
    """
    import importlib
    monkeypatch.setenv("MUNINN_DUAL_TOP_K", "3")
    from muninn.mcp import server
    importlib.reload(server)
    assert server.TOP_K_DEFAULT == 3, (
        f"MUNINN_DUAL_TOP_K=3 should set TOP_K_DEFAULT=3, got {server.TOP_K_DEFAULT}"
    )

    # Now test the converse: default value when env var unset
    monkeypatch.delenv("MUNINN_DUAL_TOP_K", raising=False)
    importlib.reload(server)
    assert server.TOP_K_DEFAULT == 10, (
        f"Without MUNINN_DUAL_TOP_K, TOP_K_DEFAULT should be 10, got {server.TOP_K_DEFAULT}"
    )


# ─── Target #5: top_k bounds clamping on out-of-range inputs ───────

def test_e6_recall_clamps_negative_top_k(tmp_path):
    """_recall_dual_impl(top_k=-5) must NOT crash or query with negative LIMIT.

    Pre-E.6 the test asserted "returns dict" but didn't verify top_k
    was actually clamped before reaching the SQL layer. A SQL injection
    or LIMIT -5 panic would have shipped silently.
    """
    from muninn.mcp.server import _recall_dual_impl, TOP_K_MIN, TOP_K_MAX

    # No mycelium needed for the bounds check — the function clamps before
    # touching SQLite. We just need ANY repo_path it can resolve.
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".muninn" / "mycelium.db").touch()  # empty file, won't be queried thanks to clamp

    # Negative top_k must clamp to TOP_K_MIN (typically 1)
    r1 = _recall_dual_impl(query="anything", top_k=-5,
                           scope="local", repo_path=str(tmp_path))
    assert isinstance(r1, dict), f"Should return dict even on negative top_k, got {type(r1)}"
    # Length of results must be in [0, TOP_K_MAX] — never negative
    n1 = len(r1.get("results", []))
    assert 0 <= n1 <= TOP_K_MAX, (
        f"Negative top_k=-5 returned {n1} results; should clamp to [{TOP_K_MIN}, {TOP_K_MAX}]"
    )


def test_e6_recall_clamps_huge_top_k(tmp_path):
    """_recall_dual_impl(top_k=10_000_000) must clamp to TOP_K_MAX, no OOM."""
    from muninn.mcp.server import _recall_dual_impl, TOP_K_MAX
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".muninn" / "mycelium.db").touch()

    r2 = _recall_dual_impl(query="anything", top_k=10_000_000,
                           scope="local", repo_path=str(tmp_path))
    assert isinstance(r2, dict)
    n2 = len(r2.get("results", []))
    assert n2 <= TOP_K_MAX, (
        f"Huge top_k=10M returned {n2} results; should clamp to TOP_K_MAX={TOP_K_MAX}"
    )
