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
        # Use normalized line count (not raw line_start/end which may include
        # trailing blanks that normalize_content strips)
        from cube import normalize_content as _nc
        n_lines = len(_nc(cube.content).split('\n'))

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
            f"Write EXACTLY {n_lines} lines. Output ONLY code. No fences. No explanation.",
        ]

        # Indentation constraint
        if indent_hint:
            if '\t' in indent_hint:
                prompt_parts.append(f"Indentation: tabs")
            else:
                prompt_parts.append(f"Indentation: {len(indent_hint)} spaces")

        # Line anchors — first, last, + checkpoints
        if ast_hints:
            if ast_hints.get('first_line'):
                prompt_parts.append(f"Line 1: {ast_hints['first_line']}")
            if ast_hints.get('anchors'):
                for line_num, line_text in ast_hints['anchors'][:5]:
                    prompt_parts.append(f"Line {line_num}: {line_text}")
            if ast_hints.get('last_line'):
                prompt_parts.append(f"Line {n_lines}: {ast_hints['last_line']}")

            # All identifiers found in the missing code
            if ast_hints.get('identifiers'):
                cube_ids = set(ast_hints['identifiers'])
                prompt_parts.append(f"Identifiers: {', '.join(ast_hints['identifiers'][:30])}")

                # Cross-reference: identifiers from neighbors that match cube's identifiers
                # This catches method names called in neighbors (e.g. mc.flushLoop())
                neighbor_ids = set()
                for n in neighbors:
                    n_text = n.content if hasattr(n, 'content') else ''
                    n_ids = set(re.findall(r'\b([a-zA-Z_]\w{1,})\b', n_text))
                    neighbor_ids.update(n_ids)
                shared = sorted(cube_ids & neighbor_ids)
                if shared:
                    prompt_parts.append(f"Confirmed by neighbors: {', '.join(shared[:20])}")

            # Structured hints (backward compat)
            if ast_hints.get('functions'):
                prompt_parts.append(f"Functions: {', '.join(ast_hints['functions'])}")
            if ast_hints.get('classes'):
                prompt_parts.append(f"Types: {', '.join(ast_hints['classes'])}")
            if ast_hints.get('variables'):
                prompt_parts.append(f"Variables: {', '.join(ast_hints['variables'][:20])}")

        # Best previous attempt — positive memory (improve, don't avoid)
        if previous_attempts and previous_attempts[0]:
            prompt_parts.append("Your best attempt so far (improve it, fix errors):")
            prompt_parts.append(previous_attempts[0])

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

        # Smart line count adjustment
        out_lines = cleaned.split('\n')
        if len(out_lines) > n_lines:
            # Too many lines: join continuation lines
            cleaned = _adjust_line_count(out_lines, n_lines)
        elif len(out_lines) < n_lines:
            # Too few lines: insert missing blank lines using anchors
            cleaned = _insert_missing_blanks(out_lines, n_lines, ast_hints)

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

def _annealing_schedule(n: int) -> list[float]:
    """Generate a cold-hot-cold temperature schedule for n attempts.

    Starts at 0.0 (deterministic best guess), ramps up to explore,
    then cools down to refine. Like metal annealing — heat to reshape,
    cool to set.

    Kirkpatrick et al. 1983 + Zhou et al. 2023 (AdapT for code).
    """
    if n <= 1:
        return [0.0]
    if n <= 3:
        return [0.0, 0.2, 0.0][:n]

    # Peak at ~40% through the schedule
    peak_idx = max(1, int(n * 0.4))
    peak_temp = 0.4  # max exploration temperature

    schedule = []
    for i in range(n):
        if i <= peak_idx:
            # Ramp up: 0.0 → peak_temp
            t = peak_temp * (i / peak_idx)
        else:
            # Cool down: peak_temp → 0.0
            remaining = n - 1 - peak_idx
            if remaining > 0:
                t = peak_temp * (1.0 - (i - peak_idx) / remaining)
            else:
                t = 0.0
        schedule.append(round(t, 3))

    # Force first and last to 0.0 (deterministic bookends)
    schedule[0] = 0.0
    schedule[-1] = 0.0
    return schedule


def _is_continuation(prev_line: str, curr_line: str) -> float:
    """Detect if curr_line is a continuation of prev_line.

    Returns a score 0.0 (not continuation) to 1.0 (definitely continuation).
    Language-agnostic: based on ending character + indentation difference.

    Higher score = more likely a line wrap (not a new block).
    - `(` alone at end = 1.0 (function call split)
    - `,` at end = 0.8 (argument list)
    - `{` at end = 0.1 (block open — usually NOT a line wrap)
    """
    prev_stripped = prev_line.rstrip()
    if not prev_stripped or not curr_line.strip():
        return 0.0

    # Current line must be indented more than previous
    prev_indent = len(prev_line) - len(prev_line.lstrip())
    curr_indent = len(curr_line) - len(curr_line.lstrip())
    if curr_indent <= prev_indent:
        return 0.0

    last_char = prev_stripped[-1]

    # Score by ending character — how likely is this a line wrap?
    scores = {
        '(': 1.0,    # function call split — almost always a wrap
        ',': 0.8,    # argument list continuation
        '.': 0.7,    # method chain
        '+': 0.7, '-': 0.6,  # expression continuation
        '[': 0.5,    # array/index
        '?': 0.5, ':': 0.4,  # ternary
        '\\': 0.9,   # explicit line continuation
        '{': 0.1,    # block open — usually NOT a wrap
        '|': 0.3, '&': 0.3,
    }
    score = scores.get(last_char, 0.0)

    # Operators
    if prev_stripped.endswith(('||', '&&')):
        score = 0.6

    return score


