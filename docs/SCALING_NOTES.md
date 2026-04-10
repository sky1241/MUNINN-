# Muninn Scaling Notes

> Compiled 2026-04-10 by Sky + Claude. Quick reference for "does Muninn scale"
> questions. Honest assessment, no hype.

---

## TL;DR

| Scale | Verdict | Bottleneck if any |
|---|---|---|
| **1 dev** | ✅ Trivially fine | None |
| **10 devs (local-first)** | ✅ Fine | None |
| **30 devs (local-first)** | ✅ Fine | None |
| **30-50 devs (shared meta on NAS)** | ⚠️ Risky | SQLite WAL on networked FS |
| **50-500 devs** | ⚠️ Needs work | Need PostgreSQL backend for meta |
| **500+ devs** | 🚫 Not yet | Need read replicas + distributed lock |

**Today's Muninn is shippable for up to ~50 devs in local-first mode** (each
dev has their own `.muninn/`, sync via git). Beyond that, see the phases below.

---

## What the WAL Monitor actually solves

`engine/core/wal_monitor.py` (109 lines) is a SQLite WAL adaptive checkpoint
manager. In plain English:

SQLite with WAL mode writes all changes to a temp file (`.db-wal`) before
merging into the real DB. Fast and safe — but if nobody triggers a checkpoint,
the WAL grows unbounded. Like a toilet bowl filling without flushing.

The WAL Monitor is the smart flush:
- **PASSIVE checkpoint** (line 95): doesn't block ongoing writers, takes what
  it can and moves on.
- **Adaptive threshold** (line 27): if checkpoints are slow, flush more
  often in smaller batches. If fast, wait longer.
- **Emergency threshold** (line 25): force flush at ~200 MB regardless.
- **Read-only WAL size check** (line 52): reads the WAL file header directly
  to count frames without triggering a side-effect mini-checkpoint.

**What it solves**: a single-process Muninn writing fast won't accidentally
balloon the WAL to gigabytes.

**What it does NOT solve**: multi-process concurrency, networked filesystems,
or contention on a shared meta-mycelium.

---

## The 3 real risks at scale

### Risk 1 — WAL on networked filesystems (NFS, SMB, OneDrive, NAS)

SQLite WAL mode is **documented to behave incorrectly** on networked FS
because the locking primitives (POSIX advisory locks) are unreliable across
machines. Two devs writing to the same `meta_mycelium.db` over SMB can
corrupt the WAL.

**The WAL Monitor doesn't help** — this is a filesystem-level locking
problem, not a size problem.

**Mitigation**:
- Don't put the meta-mycelium on a NAS / SMB share / cloud sync folder.
- Either keep it local-only and sync via git push/pull, or move to a real
  database server (PostgreSQL or LiteFS-backed SQLite).

### Risk 2 — Writer starvation under high concurrency

SQLite WAL allows N concurrent readers + 1 writer at a time. If 120 devs
read the meta in parallel, the 1 writer waits for all readers to drain
between operations. At scale, the writer becomes very slow, even blocked.

**The WAL Monitor doesn't help** — this is intrinsic SQLite single-writer
behavior.

**Mitigation**:
- For shared meta with many writers: PostgreSQL (true MVCC multi-writer)
  or LiteFS (SQLite-API but distributed).
- For local-first sync via git: no concurrent writers, no problem.

### Risk 3 — Checkpoint contention (silent slowdown)

If 5 devs run Muninn against a shared meta SQLite, all 5 WAL Monitors will
try to checkpoint in parallel. PASSIVE checkpoints don't block writers, but
they themselves get blocked by active writers. Result: each checkpoint
flushes fewer pages, the WAL keeps growing despite the monitor.

**The WAL Monitor's emergency threshold (200 MB) catches this** before
it crashes — but performance degrades silently before that.

