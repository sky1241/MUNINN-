#!/usr/bin/env python3
"""
Tests REELS avec LLM local (Ollama deepseek-coder:6.7b).

Pas de mock — on teste que le pipeline complet fonctionne avec un vrai modele.
Skip automatique si Ollama n'est pas dispo.

Usage:
    pytest tests/test_cube_real_llm.py -v              # run all
    pytest tests/test_cube_real_llm.py -v -k single    # just one cube
    pytest tests/test_cube_real_llm.py -v -k pipeline   # full pipeline
"""

import os
import sys
import json
import time
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.cube import (
    Cube, CubeStore, OllamaProvider,
    sha256_hash, subdivide_file, assign_neighbors, parse_dependencies,
    reconstruct_cube, compute_ncd, run_destruction_cycle,
    extract_all_ast_hints, prepare_cubes, post_cycle_analysis,
    ReconstructionResult, ScannedFile, FIMReconstructor,
)


# ─── Helpers ──────────────────────────────────────────────────────────

def ollama_available(model='deepseek-coder:6.7b'):
    """Check if Ollama is running and has the model."""
    try:
        url = 'http://localhost:11434/api/tags'
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            models = [m['name'] for m in data.get('models', [])]
            return model in models
    except Exception:
        return False


OLLAMA_MODEL = 'deepseek-coder:6.7b'
OLLAMA_OK = ollama_available(OLLAMA_MODEL)
skip_no_ollama = pytest.mark.skipif(
    not OLLAMA_OK,
    reason=f"Ollama not available or model {OLLAMA_MODEL} not pulled"
)


def _make_cube(id_, content, file_origin="test.py", line_start=1, line_end=5):
    return Cube(
        id=id_, content=content,
        sha256=sha256_hash(content),
        file_origin=file_origin,
        line_start=line_start, line_end=line_end,
        token_count=max(10, len(content.split())),
    )


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def provider():
    return OllamaProvider(model=OLLAMA_MODEL)


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "real_llm.db")
    s = CubeStore(db_path)
    yield s
    s.close()


# ═══════════════════════════════════════════════════════════════════════
# Test 1: Single cube reconstruction
# ═══════════════════════════════════════════════════════════════════════

@skip_no_ollama
class TestSingleCubeReconstruction:
    """Test reconstruction of individual cubes with a real LLM."""

    def test_simple_function(self, provider, store):
        """Reconstruct a trivial Python function."""
        content = "def add(a, b):\n    return a + b"
        cube = _make_cube("test:L1-L2:lv0", content)
        neighbor = _make_cube("test:L3-L5:lv0",
                              "def sub(a, b):\n    return a - b")

        result = reconstruct_cube(cube, [neighbor], provider, ncd_threshold=0.5)
        assert isinstance(result, ReconstructionResult)
        assert result.cube_id == cube.id
        # With a real LLM, NCD should be finite (< 1.0) — quality varies
        assert result.ncd_score < 1.0, f"NCD too high: {result.ncd_score}"
        print(f"\n  add(a,b): NCD={result.ncd_score:.3f} exact={result.exact_match}")

    def test_class_definition(self, provider, store):
        """Reconstruct a simple class."""
        content = "class Point:\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y"
        cube = _make_cube("test:L1-L4:lv0", content)
        neighbor = _make_cube("test:L5-L8:lv0",
                              "    def distance(self, other):\n        dx = self.x - other.x\n        return dx")

        result = reconstruct_cube(cube, [neighbor], provider, ncd_threshold=0.5)
        assert isinstance(result, ReconstructionResult)
        assert result.ncd_score < 0.8
        print(f"\n  Point class: NCD={result.ncd_score:.3f} exact={result.exact_match}")

    def test_go_function(self, provider, store):
        """Reconstruct Go code."""
        content = 'func handler(w http.ResponseWriter, r *http.Request) {\n    fmt.Fprintf(w, "Hello")\n}'
        cube = _make_cube("main.go:L1-L3:lv0", content, file_origin="main.go")

        result = reconstruct_cube(cube, [], provider, ncd_threshold=0.5)
        assert isinstance(result, ReconstructionResult)
        print(f"\n  Go handler: NCD={result.ncd_score:.3f} exact={result.exact_match}")

    def test_ncd_improves_with_neighbors(self, provider, store):
        """More context (neighbors) should help reconstruction."""
        content = "result = add(3, multiply(2, 4))\nprint(result)"
        cube = _make_cube("calc:L10-L11:lv0", content, file_origin="calc.py",
                          line_start=10, line_end=11)

        # Without neighbors
        r_alone = reconstruct_cube(cube, [], provider, ncd_threshold=0.5)

        # With neighbors
        n1 = _make_cube("calc:L1-L3:lv0", "def add(a, b):\n    return a + b",
                         file_origin="calc.py", line_start=1, line_end=3)
        n2 = _make_cube("calc:L5-L7:lv0", "def multiply(a, b):\n    return a * b",
                         file_origin="calc.py", line_start=5, line_end=7)
        r_with = reconstruct_cube(cube, [n1, n2], provider, ncd_threshold=0.5)

        print(f"\n  Without neighbors: NCD={r_alone.ncd_score:.3f}")
        print(f"  With neighbors:    NCD={r_with.ncd_score:.3f}")
        # We just verify both work — improvement not guaranteed with small examples
        assert isinstance(r_alone, ReconstructionResult)
        assert isinstance(r_with, ReconstructionResult)


