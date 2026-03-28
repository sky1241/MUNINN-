"""
Cube Providers — LLM providers, FIM reconstruction, and validation.

Classes: LLMProvider (ABC), OllamaProvider, ClaudeProvider, OpenAIProvider,
         FIMReconstructor, MockLLMProvider, ReconstructionResult.
Functions: reconstruct_cube, validate_reconstruction, compute_hotness, compute_ncd.
"""

import json
import os
import re
import urllib.error
import urllib.request
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from cube import Cube, CubeStore, sha256_hash

try:
    from engine.core.lang_lexicons import get_lexicon, format_lexicon_prompt
except ImportError:
    try:
        from .lang_lexicons import get_lexicon, format_lexicon_prompt
    except ImportError:
        from lang_lexicons import get_lexicon, format_lexicon_prompt

__all__ = [
    "LLMProvider", "OllamaProvider", "ClaudeProvider", "OpenAIProvider",
    "FIMReconstructor", "MockLLMProvider", "ReconstructionResult",
    "reconstruct_cube", "validate_reconstruction", "compute_hotness", "compute_ncd",
]

class LLMProvider(ABC):
    """
    B11: Abstract LLM provider interface for cube reconstruction.

    Implementations: Ollama (B12), Claude (B13), OpenAI (B14).
    """

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        """Generate text completion."""
        ...

    @abstractmethod
    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Calculate perplexity of completion given prompt."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g. 'ollama', 'claude', 'openai')."""
        ...

    @property
    def supports_fim(self) -> bool:
        """Whether this provider supports Fill-in-the-Middle."""
        return False

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        """FIM: generate text to fill between prefix and suffix."""
        raise NotImplementedError(f"{self.name} does not support FIM")


# ─── B12: Backend Ollama ──────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    """
    B12: LLM provider for Ollama (local models).

    Supports llama, mistral, phi, codellama, deepseek-coder.
    """

    def __init__(self, model: str = 'codellama', base_url: str = 'http://localhost:11434'):
        self.model = model
        self.base_url = base_url.rstrip('/')
        self._available = None

    @property
    def name(self) -> str:
        return 'ollama'

    @property
    def supports_fim(self) -> bool:
        fim_families = ('codellama', 'deepseek-coder', 'starcoder2',
                        'codegemma', 'qwen2.5-coder')
        return any(f in self.model for f in fim_families)

    def _request(self, endpoint: str, payload: dict, timeout: int = 300) -> dict:
        """Make HTTP request to Ollama API. Timeout=300s for cold start model loading."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}: {e}")

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        resp = self._request('/api/generate', {
            'model': self.model,
            'prompt': prompt,
            'options': {'num_predict': max_tokens, 'temperature': temperature},
            'stream': False,
        })
        return resp.get('response', '')

    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Estimate perplexity by tokenizing completion and measuring log probs."""
        # Ollama doesn't expose logprobs directly, estimate via generation
        # For now, return a rough estimate based on edit distance
        if not completion:
            return 0.0
        full_prompt = prompt + '\n# Expected:\n' + completion
        result = self.generate(full_prompt, max_tokens=len(completion) * 2)
        # Simple proxy: how different is the regeneration from the completion
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))  # 0 = perfect match, higher = more different

    def list_models(self) -> list[str]:
        if self._available is None:
            try:
                url = f"{self.base_url}/api/tags"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                    self._available = [m['name'] for m in data.get('models', [])]
            except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
                self._available = []
        return self._available

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        """FIM using Ollama's raw mode with model-specific FIM tokens."""
        if not self.supports_fim:
            raise NotImplementedError(f"{self.model} does not support FIM")
        # Model-specific FIM token formats
        if 'deepseek' in self.model:
            prompt = f"<｜fim▁begin｜>{prefix}<｜fim▁hole｜>{suffix}<｜fim▁end｜>"
        elif 'starcoder' in self.model:
            prompt = f"<fim_prefix>{prefix}<fim_suffix>{suffix}<fim_middle>"
        elif 'codegemma' in self.model or 'qwen' in self.model:
            prompt = f"<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>"
        else:
            # CodeLlama default
            prompt = f"<PRE> {prefix} <SUF>{suffix} <MID>"
        resp = self._request('/api/generate', {
            'model': self.model,
            'prompt': prompt,
            'raw': True,
            'options': {'num_predict': max_tokens, 'temperature': 0.0},
            'stream': False,
        })
        return resp.get('response', '')


