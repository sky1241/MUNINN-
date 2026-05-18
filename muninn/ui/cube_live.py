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
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

# --- PIPELINE_TRACE block (removable, see docs/PIPELINE_TRACE_REMOVAL.md) ---  # PIPELINE_TRACE
try:  # PIPELINE_TRACE
    _muninn_root = Path(__file__).resolve().parent.parent.parent  # PIPELINE_TRACE
    _pt_core = str(_muninn_root / "engine" / "core")  # PIPELINE_TRACE
    if _pt_core not in sys.path: sys.path.insert(0, _pt_core)  # PIPELINE_TRACE
    from pipeline_trace import log_event  # PIPELINE_TRACE
except Exception:  # PIPELINE_TRACE
    def log_event(*a, **kw): pass  # PIPELINE_TRACE
# --- end PIPELINE_TRACE block ---  # PIPELINE_TRACE


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
                 max_cubes: int = 0,            # 0 = no cap, process whole file
                 base_tokens: int = 112,
                 max_cycles: int = 3,
                 attempts_per_cube: int = 11):
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
                    reconstruct_adaptive, OllamaProvider, MockLLMProvider,
                )
                from engine.core.mycelium import Mycelium
            except ImportError as e:
                self.error.emit(f"Cannot import engine: {e}")
                return

            # CHUNK 2 fix: Mycelium expects a repo_path (folder), not a DB file.
            # Internally it builds <repo>/.muninn/mycelium.db. Passing a DB path
            # here would create <path>/.muninn/mycelium.db which is empty.
            # Using repo_root binds the UX to the real .muninn/mycelium.db
            # of the project (847 MB / 5.9M edges accumulated across sessions).
            repo_root = Path(__file__).resolve().parents[2]
            mycelium = Mycelium(repo_root)

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
                # CHUNK 7: also truncate `content` so the engine doesn't waste
                # GPU on cubes the UX won't show. Without this, reconstruct_adaptive
                # processes ALL cubes from the original content even if UX caps
                # to N — engine ate 51 useless LLM calls when UX was capping at 10.
                last_line = cubes[-1].line_end
                content = "\n".join(content.split("\n")[:last_line])

            self.status.emit(
                f"[reco] {self._file.name} — {len(cubes)} cubes @ {self._base_tokens} tokens, "
                f"model={self._model}, max_cycles={self._max_cycles}, "
                f"attempts/cube={self._attempts}",
                self._COL_INFO,
            )

            # H2 (2026-05-09): show the forge fused risk score for this file
            # so the user knows a-priori how risky the reconstruction is.
            # Falls back silently if forge-shield is not installed.
            try:
                from forge_metrics import forge_score_for_path
            except ImportError:
                try:
                    from engine.core.forge_metrics import forge_score_for_path
                except ImportError:
                    forge_score_for_path = None
            if forge_score_for_path is not None:
                try:
                    rel = str(self._file.resolve().relative_to(repo_root.resolve()))
                except (ValueError, OSError):
                    rel = str(self._file)
                score = forge_score_for_path(repo_root, rel)
                if score is not None:
                    bucket = ("HIGH" if score >= 0.70 else
                              "MOD"  if score >= 0.40 else
                              "LOW"  if score >= 0.20 else
                              "STABLE")
                    color = (self._COL_FAIL if score >= 0.40 else
                             self._COL_PARTIAL if score >= 0.20 else
                             self._COL_SHA)
                    self.status.emit(
                        f"[forge] risk={score:.3f} ({bucket}) for {rel}",
                        color,
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

            # POST-AUDIT FIX 2026-05-09: probe Ollama before instantiating.
            # Pre-fix: OllamaProvider(model=...) was hardcoded; if Ollama was
            # not running, the worker crashed in ConnectionError when the first
            # generate() call ran, leaving the heatmap stuck mid-cycle.
            # Now: ping /api/tags first; on any failure (down, model missing,
            # timeout) fall back to MockLLMProvider so the user gets feedback
            # instead of a stack trace. CubeConfig.get_provider() in
            # cube_analysis.py uses the same probe pattern.
            try:
                import urllib.request as _ur, json as _json
                _resp = _ur.urlopen("http://localhost:11434/api/tags", timeout=2)
                _tags = _json.loads(_resp.read())
                _models = [m.get("name", "").split(":")[0]
                           for m in _tags.get("models", [])]
                _target = self._model.split(":")[0]
                if _target not in _models:
                    raise RuntimeError(
                        f"Ollama running but model {self._model!r} not loaded "
                        f"(available: {_models[:5]}...)"
                    )
                provider = OllamaProvider(model=self._model)
                self.status.emit(
                    f"[provider] Ollama OK with {self._model}",
                    self._COL_SHA,
                )
            except Exception as _ollama_err:
                self.status.emit(
                    f"[provider] Ollama unavailable ({type(_ollama_err).__name__}: "
                    f"{_ollama_err}), falling back to MockLLMProvider — "
                    f"reconstruction will return placeholders only",
                    self._COL_PARTIAL,
                )
                provider = MockLLMProvider()

            # CHUNK 12 v2: stream the LLM's full output to the terminal so the
            # user can SEE every line qwen produces while reconstructing each
            # cube. No truncation, no flattened newlines. Each LLM call dumps
            # its full text between two separator lines so the user can read
            # the actual code being attempted.
            _COL_LLM = "#7AA0FF"  # subtle blue for raw LLM lines
            _SEP = "      " + "─" * 60
            _orig_fim = provider.fim_generate
            _orig_gen = provider.generate

            def _emit_llm(tag: str, output: str):
                # Indent each line so the user knows it's LLM output and not
                # pipeline metadata.
                lines = output.rstrip().split("\n")
                indented = "\n".join(f"      │ {ln}" for ln in lines)
                self.status.emit(
                    f"{_SEP}\n      ▼ {tag} attempt\n{indented}\n{_SEP}",
                    _COL_LLM,
                )

            def _wrap_fim(prefix, suffix, max_tokens=256):
                out = _orig_fim(prefix, suffix, max_tokens)
                _emit_llm("FIM", out)
                return out

            def _wrap_gen(prompt, max_tokens=256, temperature=0.0):
                out = _orig_gen(prompt, max_tokens, temperature)
                _emit_llm("LLM", out)
                return out

            provider.fim_generate = _wrap_fim
            provider.generate = _wrap_gen

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
                _pt_t0 = time.perf_counter()  # PIPELINE_TRACE
                log_event("pipeline.ui.cube_live.reconstruct_start", {"file": str(self._file), "base_tokens": self._base_tokens, "max_cycles": self._max_cycles, "attempts": self._attempts, "provider": str(provider)[:60]})  # PIPELINE_TRACE
                reconstruct_adaptive(
                    str(self._file), content, provider,
                    base_tokens=self._base_tokens,
                    max_cycles=self._max_cycles,
                    attempts_per_cube=self._attempts,
                    mycelium=mycelium,
                    on_cube=on_cube,
                )
                log_event("pipeline.ui.cube_live.reconstruct_end", {"file": str(self._file), "elapsed_ms": round((time.perf_counter() - _pt_t0) * 1000, 2)})  # PIPELINE_TRACE
            except ConnectionError as e:
                self.error.emit(f"Ollama connection error: {e}")
                return
            except Exception as e:  # noqa: BLE001
                self.error.emit(f"reconstruct_adaptive crash: {type(e).__name__}: {e}")
                return
            finally:
                try:
                    mycelium.close()
                except Exception:
                    pass

            if self._stop:
                self.status.emit("[reco] stopped by user.", self._COL_PARTIAL)
            else:
                self.status.emit("[reco] all cycles done.", self._COL_INFO)
            self.finished.emit()

        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Worker crash: {type(e).__name__}: {e}")
