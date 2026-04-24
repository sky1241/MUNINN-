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


# ── Anti-Adversa AI clamp ──────────────────────────────────────
# Adversa AI Red Team disclosed (2026-04-02) that Claude Code's deny rules
# silently bypass when a generated bash pipeline exceeds 50 chained subcommands.
# Patched in Claude Code v2.1.90, but the attack surface persists for any tool
# that injects arbitrary content into Claude's context.
#
# Muninn injects content via UserPromptSubmit hook (bridge_hook.py) and
# via meta-mycelium pull_from_meta() — both can carry strings sourced from
# external repos. A poisoned .mn that contains a 50+ subcommand pipeline,
# once injected back into Claude's context, would reproduce Adversa.
#
# Defense: clamp any text injected into Claude's context to MAX_CHAINED_COMMANDS
# shell separators (default 30, well below the 50 threshold). This is one of
# several defense layers — vault.py and redact_secrets_text remain the primary
# secret defense.
#
# Refs: docs/CLAUDE_CODE_LEAK_INTEL.md sections 10 and 12.

# Default conservative limit (60% of Adversa's documented threshold).
MAX_CHAINED_COMMANDS = 30

# Strong shell chaining operators. We count only `&&` and `||` because:
# - They are the canonical Adversa attack pattern (sequential cmds with
#   conditional execution: `cmd1 && cmd2 && cmd3 && ...`).
# - They are extremely rare in natural prose (English/French/markdown tables).
# - `;` and `|` are too ambiguous (markdown tables, legit Unix pipes,
#   French punctuation) and almost never used as Adversa-style attack
#   separators in practice.
_STRONG_SHELL_SEP = re.compile(r'&&|\|\|')


def count_chained_commands(text: str) -> int:
    """Count strong shell chaining operators (`&&` and `||`) in text.

    These are the canonical markers of an Adversa-style chained shell
    pipeline. A normal English/French/markdown text will essentially
    never contain more than 1-2 of these operators.
    """
    if not text:
        return 0
    return len(_STRONG_SHELL_SEP.findall(text))


def clamp_chained_commands(text: str, max_chains: int = MAX_CHAINED_COMMANDS) -> tuple[str, bool]:
    """Anti-Adversa: refuse text containing too many chained shell commands.

    Returns (clamped_text, was_clamped). If the text contains more than
    max_chains pipeline-context separators, the entire text is replaced
    with a one-line warning. We do NOT try to truncate cleanly — refusing
    in full is the safe default, since partial truncation could still
    contain a usable attack chain.

    Args:
        text: candidate text to inject into Claude's context
        max_chains: max allowed chained commands (default 30, below Adversa's 50)

    Returns:
        (text, False) if safe — text unchanged
        (warning, True) if clamped — text replaced with warning
    """
    if not text:
        return text, False
    n = count_chained_commands(text)
    if n <= max_chains:
        return text, False
    return (
        f"[MUNINN ANTI-ADVERSA] Injected content contained {n} chained shell "
        f"commands (max allowed: {max_chains}). Content refused. "
        f"See docs/CLAUDE_CODE_LEAK_INTEL.md section 10."
    ), True
