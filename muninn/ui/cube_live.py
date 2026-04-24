"""Muninn UI — Cube reconstruction live worker.

Worker thread (QObject) that reconstructs a source file cube-by-cube via
a local LLM, streaming tokens to the terminal and updating the heatmap
in real time.

MVP scope:
- No CubeEngine / no mycelium / no learned anchors — just a straight
  "reconstruct this block" prompt per slice of N lines.
- Uses OllamaProvider.stream() to get tokens live.
- Compares SHA-256 of the reconstructed text vs the original (after
  trimming/normalising trailing whitespace).
- Reports per-cube NCD via zlib (normalised compression distance).

This is the visual demo. A future version can swap the inner loop for
engine.core.cube_providers.reconstruct_adaptive() to get the full Muninn
pipeline (mycelium, learned anchors, FIM, x1/x2/x3 cycles).
"""

import hashlib
import zlib
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


DEFAULT_CUBE_LINES = 20     # ~100-150 tokens per cube, keeps prompts small
DEFAULT_MAX_CUBES = 40      # safety cap for very long files
DEFAULT_MAX_TOKENS = 400    # per cube reconstruction


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _ncd(a: str, b: str) -> float:
    """Normalised Compression Distance (Cilibrasi 2005).

    0.0 = identical, 1.0 = no similarity at all. zlib-based.
    """
    if not a and not b:
        return 0.0
    ca = len(zlib.compress(a.encode("utf-8", errors="replace")))
    cb = len(zlib.compress(b.encode("utf-8", errors="replace")))
    cab = len(zlib.compress((a + b).encode("utf-8", errors="replace")))
    denom = max(ca, cb)
    if denom == 0:
        return 0.0
    return max(0.0, min(1.0, (cab - min(ca, cb)) / denom))


def _normalise(text: str) -> str:
    """Strip trailing whitespace per line and trailing blank lines —
    SHA comparison is otherwise brittle on LLM output."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _slice_file(path: Path, lines_per_cube: int, max_cubes: int) -> list[dict]:
    """Split file content into cubes of N lines.

    Returns a list of dicts: {idx, start, end, original_text, sha, neighbors_prefix, neighbors_suffix}
    """
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total = len(lines)
    cubes = []
    idx = 0
    for start in range(0, total, lines_per_cube):
        if idx >= max_cubes:
            break
        end = min(start + lines_per_cube, total)
        body_lines = lines[start:end]
        body = "\n".join(body_lines)
        # Context: ~5 lines before and after (neighbors)
        prefix = "\n".join(lines[max(0, start - 5):start])
        suffix = "\n".join(lines[end:min(total, end + 5)])
        cubes.append({
            "idx": idx,
            "start": start,
            "end": end,
            "original": body,
            "sha": _sha256(_normalise(body)),
            "prefix": prefix,
            "suffix": suffix,
        })
        idx += 1
    return cubes


def _build_prompt(cube: dict, lang_hint: str) -> str:
    return (
        f"You are reconstructing a missing block of {lang_hint} source code.\n"
        f"Given the surrounding context, output ONLY the block that goes "
        f"between [BEFORE] and [AFTER]. No explanation, no markdown fence, "
        f"no comments added. Keep the exact indentation.\n\n"
        f"[BEFORE]\n{cube['prefix']}\n[END BEFORE]\n\n"
        f"[AFTER]\n{cube['suffix']}\n[END AFTER]\n\n"
        f"The missing block is {cube['end'] - cube['start']} lines. "
        f"Output the block now:"
    )


def _guess_lang(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".go": "Go",
        ".py": "Python",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".rs": "Rust",
        ".c": "C",
        ".cpp": "C++",
        ".java": "Java",
    }.get(ext, "source")


def _clean_llm_output(text: str) -> str:
    """Remove common markdown fence wrapping the LLM may add despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        # strip first fence line
        nl = t.find("\n")
        if nl >= 0:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t


class ReconstructionWorker(QObject):
    """Reconstructs a source file cube-by-cube via Ollama streaming.

    Signals (thread-safe, delivered on the main Qt event loop):
    - cubes_ready(list): sent once after slicing; each dict has idx/start/end/original.
    - status(str, str): informational messages: (text, hex_color).
    - token(str): a single token/chunk from the LLM stream (for the terminal).
    - cube_done(int, float, bool): idx, ncd (0..1), sha_match (True = exact).
    - finished(): all cubes processed.
    - error(str): fatal error, stops the worker.
    """

    cubes_ready = pyqtSignal(list)
    status = pyqtSignal(str, str)
    token = pyqtSignal(str)
    cube_done = pyqtSignal(int, float, bool)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, file_path: str, model: str = "qwen2.5-coder:7b",
                 lines_per_cube: int = DEFAULT_CUBE_LINES,
                 max_cubes: int = DEFAULT_MAX_CUBES):
        super().__init__()
        self._file = Path(file_path)
        self._model = model
        self._lines_per_cube = lines_per_cube
        self._max_cubes = max_cubes
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if not self._file.exists():
                self.error.emit(f"File not found: {self._file}")
                return

            self.status.emit(f"[reco] Slicing {self._file.name}...", "#00CFFF")
            cubes = _slice_file(self._file, self._lines_per_cube, self._max_cubes)
            if not cubes:
                self.error.emit("No cubes to reconstruct (empty file?)")
                return

            self.status.emit(
                f"[reco] {len(cubes)} cubes, model={self._model}, "
                f"lines/cube={self._lines_per_cube}",
                "#00CFFF",
            )
            self.cubes_ready.emit(cubes)

            # Use the lightweight _OllamaLite already shipped with the UI
            # (same one the terminal chat uses). Avoids the circular import
            # chain in engine/core (cube_providers <-> cube_analysis).
            try:
                from muninn.ui.ai_config import _OllamaLite
            except ImportError as e:
                self.error.emit(f"Cannot import _OllamaLite: {e}")
                return
            OllamaProvider = _OllamaLite

            provider = OllamaProvider(model=self._model)
            lang = _guess_lang(self._file)

            for cube in cubes:
                if self._stop:
                    self.status.emit("[reco] Stopped by user.", "#F59E0B")
                    break

                self.status.emit(
                    f"\n[cube {cube['idx']}] lines {cube['start']}-{cube['end']} "
                    f"(original sha={cube['sha'][:8]})",
                    "#00CFFF",
                )

                prompt = _build_prompt(cube, lang)
                generated = []
                try:
                    for chunk in provider.stream(
                        prompt, max_tokens=DEFAULT_MAX_TOKENS, temperature=0.1,
                    ):
                        if self._stop:
                            break
                        generated.append(chunk)
                        self.token.emit(chunk)
                except ConnectionError as e:
                    self.error.emit(f"Ollama error on cube {cube['idx']}: {e}")
                    return

                produced = _clean_llm_output("".join(generated))
                produced_sha = _sha256(_normalise(produced))
                sha_match = produced_sha == cube["sha"]
                ncd = _ncd(_normalise(cube["original"]), _normalise(produced))

                tag = "SHA MATCH" if sha_match else f"NCD={ncd:.3f}"
                color = "#32CD32" if sha_match else ("#F59E0B" if ncd < 0.3 else "#EF4444")
                self.status.emit(f"\n[cube {cube['idx']}] {tag}", color)

                self.cube_done.emit(cube["idx"], ncd, sha_match)

            self.finished.emit()

        except Exception as e:  # noqa: BLE001
            self.error.emit(f"Worker crash: {type(e).__name__}: {e}")