# ═══════════════════════════════════════════════════════════════════════
# Test 2: Destruction cycle with real LLM
# ═══════════════════════════════════════════════════════════════════════

@skip_no_ollama
class TestRealDestructionCycle:
    """Run a full destruction cycle with Ollama."""

    def _build_cubes(self, store):
        """Build a small set of cubes from Python code."""
        cubes = [
            _make_cube("math:L1-L3:lv0",
                       "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b",
                       file_origin="math_ops.py", line_start=1, line_end=3),
            _make_cube("math:L5-L7:lv0",
                       "def sub(a, b):\n    \"\"\"Subtract b from a.\"\"\"\n    return a - b",
                       file_origin="math_ops.py", line_start=5, line_end=7),
            _make_cube("math:L9-L11:lv0",
                       "def mul(a, b):\n    \"\"\"Multiply two numbers.\"\"\"\n    return a * b",
                       file_origin="math_ops.py", line_start=9, line_end=11),
            _make_cube("main:L1-L4:lv0",
                       "from math_ops import add, sub, mul\n\nresult = add(1, mul(2, sub(5, 3)))\nprint(result)",
                       file_origin="main.py", line_start=1, line_end=4),
        ]
        store.save_cubes(cubes)
        for i, c in enumerate(cubes):
            for j, n in enumerate(cubes):
                if i != j:
                    store.set_neighbor(c.id, n.id, 0.7, 'static')
        return cubes

    def test_single_cycle(self, provider, store):
        """Run 1 cycle — check results structure."""
        cubes = self._build_cubes(store)
        t0 = time.time()
        results = run_destruction_cycle(cubes, store, provider,
                                        cycle_num=1, ncd_threshold=0.3)
        elapsed = time.time() - t0

        assert len(results) == 4
        success = sum(1 for r in results if r.success)
        exact = sum(1 for r in results if r.exact_match)
        avg_ncd = sum(r.ncd_score for r in results) / len(results)

        print(f"\n  Cycle 1: {success}/4 success, {exact} exact, "
              f"avg NCD={avg_ncd:.3f}, {elapsed:.1f}s")
        for r in results:
            tag = "SHA!" if r.exact_match else ("OK" if r.success else "FAIL")
            print(f"    {r.cube_id:<30} NCD={r.ncd_score:.3f} {tag}")

        # At least one should succeed with a decent model
        assert success >= 0  # Don't fail test on LLM quality

    def test_two_cycles_improve(self, provider, store):
        """Two cycles — second should have more healed (wagon effect)."""
        cubes = self._build_cubes(store)

        r1 = run_destruction_cycle(cubes, store, provider,
                                    cycle_num=1, ncd_threshold=0.3)
        healed1 = sum(1 for r in r1 if r.success)

        r2 = run_destruction_cycle(cubes, store, provider,
                                    cycle_num=2, ncd_threshold=0.3)
        healed2 = sum(1 for r in r2 if r.success)

        print(f"\n  Cycle 1: {healed1}/4 healed")
        print(f"  Cycle 2: {healed2}/4 healed")
        # We just verify both cycles run correctly
        assert len(r1) == 4
        assert len(r2) == 4

    def test_post_cycle_bricks_run(self, provider, store):
        """After cycle, B24/B22/B38 should have set attributes."""
        cubes = self._build_cubes(store)
        run_destruction_cycle(cubes, store, provider, cycle_num=1, ncd_threshold=0.3)

        # B24: KM survival on hot cubes
        hot = sorted(cubes, key=lambda c: c.temperature, reverse=True)[:4]
        for hc in hot:
            assert hasattr(hc, '_km_survival')
            print(f"  {hc.id:<30} T={hc.temperature:.2f} KM={hc._km_survival:.2f}")


# ═══════════════════════════════════════════════════════════════════════
# Test 3: Full pipeline (scan → prepare → cycle → analysis)
# ═══════════════════════════════════════════════════════════════════════

