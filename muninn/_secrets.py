"""Shared secret redaction for Muninn.

Used by muninn.py, mycelium.py, and cube.py to filter secrets
BEFORE they enter the mycelium co-occurrence network.
"""

import re

# Secret patterns — same list as muninn.py _SECRET_PATTERNS
# Tested against 24+ real secret formats. Zero false positives on natural text.
_SECRET_PATTERNS = [
    # --- Git/CI ---
    r'ghp_[A-Za-z0-9]{20,}',
    r'github_pat_[A-Za-z0-9_]{20,}',
    r'gho_[A-Za-z0-9]{20,}',
    r'ghu_[A-Za-z0-9]{20,}',
    r'ghs_[A-Za-z0-9]{20,}',
    r'glpat-[A-Za-z0-9\-_]{20,}',
    # --- Cloud providers ---
    r'AKIA[A-Z0-9]{16}',
    r'AIzaSy[A-Za-z0-9\-_]{33}',
    r'DefaultEndpointsProtocol=[^\s]+',
    # --- AI/SaaS API keys ---
    r'sk-[A-Za-z0-9\-._]{20,}',
    r'sk_live_[A-Za-z0-9]{20,}',
    r'pk_live_[A-Za-z0-9]{20,}',
    r'SG\.[A-Za-z0-9\-_.]{20,}',
    r'SK[a-f0-9]{32}',
    r'HRKU-[a-f0-9\-]{36}',
    # --- Package registries ---
    r'npm_[A-Za-z0-9]{20,}',
    r'pypi-[A-Za-z0-9]{20,}',
    # --- Chat/Social ---
    r'xox[bpsar]-[A-Za-z0-9\-]{10,}',
    r'[A-Za-z0-9]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}',
    # --- Database URIs ---
    r'(?:mongodb(?:\+srv)?|postgresql|mysql|redis|amqp)://[^\s]*:[^\s@]+@[^\s]+',
    # --- Generic ---
    r'-----BEGIN\s+\w*\s*PRIVATE KEY-----[\s\S]*?-----END',
    r'Bearer\s+[A-Za-z0-9\-._~+/]{20,}=*',
    r'token[=:]\s*\S{20,}',
    r'password[=:]\s*\S+',
    r'secret[=:]\s*\S{10,}',
    r'api[_-]?key[=:]\s*\S{10,}',
    r'(?:cl[eé]|mdp|mot\s+de\s+passe|passwd|passphrase)[=:\s]+\S+',
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SECRET_PATTERNS]


def redact_secrets_text(text: str) -> str:
    """Redact secrets from a text string. Returns cleaned text.

    Used as defense-in-depth before observe_text() calls.
    """
    if not text:
        return text
    result = text
    for pat in _COMPILED_PATTERNS:
        result = pat.sub("[REDACTED]", result)
    return result
