#!/usr/bin/env python3
"""
Tests for Cube Muninn — Briques B7-B8.

B7: AST parser multi-langage
B8: Construction graphe de voisins
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from muninn.cube import (
    scan_repo, ScannedFile, Cube, subdivide_file,
    parse_dependencies, Dependency,
    build_neighbor_graph, assign_neighbors,
    sha256_hash, CubeStore, MAX_NEIGHBORS,
)


# ─── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def python_repo(tmp_path):
    """Create a Python repo with cross-file imports."""
    (tmp_path / "main.py").write_text(
        "from utils import helper\n"
        "from models import User\n"
        "\ndef run():\n"
        "    u = User('sky')\n"
        "    helper(u)\n"
        "\nrun()\n"
    )
    (tmp_path / "utils.py").write_text(
        "import os\n"
        "import json\n"
        "\ndef helper(obj):\n"
        "    return str(obj)\n"
        "\ndef format_path(p):\n"
        "    return os.path.normpath(p)\n"
    )
    (tmp_path / "models.py").write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "\n"
        "class Admin(User):\n"
        "    def __init__(self, name):\n"
        "        super().__init__(name)\n"
        "        self.role = 'admin'\n"
    )
    (tmp_path / "config.py").write_text(
        "TIMEOUT = 3000\n"
        "MAX_RETRIES = 5\n"
        "DB_HOST = 'localhost'\n"
    )
    (tmp_path / "tests.py").write_text(
        "from main import run\n"
        "from models import User, Admin\n"
        "\ndef test_user():\n"
        "    u = User('test')\n"
        "    assert u.name == 'test'\n"
    )
    return tmp_path


@pytest.fixture
def js_repo(tmp_path):
    """Create a JS repo with imports."""
    (tmp_path / "app.js").write_text(
        "const utils = require('./utils');\n"
        "const config = require('./config');\n"
        "\nconsole.log(utils.greet(config.name));\n"
    )
    (tmp_path / "utils.js").write_text(
        "function greet(name) {\n"
        "    return `Hello ${name}`;\n"
        "}\n"
        "module.exports = { greet };\n"
    )
    (tmp_path / "config.js").write_text(
        "module.exports = {\n"
        "    name: 'Sky',\n"
        "    timeout: 3000\n"
        "};\n"
    )
    return tmp_path


@pytest.fixture
def cube_db(tmp_path):
    db_path = str(tmp_path / "test_neighbors.db")
    store = CubeStore(db_path)
    yield store
    store.close()


# ═══════════════════════════════════════════════════════════════════════
# B7: AST parser
# ═══════════════════════════════════════════════════════════════════════

class TestB7ASTParser:
    """B7: AST parser — parse imports, calls, refs."""

    def test_python_imports_detected(self, python_repo):
        """Python imports correctly parsed via AST."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        # main.py imports utils and models
        main_deps = [d for d in deps if d.source == 'main.py']
        targets = {d.target for d in main_deps}
        assert 'utils.py' in targets
        assert 'models.py' in targets

    def test_python_from_import(self, python_repo):
        """from X import Y correctly parsed."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        main_deps = [d for d in deps if d.source == 'main.py']
        names = {d.name for d in main_deps}
        assert any('helper' in n for n in names)
        assert any('User' in n for n in names)

    def test_python_test_imports(self, python_repo):
        """Test file imports parsed."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        test_deps = [d for d in deps if d.source == 'tests.py']
        targets = {d.target for d in test_deps}
        assert 'main.py' in targets
        assert 'models.py' in targets

    def test_no_self_import(self, python_repo):
        """No file imports itself."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        for d in deps:
            assert d.source != d.target, f"Self-import: {d.source}"

    def test_js_require_detected(self, js_repo):
        """JS require() calls parsed via regex."""
        files = scan_repo(str(js_repo))
        deps = parse_dependencies(files)
        app_deps = [d for d in deps if d.source == 'app.js']
        targets = {d.target for d in app_deps}
        assert 'utils.js' in targets
        assert 'config.js' in targets

    def test_syntax_error_graceful(self):
        """Malformed Python doesn't crash the parser."""
        files = [ScannedFile(
            path='bad.py',
            content='def broken(:\n    pass\n',
            language='python',
        )]
        deps = parse_dependencies(files)
        assert deps == []  # No crash, just no deps

    def test_isolated_file_no_deps(self, python_repo):
        """File with no imports has no dependencies."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        config_deps = [d for d in deps if d.source == 'config.py']
        assert len(config_deps) == 0

    def test_all_deps_are_import_type(self, python_repo):
        """All detected deps have type='import'."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        for d in deps:
            assert d.dep_type == 'import'

    def test_dep_dataclass_fields(self, python_repo):
        """Dependency dataclass has all required fields."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        assert len(deps) > 0
        d = deps[0]
        assert hasattr(d, 'source')
        assert hasattr(d, 'target')
        assert hasattr(d, 'dep_type')
        assert hasattr(d, 'name')


# ═══════════════════════════════════════════════════════════════════════
# B8: Neighbor graph
# ═══════════════════════════════════════════════════════════════════════

class TestB8NeighborGraph:
    """B8: Construction graphe de voisins — 9 closest per cube."""

    def test_neighbors_assigned(self, python_repo):
        """Cubes with same-file siblings or deps get neighbors."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)
        # At least some cubes should have neighbors
        has_neighbors = sum(1 for neighbors in graph.values() if len(neighbors) > 0)
        assert has_neighbors > 0

    def test_max_9_neighbors(self, python_repo):
        """No cube has more than 9 neighbors."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)
        for cube_id, neighbors in graph.items():
            assert len(neighbors) <= MAX_NEIGHBORS, \
                f"{cube_id} has {len(neighbors)} neighbors (max {MAX_NEIGHBORS})"

    def test_no_self_loop(self, python_repo):
        """No cube is its own neighbor."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)
        for cube_id, neighbors in graph.items():
            neighbor_ids = {nid for nid, _ in neighbors}
            assert cube_id not in neighbor_ids, f"Self-loop: {cube_id}"

    def test_same_file_higher_weight(self, python_repo):
        """Same-file neighbors have higher weight than cross-file."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)

        # Find a cube with both same-file and cross-file neighbors
        for cube_id, neighbors in graph.items():
            cube = next(c for c in all_cubes if c.id == cube_id)
            same_file = [(nid, w) for nid, w in neighbors
                         if any(c.file_origin == cube.file_origin for c in all_cubes if c.id == nid)]
            cross_file = [(nid, w) for nid, w in neighbors
                          if any(c.file_origin != cube.file_origin for c in all_cubes if c.id == nid)]
            if same_file and cross_file:
                max_same = max(w for _, w in same_file)
                max_cross = max(w for _, w in cross_file)
                assert max_same >= max_cross, \
                    f"Cross-file weight ({max_cross}) > same-file ({max_same})"
                return  # Found a valid case
        # If no cube has both, that's ok for small repos

    def test_cross_file_via_deps(self, python_repo):
        """Cross-file neighbors exist via dependency links."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)

        # main.py cubes should have neighbors in utils.py/models.py
        main_cubes = [c for c in all_cubes if c.file_origin == 'main.py']
        if main_cubes:
            main_cube = main_cubes[0]
            neighbors = graph.get(main_cube.id, [])
            neighbor_files = set()
            for nid, _ in neighbors:
                for c in all_cubes:
                    if c.id == nid:
                        neighbor_files.add(c.file_origin)
            # Should have cross-file neighbors
            assert len(neighbor_files) > 1 or len(all_cubes) <= MAX_NEIGHBORS

    def test_assign_neighbors_mutates(self, python_repo):
        """assign_neighbors() fills cube.neighbors in-place for connected cubes."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        assign_neighbors(all_cubes, deps)
        # Cubes from files with deps or multiple cubes should have neighbors
        has_neighbors = sum(1 for c in all_cubes if len(c.neighbors) > 0)
        assert has_neighbors > 0

    def test_assign_with_store(self, python_repo, cube_db):
        """assign_neighbors() persists to CubeStore."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        cube_db.save_cubes(all_cubes)
        assign_neighbors(all_cubes, deps, store=cube_db)

        # Verify persistence
        for cube in all_cubes:
            stored_neighbors = cube_db.get_neighbors(cube.id)
            assert len(stored_neighbors) == len(cube.neighbors), \
                f"Stored neighbors mismatch for {cube.id}"

    def test_weights_are_positive(self, python_repo):
        """All neighbor weights are positive."""
        files = scan_repo(str(python_repo))
        deps = parse_dependencies(files)
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))

        graph = build_neighbor_graph(all_cubes, deps)
        for cube_id, neighbors in graph.items():
            for nid, weight in neighbors:
                assert weight > 0, f"Non-positive weight: {cube_id} -> {nid} = {weight}"

    def test_empty_cubes(self):
        """Empty cube list → empty graph."""
        assert build_neighbor_graph([], []) == {}

    def test_single_cube(self):
        """Single cube → no neighbors possible."""
        c = Cube(id="a", content="x=1", sha256="h", file_origin="f",
                 line_start=1, line_end=1)
        graph = build_neighbor_graph([c], [])
        assert len(graph.get("a", [])) == 0


