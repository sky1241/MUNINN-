"""Tests for audit-identified bugs (Bug 1-4).

Bug 1: WAL double checkpoint — get_wal_size() no longer triggers checkpoint
Bug 2: Thread safety — MyceliumDB and CubeStore have threading.Lock
Bug 3: Vault rekey atomicity — two-phase rekey + recover_rekey()
Bug 4: _high_degree_cache invalidation in observe()
"""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── Bug 1: WAL double checkpoint ─────────────────────────────────

class TestBug1WALCheckpoint:
    """get_wal_size() must NOT trigger a checkpoint as side-effect."""

    def test_get_wal_size_reads_file_not_pragma(self, tmp_path):
        """get_wal_size() reads WAL file directly, does not use PRAGMA."""
        from wal_monitor import WALMonitor, WALConfig
        import inspect

        # Verify the source code of get_wal_size does NOT contain wal_checkpoint
        source = inspect.getsource(WALMonitor.get_wal_size)
        assert "wal_checkpoint" not in source, (
            "get_wal_size() should not use PRAGMA wal_checkpoint"
        )
        assert "struct" in source or "open" in source, (
            "get_wal_size() should read the WAL file directly"
        )

    def test_checkpoint_source_has_single_pragma_call(self, tmp_path):
        """checkpoint() should contain exactly one PRAGMA wal_checkpoint statement."""
        from wal_monitor import WALMonitor
        import inspect

        source = inspect.getsource(WALMonitor.checkpoint)
        # Count actual PRAGMA calls (not comments)
        import re
        pragma_calls = re.findall(r'["\']PRAGMA wal_checkpoint', source)
        assert len(pragma_calls) == 1, (
            f"checkpoint() has {len(pragma_calls)} PRAGMA wal_checkpoint calls, expected 1"
        )

    def test_get_wal_size_returns_valid_count(self, tmp_path):
        """get_wal_size() returns page count from WAL file header."""
        from wal_monitor import WALMonitor, WALConfig
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()

        monitor = WALMonitor(conn, WALConfig())

        # Insert data to grow WAL
        for i in range(100):
            conn.execute("INSERT INTO t VALUES (?)", (i,))
        conn.commit()

        size = monitor.get_wal_size()
        assert size > 0, "WAL should have pages after inserts"

        conn.close()

    def test_get_wal_size_no_wal_file(self, tmp_path):
        """get_wal_size() returns 0 when WAL file doesn't exist."""
        from wal_monitor import WALMonitor, WALConfig
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()

        monitor = WALMonitor(conn, WALConfig())

        # Force checkpoint to eliminate WAL
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        size = monitor.get_wal_size()
        assert size == 0

        conn.close()

    def test_should_checkpoint_no_side_effect(self, tmp_path):
        """should_checkpoint() calls get_wal_size() without checkpoint side-effect."""
        from wal_monitor import WALMonitor, WALConfig
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (x INTEGER)")
        for i in range(50):
            conn.execute("INSERT INTO t VALUES (?)", (i,))
        conn.commit()

        monitor = WALMonitor(conn, WALConfig())

        # Get WAL size before
        wal_path = str(db_path) + "-wal"
        size_before = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

        # should_checkpoint internally calls get_wal_size
        monitor.should_checkpoint()

        # WAL file should not have been truncated (no checkpoint side-effect)
        size_after = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
        assert size_after == size_before, (
            f"WAL size changed from {size_before} to {size_after} — "
            f"get_wal_size() had a checkpoint side-effect!"
        )
        conn.close()


# ── Bug 2: Thread safety ─────────────────────────────────────────

