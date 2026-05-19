#!/usr/bin/env python3
"""Property-based tests for cube.py — CURATED post-D6 remediation.

CHUNK D6 (2026-05-19 remediation) — pré-D6 ce fichier contenait 12 tests
auto-générés par forge --gen-props, dont 10 prenaient des objets typés
(Cube, CubeStore, Mycelium, neighbors_list) avec stratégie `st.text()`
→ AttributeError swallowed → test passe sans rien tester.

Post-D6 : on garde UNIQUEMENT les helpers purs (string in/out) avec
vraies post-conditions. Forge --gen-props re-générera les no-op à
chaque run ; cf docs/FORGE_REGEN_HANDBOOK.md pour la procédure.

Tests gardés :
- normalize_content : (str) → str (whitespace/newlines normalisés).
- sha256_hash : (str) → str (hex64).

Tests supprimés :
- find_concept_boundaries (mycelium objet typé)
- subdivide_file (file_path + mycelium)
- subdivide_recursive (idem)
- parse_dependencies (files list/dict)
- extract_ast_hints (Cube objet)
- deduce_imports_from_file (full_content via real file)
- enrich_hints_with_file_context (cubes list + hints dict)
- extract_all_ast_hints (Cube list)
- build_neighbor_graph (cubes list + deps)
- assign_neighbors (CubeStore objet)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings
from engine.core.cube import normalize_content, sha256_hash


@pytest.fixture(autouse=True)
def _forge_isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


@given(text=st.text(max_size=500))
@settings(max_examples=50, deadline=None)
def test_normalize_content_returns_str(text: str):
    """normalize_content always returns a str (no None, no crash)."""
    result = normalize_content(text)
    assert isinstance(result, str)


@given(text=st.text(max_size=500))
@settings(max_examples=50, deadline=None)
def test_normalize_content_idempotent(text: str):
    """Applying normalize twice gives the same result as applying once."""
    once = normalize_content(text)
    twice = normalize_content(once)
    assert once == twice, f"normalize_content not idempotent : {once!r} vs {twice!r}"


@given(text=st.text(max_size=500))
@settings(max_examples=50, deadline=None)
def test_sha256_hash_returns_hex64(text: str):
    """sha256_hash returns a 64-char lowercase hex string (post-normalize)."""
    result = sha256_hash(text)
    assert isinstance(result, str)
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result), (
        f"sha256_hash output not hex64 : {result!r}"
    )


@given(text=st.text(max_size=500))
@settings(max_examples=30, deadline=None)
def test_sha256_hash_deterministic(text: str):
    """sha256_hash is deterministic : same input → same output."""
    h1 = sha256_hash(text)
    h2 = sha256_hash(text)
    assert h1 == h2
