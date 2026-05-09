"""Compatibility shim — source of truth: engine/core/cube_providers.py.

Part of BUG-091 resync (B1 fix 2026-05-09): the file was a byte-identical
copy (2124L, md5 confirmed) of engine/core/cube_providers.py. Replacing
it with a 30-line shim removes drift risk on the Carmack-top-1 hotspot
(38 bugfixes in 4 weeks per the post-H6 forge audit).

Consumers all use bare `from cube_providers import …` (cube.py, cube_live.py
etc.) and resolve via sys.path, so this is transparent.

See docs/BATTLE_PLAN_FINAL_PROD_v4_2026-05-09.md B1 for the audit plan.
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
