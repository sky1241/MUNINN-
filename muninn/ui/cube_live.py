"""Muninn UI — Cube reconstruction live worker.

QThread worker that runs the real Muninn reconstruction pipeline
(`engine.core.cube_providers.reconstruct_adaptive`) on a source file,
then feeds the heatmap and the terminal with progress events.

Unlike the first MVP (which used a naïve "reconstruct between BEFORE/AFTER"
prompt), this worker uses:
- `engine.core.cube.subdivide_file` for token-accurate cube boundaries,
- `engine.core.cube_providers.reconstruct_adaptive` for the real
  x1->x2->x3 cycles with mycelium + learned anchors + FIM.

Signals:
- cubes_ready(list): list of {idx, start, end, original, sha} dicts.
- status(str, str): (message, hex_color) text lines for the terminal.
- token(str): reserved for future streaming (not emitted by adaptive).
- cube_done(int, float, bool): (idx, ncd, sha_match).
- finished(): all cycles done.
- error(str): fatal error.
"""

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


def _ensure_engine_path():
    """Put the repo root and engine/core/ on sys.path so the real
    engine package can be imported with its sibling imports intact.
    Matches the pattern in tests/run_sanity_btree.py.
    """
    # muninn/ui/cube_live.py  ->  repo_root = parents[2]
    repo_root = Path(__file__).resolve().parents[2]
    engine_core = repo_root / "engine" / "core"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if engine_core.exists() and str(engine_core) not in sys.path:
        sys.path.insert(0, str(engine_core))
    return repo_root, engine_core


class ReconstructionWorker(QObject):
    """Runs engine.core.cube_providers.reconstruct_adaptive in a QThread."""

    cubes_ready = pyqtSignal(list)
    status = pyqtSignal(str, str)
    token = pyqtSignal(str)               # reserved (reconstruct_adaptive uses generate, not stream)
    cube_done = pyqtSignal(int, float, bool)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    # UX-facing colour palette (hex for _append_text)
    _COL_INFO = "#00CFFF"
    _COL_SHA = "#32CD32"
    _COL_PARTIAL = "#F59E0B"
    _COL_FAIL = "#EF4444"
    _COL_DIM = "rgba(255,255,255,0.60)"    # not parsed by QColor, only used by _append_text strings

    def __init__(self, file_path: str, model: str = "qwen2.5-coder:7b",
                 lines_per_cube: int = 20,      # kept for signature compat, unused (engine uses tokens)
                 max_cubes: int = 40,           # cap cubes to keep UI readable
                 base_tokens: int = 112,
                 max_cycles: int = 3,
                 attempts_per_cube: int = 3):
        super().__init__()
        self._file = Path(file_path)
        self._model = model
        self._max_cubes = max_cubes
        self._base_tokens = base_tokens
        self._max_cycles = max_cycles
        self._attempts = attempts_per_cube
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if not self._file.exists():
                self.error.emit(f"File not found: {self._file}")
                return

            _ensure_engine_path()

            # Lazy import so that importing cube_live.py at UI boot does
            # not drag engine/core into the UI process.
            try:
                from engine.core.cube import subdivide_file
                from engine.core.cube_providers import (
                    reconstruct_adaptive, OllamaProvider,
                )
            except ImportError as e:
                self.error.emit(f"Cannot import engine: {e}")
                return

            content = self._file.read_text(encoding="utf-8", errors="replace")
            cubes = subdivide_file(
                str(self._file), content,
                target_tokens=self._base_tokens, level=0,
            )
            if not cubes:
                self.error.emit("subdivide_file returned 0 cubes")
                return

            total = len(cubes)
            if self._max_cubes and total > self._max_cubes:
                self.status.emit(
                    f"[reco] file has {total} cubes, capping to first {self._max_cubes} for the heatmap",
                    self._COL_INFO,
                )
                cubes = cubes[: self._max_cubes]

            self.status.emit(
                f"[reco] {self._file.name} — {len(cubes)} cubes @ {self._base_tokens} tokens, "
                f"model={self._model}, max_cycles={self._max_cycles}, "
                f"attempts/cube={self._attempts}",
                self._COL_INFO,
            )

            # Expose cube descriptors to the heatmap. UX only needs idx, lines, sha.
            cubes_payload = [
                {
                    "idx": i,
                    "start": c.line_start,
                    "end": c.line_end,
                    "original": c.content,
                    "sha": c.sha256,
                }
                for i, c in enumerate(cubes)
            ]
            self.cubes_ready.emit(cubes_payload)

            provider = OllamaProvider(model=self._model)

            # Callback fired by reconstruct_adaptive for each cube event.
            # See tests/run_sanity_btree.py for the status vocabulary.
            def on_cube(cycle, level, cube_idx, status, attempts, ncd):
                if self._stop:
                    return
                if cube_idx is None or cube_idx < 0 or cube_idx >= len(cubes):
                    # Cycle-level events (CYCLE_END etc.) — report as text only.
                    if status == "CYCLE_END":
                        self.status.emit(
                            f"\n[cycle {cycle}] end — {int(ncd)} new SHA this cycle",
                            self._COL_INFO,
                        )
                    return
                if status == "SHA":
                    tag = "AUTO-SHA" if attempts == 0 else f"SHA (attempt {attempts})"
                    self.status.emit(
                        f"  c{cycle} x{level} cube {cube_idx:>2}: {tag}",
                        self._COL_SHA,
                    )
                    self.cube_done.emit(cube_idx, 0.0, True)
                else:
                    col = self._COL_PARTIAL if ncd < 0.3 else self._COL_FAIL
                    self.status.emit(
                        f"  c{cycle} x{level} cube {cube_idx:>2}: NCD={ncd:.3f} ({attempts}a)",
                        col,
                    )
                    self.cube_done.emit(cube_idx, float(ncd), False)

            # Cap cubes to what we showed the user (the engine will still
            # receive the full file, but it keeps the event/result stream
            # aligned with the heatmap indices).
            try:
                reconstruct_adaptive(
                    str(self._file), content, provider,
                    base_tokens=self._base_tokens,
                    max_cycles=self._max_cycles,
                    attempts_per_cube=self._attempts,
                    mycelium=None,
                    on_cube=on_cube,
                )
            except ConnectionError as e:
                self.error.emit(f"Ollama connection error: {e}")
                return
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"reconstruct_adaptive crash: {type(e).__name__}: {e}")
                return

            if self._stop:
                self.status.emit("[reco] stopped by user.", self._COL_PARTIAL)
            else:
                self.status.emit("[reco] all cycles done.", self._COL_INFO)
            self.finished.emit()

        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Worker crash: {type(e).__name__}: {e}")
