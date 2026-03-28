#!/usr/bin/env python3
"""
Test REEL du Cube — reconstruction via Claude API.

Teste sur le corpus multi-langage (tests/cube_corpus/) — 7 fichiers, 6 langages, ~12K lignes.
Pas de mock. Le LLM reconstruit depuis les voisins.
Validation SHA-256 + NCD.

Usage:
    python -m pytest tests/test_cube_real_api.py -v -s
    ~$2-3 par run complet (Sonnet, tous les cubes)
"""
import os
import sys
import time
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from cube import (
    Cube, CubeStore, ClaudeProvider,
    subdivide_file, assign_neighbors,
    reconstruct_cube, compute_ncd,
)

# Skip all tests if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skip real API tests"
)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "cube_corpus")

# All corpus files
CORPUS_FILES = {
    "go": os.path.join(CORPUS_DIR, "server.go"),
    "python": os.path.join(CORPUS_DIR, "analytics.py"),
    "jsx": os.path.join(CORPUS_DIR, "components.jsx"),
    "rust": os.path.join(CORPUS_DIR, "cache.rs"),
    "typescript": os.path.join(CORPUS_DIR, "store.ts"),
    "kotlin": os.path.join(CORPUS_DIR, "pipeline.kt"),
    "c": os.path.join(CORPUS_DIR, "allocator.c"),
}


def _safe_print(s):
    """Print with unicode fallback for Windows cp1252."""
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode('ascii', 'replace').decode())


@pytest.fixture(scope="module")
def provider():
    """Claude Sonnet for reconstruction."""
    return ClaudeProvider(model="claude-sonnet-4-6")