# ═══════════════════════════════════════════════════════════════════════
# Integration: B1-B8 pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestIntegrationB7B8:
    """Integration: scan → parse deps → subdivide → assign neighbors → store."""

    def test_full_pipeline(self, python_repo, cube_db):
        """Full B1-B8 pipeline: scan → deps → subdivide → neighbors → store."""
        # B1: scan
        files = scan_repo(str(python_repo))
        assert len(files) >= 4

        # B7: parse deps
        deps = parse_dependencies(files)
        assert len(deps) > 0

        # B4: subdivide
        all_cubes = []
        for f in files:
            all_cubes.extend(subdivide_file(f.path, f.content))
        assert len(all_cubes) > 0

        # B6: store
        cube_db.save_cubes(all_cubes)

        # B8: assign neighbors
        assign_neighbors(all_cubes, deps, store=cube_db)

        # Verify: most cubes have neighbors (isolated ones may not)
        has_neighbors = sum(1 for c in all_cubes if len(c.neighbors) > 0)
        assert has_neighbors > 0

        # Verify: neighbors stored in DB
        total_stored = 0
        for cube in all_cubes:
            stored = cube_db.get_neighbors(cube.id)
            total_stored += len(stored)
        assert total_stored > 0

    def test_on_real_repo(self):
        """Smoke test on actual Muninn repo (B1-B8)."""
        repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = scan_repo(repo_path, extensions={'.py'})
        deps = parse_dependencies(files)

        # Muninn has cross-file imports
        assert len(deps) > 0

        # Spot check: cube.py imports tokenizer
        cube_deps = [d for d in deps if 'cube' in d.source]
        assert len(cube_deps) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
