"""Shim of engine/core/cube_providers.py (BUG-091 B1, 2026-05-09).
2124L byte-identical copy → 30L shim. Carmack-top-1 hotspot (38 bugfixes
in 4 weeks per H6 forge audit) — eliminating drift here is critical.
Consumers use bare `from cube_providers import …` resolved via sys.path.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

from cube_providers import *  # noqa: F401,F403
from cube_providers import (  # explicit re-export of public surface
    LLMProvider,
    OllamaProvider,
    ClaudeProvider,
    OpenAIProvider,
    MockLLMProvider,
    FIMReconstructor,
    ReconstructionResult,
    WaveResult,
    LevelResult,
    reconstruct_cube,
    reconstruct_cube_waves,
    reconstruct_line_by_line,
    reconstruct_adaptive,
    run_progressive_levels,
    validate_reconstruction,
    compute_hotness,
    compute_ncd,
)
