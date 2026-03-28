"""WAL Adaptive Flush — robinets intelligents pour SQLite WAL.

Prevents WAL file from growing unbounded during runtime.
Checks periodically after writes and triggers PASSIVE checkpoints
when thresholds are exceeded. Adapts thresholds based on checkpoint duration.

Zero dependencies beyond sqlite3 + time (Python stdlib).
"""

import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class WALConfig:
    """Configuration adaptative du flush WAL."""
    # Verifier tous les N commits si on doit flusher
    check_every: int = 50
    # Seuil de pages WAL par defaut (1 page = 4KB, 1000 pages = ~4MB)
    default_threshold_pages: int = 1000
    # Intervalle max entre 2 checkpoints (secondes)
    max_interval_sec: float = 90.0
    # Taille max absolue du WAL avant flush force (pages)
    emergency_threshold_pages: int = 50000  # ~200MB

    def compute_threshold(self, history: list) -> int:
        """Ajuste le seuil selon la vitesse d'ecriture observee."""
        if len(history) < 3:
            return self.default_threshold_pages
        recent = history[-5:]
        avg_duration = sum(h[2] for h in recent) / len(recent)
        # Checkpoints trop longs -> reduire le seuil (flusher plus souvent)
        if avg_duration > 500:
            return max(500, int(self.default_threshold_pages * 0.5))
        # Checkpoints rapides -> on peut attendre plus
        if avg_duration < 50:
            return min(5000, int(self.default_threshold_pages * 2))
        return self.default_threshold_pages


class WALMonitor:
    """Surveille la taille du WAL et declenche des checkpoints adaptatifs."""

    def __init__(self, conn: sqlite3.Connection, config: WALConfig = None):
        self.conn = conn
        self.config = config or WALConfig()
        self.write_count = 0
        self.last_checkpoint = time.time()
        self.checkpoint_history: list[tuple[float, int, float]] = []

    def get_wal_size(self) -> int:
        """Taille actuelle du WAL en pages (read-only, no checkpoint side-effect).

        Reads the WAL file header directly to get the page count.
        Falls back to 0 if the WAL file doesn't exist or is empty
        (which means SQLite has already checkpointed everything).
        """
        try:
            import struct
            wal_path = str(self.conn.execute("PRAGMA database_list").fetchone()[2]) + "-wal"
            with open(wal_path, "rb") as f:
                header = f.read(32)
                if len(header) < 32:
                    return 0
                # WAL header: bytes 24-27 = checkpoint sequence (not needed)
                # We count frames: each frame = header(24 bytes) + page_size bytes
                page_size = struct.unpack(">I", header[8:12])[0]
                if page_size == 0 or page_size < 512 or page_size > 65536:
                    return 0
                import os
                file_size = os.fstat(f.fileno()).st_size
                frame_size = 24 + page_size  # 24-byte frame header + page data
                n_frames = (file_size - 32) // frame_size  # 32-byte WAL header
                return max(0, n_frames)
        except (OSError, struct.error, TypeError):
            return 0

    def should_checkpoint(self) -> bool:
        """Decide si on doit flusher maintenant."""
        wal_pages = self.get_wal_size()
        elapsed = time.time() - self.last_checkpoint
        # Emergency: WAL trop gros, flush immediat
        if wal_pages >= self.config.emergency_threshold_pages:
            return True
        threshold = self.config.compute_threshold(self.checkpoint_history)
        return wal_pages >= threshold or elapsed >= self.config.max_interval_sec

    def checkpoint(self):
        """Flush le WAL de maniere non-bloquante (PASSIVE). Single call, no redundancy."""
        try:
            start = time.time()
            wal_before = self.get_wal_size()
            # Single PASSIVE checkpoint — the ONLY place we call wal_checkpoint
            self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            duration_ms = (time.time() - start) * 1000
            self.checkpoint_history.append((time.time(), wal_before, duration_ms))
            self.checkpoint_history = self.checkpoint_history[-20:]
        except Exception:
            pass  # checkpoint failure should never crash the caller
        self.last_checkpoint = time.time()
        self.write_count = 0

    def on_write(self):
        """Appele apres chaque commit. Verifie si flush necessaire."""
        self.write_count += 1
        if self.write_count % self.config.check_every == 0:
            if self.should_checkpoint():
                self.checkpoint()
