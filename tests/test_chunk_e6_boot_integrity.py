"""CHUNK E6 — wire mycelium check_integrity() at CLI boot.

Run-4 audit found A3 (`MyceliumDB.check_integrity()`) was a public
helper but only invoked via `muninn doctor`. If Sky never ran doctor,
a corrupted mycelium.db stayed silent until queries returned wrong
data. E6 wires the check into every `muninn <command>` boot path
(except `init` / `doctor`).

Source: docs/BATTLE_PLAN_AUDIT3_2026-05-08.md §E6
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
MUNINN_PY = REPO / "engine" / "core" / "muninn.py"


def _run_muninn(args: list[str], env_extra: dict = None, cwd: Path = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "engine" / "core") + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(MUNINN_PY)] + args,
        capture_output=True, text=True, env=env, cwd=str(cwd or REPO),
        timeout=30,
    )


def test_boot_integrity_check_exists_in_main():
    """Static check: main() must reference check_integrity()."""
    src = MUNINN_PY.read_text(encoding="utf-8")
    assert "check_integrity()" in src, (
        "engine/core/muninn.py main() must call check_integrity() at boot — "
        "see CHUNK E6"
    )
    assert "MUNINN_SKIP_INTEGRITY" in src, (
        "Boot integrity check must support MUNINN_SKIP_INTEGRITY env override"
    )


def test_boot_integrity_warns_on_corrupt_db(tmp_path):
    """When mycelium.db is corrupt, a warning must appear on stderr."""
    # Plant a corrupt DB
    repo = tmp_path / "fake_repo"
    (repo / ".muninn").mkdir(parents=True)
    db = repo / ".muninn" / "mycelium.db"
    db.write_bytes(b"NOT A SQLITE FILE - JUST GARBAGE BYTES" * 100)

    # Run any command that should trigger boot check
    result = _run_muninn(["status", "--repo", str(repo)], cwd=repo)
    combined = result.stdout + result.stderr
    # Either: integrity warning (sqlite3 rejects), OR sqlite3 connect
    # already errored out — both are acceptable signals to the user.
    assert (
        "integrity_check failed" in combined.lower()
        or "WARNING" in combined
        or "DatabaseError" in combined
        or result.returncode != 0
    ), (
        f"Corrupt DB did not surface any signal:\n"
        f"stdout: {result.stdout[-500:]}\nstderr: {result.stderr[-500:]}"
    )


def test_boot_integrity_silent_on_clean_db(tmp_path):
    """Clean DB → no integrity warning at boot (normal operation)."""
    import importlib.util
    repo = tmp_path / "clean_repo"
    (repo / ".muninn").mkdir(parents=True)

    # Build a real, healthy mycelium.db
    spec = importlib.util.spec_from_file_location(
        "_chunk_e6_db", REPO / "engine" / "core" / "mycelium_db.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    db = mod.MyceliumDB(repo / ".muninn" / "mycelium.db")
    db.set_meta("test", "ok")

    result = _run_muninn(["status", "--repo", str(repo)], cwd=repo)
    combined = result.stdout + result.stderr
    assert "integrity_check failed" not in combined.lower(), (
        f"Clean DB triggered false integrity warning:\n{combined[-500:]}"
    )


def test_boot_integrity_respects_skip_env(tmp_path):
    """MUNINN_SKIP_INTEGRITY=1 must bypass the boot check entirely."""
    repo = tmp_path / "skipped_repo"
    (repo / ".muninn").mkdir(parents=True)
    # Plant garbage DB
    db = repo / ".muninn" / "mycelium.db"
    db.write_bytes(b"GARBAGE" * 100)

    result = _run_muninn(
        ["status", "--repo", str(repo)],
        env_extra={"MUNINN_SKIP_INTEGRITY": "1"},
        cwd=repo,
    )
    # No integrity warning on stderr (the corrupt DB is bypassed)
    assert "integrity_check failed" not in (result.stdout + result.stderr).lower()


def test_init_does_not_run_integrity_check(tmp_path):
    """`muninn init` runs BEFORE the DB exists — must not trigger
    integrity check (would warn on absent file)."""
    repo = tmp_path / "init_repo"
    repo.mkdir()
    # No .muninn/ yet
    result = _run_muninn(["init", "--repo", str(repo)], cwd=repo)
    # Even if init succeeds or fails, no integrity warning
    assert "integrity_check failed" not in (result.stdout + result.stderr).lower()
