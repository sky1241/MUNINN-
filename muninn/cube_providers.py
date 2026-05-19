"""Shim of engine/core/cube_providers.py (BUG-091 B1, 2026-05-09).
2124L byte-identical copy → 30L shim. Carmack-top-1 hotspot (38 bugfixes
in 4 weeks per H6 forge audit) — eliminating drift here is critical.
Consumers use bare `from cube_providers import …` resolved via sys.path.

CHUNK D2 (2026-05-19 remediation) — pre-import `cube` (and transitively
`cube_analysis`) BEFORE doing `from cube_providers import *`. Otherwise
the circular chain (cube_providers → cube → cube_analysis → cube_providers)
raises ImportError on cold start because at line cube_providers:20 the
module is only partially initialized. Pre-importing cube forces the full
init of the engine-core module graph in the right order.
"""
import sys
from pathlib import Path

_engine_core = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_engine_core) not in sys.path:
    sys.path.insert(0, str(_engine_core))

# D2 cold-start fix : force cube to fully initialize before cube_providers.
# `import cube` triggers cube.py which transitively imports cube_analysis
# AND cube_providers ; by the time control returns here, all three modules
# are fully loaded in sys.modules.
import cube as _cube_warmup  # noqa: F401

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
    # CHUNK D4 (2026-05-19 remediation) — surface C10 + D3 helpers for
    # shim consumers (wildcard `import *` skips `_*` per PEP 8).
    _extract_gap_lines,
    _extract_unknown_identifiers,
)
