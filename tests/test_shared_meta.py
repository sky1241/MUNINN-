"""Test P20c: Shared meta-mycelium — two devs, one collective brain.

Simulates:
  Alice works on repo_alice/, observes concepts, syncs to shared meta.
  Bob works on repo_bob/, observes different concepts, syncs to same meta.
  Both pull from meta and get each other's knowledge.

Uses real Mycelium instances with real SQLite DBs (not mocks).
"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest
import sys
from muninn.mycelium import Mycelium


@pytest.fixture
def shared_workspace(tmp_path):
    """Create a workspace with 2 repos + 1 shared meta directory."""
    # Shared meta directory (simulates NAS/OneDrive/network share)
    shared_dir = tmp_path / "shared_meta"
    shared_dir.mkdir()

    # Alice's repo
    alice_repo = tmp_path / "repo_alice"
    alice_repo.mkdir()
    (alice_repo / ".muninn").mkdir()
    # Alice's config points to shared meta
    alice_home = tmp_path / "home_alice" / ".muninn"
    alice_home.mkdir(parents=True)
    (alice_home / "config.json").write_text(
        json.dumps({"meta_path": str(shared_dir)}), encoding="utf-8"
    )

    # Bob's repo
    bob_repo = tmp_path / "repo_bob"
    bob_repo.mkdir()
    (bob_repo / ".muninn").mkdir()
    # Bob's config points to same shared meta
    bob_home = tmp_path / "home_bob" / ".muninn"
    bob_home.mkdir(parents=True)
    (bob_home / "config.json").write_text(
        json.dumps({"meta_path": str(shared_dir)}), encoding="utf-8"
    )

    return {
        "shared_dir": shared_dir,
        "alice_repo": alice_repo,
        "alice_home": alice_home.parent,
        "bob_repo": bob_repo,
        "bob_home": bob_home.parent,
    }


def _patch_home(monkeypatch, home_dir):
    """Redirect Path.home() to a custom directory."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home_dir))


# ── Test 1: Config loading ──────────────────────────────────────

class TestConfigLoading:
    def test_default_meta_path_without_config(self, monkeypatch, tmp_path):
        """Without config, meta_db_path falls back to ~/.muninn/."""
        fake_home = tmp_path / "no_config_home"
        fake_home.mkdir()
        _patch_home(monkeypatch, fake_home)
        result = Mycelium.meta_db_path()
        assert result == fake_home / ".muninn" / "meta_mycelium.db"

    def test_custom_meta_path_from_config(self, monkeypatch, shared_workspace):
        """With config, meta_db_path uses the shared directory."""
        _patch_home(monkeypatch, shared_workspace["alice_home"])
        result = Mycelium.meta_db_path()
        assert result == shared_workspace["shared_dir"] / "meta_mycelium.db"

    def test_both_devs_point_to_same_meta(self, monkeypatch, shared_workspace):
        """Alice and Bob resolve to the exact same meta DB path."""
        _patch_home(monkeypatch, shared_workspace["alice_home"])
        alice_meta = Mycelium.meta_db_path()
        _patch_home(monkeypatch, shared_workspace["bob_home"])
        bob_meta = Mycelium.meta_db_path()
        assert alice_meta == bob_meta

    def test_invalid_config_falls_back(self, monkeypatch, tmp_path):
        """Corrupted config.json falls back to default ~/.muninn/."""
        fake_home = tmp_path / "broken_home"
        muninn_dir = fake_home / ".muninn"
        muninn_dir.mkdir(parents=True)
        (muninn_dir / "config.json").write_text("NOT JSON", encoding="utf-8")
        _patch_home(monkeypatch, fake_home)
        result = Mycelium.meta_db_path()
        assert result == fake_home / ".muninn" / "meta_mycelium.db"


# ── Test 2: Sync + Pull between two devs ────────────────────────

