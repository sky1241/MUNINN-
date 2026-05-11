"""
CHUNK MCP C.1 — split engine/core/muninn.py 2666L → 3 modules <2500L each.

Demand Sky (2026-05-11 nuit): muninn.py crossed 2500L cap when install_cron
landed (chunk A.3). Was admitted to DOCUMENTED_OVERSIZED_MODULES with a
promise of refactor in Phase C polish. This is that refactor.

Split target:
- engine/core/muninn.py (~900L): CLI dispatcher + scan_repo + bootstrap +
  generate_root_mn + generate_winter_tree + handlers vault/quarantine/zones.
- engine/core/muninn_install.py (NEW ~1180L): registry, hook generators,
  install_hooks, install_cron, _detect_init_system.
- engine/core/muninn_secrets.py (NEW ~290L): scrub_secrets, purge_secrets_db,
  _SCRUB_*, _TRIGGER_*, scrub/purge CLI handlers.
- Mirror full split into muninn/_engine.py + muninn/_install.py +
  muninn/_secrets_cli.py for pip-package parity (BUG-091).

10 behavioural tests.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Size checks ─────────────────────────────────────────────


def test_c1_muninn_under_2500_lines():
    """muninn.py < 2500L after split (out of DOCUMENTED_OVERSIZED_MODULES)."""
    p = REPO_ROOT / "engine" / "core" / "muninn.py"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    assert n < 2500, f"muninn.py still oversized: {n}L (expected <2500)"


def test_c1_install_module_exists_and_sized():
    """muninn_install.py exists, 100 < L < 2500."""
    p = REPO_ROOT / "engine" / "core" / "muninn_install.py"
    assert p.exists(), f"missing {p}"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    assert 100 < n < 2500, f"muninn_install.py size: {n}L"


def test_c1_secrets_module_exists_and_sized():
    """muninn_secrets.py exists, 50 < L < 2500."""
    p = REPO_ROOT / "engine" / "core" / "muninn_secrets.py"
    assert p.exists(), f"missing {p}"
    n = sum(1 for _ in p.open(encoding="utf-8"))
    assert 50 < n < 2500, f"muninn_secrets.py size: {n}L"


# ── Public API preserved via muninn package ─────────────────


def test_c1_public_api_install_preserved():
    """from muninn import install_hooks, install_cron still works."""
    import muninn
    assert hasattr(muninn, "install_hooks"), "install_hooks missing in muninn"
    assert hasattr(muninn, "install_cron"), "install_cron missing in muninn"
    assert callable(muninn.install_hooks)
    assert callable(muninn.install_cron)


def test_c1_public_api_secrets_preserved():
    """from muninn import scrub_secrets, purge_secrets_db still works."""
    import muninn
    assert hasattr(muninn, "scrub_secrets")
    assert hasattr(muninn, "purge_secrets_db")
    assert callable(muninn.scrub_secrets)
    assert callable(muninn.purge_secrets_db)


def test_c1_internal_helpers_preserved():
    """Private re-exports used by historical tests."""
    import muninn
    for name in (
        "_generate_bridge_hook",
        "_generate_session_start_hook",
        "_register_repo",
    ):
        assert hasattr(muninn, name), f"private {name} missing in muninn"


# ── engine/core direct imports ──────────────────────────────


def test_c1_engine_core_install_directly_importable():
    """import muninn_install from engine/core/ works directly."""
    import importlib
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    mi = importlib.import_module("muninn_install")
    assert hasattr(mi, "install_hooks")
    assert hasattr(mi, "install_cron")


def test_c1_engine_core_secrets_directly_importable():
    """import muninn_secrets from engine/core/ works directly."""
    import importlib
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    ms = importlib.import_module("muninn_secrets")
    assert hasattr(ms, "scrub_secrets")
    assert hasattr(ms, "purge_secrets_db")


# ── Mirror in muninn/ ───────────────────────────────────────


def test_c1_mirror_install_exists():
    """muninn/muninn_install.py shim exists (matches SHIMMED_MODULES convention)
    and re-exports the install API."""
    p = REPO_ROOT / "muninn" / "muninn_install.py"
    assert p.exists(), f"missing mirror {p}"
    # Shim pattern — just needs to be loadable and re-export the canonical names.
    import importlib
    spec = importlib.util.spec_from_file_location("muninn_install_mirror", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "install_hooks")
    assert hasattr(mod, "install_cron")


def test_c1_mirror_secrets_exists():
    """muninn/muninn_secrets.py shim exists (matches SHIMMED_MODULES convention)."""
    p = REPO_ROOT / "muninn" / "muninn_secrets.py"
    assert p.exists(), f"missing mirror {p}"
    import importlib
    spec = importlib.util.spec_from_file_location("muninn_secrets_mirror", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "scrub_secrets")
    assert hasattr(mod, "purge_secrets_db")


# ── CLI entry point unchanged ────────────────────────────────


def test_c1_cli_entrypoint_unbroken():
    """`python -m muninn --help` still exits 0 and lists install-cron."""
    r = subprocess.run(
        [sys.executable, "-m", "muninn", "--help"],
        capture_output=True, timeout=15, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, (
        f"python -m muninn --help failed: exit {r.returncode}\n"
        f"stderr: {r.stderr.decode('utf-8', errors='replace')[-500:]}"
    )
    combined = r.stdout + r.stderr
    for cmd_token in (b"install-cron", b"scrub", b"feed"):
        assert cmd_token in combined, f"CLI usage missing {cmd_token!r}"
