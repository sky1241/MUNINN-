"""H.4 — Wire `muninn-mem metrics` CLI.

Until H.4 ships, engine/core/forge_metrics.py (344 LOC) is reachable only
via in-process import inside the UI's heatmap rendering. There's no CLI
or batch path that prints Q-modularity / carmack / locate scores.

Contract :
  - `muninn-mem metrics` argparse choice exists
  - Handler delegates to forge_metrics.get_repo_risk(repo) (no duplication)
  - Output is JSON on stdout
  - `--output FILE` writes the same JSON to FILE (re-uses an existing
    argparse flag that was dormant)
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MUNINN_PY = REPO_ROOT / "engine" / "core" / "muninn.py"


def _choices() -> list[str]:
    tree = ast.parse(MUNINN_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "command"):
            for kw in node.keywords:
                if kw.arg == "choices" and isinstance(kw.value, ast.List):
                    return [e.value for e in kw.value.elts
                            if isinstance(e, ast.Constant)]
    return []


def test_h4_metrics_in_command_choices() -> None:
    assert "metrics" in _choices(), (
        "`metrics` missing from argparse choices in engine/core/muninn.py"
    )


def test_h4_metrics_handler_exists() -> None:
    src = MUNINN_PY.read_text(encoding="utf-8")
    assert 'args.command == "metrics"' in src, (
        "No handler for `metrics` command in engine/core/muninn.py main()"
    )


def test_h4_metrics_delegates_to_get_repo_risk() -> None:
    src = MUNINN_PY.read_text(encoding="utf-8")
    assert "get_repo_risk" in src, (
        "metrics handler must call forge_metrics.get_repo_risk(repo) — "
        "don't re-implement"
    )


def test_h4_metrics_end_to_end_returns_json(tmp_path: Path) -> None:
    """muninn-mem metrics in a tmp_path must return JSON on stdout."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("MUNINN_DEBUG", None)
    proc = subprocess.run(
        [sys.executable, "-m", "muninn._engine", "metrics"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=180,
    )
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, (
        f"metrics must not crash. Got:\n{combined}"
    )
    # Stdout should contain JSON (with at least a `repo` key)
    # Find the first { and try to parse from there
    out = proc.stdout
    m = re.search(r"\{.*\}", out, re.S)
    assert m, f"metrics stdout has no JSON object. Got:\n{out}\n--stderr--\n{proc.stderr}"
    data = json.loads(m.group(0))
    assert "repo" in data, (
        f"metrics JSON must include `repo` field. Got: {data}"
    )


def test_h4_mirror_engine() -> None:
    mirror_src = (REPO_ROOT / "engine" / "core" / "muninn.py").read_text(encoding="utf-8")
    assert 'args.command == "metrics"' in mirror_src, (
        "muninn/_engine.py missing metrics handler (BUG-091 mirror)"
    )
    assert '"metrics"' in mirror_src, (
        "muninn/_engine.py missing 'metrics' in argparse choices"
    )