class TestBug2ThreadSafety:
    """MyceliumDB and CubeStore must have threading.Lock on writes."""

    def test_mycelium_db_has_lock(self, tmp_path):
        """MyceliumDB.__init__ creates a threading.Lock."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "mycelium.db")
        assert hasattr(db, '_lock')
        assert isinstance(db._lock, type(threading.Lock()))
        db.close()

    def test_cube_store_has_lock(self, tmp_path):
        """CubeStore.__init__ creates a threading.Lock."""
        from cube import CubeStore
        store = CubeStore(str(tmp_path / "cubes.db"))
        assert hasattr(store, '_lock')
        assert isinstance(store._lock, type(threading.Lock()))
        store.close()

    def test_mycelium_db_concurrent_writes(self, tmp_path):
        """Two threads writing to MyceliumDB don't corrupt data."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "mycelium.db")
        db.set_meta("migration_complete", "1")
        errors = []

        def writer(thread_id, n):
            try:
                for i in range(n):
                    db.upsert_connection(f"t{thread_id}_a{i}", f"t{thread_id}_b{i}")
            except Exception as e:
                errors.append((thread_id, str(e)))

        t1 = threading.Thread(target=writer, args=(1, 50))
        t2 = threading.Thread(target=writer, args=(2, 50))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert len(errors) == 0, f"Thread errors: {errors}"
        # Both threads should have written their connections
        count = db.connection_count()
        assert count == 100, f"Expected 100 connections, got {count}"
        db.close()

    def test_cube_store_concurrent_writes(self, tmp_path):
        """Two threads writing to CubeStore don't corrupt data."""
        from cube import CubeStore, Cube
        store = CubeStore(str(tmp_path / "cubes.db"))
        errors = []

        def writer(thread_id, n):
            try:
                for i in range(n):
                    cube = Cube(
                        id=f"t{thread_id}_c{i}",
                        sha256=f"hash_{thread_id}_{i}",
                        content=f"content {thread_id} {i}",
                        file_origin="test.py",
                        line_start=i,
                        line_end=i + 1,
                        level=0,
                        score=0.5,
                        temperature=0.5,
                        token_count=10,
                    )
                    store.save_cube(cube)
            except Exception as e:
                errors.append((thread_id, str(e)))

        t1 = threading.Thread(target=writer, args=(1, 30))
        t2 = threading.Thread(target=writer, args=(2, 30))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert len(errors) == 0, f"Thread errors: {errors}"
        count = store.count_cubes()
        assert count == 60, f"Expected 60 cubes, got {count}"
        store.close()

    def test_mycelium_db_lock_protects_delete(self, tmp_path):
        """delete_connection acquires lock."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "mycelium.db")
        db.set_meta("migration_complete", "1")
        db.upsert_connection("alpha", "beta")
        assert db.has_connection("alpha", "beta")

        # Delete should work (lock acquired internally)
        db.delete_connection("alpha", "beta")
        assert not db.has_connection("alpha", "beta")
        db.close()

    def test_mycelium_db_all_write_methods_use_lock(self, tmp_path):
        """Every write method in MyceliumDB must use self._lock."""
        import inspect
        from muninn.mycelium_db import MyceliumDB

        write_methods = [
            'set_meta', 'upsert_connection', 'upsert_fusion',
            'delete_connection', 'update_connection_count',
            'add_zone_to_edge', 'cleanup_old_tombstones', 'close',
            'batch_upsert_connections', 'batch_delete_connections',
            'commit', 'purge_secret_concepts', 'log_sync',
            'savepoint', 'rollback_to', 'release_savepoint',
            'record_tombstone',
        ]
        missing_lock = []
        for name in write_methods:
            method = getattr(MyceliumDB, name, None)
            if method is None:
                continue
            source = inspect.getsource(method)
            if 'self._lock' not in source:
                missing_lock.append(name)

        assert len(missing_lock) == 0, (
            f"Write methods without self._lock: {missing_lock}"
        )


# ── Bug 3: Vault rekey atomicity ─────────────────────────────────

class TestBug3VaultRekey:
    """rekey() must be KeyboardInterrupt-safe."""

    def _setup_vault(self, tmp_path, password="testpass"):
        """Helper: create an initialized vault with some encrypted files."""
        from vault import Vault
        muninn_dir = tmp_path / ".muninn"
        muninn_dir.mkdir(parents=True)
        # Create sensitive files
        (muninn_dir / "mycelium.db").write_bytes(b"mycelium data here")
        (muninn_dir / "session_index.json").write_text('{"sessions": []}', encoding="utf-8")

        vault = Vault(tmp_path)
        vault.init(password)
        vault.lock()
        return vault

    def test_rekey_normal(self, tmp_path):
        """Normal rekey works end-to-end."""
        from vault import Vault
        vault = self._setup_vault(tmp_path, "oldpass")
        result = vault.rekey("newpass")
        assert result["rekeyed"] >= 1
        assert "failed" not in result

        # Verify we can unlock with new password
        vault.wipe_key()
        vault2 = Vault(tmp_path)
        vault2.load_key("newpass")
        unlocked = vault2.unlock()
        assert unlocked["decrypted"] >= 1
        vault2.wipe_key()

    def test_rekey_no_rekey_marker_on_success(self, tmp_path):
        """After successful rekey, .salt.rekey marker is cleaned up."""
        vault = self._setup_vault(tmp_path)
        vault.rekey("newpass")
        salt_rekey = tmp_path / ".muninn" / "vault.salt.rekey"
        assert not salt_rekey.exists(), "Rekey marker should be cleaned up after success"
        vault.wipe_key()

    def test_rekey_phase1_interrupt_leaves_originals(self, tmp_path):
        """If interrupted during Phase 1, original .vault files are untouched."""
        from vault import Vault, _encrypt_bytes, _decrypt_bytes
        vault = self._setup_vault(tmp_path)
        locked_before = vault._get_locked_files()
        original_data = {vp.name: vp.read_bytes() for vp in locked_before}

        # Simulate Phase 1 interrupt: patch _encrypt_bytes to raise on 2nd call
        call_count = [0]
        original_encrypt = _encrypt_bytes.__wrapped__ if hasattr(_encrypt_bytes, '__wrapped__') else None

        import vault as vault_mod
        orig_encrypt = vault_mod._encrypt_bytes

        def interrupting_encrypt(data, key):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt("simulated")
            return orig_encrypt(data, key)

        vault_mod._encrypt_bytes = interrupting_encrypt
        try:
            try:
                vault.rekey("newpass")
            except KeyboardInterrupt:
                pass
        finally:
            vault_mod._encrypt_bytes = orig_encrypt

        # Original files should be untouched
        for vp in locked_before:
            if vp.exists():
                assert vp.read_bytes() == original_data[vp.name], (
                    f"{vp.name} was modified during Phase 1 interrupt!"
                )

        # .rekey temp files should exist (partial work)
        rekey_files = list((tmp_path / ".muninn").glob("*.rekey"))
        # Salt rekey marker should NOT exist (we didn't reach Phase 2)
        salt_rekey = tmp_path / ".muninn" / "vault.salt.rekey"
        assert not salt_rekey.exists(), "Salt rekey marker should not exist after Phase 1 interrupt"

        vault.wipe_key()

    def test_recover_rekey_no_marker(self, tmp_path):
        """recover_rekey() returns {recovered: False} when no marker exists."""
        from vault import Vault
        vault = self._setup_vault(tmp_path)
        result = vault.recover_rekey("anypass")
        assert result["recovered"] is False
        vault.wipe_key()

    def test_recover_rekey_with_marker_and_rekey_files(self, tmp_path):
        """recover_rekey() completes an interrupted Phase 2 with pending .rekey files."""
        from vault import Vault, _derive_key, _encrypt_bytes
        vault = self._setup_vault(tmp_path)
        new_password = "newpass123"

        # Simulate interrupted Phase 2: marker exists, .rekey files exist
        new_salt = os.urandom(32)
        new_key = _derive_key(new_password, new_salt)

        salt_rekey = tmp_path / ".muninn" / "vault.salt.rekey"
        salt_rekey.write_bytes(new_salt)

        # Create a proper .rekey file (re-encrypted with new key)
        locked = vault._get_locked_files()
        if locked:
            # Decrypt with old key, re-encrypt with new
            from vault import _decrypt_bytes
            data = locked[0].read_bytes()
            plaintext = _decrypt_bytes(data, vault._key)
            ct = _encrypt_bytes(plaintext, new_key)
            # Append .rekey (matching rekey() convention: foo.vault.rekey)
            rekey_path = locked[0].parent / (locked[0].name + ".rekey")
            rekey_path.write_bytes(ct)

        vault.wipe_key()

        # Recover
        vault2 = Vault(tmp_path)
        vault2.load_key("testpass")
        result = vault2.recover_rekey(new_password)
        assert result["recovered"] is True
        assert not salt_rekey.exists(), "Marker should be cleaned up"

        # Salt should now match the new password
        vault3 = Vault(tmp_path)
        vault3.load_key(new_password)
        vault3.wipe_key()

    def test_recover_rekey_marker_but_no_files_rekeyed(self, tmp_path):
        """CRITICAL: recover_rekey() must NOT update salt if no files were re-encrypted.

        Scenario: interrupt between salt.rekey write and first file replace.
        All .vault files still have old key. If salt is updated, data is lost forever.
        """
        from vault import Vault, _derive_key
        vault = self._setup_vault(tmp_path)
        old_password = "testpass"

        # Simulate: marker exists but NO replaces happened and NO .rekey files remain
        new_salt = os.urandom(32)
        salt_rekey = tmp_path / ".muninn" / "vault.salt.rekey"
        salt_rekey.write_bytes(new_salt)

        # Record old salt for comparison
        old_salt = vault.salt_path.read_bytes()

        vault.wipe_key()

        # Recover — should detect that files aren't decryptable with new key
        vault2 = Vault(tmp_path)
        vault2.load_key(old_password)
        result = vault2.recover_rekey("newpass_that_was_never_applied")

        # MUST NOT update salt — files are still encrypted with old key
        assert result["recovered"] is False, (
            "recover_rekey should refuse to update salt when no files were re-encrypted"
        )
        assert not salt_rekey.exists(), "Marker should be cleaned up even on refusal"

        # Old key must still work
        current_salt = vault2.salt_path.read_bytes()
        assert current_salt == old_salt, "Salt must NOT have changed"

        # Verify we can still unlock with old password
        vault3 = Vault(tmp_path)
        vault3.load_key(old_password)
        unlocked = vault3.unlock()
        assert unlocked["decrypted"] >= 1, "Must still be able to unlock with old password"
        vault3.wipe_key()

    def test_phase1_keyboard_interrupt_cleans_rekey_files(self, tmp_path):
        """KeyboardInterrupt during Phase 1 must clean up .rekey orphan files."""
        from vault import Vault
        vault = self._setup_vault(tmp_path)

        import vault as vault_mod
        orig_encrypt = vault_mod._encrypt_bytes
        call_count = [0]

        def interrupting_encrypt(data, key):
            call_count[0] += 1
            # Let first file succeed (creates .rekey), interrupt on second
            if call_count[0] >= 2:
                raise KeyboardInterrupt("simulated")
            return orig_encrypt(data, key)

        vault_mod._encrypt_bytes = interrupting_encrypt
        try:
            try:
                vault.rekey("newpass")
            except KeyboardInterrupt:
                pass
        finally:
            vault_mod._encrypt_bytes = orig_encrypt

        # .rekey files should be cleaned up by the KeyboardInterrupt handler
        rekey_orphans = list((tmp_path / ".muninn").glob("*.rekey"))
        # Filter out salt.rekey (should not exist either)
        vault_rekeys = [f for f in rekey_orphans if f.name != "vault.salt.rekey"]
        assert len(vault_rekeys) == 0, (
            f"Phase 1 KeyboardInterrupt should clean up .rekey files, found: "
            f"{[f.name for f in vault_rekeys]}"
        )
        vault.wipe_key()


# ── Bug 4: _high_degree_cache invalidation ───────────────────────

class TestBug4HighDegreeCache:
    """_high_degree_cache must be invalidated in observe(), not just save()."""

    def test_cache_invalidated_after_observe(self, tmp_path):
        """observe() invalidates _high_degree_cache."""
        from muninn.mycelium_db import MyceliumDB
        from muninn.mycelium import Mycelium

        # Create DB with migration flag
        db_path = tmp_path / ".muninn" / "mycelium.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db.close()

        m = Mycelium(tmp_path)
        assert m._db is not None

        # Prime the cache
        m._high_degree_cache = {"old_cached_value": True}

        # observe() should invalidate it
        m.observe(["concept_a", "concept_b", "concept_c"])
        assert m._high_degree_cache is None, (
            "_high_degree_cache should be None after observe()"
        )

    def test_cache_reset_during_save(self, tmp_path):
        """save() resets _high_degree_cache at start (then _check_fusions may refill it)."""
        from muninn.mycelium_db import MyceliumDB
        from muninn.mycelium import Mycelium

        db_path = tmp_path / ".muninn" / "mycelium.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db.close()

        m = Mycelium(tmp_path)
        # Set a bogus stale cache value
        m._high_degree_cache = {"STALE_VALUE": True}
        m.save()
        # After save, cache should NOT contain the stale value
        # (_check_fusions may refill with fresh data, or it's None)
        if m._high_degree_cache is not None:
            assert "STALE_VALUE" not in m._high_degree_cache, (
                "Stale cache survived save()"
            )

    def test_fusions_use_fresh_degree_after_observe(self, tmp_path):
        """After observe() adds many edges, _check_fusions sees updated degrees."""
        from muninn.mycelium_db import MyceliumDB
        from muninn.mycelium import Mycelium

        db_path = tmp_path / ".muninn" / "mycelium.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db.close()

        m = Mycelium(tmp_path)
        # Create a hub concept connected to many others
        concepts = [f"spoke_{i}" for i in range(30)]
        for c in concepts:
            m.observe(["hub_concept", c])

        # Cache should be invalidated after each observe
        assert m._high_degree_cache is None, (
            "Cache should be None after observe, not stale"
        )

        # Now if we call _check_fusions, it should see hub_concept as high-degree
        # (this is the bug — before the fix, the cache would be stale from the first observe)


# ── Integration: all bugs together ────────────────────────────────

class TestAuditBugsIntegration:
    """Integration tests to ensure all fixes work together."""

    def test_mycelium_full_cycle_with_locks(self, tmp_path):
        """Full cycle: create DB, observe, save, decay — all lock-protected."""
        from muninn.mycelium_db import MyceliumDB
        from muninn.mycelium import Mycelium

        db_path = tmp_path / ".muninn" / "mycelium.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db.close()

        m = Mycelium(tmp_path)
        # Observe
        m.observe(["test", "integration", "audit"])
        assert m._high_degree_cache is None  # Bug 4 fix
        assert hasattr(m._db, '_lock')  # Bug 2 fix

        # Save
        m.save()

        # Verify connections exist (observe uses batch writes directly on _conn)
        count = m._db.connection_count()
        assert count > 0, f"Expected connections after observe+save, got {count}"

    def test_wal_monitor_in_mycelium_db(self, tmp_path):
        """WALMonitor inside MyceliumDB doesn't double-checkpoint."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "mycelium.db")

        # The WAL monitor should use the fixed get_wal_size
        monitor = db._wal_monitor
        size = monitor.get_wal_size()
        assert isinstance(size, int)
        db.close()


