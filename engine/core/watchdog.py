"""Muninn Watchdog — runs feed --watch on all registered repos.

Designed to be called by Windows Task Scheduler every 15 minutes.
Does nothing if no conversations have changed since last check.
"""
import json
import subprocess
import sys
from pathlib import Path

# Use python.exe (not pythonw.exe) for subprocess calls — muninn.py needs stdout
_exe_dir = Path(sys.executable).parent
PYTHON = str(_exe_dir / "python.exe") if (_exe_dir / "python.exe").exists() else sys.executable
MUNINN = Path(__file__).resolve().parent / "muninn.py"
REPOS_PATH = Path.home() / ".muninn" / "repos.json"


def main():
    if not MUNINN.exists():
        print(f"WATCHDOG: muninn.py not found at {MUNINN}", file=sys.stderr)
        return

    if not REPOS_PATH.exists():
        return

    try:
        data = json.loads(REPOS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    repos = data.get("repos", {})
    for name, path in repos.items():
        repo = Path(path)
        if not (repo / ".muninn").exists():
            continue
        try:
            result = subprocess.run(
                [PYTHON, str(MUNINN), "feed", "--watch", "--repo", str(repo)],
                timeout=300,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"WATCHDOG: {name} failed (exit {result.returncode}): {result.stderr[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"WATCHDOG: {name} timed out (5min)", file=sys.stderr)
        except Exception as e:
            print(f"WATCHDOG: {name} error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
