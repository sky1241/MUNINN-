"""Muninn UI — Smart AI Router.

Routes queries to the best local Ollama model based on content analysis.
One model active at a time (RAM-safe for 16 Go machines).

Models:
  - deepseek-coder  → code questions, debugging, implementation
  - mistral          → general knowledge, French, explanations, reasoning
"""

import re
import json
import urllib.request
import urllib.error

# Keywords that signal code-related queries
_CODE_SIGNALS = {
    # Programming languages
    "python", "javascript", "typescript", "java", "rust", "go", "c++", "ruby",
    "html", "css", "sql", "bash", "shell", "powershell",
    # Code concepts
    "function", "class", "method", "variable", "loop", "array", "list", "dict",
    "import", "module", "package", "library", "framework", "api", "endpoint",
    "bug", "error", "exception", "traceback", "debug", "fix", "crash",
    "git", "commit", "push", "pull", "merge", "branch", "rebase",
    "test", "unittest", "pytest", "assert",
    "refactor", "optimize", "compile", "build", "deploy",
    "regex", "parse", "json", "xml", "yaml", "csv",
    "def", "return", "if", "else", "for", "while", "try", "except",
    "pip", "npm", "cargo", "docker", "kubernetes",
    # Code patterns
    "code", "script", "snippet", "implementation", "algorithm",
    "fonction", "boucle", "variable", "erreur", "compiler",  # French
    "implementer", "debugger", "coder", "programmer",
}

# Patterns that strongly signal code
_CODE_PATTERNS = [
    r'```',                    # code blocks
    r'def\s+\w+',             # function defs
    r'class\s+\w+',           # class defs
    r'import\s+\w+',          # imports
    r'\w+\.\w+\(',            # method calls
    r'[{}\[\]();]',           # code punctuation
    r'\w+_\w+',               # snake_case
    r'[A-Z][a-z]+[A-Z]',     # camelCase
    r'\.py|\.js|\.ts|\.rs',   # file extensions
    r'#\s*\w+|//\s*\w+',     # comments
]

# Model assignments
MODEL_CODE = "deepseek-coder:6.7b"
MODEL_GENERAL = "mistral:7b"


def classify_query(text: str) -> str:
    """Classify a query as 'code' or 'general'.

    Returns the model name to use.
    """
    text_lower = text.lower()
    words = set(re.findall(r'[a-zA-Zà-ÿ_]+', text_lower))

    # Score code signals
    code_score = 0
    for w in words:
        if w in _CODE_SIGNALS:
            code_score += 1

    # Check regex patterns
    for pat in _CODE_PATTERNS:
        if re.search(pat, text):
            code_score += 2  # patterns are stronger signals

    # Threshold: 2+ code signals = code query
    if code_score >= 2:
        return MODEL_CODE
    return MODEL_GENERAL


def get_available_models(base_url: str = "http://localhost:11434") -> list[str]:
    """Get list of models installed in Ollama."""
    try:
        url = f"{base_url}/api/tags"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return [m['name'] for m in data.get('models', [])]
    except Exception:
        return []


def pick_model(text: str, base_url: str = "http://localhost:11434") -> str:
    """Pick the best available model for a query.

    Falls back gracefully: if the ideal model isn't installed, uses whatever is available.
    """
    ideal = classify_query(text)
    available = get_available_models(base_url)

    if not available:
        return ideal  # Ollama will error anyway, return ideal for the error msg

    # Check if ideal model is available (partial match for tag variations)
    ideal_base = ideal.split(":")[0]
    for m in available:
        if ideal_base in m:
            return m

    # Fallback: use whatever is installed
    return available[0]


def get_route_label(model: str) -> str:
    """Human-readable label for the routed model."""
    if "deepseek" in model or "code" in model:
        return "code"
    elif "mistral" in model:
        return "general"
    elif "llama" in model:
        return "general"
    elif "phi" in model:
        return "fast"
    return model.split(":")[0]


class SmartRouter:
    """Smart router that picks the best Ollama model per query.

    Streams responses, one model at a time (RAM-safe).
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        self.name = "ollama-smart"
        self._last_model = ""
        self._last_route = ""

    @property
    def last_route(self) -> str:
        """Which model was last used (for UI display)."""
        return self._last_route

    def stream(self, prompt: str, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.3):
        """Route query to best model and stream response."""
        model = pick_model(prompt, self.base_url)
        self._last_model = model
        self._last_route = get_route_label(model)

        payload = {
            'model': model,
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
        with urllib.request.urlopen(req, timeout=300) as resp:
            for line in resp:
                if line.strip():
                    chunk = json.loads(line)
                    text = chunk.get('response', '')
                    if text:
                        yield text
                    if chunk.get('done', False):
                        break

    def list_models(self):
        return get_available_models(self.base_url)
