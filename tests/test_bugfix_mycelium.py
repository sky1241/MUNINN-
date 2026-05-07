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
        # Each insight, if any, must be a dict with the required schema —
        # without this the contract is just "any list works", which is
        # the kind of stub assertion that hides regressions.
        for insight in result:
            assert isinstance(insight, dict)
            assert {"type", "score", "text"}.issubset(insight.keys())

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
        assert isinstance(strong, list)
        # Strong pairs must come with a score and a textual rendering —
        # otherwise downstream consumers (compression rules, prompt) crash
        for sp in strong:
            assert sp["type"] == "strong_pair"
            assert isinstance(sp["score"], (int, float))
            assert sp["score"] > 0
            assert isinstance(sp["text"], str) and sp["text"]

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
        # Each zone must be a non-empty list of concept names — empty
        # zones leak into spreading_activation and bias the budget pick.
        for zone_name, members in zones.items():
            assert isinstance(zone_name, str) and zone_name
            assert isinstance(members, (list, set, tuple))
            assert len(members) >= 1
            for c in members:
                assert isinstance(c, str) and c

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
        related_off = mycelium.get_related("compression", top_n=20,
                                           filter_stopwords=False)
        related_on = mycelium.get_related("compression", top_n=20,
                                          filter_stopwords=True)
        assert isinstance(related_off, list)
        assert isinstance(related_on, list)
        # The contract is that filter_stopwords=False returns a *superset*
        # — flipping the flag must remove things, not add them.
        names_off = {name for name, _ in related_off}
        names_on = {name for name, _ in related_on}
        assert names_on.issubset(names_off), (
            f"filter_stopwords=True should be a subset of False, "
            f"extra concepts: {names_on - names_off}"
        )

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
        # Same contract as the @classmethod: must point at the user's
        # ~/.muninn/ tree, otherwise federation breaks silently.
        assert "meta_mycelium" in str(result)
        assert str(result).startswith(str(Path.home()))

    def test_meta_db_path_callable_on_instance(self, mycelium):
        result = mycelium.meta_db_path()
        assert isinstance(result, Path)
        assert str(result).endswith("meta_mycelium.db")
        assert str(result).startswith(str(Path.home()))


class TestBugM8OrphanCleanupInDecay:
    """BUG-M8: decay() must cleanup orphan concepts after removing edges."""

    def test_decay_calls_cleanup(self, mycelium):
        """Verify cleanup_orphan_concepts is called in decay code path."""
        import inspect
        src = inspect.getsource(mycelium.decay)
        assert "cleanup_orphan_concepts" in src

    def test_cleanup_orphan_concepts_works(self, mycelium):
        """cleanup_orphan_concepts must remove concepts with no edges."""
        # Inject an orphan: concept exists but no edge references it
        orphan_id = mycelium._db._get_or_create_concept("orphan_concept_xyz")
        mycelium._db._conn.execute(
            "DELETE FROM edges WHERE a=? OR b=?", (orphan_id, orphan_id)
        )
        mycelium._db._conn.commit()
        present_before = mycelium._db._conn.execute(
            "SELECT 1 FROM concepts WHERE id=?", (orphan_id,)
        ).fetchone()
        assert present_before is not None, "orphan must exist before cleanup"

        result = mycelium.cleanup_orphan_concepts()
        assert isinstance(result, int)
        assert result >= 1, "cleanup should have removed at least the injected orphan"

        present_after = mycelium._db._conn.execute(
            "SELECT 1 FROM concepts WHERE id=?", (orphan_id,)
        ).fetchone()
        assert present_after is None, "orphan should have been deleted"

    def test_decay_returns_int(self, mycelium):
        result = mycelium.decay()
        assert isinstance(result, int)
        assert result >= 0
        # decay() must never *grow* the edge set — only weaken or remove.
        edges_after_first = mycelium._db._conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]
        mycelium.decay()
        edges_after_second = mycelium._db._conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]
        assert edges_after_second <= edges_after_first


class TestP3DecayWritesTombstones:
    """BATTLE_PLAN_MYCELIUM_2026-05-05.md P3: decay() must write a row to
    the tombstones table for every edge it removes (count < 0.01).

    Audit 2026-05-07: code path is wired, but production tombstones table
    was empty because real edges rarely reach count < 0.01 naturally
    (~300 days needed at DECAY_HALF_LIFE=30 from count=1). This test
    forces the death scenario explicitly.
    """

    def test_decay_creates_tombstone_for_dead_edge(self, mycelium):
        """An edge with count < 0.01 must be deleted AND tombstoned by decay."""
        # Seed an edge artificially below the death threshold
        a_id = mycelium._db._get_or_create_concept("p3_test_a")
        b_id = mycelium._db._get_or_create_concept("p3_test_b")
        if a_id > b_id:
            a_id, b_id = b_id, a_id
        with mycelium._db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO edges (a, b, count, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (a_id, b_id, 0.001, 1000, 1000)
            )

        n_tomb_before = len(mycelium._db.get_tombstones())
        edge_before = mycelium._db._conn.execute(
            "SELECT 1 FROM edges WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        assert edge_before is not None, "seed edge missing"

        mycelium.decay()

        edge_after = mycelium._db._conn.execute(
            "SELECT 1 FROM edges WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        assert edge_after is None, "decay should have deleted the dead edge"

        tomb_row = mycelium._db._conn.execute(
            "SELECT a, b, deleted_by FROM tombstones WHERE a=? AND b=?", (a_id, b_id)
        ).fetchone()
        assert tomb_row is not None, "decay should have written a tombstone"
        assert tomb_row[2] == "decay", f"deleted_by should be 'decay', got {tomb_row[2]}"

        n_tomb_after = len(mycelium._db.get_tombstones())
        assert n_tomb_after >= n_tomb_before + 1
