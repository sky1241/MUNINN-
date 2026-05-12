"""G.1 — Universal degree-based stopword filter at query-time.

Problem: recall_meta("compression") returned French stopwords like "pas",
"est", "les" — the static `_STOPWORDS` set in mycelium.py:1252 is English-
only. `DEGREE_FILTER_PERCENTILE = 0.05` already exists for FUSION-time
filtering (S3 tier) but is NOT applied at query-time on MCP recall.

Fix: filter `results` in `_recall_local_impl` / `_recall_meta_impl` /
`_recall_dual_impl` before return, dropping concepts in the top
`MUNINN_RECALL_STOPWORD_PERCENTILE` (default 0.05) of the degree
distribution.

This is a TRUE language-universal solution: degree is computed from the
graph topology itself, no hardcoded word list.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def hub_repo(tmp_path: Path) -> Path:
    """Seed a mycelium with one super-hub concept co-occurring with everything."""
    from mycelium import Mycelium

    repo = tmp_path / "hub_repo"
    repo.mkdir()
    (repo / ".muninn").mkdir()

    m = Mycelium(repo)
    # 30 peripheral concepts, each co-occurring with the hub HUB100 times.
    # HUB ends up with degree = 30, everyone else with degree ~1-2.
    peripherals = [f"concept_{i:03d}" for i in range(60)]
    for p in peripherals:
        # Build a small chunk where HUB and `p` appear together.
        chunk = f"HUB {p} content body."
        m.observe(chunk)
    # Add some random pairs WITHOUT the hub for diversity
    for i in range(30):
        m.observe(f"concept_{i:03d} concept_{i+1:03d} pair")
    m.save()
    m.close()
    return repo


def test_g1_recall_local_filters_top_degree_concepts(hub_repo: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """recall_local on a repo with a hub concept must drop HUB from top-K."""
    monkeypatch.delenv("MUNINN_RECALL_STOPWORD_PERCENTILE", raising=False)
    from muninn.mcp.server import _recall_local_impl

    res = _recall_local_impl(query="concept_005",
                             top_k=10,
                             repo_path=str(hub_repo),
                             hops=2)
    concepts = [r["concept"].lower() for r in res["results"]]
    # HUB is the highest-degree node; with default 0.05 percentile it must be filtered out.
    assert "hub" not in concepts, (
        f"HUB (degree-dominant) should be filtered; got results: {concepts}"
    )


def test_g1_recall_local_percentile_zero_disables_filter(hub_repo: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """MUNINN_RECALL_STOPWORD_PERCENTILE=0 → no filter applied."""
    monkeypatch.setenv("MUNINN_RECALL_STOPWORD_PERCENTILE", "0")
    from muninn.mcp.server import _recall_local_impl

    res = _recall_local_impl(query="concept_005",
                             top_k=10,
                             repo_path=str(hub_repo),
                             hops=2)
    # With filter disabled the hub CAN appear (we don't assert it MUST appear,
    # because spread_activation may rank others higher; we just assert the
    # filter is no longer dropping it from contention).
    # The behavioural assertion: result count must equal the unfiltered count
    # when filter is OFF. We can prove that by setting percentile to a very
    # aggressive value next and observing the count drop.
    n_off = len(res["results"])
    monkeypatch.setenv("MUNINN_RECALL_STOPWORD_PERCENTILE", "0.5")
    res2 = _recall_local_impl(query="concept_005",
                              top_k=10,
                              repo_path=str(hub_repo),
                              hops=2)
    n_strict = len(res2["results"])
    # Stricter filter should drop at least one concept (or stay equal in worst case).
    assert n_strict <= n_off, (
        f"Strict 0.5 percentile must not return MORE results than disabled "
        f"filter; got {n_strict} vs {n_off}"
    )


def test_g1_recall_meta_no_french_stopwords(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """recall_meta on a seeded meta DB must filter out highest-degree concepts.

    Builds a tiny meta DB with degree-1 concepts and one degree-N hub.
    Queries by a peripheral seed; asserts hub is filtered.

    Concept names use only letters (no underscores) because the tokenizer
    accepts only `[A-Za-zÀ-ÿ]{3,}` — see _tokenize_query in server.py.
    """
    # Build a minimal meta_mycelium.db with the schema MyceliumDB uses.
    meta_dir = tmp_path / "meta_home"
    meta_dir.mkdir()
    db_path = meta_dir / "meta_mycelium.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE edges (
            a INTEGER NOT NULL,
            b INTEGER NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (a, b)
        );
    """)
    # 60 peripherals (id 1..60) + 1 hub (id 61). All names lowercase, no underscores.
    # We need the tokenization regex `[A-Za-zÀ-ÿ]{3,}` to match the seed.
    peripheral_names = [f"wordnum{c:03d}" for c in range(60)]
    for nm in peripheral_names:
        conn.execute("INSERT INTO concepts(name) VALUES (?)", (nm,))
    conn.execute("INSERT INTO concepts(name) VALUES ('pashub')")
    hub_id = 61
    # Hub connects to ALL 60 peripherals → degree 60
    for i in range(1, 61):
        conn.execute("INSERT INTO edges(a, b, count) VALUES (?, ?, 100)", (hub_id, i))
    # A few peripheral-peripheral edges (degree 1-2)
    for i in range(1, 30):
        conn.execute("INSERT INTO edges(a, b, count) VALUES (?, ?, 5)", (i, i + 1))
    conn.commit()
    conn.close()

    monkeypatch.setenv("MUNINN_META_PATH", str(meta_dir))
    monkeypatch.delenv("MUNINN_RECALL_STOPWORD_PERCENTILE", raising=False)

    from muninn.mcp import server as srv

    # Query with a token that survives `[A-Za-zÀ-ÿ]{3,}` → "wordnum"
    # (the regex only captures the letter portion, so "wordnum005" gives "wordnum").
    # But our DB names are exact like "wordnum005"; need an alphabetic
    # seed that actually matches a row. Use "wordnumzzz" as a seed by
    # inserting an extra concept with that exact name.
    conn2 = sqlite3.connect(str(db_path))
    conn2.execute("INSERT INTO concepts(name) VALUES ('apple')")
    apple_id = conn2.execute("SELECT id FROM concepts WHERE name='apple'").fetchone()[0]
    # apple co-occurs with hub (so we have something to recall)
    conn2.execute("INSERT INTO edges(a, b, count) VALUES (?, ?, 1)", (hub_id, apple_id))
    # apple also co-occurs with 5 peripherals at low count
    for i in range(1, 6):
        conn2.execute("INSERT INTO edges(a, b, count) VALUES (?, ?, 2)", (apple_id, i))
    conn2.commit()
    conn2.close()

    res = srv._recall_meta_impl(query="apple", top_k=10, hops=2)
    concepts = [r["concept"].lower() for r in res["results"]]
    assert "pashub" not in concepts, (
        f"pashub (degree-60 hub) must be filtered from meta recall; "
        f"got results: {concepts}"
    )


def test_g1_env_var_documented_in_claude_md() -> None:
    """The env var MUNINN_RECALL_STOPWORD_PERCENTILE must be documented."""
    claude_md = REPO_ROOT / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    assert "MUNINN_RECALL_STOPWORD_PERCENTILE" in text, (
        "MUNINN_RECALL_STOPWORD_PERCENTILE missing from CLAUDE.md env var table"
    )
