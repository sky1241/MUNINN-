"""
Cube Providers — LLM providers, FIM reconstruction, and validation.

Classes: LLMProvider (ABC), OllamaProvider, ClaudeProvider, OpenAIProvider,
         FIMReconstructor, MockLLMProvider, ReconstructionResult.
Functions: reconstruct_cube, reconstruct_cube_waves, run_progressive_levels,
           validate_reconstruction, compute_hotness, compute_ncd.
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

from cube import Cube, sha256_hash

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
    "WaveResult", "LevelResult",
    "reconstruct_cube", "reconstruct_cube_waves", "run_progressive_levels",
    "validate_reconstruction", "compute_hotness", "compute_ncd",
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

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        """Stream response chunks (generator). Override for real streaming.

        Default fallback: yields the full generate() result as one chunk.
        """
        yield self.generate(prompt, max_tokens, temperature)

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

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        """Stream response from Ollama (real streaming via NDJSON)."""
        payload = {
            'model': self.model,
            'prompt': prompt,
            'options': {'num_predict': max_tokens, 'temperature': temperature},
            'stream': True,
        }
        if system:
            payload['system'] = system
        url = f"{self.base_url}/api/generate"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for line in resp:
                    if line.strip():
                        chunk = json.loads(line)
                        text = chunk.get('response', '')
                        if text:
                            yield text
                        if chunk.get('done', False):
                            break
        except (urllib.error.URLError, OSError) as e:
            raise ConnectionError(f"Ollama stream error: {e}")

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

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        """Stream response from Claude API."""
        client = self._get_client()
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        if system:
            kwargs['system'] = system
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

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

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        """Stream response from OpenAI API."""
        client = self._get_client()
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

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
                                   ast_hints: dict | None = None,
                                   previous_attempts: list[str] | None = None,
                                   temperature: float = 0.0) -> str:
        """
        Reconstruct a cube using its neighbors as context.

        This is the core reconstruction: neighbors provide the context,
        the cube content is what we're trying to reconstruct.
        Injects language lexicon + AST constraints for maximum precision.

        previous_attempts: list of prior failed reconstructions (compressed
        by Muninn L1-L7) injected as negative examples so the model learns
        from its mistakes instead of retrying blind.
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

        # Try native FIM first if provider supports it
        if self.provider.supports_fim and before and after:
            ext_prefix = "\n".join(c.content for c in before)
            ext_suffix = "\n".join(c.content for c in after)
            return self.reconstruct_fim(ext_prefix, ext_suffix, max_tokens)

        # ─── FIM prompt: code with hole + constraints ────────────────
        n_lines = cube.line_end - cube.line_start + 1

        prefix = "\n".join(c.content for c in before[-4:]) if before else ""
        suffix = "\n".join(c.content for c in after[:4]) if after else ""

        # Detect indentation from suffix (first non-empty line)
        indent_hint = ""
        if suffix:
            for sline in suffix.split('\n'):
                if sline and sline != sline.lstrip():
                    indent_hint = sline[:len(sline) - len(sline.lstrip())]
                    break
        if not indent_hint and prefix:
            for pline in reversed(prefix.split('\n')):
                if pline and pline != pline.lstrip():
                    indent_hint = pline[:len(pline) - len(pline.lstrip())]
                    break

        # Build code block with hole
        code_parts = []
        if prefix:
            code_parts.append(prefix)
        code_parts.append(f"<FILL {n_lines} lines>")
        if suffix:
            code_parts.append(suffix)
        code_block = "\n".join(code_parts)

        # Compact prompt: file context + code with hole + all constraints
        prompt_parts = [
            f"File: {cube.file_origin} (lines {cube.line_start}-{cube.line_end} missing)",
            f"Write EXACTLY the {n_lines} missing lines. Output ONLY code. No fences.",
        ]

        # Indentation constraint
        if indent_hint:
            if '\t' in indent_hint:
                prompt_parts.append(f"Indentation: tabs ({len(indent_hint)} tab(s))")
            else:
                prompt_parts.append(f"Indentation: {len(indent_hint)} spaces")

        # AST constraints — functions, classes, imports AND variables
        if ast_hints:
            if ast_hints.get('functions'):
                prompt_parts.append(f"Functions defined here: {', '.join(ast_hints['functions'])}")
            if ast_hints.get('classes'):
                prompt_parts.append(f"Types/structs defined here: {', '.join(ast_hints['classes'])}")
            if ast_hints.get('imports'):
                prompt_parts.append(f"Imports: {', '.join(ast_hints['imports'])}")
            if ast_hints.get('variables'):
                prompt_parts.append(f"Variables used: {', '.join(ast_hints['variables'][:20])}")

        # Previous failed attempts — compact
        if previous_attempts:
            prompt_parts.append("Wrong attempts (do NOT repeat):")
            for i, attempt in enumerate(previous_attempts[-3:], 1):
                prompt_parts.append(f"#{i}: {attempt[:200]}")

        prompt_parts.append("")
        prompt_parts.append(code_block)
        prompt = "\n".join(prompt_parts)

        # Constrain output to ~1.5x expected size (not 3x)
        constrained_tokens = min(max_tokens, cube.token_count * 2)

        raw = self.provider.generate(prompt, max_tokens=constrained_tokens, temperature=temperature)

        # Clean response: remove code fences but PRESERVE indentation
        cleaned = raw
        # Strip only trailing whitespace, not leading (preserves indentation)
        cleaned = cleaned.rstrip()
        # Remove leading blank lines only
        while cleaned.startswith('\n'):
            cleaned = cleaned[1:]
        # Strip markdown code fences
        if cleaned.lstrip().startswith('```'):
            lines = cleaned.split('\n')
            # Find the opening fence
            start = 0
            for j, line in enumerate(lines):
                if line.lstrip().startswith('```'):
                    start = j + 1
                    break
            # Find the closing fence
            end = len(lines)
            for j in range(len(lines) - 1, start - 1, -1):
                if lines[j].lstrip().startswith('```'):
                    end = j
                    break
            cleaned = '\n'.join(lines[start:end])
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
                     ast_hints: dict | None = None,
                     previous_attempts: list[str] | None = None,
                     temperature: float = 0.0) -> ReconstructionResult:
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
        previous_attempts=previous_attempts,
        temperature=temperature,
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


