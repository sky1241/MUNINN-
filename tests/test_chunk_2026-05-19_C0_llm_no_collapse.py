"""CHUNK C0 (2026-05-19) — LLM mode collapse fix.

Pre-fix: qwen2.5-coder:1.5b (and even :7b on a single host) looped on
single tokens ("returning, returning, returning…") in the reco terminal,
because Ollama defaults to no repetition_penalty + temperature=0.0
(fully deterministic — once it picks a hot token, it picks the same one
forever).

Fix: OllamaProvider sets repeat_penalty=1.15 and temperature=0.2 by
default in every request payload (generate / stream / fim_generate).
Tunable via env vars MUNINN_LLM_REPEAT_PENALTY and MUNINN_LLM_TEMPERATURE
for legacy fallback (set both to "1.0"/"0.0" to revert).

Locks the behavior so future refactors don't silently drop the options.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Make engine/core importable for bare imports (cube_providers uses them).
REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _fresh_cube_providers(monkeypatch, repeat: str | None, temp: str | None):
    """Force re-evaluation of module-level env-driven constants.

    The constants are read at import time, so toggling env vars after
    import has no effect. This helper sets the env and reloads the
    module so the test sees the fresh values.
    """
    if repeat is None:
        monkeypatch.delenv("MUNINN_LLM_REPEAT_PENALTY", raising=False)
    else:
        monkeypatch.setenv("MUNINN_LLM_REPEAT_PENALTY", repeat)
    if temp is None:
        monkeypatch.delenv("MUNINN_LLM_TEMPERATURE", raising=False)
    else:
        monkeypatch.setenv("MUNINN_LLM_TEMPERATURE", temp)
    # Pop and reimport to re-execute the module-level reads.
    sys.modules.pop("cube_providers", None)
    sys.modules.pop("engine.core.cube_providers", None)
    return importlib.import_module("cube_providers")


def _capture_payload(provider, monkeypatch):
    """Replace provider._request with a capturing stub that returns
    a minimal-but-valid Ollama response without hitting the network."""
    captured: dict = {}

    def fake_request(endpoint, payload):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"response": "stub"}

    monkeypatch.setattr(provider, "_request", fake_request)
    return captured


def test_generate_sends_repeat_penalty_in_options(monkeypatch):
    """generate() payload contains repeat_penalty option (1.15 default)."""
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp=None)
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    captured = _capture_payload(provider, monkeypatch)
    provider.generate("hello", max_tokens=10)
    opts = captured["payload"]["options"]
    assert "repeat_penalty" in opts, f"options missing repeat_penalty: {opts}"
    assert opts["repeat_penalty"] == 1.15, (
        f"expected default 1.15, got {opts['repeat_penalty']}"
    )


def test_generate_default_temperature_is_02(monkeypatch):
    """generate() default temperature is 0.2 (was 0.0 pre-fix, caused collapse)."""
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp=None)
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    captured = _capture_payload(provider, monkeypatch)
    provider.generate("hello", max_tokens=10)
    opts = captured["payload"]["options"]
    assert opts["temperature"] == 0.2, (
        f"expected default 0.2, got {opts['temperature']}"
    )


def test_fim_generate_includes_repeat_penalty(monkeypatch):
    """fim_generate() — the path used by the reco worker — also sets
    repeat_penalty. This is THE call site that was looping pre-fix.
    `qwen2.5-coder` is in the FIM-supporting families, so supports_fim
    returns True via the @property without monkey-patching.
    """
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp=None)
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    assert provider.supports_fim, "qwen2.5-coder must support FIM"
    captured = _capture_payload(provider, monkeypatch)
    provider.fim_generate("prefix code", "suffix code", max_tokens=10)
    opts = captured["payload"]["options"]
    assert "repeat_penalty" in opts, (
        f"fim_generate missing repeat_penalty: {opts}"
    )
    assert opts["repeat_penalty"] == 1.15


def test_env_repeat_penalty_overrides_default(monkeypatch):
    """MUNINN_LLM_REPEAT_PENALTY=1.30 → payload uses 1.30."""
    cp = _fresh_cube_providers(monkeypatch, repeat="1.30", temp=None)
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    captured = _capture_payload(provider, monkeypatch)
    provider.generate("hello", max_tokens=10)
    assert captured["payload"]["options"]["repeat_penalty"] == 1.30


def test_env_temperature_overrides_default(monkeypatch):
    """MUNINN_LLM_TEMPERATURE=0.5 → payload uses 0.5."""
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp="0.5")
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    captured = _capture_payload(provider, monkeypatch)
    provider.generate("hello", max_tokens=10)
    assert captured["payload"]["options"]["temperature"] == 0.5


def test_pipeline_trace_event_emitted_on_provider_init(monkeypatch):
    """Per §8.F naming convention: provider __init__ emits
    `pipeline.engine.llm.options_applied` so the sandbox monitor can
    confirm the C0 fix is wired without launching a real reco run.
    """
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp=None)
    captured_events: list[tuple[str, dict]] = []

    def fake_log_event(name, data=None, level="info"):
        captured_events.append((name, data or {}))

    monkeypatch.setattr(cp, "log_event", fake_log_event)
    cp.OllamaProvider(model="qwen2.5-coder:7b")
    assert any(name == "pipeline.engine.llm.options_applied"
               for name, _ in captured_events), (
        f"expected pipeline.engine.llm.options_applied event, got: "
        f"{[n for n, _ in captured_events]}"
    )
    data = next(d for n, d in captured_events
                if n == "pipeline.engine.llm.options_applied")
    assert data["repeat_penalty"] == 1.15
    assert data["temperature"] == 0.2
    assert data["provider"] == "ollama"


def test_d9_options_applied_emitted_only_once_per_session(monkeypatch):
    """D9 regression : the `options_applied` event must fire ONCE per
    module session, not on every OllamaProvider instantiation.

    Pre-D9 : every OllamaProvider() emitted a fresh event → trace JSONL
    polluted with N identical lines if N providers were created.
    Pre-D9 comment claimed "trace … once at boot" — was a lie.

    Post-D9 : module-level _OPTIONS_TRACE_EMITTED guard ensures the
    event fires only the first time.
    """
    cp = _fresh_cube_providers(monkeypatch, repeat=None, temp=None)
    captured_events: list[tuple[str, dict]] = []

    def fake_log_event(name, data=None, level="info"):
        captured_events.append((name, data or {}))

    monkeypatch.setattr(cp, "log_event", fake_log_event)
    # 3 instanciations dans la même session de module
    cp.OllamaProvider(model="qwen2.5-coder:1.5b")
    cp.OllamaProvider(model="qwen2.5-coder:7b")
    cp.OllamaProvider(model="codellama:13b")

    options_events = [
        (n, d) for n, d in captured_events
        if n == "pipeline.engine.llm.options_applied"
    ]
    assert len(options_events) == 1, (
        f"expected exactly 1 options_applied event for 3 providers, "
        f"got {len(options_events)} : {options_events}"
    )


def test_legacy_mode_flag_off_restores_pre_fix_behavior(monkeypatch):
    """Setting both env to 1.0 / 0.0 simulates legacy pre-C0 behavior
    for users who need deterministic output (e.g. cached SHA testing).

    Required by §4bis feature flag table: MUNINN_LLM_REPEAT_PENALTY=1.0
    and MUNINN_LLM_TEMPERATURE=0.0 must round-trip.
    """
    cp = _fresh_cube_providers(monkeypatch, repeat="1.0", temp="0.0")
    provider = cp.OllamaProvider(model="qwen2.5-coder:7b")
    captured = _capture_payload(provider, monkeypatch)
    provider.generate("hello", max_tokens=10)
    opts = captured["payload"]["options"]
    assert opts["repeat_penalty"] == 1.0
    assert opts["temperature"] == 0.0
