#!/usr/bin/env python3
"""PreToolUse hook on Task — throttle subagent bursts to protect Anthropic quota.

Sky burned 58% of his weekly Max-20x quota on 2026-05-14 when a session
spawned 342 Explore subagents in one go. Each subagent does ~18 sequential
tool calls with a 180K-token context window. 342 x 18 x 180K = ~1.1B tokens
billed for one session.

This hook plafonne to MAX_TASK_PER_WINDOW Task tool calls per WINDOW_SECONDS.
When breached, exit 2 + stderr message blocks the call (Claude Code spec).

Override via env vars (set in shell or settings.json env block):
    MUNINN_TASK_MAX        max subagents per window (default 3)
    MUNINN_TASK_WINDOW     window length in seconds (default 60)

State file: /tmp/muninn_task_throttle.json — list of unix timestamps.
"""
import json
import os
import sys
import time
from pathlib import Path

# --- PIPELINE_TRACE block (removable, see docs/PIPELINE_TRACE_REMOVAL.md) ---  # PIPELINE_TRACE
try:  # PIPELINE_TRACE
    _pt_dir = str(Path(__file__).resolve().parent.parent.parent / "engine" / "core")  # PIPELINE_TRACE
    if _pt_dir not in sys.path: sys.path.insert(0, _pt_dir)  # PIPELINE_TRACE
    from pipeline_trace import log_event  # PIPELINE_TRACE
except Exception:  # PIPELINE_TRACE
    def log_event(*a, **kw): pass  # PIPELINE_TRACE
# --- end PIPELINE_TRACE block ---  # PIPELINE_TRACE

STATE_FILE = Path("/tmp/muninn_task_throttle.json")
MAX_TASK_PER_WINDOW = int(os.environ.get("MUNINN_TASK_MAX", "3"))
WINDOW_SECONDS = int(os.environ.get("MUNINN_TASK_WINDOW", "60"))


def _load_history():
    if not STATE_FILE.exists():
        return []
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError, ValueError):
        return []


def _save_history(timestamps):
    try:
        STATE_FILE.write_text(json.dumps(timestamps), encoding="utf-8")
    except OSError:
        pass


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        sys.exit(0)

    if not isinstance(payload, dict):
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name != "Task":
        sys.exit(0)

    now = time.time()
    history = _load_history()
    recent = [t for t in history if isinstance(t, (int, float)) and (now - t) < WINDOW_SECONDS]
    log_event("pipeline.hook.pre_task_throttle.begin", {"recent_count": len(recent), "max": MAX_TASK_PER_WINDOW, "window_s": WINDOW_SECONDS})  # PIPELINE_TRACE

    if len(recent) >= MAX_TASK_PER_WINDOW:
        oldest = min(recent)
        wait_s = int(WINDOW_SECONDS - (now - oldest)) + 1
        log_event("pipeline.hook.pre_task_throttle.blocked", {"recent_count": len(recent), "wait_s": wait_s}, level="warn")  # PIPELINE_TRACE
        sys.stderr.write(
            f"[MUNINN THROTTLE] Refused Task call: {len(recent)} subagents "
            f"already spawned in the last {WINDOW_SECONDS}s "
            f"(max={MAX_TASK_PER_WINDOW}).\n"
            f"On 2026-05-14, 342 Explore subagents in one session burned "
            f"~58% of Sky's weekly Anthropic quota. This hook protects against\n"
            f"that pattern. Wait ~{wait_s}s before retrying, or do the work "
            f"inline (Read/Grep/Bash) instead of delegating to a subagent.\n"
            f"Override: export MUNINN_TASK_MAX=<N> MUNINN_TASK_WINDOW=<sec>\n"
        )
        sys.exit(2)

    recent.append(now)
    _save_history(recent)
    log_event("pipeline.hook.pre_task_throttle.allowed", {"recent_count": len(recent)})  # PIPELINE_TRACE
    sys.exit(0)


if __name__ == "__main__":
    main()
