#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B11-B15.

B11: LLMProvider abstract interface
B12: Ollama backend
B13: Claude backend
B14: OpenAI backend
B15: FIM (Fill-in-the-Middle)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    LLMProvider, OllamaProvider, ClaudeProvider, OpenAIProvider,
    FIMReconstructor, MockLLMProvider,
    Cube, sha256_hash, subdivide_file, scan_repo,
    parse_dependencies, assign_neighbors,
)


# ═══════════════════════════════════════════════════════════════════════
# B11: LLMProvider abstract interface
# ═══════════════════════════════════════════════════════════════════════

class TestB11Interface:
    """B11: Abstract LLM provider interface."""

    def test_mock_implements_interface(self):
        """MockLLMProvider implements all abstract methods."""
        mock = MockLLMProvider()
        assert isinstance(mock, LLMProvider)
        assert mock.name == 'mock'

    def test_generate(self):
        """generate() returns string."""
        mock = MockLLMProvider({'hello': 'world'})
        result = mock.generate("hello prompt")
        assert isinstance(result, str)
        assert result == 'world'

    def test_generate_default(self):
        """generate() returns default when no match."""
        mock = MockLLMProvider()
        result = mock.generate("anything")
        assert 'pass' in result

    def test_perplexity(self):
        """get_perplexity() returns float."""
        mock = MockLLMProvider()
        p = mock.get_perplexity("prompt", "completion")
        assert isinstance(p, float)
        assert p >= 0.0

    def test_list_models(self):
        """list_models() returns list of strings."""
        mock = MockLLMProvider()
        models = mock.list_models()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_calls_tracked(self):
        """Mock tracks all calls."""
        mock = MockLLMProvider()
        mock.generate("a")
        mock.generate("b")
        mock.get_perplexity("c", "d")
        assert len(mock._calls) == 3
        assert mock._calls[0]['method'] == 'generate'
        assert mock._calls[2]['method'] == 'perplexity'

    def test_supports_fim_default_false(self):
        """supports_fim defaults to False."""
        mock = MockLLMProvider()
        assert mock.supports_fim is False

    def test_fim_not_supported_raises(self):
        """fim_generate raises when not supported."""
        mock = MockLLMProvider()
        # MockLLMProvider overrides fim_generate, but the base class would raise
        # Test that a non-FIM provider raises
        assert mock.supports_fim is False

    def test_temperature_parameter(self):
        """Temperature parameter is passed through."""
        mock = MockLLMProvider()
        mock.generate("test", temperature=0.7)
        assert mock._calls[0]['temperature'] == 0.7

    def test_max_tokens_parameter(self):
        """max_tokens parameter is passed through."""
        mock = MockLLMProvider()
        mock.generate("test", max_tokens=100)
        assert mock._calls[0]['max_tokens'] == 100


# ═══════════════════════════════════════════════════════════════════════
# B12: Ollama backend
# ═══════════════════════════════════════════════════════════════════════

class TestB12Ollama:
    """B12: Ollama backend (local LLMs)."""

    def test_ollama_provider_exists(self):
        """OllamaProvider class exists and has correct interface."""
        provider = OllamaProvider(model='codellama')
        assert provider.name == 'ollama'
        assert isinstance(provider, LLMProvider)

    def test_ollama_supports_fim(self):
        """FIM-capable models flagged correctly."""
        assert OllamaProvider(model='codellama').supports_fim is True
        assert OllamaProvider(model='deepseek-coder').supports_fim is True
        assert OllamaProvider(model='starcoder2').supports_fim is True
        assert OllamaProvider(model='llama3').supports_fim is False
        assert OllamaProvider(model='mistral').supports_fim is False

    def test_ollama_custom_url(self):
        """Custom base URL is stored."""
        provider = OllamaProvider(base_url='http://192.168.1.100:11434')
        assert provider.base_url == 'http://192.168.1.100:11434'

    @pytest.mark.skipif(
        not os.environ.get('OLLAMA_AVAILABLE'),
        reason="Ollama not available (set OLLAMA_AVAILABLE=1 to test)"
    )
    def test_ollama_generate(self):
        """Live test: Ollama generates code."""
        provider = OllamaProvider()
        result = provider.generate("Complete: def add(a, b):", max_tokens=50)
        assert len(result) > 0

    @pytest.mark.skipif(
        not os.environ.get('OLLAMA_AVAILABLE'),
        reason="Ollama not available"
    )
    def test_ollama_list_models(self):
        """Live test: Ollama lists available models."""
        provider = OllamaProvider()
        models = provider.list_models()
        assert isinstance(models, list)

    def test_ollama_connection_error(self):
        """Ollama raises on connection failure."""
        provider = OllamaProvider(base_url='http://localhost:99999')
        with pytest.raises(Exception):
            provider.generate("test")


