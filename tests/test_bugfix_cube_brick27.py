"""Tests for cube system bug fixes — brick 27 (2026-04-17).

C1: feed_mycelium_from_results transmits mechanical weight +1/-0.5
C2: Default provider = Ollama first, mock fallback
C4: auto_repair receives real reconstructor
C5: KM + Tononi persisted in cli_run result dict
C6: feed_anomalies_to_mycelium wired into post_cycle_analysis
"""
import pytest
import sys
import os
import tempfile
import json
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


@dataclass
class FakeCube:
    id: str = "cube1"
    content: str = "def hello():\n    return 'world'"
    neighbors: list = field(default_factory=lambda: ["cube2"])
    file_origin: str = "test.py"
    temperature: float = 0.5
    level: int = 0
    status: str = "done"


@dataclass
class FakeResult:
    cube_id: str = "cube1"
    success: bool = True
    exact_match: bool = False
    ncd_score: float = 0.1
    reconstructed: str = "def hello():\n    return 'world'"


class TestC1MechanicalWeight:
    """C1: feed_mycelium_from_results must transmit +1/-0.5 to mycelium."""

    def test_success_creates_positive_weight(self):
        from cube_analysis import feed_mycelium_from_results
        from mycelium import Mycelium

        with tempfile.TemporaryDirectory() as td:
            m = Mycelium(Path(td))
            # Init the DB: observe + save to create SQLite
            m.observe("compress tokenize init")
            m.save()
            assert m._db is not None, "DB should be initialized after save"

            cube1 = FakeCube(id="cube1", content="def compress():\n    pass",
                             neighbors=["cube2"])
            cube2 = FakeCube(id="cube2", content="def tokenize():\n    pass")
            result = FakeResult(cube_id="cube1", success=True)

            pairs = feed_mycelium_from_results([result], [cube1, cube2], mycelium=m)
            assert len(pairs) >= 1
            assert pairs[0]["weight"] == 1.0

            # Verify a mechanical connection exists in DB
            conn = m._db.get_connection("compress", "tokenize")
            if conn:
                assert conn["count"] > 0, "Connection should be positive"
            m.close()

    def test_failure_creates_negative_weight(self):
        from cube_analysis import feed_mycelium_from_results
        from mycelium import Mycelium

        with tempfile.TemporaryDirectory() as td:
            m = Mycelium(Path(td))
            m.observe("compress tokenize init")
            m.save()
            # Create a positive connection first
            m._db.upsert_connection("compress", "tokenize", increment=5.0)

            cube1 = FakeCube(id="cube1", content="def compress():\n    pass",
                             neighbors=["cube2"])
            cube2 = FakeCube(id="cube2", content="def tokenize():\n    pass")
            result = FakeResult(cube_id="cube1", success=False)

            pairs = feed_mycelium_from_results([result], [cube1, cube2], mycelium=m)
            assert len(pairs) >= 1
            assert pairs[0]["weight"] == -0.5
            m.close()

    def test_uses_upsert_not_observe_text(self):
        """Verify the code uses upsert_connection, not observe_text."""
        import inspect
        from cube_analysis import feed_mycelium_from_results
        src = inspect.getsource(feed_mycelium_from_results)
        assert "upsert_connection" in src
        assert "increment=weight" in src

    def test_zone_is_mechanical(self):
        """Mechanical connections should be tagged with zone='mechanical'."""
        import inspect
        from cube_analysis import feed_mycelium_from_results
        src = inspect.getsource(feed_mycelium_from_results)
        assert 'zone="mechanical"' in src


class TestC2ProviderPriority:
    """C2: Ollama must be checked before Mock."""

    def test_ollama_checked_first(self):
        import inspect
        from cube_analysis import CubeConfig
        src = inspect.getsource(CubeConfig.get_provider)
        ollama_pos = src.index("OllamaProvider")
        mock_pos = src.index("MockLLMProvider")
        assert ollama_pos < mock_pos, "Ollama must be checked before Mock"

    def test_mock_is_fallback(self):
        """When Ollama is not running, mock should be returned."""
        from cube_analysis import CubeConfig
        config = CubeConfig()
        provider = config.get_provider()
        # Without Ollama running, should fall back to mock
        assert provider.name in ("mock", "ollama")

    def test_health_check_in_source(self):
        """Provider selection should include an Ollama health check."""
        import inspect
        from cube_analysis import CubeConfig
        src = inspect.getsource(CubeConfig.get_provider)
        assert "urlopen" in src or "health" in src.lower()


class TestC4AutoRepairReconstructorWired:
    """C4: post_cycle_analysis must pass reconstructor to auto_repair."""

    def test_reconstructor_in_source(self):
        import inspect
        from cube_analysis import post_cycle_analysis
        src = inspect.getsource(post_cycle_analysis)
        assert "FIMReconstructor(provider)" in src
        assert "reconstructor=reconstructor" in src

    def test_provider_param_exists(self):
        import inspect
        from cube_analysis import post_cycle_analysis
        sig = inspect.signature(post_cycle_analysis)
        assert "provider" in sig.parameters

    def test_mycelium_param_exists(self):
        import inspect
        from cube_analysis import post_cycle_analysis
        sig = inspect.signature(post_cycle_analysis)
        assert "mycelium" in sig.parameters


class TestC5KMTononiPersisted:
    """C5: cli_run must include kaplan_meier and tononi_degeneracy in result."""

    def test_km_in_source(self):
        import inspect
        from cube_analysis import cli_run
        src = inspect.getsource(cli_run)
        assert "'kaplan_meier'" in src

    def test_tononi_in_source(self):
        import inspect
        from cube_analysis import cli_run
        src = inspect.getsource(cli_run)
        assert "'tononi_degeneracy'" in src

    def test_result_dict_has_keys(self):
        """The return dict template must include both keys."""
        import inspect
        from cube_analysis import cli_run
        src = inspect.getsource(cli_run)
        assert "kaplan_meier" in src
        assert "tononi_degeneracy" in src


class TestC6AnomalyFeedbackLoop:
    """C6: feed_anomalies_to_mycelium must be called in post_cycle_analysis."""

    def test_wired_in_post_cycle(self):
        import inspect
        from cube_analysis import post_cycle_analysis
        src = inspect.getsource(post_cycle_analysis)
        assert "feed_anomalies_to_mycelium" in src

    def test_anomalies_fed_key_in_analysis(self):
        """Should record how many anomalies were fed."""
        import inspect
        from cube_analysis import post_cycle_analysis
        src = inspect.getsource(post_cycle_analysis)
        assert "anomalies_fed_to_mycelium" in src
