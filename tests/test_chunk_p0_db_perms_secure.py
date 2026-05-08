"""CHUNK P0 — file permissions on Muninn-managed sensitive files.

Pre-fix: every file under .muninn/ was created with the user's default
umask. On most Linux servers the default umask is 022 → new files land
in mode 0644 (world-readable). For a tech-org installing Muninn on a
multi-user host this means any other user can `cat ~/.muninn/*.db`
and read learned-context secrets.

Post-fix: a centralised secure_perms(path, mode=0o600) helper in
_secrets.py is called at every creation site (sqlite3.connect, atomic
JSON/text write, anomalies.jsonl append, hook log handler, opportunistic
re-chmod when an existing DB is opened).

Sites covered:
  - engine/core/cube.py:846              CubeStorage.__init__
  - engine/core/mycelium_db.py:76        MyceliumDB.__init__
  - engine/core/mycelium_db.py:1207      TranslationCache._init_db
  - engine/core/mycelium.py:98           Mycelium load (opportunistic)
  - engine/core/muninn_tree.py:341       _atomic_json_write
  - engine/core/muninn_tree.py:363       _atomic_text_write
  - engine/core/muninn_tree.py:save_tree TREE_META write
  - engine/core/cube_analysis.py:1799    record_anomaly append
  - engine/core/_hook_logger.py:50       RotatingFileHandler

Source: docs/BATTLE_PLAN_FINAL_2026-05-08.md §P0
"""
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _mode(p: Path) -> int:
    return p.stat().st_mode & 0o777


# ── Helper itself ───────────────────────────────────────────


def test_secure_perms_helper_chmods_to_0600(tmp_path):
    from _secrets import secure_perms

    f = tmp_path / "secret.json"
    f.write_text("hello")
    os.chmod(f, 0o644)
    assert _mode(f) == 0o644, "precondition failed (umask noise)"

    secure_perms(f)
    assert _mode(f) == 0o600, f"expected 0o600 after secure_perms, got {oct(_mode(f))}"


def test_secure_perms_helper_swallows_missing_path(tmp_path):
    """Must not raise on non-existent path (callers don't always check)."""
    from _secrets import secure_perms

    secure_perms(tmp_path / "nope.txt")  # No exception expected.


def test_secure_perms_secures_parent_directory_under_home(tmp_path, monkeypatch):
    """When the file lives under HOME, the parent should chmod to 0o700."""
    from _secrets import secure_perms

    # Pretend tmp_path is HOME so the helper considers parent as protected.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    os.chmod(sub, 0o755)
    f = sub / "x"
    f.write_text("h")
    secure_perms(f)
    assert _mode(sub) == 0o700, f"parent should be 0o700, got {oct(_mode(sub))}"


def test_secure_perms_does_not_touch_system_directories(tmp_path, monkeypatch):
    """Outside HOME we must NOT chmod the parent (e.g. /tmp, /etc)."""
    from _secrets import secure_perms

    # Simulate "HOME is elsewhere" so tmp_path/.. is treated as system.
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    f = tmp_path / "y"
    f.write_text("h")
    initial_parent_mode = _mode(tmp_path)
    secure_perms(f)
    assert _mode(tmp_path) == initial_parent_mode, (
        "secure_perms must not chmod parent dirs outside HOME"
    )


# ── Real call sites ──────────────────────────────────────────


def test_atomic_json_write_creates_0600_file(tmp_path):
    """muninn_tree._atomic_json_write must produce a 0o600 file."""
    import muninn_tree

    target = tmp_path / "nested" / "out.json"
    muninn_tree._atomic_json_write(target, {"x": 1})
    assert target.exists()
    assert _mode(target) == 0o600, (
        f"_atomic_json_write produced mode {oct(_mode(target))}; expected 0o600"
    )


def test_atomic_text_write_creates_0600_file(tmp_path):
    """muninn_tree._atomic_text_write must produce a 0o600 file."""
    import muninn_tree

    target = tmp_path / "nested" / "out.mn"
    muninn_tree._atomic_text_write(target, "session content")
    assert target.exists()
    assert _mode(target) == 0o600, (
        f"_atomic_text_write produced mode {oct(_mode(target))}; expected 0o600"
    )


def test_mycelium_db_init_chmods_to_0600(tmp_path):
    """MyceliumDB(...) must chmod the new .db file to 0o600."""
    import mycelium_db

    db_path = tmp_path / "myc.db"
    db = mycelium_db.MyceliumDB(db_path)
    try:
        assert db_path.exists()
        assert _mode(db_path) == 0o600, (
            f"mycelium.db created with mode {oct(_mode(db_path))}; expected 0o600"
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


def test_record_anomaly_chmods_jsonl(tmp_path):
    """cube_analysis.record_anomaly must chmod anomalies.jsonl to 0o600."""
    import cube_analysis

    target = tmp_path / "anomalies.jsonl"
    cube_analysis.record_anomaly(
        str(target), "fake/file.py",
        {"temperature": 0.9}, ["cube_id_1"], label="test"
    )
    assert target.exists()
    assert _mode(target) == 0o600, (
        f"anomalies.jsonl created with mode {oct(_mode(target))}; expected 0o600"
    )
