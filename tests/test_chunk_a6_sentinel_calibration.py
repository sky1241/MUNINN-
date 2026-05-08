"""CHUNK A6 — Sentinel calibration (cry-wolf reduction).

Live observation during the audit session: the Sentinel triggered 5+
times on prompts WITHOUT real secrets, just because the words `secret`,
`key`, `auth` appeared in technical discussions about security patterns.
User loses trust → ignores real warnings.

Fix: word boundaries on trigger words; remove `auth` / standalone `key`
as triggers; raise entropy threshold from 2.8 → 3.5 for the trigger-
adjacent check; constrain the entropy check to a 3-word window around
the trigger instead of scanning every word in the prompt.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §A6
"""
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_bridge_hook_module():
    """Load .claude/hooks/bridge_hook.py under a unique module name."""
    repo = Path(__file__).resolve().parent.parent
    src = repo / ".claude" / "hooks" / "bridge_hook.py"
    spec = importlib.util.spec_from_file_location("_chunk_a6_bridge_hook", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bridge_hook():
    return _load_bridge_hook_module()


# ---------- Negative tests: prompts that triggered FP live this session ----

LIVE_FALSE_POSITIVE_PROMPTS = [
    # All these were observed triggering [MUNINN SENTINEL] during the audit
    # session of 2026-05-08 with NO actual secret in the message.
    "L'agent 5 disait que compress_file redactait avant L9. Faux.",
    "regarde les keys du mycelium qui sont stale",
    "le pattern auth_trigger est trop large dans bridge_hook",
    "audit security patterns secret_key in code",
    "Pour A4, je veux ajouter une validation que transcript_path",
    "ouais va si depart par chunk un push git donc avec teste reelle",
    # Common audit jargon
    "je dois fixer la fonction has_authentication dans le module",
    "le mot de passe est gere par la fonction password_hash",  # mentions term but no value
    "key=value parsing in the config loader",  # key=value generic
]


@pytest.mark.parametrize("prompt", LIVE_FALSE_POSITIVE_PROMPTS)
def test_no_fp_on_live_audit_prompts(bridge_hook, prompt):
    """Prompts that triggered FP during the live audit must now return None."""
    result = bridge_hook._check_secrets(prompt)
    assert result is None, (
        f"FALSE POSITIVE on audit prompt:\n  prompt: {prompt!r}\n  triggered: {result}"
    )


# ---------- Positive tests: real secrets MUST still be detected ----

REAL_SECRETS_PROMPTS = [
    "Voici mon api_key=ghp_aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH a rotater",
    "Token sk-aB3xY9zP4kL2nM7vQ8rT5sW1uE6iO0jH dans un .env",
    "AWS access key AKIAIOSFODNN7EXAMPLE leaked yesterday",
    "header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9aB",
]


@pytest.mark.parametrize("prompt", REAL_SECRETS_PROMPTS)
def test_real_secrets_still_detected(bridge_hook, prompt):
    """API key patterns (structural) must still be caught."""
    result = bridge_hook._check_secrets(prompt)
    assert result is not None, f"FAILED to detect real secret in: {prompt!r}"
    assert "MUNINN SENTINEL" in result


# ---------- Edge cases ----

def test_sha_short_no_fp(bridge_hook):
    """Git short SHA in audit message must not trigger FP."""
    msg = "le commit 5858445 a fix le path traversal"
    assert bridge_hook._check_secrets(msg) is None


def test_high_entropy_password_in_explicit_context_caught(bridge_hook):
    """Long high-entropy string AFTER an explicit trigger word is a real secret."""
    # Strong password near trigger word "password"
    msg = "password=Tr0ub4dor&3xK7p9qZmN2vWLpR will be rotated"
    result = bridge_hook._check_secrets(msg)
    # The structural pattern `password[=:]\s*\S+` should catch it via API patterns
    # OR the trigger+entropy check should catch it.
    # We accept either.
    assert result is not None, f"missed strong password near trigger: {msg!r}"


def test_typing_a_real_password(bridge_hook):
    """User actually typing a password (high entropy, len > 10) MUST be caught."""
    msg = "the password is xK7p9qZmNvWLpR2"
    result = bridge_hook._check_secrets(msg)
    assert result is not None, f"missed user-typed password: {msg!r}"


def test_clean_prose_unchanged(bridge_hook):
    """Plain prose without secret indicators must return None."""
    cases = [
        "Hello there, how are you today?",
        "Just running pytest on tests/ and seeing what passes",
        "Le mycelium est branche correctement dans engine/core/",
        "Refactor these 3 functions to be smaller please",
    ]
    for msg in cases:
        assert bridge_hook._check_secrets(msg) is None, f"FP on clean prose: {msg!r}"
