"""CHUNK D10 (2026-05-19 remediation) — runtime proof that C0 options
are sent in the Ollama HTTP request payload.

Closes the gap left by the original C0 commit (928995f) which only had
unit tests on the env-var constants + provider._request stub, not on
the actual urllib.request.urlopen HTTP path.

Uses tests/_helpers/mock_ollama.mock_ollama_session which patches
urllib.request.urlopen + captures all request payloads, so we can
assert that `options.repeat_penalty=1.15` and `options.temperature=0.2`
arrive in the payload sent to /api/generate.

Bonus : valorise mock_ollama (pre-D10 c'était du code mort, audit avait
flag 92 LoC sans consumer).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"
for p in (str(REPO_ROOT), str(ENGINE_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from tests._helpers.mock_ollama import mock_ollama_session


@pytest.fixture(autouse=True)
def _fresh_cube_providers_module(monkeypatch):
    """Force reload of cube_providers with clean env so the C0 constants
    (_OLLAMA_REPEAT_PENALTY=1.15, _OLLAMA_TEMPERATURE=0.2) are read fresh.
    Without this, the previous test file's `_fresh_cube_providers` may
    leave a polluted module in sys.modules with env-overridden values.
    """
    import importlib
    monkeypatch.delenv("MUNINN_LLM_REPEAT_PENALTY", raising=False)
    monkeypatch.delenv("MUNINN_LLM_TEMPERATURE", raising=False)
    sys.modules.pop("cube_providers", None)
    sys.modules.pop("engine.core.cube_providers", None)
    importlib.import_module("cube_providers")
    yield


def test_d10_ollama_generate_includes_repeat_penalty():
    """D10 C0 wire proof : OllamaProvider.generate() sends
    repeat_penalty=1.15 in the options block of /api/generate payload."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider, _OLLAMA_REPEAT_PENALTY
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.generate("hello world")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls, f"no /api/generate call captured ; captured={captured}"
    opts = gen_calls[-1]["payload"]["options"]
    assert opts["repeat_penalty"] == _OLLAMA_REPEAT_PENALTY
    assert abs(opts["repeat_penalty"] - 1.15) < 1e-6


def test_d10_ollama_generate_includes_temperature():
    """D10 C0 wire proof : OllamaProvider.generate() sends temperature=0.2."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider, _OLLAMA_TEMPERATURE
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.generate("hello")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls
    opts = gen_calls[-1]["payload"]["options"]
    assert opts["temperature"] == _OLLAMA_TEMPERATURE
    assert abs(opts["temperature"] - 0.2) < 1e-6


def test_d10_ollama_fim_generate_includes_options():
    """D10 C0 wire proof : fim_generate also carries the C0 options.
    Uses FIM-capable model name to trigger fim_generate path."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.fim_generate(prefix="def f():\n    ", suffix="\n    pass\n")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls
    opts = gen_calls[-1]["payload"]["options"]
    assert "repeat_penalty" in opts
    assert "temperature" in opts


def test_d10_captured_includes_model_name():
    """D10 mock_ollama wires the model name into the payload."""
    with mock_ollama_session(generate_text="stub") as captured:
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="codellama:13b")
        p.generate("hello")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls
    assert gen_calls[-1]["payload"]["model"] == "codellama:13b"


def test_d10_mock_ollama_yields_captured_list():
    """D10 regression : mock_ollama_session must yield a captured list."""
    with mock_ollama_session(generate_text="x") as captured:
        assert isinstance(captured, list)
        assert captured == []  # empty before any request
        from cube_providers import OllamaProvider
        OllamaProvider(model="qwen2.5-coder:1.5b")
        # OllamaProvider.__init__ itself doesn't hit the network anymore
        # (C0/D9 only emit a pipeline_trace event, no HTTP call). So
        # captured stays empty until an explicit generate/fim/chat call.
        assert captured == []
