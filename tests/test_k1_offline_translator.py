"""K.1 — Offline FR→EN lexicon for ConceptTranslator.

Goal: make Muninn multilingual concept normalization work WITHOUT requiring
an ANTHROPIC_API_KEY. A static dict at `engine/core/data/lexicons/fr_en.json`
(~946 curated dev-vocab entries, MIT-clean) is loaded into the cache at
boot. API fallback becomes opt-in via `MUNINN_TRANSLATE_FALLBACK_API=1`.

Phase K Battle plan: docs/BATTLE_PLAN_PHASE_K_MULTILINGUAL_OFFLINE.md
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LEX_PATH = REPO_ROOT / "engine" / "core" / "data" / "lexicons" / "fr_en.json"


@pytest.fixture
def ct(monkeypatch):
    """Fresh ConceptTranslator, isolated cache DB (tmp), API fallback OFF."""
    import importlib
    # Make sure API fallback is OFF in default tests
    monkeypatch.delenv("MUNINN_TRANSLATE_FALLBACK_API", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Reset singleton so each test gets a fresh instance
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    if "mycelium_db" in sys.modules:
        importlib.reload(sys.modules["mycelium_db"])
    from mycelium_db import ConceptTranslator
    ConceptTranslator._instance = None
    inst = ConceptTranslator.get()
    yield inst
    ConceptTranslator._instance = None


def test_k1_lexicon_json_exists_in_repo() -> None:
    """The static lexicon must be shipped at the expected path."""
    assert LEX_PATH.exists(), f"K.1 lexicon missing at {LEX_PATH}"
    data = json.loads(LEX_PATH.read_text(encoding="utf-8"))
    # Count non-meta entries
    entries = {k: v for k, v in data.items() if not k.startswith("_")}
    # K.1.bis (2026-05-13) extended via Wikidata SPARQL pull (CC0).
    # Baseline curated 946 + Wikidata ~389 = ~1335 entries minimum.
    assert len(entries) >= 1000, (
        f"K.1+K.1.bis lexicon should ship ≥1000 entries, got {len(entries)}"
    )


def test_k1_static_dict_loaded_at_boot(ct) -> None:
    """ConceptTranslator should load the static lexicon at __init__ time."""
    assert ct._static_dict_size >= 1000, (
        f"K.1+K.1.bis static dict should load ≥1000 entries into cache. "
        f"Got: {ct._static_dict_size}"
    )


def test_k1bis_wikidata_subset_present(ct) -> None:
    """K.1.bis Wikidata pull added scientific/academic vocab (CC0)."""
    # These are pulled from Wikidata seed categories (science, academic discipline)
    # and should NOT have been in the curated MIT dict.
    probes = {
        "astronomie": "astronomy",
        "mathématiques": "mathematics",
        "biologie": "biology",
        "physique": "physics",
    }
    out = ct.normalize_concepts(list(probes.keys()))
    matches = sum(1 for got, exp in zip(out, probes.values()) if got == exp)
    assert matches >= 3, (
        f"K.1.bis Wikidata should cover ≥3 of {list(probes.keys())}. "
        f"Got: {dict(zip(probes.keys(), out))}"
    )


def test_k1_static_dict_actually_serves_translation(monkeypatch, tmp_path) -> None:
    """GAP test (Agent 3 audit 2026-05-13) : prove the static dict is the
    actual source of translation, not stale SQLite cache.

    Without _load_static_lexicon + with an empty cache → 'arbre' must
    passthrough as 'arbre' (no translation). Then the OPPOSITE check :
    with static dict loaded → 'arbre' → 'tree'.

    Pre-K.1.bis the K.1 tests could pass even if _load_static_lexicon
    was disabled, because ~/.muninn/translations.db might still hold
    'arbre→tree' from a previous API call.
    """
    import importlib
    import sys
    monkeypatch.delenv("MUNINN_TRANSLATE_FALLBACK_API", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))
    if "mycelium_db" in sys.modules:
        importlib.reload(sys.modules["mycelium_db"])
    from mycelium_db import ConceptTranslator
    ConceptTranslator._instance = None

    # Force the cache DB into a tmp_path so we don't read the user's real
    # ~/.muninn/translations.db (which may contain stale "arbre→tree" entries).
    monkeypatch.setattr(
        "pathlib.Path.home", lambda: tmp_path,
    )

    # Phase 1 : NEUTRALIZE _load_static_lexicon BEFORE instantiation
    monkeypatch.setattr(
        ConceptTranslator, "_load_static_lexicon",
        lambda self: None,
    )
    ct_no_dict = ConceptTranslator()  # bypass singleton
    out_no_dict = ct_no_dict.normalize_concepts(["arbre"])
    assert out_no_dict == ["arbre"], (
        f"Without static dict + clean cache + no API, 'arbre' should "
        f"passthrough as 'arbre'. Got: {out_no_dict}"
    )

    # Phase 2 : restore _load_static_lexicon, fresh instance, expect 'tree'
    monkeypatch.undo()
    monkeypatch.delenv("MUNINN_TRANSLATE_FALLBACK_API", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        "pathlib.Path.home", lambda: tmp_path,
    )
    ConceptTranslator._instance = None
    importlib.reload(sys.modules["mycelium_db"])
    from mycelium_db import ConceptTranslator as CT2
    ct_with_dict = CT2()
    out_with_dict = ct_with_dict.normalize_concepts(["arbre"])
    assert out_with_dict == ["tree"], (
        f"With static dict loaded, 'arbre' must translate to 'tree'. "
        f"Got: {out_with_dict}"
    )


def test_k1_arbre_translates_to_tree(ct) -> None:
    """The flagship case: 'arbre' must resolve to 'tree' without API."""
    out = ct.normalize_concepts(["arbre"])
    assert out == ["tree"], f"Expected ['tree'], got {out}"


def test_k1_common_dev_vocab_translates(ct) -> None:
    """A handful of dev-vocab probes must round-trip via static dict."""
    probes = {
        "fichier": "file",
        "fonction": "function",
        "mémoire": "memory",
        "compression": "compression",
        "branche": "branch",
        "commit": "commit",
        "erreur": "error",
        "vérifier": "verify",
    }
    out = ct.normalize_concepts(list(probes.keys()))
    assert out == list(probes.values()), (
        f"Static dict round-trip failed. Expected {list(probes.values())}, got {out}"
    )


def test_k1_unknown_word_passthrough(ct) -> None:
    """A word absent from the dict should passthrough (not crash, not call API)."""
    # 'sphincter' is intentionally NOT in the dev-vocab dict
    out = ct.normalize_concepts(["sphincter"])
    assert out == ["sphincter"], (
        f"Unknown word should passthrough as-is. Got: {out}"
    )


def test_k1_no_api_call_required_in_default_mode(ct, monkeypatch) -> None:
    """With MUNINN_TRANSLATE_FALLBACK_API unset, _api_translate must return None."""
    monkeypatch.delenv("MUNINN_TRANSLATE_FALLBACK_API", raising=False)
    result = ct._api_translate(["mot_inconnu_xyz"])
    assert result is None, (
        f"K.1 default mode must not call API. Got: {result}"
    )


def test_k1_api_fallback_opt_in_when_env_set(ct, monkeypatch) -> None:
    """With MUNINN_TRANSLATE_FALLBACK_API=1 + no anthropic lib, returns None gracefully."""
    monkeypatch.setenv("MUNINN_TRANSLATE_FALLBACK_API", "1")
    # No ANTHROPIC_API_KEY set, anthropic lib may or may not raise — must not crash
    try:
        result = ct._api_translate([])  # empty list = early return None
        # Empty list always returns None even with API enabled
        assert result is None
    except Exception as e:
        pytest.fail(f"K.1 API opt-in path should never crash. Got: {e}")


def test_k1_pyproject_includes_lexicon_data() -> None:
    """The lexicon JSON must be declared in pyproject.toml package-data."""
    import tomllib
    pp = REPO_ROOT / "pyproject.toml"
    cfg = tomllib.loads(pp.read_text(encoding="utf-8"))
    pkg_data = cfg.get("tool", {}).get("setuptools", {}).get("package-data", {})
    found = any(
        "data" in k or "lexicons" in k or "*.json" in str(v)
        for k, v in pkg_data.items()
    )
    assert found, (
        f"pyproject.toml [tool.setuptools.package-data] must include the "
        f"lexicon JSON so it ships in the wheel. Current: {pkg_data}"
    )
