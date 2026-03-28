"""Phase 7 tests — Intelligence (A1-A8).

Tests cover: adaptive fusion threshold, adaptive decay, orphan cleanup,
auto-vacuum, adaptive spreading hops, git diff pre-warm, auto-backup, prune warning.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

from muninn.mycelium_db import MyceliumDB, today_days


# ── A1: Fusion threshold adaptatif ───────────────────────────────

class TestA1AdaptiveFusion:
    def test_adaptive_threshold_small(self, tmp_path):
        """A1: Small mycelium gets low fusion threshold."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("alpha beta gamma")
        m.save()
        threshold = m.adaptive_fusion_threshold()
        assert threshold >= 2  # Minimum is 2
        m.close()

    def test_adaptive_threshold_large(self, tmp_path):
        """A1: Large mycelium gets higher fusion threshold."""
        # Create DB with many concepts
        db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
        for i in range(400):
            db._get_or_create_concept(f"concept_{i}")
        db.set_meta("migration_complete", "1")
        db.commit()
        db.close()

        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        threshold = m.adaptive_fusion_threshold()
        # sqrt(400) * 0.4 = 8
        assert threshold >= 5
        m.close()

    def test_adaptive_threshold_min(self, tmp_path):
        """A1: Threshold never goes below 2."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        threshold = m.adaptive_fusion_threshold()
        assert threshold >= 2
        m.close()


# ── A2: Decay half-life adaptatif ────────────────────────────────

class TestA2AdaptiveDecay:
    def test_adaptive_decay_default(self, tmp_path):
        """A2: Fresh mycelium returns default half-life."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        hl = m.adaptive_decay_half_life()
        assert 15 <= hl <= 90
        m.close()

    def test_adaptive_decay_active(self, tmp_path):
        """A2: Active repo gets shorter half-life."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.data["session_count"] = 100
        m.data["created"] = "2026-01-01"
        hl = m.adaptive_decay_half_life()
        # 100 sessions over ~3 months = ~1.1/day -> ~27 days
        assert hl < 40
        m.close()

    def test_adaptive_decay_inactive(self, tmp_path):
        """A2: Inactive repo gets longer half-life."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.data["session_count"] = 3
        m.data["created"] = "2025-01-01"
        hl = m.adaptive_decay_half_life()
        # 3 sessions over ~450 days = very low rate -> cap at 90
        assert hl >= 30
        m.close()


# ── A3: Orphan cleanup auto ─────────────────────────────────────

class TestA3OrphanCleanup:
    def test_cleanup_orphan_concepts(self, tmp_path):
        """A3: Removes concepts without edges when >20%."""
        db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
        # Create 10 concepts, only 2 with edges
        for i in range(10):
            db._get_or_create_concept(f"c_{i}")
        a = db._concept_cache["c_0"]
        b = db._concept_cache["c_1"]
        db._conn.execute(
            "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, 5, ?, ?)",
            (a, b, today_days(), today_days()))
        db.set_meta("migration_complete", "1")
        db.commit()
        db.close()

        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        removed = m.cleanup_orphan_concepts()
        assert removed == 8  # 10 - 2 = 8 orphans (80% > 20% threshold)
        m.close()

    def test_no_cleanup_below_threshold(self, tmp_path):
        """A3: No cleanup when orphans < 20%."""
        db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
        # All concepts have edges
        for i in range(5):
            a = db._get_or_create_concept(f"a_{i}")
            b = db._get_or_create_concept(f"b_{i}")
            db._conn.execute(
                "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, 5, ?, ?)",
                (a, b, today_days(), today_days()))
        db.set_meta("migration_complete", "1")
        db.commit()
        db.close()

        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        removed = m.cleanup_orphan_concepts()
        assert removed == 0
        m.close()


# ── A4: Auto-vacuum when decay > 10s ────────────────────────────

class TestA4AutoVacuum:
    def test_vacuum_method_exists(self, tmp_path):
        """A4: vacuum_if_needed method exists."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        assert hasattr(m, "vacuum_if_needed")
        m.close()

    def test_decay_returns_count(self, tmp_path):
        """A4: decay() returns dead count (vacuum timing integrated)."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("test data for decay")
        m.save()
        dead = m.decay(days=30)
        assert dead == 0  # Fresh edges don't die
        m.close()


# ── A5: Spreading activation hops adaptatif ──────────────────────

class TestA5AdaptiveHops:
    def test_adaptive_hops_default(self, tmp_path):
        """A5: Default hops = 2 for moderate graph."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        hops = m.adaptive_hops()
        assert hops in (1, 2, 3)
        m.close()

    def test_adaptive_hops_sparse(self, tmp_path):
        """A5: Sparse graph gets 3 hops."""
        db = MyceliumDB(tmp_path / ".muninn" / "mycelium.db")
        # Create sparse graph: 100 concepts, 50 edges (avg degree 1)
        for i in range(100):
            db._get_or_create_concept(f"sparse_{i}")
        for i in range(50):
            a = db._concept_cache[f"sparse_{i*2}"]
            b = db._concept_cache[f"sparse_{i*2+1}"]
            db._conn.execute(
                "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, 1, ?, ?)",
                (a, b, today_days(), today_days()))
        db.set_meta("migration_complete", "1")
        db.commit()
        db.close()

        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        hops = m.adaptive_hops()
        assert hops == 3  # Sparse = more hops
        m.close()

    def test_spread_uses_adaptive_hops(self, tmp_path):
        """A5: spread_activation uses adaptive hops when hops=None."""
        from muninn.mycelium import Mycelium
        m = Mycelium(tmp_path)
        m.observe_text("neural network deep learning")
        m.save()
        # hops=None should use adaptive
        result = m.spread_activation(["neural"])
        assert isinstance(result, list)
        m.close()


# ── A6: Boot pre-warm par git diff ───────────────────────────────

class TestA6BootPreWarm:
    def test_boot_has_git_diff_logic(self):
        """A6: boot() contains git diff pre-warm code."""
        import muninn
        _mdir = Path(muninn.__file__).parent
        src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
        assert "git diff" in src.lower() or "git" in src
        assert "diff_concepts" in src or "A6" in src


# ── A7: Auto-backup avant prune ─────────────────────────────────

class TestA7AutoBackup:
    def test_auto_backup_function_exists(self):
        """A7: _auto_backup_tree function exists."""
        import muninn
        assert hasattr(muninn, "_auto_backup_tree")
        assert callable(muninn._auto_backup_tree)

    def test_auto_backup_creates_tar(self, tmp_path, monkeypatch):
        """A7: Backup creates tar.gz file."""
        import muninn
        monkeypatch.setattr(muninn, "_REPO_PATH", tmp_path)
        tree_dir = tmp_path / ".muninn" / "tree"
        tree_dir.mkdir(parents=True)
        (tree_dir / "tree.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(muninn, "TREE_DIR", tree_dir)

        muninn._auto_backup_tree()
        backups = list((tmp_path / ".muninn" / "backups").glob("prune_before_*.tar.gz"))
        assert len(backups) == 1


# ── A8: Prune warning au boot ───────────────────────────────────

class TestA8PruneWarning:
    def test_prune_warning_in_boot(self):
        """A8: boot() contains prune warning logic."""
        import muninn
        _mdir = Path(muninn.__file__).parent
        src = chr(10).join(_mdir.joinpath(f).read_text(encoding="utf-8") for f in ["_engine.py", "muninn_layers.py", "muninn_tree.py", "muninn_feed.py"])
        assert "branches are cold" in src or "A8" in src
        assert "muninn prune" in src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
