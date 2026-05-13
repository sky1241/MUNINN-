"""H.0 — Garde-fou anti-orphan : système immunitaire CI.

Each test asserts a different facet of "no dormant code shipped" :
  - every engine/core/*.py module is imported by shipped code
  - every muninn/ui/*.py module is referenced inside the UI tree
  - every env var documented in CLAUDE.md is actually read by the engine
  - every argparse `add_argument(...)` is consumed later in `main()`
  - every CLI choice has a `if args.command == "X":` handler
  - every .claude/hooks/*.py file is referenced in settings.local.json

These are HARDENED to be RED today (orphans exist) and turn GREEN once
H.1-H.7 wire the dormant features. NEVER `@pytest.mark.skip` them —
the RED state is THE signal that drives Phase H.

Whitelists capture truly intentional dormants (standalone Windows
scripts, audit reserves, etc.).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Modules NOT required to be imported by shipped code. Reason in comment.
WHITELIST_DORMANT_MODULES = {
    "watchdog.py",          # standalone polling script for Windows; Linux N/A
    "__init__.py",          # package marker, no callable surface
    "__main__.py",          # python -m entry; not imported by name
    # Files in `experimental/` are auto-whitelisted (see _is_experimental).
}

# UI modules dormant by design (Phase J refactor will decide wire vs delete).
WHITELIST_DORMANT_UI_MODULES = {
    "_tree_engine.py",     # legacy tree rendering helpers, kept while tree_view stabilizes
    "_tree_renderer.py",   # same family, marked underscore-private to signal "internal/dormant"
    "about_dialog.py",     # main_window references `self._about_dialog` but never imports —
                           # planned Help menu integration in Phase J
    "__init__.py",
    "__main__.py",
}

# Hooks NOT required to be wired in settings.local.json (audit reserves).
# 2026-05-13 chunk E (Sky decision A) : config_change_hook +
# notification_audit_hook WIRED by default — removed from this whitelist.
WHITELIST_DORMANT_HOOKS = {
    # I.3 (2026-05-12): post_tool_use_edit_log is enterprise scaffolding;
    # the intended audit-viewer consumer was never implemented. Kept
    # opt-in for Phase 3 compliance pitch. Sky activates manually.
    "post_tool_use_edit_log.py",
}

# Env vars documented in CLAUDE.md but legitimately NOT read by engine code
# (referenced only by external systems, e.g., test harness env contracts).
WHITELIST_DOC_ONLY_ENV_VARS = {
    "MUNINN_RUN_REAL_API_TESTS",  # pytest skip marker, read in test files
    "MUNINN_RUN_REAL_LLM_TESTS",  # same
    "MUNINN_RUN_E2E",             # e2e pytest opt-in
    "MUNINN_TEST_REPOS",          # test harness only
    "MUNINN_BENCH_N",             # benchmark scripts
    "MUNINN_EVAL_MODE",           # eval harness
    "MUNINN_EVAL_MODEL",          # eval harness
    "MUNINN_EVAL_RUNS",           # eval harness
    "MUNINN_EVAL_ONLY_IDS",       # eval harness
    "MUNINN_DEMO_REPO",           # examples/ only
}


def _shipped_text() -> str:
    """Cat all shipped (non-test) Python text into one big string for grep."""
    chunks: list[str] = []
    for root in ("engine", "muninn"):
        for py in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                chunks.append(py.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    for hk in (REPO_ROOT / ".claude" / "hooks").glob("*.py"):
        try:
            chunks.append(hk.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def _is_experimental(path: Path) -> bool:
    return "experimental" in path.parts


def test_h0_no_orphan_engine_module() -> None:
    """Each engine/core/*.py must be imported by at least one shipped file
    (engine/, muninn/, .claude/hooks/). Whitelist for standalone scripts."""
    body = _shipped_text()
    orphans: list[str] = []
    for py in (REPO_ROOT / "engine" / "core").glob("*.py"):
        if py.name in WHITELIST_DORMANT_MODULES:
            continue
        if _is_experimental(py):
            continue
        stem = py.stem
        # Look for `import <stem>` or `from <stem> import ...` or
        # quoted module path that includes the stem.
        patterns = [
            rf"\bimport\s+{re.escape(stem)}\b",
            rf"\bfrom\s+{re.escape(stem)}\b",
            rf"\bfrom\s+engine\.core\.{re.escape(stem)}\b",
            rf'"{re.escape(stem)}"',
            rf"'{re.escape(stem)}'",
        ]
        if not any(re.search(p, body) for p in patterns):
            orphans.append(py.name)
    if orphans:
        pytest.fail(
            f"{len(orphans)} engine/core orphan module(s):\n  "
            + "\n  ".join(orphans)
            + "\n\nAdd to WHITELIST_DORMANT_MODULES or wire them in (H.1-H.7)."
        )


def test_h0_no_orphan_ui_module() -> None:
    """Each muninn/ui/*.py must be referenced by main_window.py or another ui/ file.

    H.2 (2026-05-12) wired the entry point. Truly dormant UI helpers are in
    WHITELIST_DORMANT_UI_MODULES with rationale.
    """
    ui_dir = REPO_ROOT / "muninn" / "ui"
    if not ui_dir.exists():
        pytest.skip("muninn/ui/ missing")
    # Cat all UI source
    ui_text = ""
    for f in ui_dir.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        ui_text += f.read_text(encoding="utf-8", errors="ignore") + "\n"
    orphans: list[str] = []
    for py in ui_dir.rglob("*.py"):
        if py.name in WHITELIST_DORMANT_UI_MODULES:
            continue
        if py.name == "main_window.py":
            continue  # the entry point itself
        if "__pycache__" in py.parts:
            continue
        stem = py.stem
        if not re.search(rf"\b{re.escape(stem)}\b", ui_text):
            orphans.append(str(py.relative_to(REPO_ROOT)))
    if orphans:
        pytest.fail(
            f"{len(orphans)} UI orphan module(s):\n  " + "\n  ".join(orphans)
            + "\n\nAdd to WHITELIST_DORMANT_UI_MODULES (with rationale) or wire them in."
        )


def test_h0_all_env_vars_documented_read() -> None:
    """Each MUNINN_* env var in CLAUDE.md table must be read in shipped code
    (or test code for harness-only vars in WHITELIST_DOC_ONLY_ENV_VARS)."""
    claude_md = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    # Only tokens that appear inside the markdown table (lines starting with
    # `| \``), to avoid matching XML tag names like `<MUNINN_RULES>`.
    documented: set[str] = set()
    for line in claude_md.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        for hit in re.findall(r"`(MUNINN_[A-Z][A-Z0-9_]*)`", line):
            documented.add(hit)
    body = _shipped_text()
    test_body = ""
    for py in (REPO_ROOT / "tests").rglob("*.py"):
        try:
            test_body += py.read_text(encoding="utf-8", errors="ignore") + "\n"
        except OSError:
            continue
    missing: list[str] = []
    for var in sorted(documented):
        if var in WHITELIST_DOC_ONLY_ENV_VARS:
            # at least the test harness must reference it
            if var not in test_body and var not in body:
                missing.append(f"{var} (whitelisted-doc-only, but no caller)")
            continue
        if var not in body:
            missing.append(var)
    if missing:
        pytest.fail(
            f"{len(missing)} env var(s) documented but unread:\n  "
            + "\n  ".join(missing)
        )


def test_h0_all_argparse_flags_consumed() -> None:
    """For each `add_argument("--X")` in engine/core/muninn.py, assert
    `args.X` or `args["X"]` appears later in the same file."""
    muninn_py = (REPO_ROOT / "engine" / "core" / "muninn.py").read_text(encoding="utf-8")
    # Strip dashes for attribute lookup. dest defaults to longest --flag stripped of leading --.
    flag_re = re.compile(r'add_argument\(\s*"(--[a-zA-Z][\w-]*)"')
    flags = flag_re.findall(muninn_py)
    unused: list[str] = []
    for flag in flags:
        dest = flag.lstrip("-").replace("-", "_")
        if not re.search(rf"\bargs\.{re.escape(dest)}\b", muninn_py):
            # also accept getattr(args, "X")
            if not re.search(rf'getattr\(\s*args\s*,\s*[\'"]{re.escape(dest)}[\'"]',
                             muninn_py):
                unused.append(flag)
    if unused:
        pytest.fail(
            f"{len(unused)} argparse flag(s) declared but unused in main():\n  "
            + "\n  ".join(unused)
        )


def test_h0_all_cli_commands_have_handler() -> None:
    """For each `choices=[...]` of the 'command' positional in muninn.py,
    assert there's a handler `if args.command == "X":` somewhere in main()."""
    muninn_py = (REPO_ROOT / "engine" / "core" / "muninn.py").read_text(encoding="utf-8")
    # Find first add_argument("command", ..., choices=[...]) — use AST for safety.
    tree = ast.parse(muninn_py)
    choices: list[str] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
                and node.args and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "command"):
            for kw in node.keywords:
                if kw.arg == "choices" and isinstance(kw.value, ast.List):
                    choices = [
                        e.value for e in kw.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    ]
                    break
            break
    if not choices:
        pytest.skip("Could not parse argparse choices for 'command'")
    no_handler: list[str] = []
    for cmd in choices:
        if not re.search(rf'args\.command\s*==\s*[\'"]{re.escape(cmd)}[\'"]',
                         muninn_py):
            no_handler.append(cmd)
    if no_handler:
        pytest.fail(
            f"{len(no_handler)} CLI command(s) declared but no handler:\n  "
            + "\n  ".join(no_handler)
        )


def test_h0_all_hooks_on_disk_registered() -> None:
    """Each .claude/hooks/*.py file must be referenced by settings.local.json
    (unless it's in WHITELIST_DORMANT_HOOKS).

    I.5 (2026-05-13) : xfail removed after Sky ran `muninn-mem init` to
    migrate his live settings.local.json. The 3 defensive PreToolUse hooks
    (pre_tool_use_bash_{destructive,secrets,edit_hardcode}) are now wired.
    Note : settings.local.json is gitignored → in CI this test will SKIP
    (file absent in clean checkout). Only Sky's local run validates it.
    """
    hooks_dir = REPO_ROOT / ".claude" / "hooks"
    if not hooks_dir.exists():
        pytest.skip(".claude/hooks/ missing")
    settings_path = REPO_ROOT / ".claude" / "settings.local.json"
    if not settings_path.exists():
        pytest.skip(".claude/settings.local.json missing")
    settings_text = settings_path.read_text(encoding="utf-8")
    orphans: list[str] = []
    for hk in hooks_dir.glob("*.py"):
        if hk.name in WHITELIST_DORMANT_HOOKS:
            continue
        if hk.name not in settings_text:
            orphans.append(hk.name)
    if orphans:
        pytest.fail(
            f"{len(orphans)} hook(s) on disk but not in settings.local.json:\n  "
            + "\n  ".join(orphans)
            + "\n\nAdd to WHITELIST_DORMANT_HOOKS or wire them in (H.6)."
        )