# ─── B40: Wave result ──────────────────────────────────────────────────

@dataclass
class WaveResult:
    """Result of a die-and-retry wave on one cube."""
    cube_id: str
    sha_matched: bool
    wave_number: int          # which wave found SHA match (0 = not found)
    attempt_in_wave: int      # attempt within the winning wave (0 = not found)
    total_attempts: int       # total attempts across all waves
    best_ncd: float           # best NCD seen across all attempts
    best_reconstruction: str  # the closest reconstruction so far


@dataclass
class LevelResult:
    """Result of a full level run (all cubes at one size)."""
    level: int                # x1, x2, x3...
    target_tokens: int        # 112, 224, 336...
    n_cubes: int
    sha_matched: int
    sha_pct: float
    avg_best_ncd: float
    heatmap: list[WaveResult]


# ─── B40: Die-and-retry with waves ─────────────────────────────────────

def _compress_attempt(text: str) -> str:
    """Compress a failed attempt using Muninn L1-L7 (regex, no API).

    Falls back to truncation if muninn_layers is not available.
    """
    try:
        from engine.core.muninn_layers import compress_line
    except ImportError:
        try:
            from muninn_layers import compress_line
        except ImportError:
            compress_line = None

    if compress_line is not None:
        try:
            lines = text.split('\n')
            compressed = [compress_line(line) for line in lines]
            return '\n'.join(line for line in compressed if line.strip())
        except Exception:
            pass

    # Fallback: keep first 20 lines max
    lines = text.split('\n')
    return '\n'.join(lines[:20])


def reconstruct_cube_waves(cube: Cube, neighbors: list[Cube],
                           provider: LLMProvider,
                           attempts_per_wave: int = 11,
                           max_waves: int = 11,
                           ast_hints: dict | None = None,
                           temperature: float = 0.3,
                           on_attempt: callable = None) -> WaveResult:
    """
    B40: Die-and-retry reconstruction with waves.

    Each wave = `attempts_per_wave` tries. SHA-256 match = exit.
    Failed attempts are compressed by Muninn L1-L7 and injected
    as negative examples in the next attempt's prompt.

    on_attempt: optional callback(wave, attempt, ncd, sha_match) for progress.
    """
    all_failed: list[str] = []
    best_ncd = 1.0
    best_reconstruction = ""
    total_attempts = 0

    for wave in range(1, max_waves + 1):
        for attempt in range(1, attempts_per_wave + 1):
            total_attempts += 1

            # Compress previous failures for injection (last 3 max)
            compressed_attempts = None
            if all_failed:
                compressed_attempts = all_failed[-3:]

            try:
                result = reconstruct_cube(
                    cube, neighbors, provider,
                    ncd_threshold=0.0,  # we only care about SHA
                    ast_hints=ast_hints,
                    previous_attempts=compressed_attempts,
                    temperature=temperature,
                )

                if result.ncd_score < best_ncd:
                    best_ncd = result.ncd_score
                    best_reconstruction = result.reconstruction

                if on_attempt:
                    on_attempt(wave, attempt, result.ncd_score, result.exact_match)

                if result.exact_match:
                    return WaveResult(
                        cube_id=cube.id,
                        sha_matched=True,
                        wave_number=wave,
                        attempt_in_wave=attempt,
                        total_attempts=total_attempts,
                        best_ncd=result.ncd_score,
                        best_reconstruction=result.reconstruction,
                    )

                # Compress this failed attempt for next iteration
                all_failed.append(_compress_attempt(result.reconstruction))

            except Exception:
                if on_attempt:
                    on_attempt(wave, attempt, 1.0, False)

    # All waves exhausted, no SHA match
    return WaveResult(
        cube_id=cube.id,
        sha_matched=False,
        wave_number=0,
        attempt_in_wave=0,
        total_attempts=total_attempts,
        best_ncd=best_ncd,
        best_reconstruction=best_reconstruction,
    )


