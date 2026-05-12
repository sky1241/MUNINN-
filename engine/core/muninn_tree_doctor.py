"""P3.1 split (2026-05-10) — `doctor()` extracted from muninn_tree.py:3267-3548.

Self-contained pre-flight environment check (Python/SQLite versions, deps,
.muninn directory layout, DB integrity, hook logs, optional layers, etc.).
Re-exported via `from muninn_tree_doctor import doctor` at end of
muninn_tree.py — external code keeps importing `from muninn_tree import doctor`.

No standalone shim in muninn/ (see test_chunk_d11_shim_drift.py engine_only).
"""
import json
import sys
from pathlib import Path

from muninn_tree import _m, cleanup_tmp_files


def doctor():
    """Pre-flight environment check — runs in <5s, green/red per check.

    G.6 (2026-05-12): when the target repo has no `.muninn/`, short-circuit
    to a 5-check pre-init smoke test (Python, SQLite, tiktoken, plus the
    "you haven't run init yet" hint). The full 25+ check sweep only fires
    once the repo is bootstrapped.
    """
    print("=== MUNINN DOCTOR ===\n")
    ok_count = 0
    fail_count = 0

    def _ok(label, detail=""):
        nonlocal ok_count
        ok_count += 1
        print(f"  [OK] {label}" + (f" — {detail}" if detail else ""))

    def _fail(label, detail=""):
        nonlocal fail_count
        fail_count += 1
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))

    def _warn(label, detail=""):
        print(f"  [WARN] {label}" + (f" — {detail}" if detail else ""))

    # G.6: pre-init short-circuit. If no .muninn/, run only the global deps
    # checks and tell the user to `muninn-mem init` first.
    repo_for_preinit = _m._REPO_PATH or Path(".").resolve()
    if not (repo_for_preinit / ".muninn").exists():
        # 1. Python
        v = sys.version_info
        if v >= (3, 10):
            _ok(f"Python {v.major}.{v.minor}.{v.micro}")
        else:
            _fail(f"Python {v.major}.{v.minor}.{v.micro}", "need >= 3.10")
        # 2. SQLite
        try:
            import sqlite3
            sv = sqlite3.sqlite_version
            if tuple(int(x) for x in sv.split(".")) >= (3, 24):
                _ok(f"SQLite {sv}")
            else:
                _fail(f"SQLite {sv}", "need >= 3.24 for WAL/UPSERT")
        except Exception as e:
            _fail("SQLite", str(e))
        # 3. tiktoken
        try:
            import tiktoken  # noqa: F401
            _ok("tiktoken installed")
        except ImportError:
            _fail("tiktoken missing", "pip install tiktoken")
        # 4. Anchor message — this is the action item
        _fail(
            f".muninn/ missing in {repo_for_preinit}",
            "Run `muninn-mem init` first to bootstrap this repo, then "
            "re-run doctor for the full sweep.",
        )
        print()
        print("  ====================")
        print(f"  Pre-init mode: {ok_count} deps OK, {fail_count} blocker(s).")
        print("  Once you've run `muninn-mem init`, re-run `muninn-mem doctor`")
        print("  for the full 22-check repo health sweep.")
        print("  ====================")
        return {"ok": ok_count, "fail": fail_count}

    # 1. Python version (>= 3.10)
    v = sys.version_info
    if v >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro}", "need >= 3.10")

    # 2. SQLite version (>= 3.24 for UPSERT, WAL)
    try:
        import sqlite3
        sv = sqlite3.sqlite_version
        if tuple(int(x) for x in sv.split(".")) >= (3, 24):
            _ok(f"SQLite {sv}")
        else:
            _fail(f"SQLite {sv}", "need >= 3.24 for WAL/UPSERT")
    except Exception as e:
        _fail("SQLite", str(e))

    # 3. tiktoken (required for token counting)
    try:
        import tiktoken
        _ok("tiktoken installed")
    except ImportError:
        _fail("tiktoken missing", "pip install tiktoken")

    # 4. cryptography (optional — for AES-256)
    try:
        from cryptography.fernet import Fernet
        _ok("cryptography installed (AES-256 ready)")
    except ImportError:
        _warn("cryptography not installed", "pip install cryptography (needed for AES-256)")

    # 5. anthropic (optional — for L9)
    try:
        import anthropic
        _ok("anthropic installed (L9 ready)")
    except ImportError:
        _warn("anthropic not installed", "pip install anthropic (optional, for L9)")

    # 6. .muninn directory
    repo = _m._REPO_PATH or Path(".").resolve()
    muninn_dir = repo / ".muninn"
    if muninn_dir.exists():
        _ok(f".muninn/ exists ({repo.name})")
    else:
        _fail(f".muninn/ missing in {repo}", "run: muninn-mem init")

    # 7. Write permissions
    if muninn_dir.exists():
        try:
            test_file = muninn_dir / ".doctor_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            _ok("Write permissions OK")
        except Exception as e:
            _fail("Write permissions", str(e))

    # 8. tree.json exists and is valid JSON
    tree_path = muninn_dir / "tree" / "tree.json" if muninn_dir.exists() else None
    if tree_path and tree_path.exists():
        try:
            data = json.loads(tree_path.read_text(encoding="utf-8"))
            n_nodes = len(data.get("nodes", {}))
            _ok(f"tree.json valid ({n_nodes} nodes)")
        except Exception as e:
            _fail("tree.json corrupted", str(e))
    elif muninn_dir.exists():
        # Try legacy path
        legacy = repo / "memory" / "tree.json"
        if legacy.exists():
            _ok(f"tree.json found (legacy path)")
        else:
            _warn("tree.json not found", "run: muninn-mem bootstrap <repo>")

    # 9. mycelium.db exists and is readable
    db_path = muninn_dir / "mycelium.db" if muninn_dir.exists() else None
    if db_path and db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            # Try both schemas: edges (SQLite tier3) or connections (legacy)
            try:
                count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            except sqlite3.OperationalError:
                count = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
            conn.close()
            _ok(f"mycelium.db valid ({count:,} connections)")
        except Exception as e:
            _fail("mycelium.db", str(e))
    elif muninn_dir.exists():
        _warn("mycelium.db not found", "run: muninn-mem bootstrap <repo>")

    # 10. Encoding check — scan repo for non-UTF8 files that could crash boot
    if muninn_dir.exists():
        bad_files = []
        scan_dirs = [muninn_dir / "tree", muninn_dir / "sessions"]
        for d in scan_dirs:
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.suffix in (".mn", ".json"):
                    try:
                        f.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, PermissionError):
                        bad_files.append(str(f.name))
        if bad_files:
            _fail(f"Encoding issues in {len(bad_files)} file(s)", ", ".join(bad_files[:5]))
        else:
            _ok("All .mn/.json files are valid UTF-8")

    # 11. Disk space (warn if < 500MB free)
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(repo))
        free_mb = free // (1024 * 1024)
        if free_mb > 500:
            _ok(f"Disk space: {free_mb:,} MB free")
        else:
            _warn(f"Disk space low: {free_mb} MB free", "< 500 MB")
    except Exception:
        pass  # Not critical

    # 12. RAM check (warn if < 512MB available)
    try:
        import psutil
        avail = psutil.virtual_memory().available // (1024 * 1024)
        if avail > 512:
            _ok(f"RAM: {avail:,} MB available")
        else:
            _warn(f"RAM low: {avail} MB available")
    except ImportError:
        pass  # psutil optional

    # 13. I4: Sync backend health
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        from sync_backend import sync_doctor
        sync_result = sync_doctor()
        for check, info in sync_result.items():
            if info.get("ok"):
                _ok(f"Sync {check}", info.get("detail", ""))
            else:
                _fail(f"Sync {check}", info.get("detail", ""))
    except Exception as e:
        _warn(f"Sync check skipped", str(e))

    # 14. Code formatters for Cube reconstruction
    try:
        from cube import check_formatters
    except ImportError:
        try:
            from engine.core.cube import check_formatters
        except ImportError:
            check_formatters = None
    if check_formatters:
        repo = _m._REPO_PATH or Path(".").resolve()
        fmt_status = check_formatters(repo_path=str(repo))
        any_missing = False
        for name, info in fmt_status.items():
            if info['needed'] and info['installed']:
                _ok(f"formatter: {name}", info['path'] or 'npx')
            elif info['needed'] and not info['installed']:
                if info.get('npx_fallback'):
                    _ok(f"formatter: {name}", "via npx (no global install)")
                else:
                    _warn(f"formatter: {name} NOT installed",
                           f"needed for {', '.join(info['extensions'])} — "
                           f"install: {info['install_cmd']}")
                    any_missing = True
        if any_missing:
            _warn("Run 'muninn-mem doctor --fix' to auto-install missing formatters")

    # CHUNK B11 (2026-05-08): integrate Phase A/B fixes into doctor.

    # 15. DB integrity check (CHUNK A3)
    if db_path and db_path.exists():
        try:
            if _m._CORE_DIR not in sys.path:
                sys.path.insert(0, _m._CORE_DIR)
            from mycelium_db import MyceliumDB
            mdb = MyceliumDB(db_path)
            ok, msg = mdb.check_integrity()
            if ok:
                _ok("DB integrity_check", "ok")
            else:
                _fail("DB integrity_check", msg[:120])
        except Exception as e:
            _warn("DB integrity_check skipped", str(e)[:120])

    # 16. Cleanup stale .tmp / .lock files (CHUNK B4)
    try:
        n_removed = cleanup_tmp_files()
        if n_removed > 0:
            _ok(f"cleanup: removed {n_removed} stale .tmp/.lock file(s)")
        else:
            _ok("cleanup: no stale .tmp/.lock files")
    except Exception as e:
        _warn("cleanup skipped", str(e)[:120])

    # 17. Hook log size (CHUNK A8 surface)
    try:
        log_path = Path.home() / ".muninn" / "hook_errors.log"
        if log_path.exists():
            size = log_path.stat().st_size
            size_mb = size / (1024 * 1024)
            if size > 1_000_000:
                _warn(f"hook_errors.log large: {size_mb:.1f} MB",
                      "consider archiving (rotation handles future growth)")
            else:
                _ok(f"hook_errors.log size: {size_mb:.2f} MB")
        else:
            _ok("hook_errors.log absent (clean)")
    except Exception as e:
        _warn("hook_errors.log check skipped", str(e)[:120])

    # 18. Optional layer status (CHUNK D12 wired E2)
    # Pre-fix: muninn_layers.health() was defined but never called in
    # production — flagged dead by test_brick19. Wiring it into doctor
    # surfaces lexicons/dedup/budget_select/L9 status to the user.
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        from muninn_layers import health as _layers_health
        h = _layers_health()
        for k, v in h.items():
            if v:
                _ok(f"layer.{k} active")
            else:
                _warn(f"layer.{k} unavailable")
    except Exception as e:
        _warn("layers.health() skipped", str(e)[:120])

    # 19. Anomalies log purge (CHUNK D7 wired E2)
    # Pre-fix: purge_old_anomalies() existed but no caller. Wiring it
    # into doctor cleans up ~/.muninn/anomalies.jsonl on every health
    # check (cheap operation; idempotent).
    try:
        if _m._CORE_DIR not in sys.path:
            sys.path.insert(0, _m._CORE_DIR)
        from cube_analysis import purge_old_anomalies
        anomalies_path = Path.home() / ".muninn" / "anomalies.jsonl"
        if anomalies_path.exists():
            n_purged = purge_old_anomalies(str(anomalies_path), max_age_days=7)
            if n_purged > 0:
                _ok(f"anomalies purged: {n_purged} stale entries removed (>7d)")
            else:
                _ok("anomalies.jsonl: no stale entries")
        else:
            _ok("anomalies.jsonl absent (clean)")
    except Exception as e:
        _warn("anomalies purge skipped", str(e)[:120])

    # CHUNK MCP D.5 (2026-05-12): pip-install health checks.
    # These catch regressions that ONLY manifest in pip-installed mode
    # (e.g. console scripts crashing because the shim chain's bare
    # `from X import *` can't resolve without engine/core/ shipped).
    # The BUG-091 fix that ships engine/* in the wheel (D.1, 2026-05-12)
    # would have been caught here on day 1.
    #
    # When invoked directly via `python3 engine/core/muninn.py doctor` from
    # a dev checkout (not via the pip-installed `muninn` binary), the import
    # paths look different — we downgrade FAIL to WARN in that case to avoid
    # false positives. Detection: this file lives outside site-packages.
    _is_pip_install = "site-packages" in __file__

    # 20. Console scripts importability — `muninn`, `mycelium`, `muninn-mcp`
    # all resolve to `module:attr` entry points. If any one fails to
    # import, the binary will crash at first invocation.
    for cmd_name, target in (
        ("muninn", "muninn._engine:main"),
        ("mycelium", "muninn.mycelium:main"),
        ("muninn-mcp", "muninn.mcp.server:main"),
    ):
        module_path, _, attr = target.partition(":")
        try:
            mod = __import__(module_path, fromlist=[attr])
            func = getattr(mod, attr, None)
            if callable(func):
                _ok(f"console_script {cmd_name}", target)
            else:
                (_fail if _is_pip_install else _warn)(
                    f"console_script {cmd_name}", f"{attr} not callable"
                )
        except ImportError as exc:
            # mcp is an optional extra — always warn
            if cmd_name == "muninn-mcp" and "mcp" in str(exc).lower():
                _warn(f"console_script {cmd_name}",
                       "pip install 'muninn-memory[mcp]' to enable")
            elif _is_pip_install:
                _fail(f"console_script {cmd_name}", f"import failed: {exc}")
            else:
                _warn(f"console_script {cmd_name}",
                       f"(dev mode — only meaningful via pip install): {exc}")

    # 21. engine.core package shipped — D.1 regression check. The shims
    # in muninn/*.py rely on `engine/core/` being on sys.path; that path
    # only exists inside the wheel if pyproject.toml's packages.find
    # includes "engine*". If a future packaging change drops it, surface
    # the breakage here instead of letting users hit ModuleNotFoundError.
    try:
        import engine.core  # noqa: F401
        _ok("engine.core package shipped (D.1 regression check)")
    except ImportError as exc:
        if _is_pip_install:
            _fail("engine.core not importable",
                   f"shim chain will crash — check pyproject [tool.setuptools.packages.find]: {exc}")
        else:
            _warn("engine.core not importable (dev mode — meaningful only via pip install)",
                  str(exc)[:120])

    # 22. mcp package (separate from anthropic, different extras).
    # `pip install muninn-memory[mcp]` adds the `mcp` lib needed by
    # the muninn-mcp console script and the muninn/mcp/server.py module.
    try:
        import mcp  # noqa: F401
        _ok("mcp installed (muninn-mcp ready)")
    except ImportError:
        _warn("mcp not installed",
              "pip install 'muninn-memory[mcp]' to enable Claude Code integration")

    # Summary
    print(f"\n{'='*40}")
    if fail_count == 0:
        print(f"  ALL GREEN — {ok_count} checks passed")
    else:
        print(f"  {fail_count} FAIL, {ok_count} OK — fix issues above")
    print(f"{'='*40}")

    return {"ok": ok_count, "fail": fail_count}
