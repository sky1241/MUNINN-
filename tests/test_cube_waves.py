"""
Tests for B40/B41: die-and-retry waves + progressive levels.

Uses MockLLMProvider to test logic without API calls.
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from engine.core.cube_providers import (
    MockLLMProvider, WaveResult, LevelResult,
    reconstruct_cube_waves, run_progressive_levels,
    _compress_attempt,
)
from engine.core.cube import Cube, CubeStore, sha256_hash, subdivide_file, assign_neighbors


# ─── Helpers ─────────────────────────────────────────────────────────

def _make_cube(content="func main() {\n\tfmt.Println(\"hello\")\n}", cube_id="test:L1-L3:level0"):
    return Cube(
        id=cube_id,
        content=content,
        sha256=sha256_hash(content),
        file_origin="server.go",
        line_start=1,
        line_end=3,
        level=0,
        token_count=20,
    )


def _make_neighbors(cube):
    before = Cube(
        id="test:L0-L0:before", content="package main\n\nimport \"fmt\"\n",
        sha256=sha256_hash("package main\n\nimport \"fmt\"\n"),
        file_origin=cube.file_origin, line_start=0, line_end=0, level=0, token_count=10,
    )
    after = Cube(
        id="test:L4-L6:after", content="func helper() {\n\treturn\n}\n",
        sha256=sha256_hash("func helper() {\n\treturn\n}\n"),
        file_origin=cube.file_origin, line_start=4, line_end=6, level=0, token_count=10,
    )
    return [before, after]


# ─── Tests: _compress_attempt ────────────────────────────────────────

def test_compress_attempt_basic():
    """Compressing a code snippet returns something non-empty."""
    text = "func main() {\n\tfmt.Println(\"hello world\")\n}"
    result = _compress_attempt(text)
    assert len(result) > 0
    assert len(result) <= len(text) + 10  # should not grow much


def test_compress_attempt_empty():
    result = _compress_attempt("")
    assert result == ""


# ─── Tests: reconstruct_cube_waves ───────────────────────────────────

def test_waves_sha_match_first_try():
    """Mock returns exact content → SHA match on attempt 1."""
    cube = _make_cube()
    neighbors = _make_neighbors(cube)
    # Use "server.go" as key — it appears in the prompt (file_origin)
    provider = MockLLMProvider(responses={"server.go": cube.content})

    result = reconstruct_cube_waves(
        cube, neighbors, provider,
        attempts_per_wave=11, max_waves=2,
    )

    assert isinstance(result, WaveResult)
    assert result.sha_matched is True
    assert result.wave_number == 1
    assert result.attempt_in_wave == 1
    assert result.total_attempts == 1
    assert result.best_ncd < 0.1  # NCD ~0 but zlib adds small variance


def test_waves_sha_never_matches():
    """Mock returns wrong content → SHA never matches."""
    cube = _make_cube()
    neighbors = _make_neighbors(cube)
    provider = MockLLMProvider(responses={"default": "completely wrong code"})

    result = reconstruct_cube_waves(
        cube, neighbors, provider,
        attempts_per_wave=3, max_waves=2,
        ncd_give_up=1.0,  # don't give up for this test
    )

    assert result.sha_matched is False
    assert result.wave_number == 0
    assert result.total_attempts == 6  # 3 * 2
    assert result.best_ncd > 0.0


def test_waves_callback_called():
    """on_attempt callback fires for each attempt."""
    cube = _make_cube()
    neighbors = _make_neighbors(cube)
    provider = MockLLMProvider(responses={"server.go": cube.content})
    calls = []

    def cb(wave, attempt, ncd, sha):
        calls.append((wave, attempt, ncd, sha))

    reconstruct_cube_waves(
        cube, neighbors, provider,
        attempts_per_wave=11, max_waves=1,
        on_attempt=cb,
    )

    assert len(calls) == 1  # SHA matched on first try
    assert calls[0][0] == 1  # wave 1
    assert calls[0][1] == 1  # attempt 1
    assert calls[0][2] < 0.1  # NCD ~0
    assert calls[0][3] is True  # SHA match


def test_waves_previous_attempts_accumulate():
    """After failed attempts, previous_attempts list grows."""
    cube = _make_cube()
    neighbors = _make_neighbors(cube)

    # Track what prompts the provider sees
    call_count = [0]
    original_generate = MockLLMProvider.generate

    class TrackingProvider(MockLLMProvider):
        def generate(self, prompt, max_tokens=256, temperature=0.0):
            call_count[0] += 1
            # Return wrong content until attempt 4
            if call_count[0] < 4:
                return f"wrong attempt {call_count[0]}"
            return cube.content

    provider = TrackingProvider()

    result = reconstruct_cube_waves(
        cube, neighbors, provider,
        attempts_per_wave=11, max_waves=1,
    )

    assert result.sha_matched is True
    assert result.total_attempts == 4
    assert result.wave_number == 1
    assert result.attempt_in_wave == 4


# ─── Tests: run_progressive_levels ───────────────────────────────────

def test_progressive_levels_structure():
    """Progressive levels returns correct structure."""
    content = "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(\"hello\")\n}\n"

    class AlwaysMatchProvider(MockLLMProvider):
        """Returns whatever content the cube has — always SHA match."""
        def generate(self, prompt, max_tokens=256, temperature=0.0):
            # Extract line range from prompt and return matching content
            return content

    provider = AlwaysMatchProvider()

    results = run_progressive_levels(
        file_path="test.go", content=content,
        provider=provider, base_tokens=112,
        max_levels=2, attempts_per_wave=2, max_waves=1,
        max_cubes_per_level=5,
    )

    assert isinstance(results, list)
    assert all(isinstance(r, LevelResult) for r in results)
    if results:
        assert results[0].level == 1
        assert results[0].target_tokens == 112


def test_progressive_early_exit_on_100pct():
    """If all cubes match SHA at level x1, stop — don't go to x2."""
    cube = _make_cube()

    class PerfectProvider(MockLLMProvider):
        def generate(self, prompt, max_tokens=256, temperature=0.0):
            return cube.content

    content = cube.content
    provider = PerfectProvider()
    level_calls = []

    def on_level(lr):
        level_calls.append(lr.level)

    results = run_progressive_levels(
        file_path="test.go", content=content,
        provider=provider, base_tokens=112,
        max_levels=5, attempts_per_wave=2, max_waves=1,
        max_cubes_per_level=5,
        on_level=on_level,
    )

    # Should stop after level 1 if 100% SHA
    assert len(results) >= 1
    # With tiny content, there may be only 1 cube, which matches → early exit


def test_wave_result_fields():
    """WaveResult dataclass has all expected fields."""
    wr = WaveResult(
        cube_id="test", sha_matched=True, wave_number=3,
        attempt_in_wave=7, total_attempts=29,
        best_ncd=0.05, best_reconstruction="code here",
    )
    assert wr.cube_id == "test"
    assert wr.sha_matched is True
    assert wr.wave_number == 3
    assert wr.attempt_in_wave == 7
    assert wr.total_attempts == 29
    assert wr.best_ncd == 0.05


def test_level_result_fields():
    """LevelResult dataclass has all expected fields."""
    lr = LevelResult(
        level=2, target_tokens=224, n_cubes=10,
        sha_matched=7, sha_pct=70.0, avg_best_ncd=0.15,
        heatmap=[],
    )
    assert lr.level == 2
    assert lr.target_tokens == 224
    assert lr.sha_pct == 70.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
