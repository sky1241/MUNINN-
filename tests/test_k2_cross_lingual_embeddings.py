"""K.2 (2026-05-14) tests — cross-lingual sentence-embedding fusion.

The heavy tests (model load, real cosine) are auto-skipped when
sentence-transformers isn't installed OR when MUNINN_EMBEDDINGS != "1".
Sky's CI keeps these off by default so we don't pull 500 MB of weights
on every CI run; opt-in locally with:

    MUNINN_EMBEDDINGS=1 pytest tests/test_k2_cross_lingual_embeddings.py -v
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


SKIP_NO_OPT_IN = pytest.mark.skipif(
    os.environ.get("MUNINN_EMBEDDINGS") != "1",
    reason="K.2 disabled — set MUNINN_EMBEDDINGS=1 to run real-model tests",
)


# ─── A. Provider behaviour without opt-in ─────────────────────────────────

def test_provider_disabled_by_default(monkeypatch):
    """Without MUNINN_EMBEDDINGS=1, the provider is_enabled() returns False
    and is_available() short-circuits without touching sentence-transformers."""
    monkeypatch.delenv("MUNINN_EMBEDDINGS", raising=False)
    from engine.core.embeddings import EmbeddingProvider
    # Force a fresh singleton (avoid contamination from other tests)
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    assert p.is_enabled() is False
    assert p.is_available() is False
    # embed() must be a no-op
    assert p.embed("anything") is None


def test_provider_threshold_clamped(monkeypatch):
    monkeypatch.setenv("MUNINN_EMBEDDINGS_THRESHOLD", "2.5")
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    assert p.threshold == 1.0  # clamped
    monkeypatch.setenv("MUNINN_EMBEDDINGS_THRESHOLD", "-0.4")
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    assert p.threshold == 0.0  # clamped


def test_provider_health_report_keys(monkeypatch):
    monkeypatch.delenv("MUNINN_EMBEDDINGS", raising=False)
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    rep = p.health_report()
    for k in ("enabled", "available", "model", "dim", "threshold", "lru_size", "init_error"):
        assert k in rep


# ─── B. Schema migration v4 → v5 ──────────────────────────────────────────

def test_concept_embeddings_table_created_at_boot(tmp_path):
    from engine.core.mycelium_db import MyceliumDB
    db = MyceliumDB(tmp_path / "fresh.db")
    tables = {r[0] for r in db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "concept_embeddings" in tables
    cols = {r[1] for r in db._conn.execute(
        "PRAGMA table_info(concept_embeddings)").fetchall()}
    assert cols == {"concept_id", "model", "dim", "embedding", "created_at"}
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version >= 5
    db._conn.close()


def test_concept_embeddings_migration_v4_to_v5(tmp_path):
    """A pre-v5 DB without concept_embeddings gets the table on next open."""
    from engine.core.mycelium_db import MyceliumDB
    db_path = tmp_path / "old.db"
    db = MyceliumDB(db_path)
    db._conn.execute("DROP TABLE IF EXISTS concept_embeddings")
    db._conn.execute("PRAGMA user_version = 4")
    db._conn.commit()
    db._conn.close()

    db2 = MyceliumDB(db_path)
    tables = {r[0] for r in db2._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "concept_embeddings" in tables
    assert db2._conn.execute("PRAGMA user_version").fetchone()[0] >= 5
    db2._conn.close()


# ─── C. Persist + retrieve embedding (no real model needed) ───────────────

def test_persist_embedding_and_count(tmp_path):
    """Round-trip an embedding without invoking sentence-transformers."""
    import numpy as np
    from engine.core.mycelium_db import MyceliumDB
    db = MyceliumDB(tmp_path / "p.db")
    cid = db._get_or_create_concept("test_concept")
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    db._persist_embedding(cid, "fake-model", vec)
    n = db.get_embedding_count("fake-model")
    assert n == 1
    # Round-trip the blob
    row = db._conn.execute(
        "SELECT dim, embedding FROM concept_embeddings WHERE concept_id = ? AND model = ?",
        (cid, "fake-model"),
    ).fetchone()
    assert row[0] == 3
    restored = np.frombuffer(row[1], dtype=np.float32)
    assert np.allclose(restored, vec)
    db._conn.close()


def test_persist_embedding_is_idempotent(tmp_path):
    import numpy as np
    from engine.core.mycelium_db import MyceliumDB
    db = MyceliumDB(tmp_path / "p.db")
    cid = db._get_or_create_concept("same")
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)
    db._persist_embedding(cid, "m", v1)
    db._persist_embedding(cid, "m", v2)
    assert db.get_embedding_count("m") == 1  # OR REPLACE keeps a single row
    row = db._conn.execute(
        "SELECT embedding FROM concept_embeddings WHERE concept_id = ? AND model = ?",
        (cid, "m"),
    ).fetchone()
    restored = np.frombuffer(row[0], dtype=np.float32)
    assert np.allclose(restored, v2)  # second write wins
    db._conn.close()


# ─── D. Observe path is a no-op when K.2 disabled ─────────────────────────

def test_observe_unchanged_when_k2_disabled(tmp_path, monkeypatch):
    """Without MUNINN_EMBEDDINGS=1, observe() must behave exactly as pre-K.2.

    Concretely: no embedding row is inserted regardless of how many foreign
    concepts get observed.
    """
    monkeypatch.delenv("MUNINN_EMBEDDINGS", raising=False)
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    from engine.core.mycelium_db import MyceliumDB
    from engine.core.mycelium import Mycelium

    # Force the SQLite backend up-front (Mycelium uses lazy modes — JSON
    # fallback in some paths). Touching it through MyceliumDB ensures the
    # concept_embeddings table exists before we query it.
    db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
    db._conn.close()

    m = Mycelium(tmp_path)
    m.observe(["Baum", "Wurzel"])  # DE — would fuse if K.2 were enabled
    conn = sqlite3.connect(str(tmp_path / ".muninn" / "mycelium.db"))
    n_embed = conn.execute("SELECT COUNT(*) FROM concept_embeddings").fetchone()[0]
    assert n_embed == 0  # K.2 stayed silent


# ─── E. Real-model cross-lingual tests (opt-in only) ──────────────────────

@SKIP_NO_OPT_IN
def test_real_cosine_arbre_tree_high():
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    assert p.is_available(), p.health_report()
    a = p.embed("arbre")
    b = p.embed("tree")
    assert p.cosine(a, b) > 0.85


@SKIP_NO_OPT_IN
def test_real_cosine_distinct_concepts_low():
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    p = EmbeddingProvider.get()
    a = p.embed("compression")
    b = p.embed("arbre")
    assert p.cosine(a, b) < 0.5


@SKIP_NO_OPT_IN
def test_real_fusion_with_pre_existing_embedding(tmp_path, monkeypatch):
    """End-to-end: seed an EN concept + embedding, then observe its FR/JP
    equivalent and verify no separate concept gets created (= fusion)."""
    monkeypatch.setenv("MUNINN_EMBEDDINGS", "1")
    from engine.core.embeddings import EmbeddingProvider
    EmbeddingProvider._instance = None
    from engine.core.mycelium import Mycelium
    from engine.core.mycelium_db import MyceliumDB

    # Force the SQLite backend up-front so m._db is non-None.
    db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
    db._conn.close()
    m = Mycelium(tmp_path)
    m.observe(["seed1", "seed2"])  # triggers _db assignment
    p = EmbeddingProvider.get()

    # Seed 'tree' as the canonical EN concept + its embedding so the
    # cross-lingual fusion has something to match against.
    tree_id = m._db._get_or_create_concept("tree")
    m._db._persist_embedding(tree_id, p.model_name, p.embed("tree"))
    # Reset the in-memory matrix so the next observe re-loads
    m._db._embedding_loaded = False
    m._db._embedding_matrix = None

    # Observe a JP synonym + a second random concept (need ≥2 to record a pair)
    m.observe(["木", "filler"])  # JP: tree

    conn = sqlite3.connect(str(tmp_path / ".muninn" / "mycelium.db"))
    # The Japanese character should NOT have a row of its own — it fused into 'tree'.
    row = conn.execute("SELECT id FROM concepts WHERE name = ?", ("木",)).fetchone()
    assert row is None, "Japanese tree should have fused into 'tree' but got its own concept"