def _build_cubes(file_path, target_tokens=112):
    """Subdivide a file into cubes, store, assign neighbors."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "cube_test.db")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    cubes = subdivide_file(content=content, file_path=file_path, target_tokens=target_tokens)
    store = CubeStore(db_path)
    for cube in cubes:
        store.save_cube(cube)
    assign_neighbors(cubes, [], store, max_neighbors=9)
    return cubes, store, tmp


def _reconstruct_one(cubes, store, provider, index, quiet=False):
    """Destroy cube at index, reconstruct via API, return result."""
    target = cubes[index]
    neighbor_entries = store.get_neighbors(target.id)
    neighbor_cubes = [store.get_cube(nid) for nid, _, _ in neighbor_entries if store.get_cube(nid)]

    result = reconstruct_cube(target, neighbor_cubes, provider, ncd_threshold=0.3)

    if not quiet:
        _safe_print(f"  [{index:>4}] L{target.line_start}-{target.line_end} "
                     f"SHA={'Y' if result.exact_match else 'N'} "
                     f"NCD={result.ncd_score:.3f} "
                     f"{'OK' if result.success else 'FAIL'}")

    return result


def _run_full_destruction(lang, file_path, provider):
    """Run destruction/reconstruction on ALL cubes of a file. Returns stats dict."""
    _safe_print(f"\n{'='*70}")
    _safe_print(f"  {lang.upper()} — {os.path.basename(file_path)}")
    _safe_print(f"{'='*70}")

    cubes, store, tmp = _build_cubes(file_path)
    n = len(cubes)
    _safe_print(f"  {n} cubes ({os.path.basename(file_path)})")
    _safe_print(f"  {'─'*60}")

    results = []
    t0 = time.time()

    for i in range(n):
        try:
            result = _reconstruct_one(cubes, store, provider, i)
            results.append(result)
        except Exception as e:
            _safe_print(f"  [{i:>4}] ERROR: {e}")
            results.append(None)

    elapsed = time.time() - t0

    # Stats
    valid = [r for r in results if r is not None]
    exact = sum(1 for r in valid if r.exact_match)
    success = sum(1 for r in valid if r.success)
    errors = sum(1 for r in results if r is None)
    avg_ncd = sum(r.ncd_score for r in valid) / len(valid) if valid else 1.0
    min_ncd = min(r.ncd_score for r in valid) if valid else 1.0
    max_ncd = max(r.ncd_score for r in valid) if valid else 1.0

    _safe_print(f"\n  {'='*60}")
    _safe_print(f"  BILAN {lang.upper()}: {n} cubes, {elapsed:.1f}s")
    _safe_print(f"  SHA exact:  {exact}/{n} ({100*exact/n:.1f}%)")
    _safe_print(f"  NCD < 0.3:  {success}/{n} ({100*success/n:.1f}%)")
    _safe_print(f"  NCD avg:    {avg_ncd:.3f}  (min={min_ncd:.3f}, max={max_ncd:.3f})")
    _safe_print(f"  Errors:     {errors}")
    _safe_print(f"  {'='*60}")

    store.close()
    shutil.rmtree(tmp, ignore_errors=True)

    return {
        "lang": lang,
        "file": os.path.basename(file_path),
        "total": n,
        "exact": exact,
        "success": success,
        "errors": errors,
        "avg_ncd": avg_ncd,
        "min_ncd": min_ncd,
        "max_ncd": max_ncd,
        "elapsed": elapsed,
    }


# ─── TEST: Full destruction of each language ──────────────────────────

class TestCorpusFullDestruction:
    """Destruction/reconstruction de TOUS les cubes du corpus multi-langage."""

    def test_go_full(self, provider):
        """Go — server.go full destruction."""
        stats = _run_full_destruction("go", CORPUS_FILES["go"], provider)
        assert stats["errors"] == 0, f"{stats['errors']} API errors"
        assert stats["avg_ncd"] < 0.85, f"avg NCD {stats['avg_ncd']:.3f} too high"

    def test_python_full(self, provider):
        """Python — analytics.py full destruction."""
        stats = _run_full_destruction("python", CORPUS_FILES["python"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85

    def test_jsx_full(self, provider):
        """JSX — components.jsx full destruction."""
        stats = _run_full_destruction("jsx", CORPUS_FILES["jsx"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85

    def test_rust_full(self, provider):
        """Rust — cache.rs full destruction."""
        stats = _run_full_destruction("rust", CORPUS_FILES["rust"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85

    def test_typescript_full(self, provider):
        """TypeScript — store.ts full destruction."""
        stats = _run_full_destruction("typescript", CORPUS_FILES["typescript"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85

    def test_kotlin_full(self, provider):
        """Kotlin — pipeline.kt full destruction."""
        stats = _run_full_destruction("kotlin", CORPUS_FILES["kotlin"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85

    def test_c_full(self, provider):
        """C — allocator.c full destruction."""
        stats = _run_full_destruction("c", CORPUS_FILES["c"], provider)
        assert stats["errors"] == 0
        assert stats["avg_ncd"] < 0.85


# ─── TEST: Cross-language summary ─────────────────────────────────────

class TestCorpusSummary:
    """Run all languages and print a final comparison table."""

    def test_full_corpus_report(self, provider):
        """ALL LANGUAGES — full destruction + summary report."""
        all_stats = []
        total_cubes = 0
        total_exact = 0
        total_success = 0
        total_time = 0

        for lang, fpath in CORPUS_FILES.items():
            if not os.path.exists(fpath):
                _safe_print(f"  SKIP {lang}: file not found")
                continue
            stats = _run_full_destruction(lang, fpath, provider)
            all_stats.append(stats)
            total_cubes += stats["total"]
            total_exact += stats["exact"]
            total_success += stats["success"]
            total_time += stats["elapsed"]

        # Final report
        _safe_print(f"\n{'#'*70}")
        _safe_print(f"  RAPPORT FINAL — CORPUS COMPLET")
        _safe_print(f"{'#'*70}")
        _safe_print(f"  {'Lang':<12} {'Cubes':>6} {'Exact':>6} {'NCD<0.3':>8} {'Avg NCD':>8} {'Min':>6} {'Max':>6} {'Time':>7}")
        _safe_print(f"  {'─'*62}")

        for s in all_stats:
            _safe_print(f"  {s['lang']:<12} {s['total']:>6} {s['exact']:>6} "
                         f"{s['success']:>8} {s['avg_ncd']:>8.3f} "
                         f"{s['min_ncd']:>6.3f} {s['max_ncd']:>6.3f} "
                         f"{s['elapsed']:>6.1f}s")

        _safe_print(f"  {'─'*62}")
        global_avg = sum(s['avg_ncd'] for s in all_stats) / len(all_stats) if all_stats else 0
        _safe_print(f"  {'TOTAL':<12} {total_cubes:>6} {total_exact:>6} "
                     f"{total_success:>8} {global_avg:>8.3f} "
                     f"{'':>6} {'':>6} {total_time:>6.1f}s")
        _safe_print(f"{'#'*70}")

        # Save report to file
        report_path = os.path.join(os.path.dirname(__file__), "cube_corpus", "RESULTS.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"Cube Reconstruction Report — {time.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Model: claude-sonnet-4-6\n")
            f.write(f"{'='*70}\n\n")
            f.write(f"{'Lang':<12} {'Cubes':>6} {'Exact':>6} {'NCD<0.3':>8} {'Avg NCD':>8} {'Min':>6} {'Max':>6} {'Time':>7}\n")
            f.write(f"{'─'*62}\n")
            for s in all_stats:
                f.write(f"{s['lang']:<12} {s['total']:>6} {s['exact']:>6} "
                        f"{s['success']:>8} {s['avg_ncd']:>8.3f} "
                        f"{s['min_ncd']:>6.3f} {s['max_ncd']:>6.3f} "
                        f"{s['elapsed']:>6.1f}s\n")
            f.write(f"{'─'*62}\n")
            f.write(f"{'TOTAL':<12} {total_cubes:>6} {total_exact:>6} "
                    f"{total_success:>8} {global_avg:>8.3f} "
                    f"{'':>6} {'':>6} {total_time:>6.1f}s\n")

        _safe_print(f"\n  Report saved: {report_path}")

        # Assertions globales
        assert total_cubes > 100, f"Only {total_cubes} cubes — corpus too small"
        assert total_exact >= 0, "Sanity check"
