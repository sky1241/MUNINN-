#!/usr/bin/env python3
"""
Muninn tokenizer wrapper — real token counting with graceful fallback.

Tries in order:
1. tiktoken (cl100k_base, same as Claude) — pip install tiktoken
2. Estimate: len(text) // 4 (fallback, ~20-40% off)

Returns (count, method) where method is "tiktoken" or "estimate".
"""

_tiktoken_enc = None
_method = None


def count_tokens(text: str) -> tuple[int, str]:
    """Count tokens in text. Returns (count, method_name)."""
    global _tiktoken_enc, _method

    if not isinstance(text, str):
        text = str(text) if text is not None else ""

    # Try tiktoken (cached encoder)
    if _method is None or _method == "tiktoken":
        try:
            if _tiktoken_enc is None:
                import tiktoken
                _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
                _method = "tiktoken"
            return len(_tiktoken_enc.encode(text)), "tiktoken"
        except ImportError:
            _method = "estimate"
        except Exception:
            _method = "estimate"

    # Fallback: character-based estimate
    return len(text) // 4, "estimate"


def token_count(text: str) -> int:
    """Simple version — just the count, no method."""
    count, _ = count_tokens(text)
    return count