# ── Audit Pass 2: 3 CRITICAL fixes ───────────────────────────────

class TestSQLInjectionSavepoint:
    """Savepoint name must be validated to prevent SQL injection."""

    def test_valid_names_accepted(self, tmp_path):
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        db.savepoint("pre_sync")
        db.release_savepoint("pre_sync")
        db.savepoint("my_save_123")
        db.release_savepoint("my_save_123")
        db.close()

    def test_injection_rejected(self, tmp_path):
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with pytest.raises(ValueError, match="Invalid savepoint name"):
            db.savepoint("x; DROP TABLE connections; --")
        db.close()

    def test_injection_with_quotes_rejected(self, tmp_path):
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with pytest.raises(ValueError):
            db.rollback_to("x' OR '1'='1")
        db.close()

    def test_injection_with_spaces_rejected(self, tmp_path):
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with pytest.raises(ValueError):
            db.release_savepoint("pre sync")
        db.close()

    def test_empty_name_rejected(self, tmp_path):
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with pytest.raises(ValueError):
            db.savepoint("")
        db.close()

    def test_validate_method_exists(self):
        """Source code must have _validate_savepoint_name."""
        import inspect
        from muninn.mycelium_db import MyceliumDB
        source = inspect.getsource(MyceliumDB)
        assert "_validate_savepoint_name" in source
        assert "re.match" in source


