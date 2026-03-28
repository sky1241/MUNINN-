"""TIER 3 S4: Auto-translation tokenizer detection tests."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_s4_1_english_detection():
    """English words detected as 1 token."""
    from muninn.mycelium_db import ConceptTranslator
    t = ConceptTranslator()
    english_words = ["compression", "tree", "algorithm", "sqlite", "memory",
                     "database", "branch", "token", "network", "graph"]
    for w in english_words:
        assert t.is_english(w), f"{w} should be English"


def test_s4_2_foreign_detection():
    """Non-English words detected as 2+ tokens."""
    from muninn.mycelium_db import ConceptTranslator
    t = ConceptTranslator()
    foreign_words = ["pouvait", "surtout", "dessus", "paradigme"]
    for w in foreign_words:
        assert not t.is_english(w), f"{w} should be non-English"


def test_s4_3_normalize_passthrough():
    """English concepts pass through unchanged."""
    from muninn.mycelium_db import ConceptTranslator
    t = ConceptTranslator()
    concepts = ["compression", "tree", "memory"]
    result = t.normalize_concepts(concepts)
    assert result == concepts


def test_s4_4_pending_queue():
    """Non-English concepts are queued for batch translation."""
    from muninn.mycelium_db import ConceptTranslator
    t = ConceptTranslator()
    t._pending = []  # Reset
    concepts = ["compression", "pouvait", "surtout"]
    t.normalize_concepts(concepts)
    assert "pouvait" in t._pending or "pouvait" in t._cache
    assert "surtout" in t._pending or "surtout" in t._cache


def test_s4_5_cache_hit():
    """Cached translations are returned immediately."""
    from muninn.mycelium_db import ConceptTranslator
    t = ConceptTranslator()
    t._cache["pouvait"] = "could"
    t._cache["surtout"] = "especially"
    concepts = ["compression", "pouvait", "surtout"]
    result = t.normalize_concepts(concepts)
    assert result == ["compression", "could", "especially"]