class TestSharedSync:
    def test_alice_syncs_bob_pulls(self, monkeypatch, shared_workspace):
        """Alice observes concepts, syncs. Bob pulls and gets Alice's knowledge."""
        ws = shared_workspace

        # Alice observes "compression" + "tokens" + "muninn"
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        alice.observe(["compression", "tokens", "muninn", "pipeline"])
        alice.save()
        n_sync = alice.sync_to_meta()
        assert n_sync > 0, "Alice should have synced connections"

        # Verify meta DB exists in shared dir
        meta_db = ws["shared_dir"] / "meta_mycelium.db"
        assert meta_db.exists(), "Meta DB should be in shared directory"

        # Bob pulls from the same meta
        _patch_home(monkeypatch, ws["bob_home"])
        bob = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        bob.save()  # Initialize DB
        n_pull = bob.pull_from_meta(query_concepts=["compression", "tokens"])
        assert n_pull > 0, "Bob should have pulled Alice's connections"

        # Verify Bob now knows about compression<->tokens
        related = bob.get_related("compression", top_n=10)
        concept_names = [r[0] for r in related]
        assert "tokens" in concept_names or "muninn" in concept_names, \
            f"Bob should know Alice's concepts, got: {concept_names}"

    def test_bidirectional_sync(self, monkeypatch, shared_workspace):
        """Both devs sync, both get each other's knowledge."""
        ws = shared_workspace

        # Alice works on compression
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        alice.observe(["compression", "tokens", "benchmark", "ratio"])
        alice.save()
        alice.sync_to_meta()

        # Bob works on yggdrasil (totally different domain)
        _patch_home(monkeypatch, ws["bob_home"])
        bob = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        bob.observe(["yggdrasil", "graph", "structural_holes", "papers"])
        bob.save()
        bob.sync_to_meta()

        # Now Alice pulls — she should get Bob's yggdrasil concepts
        _patch_home(monkeypatch, ws["alice_home"])
        alice2 = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        n_pull = alice2.pull_from_meta(query_concepts=["yggdrasil", "graph"])
        assert n_pull > 0, "Alice should pull Bob's yggdrasil knowledge"

        # And Bob pulls Alice's compression concepts
        _patch_home(monkeypatch, ws["bob_home"])
        bob2 = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        n_pull2 = bob2.pull_from_meta(query_concepts=["compression", "tokens"])
        assert n_pull2 > 0, "Bob should pull Alice's compression knowledge"

    def test_zones_preserved_in_meta(self, monkeypatch, shared_workspace):
        """Each dev's zone tag is preserved in the shared meta."""
        ws = shared_workspace

        # Alice syncs
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        alice.observe(["shared_concept", "alice_specific"])
        alice.save()
        alice.sync_to_meta()

        # Bob syncs same concept
        _patch_home(monkeypatch, ws["bob_home"])
        bob = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        bob.observe(["shared_concept", "bob_specific"])
        bob.save()
        bob.sync_to_meta()

        # Check meta DB has both zones
        from muninn.mycelium_db import MyceliumDB
        _patch_home(monkeypatch, ws["alice_home"])  # either home works
        meta_db = MyceliumDB(Mycelium.meta_db_path())
        zones = set()
        for row in meta_db._conn.execute("SELECT DISTINCT zone FROM edge_zones"):
            zones.add(row[0])
        meta_db.close()
        assert "alice_repo" in zones, f"Alice's zone should be in meta, got: {zones}"
        assert "bob_repo" in zones, f"Bob's zone should be in meta, got: {zones}"


# ── Test 3: Conflict resistance ─────────────────────────────────