# ─── B41: Progressive levels with mycelium accumulation ────────────────

def run_progressive_levels(file_path: str, content: str,
                           provider: LLMProvider,
                           base_tokens: int = 112,
                           max_levels: int = 11,
                           attempts_per_wave: int = 11,
                           max_waves: int = 11,
                           max_cubes_per_level: int = 20,
                           mycelium_db_path: str = None,
                           ast_hints: dict | None = None,
                           on_cube: callable = None,
                           on_level: callable = None) -> list[LevelResult]:
    """
    B41: Progressive level reconstruction with mycelium accumulation.

    Level x1: cubes of base_tokens (112). Waves until SHA or exhaustion.
    Level x2: cubes of base_tokens*2 (224). Mycelium carries over from x1.
    Level x3: cubes of base_tokens*3 (336). Mycelium carries over from x1+x2.
    ...up to max_levels.

    Each successful SHA reconstruction feeds the mycelium via observe(),
    so later levels benefit from accumulated co-occurrence knowledge.
    """
    from cube import CubeStore, subdivide_file, assign_neighbors

    # Optional mycelium wiring
    mycelium = None
    if mycelium_db_path:
        try:
            from engine.core.mycelium_db import MyceliumDB
            mycelium = MyceliumDB(mycelium_db_path)
        except ImportError:
            try:
                from mycelium_db import MyceliumDB
                mycelium = MyceliumDB(mycelium_db_path)
            except ImportError:
                pass

    results: list[LevelResult] = []
    import tempfile, shutil

    for level in range(1, max_levels + 1):
        target_tokens = base_tokens * level

        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, f"level_{level}.db")

        cubes = subdivide_file(
            content=content, file_path=file_path,
            target_tokens=target_tokens,
        )
        store = CubeStore(db_path)
        for c in cubes:
            store.save_cube(c)
        assign_neighbors(cubes, [], store, max_neighbors=9)

        n = min(len(cubes), max_cubes_per_level)
        heatmap: list[WaveResult] = []

        for i in range(n):
            tc = cubes[i]
            ne = store.get_neighbors(tc.id)
            nc = [store.get_cube(nid) for nid, _, _ in ne if store.get_cube(nid)]

            wave_result = reconstruct_cube_waves(
                tc, nc, provider,
                attempts_per_wave=attempts_per_wave,
                max_waves=max_waves,
                ast_hints=ast_hints,
                on_attempt=None,
            )
            heatmap.append(wave_result)

            if on_cube:
                on_cube(level, i + 1, n, wave_result)

            # Feed mycelium on SHA match — accumulate learning
            if wave_result.sha_matched and mycelium is not None:
                mycelium.observe(wave_result.best_reconstruction,
                                zone=f"cube_level_{level}")

        sha_matched = sum(1 for w in heatmap if w.sha_matched)
        avg_ncd = (sum(w.best_ncd for w in heatmap) / len(heatmap)
                   if heatmap else 1.0)

        level_result = LevelResult(
            level=level,
            target_tokens=target_tokens,
            n_cubes=n,
            sha_matched=sha_matched,
            sha_pct=100.0 * sha_matched / n if n else 0.0,
            avg_best_ncd=avg_ncd,
            heatmap=heatmap,
        )
        results.append(level_result)

        if on_level:
            on_level(level_result)

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)

        # Early exit: if 100% SHA at this level, no need to continue
        if sha_matched == n:
            break

    return results