def _adjust_line_count(lines: list[str], target: int) -> str:
    """Adjust output to target line count by joining continuation lines.

    Language-agnostic: finds lines that are continuations of the previous
    line (more indented + prev ends with open delimiter) and joins them.
    Picks the SHORTEST continuation lines first (most obvious joins).
    Only joins as many as needed to reach the target count.

    Falls back to truncation if no joinable lines found.
    """
    if len(lines) <= target:
        return '\n'.join(lines)

    excess = len(lines) - target
    result = list(lines)

    for _ in range(excess):
        # Find all joinable pairs, pick highest score (most likely a line wrap)
        candidates = []
        for i in range(1, len(result)):
            score = _is_continuation(result[i - 1], result[i])
            if score > 0.0:
                candidates.append((-score, i))  # negative for descending sort

        if not candidates:
            break  # no more joinable pairs

        # Join the highest-score pair first (most obvious line wrap)
        candidates.sort()
        _, best_idx = candidates[0]
        prev = result[best_idx - 1].rstrip()
        # No space after open paren/bracket — natural join
        if prev and prev[-1] in ('(', '['):
            combined = prev + result[best_idx].strip()
        else:
            combined = prev + ' ' + result[best_idx].strip()
        result[best_idx - 1] = combined
        result.pop(best_idx)

    # If still too many lines, truncate as last resort
    if len(result) > target:
        result = result[:target]

    return '\n'.join(result)


def _insert_missing_blanks(lines: list[str], target: int,
                           ast_hints: dict | None = None) -> str:
    """Insert missing blank lines to reach target line count.

    When the LLM generates fewer lines than expected, it's almost always
    because it skipped blank separator lines between code blocks.

    Strategy: find positions where a blank line belongs (after closing
    braces, before function declarations, between logical sections)
    and insert blanks until we reach target count.

    Language-agnostic: uses structural patterns (closing brace followed
    by non-blank = missing separator).
    """
    if len(lines) >= target:
        return '\n'.join(lines)

    missing = target - len(lines)
    result = list(lines)

    # Find insertion points: after } or end-of-block, before new declaration
    # These are places where blank separators naturally go
    candidates = []
    for i in range(len(result) - 1):
        curr = result[i].strip()
        next_line = result[i + 1].strip()

        # After closing brace/end, before non-blank non-brace
        if curr in ('}', 'end', 'end.', 'END', 'END.') and next_line and next_line not in ('}', ')'):
            candidates.append(i + 1)

        # After return/break before new function/type
        if curr.startswith(('return ', 'return\t')) and next_line.startswith(('func ', 'def ', 'class ', 'type ', 'fn ', 'pub ')):
            candidates.append(i + 1)

    # If anchors available, prefer positions that match anchor line numbers
    if ast_hints and ast_hints.get('anchors'):
        for anchor_num, anchor_text in ast_hints['anchors']:
            if anchor_text.strip() == '' and 0 < anchor_num <= len(result) + missing:
                # This anchor IS a blank line — prioritize inserting here
                if anchor_num - 1 not in candidates:
                    candidates.insert(0, min(anchor_num - 1, len(result)))

    # Insert blanks at best candidates (from bottom to top to preserve indices)
    candidates = sorted(set(candidates), reverse=True)
    inserted = 0
    for pos in candidates:
        if inserted >= missing:
            break
        result.insert(pos, '')
        inserted += 1

    # If still short, insert at end
    while len(result) < target:
        result.append('')

    return '\n'.join(result)


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
                           max_waves: int = 1,
                           ast_hints: dict | None = None,
                           temperature: float = 0.3,
                           ncd_give_up: float = 0.3,
                           on_attempt: callable = None) -> WaveResult:
    """
    B40: Annealing reconstruction — 1 wave, variable temperature.

    Temperature schedule: cold → hot → cold (simulated annealing in 1 wave).
    Stops early on SHA match. Gives up if best NCD > ncd_give_up after wave.
    Positive memory: injects best attempt so far for refinement.

    Based on AdapT (Zhou et al. 2023, AAAI 2024) + simulated annealing
    (Kirkpatrick et al. 1983). Max 11 API calls per cube.

    on_attempt: optional callback(wave, attempt, ncd, sha_match) for progress.
    """
    # Annealing schedule: cold-hot-cold
    # Start deterministic (best guess), explore (find alternatives), refine (lock in)
    n = attempts_per_wave
    schedule = _annealing_schedule(n)

    best_ncd = 1.0
    best_reconstruction = ""
    total_attempts = 0

    for wave in range(1, max_waves + 1):
        for attempt in range(1, n + 1):
            total_attempts += 1
            temp = schedule[attempt - 1] if attempt <= len(schedule) else temperature

            # Pure Best-of-N: each attempt is independent (no memory injection)
            # Data shows memory (positive or negative) makes results WORSE.
            # Best NCD is always attempt 1 (no context pollution).
            try:
                result = reconstruct_cube(
                    cube, neighbors, provider,
                    ncd_threshold=0.0,
                    ast_hints=ast_hints,
                    previous_attempts=None,
                    temperature=temp,
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

            except Exception:
                if on_attempt:
                    on_attempt(wave, attempt, 1.0, False)

        # After wave: give up if too far
        if best_ncd > ncd_give_up:
            break  # this cube needs a bigger level, stop wasting calls

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

            # Extract AST hints per cube (not global)
            try:
                from cube import extract_ast_hints as _extract
                cube_hints = _extract(tc)
            except ImportError:
                cube_hints = ast_hints

            wave_result = reconstruct_cube_waves(
                tc, nc, provider,
                attempts_per_wave=attempts_per_wave,
                max_waves=max_waves,
                ast_hints=cube_hints,
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


