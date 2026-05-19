"""CHUNK C13 (2026-05-19) — mock_ollama helper.

Patches `urllib.request.urlopen` to fake the Ollama HTTP endpoints used
by `OllamaProvider.__init__` (`/api/tags`) and the various generate /
fim / chat paths. Tests that exercise the LLM provider layer can use
this to run without a live Ollama daemon.

CHUNK D10 (2026-05-19 remediation) — `mock_ollama_session` now yields a
`captured` list so tests can assert on the payloads sent to the mocked
endpoints. Pre-D10, this helper was dead code (zero consumer in the
C13 batch).

Usage :

    with mock_ollama_session(models=["qwen2.5-coder"],
                              generate_text="def foo()\\n") as captured:
        from cube_providers import OllamaProvider
        p = OllamaProvider(model="qwen2.5-coder:1.5b")
        p.generate("hello")
    gen_calls = [c for c in captured if "/api/generate" in c["url"]]
    assert gen_calls[-1]["payload"]["options"]["repeat_penalty"] == 1.15
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


def _build_handler(models, generate_text, chat_text, captured):
    """Return a function that mimics urllib.request.urlopen(request, timeout=...)
    routing /api/tags, /api/generate, /api/chat to canned payloads.
    Each request body is captured into the `captured` list (parsed as JSON
    when possible, otherwise stored raw).
    Unknown URLs raise URLError (Ollama "not running" simulation)."""
    def _fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        # D10 : capture the request body (sent payload) so tests can assert.
        payload = None
        if hasattr(req, "data") and req.data:
            try:
                payload = json.loads(req.data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {"_raw": req.data}
        captured.append({"url": url, "payload": payload})

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
    duration of the block. Yields a `captured` list populated in order
    with dicts {"url": str, "payload": dict|None}. Restores the
    original urlopen on exit even if an exception was raised inside.
    """
    captured: list = []
    saved = urllib.request.urlopen
    urllib.request.urlopen = _build_handler(
        list(models), generate_text, chat_text, captured,
    )
    try:
        yield captured
    finally:
        urllib.request.urlopen = saved