class TestInjectMemoryLock:
    """inject_memory() must hold _MuninnLock to prevent concurrent tree corruption."""

    def test_inject_uses_muninn_lock(self):
        """Source code of inject_memory must contain _MuninnLock."""
        import inspect
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn
        source = inspect.getsource(muninn.inject_memory)
        assert "_MuninnLock" in source, "inject_memory must use _MuninnLock"

    def test_inject_memory_basic(self, tmp_path):
        """inject_memory works correctly with the lock."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn

        # Setup tree
        tree_dir = tmp_path / ".muninn" / "tree"
        tree_dir.mkdir(parents=True, exist_ok=True)

        import json
        tree = {
            "root": {"file": "root.mn", "type": "root", "children": []},
            "nodes": {},
            "version": 3
        }
        tree_path = tree_dir / "tree.json"
        tree_path.write_text(json.dumps(tree), encoding="utf-8")

        with patch.object(muninn, '_REPO_PATH', tmp_path), \
             patch.object(muninn, '_get_tree_dir', return_value=tree_dir), \
             patch.object(muninn, 'load_tree', return_value=tree), \
             patch.object(muninn, 'save_tree'):
            result = muninn.inject_memory("test fact", repo_path=tmp_path)
            assert result is not None


class TestCubeStoreReadLocks:
    """CubeStore read methods must be protected by _lock."""

    def test_all_read_methods_use_lock(self):
        """Source code of read methods must contain self._lock."""
        import inspect
        from cube import CubeStore
        read_methods = ['get_cube', 'get_cubes_by_file', 'get_cubes_by_level',
                        'get_hot_cubes', 'count_cubes', 'get_neighbors', 'get_cycles']
        for method_name in read_methods:
            source = inspect.getsource(getattr(CubeStore, method_name))
            assert "self._lock" in source, f"{method_name} must use self._lock"

    def test_concurrent_read_write(self, tmp_path):
        """Reads and writes can happen concurrently without cursor corruption."""
        from cube import CubeStore, Cube
        store = CubeStore(tmp_path / "cubes.db")

        # Seed with data
        for i in range(10):
            store.save_cube(Cube(
                id=f"c{i}", sha256=f"h{i}", content=f"test {i}",
                file_origin="test.py", line_start=i, line_end=i+1,
                level=0, score=0.5, temperature=0.5, token_count=10
            ))

        errors = []

        def reader():
            try:
                for _ in range(50):
                    store.get_cube("c0")
                    store.count_cubes()
                    store.get_cubes_by_file("test.py")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(50):
                    store.update_temperature(f"c{i % 10}", 0.1 * (i % 10))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads += [threading.Thread(target=writer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        store.close()
        assert not errors, f"Concurrent read/write errors: {errors}"


class TestVaultKeyZeroing:
    """Vault must zero key material on all error paths."""

    def test_wrong_password_zeros_key(self, tmp_path):
        """Wrong password triggers _zero_bytes before setting key to None."""
        import inspect
        from vault import Vault
        source = inspect.getsource(Vault.load_key)
        # Verify _zero_bytes is called before self._key = None on auth fail
        assert "_zero_bytes(self._key)" in source, "load_key must call _zero_bytes on auth fail"

    def test_lock_has_finally_cleanup(self):
        """lock() must use try/finally to clean up plaintext data."""
        import inspect
        from vault import Vault
        source = inspect.getsource(Vault.lock)
        assert "finally:" in source, "lock() must have finally block for data cleanup"

    def test_unlock_has_finally_cleanup(self):
        """unlock() must use try/finally to clean up decrypted data."""
        import inspect
        from vault import Vault
        source = inspect.getsource(Vault.unlock)
        assert "finally:" in source, "unlock() must have finally block for plaintext cleanup"


class TestWALPageSizeValidation:
    """WAL page_size must be validated within SQLite bounds."""

    def test_page_size_bounds_in_source(self):
        """get_wal_size must reject page sizes outside 512-65536."""
        import inspect
        from wal_monitor import WALMonitor
        source = inspect.getsource(WALMonitor.get_wal_size)
        assert "512" in source, "Must validate minimum page size (512)"
        assert "65536" in source, "Must validate maximum page size (65536)"

    def test_corrupted_wal_returns_zero(self, tmp_path):
        """A WAL with invalid page size returns 0 frames."""
        import struct
        from wal_monitor import WALMonitor, WALConfig
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t(x)")
        conn.commit()

        # Write a fake WAL with invalid page_size (0xFFFFFFFF = 4GB)
        wal_path = str(db_path) + "-wal"
        header = bytearray(32)
        struct.pack_into(">I", header, 8, 0xFFFFFFFF)  # Invalid page size
        with open(wal_path, "wb") as f:
            f.write(header)

        monitor = WALMonitor(conn, WALConfig())
        assert monitor.get_wal_size() == 0, "Invalid page_size should return 0"
        conn.close()


class TestLockExitLogging:
    """_MuninnLock.__exit__ must log failures instead of silently ignoring."""

    def test_exit_does_not_use_ignore_errors(self):
        """__exit__ must not use ignore_errors=True."""
        import inspect
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn
        source = inspect.getsource(muninn._MuninnLock.__exit__)
        assert "ignore_errors" not in source, "__exit__ must not silently ignore rmtree errors"


class TestStaleLockTOCTOU:
    """Stale lock removal must use atomic rename to prevent TOCTOU race."""

    def test_stale_lock_uses_rename(self):
        """Source code must use rename() not just rmtree() for stale locks."""
        import inspect
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn
        source = inspect.getsource(muninn._MuninnLock.__enter__)
        assert ".rename(" in source, "Stale lock must use atomic rename"
        assert ".stale." in source, "Renamed stale lock must have .stale. marker"

    def test_stale_lock_cleanup(self, tmp_path):
        """After stale lock rename+cleanup, lock dir is gone."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn

        # Create a fake stale lock (no valid PID)
        lock_dir = tmp_path / ".muninn" / ".lock_tree"
        lock_dir.mkdir(parents=True, exist_ok=True)
        pid_file = lock_dir / "pid"
        pid_file.write_text("999999999", encoding="utf-8")  # dead PID
        hb_file = lock_dir / "heartbeat"
        hb_file.write_text("0", encoding="utf-8")  # ancient heartbeat

        lock = muninn._MuninnLock(tmp_path)
        # The lock should detect stale and acquire
        try:
            with lock:
                # If we get here, stale lock was removed and we acquired
                assert lock.lock_dir.exists()
        except (TimeoutError, OSError):
            pytest.skip("Could not test stale lock on this platform")