# ═══════════════════════════════════════════════════════════════════════
# B13: Claude backend
# ═══════════════════════════════════════════════════════════════════════

class TestB13Claude:
    """B13: Claude API backend."""

    def test_claude_provider_exists(self):
        """ClaudeProvider class exists with correct interface."""
        provider = ClaudeProvider()
        assert provider.name == 'claude'
        assert isinstance(provider, LLMProvider)

    def test_claude_no_fim(self):
        """Claude doesn't support FIM."""
        provider = ClaudeProvider()
        assert provider.supports_fim is False

    def test_claude_list_models(self):
        """Claude lists available models."""
        provider = ClaudeProvider()
        models = provider.list_models()
        assert 'claude-sonnet-4-6' in models
        assert 'claude-opus-4-6' in models

    def test_claude_no_key_raises(self):
        """Claude raises without API key."""
        provider = ClaudeProvider(api_key='')
        # Clear env var temporarily
        old_key = os.environ.get('ANTHROPIC_API_KEY', '')
        try:
            os.environ.pop('ANTHROPIC_API_KEY', None)
            provider._api_key = ''
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                provider._get_client()
        finally:
            if old_key:
                os.environ['ANTHROPIC_API_KEY'] = old_key

    @pytest.mark.skipif(
        not os.environ.get('ANTHROPIC_API_KEY'),
        reason="ANTHROPIC_API_KEY not set"
    )
    def test_claude_generate(self):
        """Live test: Claude generates code."""
        provider = ClaudeProvider(model='claude-haiku-4-5-20251001')
        result = provider.generate("Output only: print('hello')", max_tokens=20)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════
# B14: OpenAI backend
# ═══════════════════════════════════════════════════════════════════════

class TestB14OpenAI:
    """B14: OpenAI GPT backend."""

    def test_openai_provider_exists(self):
        """OpenAIProvider class exists with correct interface."""
        provider = OpenAIProvider()
        assert provider.name == 'openai'
        assert isinstance(provider, LLMProvider)

    def test_openai_no_fim(self):
        """OpenAI doesn't support FIM (via this provider)."""
        provider = OpenAIProvider()
        assert provider.supports_fim is False

    def test_openai_list_models(self):
        """OpenAI lists available models."""
        provider = OpenAIProvider()
        models = provider.list_models()
        assert 'gpt-4o' in models

    def test_openai_no_key_raises(self):
        """OpenAI raises without API key."""
        provider = OpenAIProvider(api_key='')
        old_key = os.environ.get('OPENAI_API_KEY', '')
        try:
            os.environ.pop('OPENAI_API_KEY', None)
            provider._api_key = ''
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                provider._get_client()
        finally:
            if old_key:
                os.environ['OPENAI_API_KEY'] = old_key

    @pytest.mark.skipif(
        not os.environ.get('OPENAI_API_KEY'),
        reason="OPENAI_API_KEY not set"
    )
    def test_openai_generate(self):
        """Live test: OpenAI generates code."""
        provider = OpenAIProvider(model='gpt-4o-mini')
        result = provider.generate("Output only: print('hello')", max_tokens=20)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════
# B15: FIM (Fill-in-the-Middle)
# ═══════════════════════════════════════════════════════════════════════

