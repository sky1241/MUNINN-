"""CHUNK C13 (2026-05-19) — mock_ollama helper.

Patches `urllib.request.urlopen` to fake the Ollama HTTP endpoints used
by `OllamaProvider.__init__` (`/api/tags`) and the various generate /
fim / chat paths. Tests that exercise the LLM provider layer can use
this to run without a live Ollama daemon.

Usage :

    with mock_ollama_session(models=["qwen2.5-coder"],
                              generate_text="def foo():\\n    pass\\n"):
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        out = p.generate("...")
        assert "def foo" in out
"""
from __future__ import annotations

import contextlib
import io
import json
import urllib.request


class _FakeResponse:
    """Minimal urlopen() return type — supports .read() and context manager."""

    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self._status = status

    def read(self) -> bytes:
        return self._payload

    def getcode(self) -> int:
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass


def _build_handler(models, generate_text, chat_text):
    """Return a function that mimics urllib.request.urlopen(request, timeout=...)
    routing /api/tags, /api/generate, /api/chat to canned payloads.
    Unknown URLs raise URLError (Ollama "not running" simulation)."""
    def _fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/api/tags" in url:
            body = json.dumps({
                "models": [{"name": m} for m in models],
            }).encode()
            return _FakeResponse(body)
        if "/api/generate" in url:
            body = json.dumps({
                "response": generate_text,
                "done": True,
            }).encode()
            return _FakeResponse(body)
        if "/api/chat" in url:
            body = json.dumps({
                "message": {"role": "assistant", "content": chat_text},
                "done": True,
            }).encode()
            return _FakeResponse(body)
        # Unknown endpoint → simulate "Ollama down".
        raise urllib.error.URLError(f"mock_ollama: unrecognized URL {url}")
    return _fake_urlopen


@contextlib.contextmanager
def mock_ollama_session(*, models=("qwen2.5-coder",),
                        generate_text: str = "",
                        chat_text: str = ""):
    """Context manager that patches urllib.request.urlopen for the
    duration of the block. Restores the original on exit even if an
    exception was raised inside.
    """
    saved = urllib.request.urlopen
    urllib.request.urlopen = _build_handler(
        list(models), generate_text, chat_text
    )
    try:
        yield
    finally:
        urllib.request.urlopen = saved