# ─── B13: Backend Claude API ─────────────────────────────────────────

class ClaudeProvider(LLMProvider):
    """
    B13: LLM provider for Claude API (Anthropic).

    Reuses the anthropic SDK.
    """

    def __init__(self, model: str = 'claude-sonnet-4-6',
                 api_key: Optional[str] = None):
        self.model = model
        self._api_key = api_key or os.environ.get('ANTHROPIC_API_KEY', '')
        self._client = None

    @property
    def name(self) -> str:
        return 'claude'

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError("pip install anthropic required")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        client = self._get_client()
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.content[0].text if resp.content else ''

    def get_perplexity(self, prompt: str, completion: str) -> float:
        """Claude doesn't expose logprobs; estimate via regeneration similarity."""
        if not completion:
            return 0.0
        result = self.generate(
            f"Complete this code exactly:\n{prompt}",
            max_tokens=len(completion) * 2,
        )
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))

    def list_models(self) -> list[str]:
        return ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001',
                'claude-opus-4-6']


# ─── B14: Backend OpenAI API ─────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """
    B14: LLM provider for OpenAI GPT models.
    """

    def __init__(self, model: str = 'gpt-4o-mini',
                 api_key: Optional[str] = None):
        self.model = model
        self._api_key = api_key or os.environ.get('OPENAI_API_KEY', '')
        self._client = None

    @property
    def name(self) -> str:
        return 'openai'

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise ValueError("OPENAI_API_KEY not set")
            try:
                import openai
                self._client = openai.OpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError("pip install openai required")
        return self._client

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return resp.choices[0].message.content or ''

    def get_perplexity(self, prompt: str, completion: str) -> float:
        if not completion:
            return 0.0
        result = self.generate(
            f"Complete this code exactly:\n{prompt}",
            max_tokens=len(completion) * 2,
        )
        import difflib
        ratio = difflib.SequenceMatcher(None, completion, result).ratio()
        return max(0.0, -2.0 * (ratio - 1.0))

    def list_models(self) -> list[str]:
        return ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo']


# ─── B15: Mode FIM (Fill-in-the-Middle) ──────────────────────────────

class FIMReconstructor:
    """
    B15: Fill-in-the-Middle reconstruction engine.

    Cube reconstruction IS code infilling — the cube is the span to fill.
    Uses FIM-capable models (DeepSeek-Coder, StarCoder2, CodeLlama) or
    falls back to standard prompt-based reconstruction.
    """

    # FIM token formats per model family
    FIM_FORMATS = {
        'codellama': {'pre': '<PRE> ', 'suf': ' <SUF>', 'mid': ' <MID>'},
        'deepseek-coder': {'pre': '<｜fim▁begin｜>', 'suf': '<｜fim▁hole｜>', 'mid': '<｜fim▁end｜>'},
        'starcoder2': {'pre': '<fim_prefix>', 'suf': '<fim_suffix>', 'mid': '<fim_middle>'},
        'codegemma': {'pre': '<|fim_prefix|>', 'suf': '<|fim_suffix|>', 'mid': '<|fim_middle|>'},
    }

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def reconstruct_fim(self, prefix: str, suffix: str,
                        max_tokens: int = 256) -> str:
        """Reconstruct missing code using FIM if available."""
        if self.provider.supports_fim:
            return self.provider.fim_generate(prefix, suffix, max_tokens)

        # Fallback: standard prompt-based infilling
        prompt = (
            "You are a code completion engine. Fill in the missing code between "
            "PREFIX and SUFFIX. Output ONLY the missing code, nothing else.\n\n"
            f"PREFIX:\n```\n{prefix}\n```\n\n"
            f"SUFFIX:\n```\n{suffix}\n```\n\n"
            "MISSING CODE:"
        )
        return self.provider.generate(prompt, max_tokens=max_tokens)

    # Language detection from file extension
    _EXT_TO_LANG = {
        '.py': 'Python', '.go': 'Go', '.rs': 'Rust', '.js': 'JavaScript',
        '.jsx': 'JSX/React', '.ts': 'TypeScript', '.tsx': 'TSX/React',
        '.c': 'C', '.h': 'C', '.cpp': 'C++', '.java': 'Java',
        '.kt': 'Kotlin', '.rb': 'Ruby', '.swift': 'Swift', '.zig': 'Zig',
        '.cob': 'COBOL', '.cbl': 'COBOL', '.cpy': 'COBOL',
    }

    def reconstruct_with_neighbors(self, cube: Cube, neighbors: list[Cube],
                                   max_tokens: int = 256,
                                   ast_hints: dict | None = None) -> str:
        """
        Reconstruct a cube using its neighbors as context.

        This is the core reconstruction: neighbors provide the context,
        the cube content is what we're trying to reconstruct.
        Injects language lexicon + AST constraints for maximum precision.
        """
        # Detect language from file extension
        ext = os.path.splitext(cube.file_origin)[1].lower() if cube.file_origin else ''
        lang = self._EXT_TO_LANG.get(ext, 'code')
        lang_key = ext.lstrip('.')  # for lexicon lookup

        # Sort neighbors by line position (not proximity — preserve order)
        same_file = [n for n in neighbors if n.file_origin == cube.file_origin]
        before = sorted([n for n in same_file if n.line_end <= cube.line_start],
                        key=lambda c: c.line_start)
        after = sorted([n for n in same_file if n.line_start >= cube.line_end],
                       key=lambda c: c.line_start)

        # Try FIM first if available
        if self.provider.supports_fim and before and after:
            ext_prefix = "\n".join(c.content for c in before)
            ext_suffix = "\n".join(c.content for c in after)
            return self.reconstruct_fim(ext_prefix, ext_suffix, max_tokens)

        # Build structured prompt — lexicon + constraints + neighbors
        parts = []
        parts.append(f"You are reconstructing {lang} code from file {cube.file_origin}.")
        n_lines = cube.line_end - cube.line_start + 1
        parts.append(f"Lines {cube.line_start}-{cube.line_end} are missing ({n_lines} lines, ~{cube.token_count} tokens).")
        parts.append("")

        # Inject language lexicon — constrains formatting + syntax
        lexicon_text = format_lexicon_prompt(lang_key)
        if lexicon_text:
            parts.append(lexicon_text)
            parts.append("")

        # Inject AST constraints if available
        if ast_hints:
            parts.append("=== CONSTRAINTS (from static analysis) ===")
            if ast_hints.get('functions'):
                parts.append(f"Functions defined: {', '.join(ast_hints['functions'])}")
            if ast_hints.get('classes'):
                parts.append(f"Classes defined: {', '.join(ast_hints['classes'])}")
            if ast_hints.get('imports'):
                parts.append(f"Imports used: {', '.join(ast_hints['imports'])}")
            if ast_hints.get('variables'):
                parts.append(f"Variables: {', '.join(ast_hints['variables'][:20])}")
            if ast_hints.get('indent_char'):
                parts.append(f"Indentation: {ast_hints['indent_char']}")
            if ast_hints.get('indent_level'):
                parts.append(f"Base indent level: {ast_hints['indent_level']}")
            parts.append("=== END CONSTRAINTS ===")
            parts.append("")

        if before:
            parts.append("=== CODE BEFORE (ends at line {}) ===".format(cube.line_start - 1))
            for b in before[-4:]:  # last 4 before-cubes max
                parts.append(b.content)
            parts.append("")

        if after:
            parts.append("=== CODE AFTER (starts at line {}) ===".format(cube.line_end + 1))
            for a in after[:4]:  # first 4 after-cubes max
                parts.append(a.content)
            parts.append("")

        parts.append(f"Write EXACTLY {n_lines} lines of {lang} code for lines {cube.line_start}-{cube.line_end}.")
        parts.append("Match the style, indentation, and conventions of the surrounding code.")
        parts.append("Output ONLY the code. No markdown fences. No explanation.")

        prompt = "\n".join(parts)

        # Constrain output to ~1.5x expected size (not 3x)
        constrained_tokens = min(max_tokens, cube.token_count * 2)

        raw = self.provider.generate(prompt, max_tokens=constrained_tokens)
        # Strip markdown code fences that LLMs love to add
        cleaned = raw.strip()
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            if lines[-1].strip() == '```':
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = '\n'.join(lines)
        return cleaned


# ─── Mock provider for testing ────────────────────────────────────────

class MockLLMProvider(LLMProvider):
    """Test-only mock provider that returns predictable results."""

    def __init__(self, responses: Optional[dict[str, str]] = None):
        self._responses = responses or {}
        self._calls: list[dict] = []
        self._fim_enabled = False

    @property
    def name(self) -> str:
        return 'mock'

    @property
    def supports_fim(self) -> bool:
        return self._fim_enabled

    def generate(self, prompt: str, max_tokens: int = 256,
                 temperature: float = 0.0) -> str:
        self._calls.append({'method': 'generate', 'prompt': prompt,
                           'max_tokens': max_tokens, 'temperature': temperature})
        # Check if any response key is in the prompt
        for key, response in self._responses.items():
            if key in prompt:
                return response
        return "# mock generated code\npass"

    def get_perplexity(self, prompt: str, completion: str) -> float:
        self._calls.append({'method': 'perplexity', 'prompt': prompt,
                           'completion': completion})
        return 1.0

    def list_models(self) -> list[str]:
        return ['mock-model']

    def fim_generate(self, prefix: str, suffix: str,
                     max_tokens: int = 256) -> str:
        self._calls.append({'method': 'fim', 'prefix': prefix, 'suffix': suffix})
        return self._responses.get('fim', '# mock FIM result\npass')


# ─── B16: Moteur de reconstruction ───────────────────────────────────

@dataclass
class ReconstructionResult:
    """Result of a cube reconstruction attempt."""
    cube_id: str
    original_sha256: str
    reconstruction: str
    reconstruction_sha256: str
    exact_match: bool
    ncd_score: float      # 0.0 = identical, 1.0 = completely different
    perplexity: float
    success: bool         # exact_match OR ncd_score < threshold


def reconstruct_cube(cube: Cube, neighbors: list[Cube],
                     provider: LLMProvider,
                     ncd_threshold: float = 0.3,
                     ast_hints: dict | None = None) -> ReconstructionResult:
    """
    B16: Reconstruct a cube using its neighbors + LLM.

    1. Build prompt from neighbors context + lexicon + AST hints
    2. Call LLM to reconstruct
    3. Validate via SHA-256 (B17) and NCD fallback (B19)
    4. Score perplexity (B18)
    """
    fim = FIMReconstructor(provider)
    reconstruction = fim.reconstruct_with_neighbors(
        cube, neighbors, max_tokens=cube.token_count * 3,
        ast_hints=ast_hints,
    )

    # B17: SHA-256 validation
    recon_sha256 = sha256_hash(reconstruction)
    exact_match = (recon_sha256 == cube.sha256)

    # B19: NCD fallback
    ncd = compute_ncd(cube.content, reconstruction)

    # B18: Perplexity scoring
    perplexity = provider.get_perplexity(
        "\n".join(n.content for n in neighbors[:3]),
        cube.content
    )

    success = exact_match or ncd < ncd_threshold

    return ReconstructionResult(
        cube_id=cube.id,
        original_sha256=cube.sha256,
        reconstruction=reconstruction,
        reconstruction_sha256=recon_sha256,
        exact_match=exact_match,
        ncd_score=ncd,
        perplexity=perplexity,
        success=success,
    )


# ─── B17: Validation SHA-256 ─────────────────────────────────────────

def validate_reconstruction(original: str, reconstruction: str) -> bool:
    """
    B17: Validate reconstruction via SHA-256 comparison.

    Both strings are normalized before hashing.
    """
    return sha256_hash(original) == sha256_hash(reconstruction)


# ─── B18: Scoring perplexite (hotness) ───────────────────────────────

def compute_hotness(cube: Cube, neighbors: list[Cube],
                    provider: LLMProvider) -> float:
    """
    B18: Compute hotness score for a cube.

    Hotness(cube) = -Σ log P_LLM(token_i | neighbors)
    ≈ perplexity of cube content given neighbor context.

    High hotness = irreconstructible = critical code.
    1 LLM call instead of 11 destructions.
    """
    context = "\n".join(n.content for n in neighbors[:9])
    return provider.get_perplexity(context, cube.content)


# ─── B19: NCD fallback ───────────────────────────────────────────────

def compute_ncd(a: str, b: str) -> float:
    """
    B19: Normalized Compression Distance.

    NCD(a,b) = (C(ab) - min(C(a),C(b))) / max(C(a),C(b))

    Returns 0.0 for identical strings, ~1.0 for completely different.
    Uses zlib as compressor.
    """
    import zlib

    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0

    a_bytes = a.encode('utf-8')
    b_bytes = b.encode('utf-8')

    ca = len(zlib.compress(a_bytes, 9))
    cb = len(zlib.compress(b_bytes, 9))
    cab = len(zlib.compress(a_bytes + b_bytes, 9))

    ncd = (cab - min(ca, cb)) / max(ca, cb)
    return max(0.0, min(1.0, ncd))  # Clamp to [0, 1]