**Mitigation**:
- Designate a single "checkpoint master" via distributed lock (file-based
  with heartbeat, ~50 lines Python). Only one process at a time runs the
  WAL Monitor for the shared meta.
- Or move checkpoint logic to a dedicated background daemon.

---

## Phase plan for selling Muninn at scale

### Phase 1 — Today's Muninn (up to ~50 devs)

**Mode**: local-first, each dev has their own `.muninn/`, sync via git.

**Required**: nothing new. The current code already supports this.

**Pitch**: "Each developer gets a memory engine that learns their codebase.
Sync via git to share team knowledge. No central server, no admin overhead."

**Vendable demain.**

### Phase 2 — Up to ~500 devs (shared backend)

**Mode**: local Muninn per dev + central PostgreSQL for meta-mycelium.

**Required work** (~1 week of effort):
1. Add `MyceliumDBPostgres` class implementing the same interface as
   `MyceliumDB` (the SQLite version).
2. `~/.muninn/config.json` gets a `backend: postgres` option with connection
   string.
3. The PreToolUse hooks and the local Muninn engine remain unchanged — they
   only touch the local SQLite.
4. Document the PostgreSQL setup in `docs/INSTALL_TEAM.md`.

**Estimated cost**: 1 week of dev. Single dependency added (`psycopg2`).

### Phase 3 — 500+ devs (multi-region, audit, compliance)

**Required work** (~1 month of effort):
1. Read replicas of meta-mycelium for query load
2. Distributed lock for the WAL Monitor / checkpoint master
3. Audit trail hooks (Notification, PostToolUse Edit) for compliance —
   **already added in chunk 15** below
4. Multi-region sync with eventual consistency
5. Per-team isolation in the shared meta

**Estimated cost**: 1 month, multiple new components. At this scale you're
selling multiple licenses, so it pays for itself.

---

## What was added in chunk 15 (this commit)

3 new hooks coded but **NOT activated by default**. They are scaffolding
for the Phase 3 enterprise pitch. Sky decides when to activate them.

| Hook | Purpose | When to activate |
|---|---|---|
| `notification_audit_hook.py` | Append every Claude Code notification (permission_prompt, idle_prompt, auth_success) to `.muninn/audit_log.jsonl` | When you need a compliance audit trail (SOC 2, ISO 27001) |
| `post_tool_use_edit_log.py` | Log every successful Edit/Write to `.muninn/edits_log.jsonl` with file, byte counts, timestamp | When you need to detect drift, count lines/session, or trigger linters |
| `config_change_hook.py` | When `.claude/settings.local.json` or `.claude/rules/*.md` change, log + ping Muninn for re-validation | Multi-dev teams editing shared config |

These hooks are **fail-safe**: if they crash, exit 0, no impact on Claude.
They are **append-only and capped** (10 000 entries max each, oldest dropped).

**Activation**: edit `.claude/settings.local.json` to add the entries (see
the hook docstrings for the exact JSON snippet) or run
`python engine/core/muninn.py install --enable-extras` (when implemented).

---

## Honest verdict for Sky's pitch

**For 1-50 devs**: ship today. Local-first + git sync. The WAL Monitor +
the existing 9 hooks are enough.

**For 50-500 devs**: 1 week of work to add PostgreSQL backend. Vendable then.

**For 500+ devs**: 1 month of work for full enterprise. Sell this when you
have a paying customer asking for it, not before.

**The WAL Monitor itself is fine.** It's not the bottleneck. The bottleneck
at scale is "shared SQLite is wrong tool for shared meta", and the answer
is "swap the backend, keep the code".

---

## References

- SQLite WAL mode docs: https://www.sqlite.org/wal.html
- Why WAL doesn't work on NFS: https://www.sqlite.org/lockingv3.html
- LiteFS (distributed SQLite): https://fly.io/docs/litefs/
- Turso (managed SQLite): https://turso.tech/
- PostgreSQL MVCC: https://www.postgresql.org/docs/current/mvcc-intro.html
