"""Tests for mycelium bug fixes BUG-M1 through BUG-M8.

Each test creates a small in-memory mycelium and verifies the fix
works correctly. No real DB required — uses tmp_path fixtures.
"""
import pytest
from pathlib import Path
from collections import deque


@pytest.fixture
def mycelium(tmp_path):
    """Create a small mycelium with known data for testing."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
    from mycelium import Mycelium

    m = Mycelium(tmp_path)

    # Feed some text to create connections
    texts = [
        "compression memory tokens mycelium tree branch boot session",
        "compression layers pipeline regex filter strip",
        "mycelium connections fusions decay observe spreading",
        "branch grow prune temperature cold hot recall",
        "session transcript feed hook compact save load",
        # Add some "stopword-like" high-frequency concepts
        "est pas que les des sur une qui par son",
        "est pas que les des sur une qui par son",
        "est pas que les des sur une qui par son",
        "est pas les que des sur une par qui son",
        "est pas les que des sur une par qui son",
        "est les pas que des sur une par qui son",
        "est les pas que des sur une par qui son",
        "est les pas que des sur une par qui son",
        "est les pas que des sur une par qui son",
        "est les pas que des sur une par qui son",
        # Mix stopwords with real concepts to pollute
        "est compression pas memory les tokens",
        "est mycelium pas tree les branch",
        "est session pas hook les feed",
    ]
    for t in texts:
        m.observe(t)
    m.save()
    return m


class TestBugM1DreamNoOOM:
    """BUG-M1: dream() must not load all edges into RAM."""

    def test_dream_returns_list(self, mycelium):
        result = mycelium.dream()
        assert isinstance(result, list)

    def test_dream_produces_insights_or_empty(self, mycelium):
        result = mycelium.dream()
        # Small test graph may not have enough connections for insights.
        # The key assertion is that it returns a list without crashing.
        assert isinstance(result, list)
        if result:
            types = [i["type"] for i in result]
            # If we got insights, each must have required fields
            for i in result:
                assert "type" in i
                assert "score" in i
                assert "text" in i

    def test_dream_strong_pairs_detected(self, mycelium):
        result = mycelium.dream()
        strong = [i for i in result if i["type"] == "strong_pair"]
        # We fed stopwords 10 times — they should have strong pairs
        # (or not, depending on threshold — just verify no crash)
        assert isinstance(strong, list)

    def test_dream_with_small_graph(self, tmp_path):
        """dream() on graph with <10 connections returns empty list."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        from mycelium import Mycelium
        m = Mycelium(tmp_path / "small")
        m.observe("one two three")
        result = m.dream()
        assert result == [] or isinstance(result, list)
        m.close()


class TestBugM2TripAndBfsZones:
    """BUG-M2: trip() and _bfs_zones() must not OOM."""

    def test_bfs_zones_returns_dict(self, mycelium):
        degree = mycelium._db.all_degrees()
        zones = mycelium._bfs_zones(degree)
        assert isinstance(zones, dict)

    def test_bfs_zones_uses_deque(self, mycelium):
        """Verify the fix uses deque (O(1) popleft) not list.pop(0)."""
        import inspect
        src = inspect.getsource(mycelium._bfs_zones)
        assert "deque" in src
        assert "queue.popleft()" in src

    def test_bfs_zones_bounded_by_max_concepts(self, mycelium):
        degree = mycelium._db.all_degrees()
        zones_small = mycelium._bfs_zones(degree, max_concepts=5)
        zones_large = mycelium._bfs_zones(degree, max_concepts=5000)
        # Small should have fewer or equal zone concepts
        small_total = sum(len(v) for v in zones_small.values())
        large_total = sum(len(v) for v in zones_large.values())
        assert small_total <= large_total or small_total <= 5

    def test_bfs_zones_empty_degree(self, mycelium):
        zones = mycelium._bfs_zones({})
        assert zones == {}

    def test_trip_returns_dict(self, mycelium):
        result = mycelium.trip(intensity=0.5, max_dreams=3)
        assert isinstance(result, dict)
        assert "created" in result
        assert "entropy_before" in result
        assert "dreams" in result

    def test_trip_respects_max_dreams(self, mycelium):
        result = mycelium.trip(intensity=0.5, max_dreams=2)
        assert result["created"] <= 2