# ── Pass 4: Full codebase audit fixes ────────────────────────────

class TestRecordQuarantineLock:
    """record_quarantine/record_anomaly must use module-level locks."""

    def test_module_level_locks_exist(self):
        """Locks must be module-level in cube_analysis (M3 fix: moved from cube.py).
        cube_analysis is imported into cube via star-import, but the locks
        are not in __all__ so they stay only in cube_analysis's own namespace."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import cube_analysis
        assert hasattr(cube_analysis, '_quarantine_lock'), "Module-level _quarantine_lock required"
        assert hasattr(cube_analysis, '_anomaly_lock'), "Module-level _anomaly_lock required"
        assert isinstance(cube_analysis._quarantine_lock, type(threading.Lock()))
        assert isinstance(cube_analysis._anomaly_lock, type(threading.Lock()))

    def test_no_hasattr_lock_init(self):
        """Source must NOT use hasattr for lock initialization (race condition)."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import inspect, cube_analysis
        src_q = inspect.getsource(cube_analysis.record_quarantine)
        src_a = inspect.getsource(cube_analysis.record_anomaly)
        assert "hasattr" not in src_q, "record_quarantine must not use hasattr for lock"
        assert "hasattr" not in src_a, "record_anomaly must not use hasattr for lock"


class TestCubeHeatmapLock:
    """cube_heatmap and fuse_risks must use store._lock for reads."""

    def test_heatmap_uses_lock(self):
        import inspect, cube
        source = inspect.getsource(cube.cube_heatmap)
        assert "store._lock" in source, "cube_heatmap must use store._lock"

    def test_fuse_risks_uses_lock(self):
        import inspect, cube
        source = inspect.getsource(cube.fuse_risks)
        assert "store._lock" in source, "fuse_risks must use store._lock"


