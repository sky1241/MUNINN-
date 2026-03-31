"""Muninn UI — AI Provider Configuration.

Persists provider choice + API keys in ~/.muninn/ui_config.json.
Keys are stored base64-encoded (not encryption — just not plaintext on disk).
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional

_CONFIG_DIR = Path.home() / ".muninn"
_CONFIG_FILE = _CONFIG_DIR / "ui_config.json"

# Supported providers and their default models
PROVIDERS = {
    "claude": {
        "label": "Claude (Anthropic)",
        "models": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-6"],
        "default_model": "claude-haiku-4-5-20251001",
        "env_key": "ANTHROPIC_API_KEY",
        "needs_key": True,
    },
    "openai": {
        "label": "GPT (OpenAI)",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "needs_key": True,
    },
    "ollama": {
        "label": "Ollama (Local)",
        "models": ["llama3.1", "mistral", "phi3", "codellama", "deepseek-coder"],
        "default_model": "llama3.1",
        "env_key": None,
        "needs_key": False,
    },
    "ollama-smart": {
        "label": "Ollama Smart (Router)",
        "models": [],
        "default_model": "",
        "env_key": None,
        "needs_key": False,
    },
    "off": {
        "label": "Off (Echo)",
        "models": [],
        "default_model": "",
        "env_key": None,
        "needs_key": False,
    },
}


def _encode(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _decode(s: str) -> str:
    try:
        return base64.b64decode(s.encode()).decode()
    except Exception:
        return s


def load_config() -> dict:
    """Load config from ~/.muninn/ui_config.json."""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(cfg: dict):
    """Save config to ~/.muninn/ui_config.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_active_provider() -> str:
    """Return current provider name (claude/openai/ollama/off)."""
    cfg = load_config()
    return cfg.get("provider", "off")


def set_active_provider(name: str):
    """Set the active provider."""
    cfg = load_config()
    cfg["provider"] = name
    save_config(cfg)


def get_active_model() -> str:
    """Return current model for active provider."""
    cfg = load_config()
    provider = cfg.get("provider", "off")
    return cfg.get(f"{provider}_model", PROVIDERS.get(provider, {}).get("default_model", ""))


def set_active_model(provider: str, model: str):
    """Set the model for a provider."""
    cfg = load_config()
    cfg[f"{provider}_model"] = model
    save_config(cfg)


def get_api_key(provider: str) -> str:
    """Get API key — config first, then env var."""
    cfg = load_config()
    stored = cfg.get(f"{provider}_key", "")
    if stored:
        return _decode(stored)
    env_var = PROVIDERS.get(provider, {}).get("env_key")
    if env_var:
        return os.environ.get(env_var, "")
    return ""


def set_api_key(provider: str, key: str):
    """Store API key (base64-encoded)."""
    cfg = load_config()
    cfg[f"{provider}_key"] = _encode(key) if key else ""
    save_config(cfg)


def get_mycelium_boost() -> bool:
    """Whether AI responses should feed the mycelium."""
    cfg = load_config()
    return cfg.get("mycelium_boost", True)


def set_mycelium_boost(enabled: bool):
    """Toggle mycelium boost."""
    cfg = load_config()
    cfg["mycelium_boost"] = enabled
    save_config(cfg)


def create_provider(provider_name: Optional[str] = None, model: Optional[str] = None):
    """Factory: create a lightweight LLM provider instance from config.

    Returns None if provider is 'off' or unavailable.
    Uses lightweight wrappers that avoid heavy cube_providers dependencies.
    """
    name = provider_name or get_active_provider()
    if name == "off":
        return None

    mdl = model or get_active_model()
    key = get_api_key(name)

    if name == "claude":
        if not key:
            return None
        return _ClaudeLite(model=mdl or "claude-haiku-4-5-20251001", api_key=key)
    elif name == "openai":
        if not key:
            return None
        return _OpenAILite(model=mdl or "gpt-4o-mini", api_key=key)
    elif name == "ollama":
        return _OllamaLite(model=mdl or "llama3.1")
    elif name == "ollama-smart":
        from muninn.ui.ai_router import SmartRouter
        return SmartRouter()
    return None


# --- Lightweight provider wrappers (no cube dependency) ---

class _ClaudeLite:
    """Minimal Claude provider for terminal chat (streaming)."""
    name = "claude"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        client = self._get_client()
        kwargs = dict(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        if system:
            kwargs['system'] = system
        with client.messages.stream(**kwargs) as s:
            for text in s.text_stream:
                yield text

    def list_models(self):
        return ['claude-haiku-4-5-20251001', 'claude-sonnet-4-6', 'claude-opus-4-6']


class _OpenAILite:
    """Minimal OpenAI provider for terminal chat (streaming)."""
    name = "openai"

    def __init__(self, model: str, api_key: str):
        self.model = model
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        client = self._get_client()
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        resp = client.chat.completions.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            messages=messages, stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def list_models(self):
        return ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo']


class _OllamaLite:
    """Minimal Ollama provider for terminal chat (streaming)."""
    name = "ollama"

    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip('/')

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        import json as _json
        import urllib.request
        payload = {
            'model': self.model,
            'prompt': prompt,
            'options': {'num_predict': max_tokens, 'temperature': temperature},
            'stream': True,
        }
        if system:
            payload['system'] = system
        url = f"{self.base_url}/api/generate"
        data = _json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if line.strip():
                    chunk = _json.loads(line)
                    text = chunk.get('response', '')
                    if text:
                        yield text
                    if chunk.get('done', False):
                        break

    def list_models(self):
        import json as _json
        import urllib.request
        try:
            url = f"{self.base_url}/api/tags"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
                return [m['name'] for m in data.get('models', [])]
        except Exception:
            return []