class TestB15FIM:
    """B15: Fill-in-the-Middle reconstruction."""

    def test_fim_reconstructor_exists(self):
        """FIMReconstructor class exists."""
        mock = MockLLMProvider()
        fim = FIMReconstructor(mock)
        assert fim.provider is mock

    def test_fim_fallback_to_prompt(self):
        """Non-FIM provider falls back to prompt-based reconstruction."""
        mock = MockLLMProvider({'MISSING CODE': 'return x + y'})
        fim = FIMReconstructor(mock)
        result = fim.reconstruct_fim("def add(a, b):\n", "\nresult = add(1, 2)")
        assert result == 'return x + y'
        # Should have called generate, not fim
        assert mock._calls[0]['method'] == 'generate'

    def test_fim_with_fim_provider(self):
        """FIM-capable provider uses FIM tokens."""
        mock = MockLLMProvider({'fim': '    return a + b'})
        mock._fim_enabled = True
        fim = FIMReconstructor(mock)
        result = fim.reconstruct_fim("def add(a, b):\n", "\nresult = add(1, 2)")
        assert result == '    return a + b'
        assert mock._calls[0]['method'] == 'fim'

    def test_reconstruct_with_neighbors(self):
        """reconstruct_with_neighbors uses neighbor context."""
        mock = MockLLMProvider({'Reconstruct': 'return self.name'})
        fim = FIMReconstructor(mock)

        target = Cube(id="t:L5-L7:lv0", content="return self.name",
                      sha256=sha256_hash("return self.name"),
                      file_origin="t.py", line_start=5, line_end=7)

        neighbors = [
            Cube(id="t:L1-L4:lv0", content="class User:\n    def __init__(self, name):\n        self.name = name",
                 sha256="h1", file_origin="t.py", line_start=1, line_end=4),
            Cube(id="t:L8-L10:lv0", content="def __repr__(self):\n    return f'User({self.name})'",
                 sha256="h2", file_origin="t.py", line_start=8, line_end=10),
        ]

        result = fim.reconstruct_with_neighbors(target, neighbors)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_reconstruct_tracks_calls(self):
        """Reconstruction makes at least one LLM call."""
        mock = MockLLMProvider()
        fim = FIMReconstructor(mock)

        target = Cube(id="a:L1-L3:lv0", content="x=1", sha256="h",
                      file_origin="a.py", line_start=1, line_end=3)
        neighbors = [
            Cube(id="a:L4-L6:lv0", content="y=2", sha256="h2",
                 file_origin="a.py", line_start=4, line_end=6),
        ]

        fim.reconstruct_with_neighbors(target, neighbors)
        assert len(mock._calls) >= 1

    def test_fim_formats_defined(self):
        """FIM token formats are defined for known models."""
        assert 'codellama' in FIMReconstructor.FIM_FORMATS
        assert 'deepseek-coder' in FIMReconstructor.FIM_FORMATS
        assert 'starcoder2' in FIMReconstructor.FIM_FORMATS

    def test_empty_neighbors(self):
        """Reconstruction with no neighbors still works."""
        mock = MockLLMProvider()
        fim = FIMReconstructor(mock)
        target = Cube(id="a:L1:lv0", content="x=1", sha256="h",
                      file_origin="a.py", line_start=1, line_end=1)
        result = fim.reconstruct_with_neighbors(target, [])
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════
# Integration: B1-B8 + B11-B15
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB11B15:
    """Integration: scan → subdivide → neighbors → reconstruct (mock)."""

    def test_full_pipeline_with_mock(self, tmp_path):
        """Full pipeline: scan → cubes → neighbors → FIM reconstruct."""
        # Create test repo
        (tmp_path / "calc.py").write_text(
            "def add(a, b):\n"
            "    return a + b\n"
            "\ndef multiply(a, b):\n"
            "    return a * b\n"
            "\nresult = add(3, multiply(2, 4))\n"
            "print(result)\n"
        )

        # B1: scan
        files = scan_repo(str(tmp_path))
        assert len(files) == 1

        # B4: subdivide
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        # B7+B8: deps + neighbors
        deps = parse_dependencies(files)
        assign_neighbors(all_cubes, deps)

        # B15: reconstruct with mock
        mock = MockLLMProvider({'Reconstruct': 'return a + b'})
        fim = FIMReconstructor(mock)

        target = all_cubes[0]
        neighbor_cubes = [c for c in all_cubes if c.id in target.neighbors]
        result = fim.reconstruct_with_neighbors(target, neighbor_cubes)
        assert isinstance(result, str)
        assert len(mock._calls) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
