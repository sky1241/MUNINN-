"""Compatibility shim — source of truth: engine/core/embeddings.py.

K.2 (2026-05-14): cross-lingual sentence-embedding provider. The shim
pattern matches mycelium.py / mycelium_db.py so the package layout stays
consistent and `muninn._engine` (with `engine/core` on sys.path) keeps
working without duplicating code.
"""

import sys
from pathlib import Path

_engine_core = str(Path(__file__).resolve().parent.parent / "engine" / "core")
if _engine_core not in sys.path:
    sys.path.insert(0, _engine_core)

# Pop ourselves so the next import resolves to the canonical module.
sys.modules.pop("embeddings", None)

from embeddings import EmbeddingProvider, DEFAULT_MODEL, DEFAULT_THRESHOLD, DEFAULT_LRU_CAPACITY  # noqa: E402,F401

__all__ = ["EmbeddingProvider", "DEFAULT_MODEL", "DEFAULT_THRESHOLD", "DEFAULT_LRU_CAPACITY"]