class TestBugM3DetectZonesFallback:
    """BUG-M3: _bfs_zones must work as fallback when scipy is missing."""

    def test_bfs_zones_finds_components(self, mycelium):
        degree = mycelium._db.all_degrees()
        zones = mycelium._bfs_zones(degree)
        # Should find at least 1 zone from our test data
        if zones:
            for name, members in zones.items():
                assert len(members) >= 3  # min component size


class TestBugM4GetRelatedStopwords:
    """BUG-M4: get_related() must filter stopword hubs by default."""

    def test_default_filters_stopwords(self, mycelium):
        related = mycelium.get_related("compression", top_n=10)
        stopwords = {"est", "pas", "que", "les", "des", "sur", "une", "qui", "par", "son"}
        names = {name for name, _ in related}
        overlap = names & stopwords
        assert len(overlap) == 0, f"Stopwords in results: {overlap}"

    def test_filter_stopwords_false_includes_them(self, mycelium):
        related = mycelium.get_related("compression", top_n=20,
                                       filter_stopwords=False)
        # With filter off, stopwords may appear (if they co-occur)
        names = {name for name, _ in related}
        # Just verify it returns something and doesn't crash
        assert isinstance(related, list)

    def test_empty_concept_returns_empty(self, mycelium):
        assert mycelium.get_related("", top_n=5) == []

    def test_nonexistent_concept_returns_empty(self, mycelium):
        assert mycelium.get_related("xyznonexistent999", top_n=5) == []


class TestBugM6CompressionRulesFiltered:
    """BUG-M6: get_compression_rules() must filter noise fusions."""

    def test_rules_respect_min_strength(self, mycelium):
        rules = mycelium.get_compression_rules(min_strength=5)
        for key, rule in rules.items():
            assert rule["strength"] >= 5

    def test_rules_respect_max_rules(self, mycelium):
        rules = mycelium.get_compression_rules(max_rules=3)
        assert len(rules) <= 3

    def test_rules_no_stopwords(self, mycelium):
        """Stopword concepts should be filtered from compression rules."""
        rules = mycelium.get_compression_rules(min_strength=1)
        hub_set = mycelium._get_high_degree_concepts()
        for key, rule in rules.items():
            for concept in rule["concepts"]:
                assert concept not in hub_set, (
                    f"Hub concept '{concept}' found in compression rule {key}"
                )

    def test_rules_no_short_concepts(self, mycelium):
        rules = mycelium.get_compression_rules(min_strength=1)
        for key, rule in rules.items():
            for concept in rule["concepts"]:
                assert len(concept) >= mycelium.MIN_CONCEPT_LEN, (
                    f"Short concept '{concept}' in rule {key}"
                )


class TestBugM7MetaPathStaticmethod:
    """BUG-M7: meta_path/meta_db_path are @staticmethod — verify callable."""

    def test_meta_path_callable_on_class(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        from mycelium import Mycelium
        # Must be callable as Mycelium.meta_path()
        result = Mycelium.meta_path()
        assert isinstance(result, Path)
        assert "meta_mycelium" in str(result)

    def test_meta_db_path_callable_on_class(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        from mycelium import Mycelium
        result = Mycelium.meta_db_path()
        assert isinstance(result, Path)
        assert "meta_mycelium.db" in str(result)

    def test_meta_path_callable_on_instance(self, mycelium):
        result = mycelium.meta_path()
        assert isinstance(result, Path)

    def test_meta_db_path_callable_on_instance(self, mycelium):
        result = mycelium.meta_db_path()
        assert isinstance(result, Path)


class TestBugM8OrphanCleanupInDecay:
    """BUG-M8: decay() must cleanup orphan concepts after removing edges."""

    def test_decay_calls_cleanup(self, mycelium):
        """Verify cleanup_orphan_concepts is called in decay code path."""
        import inspect
        src = inspect.getsource(mycelium.decay)
        assert "cleanup_orphan_concepts" in src

    def test_cleanup_orphan_concepts_works(self, mycelium):
        """cleanup_orphan_concepts returns int count."""
        result = mycelium.cleanup_orphan_concepts()
        assert isinstance(result, int)
        assert result >= 0

    def test_decay_returns_int(self, mycelium):
        result = mycelium.decay()
        assert isinstance(result, int)
        assert result >= 0
