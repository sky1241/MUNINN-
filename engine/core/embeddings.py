"""K.2 (2026-05-14): cross-lingual sentence-embedding provider.

Wraps sentence-transformers to give Mycelium a single place to:
  1. Lazy-load LaBSE (or any HF model) without paying the import cost
     when MUNINN_EMBEDDINGS is disabled.
  2. Cache embeddings in-memory (LRU) so repeated lookups within a
     session are free.
  3. Persist embeddings to mycelium.db `concept_embeddings` so we don't
     re-compute across sessions.
  4. Run cross-lingual nearest-neighbour search (brute-force matmul on
     CPU — fine up to ~50k concepts; swap for ANN at higher scale).

Activation:
  - MUNINN_EMBEDDINGS=1            : on (off by default to keep cold-start cheap)
  - MUNINN_EMBEDDINGS_MODEL=...    : default sentence-transformers/LaBSE
  - MUNINN_EMBEDDINGS_THRESHOLD=.. : cosine threshold for fusion (default 0.85)

Without the env var (or without sentence-transformers installed), every
method is a no-op and `is_available()` returns False — Mycelium falls
back to the K.1 dict-only path.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import OrderedDict
from typing import Iterable

DEFAULT_MODEL = "sentence-transformers/LaBSE"
DEFAULT_THRESHOLD = 0.85
DEFAULT_LRU_CAPACITY = 4096

__all__ = ["EmbeddingProvider", "DEFAULT_MODEL", "DEFAULT_THRESHOLD", "DEFAULT_LRU_CAPACITY"]

_PROVIDER_LOCK = threading.Lock()


class EmbeddingProvider:
    """Lazy singleton wrapping a sentence-transformers model.

    Thread-safe via per-instance lock + module-level singleton lock.
    Returns float32 numpy arrays. Embeddings are L2-normalized at load
    time so `cosine(a, b) == np.dot(a, b)` (cheaper than full cosine).
    """

    _instance: "EmbeddingProvider | None" = None

    def __init__(self):
        self._lock = threading.Lock()
        self._model = None
        self._model_name = os.environ.get("MUNINN_EMBEDDINGS_MODEL", DEFAULT_MODEL)
        self._threshold = self._read_threshold()
        self._lru: OrderedDict[str, "np.ndarray"] = OrderedDict()  # type: ignore[name-defined]  # noqa: F821
        self._lru_capacity = DEFAULT_LRU_CAPACITY
        self._init_error: str | None = None
        self._np = None  # numpy module, loaded lazily with the model
        self._dim: int | None = None

    @classmethod
    def get(cls) -> "EmbeddingProvider":
        with _PROVIDER_LOCK:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    @staticmethod
    def is_enabled() -> bool:
        """Return True iff the user opted into embedding-based fusion.

        Default is OFF — K.2 only activates when MUNINN_EMBEDDINGS=1.
        Keeps cold-start free for users who don't need cross-lingual
        fusion.
        """
        return os.environ.get("MUNINN_EMBEDDINGS") == "1"

    def is_available(self) -> bool:
        """True if the model loaded successfully and embed() will work."""
        if not self.is_enabled():
            return False
        self._ensure_loaded()
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int | None:
        return self._dim

    @property
    def threshold(self) -> float:
        return self._threshold

    def _read_threshold(self) -> float:
        raw = os.environ.get("MUNINN_EMBEDDINGS_THRESHOLD")
        if not raw:
            return DEFAULT_THRESHOLD
        try:
            val = float(raw)
        except ValueError:
            return DEFAULT_THRESHOLD
        return max(0.0, min(1.0, val))

    def _ensure_loaded(self) -> None:
        if self._model is not None or self._init_error:
            return
        with self._lock:
            if self._model is not None or self._init_error:
                return
            try:
                import numpy as np  # noqa: F401 — needed for downstream ops
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                self._init_error = f"sentence-transformers not installed: {exc}"
                return
            try:
                t0 = time.time()
                self._model = SentenceTransformer(self._model_name)
                # Resolve dim across new and old sentence-transformers APIs
                if hasattr(self._model, "get_embedding_dimension"):
                    self._dim = int(self._model.get_embedding_dimension())
                else:
                    self._dim = int(self._model.get_sentence_embedding_dimension())
                self._np = np
                if os.environ.get("MUNINN_DEBUG"):
                    print(
                        f"K.2: loaded {self._model_name} (dim={self._dim}) "
                        f"in {time.time() - t0:.1f}s",
                        file=sys.stderr,
                    )
            except Exception as exc:  # noqa: BLE001 — broad: missing weights, OOM, etc.
                self._init_error = f"K.2 model load failed: {exc}"
                self._model = None

    def embed(self, text: str):
        """Return a normalized float32 embedding, or None if unavailable.

        Caches the latest LRU_CAPACITY lookups in-memory. The caller is
        responsible for persisting the embedding to `concept_embeddings`
        if they want it to survive a restart.
        """
        if not text:
            return None
        if not self.is_available():
            return None
        key = text.lower().strip()
        with self._lock:
            cached = self._lru.get(key)
            if cached is not None:
                # Move to end (LRU touch)
                self._lru.move_to_end(key)
                return cached
        vec = self._model.encode(key, normalize_embeddings=True)
        if vec is None:
            return None
        vec = self._np.asarray(vec, dtype=self._np.float32)
        with self._lock:
            self._lru[key] = vec
            if len(self._lru) > self._lru_capacity:
                self._lru.popitem(last=False)
        return vec

    def embed_batch(self, texts: Iterable[str]):
        """Encode a list of texts in one model call (much faster than N embed())."""
        if not self.is_available():
            return None
        texts_list = [t.lower().strip() for t in texts if t]
        if not texts_list:
            return None
        vecs = self._model.encode(texts_list, normalize_embeddings=True)
        return self._np.asarray(vecs, dtype=self._np.float32)

    def cosine(self, a, b) -> float:
        """Cosine similarity of two normalized vectors == dot product."""
        return float(self._np.dot(a, b))

    def find_best_match(self, query_vec, candidate_matrix, candidate_names):
        """Vectorized nearest-neighbour over an (N, dim) matrix.

        Returns (best_name, best_score) or (None, -1.0) if matrix is empty.
        Assumes query_vec and rows of candidate_matrix are L2-normalized
        (the default in embed()), so cosine == dot.
        """
        if candidate_matrix is None or len(candidate_names) == 0:
            return None, -1.0
        scores = candidate_matrix @ query_vec  # (N,)
        best_idx = int(self._np.argmax(scores))
        return candidate_names[best_idx], float(scores[best_idx])

    def health_report(self) -> dict:
        """Diagnostic snapshot for `muninn-mem doctor` and tests."""
        return {
            "enabled": self.is_enabled(),
            "available": self.is_available(),
            "model": self._model_name,
            "dim": self._dim,
            "threshold": self._threshold,
            "lru_size": len(self._lru),
            "init_error": self._init_error,
        }
