"""CHUNK C13 (2026-05-19) — pipeline_trace reader for tests.

Helper to read `.muninn/pipeline_trace.jsonl` as a list of event dicts
so tests can assert that a specific pipeline event was emitted during
the test.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_trace_events(repo: str | Path) -> list[dict]:
    """Read `<repo>/.muninn/pipeline_trace.jsonl` and return the list of
    event records (parsed JSON objects). Returns [] if the file does
    not exist or contains no valid lines.

    Each event is a dict with keys: ts, pid, session_id, event, level, data.
    """
    p = Path(repo) / ".muninn" / "pipeline_trace.jsonl"
    if not p.exists():
        return []
    events: list[dict] = []
    try:
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return events


def has_event(events: list[dict], name: str) -> bool:
    """True if at least one event with the given dotted name exists."""
    return any(e.get("event") == name for e in events)


def count_events(events: list[dict], name: str) -> int:
    """How many times the given event fired."""
    return sum(1 for e in events if e.get("event") == name)


def events_by_prefix(events: list[dict], prefix: str) -> list[dict]:
    """All events whose name starts with `prefix` (e.g. `pipeline.scan.`)."""
    return [e for e in events if str(e.get("event", "")).startswith(prefix)]
