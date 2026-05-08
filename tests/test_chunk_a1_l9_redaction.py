"""CHUNK A1 — L9 redact_secrets defense-in-depth.

Vérifie qu'aucun secret ne peut atteindre l'API Anthropic via
_llm_compress / _llm_compress_chunk, même si un caller a oublié
de redact en amont (cas du cold-branch path muninn_tree.py:2887).

Tests written BEFORE the fix to demonstrate the bug exists.
After fix, all tests must pass.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A1
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ENGINE_CORE = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _build_payload_capture():
    """Mock anthropic client. Returns (client, captured_payloads list)."""
    captured = []

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    mock_response.stop_reason = "end_turn"
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=20)

    def capture(**kwargs):
        captured.append(kwargs)
        return mock_response

    client = MagicMock()
    client.messages.create = capture
    return client, captured


def _padded(text: str, target_len: int = 5000) -> str:
    """Pad text to exceed L9 threshold (>4000 chars)."""
    pad = "lorem ipsum dolor sit amet consectetur adipiscing elit. "
    needed = max(0, target_len - len(text))
    return text + "\n" + (pad * (needed // len(pad) + 1))


@pytest.fixture
def l9_active(monkeypatch):
    """Force _llm_compress to call API (no early-return on missing key)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-mock-not-real")
    import muninn_layers
    monkeypatch.setattr(muninn_layers._m, "_SKIP_L9", False)
    return muninn_layers


def test_llm_compress_chunk_redacts_ghp_token():
    """Defense-in-depth: _llm_compress_chunk must not send ghp_* to API."""
    import muninn_layers
    secret = "ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH"
    text = f"Some text mentioning api_key={secret} should be redacted before sending."
    client, payloads = _build_payload_capture()

    muninn_layers._llm_compress_chunk(text, client, context="test")

    assert payloads, "API not called"
    sent = str(payloads[0])
    assert "ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH" not in sent, (
        f"GHP token leaked to API payload: {sent[:300]}"
    )


def test_llm_compress_chunk_redacts_sk_key():
    """Defense-in-depth: _llm_compress_chunk must not send sk-* to API."""
    import muninn_layers
    secret = "sk-aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH"
    text = f"Token: api_key={secret} embedded somewhere."
    client, payloads = _build_payload_capture()

    muninn_layers._llm_compress_chunk(text, client, context="test")

    assert payloads
    sent = str(payloads[0])
    assert secret not in sent


def test_llm_compress_chunk_redacts_aws_akia():
    """Defense-in-depth: _llm_compress_chunk must not send AWS keys to API."""
    import muninn_layers
    secret = "AKIAIOSFODNN7EXAMPLE"
    text = f"AWS config with key={secret} in plain text."
    client, payloads = _build_payload_capture()

    muninn_layers._llm_compress_chunk(text, client, context="test")

    assert payloads
    sent = str(payloads[0])
    assert secret not in sent


def test_llm_compress_full_pipeline_redacts_secret(l9_active):
    """End-to-end: _llm_compress must redact secrets before API."""
    secret = "ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH"
    text = _padded(f"## Section A\nsome content\n\n## Section B\napi_key={secret}\nmore content\n")
    assert len(text) > 4000

    client, payloads = _build_payload_capture()
    with patch("anthropic.Anthropic", return_value=client):
        l9_active._llm_compress(text, context="cold-branch:test")

    assert payloads, "API never called"
    for payload in payloads:
        sent = str(payload)
        assert secret not in sent, f"Secret leaked in payload: {sent[:300]}"


def test_llm_compress_clean_text_unchanged_at_api(l9_active):
    """Negative control: clean text must reach API unchanged (no false redaction)."""
    text = _padded("## Real content\nLorem ipsum dolor sit amet.\n## Section\nclean prose only.\n")
    assert len(text) > 4000

    client, payloads = _build_payload_capture()
    with patch("anthropic.Anthropic", return_value=client):
        l9_active._llm_compress(text, context="test")

    assert payloads
    sent = str(payloads[0])
    assert "[REDACTED]" not in sent, "Clean text was wrongly redacted"
    assert "Lorem ipsum" in sent, "Clean prose missing from payload"


def test_llm_compress_chunk_clean_text_unchanged():
    """Negative control: _llm_compress_chunk must not alter clean prose."""
    import muninn_layers
    text = "Just prose with no secrets at all. Lorem ipsum dolor."
    client, payloads = _build_payload_capture()

    muninn_layers._llm_compress_chunk(text, client, context="test")

    assert payloads
    sent = str(payloads[0])
    assert "[REDACTED]" not in sent
    assert "Lorem ipsum" in sent


def test_cold_branch_scenario_redacts(l9_active, tmp_path):
    """Scenario reproduction: muninn_tree.py:2884-2887 cold-branch path.

    Mirrors the exact code:
        content = filepath.read_text(encoding="utf-8")
        compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
    """
    secret = "ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH"
    branch_text = _padded(
        "## history\n"
        + "fact: x\n" * 50
        + f"## leaked\nold token from session: {secret}\n"
        + "more facts here\n" * 50
    )
    branch_file = tmp_path / "cold_branch.mn"
    branch_file.write_text(branch_text, encoding="utf-8")

    client, payloads = _build_payload_capture()
    with patch("anthropic.Anthropic", return_value=client):
        # Mirror exactement le code de muninn_tree.py:2884-2887
        content = branch_file.read_text(encoding="utf-8")
        l9_active._llm_compress(content, context="cold-branch:history")

    assert payloads
    for payload in payloads:
        sent = str(payload)
        assert secret not in sent, (
            f"COLD-BRANCH LEAK: token sent to API in payload: {sent[:400]}"
        )