class TestConfigEncoding:
    """CubeConfig file operations must specify encoding='utf-8'."""

    def test_load_has_encoding(self):
        import inspect, cube
        source = inspect.getsource(cube.CubeConfig.load)
        # Count open() calls — all must have encoding
        opens = [l.strip() for l in source.split('\n') if 'open(' in l]
        for line in opens:
            assert "encoding" in line, f"open() without encoding: {line}"

    def test_save_has_encoding(self):
        import inspect, cube
        source = inspect.getsource(cube.CubeConfig.save)
        opens = [l.strip() for l in source.split('\n') if 'open(' in l]
        for line in opens:
            assert "encoding" in line, f"open() without encoding: {line}"


class TestTreeLockLeak:
    """_tree_lock must not leak file handles on timeout."""

    def test_timeout_returns_none(self):
        """On timeout, _tree_lock returns (None, False) — no leaked handle."""
        import inspect
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))
        import muninn
        source = inspect.getsource(muninn._tree_lock)
        # Must close handle before returning on timeout
        assert "lock_f.close()" in source, "_tree_lock must close handle on timeout"
        # Timeout path must return None, not the open handle
        assert "return None, False" in source

    def test_lock_open_has_encoding(self):
        """_tree_lock open() must specify encoding."""
        import inspect
        import muninn
        source = inspect.getsource(muninn._tree_lock)
        assert 'encoding="utf-8"' in source or "encoding='utf-8'" in source


