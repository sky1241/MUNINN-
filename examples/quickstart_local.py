"""quickstart_local.py — see Muninn grow a mycelium from one transcript.

Wall-time: ~30s. No API key, no MCP server, no Claude Code needed.

Demonstrates the pure-local data flow:
    repo path  →  muninn init       (.muninn/ layout)
              →  observe transcript (mycelium learns word co-occurrences)
              →  recall query       (return concepts connected to a seed)

Pick any directory with some text/code in it via $MUNINN_DEMO_REPO.
Defaults to /tmp/muninn-quickstart (created if missing).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _ensure_repo() -> Path:
    """Pick a target repo. Use $MUNINN_DEMO_REPO if set, else /tmp/quickstart."""
    env = os.environ.get("MUNINN_DEMO_REPO")
    if env:
        repo = Path(env).expanduser().resolve()
        if not repo.exists():
            print(f"$MUNINN_DEMO_REPO points to non-existent path: {repo}")
            sys.exit(1)
        return repo
    repo = Path(tempfile.gettempdir()) / "muninn-quickstart"
    repo.mkdir(exist_ok=True)
    # Seed with a tiny "fake codebase" so the mycelium has something to learn from
    (repo / "README.md").write_text(
        "# Demo project\n\n"
        "Compression engine for LLM memory. Uses a mycelium of concept "
        "co-occurrences plus a fractal tree of compressed sessions.\n",
        encoding="utf-8",
    )
    (repo / "main.py").write_text(
        '"""Compression entry point."""\n'
        "def compress(text):\n"
        "    return text  # placeholder\n",
        encoding="utf-8",
    )
    return repo


def _run(label: str, cmd: list[str], cwd: Path) -> None:
    """Run a muninn subcommand, print a header + tail of output."""
    print(f"\n─── {label} ───")
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120)
    out = r.stdout.strip()
    err = r.stderr.strip()
    if out:
        # Print only the last 15 lines to keep noise down
        tail = "\n".join(out.splitlines()[-15:])
        print(tail)
    if r.returncode != 0:
        print(f"[err] {err[:400]}")
        sys.exit(r.returncode)


def main() -> None:
    repo = _ensure_repo()
    print(f"Target repo: {repo}")

    # Use `python -m muninn._engine` so the example works in BOTH modes :
    #   - dev checkout (no console script installed) — picks up the module
    #   - pip-installed (post `pip install muninn-memory`) — same code path
    # The pip-installed console script is `muninn-mem` (renamed in E.3 to
    # avoid PyPI collision with `muninn` 7.2.1), but we don't depend on it
    # being on $PATH here.
    muninn = [sys.executable, "-m", "muninn._engine"]

    # 1. Initialize Muninn in the repo (creates .muninn/, installs hooks)
    _run("STEP 1 — muninn init", [*muninn, "init"], cwd=repo)

    # 2. Show the layout that was created
    _run("STEP 2 — muninn status", [*muninn, "status"], cwd=repo)

    # 3. Bootstrap mycelium from the repo's source files
    _run("STEP 3 — muninn bootstrap", [*muninn, "bootstrap", str(repo)], cwd=repo)

    # 4. Query the mycelium for concepts connected to "compression"
    _run("STEP 4 — muninn recall 'compression'", [*muninn, "recall", "compression"], cwd=repo)

    print("\n✓ Done. Next steps:")
    print(f"  - Inspect {repo}/.muninn/ (tree.json, mycelium.db, sessions/)")
    print("  - Try `muninn doctor` to verify your install")
    print("  - Try `mcp_recall_demo.py` to see the MCP-style API")


if __name__ == "__main__":
    main()