class TestConflictResistance:
    def test_concurrent_sync_no_crash(self, monkeypatch, shared_workspace):
        """Two devs syncing to same meta don't crash (SQLite WAL handles it)."""
        ws = shared_workspace

        # Alice creates mycelium with data
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        for i in range(20):
            alice.observe([f"concept_a{i}", f"concept_a{i+1}", "shared"])
        alice.save()

        # Bob creates mycelium with data
        _patch_home(monkeypatch, ws["bob_home"])
        bob = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        for i in range(20):
            bob.observe([f"concept_b{i}", f"concept_b{i+1}", "shared"])
        bob.save()

        # Both sync (sequentially — true concurrency needs threads)
        _patch_home(monkeypatch, ws["alice_home"])
        alice.sync_to_meta()
        _patch_home(monkeypatch, ws["bob_home"])
        bob.sync_to_meta()

        # Verify meta has data from both
        from muninn.mycelium_db import MyceliumDB
        _patch_home(monkeypatch, ws["alice_home"])
        meta_db = MyceliumDB(Mycelium.meta_db_path())
        edge_count = meta_db._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        concept_count = meta_db._conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
        meta_db.close()

        assert edge_count > 40, f"Meta should have edges from both devs, got {edge_count}"
        assert concept_count > 20, f"Meta should have concepts from both, got {concept_count}"

    def test_merge_strategy_max_not_sum(self, monkeypatch, shared_workspace):
        """Repeated syncs use MAX on counts (not SUM — avoids inflation)."""
        ws = shared_workspace
        _patch_home(monkeypatch, ws["alice_home"])

        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        # Observe same pair 5 times = count ~5
        for _ in range(5):
            alice.observe(["alpha", "beta"])
        alice.save()

        # Sync twice
        alice.sync_to_meta()
        alice.sync_to_meta()

        # Check count in meta — should be ~5, not ~10
        from muninn.mycelium_db import MyceliumDB
        meta_db = MyceliumDB(Mycelium.meta_db_path())
        row = meta_db._conn.execute(
            "SELECT count FROM edges LIMIT 1"
        ).fetchone()
        meta_db.close()
        assert row is not None
        assert row[0] < 8, f"Count should be ~5 (MAX strategy), not inflated, got {row[0]}"

    def test_no_data_loss_on_pull(self, monkeypatch, shared_workspace):
        """Pull only adds missing connections — doesn't overwrite local data."""
        ws = shared_workspace

        # Bob has strong local connection
        _patch_home(monkeypatch, ws["bob_home"])
        bob = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        for _ in range(10):
            bob.observe(["local_strong", "local_partner"])
        bob.save()

        # Get Bob's local count before pull
        bob_count_before = bob._db._conn.execute(
            "SELECT count FROM edges LIMIT 1"
        ).fetchone()[0]

        # Alice syncs a weak version of the same pair
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        alice.observe(["local_strong", "local_partner"])  # count=1
        alice.save()
        alice.sync_to_meta()

        # Bob pulls — his strong local count should NOT decrease
        _patch_home(monkeypatch, ws["bob_home"])
        bob2 = Mycelium(ws["bob_repo"], federated=True, zone="bob_repo")
        bob2.pull_from_meta(query_concepts=["local_strong"])

        bob_count_after = bob2._db._conn.execute(
            "SELECT count FROM edges LIMIT 1"
        ).fetchone()[0]

        assert bob_count_after >= bob_count_before, \
            f"Pull should not weaken local data: {bob_count_before} -> {bob_count_after}"


# ── Test 4: Edge cases ──────────────────────────────────────────

class TestEdgeCases:
    def test_empty_meta_pull_no_crash(self, monkeypatch, shared_workspace):
        """Pull from empty meta (no one synced yet) doesn't crash."""
        ws = shared_workspace
        _patch_home(monkeypatch, ws["alice_home"])
        alice = Mycelium(ws["alice_repo"], federated=True, zone="alice_repo")
        alice.save()
        n = alice.pull_from_meta(query_concepts=["anything"])
        assert n == 0

    def test_nonexistent_shared_dir_created(self, monkeypatch, tmp_path):
        """If meta_path points to nonexistent dir, it's auto-created."""
        fake_home = tmp_path / "auto_create_home"
        muninn_dir = fake_home / ".muninn"
        muninn_dir.mkdir(parents=True)
        new_shared = tmp_path / "does_not_exist_yet" / "deep" / "path"
        (muninn_dir / "config.json").write_text(
            json.dumps({"meta_path": str(new_shared)}), encoding="utf-8"
        )
        _patch_home(monkeypatch, fake_home)
        result = Mycelium.meta_db_path()
        assert result == new_shared / "meta_mycelium.db"
        assert new_shared.exists(), "Directory should be auto-created"

    def test_config_without_meta_path_key(self, monkeypatch, tmp_path):
        """Config exists but has no meta_path key — falls back to default."""
        fake_home = tmp_path / "no_key_home"
        muninn_dir = fake_home / ".muninn"
        muninn_dir.mkdir(parents=True)
        (muninn_dir / "config.json").write_text(
            json.dumps({"other_setting": "value"}), encoding="utf-8"
        )
        _patch_home(monkeypatch, fake_home)
        result = Mycelium.meta_db_path()
        assert result == fake_home / ".muninn" / "meta_mycelium.db"