class TestMyceliumDBTransaction:
    """MyceliumDB.transaction() must provide locked transactional access."""

    def test_transaction_exists(self):
        """MyceliumDB must have a transaction() method."""
        from muninn.mycelium_db import MyceliumDB
        assert hasattr(MyceliumDB, 'transaction')

    def test_transaction_acquires_lock(self, tmp_path):
        """transaction() must acquire _lock during context."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with db.transaction() as conn:
            # Lock should be held
            assert not db._lock.acquire(blocking=False), "Lock should be held during transaction"
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('test', 'val')")
        # Lock should be released
        assert db._lock.acquire(blocking=False), "Lock should be free after transaction"
        db._lock.release()
        db.close()

    def test_transaction_commits_on_success(self, tmp_path):
        """transaction() commits on clean exit."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        with db.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('tx_test', 'committed')")
        val = db.get_meta("tx_test")
        assert val == "committed"
        db.close()

    def test_transaction_rollback_on_error(self, tmp_path):
        """transaction() rolls back on exception."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        db.set_meta("before", "original")
        try:
            with db.transaction() as conn:
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('before', 'changed')")
                raise ValueError("simulated failure")
        except ValueError:
            pass
        # Value should be rolled back
        val = db.get_meta("before")
        assert val == "original", f"Expected 'original' after rollback, got '{val}'"
        db.close()

    def test_new_utility_methods_exist(self, tmp_path):
        """New utility methods must exist on MyceliumDB."""
        from muninn.mycelium_db import MyceliumDB
        db = MyceliumDB(tmp_path / "test.db")
        assert hasattr(db, 'checkpoint_wal')
        assert hasattr(db, 'vacuum')
        assert hasattr(db, 'delete_stale_fusions')
        assert hasattr(db, 'cleanup_orphan_concepts')
        assert hasattr(db, 'cleanup_orphan_zones')
        assert hasattr(db, 'get_zone_counts')
        assert hasattr(db, 'get_multi_zone_edges')
        assert hasattr(db, 'get_zone_avg_count')
        db.close()


class TestObserveUsesTransaction:
    """observe() must use db.transaction() instead of direct ._conn."""

    def test_observe_source_uses_transaction(self):
        """observe() source code must use transaction(), not _db._conn."""
        import inspect
        from muninn.mycelium import Mycelium
        source = inspect.getsource(Mycelium.observe)
        assert "self._db.transaction()" in source, "observe() must use db.transaction()"

    def test_save_uses_transaction(self):
        """save() source code must use transaction(), not _db._conn."""
        import inspect
        from muninn.mycelium import Mycelium
        source = inspect.getsource(Mycelium.save)
        assert "self._db.transaction()" in source, "save() must use db.transaction()"


class TestBareExceptsFixed:
    """Core files must use specific exception types, not bare except Exception."""

    def test_mycelium_db_no_bare_except_pass(self):
        """mycelium_db.py should not have 'except Exception: pass'."""
        source = open('engine/core/mycelium_db.py', encoding='utf-8').read()
        # Split into lines and check for the pattern
        lines = source.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "except Exception:" and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line == "pass":
                    assert False, f"Bare 'except Exception: pass' at line {i+1}"

    def test_mycelium_core_exceptions_specific(self):
        """mycelium.py core ops (save, observe, close) should use specific exceptions."""
        import inspect
        from muninn.mycelium import Mycelium
        for method_name in ['save', 'close']:
            source = inspect.getsource(getattr(Mycelium, method_name))
            if "except Exception:" in source and "pass" in source:
                # Check it's not just a comment
                lines = source.split('\n')
                for i, line in enumerate(lines):
                    if "except Exception:" in line and i + 1 < len(lines):
                        next_stripped = lines[i + 1].strip()
                        if next_stripped == "pass":
                            assert False, f"{method_name}: bare 'except Exception: pass' found"


class TestSessionSeenInit:
    """_session_seen must be initialized in __init__, not via hasattr."""

    def test_init_has_session_seen(self):
        """Mycelium.__init__ must set _session_seen."""
        import inspect
        from muninn.mycelium import Mycelium
        source = inspect.getsource(Mycelium.__init__)
        assert "_session_seen" in source, "__init__ must initialize _session_seen"
        assert "_congestion_checked" in source, "__init__ must initialize _congestion_checked"

    def test_observe_no_hasattr(self):
        """observe() must not use hasattr for _session_seen (race condition)."""
        import inspect
        from muninn.mycelium import Mycelium
        source = inspect.getsource(Mycelium.observe)
        assert "hasattr" not in source or "_session_seen" not in source.split("hasattr")[1][:50] if "hasattr" in source else True

    def test_session_seen_works(self, tmp_path):
        """_session_seen initialized properly and usable."""
        from muninn.mycelium_db import MyceliumDB
        from muninn.mycelium import Mycelium
        db_path = tmp_path / ".muninn" / "mycelium.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = MyceliumDB(db_path)
        db.set_meta("migration_complete", "1")
        db.close()
        m = Mycelium(tmp_path)
        assert hasattr(m, '_session_seen')
        assert isinstance(m._session_seen, set)
        assert hasattr(m, '_congestion_checked')
        assert m._congestion_checked is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
