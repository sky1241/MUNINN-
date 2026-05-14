#!/usr/bin/env python3
"""Migrate existing mycelium concepts through the K.1 static lexicon.

K.1 (shipped 2026-05-13) added an offline FR->EN dict that normalizes new
observations at write time. The pre-K.1 stock kept its French names. This
script retrofits the K.1 normalization onto the existing concepts:

  1. Load every concept name from .muninn/mycelium.db.
  2. Ask ConceptTranslator.normalize_concepts([name]) for each.
  3. If translated != original, that concept is a migration candidate.
  4. For each candidate group (new_name -> list of old_ids):
     a) If new_name not yet a concept -> RENAME the row.
     b) If new_name already a concept -> MERGE the FR concept into it
        (edges + fusions + edge_zones + tombstones + failures all
        redirect a/b from FR_id to EN_id, then DELETE the FR concept).

Usage:
  python3 scripts/migrate_k1_normalize_mycelium.py --dry-run
  python3 scripts/migrate_k1_normalize_mycelium.py --apply
  python3 scripts/migrate_k1_normalize_mycelium.py --db /path/mycelium.db --apply

The --dry-run mode reports stats without writing. --apply is destructive
(rule 2: confirm-before-destructive — caller's responsibility to backup).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.core.mycelium_db import ConceptTranslator  # noqa: E402


# Tables in mycelium.db whose primary key contains (a, b) concept ids and
# that need to be redirected during a merge. Order matters: edges first
# (largest), then secondary tables.
ID_REDIRECT_TABLES = ("edges", "fusions", "edge_zones", "tombstones", "failures")


def collect_concepts(conn: sqlite3.Connection) -> dict[int, str]:
    return {row[0]: row[1] for row in conn.execute("SELECT id, name FROM concepts")}


def plan_migrations(translator: ConceptTranslator, concepts: dict[int, str]) -> dict[str, list[int]]:
    """Return {new_name: [old_id, ...]} for every concept whose K.1 lookup
    yields a different lowercase name. Concepts that translate to themselves
    are skipped."""
    plan: dict[str, list[int]] = defaultdict(list)
    for cid, name in concepts.items():
        if not name:
            continue
        normalized = translator.normalize_concepts([name])[0]
        if normalized and normalized != name.lower().strip():
            plan[normalized].append(cid)
    return plan


def merge_into(conn: sqlite3.Connection, src_id: int, dst_id: int) -> dict[str, int]:
    """Redirect every row referencing src_id (in a or b) to dst_id, then
    DELETE the src concept. Returns counts per table for the report."""
    counts: dict[str, int] = {}
    cur = conn.cursor()

    for table in ID_REDIRECT_TABLES:
        if table == "edges":
            # Special handling: merge (count, first_seen, last_seen) on conflict.
            counts[table] = _merge_edges(cur, src_id, dst_id)
        elif table == "failures":
            counts[table] = _merge_failures(cur, src_id, dst_id)
        elif table == "fusions":
            counts[table] = _merge_fusions(cur, src_id, dst_id)
        else:
            counts[table] = _merge_simple(cur, table, src_id, dst_id)

    cur.execute("DELETE FROM concepts WHERE id = ?", (src_id,))
    return counts


def _merge_edges(cur: sqlite3.Cursor, src: int, dst: int) -> int:
    """Redirect edges from src to dst; combine count + first_seen/last_seen."""
    moved = 0
    # Process edges where src is in column a
    rows = cur.execute(
        "SELECT b, count, first_seen, last_seen FROM edges WHERE a = ?",
        (src,),
    ).fetchall()
    for b, count, fs, ls in rows:
        target_b = dst if b == src else b  # self-loop guard
        if target_b == dst:
            # FR self-loop or FR -> FR becomes EN -> EN; treat as self-edge
            target_b = dst
        existing = cur.execute(
            "SELECT count, first_seen, last_seen FROM edges WHERE a = ? AND b = ?",
            (dst, target_b),
        ).fetchone()
        if existing:
            new_count = existing[0] + count
            new_fs = min(existing[1], fs)
            new_ls = max(existing[2], ls)
            cur.execute(
                "UPDATE edges SET count = ?, first_seen = ?, last_seen = ? WHERE a = ? AND b = ?",
                (new_count, new_fs, new_ls, dst, target_b),
            )
        else:
            cur.execute(
                "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                (dst, target_b, count, fs, ls),
            )
        moved += 1
    cur.execute("DELETE FROM edges WHERE a = ?", (src,))

    # Process edges where src is in column b
    rows = cur.execute(
        "SELECT a, count, first_seen, last_seen FROM edges WHERE b = ?",
        (src,),
    ).fetchall()
    for a, count, fs, ls in rows:
        if a == src:
            continue  # already handled above
        target_a = a
        existing = cur.execute(
            "SELECT count, first_seen, last_seen FROM edges WHERE a = ? AND b = ?",
            (target_a, dst),
        ).fetchone()
        if existing:
            new_count = existing[0] + count
            new_fs = min(existing[1], fs)
            new_ls = max(existing[2], ls)
            cur.execute(
                "UPDATE edges SET count = ?, first_seen = ?, last_seen = ? WHERE a = ? AND b = ?",
                (new_count, new_fs, new_ls, target_a, dst),
            )
        else:
            cur.execute(
                "INSERT INTO edges (a, b, count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                (target_a, dst, count, fs, ls),
            )
        moved += 1
    cur.execute("DELETE FROM edges WHERE b = ?", (src,))
    return moved


def _merge_failures(cur: sqlite3.Cursor, src: int, dst: int) -> int:
    """Same idea as edges but for (count INTEGER, weight_sum REAL, first/last)."""
    moved = 0
    for col in ("a", "b"):
        other = "b" if col == "a" else "a"
        rows = cur.execute(
            f"SELECT {other}, count, weight_sum, first_seen, last_seen FROM failures WHERE {col} = ?",
            (src,),
        ).fetchall()
        for other_id, cnt, wsum, fs, ls in rows:
            target = dst if other_id == src else other_id
            new_pk = (dst, target) if col == "a" else (target, dst)
            existing = cur.execute(
                "SELECT count, weight_sum, first_seen, last_seen FROM failures WHERE a = ? AND b = ?",
                new_pk,
            ).fetchone()
            if existing:
                cur.execute(
                    "UPDATE failures SET count = ?, weight_sum = ?, first_seen = ?, last_seen = ? WHERE a = ? AND b = ?",
                    (existing[0] + cnt, existing[1] + wsum, min(existing[2], fs), max(existing[3], ls), *new_pk),
                )
            else:
                cur.execute(
                    "INSERT INTO failures (a, b, count, weight_sum, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                    (new_pk[0], new_pk[1], cnt, wsum, fs, ls),
                )
            moved += 1
        cur.execute(f"DELETE FROM failures WHERE {col} = ?", (src,))
    return moved


def _merge_fusions(cur: sqlite3.Cursor, src: int, dst: int) -> int:
    """Fusions PK is (a, b). On conflict keep max(strength), latest fused_at."""
    moved = 0
    for col in ("a", "b"):
        other = "b" if col == "a" else "a"
        rows = cur.execute(
            f"SELECT {other}, form, strength, fused_at FROM fusions WHERE {col} = ?",
            (src,),
        ).fetchall()
        for other_id, form, strength, fused_at in rows:
            target = dst if other_id == src else other_id
            new_pk = (dst, target) if col == "a" else (target, dst)
            existing = cur.execute(
                "SELECT strength, fused_at FROM fusions WHERE a = ? AND b = ?",
                new_pk,
            ).fetchone()
            if existing:
                cur.execute(
                    "UPDATE fusions SET strength = ?, fused_at = ? WHERE a = ? AND b = ?",
                    (max(existing[0], strength), max(existing[1], fused_at), *new_pk),
                )
            else:
                cur.execute(
                    "INSERT INTO fusions (a, b, form, strength, fused_at) VALUES (?, ?, ?, ?, ?)",
                    (new_pk[0], new_pk[1], form, strength, fused_at),
                )
            moved += 1
        cur.execute(f"DELETE FROM fusions WHERE {col} = ?", (src,))
    return moved


def _merge_simple(cur: sqlite3.Cursor, table: str, src: int, dst: int) -> int:
    """Redirect (a, b) where one of them is src. PK conflicts are silently
    ignored via INSERT OR IGNORE. Used for edge_zones and tombstones."""
    cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if not cols:
        return 0
    idx_a = cols.index("a")
    idx_b = cols.index("b")
    moved = 0
    for col in ("a", "b"):
        rows = cur.execute(f"SELECT {','.join(cols)} FROM {table} WHERE {col} = ?", (src,)).fetchall()
        for row in rows:
            row = list(row)
            row[idx_a] = dst if row[idx_a] == src else row[idx_a]
            row[idx_b] = dst if row[idx_b] == src else row[idx_b]
            placeholders = ",".join("?" * len(row))
            cur.execute(f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})", row)
            moved += 1
        cur.execute(f"DELETE FROM {table} WHERE {col} = ?", (src,))
    return moved


def run(db_path: Path, apply: bool) -> int:
    if not db_path.exists():
        print(f"ERROR: mycelium DB not found: {db_path}", file=sys.stderr)
        return 1

    translator = ConceptTranslator.get()
    print(f"K.1 static lexicon: {translator._static_dict_size} entries loaded")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")
    concepts = collect_concepts(conn)
    print(f"Mycelium concepts: {len(concepts)}")

    plan = plan_migrations(translator, concepts)
    print(f"Migration candidates: {sum(len(v) for v in plan.values())} concept(s) -> {len(plan)} target name(s)")

    # Classify
    name_to_id = {n.lower().strip(): cid for cid, n in concepts.items()}
    pure_renames = []   # (old_id, old_name, new_name)
    merges = []         # (src_id, src_name, dst_id, dst_name)
    for new_name, src_ids in plan.items():
        for src_id in src_ids:
            old_name = concepts[src_id]
            if new_name in name_to_id and name_to_id[new_name] != src_id:
                merges.append((src_id, old_name, name_to_id[new_name], new_name))
            else:
                pure_renames.append((src_id, old_name, new_name))

    print(f"  Pure renames (FR-only, no EN twin): {len(pure_renames)}")
    print(f"  Merges (FR + EN coexist, merge edges): {len(merges)}")

    # Sample preview
    if pure_renames:
        print("\nSample pure renames (up to 10):")
        for src_id, old, new in pure_renames[:10]:
            print(f"  [{src_id}] {old!r} -> {new!r}")
    if merges:
        print("\nSample merges (up to 20):")
        for src_id, old, dst_id, dst_name in merges[:20]:
            old_deg = conn.execute("SELECT COUNT(*) FROM edges WHERE a=? OR b=?", (src_id, src_id)).fetchone()[0]
            dst_deg = conn.execute("SELECT COUNT(*) FROM edges WHERE a=? OR b=?", (dst_id, dst_id)).fetchone()[0]
            print(f"  [{src_id}] {old!r} ({old_deg} edges) -> [{dst_id}] {dst_name!r} ({dst_deg} edges)")

    if not apply:
        print("\n--dry-run: no DB writes. Re-run with --apply to commit.")
        conn.close()
        return 0

    print("\n--apply: executing migration (atomic transaction)...")
    total_renames = 0
    total_merges = 0
    edge_moves = 0
    conn.execute("BEGIN")
    try:
      for src_id, old_name, new_name in pure_renames:
        try:
            conn.execute("UPDATE concepts SET name = ? WHERE id = ?", (new_name, src_id))
            total_renames += 1
        except sqlite3.IntegrityError:
            # New name appeared mid-loop -> treat as merge instead
            row = conn.execute("SELECT id FROM concepts WHERE name = ?", (new_name,)).fetchone()
            if row and row[0] != src_id:
                counts = merge_into(conn, src_id, row[0])
                edge_moves += counts.get("edges", 0)
                total_merges += 1

      for src_id, _old, dst_id, _new in merges:
        counts = merge_into(conn, src_id, dst_id)
        edge_moves += counts.get("edges", 0)
        total_merges += 1

      conn.commit()
    except Exception as exc:
      conn.rollback()
      print(f"\nABORT: migration failed mid-transaction, rolled back. Error: {exc}", file=sys.stderr)
      raise
    print(f"  {total_renames} concept(s) renamed")
    print(f"  {total_merges} concept(s) merged")
    print(f"  {edge_moves} edge row(s) redirected/combined")
    print("  VACUUM...")
    conn.execute("VACUUM")
    conn.close()
    print("Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrofit K.1 normalization on mycelium.db")
    parser.add_argument("--db", default=str(REPO_ROOT / ".muninn" / "mycelium.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pick one: --dry-run or --apply")
    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply are mutually exclusive")
    return run(Path(args.db), apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
