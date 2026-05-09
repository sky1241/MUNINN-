"""Fetch + cache forge-shield risk scores for the cube heatmap UX.

Phase F6 of BATTLE_PLAN_FORGE_FINDINGS_2026-05-09.md.

The cube view in muninn/ui/ already colours bricks by mycelium temperature
(hot/cold runtime usage). Sky's idea: fold in the forge-shield signals
(carmack composite + locate Ochiai SBFL + modularity Q-contribution) so
the heatmap also reflects historical fragility, not just current usage.

This module is intentionally **standalone**:
  - No Qt import → safe to call from any process / test context
  - Pure subprocess shell-out to `forge` → no Python import dance
  - Disk cache in `.muninn/forge_cache.json` with a 24h TTL → the heatmap
    re-paints in milliseconds; only the first call (or stale cache hit)
    pays the actual `forge` runtime
  - Graceful degradation: if forge-shield is not installed, returns an
    empty-ish report so the UI can render the existing temperature-only
    heatmap without crashing

Usage from the UI:
    from forge_metrics import get_repo_risk
    report = get_repo_risk(Path("/path/to/repo"))
    score = report.fused.get("engine/core/muninn.py", 0.0)  # 0..1
    color = color_for_score(score)

Anti-bullshit notes:
  - No claim about heatmap colours being "correct" — the fusion weights
    (0.5 * carmack + 0.4 * locate + 0.1 * modularity) are heuristic, not
    calibrated against a labelled dataset. Mirror of forge-shield's own
    "Honest limits" section.
  - locate Ochiai requires `forge-shield[locate]` (coverage + pytest-cov).
    If not installed, that signal is silently dropped from the fusion.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# G1.2 (2026-05-09): hoist secure_perms to module scope with an explicit
# no-op fallback. Pre-fix, _save_cache used a triple-nested try/except
# whose ImportError branch did `return` AFTER the file was already written
# in 0o644 — silently leaking forge-cache permissions on multi-user hosts.
try:
    from _secrets import secure_perms  # type: ignore[no-redef]
except ImportError:
    try:
        from muninn._secrets import secure_perms  # type: ignore[no-redef]
    except ImportError:
        # Last resort: log to stderr ONCE so the leak is visible, then no-op.
        # Calling code should not crash because of a missing security helper.
        print(
            "[forge_metrics] WARNING: _secrets.secure_perms unavailable — "
            "forge cache files will inherit the process umask (likely 0o644). "
            "Install muninn-memory or fix the engine.core path resolution.",
            file=sys.stderr,
        )

        def secure_perms(path, **kwargs):  # type: ignore[no-redef]
            """No-op fallback. _secrets.py was unimportable at module load."""
            return None

# 24h is long enough to amortise the carmack cost (which scans 12 weeks of
# git log) but short enough that a normal dev workflow refreshes daily.
_CACHE_TTL_SECONDS = 24 * 60 * 60

# Fusion weights — heuristic, see module docstring.
_FUSION_WEIGHTS = {"carmack": 0.5, "locate": 0.4, "modularity": 0.1}

_FORGE_TIMEOUT_SECONDS = 120


@dataclass
class ForgeRiskReport:
    """One snapshot of forge-shield risk metrics for a repo."""

    repo: Path
    captured_at: float = field(default_factory=time.time)
    carmack: dict[str, float] = field(default_factory=dict)
    locate: dict[str, float] = field(default_factory=dict)
    modularity_q: Optional[float] = None
    fused: dict[str, float] = field(default_factory=dict)
    forge_available: bool = True
    error: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "repo": str(self.repo),
            "captured_at": self.captured_at,
            "carmack": self.carmack,
            "locate": self.locate,
            "modularity_q": self.modularity_q,
            "fused": self.fused,
            "forge_available": self.forge_available,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, data: dict) -> "ForgeRiskReport":
        return cls(
            repo=Path(data.get("repo", ".")),
            captured_at=float(data.get("captured_at", 0.0)),
            carmack=dict(data.get("carmack") or {}),
            locate=dict(data.get("locate") or {}),
            modularity_q=data.get("modularity_q"),
            fused=dict(data.get("fused") or {}),
            forge_available=bool(data.get("forge_available", True)),
            error=data.get("error"),
        )


def _forge_binary_available() -> bool:
    """True iff `forge` is on PATH (forge-shield 1.1.x installed)."""
    return shutil.which("forge") is not None


def _run_forge(repo: Path, *args: str) -> tuple[str, int]:
    """Run `forge <args>` in the target repo. Returns (stdout, returncode).
    On any subprocess error, returns ('', -1) — callers handle gracefully."""
    try:
        proc = subprocess.run(
            ["forge", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=_FORGE_TIMEOUT_SECONDS,
            check=False,
        )
        return proc.stdout, proc.returncode
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return "", -1


# ── Output parsers ───────────────────────────────────────────────
# forge prints text reports to stdout; we parse with anchored regex.
# These are intentionally tolerant: forge's exact format may shift across
# versions, and we'd rather lose a row than crash the UI.

_CARMACK_LINE_RE = re.compile(
    r"^\s*([0-9]+\.[0-9]+)\s+(\S+\.py)\s*$", re.MULTILINE
)
_LOCATE_LINE_RE = re.compile(
    r"^\s*([0-9]+\.[0-9]+)\s+(\S+\.py):[0-9]+\b", re.MULTILINE
)
_MODULARITY_Q_RE = re.compile(r"\bQ\s*=\s*([0-9]+\.[0-9]+)")


def _parse_carmack(stdout: str) -> dict[str, float]:
    """Extract {file_path: score 0..1} from `forge --carmack` output."""
    return {m.group(2): float(m.group(1)) for m in _CARMACK_LINE_RE.finditer(stdout)}


def _parse_locate(stdout: str) -> dict[str, float]:
    """Extract {file_path: ochiai_score} from `forge --locate` output.
    Multiple lines per file (one per line number) — keep the max."""
    out: dict[str, float] = {}
    for m in _LOCATE_LINE_RE.finditer(stdout):
        score, path = float(m.group(1)), m.group(2)
        if score > out.get(path, 0.0):
            out[path] = score
    return out


def _parse_modularity_q(stdout: str) -> Optional[float]:
    """Extract the global Q value from `forge --modularity` output."""
    m = _MODULARITY_Q_RE.search(stdout)
    return float(m.group(1)) if m else None


# ── Fusion ───────────────────────────────────────────────────────


def _fuse(carmack: dict[str, float], locate: dict[str, float],
          modularity_q: Optional[float]) -> dict[str, float]:
    """Combine the three signals into a single 0..1 risk score per file.

    carmack and locate are already in [0, 1]. modularity_q is global
    (one value for the whole repo); we apply (1 - q) as a uniform bonus
    when the repo as a whole is poorly modularised.
    """
    files = set(carmack) | set(locate)
    fused: dict[str, float] = {}
    coupling_penalty = 0.0
    if modularity_q is not None and modularity_q < 0.30:
        # Q < 0.30 = "not modular"; nudge every file up.
        coupling_penalty = (0.30 - modularity_q) / 0.30  # 0..1
    for f in files:
        score = (
            _FUSION_WEIGHTS["carmack"] * carmack.get(f, 0.0)
            + _FUSION_WEIGHTS["locate"] * locate.get(f, 0.0)
            + _FUSION_WEIGHTS["modularity"] * coupling_penalty
        )
        fused[f] = min(1.0, score)
    return fused


# ── Cache + public API ───────────────────────────────────────────


def _cache_path(repo: Path) -> Path:
    return repo / ".muninn" / "forge_cache.json"


def _load_cached(repo: Path, ttl: int) -> Optional[ForgeRiskReport]:
    p = _cache_path(repo)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    captured = float(data.get("captured_at", 0.0))
    if time.time() - captured > ttl:
        return None
    return ForgeRiskReport.from_json(data)


def _save_cache(report: ForgeRiskReport) -> None:
    p = _cache_path(report.repo)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")
        secure_perms(p)  # module-level import; no-op fallback if _secrets missing
    except OSError:
        pass


def get_repo_risk(repo: Path, *, force_refresh: bool = False,
                  ttl_seconds: int = _CACHE_TTL_SECONDS) -> ForgeRiskReport:
    """Public entry point. Returns a `ForgeRiskReport` for `repo`.

    Caching: hits `.muninn/forge_cache.json` if younger than `ttl_seconds`,
    unless `force_refresh=True`.

    Graceful degradation: if `forge` is not on PATH, returns a report with
    `forge_available=False` and empty maps; the UI can fall back to the
    temperature-only heatmap without conditional logic.
    """
    repo = Path(repo).resolve()

    if not force_refresh:
        cached = _load_cached(repo, ttl_seconds)
        if cached is not None:
            return cached

    if not _forge_binary_available():
        report = ForgeRiskReport(
            repo=repo, forge_available=False,
            error="forge-shield not installed (pip install 'git+https://github.com/sky1241/forge.git@v1.1.1')",
        )
        _save_cache(report)
        return report

    carmack_out, carmack_rc = _run_forge(repo, "--carmack")
    locate_out, _ = _run_forge(repo, "--locate")  # fails silently if no [locate] extra
    modularity_out, _ = _run_forge(repo, "--modularity")

    carmack = _parse_carmack(carmack_out) if carmack_rc == 0 else {}
    locate = _parse_locate(locate_out)
    modularity_q = _parse_modularity_q(modularity_out)

    report = ForgeRiskReport(
        repo=repo,
        carmack=carmack,
        locate=locate,
        modularity_q=modularity_q,
        fused=_fuse(carmack, locate, modularity_q),
    )
    _save_cache(report)
    return report


# ── Colour mapping ───────────────────────────────────────────────


def color_for_score(score: float) -> str:
    """Map a fused risk score to a 6-digit hex colour for the heatmap.

    Thresholds picked to mirror the carmack writeup:
      - >= 0.70  → bright red    (high coupling + die-and-retry)
      - >= 0.40  → orange        (moderate)
      - >= 0.20  → yellow
      -  < 0.20  → green         (stable)
    """
    if score >= 0.70:
        return "#d62728"
    if score >= 0.40:
        return "#ff7f0e"
    if score >= 0.20:
        return "#bcbd22"
    return "#2ca02c"


# ── H2 (2026-05-09): UI helpers ──────────────────────────────────


def forge_score_for_path(repo: Path, file_path: str) -> Optional[float]:
    """Return the fused forge risk score for `file_path` relative to `repo`.

    Lazy + cached via get_repo_risk() (24h TTL on .muninn/forge_cache.json).
    Returns None if forge is unavailable, cache is empty, or the path is not
    in the report — UI callers can treat None as "no forge data, fall back
    to the temperature-based colour".
    """
    try:
        report = get_repo_risk(Path(repo))
    except Exception:
        return None
    if not report.forge_available or not report.fused:
        return None
    # Try several path normalisations to be robust to caller conventions.
    candidates = [str(file_path)]
    p = Path(file_path)
    candidates.append(str(p))
    try:
        candidates.append(str(p.relative_to(Path(repo).resolve())))
    except ValueError:
        pass
    for c in candidates:
        if c in report.fused:
            return float(report.fused[c])
    return None


def forge_color_for_path(repo: Path, file_path: str,
                         default: str = "#cccccc") -> str:
    """Map (repo, file_path) → 6-digit hex colour via forge fused score.

    Falls back to `default` when:
      - forge binary not installed
      - file not found in the carmack/locate report (e.g. just renamed)
      - any subprocess error talking to forge
    """
    score = forge_score_for_path(repo, file_path)
    if score is None:
        return default
    return color_for_score(score)