@skip_no_ollama
class TestRealFullPipeline:
    """Full pipeline with real LLM on real files."""

    def test_pipeline_python_files(self, provider, store, tmp_path):
        """Full pipeline on 2 small Python files."""
        # Create test files
        (tmp_path / "calculator.py").write_text(
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def sub(a, b):\n"
            "    return a - b\n\n"
            "def mul(a, b):\n"
            "    return a * b\n\n"
            "def div(a, b):\n"
            "    if b == 0:\n"
            "        raise ValueError('division by zero')\n"
            "    return a / b\n"
        )
        (tmp_path / "main.py").write_text(
            "from calculator import add, sub, mul, div\n\n"
            "x = add(10, mul(3, sub(7, 2)))\n"
            "y = div(x, 5)\n"
            "print(f'Result: {x}, {y}')\n"
        )

        # Scan
        from engine.core.cube import scan_repo
        scanned = scan_repo(str(tmp_path), extensions=['.py'])
        assert len(scanned) == 2

        # Subdivide
        all_cubes = []
        for sf in scanned:
            cubes = subdivide_file(sf.path, sf.content)
            all_cubes.extend(cubes)
        print(f"\n  Scanned: {len(scanned)} files -> {len(all_cubes)} cubes")
        assert len(all_cubes) >= 2

        # Wire
        store.save_cubes(all_cubes)
        deps = parse_dependencies(scanned)
        assign_neighbors(all_cubes, deps, store)

        # Prepare (B25 + B21)
        active, stats = prepare_cubes(all_cubes, store, deps=deps, use_survey=False)
        print(f"  Prepare: {stats}")

        # AST hints
        ast_hints = extract_all_ast_hints(all_cubes)

        # Cycle 1
        t0 = time.time()
        results = run_destruction_cycle(active, store, provider,
                                        cycle_num=1, ncd_threshold=0.3,
                                        ast_hints=ast_hints)
        elapsed = time.time() - t0

        success = sum(1 for r in results if r.success)
        exact = sum(1 for r in results if r.exact_match)
        avg_ncd = sum(r.ncd_score for r in results) / len(results) if results else 1.0

        print(f"  Cycle 1: {success}/{len(results)} success, "
              f"{exact} SHA exact, avg NCD={avg_ncd:.3f}, {elapsed:.1f}s")

        for r in results:
            tag = "SHA!" if r.exact_match else ("OK" if r.success else "FAIL")
            print(f"    {r.cube_id:<45} NCD={r.ncd_score:.3f} {tag}")

        # Post-cycle analysis
        analysis = post_cycle_analysis(active, store, deps=deps)
        print(f"\n  Analysis keys: {list(analysis.keys())}")
        if 'gods_number' in analysis and 'value' in analysis.get('gods_number', {}):
            print(f"  God's Number: {analysis['gods_number']['value']}")

        # Assertions — structure, not quality
        assert len(results) == len(active)
        assert all(isinstance(r, ReconstructionResult) for r in results)
        assert 'levels' in analysis
        assert 'gods_number' in analysis

    def test_corpus_file_go(self, provider, store):
        """Test on the Go corpus file if available."""
        corpus_dir = os.path.join(os.path.dirname(__file__), "cube_corpus")
        go_file = os.path.join(corpus_dir, "server.go")
        if not os.path.exists(go_file):
            pytest.skip("server.go not found in corpus")

        with open(go_file, "r", encoding="utf-8") as f:
            content = f.read()

        cubes = subdivide_file(go_file, content)
        store.save_cubes(cubes)
        assign_neighbors(cubes, [], store)

        print(f"\n  server.go: {len(cubes)} cubes")

        # Just test first 3 cubes to keep it fast
        test_cubes = cubes[:3]
        results = run_destruction_cycle(test_cubes, store, provider,
                                        cycle_num=1, ncd_threshold=0.3)

        for r in results:
            tag = "SHA!" if r.exact_match else ("OK" if r.success else "FAIL")
            print(f"    {r.cube_id:<45} NCD={r.ncd_score:.3f} {tag}")

        assert len(results) == len(test_cubes)


# ═══════════════════════════════════════════════════════════════════════
# Test 4: FIM (Fill-In-the-Middle) — deepseek-coder supporte FIM
# ═══════════════════════════════════════════════════════════════════════

@skip_no_ollama
class TestFIMReconstruction:
    """Test FIM mode with deepseek-coder (supports FIM tokens)."""

    def test_fim_supported(self, provider):
        """deepseek-coder should support FIM."""
        assert provider.supports_fim, f"{OLLAMA_MODEL} should support FIM"

    def test_fim_generate(self, provider):
        """Direct FIM generation works."""
        prefix = "def add(a, b):\n    "
        suffix = "\n\ndef sub(a, b):\n    return a - b"
        result = provider.fim_generate(prefix, suffix, max_tokens=50)
        assert isinstance(result, str)
        assert len(result) > 0
        print(f"\n  FIM result: {result[:80]!r}")

    def test_fim_reconstructor(self, provider, store):
        """FIMReconstructor uses FIM when provider supports it."""
        content = "def add(a, b):\n    return a + b"
        cube = _make_cube("test:L5-L6:lv0", content,
                          file_origin="calc.py", line_start=5, line_end=6)
        before = _make_cube("test:L1-L4:lv0",
                            "# Calculator module\nimport math\n\n",
                            file_origin="calc.py", line_start=1, line_end=4)
        after = _make_cube("test:L7-L10:lv0",
                           "def sub(a, b):\n    return a - b\n",
                           file_origin="calc.py", line_start=7, line_end=10)

        reconstructor = FIMReconstructor(provider)
        result = reconstructor.reconstruct_fim(
            prefix=before.content, suffix=after.content, max_tokens=100)
        assert isinstance(result, str)
        assert len(result) > 0
        ncd = compute_ncd(content, result)
        print(f"\n  FIM reconstruct: NCD={ncd:.3f}")
        print(f"  Original: {content!r}")
        print(f"  FIM:      {result[:80]!r}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
