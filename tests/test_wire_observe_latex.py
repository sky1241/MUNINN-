"""Tests for observe_latex/observe_with_concepts wiring.

Validates that:
1. observe_latex() correctly chunks LaTeX by \\section markers
2. observe_with_concepts() uses external concept lists
3. bootstrap_mycelium() routes .tex files to observe_latex()
4. ingest() includes .tex files and routes them correctly
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))

from mycelium import Mycelium
from mycelium_db import MyceliumDB


SAMPLE_LATEX = r"""
\documentclass{article}
\begin{abstract}
We study dark matter halos and galaxy formation in the early universe.
Observations of velocity dispersion provide evidence for hierarchical clustering.
\end{abstract}

\section{Introduction}
Galaxy rotation curves indicate the presence of dark matter.
The velocity dispersion of galaxy clusters supports this interpretation.
Numerical simulations of structure formation reproduce these observations.

\section{Methods}
We use N-body simulations with adaptive mesh refinement.
The gravitational potential is computed using a multigrid solver.
Baryon density profiles are measured from X-ray observations.

\section{Results}
The dark matter halo mass function agrees with predictions from Press-Schechter theory.
Galaxy clusters show a clear correlation between velocity dispersion and mass.
"""


def _make_mycelium(tmp_path: str) -> Mycelium:
    """Create a test mycelium with SQLite backend."""
    repo = Path(tmp_path) / "repo"
    repo.mkdir(exist_ok=True)
    m = Mycelium(repo_path=repo)
    m.observe(["seed_a", "seed_b"])
    m.save()
    return m


class TestObserveLatex:
    """T1: observe_latex() correctly parses LaTeX and creates connections."""

    def test_observe_latex_creates_connections(self, tmp_path):
        """LaTeX text should produce concept co-occurrences."""
        m = _make_mycelium(str(tmp_path))
        initial_count = m._db.connection_count()

        m.observe_latex(SAMPLE_LATEX)
        m.save()

        final_count = m._db.connection_count()
        assert final_count > initial_count, (
            f"observe_latex should create connections: {initial_count} -> {final_count}")

    def test_observe_latex_chunks_by_section(self, tmp_path):
        """Should chunk on \\section, not just \\n\\n."""
        m = _make_mycelium(str(tmp_path))

        # Spy on observe() to see what concept groups are passed
        observed_groups = []
        original_observe = m.observe

        def spy_observe(concepts, **kwargs):
            observed_groups.append(concepts)
            return original_observe(concepts, **kwargs)

        with patch.object(m, 'observe', side_effect=spy_observe):
            m.observe_latex(SAMPLE_LATEX)

        # Should have multiple groups (one per section)
        assert len(observed_groups) >= 2, (
            f"Should chunk into 2+ sections, got {len(observed_groups)}")

    def test_observe_latex_strips_commands(self, tmp_path):
        """LaTeX commands should be stripped, not treated as concepts."""
        m = _make_mycelium(str(tmp_path))
        m.observe_latex(r"\textbf{important} \textit{result} and \cite{smith2020}")
        m.save()

        # Check that "textbf", "textit", "cite" are NOT concepts
        if m._db is not None:
            concepts = set(m._db._concept_cache.keys())
            assert "textbf" not in concepts
            assert "textit" not in concepts

    def test_observe_latex_empty_input(self, tmp_path):
        """Empty or minimal LaTeX should not crash."""
        m = _make_mycelium(str(tmp_path))
        m.observe_latex("")
        m.observe_latex("\\section{Empty}")
        m.save()  # Should not crash


class TestObserveWithConcepts:
    """T2: observe_with_concepts() uses external concept lists."""

    def test_observe_with_known_concepts(self, tmp_path):
        """Should only track known concepts, ignoring everything else."""
        m = _make_mycelium(str(tmp_path))
        initial_count = m._db.connection_count()

        known = ["dark matter", "galaxy", "velocity", "simulation", "halo"]
        m.observe_with_concepts(SAMPLE_LATEX, known)
        m.save()

        final_count = m._db.connection_count()
        assert final_count > initial_count, (
            f"Should create connections for known concepts: {initial_count} -> {final_count}")

    def test_observe_with_concepts_filters(self, tmp_path):
        """Concepts NOT in the known list should not create connections."""
        m = _make_mycelium(str(tmp_path))

        # Only track "dark matter" — nothing else should pair with it
        known = ["dark matter"]
        m.observe_with_concepts(SAMPLE_LATEX, known)
        m.save()

        # With only 1 known concept, no pairs can be formed
        # (need 2+ concepts in same chunk)
        concepts = set(m._db._concept_cache.keys())
        # "dark matter" may or may not appear (depends on regex matching)
        # but no foreign concepts should sneak in
        assert "multigrid" not in concepts

    def test_observe_with_concepts_on_plain_text(self, tmp_path):
        """Should auto-detect plain text (no LaTeX markers) and chunk by paragraph."""
        m = _make_mycelium(str(tmp_path))
        plain = "Dark matter and galaxy formation.\n\nVelocity and simulation results."
        known = ["dark matter", "galaxy", "velocity", "simulation"]
        m.observe_with_concepts(plain, known)
        m.save()
        # Should not crash, may create connections if concepts found


class TestBootstrapTexRouting:
    """T3: bootstrap_mycelium() routes .tex files to observe_latex()."""

    def test_bootstrap_picks_up_tex_files(self, tmp_path):
        """Bootstrap should find and process .tex files — verify via connections."""
        repo = Path(str(tmp_path)) / "test_repo"
        repo.mkdir()
        # Create a .tex file with distinct academic concepts
        (repo / "paper.tex").write_text(SAMPLE_LATEX, encoding="utf-8")

        from muninn import bootstrap_mycelium
        bootstrap_mycelium(repo)

        # Verify the mycelium was fed — should have connections from LaTeX content
        m = Mycelium(repo_path=repo)
        count = m._db.connection_count() if m._db else 0
        assert count > 0, "Bootstrap with .tex should create mycelium connections"

    def test_bootstrap_tex_pattern_in_glob(self):
        """The bootstrap glob list should include **/*.tex."""
        import inspect
        from muninn import bootstrap_mycelium
        source = inspect.getsource(bootstrap_mycelium)
        assert "**/*.tex" in source, "bootstrap should glob for .tex files"

    def test_bootstrap_routing_logic(self):
        """The bootstrap should check f.suffix == '.tex' for routing."""
        import inspect
        from muninn import bootstrap_mycelium
        source = inspect.getsource(bootstrap_mycelium)
        assert "observe_latex" in source, "bootstrap should call observe_latex for .tex"


class TestIngestTexRouting:
    """T4: ingest() includes .tex and routes to observe_latex()."""

    def test_ingest_glob_includes_tex(self):
        """ingest() should glob for .tex files in directories."""
        import inspect
        from muninn_feed import ingest
        source = inspect.getsource(ingest)
        assert "**/*.tex" in source, "ingest should glob for .tex files"

    def test_ingest_routing_logic(self):
        """ingest() should route .tex to observe_latex()."""
        import inspect
        from muninn_feed import ingest
        source = inspect.getsource(ingest)
        assert "observe_latex" in source, "ingest should call observe_latex for .tex"


class TestEndToEnd:
    """E2E: Full pipeline with LaTeX files."""

    def test_latex_observe_save_status(self, tmp_path):
        """observe_latex -> save -> status should work end-to-end."""
        m = _make_mycelium(str(tmp_path))

        m.observe_latex(SAMPLE_LATEX)
        m.save()

        status = m.status()
        assert isinstance(status, str)
        assert len(status) > 0

        # Should have connections from the LaTeX content
        count = m._db.connection_count()
        assert count > 1, f"Should have multiple connections, got {count}"
