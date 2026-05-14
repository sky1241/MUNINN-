#!/usr/bin/env python3
"""Pre-compute LaBSE embeddings for every concept already in mycelium.db.

K.2.3 wires cross-lingual fusion in Mycelium.observe(), but the fusion can
only match against concepts that already have an embedding stored. Fresh
DBs have zero embeddings, so the very first observes can't fuse — they
just seed embeddings for their own (small) concept set.

This script closes that gap: it iterates every concept, embeds it via the
active EmbeddingProvider model, and persists the result. After running it,
Mycelium.observe(['Baum']) will fuse into the existing 'tree' concept
instead of creating a new orphan.

Run with MUNINN_EMBEDDINGS=1 in the environment so the provider is active.

Usage:
  MUNINN_EMBEDDINGS=1 python3 scripts/migrate_k2_embed_existing_concepts.py --dry-run
  MUNINN_EMBEDDINGS=1 python3 scripts/migrate_k2_embed_existing_concepts.py --apply
  MUNINN_EMBEDDINGS=1 python3 scripts/migrate_k2_embed_existing_concepts.py --apply --batch-size 128

The script is idempotent: re-running skips concepts that already have an
embedding for the current model (one row per (concept_id, model)).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.core.embeddings import EmbeddingProvider  # noqa: E402


def collect_pending(conn: sqlite3.Connection, model: str) -> list[tuple[int, str]]:
    """Return concepts that have NO embedding for the active model."""
    rows = conn.execute(
        """
        SELECT c.id, c.name
        FROM concepts c
        LEFT JOIN concept_embeddings ce
          ON c.id = ce.concept_id AND ce.model = ?
        WHERE ce.concept_id IS NULL
        ORDER BY c.id
        """,
        (model,),
    ).fetchall()
    return list(rows)


def persist_batch(conn: sqlite3.Connection, ids: list[int], vecs, model: str) -> None:
    import numpy as np
    ts = int(time.time())
    dim = int(vecs.shape[1])
    rows = []
    for cid, vec in zip(ids, vecs):
        vec = np.asarray(vec, dtype=np.float32)
        rows.append((cid, model, dim, vec.tobytes(), ts))
    conn.executemany(
        "INSERT OR REPLACE INTO concept_embeddings "
        "(concept_id, model, dim, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def run(db_path: Path, apply: bool, batch_size: int, max_concepts: int | None) -> int:
    if not db_path.exists():
        print(f"ERROR: mycelium DB not found: {db_path}", file=sys.stderr)
        return 1

    provider = EmbeddingProvider.get()
    if not provider.is_enabled():
        print(
            "ERROR: MUNINN_EMBEDDINGS != '1'. Set MUNINN_EMBEDDINGS=1 to opt in.",
            file=sys.stderr,
        )
        return 1
    if not provider.is_available():
        report = provider.health_report()
        print(f"ERROR: EmbeddingProvider not available: {report}", file=sys.stderr)
        return 1

    model = provider.model_name
    print(f"K.2 model: {model} (dim={provider.dim}, threshold={provider.threshold})")

    conn = sqlite3.connect(str(db_path))
    total_concepts = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    existing = conn.execute(
        "SELECT COUNT(*) FROM concept_embeddings WHERE model = ?", (model,)
    ).fetchone()[0]
    pending = collect_pending(conn, model)
    if max_concepts is not None:
        pending = pending[:max_concepts]
    print(f"Concepts: {total_concepts} total, {existing} already embedded, {len(pending)} pending")

    if not pending:
        print("Nothing to do.")
        conn.close()
        return 0

    if not apply:
        print(f"\n--dry-run: would embed {len(pending)} concepts in batches of {batch_size}.")
        print("Sample first 10 pending names:")
        for cid, name in pending[:10]:
            print(f"  [{cid}] {name!r}")
        eta_s = len(pending) * 0.012  # ~12ms per concept warm CPU
        print(f"\nEstimated wall time: {eta_s:.1f}s ({eta_s/60:.1f} min)")
        conn.close()
        return 0

    print(f"\n--apply: embedding {len(pending)} concepts in batches of {batch_size}...")
    t0 = time.time()
    done = 0
    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        names = [name for _cid, name in batch]
        ids = [cid for cid, _name in batch]
        vecs = provider.embed_batch(names)
        if vecs is None:
            print("ERROR: embed_batch returned None mid-run; aborting", file=sys.stderr)
            conn.close()
            return 2
        persist_batch(conn, ids, vecs, model)
        done += len(batch)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (len(pending) - done) / rate if rate > 0 else 0
        print(f"  {done}/{len(pending)}  ({rate:.0f}/s, ETA {eta:.0f}s)")

    final_existing = conn.execute(
        "SELECT COUNT(*) FROM concept_embeddings WHERE model = ?", (model,)
    ).fetchone()[0]
    print(f"\nDone in {time.time() - t0:.1f}s.")
    print(f"concept_embeddings rows for model {model}: {existing} -> {final_existing}")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-compute K.2 embeddings for existing concepts")
    parser.add_argument("--db", default=str(REPO_ROOT / ".muninn" / "mycelium.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max", type=int, default=None, help="cap (debug); default = all")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pick one: --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply are mutually exclusive")
    return run(Path(args.db), apply=args.apply, batch_size=args.batch_size, max_concepts=args.max)


if __name__ == "__main__":
    sys.exit(main())
