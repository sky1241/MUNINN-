"""Pipeline trace — observability scaffolding (TEMPORARY).

Every line emitted lives in `<repo>/.muninn/pipeline_trace.jsonl`. A live
`tail -f` on that file shows exactly which code paths execute when Sky
performs an action (UI click, hook fire, CLI command). The goal is to
catch drifts between what the docs promise and what the runtime does.

This module is INSTRUMENTATION ONLY. It is not engine logic. All call
sites added across the codebase are marked with the trailing comment
`# PIPELINE_TRACE` for grep-based removal. See
`docs/PIPELINE_TRACE_REMOVAL.md` for the per-chunk removal manifest.

Removal (2 paths):
  1. Hard:  git revert each chunk commit in reverse order.
  2. Soft:  grep -rln "# PIPELINE_TRACE" --include="*.py" \
              | xargs sed -i '/# PIPELINE_TRACE/d'
            rm engine/core/pipeline_trace.py docs/PIPELINE_TRACE_REMOVAL.md

Hot-path constraint: hooks have a <500ms budget. `log_event(...)` must
stay under 1ms per call. Measurement at chunk 0 commit time:
  see commit message for the perf numbers from `_self_bench()`.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO_CACHE: Path | None = None
_TRACE_PATH_CACHE: Path | None = None
_DISABLED: bool = os.environ.get("PIPELINE_TRACE_DISABLE") == "1"


def _resolve_repo() -> Path | None:
    """Resolve the repo root once (cached). Returns None if no .muninn/
    can be found — caller becomes a no-op in that case."""
    global _REPO_CACHE
    if _REPO_CACHE is not None:
        return _REPO_CACHE
    candidates: list[Path] = []
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("MUNINN_REPO")
    if env_dir:
        candidates.append(Path(env_dir))
    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    candidates.extend(cwd.parents)
    for cand in candidates:
        if (cand / ".muninn").exists():
            _REPO_CACHE = cand
            return cand
    return None


def _resolve_trace_path() -> Path | None:
    global _TRACE_PATH_CACHE
    if _TRACE_PATH_CACHE is not None:
        return _TRACE_PATH_CACHE
    repo = _resolve_repo()
    if repo is None:
        return None
    muninn_dir = repo / ".muninn"
    try:
        muninn_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    path = muninn_dir / "pipeline_trace.jsonl"
    _TRACE_PATH_CACHE = path
    return path


def log_event(name: str, data: dict[str, Any] | None = None, level: str = "info") -> None:
    """Append one JSONL line to <repo>/.muninn/pipeline_trace.jsonl.

    Silently no-ops if:
      - the trace file path cannot be resolved (no .muninn/ around)
      - the env var PIPELINE_TRACE_DISABLE=1 was set at module import
      - any IO error during write (we must NEVER raise to the caller —
        a trace failure cannot break the hook or engine path it wraps)

    Args:
        name: event name, dotted convention "pipeline.<area>.<phase>"
              e.g. "pipeline.hook.bridge.begin"
        data: arbitrary JSON-serializable payload
        level: "info" | "warn" | "error" — purely advisory
    """
    if _DISABLED:
        return
    path = _resolve_trace_path()
    if path is None:
        return
    record = {
        "ts": time.time(),
        "pid": os.getpid(),
        "session_id": os.environ.get("CLAUDE_SESSION_ID", ""),
        "event": name,
        "level": level,
        "data": data or {},
    }
    try:
        line = json.dumps(record, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        line = json.dumps({**record, "data": {"_unserializable": True}})
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except OSError:
        return


def _self_bench(n: int = 1000) -> dict[str, float]:
    """Internal: measure per-call cost on the current host. Returns
    avg/p50/p99 microseconds. Called from `python -m engine.core.pipeline_trace`."""
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        log_event("pipeline.selfbench", {"i": _})
        samples.append((time.perf_counter() - t0) * 1e6)
    samples.sort()
    return {
        "n": float(n),
        "avg_us": sum(samples) / n,
        "p50_us": samples[n // 2],
        "p99_us": samples[int(n * 0.99)],
        "max_us": samples[-1],
    }


if __name__ == "__main__":
    repo = _resolve_repo()
    path = _resolve_trace_path()
    print(f"repo:  {repo}", file=sys.stderr)
    print(f"trace: {path}", file=sys.stderr)
    if path is None:
        print("no .muninn/ resolved — log_event is a no-op here", file=sys.stderr)
        sys.exit(1)
    bench = _self_bench(1000)
    print(json.dumps(bench, indent=2))
